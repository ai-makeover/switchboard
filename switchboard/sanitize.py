"""Inbound text is attacker-controlled. Neutralise it before the model sees it.

- Links become "[link: domain.tld]", so there's no "click here" and no URL to append data to.
- Zero-width, bidi, tag and variation-selector characters are removed (they hide payloads).
- Long whitespace runs collapse (the published Invariant payload hid behind spaces).
- Every message is capped in length.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit

_HIDDEN = re.compile(
    "["
    "­"            # soft hyphen
    "؜"            # arabic letter mark
    "ᅟᅠㅤﾠ"  # hangul fillers (render blank)
    "᠎"            # mongolian vowel separator
    "​-‏"     # zero-width + LRM/RLM
    "‪-‮"     # bidi embeddings / overrides
    "⁠-⁤"     # word joiner, invisible operators
    "⁦-⁩"     # bidi isolates
    "⁪-⁯"     # deprecated format chars
    "︀-︎"     # variation selectors (FE0F kept: emoji presentation)
    "﻿"            # BOM / zero-width no-break space
    "\U000e0000-\U000e007f"  # tag characters
    "\U000e0100-\U000e01ef"  # supplementary variation selectors
    "]"
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_URL = re.compile(
    r"(?i)\b(?:(?:https?|ftp|file|data|javascript|mailto|tel|wa|whatsapp):[^\s<>\"')\]]+"
    r"|www\.[^\s<>\"')\]]+"
    r"|(?:[a-z0-9-]+\.)+(?:com|net|org|io|ai|co|app|dev|me|xyz|info|biz|ly|gl|to|link|site|online|"
    r"shop|store|page|live|tech|cc|tk|ru|cn|us|uk|nz|au|ae|in|de|fr)(?:/[^\s<>\"')\]]*)?)"
)
_SPACES = re.compile(r"[ \t  -   　]{3,}")
_NEWLINES = re.compile(r"\n{3,}")

MAX_MESSAGE_CHARS = 2000
MAX_NAME_CHARS = 80


def _domain(url: str) -> str:
    u = url if "://" in url or ":" in url.split("/")[0] else "http://" + url
    try:
        host = urlsplit(u).hostname or ""
    except ValueError:
        host = ""
    host = host.lower().removeprefix("www.")
    if not host:
        scheme = url.split(":", 1)[0].lower()
        return scheme or "unknown"
    return host[:60]


def strip_hidden(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = _HIDDEN.sub("", text)
    return _CONTROL.sub("", text)


def neutralise(text: str | None, limit: int = MAX_MESSAGE_CHARS) -> str:
    """For inbound text shown to the model."""
    if not text:
        return ""
    text = strip_hidden(text)
    text = _URL.sub(lambda m: f"[link: {_domain(m.group(0))}]", text)
    text = _SPACES.sub(" ", text)
    text = _NEWLINES.sub("\n\n", text).strip()
    if len(text) > limit:
        text = text[: limit - 1] + "… [truncated]"
    return text


def name(text: str | None) -> str:
    """Display names are inbound too (anyone can set a WhatsApp name)."""
    return neutralise(text, MAX_NAME_CHARS).replace("\n", " ")


def links_in(text: str) -> list[str]:
    """Domains linked from an outbound draft, so the confirm page can flag them."""
    return sorted({_domain(m.group(0)) for m in _URL.finditer(text or "")})
