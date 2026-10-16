"""ASGI entry point. ``uvicorn mp_mcp.asgi:app`` serves the MCP endpoint.

Importing this module is the Lambda cold start: the bearer token is fetched
from SSM here and cached for the life of the process (SR5).
"""

from __future__ import annotations

from mp_mcp.server import create_app

app = create_app()
