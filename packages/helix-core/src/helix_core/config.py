"""Configuration & secrets.

Precedence: CLI flags > env/.env > ~/.helix/config.toml > defaults (TSD §9).
Secrets come from the environment ONLY; never logged, never written into a strand.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import platformdirs


def _home() -> Path:
    return Path(os.environ.get("HELIX_HOME") or platformdirs.user_data_dir("helix"))


@dataclass(slots=True)
class Config:
    # --- storage ---
    home: Path = _home()

    # --- embeddings (default = local, $0) ---
    embeddings_provider: str = os.environ.get("HELIX_EMBEDDINGS_PROVIDER", "local")
    local_embed_model: str = os.environ.get("HELIX_LOCAL_EMBED_MODEL", "BAAI/bge-small-en-v1.5")

    # --- llm router (optional; used only for extraction/consolidation) ---
    llm_provider: str = os.environ.get("HELIX_LLM_PROVIDER", "none")  # none|gemini|openai
    gemini_model: str = os.environ.get("HELIX_GEMINI_MODEL", "gemini-2.0-flash")
    openai_model: str = os.environ.get("HELIX_OPENAI_MODEL", "gpt-4o-mini")

    # --- cost guardrails ---
    monthly_token_budget: int = int(os.environ.get("HELIX_MONTHLY_TOKEN_BUDGET", "0"))
    heuristic_confidence_cutoff: float = float(
        os.environ.get("HELIX_HEURISTIC_CONFIDENCE_CUTOFF", "0.75")
    )

    # --- privacy ---
    telemetry: str = os.environ.get("HELIX_TELEMETRY", "off")

    @property
    def gemini_api_key(self) -> str | None:
        return os.environ.get("GEMINI_API_KEY") or None

    @property
    def openai_api_key(self) -> str | None:
        return os.environ.get("OPENAI_API_KEY") or None

    @property
    def passphrase(self) -> str | None:
        return os.environ.get("HELIX_PASSPHRASE") or None

    def llm_enabled(self) -> bool:
        """True only if the user opted into a provider AND supplied a key."""
        if self.llm_provider == "gemini":
            return self.gemini_api_key is not None
        if self.llm_provider == "openai":
            return self.openai_api_key is not None
        return False


def load() -> Config:
    """Load config from env/defaults. (.env loading + config.toml merge added in Phase 1.)"""
    return Config()
