"""AWS Lambda Function URL adapter for the existing browser UI."""

from __future__ import annotations

import base64
import json
from typing import Any

from shopping_agent.ui.web import HTML_PAGE, ShoppingApplication


application = ShoppingApplication()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle the same routes served by the local standard-library server."""
    path = event.get("rawPath", "/")
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    headers = {str(key).lower(): value for key, value in event.get("headers", {}).items()}
    session_id = _cookie_session_id(headers.get("cookie", ""))

    if method == "GET" and path == "/":
        new_id, _ = application.get_session(session_id)
        return _response(HTML_PAGE, "text/html; charset=utf-8", new_id if new_id != session_id else None)

    if method == "GET" and path == "/api/state":
        new_id, session = application.get_session(session_id)
        return _json_response(application.view(session), new_id if new_id != session_id else None)

    if method == "POST" and path in {"/api/chat", "/api/reset"}:
        payload = _payload(event)
        new_id, session = application.get_session(session_id)
        if path == "/api/reset":
            new_id, session = application.reset(session_id)
            return _json_response(application.view(session), new_id if new_id != session_id else None)
        message = payload.get("message")
        if not isinstance(message, str):
            return _json_response({"error": "message must be a string."}, 400)
        return _json_response(application.send(session, message), new_id if new_id != session_id else None)

    return _json_response({"error": "Not found"}, 404)


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        value = json.loads(body)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _cookie_session_id(cookie_header: str) -> str | None:
    for part in cookie_header.split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == "shopping_session":
            return value
    return None


def _json_response(payload: dict[str, Any], session_id: str | int | None = None) -> dict[str, Any]:
    if isinstance(session_id, int):
        return _response(json.dumps(payload), "application/json; charset=utf-8", status=session_id)
    return _response(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8", session_id=session_id)


def _response(content: str, content_type: str, session_id: str | None = None, status: int = 200) -> dict[str, Any]:
    response: dict[str, Any] = {
        "statusCode": status,
        "headers": {"Content-Type": content_type, "Cache-Control": "no-store"},
        "body": content,
    }
    if session_id:
        response["cookies"] = [f"shopping_session={session_id}; Path=/; SameSite=Lax"]
    return response