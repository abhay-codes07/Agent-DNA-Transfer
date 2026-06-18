"""Configuration & secrets.

Precedence: CLI flags > real env vars > .env file > defaults (TSD §9).
Secrets come from the environment ONLY; never logged, never written into a strand.

Stdlib-only: no third-party imports, so the $0/offline core runs on a bare Python. Env-derived
fields use default_factory so they are read at *construction* time — which means a .env loaded
just before `Config()` takes effect.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def default_home() -> Path:
    """Where strands live by default. Honors HELIX_HOME, else an OS-appropriate data dir."""
    env = os.environ.get("HELIX_HOME")
    if env:
        return Path(env)
    base = (
        os.environ.get("APPDATA")  # Windows
        or os.environ.get("XDG_DATA_HOME")  # Linux
        or os.path.join(os.path.expanduser("~"), ".local", "share")
    )
    return Path(base) / "helix"


def load_dotenv(*paths: str | os.PathLike) -> None:
    """Minimal stdlib .env loader. Real env vars always win (set only if absent).

    Looks at the given paths, else `./.env` and `<HELIX_HOME>/.env`. Lines are KEY=VALUE;
    `#` comments and blank lines are ignored; surrounding quotes are stripped.
    """
    candidates = [Path(p) for p in paths] if paths else [Path.cwd() / ".env"]
    if not paths:
        home = os.environ.get("HELIX_HOME")
        if home:
            candidates.append(Path(home) / ".env")
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _env(key: str, default: str):
    return lambda: os.environ.get(key, default)


@dataclass(slots=True)
class Config:
    # --- storage ---
    home: Path = field(default_factory=default_home)
    strand: str = field(default_factory=_env("HELIX_STRAND", "default"))

    # --- embeddings (default = local; falls back to the dependency-free hashing embedder) ---
    embeddings_provider: str = field(default_factory=_env("HELIX_EMBEDDINGS_PROVIDER", "local"))
    local_embed_model: str = field(
        default_factory=_env("HELIX_LOCAL_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    )

    # --- llm router (optional; used only for extraction/consolidation) ---
    llm_provider: str = field(default_factory=_env("HELIX_LLM_PROVIDER", "none"))
    gemini_model: str = field(default_factory=_env("HELIX_GEMINI_MODEL", "gemini-2.0-flash"))
    openai_model: str = field(default_factory=_env("HELIX_OPENAI_MODEL", "gpt-4o-mini"))

    # --- cost guardrails ---
    monthly_token_budget: int = field(
        default_factory=lambda: int(os.environ.get("HELIX_MONTHLY_TOKEN_BUDGET", "0"))
    )
    heuristic_confidence_cutoff: float = field(
        default_factory=lambda: float(os.environ.get("HELIX_HEURISTIC_CONFIDENCE_CUTOFF", "0.75"))
    )

    # --- privacy ---
    telemetry: str = field(default_factory=_env("HELIX_TELEMETRY", "off"))

    @property
    def strand_path(self) -> Path:
        return self.home / f"{self.strand}.helix.db"

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
    """Load .env (if present) then build config from env/defaults."""
    load_dotenv()
    return Config()
