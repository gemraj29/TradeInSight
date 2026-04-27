"""Recovery Plan Generator.

Produces three outputs from analysis data:
1. Top loss-causing behaviors with estimated dollar impact
2. Rule suggestions to prevent repeat mistakes
3. "What-if" simulation: how much would have been saved by following each rule
4. Optional: Claude API narrative (if ANTHROPIC_API_KEY is configured)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.core.config import settings
from app.core.logging_setup import get_logger
from app.domain.models.behavior_flag import BehaviorFlag, BehaviorType, BEHAVIOR_LABELS
from app.domain.models.pnl import PnLSummary
from app.domain.models.trade_journey import JourneyOutcome, TradeJourney

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #

@dataclass
class BehaviorInsight:
    """A single behavior with its dollar impact and a prevention rule."""
    behavior_type: str
    label: str
    total_loss: float
    journey_count: int
    pct_of_total_loss: float
    rule: str
    what_if_savings: float


@dataclass
class RecoveryPlan:
    """The complete recovery plan for the account."""
    top_behaviors: List[BehaviorInsight] = field(default_factory=list)
    total_avoidable_loss: float = 0.0
    total_actual_loss: float = 0.0
    recovery_pct: float = 0.0
    suggested_rules: List[str] = field(default_factory=list)
    narrative: Optional[str] = None  # Claude-generated narrative if LLM enabled


# --------------------------------------------------------------------------- #
# Rule library
# --------------------------------------------------------------------------- #

BEHAVIOR_RULES: dict[str, str] = {
    BehaviorType.AVERAGING_DOWN.value: (
        "Never add to a losing long-option position. "
        "If the trade is wrong, exit — do not double down."
    ),
    BehaviorType.ROLLING_LOSER.value: (
        "Do not roll a losing option to a further expiry to 'save' the trade. "
        "Accept the loss and re-evaluate with fresh eyes."
    ),
    BehaviorType.NEAR_EXPIRY_HOLD.value: (
        f"Close or roll any long option position before it reaches "
        f"{settings.near_expiry_dte} DTE. Theta accelerates sharply in the final week."
    ),
    BehaviorType.OVERSIZED_POSITION.value: (
        f"Never risk more than {settings.oversize_pct}% of account value on a "
        f"single options trade. Size determines survival."
    ),
    BehaviorType.FOMO_ENTRY.value: (
        "Never chase a move. If the underlying has already moved significantly "
        "in your direction today, wait for the next setup."
    ),
    BehaviorType.LATE_EXIT.value: (
        "Set a hard stop-loss on all long options at 50% of purchase price. "
        "A small loss beats a near-total loss."
    ),
    BehaviorType.REPEAT_LOSER.value: (
        "After two consecutive losses on the same symbol, impose a cooling-off "
        "period of at least 30 days before trading it again."
    ),
}

# What-if multiplier: what fraction of the impact could have been avoided
AVOIDANCE_FACTOR: dict[str, float] = {
    BehaviorType.AVERAGING_DOWN.value: 0.70,      # 70% of add losses avoidable
    BehaviorType.ROLLING_LOSER.value: 0.60,
    BehaviorType.NEAR_EXPIRY_HOLD.value: 0.50,
    BehaviorType.OVERSIZED_POSITION.value: 0.40,
    BehaviorType.FOMO_ENTRY.value: 0.55,
    BehaviorType.LATE_EXIT.value: 0.50,
    BehaviorType.REPEAT_LOSER.value: 0.65,
}


# --------------------------------------------------------------------------- #
# Main generator
# --------------------------------------------------------------------------- #

def generate_recovery_plan(
    journeys: List[TradeJourney],
    pnl_summary: PnLSummary,
    behavior_flags: List[BehaviorFlag],
) -> RecoveryPlan:
    """Generate a complete recovery plan from analysis data.

    Args:
        journeys: All trade journeys.
        pnl_summary: Calculated P&L summary.
        behavior_flags: Detected behavior flags.

    Returns:
        RecoveryPlan with insights, rules, what-if savings, and optional narrative.
    """
    plan = RecoveryPlan()

    total_loss = abs(min(pnl_summary.total_realized_pnl, 0))
    if total_loss == 0 and pnl_summary.total_realized_pnl >= 0:
        # Use sum of individual losses
        total_loss = abs(sum(b.total_loss_impact for b in pnl_summary.by_behavior))

    plan.total_actual_loss = total_loss

    # Build behavior insights
    behavior_totals: dict[str, Tuple[float, int]] = {}
    for flag in behavior_flags:
        bt = flag.behavior_type.value
        if bt == BehaviorType.DISCIPLINED.value:
            continue
        impact, count = behavior_totals.get(bt, (0.0, 0))
        behavior_totals[bt] = (impact + flag.estimated_loss_impact, count + 1)

    insights = []
    total_avoidable = 0.0
    for bt, (impact, count) in sorted(behavior_totals.items(), key=lambda x: x[1][0]):
        pct = (abs(impact) / total_loss * 100) if total_loss > 0 else 0.0
        avoidance = AVOIDANCE_FACTOR.get(bt, 0.5)
        savings = abs(impact) * avoidance
        total_avoidable += savings

        insights.append(BehaviorInsight(
            behavior_type=bt,
            label=BEHAVIOR_LABELS.get(
                next((b for b in BehaviorType if b.value == bt), None), bt
            ),
            total_loss=impact,
            journey_count=count,
            pct_of_total_loss=pct,
            rule=BEHAVIOR_RULES.get(bt, "Review this trade pattern and develop a rule."),
            what_if_savings=savings,
        ))

    # Sort: worst impact first
    insights.sort(key=lambda i: i.total_loss)
    plan.top_behaviors = insights[:7]
    plan.total_avoidable_loss = total_avoidable
    plan.recovery_pct = (total_avoidable / total_loss * 100) if total_loss > 0 else 0.0

    # Suggested rules (top 5 behaviors → their rules)
    plan.suggested_rules = [i.rule for i in plan.top_behaviors[:5]]

    # Optional LLM narrative
    if settings.has_llm:
        plan.narrative = _generate_llm_narrative(plan, pnl_summary)

    return plan


def simulate_without_behavior(
    journeys: List[TradeJourney],
    behavior_flags: List[BehaviorFlag],
    behavior_type: str,
) -> Tuple[float, float]:
    """Simulate P&L if a specific behavior had been avoided.

    Args:
        journeys: All journeys.
        behavior_flags: All behavior flags.
        behavior_type: The behavior to exclude (e.g. "averaging_down").

    Returns:
        (simulated_pnl, saved_amount) tuple.
    """
    flagged_journeys = {
        f.journey_id for f in behavior_flags if f.behavior_type.value == behavior_type
    }
    avoidance = AVOIDANCE_FACTOR.get(behavior_type, 0.5)

    simulated_pnl = 0.0
    for j in journeys:
        if j.journey_id in flagged_journeys:
            # Assume partial recovery proportional to avoidance factor
            adjusted = j.realized_pnl * (1 - avoidance) if j.realized_pnl < 0 else j.realized_pnl
            simulated_pnl += adjusted
        else:
            simulated_pnl += j.realized_pnl

    actual_pnl = sum(j.realized_pnl for j in journeys)
    saved = simulated_pnl - actual_pnl

    return round(simulated_pnl, 2), round(saved, 2)


# --------------------------------------------------------------------------- #
# Optional LLM narrative
# --------------------------------------------------------------------------- #

def _generate_llm_narrative(plan: RecoveryPlan, pnl_summary: PnLSummary) -> Optional[str]:
    """Call Claude API to generate a personalized narrative for the recovery plan."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        behavior_summary = "\n".join(
            f"- {i.label}: ${abs(i.total_loss):,.2f} loss across {i.journey_count} trades "
            f"({i.pct_of_total_loss:.1f}% of total losses)"
            for i in plan.top_behaviors[:5]
        )

        prompt = f"""You are a trading coach analyzing a retail options trader's historical mistakes.

Here is their P&L summary:
- Total realized P&L: ${pnl_summary.total_realized_pnl:,.2f}
- Win rate: {pnl_summary.win_rate:.1f}%
- Average win: ${pnl_summary.avg_win:,.2f}
- Average loss: ${pnl_summary.avg_loss:,.2f}
- Total trades: {pnl_summary.total_trades}

Top behavioral mistakes detected:
{behavior_summary}

Estimated avoidable loss: ${plan.total_avoidable_loss:,.2f} ({plan.recovery_pct:.0f}% of total losses)

Write a concise (200-250 word), empathetic, actionable recovery narrative for this trader. Focus on:
1. The single most damaging pattern and WHY it's psychologically hard to avoid
2. One concrete, specific rule they should implement immediately
3. An encouraging note about what their winning trades reveal about their actual skill

Do not use bullet points. Write in a warm, direct coaching tone."""

        message = client.messages.create(
            model=settings.llm_model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text if message.content else None

    except ImportError:
        logger.warning("anthropic package not installed — skipping LLM narrative")
        return None
    except Exception as exc:
        logger.error("LLM narrative generation failed: %s", exc)
        return None
