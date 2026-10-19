"""Public JSON facade for the MCP quote tool, with an anonymous daily quota."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from typing import Any

import boto3
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

MCP_ENDPOINT = os.environ["MCP_ENDPOINT"]
AUTH_TOKEN_PARAM = os.getenv("SSM_AUTH_TOKEN_PARAM", "/mcp-server/auth-token")
QUOTA_TABLE = os.environ["QUOTA_TABLE_NAME"]
QUOTA_LIMIT = int(os.getenv("QUOTA_LIMIT", "5"))
QUOTA_WINDOW_SECONDS = int(os.getenv("QUOTA_WINDOW_SECONDS", "86400"))

_ssm = boto3.client("ssm")
_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(QUOTA_TABLE)
_auth_token: str | None = None


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
        },
        "body": json.dumps(body, ensure_ascii=False),
    }


def _token() -> str:
    global _auth_token
    if _auth_token is None:
        _auth_token = _ssm.get_parameter(Name=AUTH_TOKEN_PARAM, WithDecryption=True)[
            "Parameter"
        ]["Value"]
    return _auth_token


def _client_key(event: dict[str, Any]) -> str:
    source_ip = event.get("requestContext", {}).get("http", {}).get("sourceIp")
    if not source_ip:
        raise ValueError("Request source IP is unavailable")
    # Avoid persisting raw addresses in DynamoDB; the API Gateway source is trusted.
    return hashlib.sha256(source_ip.encode()).hexdigest()


def _window(now: int) -> tuple[int, int]:
    if QUOTA_WINDOW_SECONDS < 1:
        raise ValueError("QUOTA_WINDOW_SECONDS must be positive")
    window_id = now // QUOTA_WINDOW_SECONDS
    return window_id, (window_id + 1) * QUOTA_WINDOW_SECONDS


def _quota_item(client_key: str, window_id: int) -> dict[str, Any]:
    response = _table.get_item(
        Key={"client_key": client_key, "window_id": window_id}, ConsistentRead=True
    )
    return response.get("Item", {})


def _quota_view(count: int, reset_epoch: int) -> dict[str, Any]:
    return {
        "limit": QUOTA_LIMIT,
        "remaining": max(0, QUOTA_LIMIT - count),
        "resetAt": datetime.fromtimestamp(reset_epoch, UTC).isoformat(),
        "resetInSeconds": max(0, reset_epoch - int(time.time())),
    }


def _read_quota(client_key: str, now: int) -> dict[str, Any]:
    window_id, reset_epoch = _window(now)
    item = _quota_item(client_key, window_id)
    return _quota_view(int(item.get("usage_count", 0)), reset_epoch)


def _reserve_request(client_key: str, now: int) -> dict[str, Any] | None:
    """Atomically consume one use, returning quota when allowed, else None."""
    window_id, reset_epoch = _window(now)
    try:
        result = _table.update_item(
            Key={"client_key": client_key, "window_id": window_id},
            UpdateExpression=(
                "SET #count = if_not_exists(#count, :zero) + :one, "
                "expires_at = if_not_exists(expires_at, :expires)"
            ),
            ConditionExpression="attribute_not_exists(#count) OR #count < :limit",
            ExpressionAttributeNames={"#count": "usage_count"},
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":limit": QUOTA_LIMIT,
                ":expires": reset_epoch + QUOTA_WINDOW_SECONDS,
            },
            ReturnValues="UPDATED_NEW",
        )
    except _table.meta.client.exceptions.ConditionalCheckFailedException:
        return None

    count = int(result["Attributes"]["usage_count"])
    return _quota_view(count, reset_epoch)


async def _call_quote_tool(query: str) -> dict[str, Any]:
    http_client = create_mcp_http_client(headers={"Authorization": f"Bearer {_token()}"})
    async with http_client:
        async with streamable_http_client(
            MCP_ENDPOINT, http_client=http_client, terminate_on_close=False
        ) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool("find_quote", {"query": query})

    if result.isError:
        raise RuntimeError("MCP quote tool failed")
    text = next((item.text for item in result.content if item.type == "text"), "")
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {"quote": None, "speaker": None}


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object")
    return parsed


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    route = event.get("routeKey", "")
    try:
        client_key = _client_key(event)
    except ValueError as exc:
        return _response(400, {"error": str(exc)})

    now = int(time.time())
    if route == "GET /quota":
        try:
            return _response(200, {"quota": _read_quota(client_key, now)})
        except Exception:  # noqa: BLE001 - never leak AWS details to public callers
            return _response(503, {"error": "Quota service unavailable"})

    if route != "POST /quote":
        return _response(404, {"error": "Not found"})

    try:
        body = _parse_body(event)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return _response(400, {"error": "Request body must be valid JSON"})

    query = body.get("text")
    if not isinstance(query, str) or not query.strip() or len(query.strip()) > 20:
        return _response(400, {"error": "Enter text containing 1 to 20 characters"})
    query = query.strip()

    try:
        quota = _reserve_request(client_key, now)
    except Exception:  # noqa: BLE001 - fail closed so quota storage outages spend no tokens
        return _response(503, {"error": "Quota service unavailable"})
    if quota is None:
        try:
            current = _read_quota(client_key, now)
        except Exception:  # noqa: BLE001 - hide storage details from public callers
            return _response(503, {"error": "Quota service unavailable"})
        return _response(429, {"error": "daily_limit_reached", "quota": current})

    try:
        match = asyncio.run(_call_quote_tool(query))
    except Exception:  # noqa: BLE001 - don't return MCP, SSM, or provider internals
        return _response(502, {"error": "Quote matching is temporarily unavailable", "quota": quota})

    return _response(200, {"match": match, "quota": quota})
