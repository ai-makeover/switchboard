"""Unipile client for v1 (per-customer DSN) and v2 (api.unipile.com/v2). Normalises both into one shape.

Every id that reaches a URL path is validated first and then percent-encoded. Errors map to fixed
codes; the upstream response body is never surfaced.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings
from .errors import SBError

log = logging.getLogger("switchboard.unipile")

# Unipile v1 ids are url-safe base64-ish; v2 WhatsApp ids are JIDs like 123@s.whatsapp.net / 120...@g.us /
# ...@lid. No slash, percent, colon, query or whitespace can get through, and no dot-segments.
_RAW_ID = re.compile(r"^[A-Za-z0-9@._=+-]{1,200}$")
_PUBLIC_ID = re.compile(r"^(whatsapp|linkedin|instagram):([A-Za-z0-9@._=+-]{1,200})$")
_PHONE = re.compile(r"^\+?(\d{6,15})(?:@s\.whatsapp\.net|@c\.us)?$")
_V1_TYPES = {"whatsapp": "WHATSAPP", "linkedin": "LINKEDIN", "instagram": "INSTAGRAM"}


def check_raw(raw: str) -> str:
    if not isinstance(raw, str) or not _RAW_ID.match(raw) or ".." in raw or set(raw) <= {"."}:
        raise SBError("invalid_id")
    return raw


def parse_public_id(public: str) -> tuple[str, str]:
    m = _PUBLIC_ID.match(public or "")
    if not m:
        raise SBError("invalid_id")
    return m.group(1), check_raw(m.group(2))


def seg(raw: str) -> str:
    return quote(check_raw(raw), safe="@")


def phone_of(*candidates: Any) -> str | None:
    """A WhatsApp number, if one of the identifiers is a phone JID or a bare number. LIDs give None."""
    for c in candidates:
        if isinstance(c, str):
            m = _PHONE.match(c.strip())
            if m:
                return "+" + m.group(1)
    return None


class Unipile:
    def __init__(self, s: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.s = s
        self.v2 = s.unipile_version == "v2"
        self._client = httpx.AsyncClient(
            base_url=s.unipile_base,
            headers={"X-API-KEY": s.unipile_key, "accept": "application/json"},
            timeout=httpx.Timeout(30.0, connect=10.0),
            transport=transport,
            follow_redirects=False,
        )
        self._accounts: dict[str, str] = {}
        self._sem = asyncio.Semaphore(8)

    async def aclose(self):
        await self._client.aclose()

    # ---- transport -------------------------------------------------------------------------------

    async def _req(self, method: str, path: str, **kw) -> Any:
        try:
            async with self._sem:
                r = await self._client.request(method, path, **kw)
        except httpx.HTTPError as e:
            log.warning("unipile %s %s transport_error type=%s", method, path.split("?")[0].split("/")[1:3], type(e).__name__)
            raise SBError("upstream_error") from None
        if r.status_code >= 400:
            log.warning("unipile %s status=%s", method, r.status_code)
            if r.status_code in (401, 403):
                raise SBError("upstream_auth")
            if r.status_code == 404:
                raise SBError("not_found")
            if r.status_code == 429:
                raise SBError("upstream_rate_limited")
            raise SBError("upstream_error")
        if not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            raise SBError("upstream_error") from None

    @staticmethod
    def _items(page: dict) -> tuple[list, str | None]:
        if "data" in page:
            return page.get("data") or [], page.get("next_cursor")
        return page.get("items") or [], page.get("cursor")

    async def _paged(self, path: str, cap: int, page_size: int = 100) -> list:
        out: list = []
        cursor = None
        joiner = "&" if "?" in path else "?"
        while len(out) < cap:
            q = f"{path}{joiner}limit={min(page_size, cap - len(out))}"
            if cursor:
                q += "&cursor=" + quote(str(cursor), safe="")
            items, cursor = self._items(await self._req("GET", q))
            out.extend(items)
            if not cursor or not items:
                break
        return out[:cap]

    # ---- accounts --------------------------------------------------------------------------------

    async def account(self, channel: str) -> str:
        if channel not in self.s.enabled:
            raise SBError("channel_disabled")
        if channel in self._accounts:
            return self._accounts[channel]
        acc = self.s.account_ids.get(channel) or ""
        if not acc and not self.v2:
            # v1 only: find the single connected account of this type.
            page = await self._req("GET", "/api/v1/accounts")
            items, _ = self._items(page)
            hits = [a.get("id") for a in items if (a.get("type") or "").upper() == _V1_TYPES[channel]]
            if len(hits) == 1 and isinstance(hits[0], str):
                acc = hits[0]
        if not acc:
            raise SBError("account_not_configured")
        self._accounts[channel] = check_raw(acc)
        return self._accounts[channel]

    async def account_status(self, channel: str) -> dict:
        """Normalised link state: connected, needs_relink, provider_error, connecting, subscription_locked, unknown."""
        acc = await self.account(channel)
        if self.v2:
            a = await self._req("GET", f"/v2/accounts/{seg(acc)}")
            if a.get("is_locked"):
                return {"state": "subscription_locked"}
            st = str(a.get("status") or "").lower()
            state = {"running": "connected", "disconnected": "needs_relink", "partial": "needs_relink",
                     "errored": "provider_error", "degraded": "provider_error"}.get(st, "unknown")
            return {"state": state}
        a = await self._req("GET", f"/api/v1/accounts/{seg(acc)}")
        statuses = {str(x.get("status") or "").upper() for x in (a.get("sources") or []) if isinstance(x, dict)}
        if statuses & {"CREDENTIALS", "DELETED"}:
            state = "needs_relink"
        elif statuses & {"ERROR", "STOPPED"}:
            state = "provider_error"
        elif "CONNECTING" in statuses:
            state = "connecting"
        elif statuses and statuses <= {"OK", "SYNC_SUCCESS", "CREATION_SUCCESS", "RECONNECTED"}:
            state = "connected"
        else:
            state = "unknown"
        return {"state": state}

    # ---- chats -----------------------------------------------------------------------------------

    def _norm_chat(self, channel: str, c: dict) -> dict:
        if self.v2:
            user = c.get("user") or {}
            spec = user.get("specifics") or {}
            last = c.get("last_message") or {}
            is_group = bool(c.get("is_group")) or c.get("type") == "group"
            return {
                "raw": c.get("id"),
                "channel": channel,
                "name": (spec.get("contact_name") or user.get("display_name") or c.get("name")) if not is_group else c.get("name"),
                "is_group": is_group,
                "unread": int(c.get("unread_count") or 0),
                "last_at": c.get("last_message_timestamp") or last.get("timestamp"),
                "last_from_me": last.get("is_sender"),
                "last_text": last.get("text"),
                "peer_number": None if is_group else phone_of(user.get("public_identifier"), c.get("user_id")),
                "readonly": bool(c.get("is_readonly")),
                "account_id": None,
            }
        last = c.get("lastMessage") or {}
        is_group = c.get("type") in (1, 2)
        return {
            "raw": c.get("id"),
            "channel": channel,
            "name": c.get("name"),
            "is_group": is_group,
            "unread": int(c.get("unread_count") or 0),
            "last_at": c.get("timestamp"),
            "last_from_me": last.get("is_sender") if last else None,
            "last_text": last.get("text") if last else None,
            "peer_number": None if is_group else phone_of(c.get("attendee_public_identifier"), c.get("attendee_provider_id")),
            "readonly": bool(c.get("read_only")),
            "account_id": c.get("account_id"),
            "peer_provider_id": c.get("attendee_provider_id"),
        }

    async def list_chats(self, channel: str, cap: int, fill: bool = True) -> list[dict]:
        acc = await self.account(channel)
        if self.v2:
            rows = await self._paged(f"/v2/{seg(acc)}/chats", cap)
        else:
            rows = await self._paged(f"/api/v1/chats?account_id={quote(acc, safe='')}", cap)
        chats = [self._norm_chat(channel, c) for c in rows if isinstance(c, dict) and c.get("id")]
        if not self.v2 and fill:
            await self._fill_v1(chats)
        return chats

    async def v1_contact_names(self, channel: str) -> dict[str, str]:
        """v1 only: provider_id -> name for every known contact, in a few paged calls. Used to name DMs
        in bulk for search, instead of one attendees call per chat."""
        acc = await self.account(channel)
        rows = await self._paged(f"/api/v1/chat_attendees?account_id={quote(acc, safe='')}", 5000, 250)
        return {a["provider_id"]: a.get("name") for a in rows if isinstance(a, dict) and a.get("provider_id") and a.get("name")}

    async def get_chat(self, channel: str, raw: str) -> dict:
        acc = await self.account(channel)
        if self.v2:
            c = await self._req("GET", f"/v2/{seg(acc)}/chats/{seg(raw)}")
            return self._norm_chat(channel, c)
        c = await self._req("GET", f"/api/v1/chats/{seg(raw)}")
        chat = self._norm_chat(channel, c)
        # A v1 chat id is global, so make sure it belongs to this channel's account. Otherwise a
        # "whatsapp:" id could reach a LinkedIn chat even with LinkedIn switched off.
        if chat["account_id"] != acc:
            raise SBError("not_found")
        await self._fill_v1([chat])
        return chat

    async def _fill_v1(self, chats: list[dict]) -> None:
        """v1 leaves a DM's name as its raw JID and often omits the last message. Fill both."""

        async def fill(chat):
            try:
                if chat["last_from_me"] is None:
                    page = await self._req("GET", f"/api/v1/chats/{seg(chat['raw'])}/messages?limit=5")
                    items, _ = self._items(page)
                    m = next((m for m in items if not m.get("is_event")), None)
                    if m:
                        chat["last_from_me"] = bool(m.get("is_sender"))
                        chat["last_text"] = m.get("text") or _attachment_label(m)
                        chat["last_at"] = m.get("timestamp") or chat["last_at"]
                if not chat["is_group"] and (not chat["name"] or "@" in (chat["name"] or "")):
                    page = await self._req("GET", f"/api/v1/chats/{seg(chat['raw'])}/attendees")
                    items, _ = self._items(page)
                    peer = next((a for a in items if not a.get("is_self")), None)
                    if peer:
                        chat["name"] = peer.get("name") or chat["name"]
                        chat["peer_number"] = chat["peer_number"] or phone_of(peer.get("public_identifier"), peer.get("provider_id"))
            except SBError:
                pass  # a row with a raw label beats no row

        await asyncio.gather(*(fill(c) for c in chats))

    # ---- messages and members -------------------------------------------------------------------

    async def messages(self, channel: str, raw: str, n: int) -> list[dict]:
        acc = await self.account(channel)
        if self.v2:
            rows = await self._paged(f"/v2/{seg(acc)}/chats/{seg(raw)}/messages", n)
        else:
            await self.get_chat(channel, raw)  # account ownership check
            rows = await self._paged(f"/api/v1/chats/{seg(raw)}/messages", n)
        out = []
        for m in rows:
            if not isinstance(m, dict) or m.get("is_event"):
                continue
            sender = m.get("sender") or {}
            spec = sender.get("specifics") or {}
            out.append({
                "at": m.get("timestamp"),
                "from_me": bool(m.get("is_sender")),
                "sender": spec.get("contact_name") or sender.get("display_name") or m.get("sender_name"),
                "sender_id": m.get("sender_id"),
                "text": m.get("text"),
                "attachment": _attachment_label(m) if not m.get("text") else None,
            })
        return out

    async def members(self, channel: str, raw: str) -> list[dict]:
        acc = await self.account(channel)
        if self.v2:
            rows = await self._paged(f"/v2/{seg(acc)}/chats/{seg(raw)}/participants", 2000)
            out = []
            for p in rows:
                u = p.get("user") or {}
                spec = u.get("specifics") or {}
                out.append({
                    "name": u.get("display_name") or " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x),
                    "saved_as": spec.get("contact_name"),
                    "number": phone_of(u.get("public_identifier"), u.get("id")),
                    "is_admin": bool(p.get("is_admin")),
                    "is_self": bool(p.get("is_self")),
                })
            return out
        await self.get_chat(channel, raw)
        rows = await self._paged(f"/api/v1/chats/{seg(raw)}/attendees", 2000)
        out = []
        for a in rows:
            spec = a.get("specifics") or {}
            out.append({
                "name": a.get("name"),
                "saved_as": spec.get("contact_name") if isinstance(spec, dict) else None,
                "number": phone_of(a.get("public_identifier"), spec.get("phone_number") if isinstance(spec, dict) else None,
                                   a.get("provider_id")),
                "is_admin": bool((spec or {}).get("is_admin")) if isinstance(spec, dict) else False,
                "is_self": bool(a.get("is_self")),
            })
        return out

    # ---- the one send path (called only from the confirm page) ---------------------------------

    async def send(self, channel: str, raw: str, text: str) -> None:
        acc = await self.account(channel)
        if self.v2:
            await self._req("POST", f"/v2/{seg(acc)}/chats/{seg(raw)}/messages/send", json={"text": text})
        else:
            await self.get_chat(channel, raw)
            await self._req("POST", f"/api/v1/chats/{seg(raw)}/messages", data={"text": text})


def _attachment_label(m: dict) -> str | None:
    atts = m.get("attachments") or []
    if not atts:
        return None
    a = atts[0] if isinstance(atts[0], dict) else {}
    if a.get("voice_note"):
        return "(voice note)"
    kind = (a.get("type") or "file").lower()
    return f"({kind})"
