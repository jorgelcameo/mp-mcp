"""Fetch secrets from SSM Parameter Store, once per cold start (SR5).

Values are cached in module-level state so a warm Lambda invocation never pays
for another SSM call. Nothing here is ever logged (SR7).
"""

from __future__ import annotations

import threading

from mp_mcp.config import Settings

_cache: dict[str, str] = {}
_lock = threading.Lock()


def _ssm():
    import boto3

    return boto3.client("ssm")


def get_secure_parameter(name: str) -> str:
    """Return a SecureString parameter, cached for the life of the process."""
    with _lock:
        cached = _cache.get(name)
        if cached is not None:
            return cached

        response = _ssm().get_parameter(Name=name, WithDecryption=True)
        value = response["Parameter"]["Value"]
        _cache[name] = value
        return value


def get_auth_token(settings: Settings) -> str:
    """The bearer token every request must present (SR2, SR3)."""
    return get_secure_parameter(settings.auth_token_param)


def get_anthropic_api_key(settings: Settings) -> str:
    """Anthropic API key, for tools that call the model (SR3, SR6).

    Unused until the Section 11 tools are implemented, but wired now so the
    parameter path is exercised end to end.
    """
    return get_secure_parameter(settings.anthropic_api_key_param)
