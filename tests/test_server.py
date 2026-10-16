"""End-to-end HTTP tests against the real MCP app (no AWS calls).

The token is injected through ``create_app``, so these run offline.
"""

from __future__ import annotations

import json

import pytest
from starlette.testclient import TestClient

from mp_mcp.server import create_app

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MCP_HEADERS = {
    **AUTH,
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


@pytest.fixture
def client() -> TestClient:
    app = create_app(auth_token=TOKEN, extra_allowed_hosts=["testserver"])
    with TestClient(app) as test_client:
        yield test_client


def rpc(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    body: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        body["params"] = params
    return body


def test_missing_token_is_401(client: TestClient) -> None:
    response = client.post("/mcp", json=rpc("ping"))
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_wrong_token_is_401(client: TestClient) -> None:
    headers = {**MCP_HEADERS, "Authorization": "Bearer nope"}
    response = client.post("/mcp", json=rpc("ping"), headers=headers)
    assert response.status_code == 401


def test_health_is_open(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_initialize_and_list_tools(client: TestClient) -> None:
    init = client.post(
        "/mcp",
        json=rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        ),
        headers=MCP_HEADERS,
    )
    assert init.status_code == 200, init.text

    listed = client.post("/mcp", json=rpc("tools/list"), headers=MCP_HEADERS)
    assert listed.status_code == 200, listed.text
    names = [tool["name"] for tool in listed.json()["result"]["tools"]]
    assert "ping" in names


def test_call_ping(client: TestClient) -> None:
    called = client.post(
        "/mcp",
        json=rpc("tools/call", {"name": "ping", "arguments": {}}),
        headers=MCP_HEADERS,
    )
    assert called.status_code == 200, called.text
    body = called.json()
    assert body["result"]["isError"] is False
    assert "pong" in json.dumps(body["result"])
