import pytest

from iaiep.config import ConfigError, LLMSettings


def test_reads_settings_from_environment() -> None:
    settings = LLMSettings.from_env(
        {"LLM_BASE_URL": "http://llm:11434/v1", "LLM_MODEL": "qwen3:30b-a3b", "LLM_API_KEY": "secret"}
    )
    assert settings == LLMSettings("http://llm:11434/v1", "qwen3:30b-a3b", "secret")


def test_missing_variables_are_named() -> None:
    with pytest.raises(ConfigError, match="LLM_BASE_URL, LLM_MODEL"):
        LLMSettings.from_env({"LLM_MODEL": "  "})


def test_api_key_is_optional_and_never_shown() -> None:
    settings = LLMSettings.from_env({"LLM_BASE_URL": "http://llm/v1", "LLM_MODEL": "m"})
    assert settings.api_key == "not-set"
    assert "secret" not in repr(LLMSettings("u", "m", "secret"))
