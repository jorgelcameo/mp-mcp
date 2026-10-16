"""mp-mcp — remote MCP server for AWS Lambda."""

from __future__ import annotations

import logging
import os


def main() -> None:
    """Local dev runner: ``mp-mcp`` serves the app with uvicorn.

    Against real AWS secrets (``ssm:GetParameter`` on the two parameters), so run
    it with credentials that can read them::

        AWS_PROFILE=personal-dev uv run mp-mcp
    """
    import uvicorn

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")

    port = int(os.getenv("AWS_LWA_PORT") or os.getenv("PORT") or "8080")
    uvicorn.run("mp_mcp.asgi:app", host="0.0.0.0", port=port, log_level="info")


__all__ = ["main"]
