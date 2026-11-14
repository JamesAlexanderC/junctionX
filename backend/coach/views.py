"""POST /api/chat/: the coach as a Server-Sent Events stream.

Body: ``{"customer_id": str, "messages": [{"role", "content"}]}``. Each event
is one ``data: <json>\\n\\n`` line (contract in docs/design.md); ``meta`` is
always first and ``done`` always last.
"""

from __future__ import annotations

import json
import logging

from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from finance import services
from finance.models import Customer

from .providers import get_provider
from .tools import CoachContext

log = logging.getLogger(__name__)

MAX_MESSAGES = 20
MAX_CONTENT = 2000
MAX_ID = 32
ROLES = {"user", "assistant"}


class BadRequest(ValueError):
    pass


def sse(event):
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def parse_body(raw):
    """Validate the request body; returns ``(customer_id, messages)``."""
    try:
        body = json.loads(raw or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise BadRequest("Body must be JSON.")
    if not isinstance(body, dict):
        raise BadRequest("Body must be a JSON object.")
    customer_id = body.get("customer_id")
    if not isinstance(customer_id, str) or not 0 < len(customer_id) <= MAX_ID:
        raise BadRequest("customer_id is required.")
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise BadRequest("messages must be a non-empty list.")
    clean = []
    # Keep the most recent turns only.
    for m in messages[-MAX_MESSAGES:]:
        if not isinstance(m, dict) or m.get("role") not in ROLES:
            raise BadRequest("Each message needs a role of user or assistant.")
        content = m.get("content")
        if not isinstance(content, str):
            raise BadRequest("Each message needs a text content.")
        clean.append({"role": m["role"], "content": content[:MAX_CONTENT]})
    if clean[-1]["role"] != "user" or not clean[-1]["content"].strip():
        raise BadRequest("The last message must be a non-empty user message.")
    return customer_id.strip(), clean


def _stream(events):
    response = StreamingHttpResponse(
        (sse(e) for e in events), content_type="text/event-stream"
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _error_stream(provider, message, status):
    events = [
        {"type": "meta", "provider": provider.name, "model": provider.model},
        {"type": "error", "message": message},
        {"type": "done"},
    ]
    response = _stream(events)
    response.status_code = status
    return response


def _events(provider, ctx, messages):
    yield {"type": "meta", "provider": provider.name, "model": provider.model}
    try:
        yield from provider.stream(ctx, messages)
    except Exception:  # noqa: BLE001 - report instead of cutting the stream
        log.exception("Coach provider %s failed", provider.name)
        yield {
            "type": "error",
            "message": "Sorry, something went wrong while answering.",
        }
    yield {"type": "done"}


@csrf_exempt
@require_POST
def chat(request):
    provider = get_provider()
    try:
        customer_id, messages = parse_body(request.body)
    except BadRequest as exc:
        return _error_stream(provider, str(exc), 400)
    try:
        data = services.load_customer(customer_id)
    except Customer.DoesNotExist:
        return _error_stream(provider, f"Unknown customer {customer_id}", 404)
    return _stream(_events(provider, CoachContext(data), messages))
