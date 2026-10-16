"""Unit tests for environment-driven configuration."""

from __future__ import annotations

import pytest

from mp_mcp.config import DEFAULT_AUTH_TOKEN_PARAM, Settings


def test_defaults_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("ALLOWED_HOSTS", "ALLOWED_ORIGINS", "SSM_AUTH_TOKEN_PARAM"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.auth_token_param == DEFAULT_AUTH_TOKEN_PARAM
    assert settings.allowed_hosts == ["localhost", "127.0.0.1"]
    assert settings.dns_rebinding_protection is True


def test_star_disables_dns_rebinding_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_HOSTS", "*")

    settings = Settings.from_env()

    assert settings.allowed_hosts == []
    assert settings.dns_rebinding_protection is False


def test_explicit_hosts_keep_protection_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_HOSTS", "abc123.lambda-url.us-east-2.on.aws, localhost")

    settings = Settings.from_env()

    assert settings.allowed_hosts == ["abc123.lambda-url.us-east-2.on.aws", "localhost"]
    assert settings.dns_rebinding_protection is True
