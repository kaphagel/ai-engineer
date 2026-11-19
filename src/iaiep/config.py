"""Runtime configuration read from environment variables.

Endpoints, models and keys are never hard-coded (spec §27.2); they come from the environment
(the Dev Container sets them from docker-compose.yml and the git-ignored .env).
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


class ConfigError(RuntimeError):
    """Required configuration is missing or invalid."""


@dataclass(frozen=True)
class LLMSettings:
    """Connection to an OpenAI-compatible model endpoint (ADR-0002, D-16)."""

    base_url: str
    model: str
    # Ollama accepts any non-empty key; cloud providers need a real one.
    api_key: str = field(repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LLMSettings":
        env = os.environ if env is None else env
        required = ("LLM_BASE_URL", "LLM_MODEL")
        missing = [name for name in required if not env.get(name, "").strip()]
        if missing:
            raise ConfigError(f"Missing environment variables: {', '.join(missing)}")
        return cls(
            base_url=env["LLM_BASE_URL"].strip(),
            model=env["LLM_MODEL"].strip(),
            api_key=env.get("LLM_API_KEY", "").strip() or "not-set",
        )
