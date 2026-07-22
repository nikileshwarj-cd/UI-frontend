# ============================================================
# config.py — Centralised configuration loader
# All settings come from .env / environment variables.
# ============================================================

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (the directory containing config.py)
_ROOT = Path(__file__).parent
load_dotenv(_ROOT / ".env", override=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require(key: str) -> str:
    """Read a required env var; exit with a clear message if missing."""
    val = os.getenv(key, "").strip()
    if not val:
        print(
            f"\n[CONFIG ERROR] Environment variable '{key}' is not set.\n"
            f"  → Copy .env.example to .env and fill in your values.\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return val


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _get_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _get_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    # Groq
    groq_api_key: str = field(default_factory=lambda: _require("GROQ_API_KEY"))

    # Models — loaded lazily so tests can override env before import
    vision_model: str = field(
        default_factory=lambda: _get(
            "VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
        )
    )
    code_model: str = field(
        default_factory=lambda: _get("CODE_MODEL", "llama-3.3-70b-versatile")
    )

    # Output
    output_language: str = field(
        default_factory=lambda: _get("OUTPUT_LANGUAGE", "tsx").lower()
    )
    output_dir: Path = field(
        default_factory=lambda: _ROOT / _get("OUTPUT_DIR", "output")
    )

    # Web UI
    ui_host: str = field(default_factory=lambda: _get("UI_HOST", "127.0.0.1"))
    ui_port: int = field(default_factory=lambda: _get_int("UI_PORT", 5000))
    ui_debug: bool = field(default_factory=lambda: _get_bool("UI_DEBUG", False))

    # Agent behaviour
    max_json_retries: int = field(
        default_factory=lambda: _get_int("MAX_JSON_RETRIES", 3)
    )

    # Paths
    project_root: Path = field(default_factory=lambda: _ROOT)
    input_dir: Path = field(default_factory=lambda: _ROOT / "input")
    prompts_dir: Path = field(default_factory=lambda: _ROOT / "prompts")

    def __post_init__(self) -> None:
        # Validate output language
        if self.output_language not in ("tsx", "jsx"):
            print(
                f"[CONFIG WARNING] OUTPUT_LANGUAGE='{self.output_language}' is not "
                f"recognised. Defaulting to 'tsx'.",
                file=sys.stderr,
            )
            self.output_language = "tsx"

        # Ensure core directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.input_dir / "images").mkdir(parents=True, exist_ok=True)
        (self.input_dir / "user_stories").mkdir(parents=True, exist_ok=True)

    @property
    def file_extension(self) -> str:
        """Return the file extension for React components (tsx or jsx)."""
        return self.output_language  # 'tsx' or 'jsx'

    @property
    def is_typescript(self) -> bool:
        return self.output_language == "tsx"

    def __repr__(self) -> str:
        return (
            f"Settings("
            f"vision_model={self.vision_model!r}, "
            f"code_model={self.code_model!r}, "
            f"output_language={self.output_language!r}, "
            f"output_dir={self.output_dir}, "
            f"ui_port={self.ui_port}"
            f")"
        )


# ---------------------------------------------------------------------------
# Singleton — import this everywhere
# ---------------------------------------------------------------------------

settings = Settings()
