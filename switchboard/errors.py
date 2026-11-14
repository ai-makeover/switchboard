"""Fixed error codes. A tool result never carries exception text: an upstream error can echo a URL,
a header or a key, and the model reads tool results."""
from __future__ import annotations

import functools
import logging

from fastmcp.exceptions import ToolError

log = logging.getLogger("switchboard")

CODES = {
    "invalid_id": "That id isn't valid. Use an id returned by inbox, waiting_on_me or search_contacts.",
    "invalid_argument": "An argument is out of range.",
    "channel_disabled": "That channel isn't enabled on this server.",
    "account_not_configured": "No account is configured for that channel.",
    "not_found": "Not found.",
    "chat_readonly": "That chat doesn't accept messages.",
    "not_a_group": "That chat isn't a group.",
    "text_empty": "The draft text is empty.",
    "text_too_long": "The draft is too long (4000 characters max).",
    "draft_rate_limited": "Too many drafts this hour. Try again later.",
    "unipile_key_missing": "No Unipile API key is set on the server yet. Paste it into Railway > Variables > UNIPILE_API_KEY.",
    "upstream_auth": "The messaging provider rejected the server's credentials.",
    "upstream_rate_limited": "The messaging provider is rate limiting. Try again shortly.",
    "upstream_error": "The messaging provider returned an error.",
    "not_allowed": "Not allowed.",
    "internal_error": "Internal error.",
}


class SBError(Exception):
    """An error with a fixed public code. Never put upstream text in it."""

    def __init__(self, code: str):
        assert code in CODES, code
        super().__init__(code)
        self.code = code


def tool_error(code: str) -> ToolError:
    return ToolError(f"{code}: {CODES[code]}")


def guarded(fn):
    """Wrap a tool so any failure surfaces as a fixed code. The real exception is logged by type
    only (its message can carry upstream text)."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except SBError as e:
            log.info("tool=%s error=%s", fn.__name__, e.code)
            raise tool_error(e.code) from None
        except Exception as e:  # noqa: BLE001
            log.error("tool=%s internal_error type=%s", fn.__name__, type(e).__name__)
            raise tool_error("internal_error") from None

    return wrapper
