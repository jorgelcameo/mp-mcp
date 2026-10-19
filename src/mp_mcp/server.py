"""The MCP server: tools live here, plus the ASGI app factory.

Transport is Streamable HTTP in **stateless** mode with JSON responses (FR1-FR3),
which is what lets this run on Lambda with no session state between invocations.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from mp_mcp.config import Settings
from mp_mcp.middleware import AccessLogMiddleware, BearerAuthMiddleware
from mp_mcp.secrets import get_auth_token

INSTRUCTIONS = (
    "A remote MCP server for the Max Payne fan tribute. It can find a thematically "
    "relevant quote from its curated v1 collection."
)

mcp = MCPServer("mp-mcp", instructions=INSTRUCTIONS, version="0.1.0")


@mcp.tool(
    description="Liveness check. Returns 'pong'; use it to verify the server answers.",
)
def ping() -> str:
    """Placeholder tool — Section 11 of the spec (SPEC.md) defines the real ones."""
    return "pong"


@mcp.tool(
    description=(
        "Match a short text (up to 20 characters) to the closest quote in the curated Max Payne "
        "collection. Returns the quote, speaker, source, and brief reason, or a no-match result."
    ),
)
async def find_quote(query: str) -> str:
    """Select the closest known quote without generating new quote text."""
    from mp_mcp.quote_matcher import find_best_quote

    return await find_best_quote(query)


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    """Readiness probe for the Lambda Web Adapter. Unauthenticated on purpose."""
    return JSONResponse({"status": "ok"})


def create_app(
    *,
    auth_token: str | None = None,
    settings: Settings | None = None,
    extra_allowed_hosts: list[str] | None = None,
) -> Starlette:
    """Build the ASGI app.

    ``auth_token`` is injected in tests; in production it is read from SSM at
    cold start (SR3, SR5).
    """
    settings = settings or Settings.from_env()
    token = auth_token if auth_token is not None else get_auth_token(settings)

    allowed_hosts = list(settings.allowed_hosts)
    for host in extra_allowed_hosts or []:
        if host not in allowed_hosts:
            allowed_hosts.append(host)

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=settings.dns_rebinding_protection,
        allowed_hosts=allowed_hosts,
        allowed_origins=settings.allowed_origins,
    )

    app: Starlette = mcp.streamable_http_app(
        json_response=True,
        stateless_http=True,
        transport_security=security,
    )

    # Order matters: wrapping inward-out means CORS answers preflights before the
    # bearer check ever runs, and the access log still sees rejected requests.
    app = BearerAuthMiddleware(app, token)
    app = AccessLogMiddleware(app)
    app = CORSMiddleware(
        app,
        allow_origins=settings.allowed_origins or ["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
    )
    return app
