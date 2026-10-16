"""ASGI middleware: bearer-token auth (SR2) and one structured log line per request.

Both run before any tool code. Neither logs tokens, keys, or request bodies (SR7).
"""

from __future__ import annotations

import hmac
import json
import logging
import time
from collections import deque

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("mp_mcp.access")

_UNAUTHORIZED = b'{"error":"unauthorized"}'
_JSON_HEADERS = [(b"content-type", b"application/json")]

_BEARER = "Bearer "


class BearerAuthMiddleware:
    """Reject any request without ``Authorization: Bearer <token>`` with a 401.

    The comparison is constant time (SR2). The Function URL has ``AuthType: NONE``
    (SR1) because MCP clients cannot sign SigV4, so this is the only gate.

    ``open_paths`` exempts endpoints that must answer without a token, such as the
    readiness probe the Lambda Web Adapter calls during cold start.
    """

    def __init__(
        self,
        app: ASGIApp,
        token: str,
        open_paths: tuple[str, ...] = ("/health",),
    ) -> None:
        if not token:
            raise ValueError("auth token must not be empty")
        self.app = app
        self._expected = (_BEARER + token).encode()
        self._open_paths = open_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope["path"] in self._open_paths:
            await self.app(scope, receive, send)
            return

        if not self._authorized(scope):
            await self._reject(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _authorized(self, scope: Scope) -> bool:
        for key, value in scope["headers"]:
            if key == b"authorization":
                return hmac.compare_digest(value, self._expected)
        return False

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = [*_JSON_HEADERS, (b"www-authenticate", b"Bearer")]
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": _UNAUTHORIZED})


class AccessLogMiddleware:
    """Emit one structured JSON log line per request (Section 9).

    The JSON-RPC method and, for ``tools/call``, the tool name are best-effort
    extracted from a JSON body. The body itself is never logged.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        replay, payload = await self._buffered_body(receive)

        status = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        error: str | None = None
        try:
            await self.app(scope, replay, send_wrapper)
        except Exception as exc:  # noqa: BLE001 - re-raised after logging
            error = type(exc).__name__
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            record = {
                "event": "request",
                "method": scope["method"],
                "path": scope["path"],
                "status": status,
                "duration_ms": duration_ms,
                "rpc_method": payload.get("rpc_method"),
                "tool": payload.get("tool"),
                "client": payload.get("client"),
            }
            if error:
                record["error"] = error
            logger.info(json.dumps(record, separators=(",", ":")))

    async def _buffered_body(self, receive: Receive) -> tuple[Receive, dict[str, str | None]]:
        payload: dict[str, str | None] = {"rpc_method": None, "tool": None, "client": None}
        messages: deque[Message] = deque()

        while True:
            message = await receive()
            if message["type"] != "http.request":
                messages.append(message)
                break
            messages.append(message)
            if not message.get("more_body", False):
                break

        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.request")
        payload.update(_inspect(body))

        async def replay() -> Message:
            if messages:
                return messages.popleft()
            return await receive()

        return replay, payload


def _inspect(body: bytes) -> dict[str, str | None]:
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}

    rpc_method = parsed.get("method")
    result: dict[str, str | None] = {}
    if isinstance(rpc_method, str):
        result["rpc_method"] = rpc_method

    params = parsed.get("params")
    if isinstance(params, dict):
        if rpc_method == "tools/call":
            name = params.get("name")
            if isinstance(name, str):
                result["tool"] = name
        if rpc_method == "initialize":
            client_info = params.get("clientInfo")
            if isinstance(client_info, dict):
                name = client_info.get("name")
                if isinstance(name, str):
                    result["client"] = name
    return result
