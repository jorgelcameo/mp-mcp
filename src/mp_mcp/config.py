"""Runtime configuration, read from environment variables.

No secrets live here: the bearer token and the Anthropic API key are SSM
parameter *names* (see :mod:`mp_mcp.secrets`), never values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_AUTH_TOKEN_PARAM = "/mcp-server/auth-token"
DEFAULT_ANTHROPIC_KEY_PARAM = "/mcp-server/anthropic-api-key"

DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1")


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Process-wide settings resolved from the environment."""

    auth_token_param: str = DEFAULT_AUTH_TOKEN_PARAM
    anthropic_api_key_param: str = DEFAULT_ANTHROPIC_KEY_PARAM
    allowed_hosts: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_HOSTS))
    allowed_origins: list[str] = field(default_factory=list)
    dns_rebinding_protection: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        hosts, protection = _parse_allowed_hosts(os.getenv("ALLOWED_HOSTS"))
        return cls(
            auth_token_param=os.getenv("SSM_AUTH_TOKEN_PARAM", DEFAULT_AUTH_TOKEN_PARAM),
            anthropic_api_key_param=os.getenv(
                "SSM_ANTHROPIC_KEY_PARAM", DEFAULT_ANTHROPIC_KEY_PARAM
            ),
            allowed_hosts=hosts,
            allowed_origins=_split_csv(os.getenv("ALLOWED_ORIGINS")),
            dns_rebinding_protection=protection,
        )


def _parse_allowed_hosts(raw: str | None) -> tuple[list[str], bool]:
    """Resolve ``ALLOWED_HOSTS`` into (hosts, dns_rebinding_protection).

    - unset: localhost only, protection on — the right default for local dev.
    - ``*``: protection off. The Lambda Function URL hostname is only known after
      the first deploy, so the stack opts out and relies on the bearer token (SR2).
    - otherwise: exact hostnames, protection on.
    """
    if raw is None:
        return list(DEFAULT_ALLOWED_HOSTS), True
    hosts = _split_csv(raw)
    if "*" in hosts:
        return [], False
    return hosts or list(DEFAULT_ALLOWED_HOSTS), True
