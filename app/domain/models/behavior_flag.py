"""Domain model for a detected behavioral mistake flag."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BehaviorType(str, Enum):
    """Enumeration of all detectable trading behavior patterns."""
    AVERAGING_DOWN = "averaging_down"
    ROLLING_LOSER = "rolling_loser"
    NEAR_EXPIRY_HOLD = "near_expiry_hold"
    OVERSIZED_POSITION = "oversized_position"
    FOMO_ENTRY = "fomo_entry"
    LATE_EXIT = "late_exit"
    REPEAT_LOSER = "repeat_loser"
    DISCIPLINED = "disciplined"  # positive flag — correct behavior


BEHAVIOR_LABELS: dict[BehaviorType, str] = {
    BehaviorType.AVERAGING_DOWN: "Averaging Down",
    BehaviorType.ROLLING_LOSER: "Rolling a Loser",
    BehaviorType.NEAR_EXPIRY_HOLD: "Held Near Expiry",
    BehaviorType.OVERSIZED_POSITION: "Oversized Position",
    BehaviorType.FOMO_ENTRY: "FOMO Entry",
    BehaviorType.LATE_EXIT: "Late Exit (let it bleed)",
    BehaviorType.REPEAT_LOSER: "Repeat Loser (same symbol)",
    BehaviorType.DISCIPLINED: "Disciplined Exit",
}

BEHAVIOR_DESCRIPTIONS: dict[BehaviorType, str] = {
    BehaviorType.AVERAGING_DOWN: (
        "Added contracts to a losing position at least twice, increasing cost basis "
        "and risk instead of exiting or reducing."
    ),
    BehaviorType.ROLLING_LOSER: (
        "Closed a losing option position and immediately opened a replacement in a "
        "further expiry, deferring the loss rather than accepting it."
    ),
    BehaviorType.NEAR_EXPIRY_HOLD: (
        "Held an options position into the final days before expiry, where theta "
        "decay is steepest and recovery chance is lowest."
    ),
    BehaviorType.OVERSIZED_POSITION: (
        "Position size exceeded the configured account-size threshold, concentrating "
        "risk in a single trade."
    ),
    BehaviorType.FOMO_ENTRY: (
        "Entered a directional trade after a large move had already occurred in the "
        "same direction — likely chasing momentum."
    ),
    BehaviorType.LATE_EXIT: (
        "Exited a long option after it had already lost most of its value, "
        "rather than cutting the loss at a sensible stop-loss level."
    ),
    BehaviorType.REPEAT_LOSER: (
        "Lost money on the same underlying symbol three or more times, suggesting "
        "a recurring mistake or bias toward a specific ticker."
    ),
    BehaviorType.DISCIPLINED: (
        "Exited the position following a disciplined rule — cut loss at plan, "
        "or took profit at target."
    ),
}


@dataclass
class BehaviorFlag:
    """A single detected behavior flag for a trade journey.

    Attributes:
        journey_id: The journey this flag belongs to.
        behavior_type: Which behavior was detected.
        severity: 1 (low) to 3 (high).
        estimated_loss_impact: Approximate dollar amount attributable to this behavior.
        detail: Human-readable explanation for this specific journey.
        evidence: Short data evidence string (e.g. "3 adds: +10 @ $3.45, +5 @ $2.10, +5 @ $1.35").
    """

    journey_id: str
    behavior_type: BehaviorType
    severity: int  # 1 = low, 2 = medium, 3 = high
    estimated_loss_impact: float = 0.0
    detail: str = ""
    evidence: str = ""

    @property
    def label(self) -> str:
        """Human-readable label for this behavior type."""
        return BEHAVIOR_LABELS.get(self.behavior_type, self.behavior_type.value)

    @property
    def description(self) -> str:
        """Generic description of what this behavior means."""
        return BEHAVIOR_DESCRIPTIONS.get(self.behavior_type, "")

    @property
    def severity_label(self) -> str:
        """Return Low / Medium / High string."""
        return {1: "Low", 2: "Medium", 3: "High"}.get(self.severity, "Unknown")
