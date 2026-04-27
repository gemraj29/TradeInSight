"""Application configuration loaded from environment variables / .env file."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings:
    """Central settings object — read once at startup."""

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'tradein_sight.db'}"
    )

    # Optional LLM
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    llm_model: str = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Behavior thresholds
    avg_down_threshold: int = int(os.getenv("AVG_DOWN_THRESHOLD", "2"))
    near_expiry_dte: int = int(os.getenv("NEAR_EXPIRY_DTE", "7"))
    oversize_pct: float = float(os.getenv("OVERSIZE_PCT", "10"))
    fomo_move_pct: float = float(os.getenv("FOMO_MOVE_PCT", "5"))
    max_account_size: float = float(os.getenv("MAX_ACCOUNT_SIZE", "100000"))

    # Derived helpers
    @property
    def has_llm(self) -> bool:
        """Return True if an Anthropic API key is configured."""
        return bool(self.anthropic_api_key)

    @property
    def data_dir(self) -> Path:
        """Absolute path to the data directory."""
        d = BASE_DIR / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def sample_csv_path(self) -> Path:
        """Path to the bundled sample Fidelity CSV."""
        return BASE_DIR / "data" / "sample" / "fidelity_sample.csv"


settings = Settings()
