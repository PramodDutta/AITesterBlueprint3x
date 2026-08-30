"""Configuration loading, validation and readiness reporting."""

from __future__ import annotations

import os

import pytest

from jira_qa_crew.config import AuthMode, IntegrationMode, MCPTransport, Settings
from jira_qa_crew.exceptions import ConfigurationError


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("JIRA_QA_CREW_SKIP_DOTENV", "1")
    for key in list(os.environ):
        if key.startswith(("JIRA_", "LLM_", "PIPELINE_", "DEMO_", "APP_", "OUTPUT_")):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("JIRA_QA_CREW_SKIP_DOTENV", "1")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))


def load() -> Settings:
    return Settings.load()


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------
def test_defaults_are_sane_with_an_empty_environment():
    settings = load()
    assert settings.app_name == "Jira QA Crew"
    assert settings.jira_integration_mode is IntegrationMode.AUTO
    assert settings.jira_auth_mode is AuthMode.BASIC
    assert settings.jira_mcp_transport is MCPTransport.STREAMABLE_HTTP
    assert settings.pipeline_max_tickets == 20
    assert settings.demo_mode is False


def test_a_missing_environment_is_not_fatal():
    """The app must start and explain itself rather than crash on boot."""
    settings = load()
    assert settings.llm_ready() is False
    assert settings.blocking_problems()


def test_deepseek_key_is_accepted_as_the_llm_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-123456")
    assert load().llm_api_key == "sk-deepseek-123456"


# --------------------------------------------------------------------------
# Validation of values that are present but wrong
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("LLM_TEMPERATURE", "not-a-number"),
        ("LLM_TEMPERATURE", "9.5"),
        ("PIPELINE_MAX_TICKETS", "0"),
        ("PIPELINE_MAX_TICKETS", "abc"),
        ("JIRA_INTEGRATION_MODE", "carrier-pigeon"),
        ("JIRA_AUTH_MODE", "magic"),
        ("JIRA_MCP_TRANSPORT", "telepathy"),
        ("JIRA_MCP_ARGS_JSON", "{not json}"),
        ("JIRA_MCP_ARGS_JSON", '{"not":"a list"}'),
        ("JIRA_MCP_HEADERS_JSON", "[1,2,3]"),
        ("JIRA_KEY_PATTERN", "([unclosed"),
    ],
)
def test_bad_values_raise_an_actionable_configuration_error(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ConfigurationError) as exc:
        load()
    assert key in str(exc.value), "the message must name the setting that is wrong"


def test_enum_errors_list_the_allowed_values(monkeypatch):
    monkeypatch.setenv("JIRA_INTEGRATION_MODE", "nope")
    with pytest.raises(ConfigurationError, match="auto, mcp, rest"):
        load()


# --------------------------------------------------------------------------
# Readiness
# --------------------------------------------------------------------------
def test_rest_readiness_requires_url_and_credentials(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://example.atlassian.net")
    assert load().rest_ready() is False

    monkeypatch.setenv("JIRA_EMAIL", "qa@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token-123456789")
    assert load().rest_ready() is True


def test_bearer_readiness_ignores_email(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_AUTH_MODE", "bearer")
    assert load().rest_ready() is False
    monkeypatch.setenv("JIRA_BEARER_TOKEN", "bearer-123456789")
    assert load().rest_ready() is True


def test_mcp_readiness_depends_on_the_transport(monkeypatch):
    monkeypatch.setenv("JIRA_MCP_TRANSPORT", "stdio")
    assert load().mcp_ready() is False
    monkeypatch.setenv("JIRA_MCP_COMMAND", "npx")
    assert load().mcp_ready() is True

    monkeypatch.setenv("JIRA_MCP_TRANSPORT", "streamable_http")
    monkeypatch.delenv("JIRA_MCP_COMMAND")
    assert load().mcp_ready() is False
    monkeypatch.setenv("JIRA_MCP_URL", "https://mcp.example.com/mcp")
    assert load().mcp_ready() is True


def test_mcp_only_mode_complains_when_mcp_is_unconfigured(monkeypatch):
    monkeypatch.setenv("JIRA_INTEGRATION_MODE", "mcp")
    monkeypatch.setenv("LLM_API_KEY", "sk-123456789")
    problems = " ".join(load().blocking_problems())
    assert "mcp" in problems.lower()
    assert "JIRA_MCP_URL" in problems


def test_rest_only_mode_complains_when_rest_is_unconfigured(monkeypatch):
    monkeypatch.setenv("JIRA_INTEGRATION_MODE", "rest")
    monkeypatch.setenv("LLM_API_KEY", "sk-123456789")
    problems = " ".join(load().blocking_problems())
    assert "rest" in problems.lower()


def test_auto_mode_complains_only_when_neither_provider_is_configured(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-123456789")
    assert any("neither MCP nor REST" in p for p in load().blocking_problems())

    monkeypatch.setenv("JIRA_MCP_URL", "https://mcp.example.com/mcp")
    assert load().blocking_problems() == []


def test_demo_mode_needs_no_provider_configuration(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    assert load().blocking_problems() == []


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_boolean_parsing_accepts_the_usual_spellings(monkeypatch, value):
    monkeypatch.setenv("DEMO_MODE", value)
    assert load().demo_mode is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "anything-else"])
def test_boolean_parsing_defaults_to_false(monkeypatch, value):
    monkeypatch.setenv("DEMO_MODE", value)
    assert load().demo_mode is False


def test_trailing_slash_is_stripped_from_the_jira_url(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://example.atlassian.net/")
    assert load().jira_url == "https://example.atlassian.net"


def test_skip_dotenv_means_a_local_env_file_cannot_change_behaviour(tmp_path, monkeypatch):
    """Guards test isolation and explicit container configuration."""
    env_file = tmp_path / "sneaky.env"
    env_file.write_text("APP_NAME=Hijacked\n")
    monkeypatch.setenv("JIRA_QA_CREW_SKIP_DOTENV", "1")
    assert Settings.load(env_file).app_name == "Jira QA Crew"

    monkeypatch.delenv("JIRA_QA_CREW_SKIP_DOTENV")
    assert Settings.load(env_file).app_name == "Hijacked"


def test_secrets_property_ignores_short_or_empty_values(monkeypatch):
    monkeypatch.setenv("JIRA_API_TOKEN", "abc")  # too short to redact usefully
    monkeypatch.setenv("LLM_API_KEY", "sk-a-real-looking-key-123")
    secrets = load().secrets
    assert "abc" not in secrets
    assert "sk-a-real-looking-key-123" in secrets


def test_structured_output_mode_defaults_to_auto():
    from jira_qa_crew.config import StructuredOutputMode

    assert load().llm_structured_output is StructuredOutputMode.AUTO


@pytest.mark.parametrize("value", ["auto", "schema", "prompt"])
def test_structured_output_mode_accepts_each_mode(monkeypatch, value):
    monkeypatch.setenv("LLM_STRUCTURED_OUTPUT", value)
    assert load().llm_structured_output.value == value


def test_an_unknown_structured_output_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_STRUCTURED_OUTPUT", "telepathy")
    with pytest.raises(ConfigurationError, match="auto, schema, prompt"):
        load()
