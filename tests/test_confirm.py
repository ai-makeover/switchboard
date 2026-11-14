"""The confirm page is the only send path."""
import re
import time

import pytest
from fastmcp import Client
from starlette.testclient import TestClient

from switchboard.auth import SESSION_COOKIE


async def make_draft(mcp, chat="whatsapp:chatDM1", text="Hi Ann, see you at 3"):
    async with Client(mcp) as c:
        r = await c.call_tool("draft_reply", {"chat_id": chat, "text": text})
    url = r.structured_content["confirm_url"]
    return url.split("/confirm/")[1], r.structured_content


def client(mcp, s, ident="owner"):
    tc = TestClient(mcp.http_app(path="/mcp", stateless_http=True), base_url=s.base_url, follow_redirects=False)
    if ident:
        tc.cookies.set(SESSION_COOKIE, mcp._switchboard["web"].session_cookie(ident))
    return tc


def csrf_of(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


async def test_page_shows_text_name_and_number(harness):
    mcp, fake, db, s, _ = harness("v1")
    token, _ = await make_draft(mcp, text="Hi <b>Ann</b>, see https://cal.example.com/x")
    with client(mcp, s) as tc:
        r = tc.get(f"/confirm/{token}")
    assert r.status_code == 200
    assert "Ann Smith" in r.text and "+15550001111" in r.text
    assert "Hi &lt;b&gt;Ann&lt;/b&gt;" in r.text  # escaped, shown in full
    assert "cal.example.com" in r.text and "Contains a link" in r.text
    assert r.headers["cache-control"] == "no-store"
    assert fake.sent == []


async def test_signed_out_or_stranger_goes_to_login(harness):
    mcp, fake, db, s, _ = harness("v1")
    token, _ = await make_draft(mcp)
    for ident in (None, "jesse@example.com"):
        with client(mcp, s, ident) as tc:
            r = tc.get(f"/confirm/{token}")
            assert r.status_code == 302 and r.headers["location"].startswith("/login?next=/confirm/")
            r = tc.post(f"/confirm/{token}", data={"action": "send", "csrf": "x"})
            assert r.status_code == 401
    assert fake.sent == []


async def test_send_once_then_token_dead(harness):
    mcp, fake, db, s, _ = harness("v1")
    token, d = await make_draft(mcp)
    with client(mcp, s) as tc:
        csrf = csrf_of(tc.get(f"/confirm/{token}").text)
        r = tc.post(f"/confirm/{token}", data={"action": "send", "csrf": csrf})
        assert r.status_code == 200 and "Sent" in r.text
        assert fake.sent == [("chatDM1", "Hi Ann, see you at 3")]
        r = tc.post(f"/confirm/{token}", data={"action": "send", "csrf": csrf})
        assert "already sent" in r.text
        r = tc.get(f"/confirm/{token}")
        assert "already sent" in r.text
    assert len(fake.sent) == 1
    row = db.db.execute("SELECT text, status FROM drafts WHERE id=?", (d["draft_id"],)).fetchone()
    assert row["status"] == "sent" and row["text"] is None  # content wiped after send


async def test_csrf_required(harness):
    mcp, fake, db, s, _ = harness("v1")
    token, _ = await make_draft(mcp)
    with client(mcp, s) as tc:
        r = tc.post(f"/confirm/{token}", data={"action": "send", "csrf": "forged"})
        assert r.status_code == 400
        r = tc.get(f"/confirm/{token}?action=send")
        assert "Confirm" in r.text
    assert fake.sent == []


async def test_send_gap_enforced(harness):
    mcp, fake, db, s, _ = harness("v1")
    t1, _ = await make_draft(mcp, text="one")
    t2, _ = await make_draft(mcp, text="two")
    with client(mcp, s) as tc:
        tc.post(f"/confirm/{t1}", data={"action": "send", "csrf": csrf_of(tc.get(f"/confirm/{t1}").text)})
        r = tc.post(f"/confirm/{t2}", data={"action": "send", "csrf": csrf_of(tc.get(f"/confirm/{t2}").text)})
        assert "pacing limit" in r.text
        assert fake.sent == [("chatDM1", "one")]
        # once the gap has passed it goes
        db.db.execute("UPDATE sends SET at = at - 41")
        r = tc.post(f"/confirm/{t2}", data={"action": "send", "csrf": csrf_of(tc.get(f"/confirm/{t2}").text)})
        assert "Sent" in r.text
    assert [t for _, t in fake.sent] == ["one", "two"]


async def test_daily_cap(harness):
    mcp, fake, db, s, _ = harness("v1", WHATSAPP_SENDS_PER_DAY="2", WHATSAPP_MIN_GAP_SECONDS="0", WHATSAPP_SENDS_PER_HOUR="100")
    now = time.time()
    db.record_send("whatsapp", now - 7200)
    db.record_send("whatsapp", now - 3600)
    token, _ = await make_draft(mcp)
    with client(mcp, s) as tc:
        r = tc.post(f"/confirm/{token}", data={"action": "send", "csrf": csrf_of(tc.get(f"/confirm/{token}").text)})
    assert "pacing limit" in r.text and fake.sent == []


async def test_discard(harness):
    mcp, fake, db, s, _ = harness("v1")
    token, _ = await make_draft(mcp)
    with client(mcp, s) as tc:
        r = tc.post(f"/confirm/{token}", data={"action": "discard", "csrf": csrf_of(tc.get(f"/confirm/{token}").text)})
        assert "Discarded" in r.text
        assert "discarded" in tc.get(f"/confirm/{token}").text
    assert fake.sent == []


async def test_expired(harness):
    mcp, fake, db, s, _ = harness("v1")
    token, d = await make_draft(mcp)
    db.db.execute("UPDATE drafts SET expires_at = ?", (time.time() - 1,))
    with client(mcp, s) as tc:
        assert "expired" in tc.get(f"/confirm/{token}").text
    assert db.db.execute("SELECT text FROM drafts").fetchone()[0] is None


async def test_failed_send_is_not_retried(harness):
    mcp, fake, db, s, _ = harness("v1")
    token, _ = await make_draft(mcp)
    with client(mcp, s) as tc:
        csrf = csrf_of(tc.get(f"/confirm/{token}").text)
        fake.fail_with = 500
        r = tc.post(f"/confirm/{token}", data={"action": "send", "csrf": csrf})
        assert r.status_code == 502 and "boom" not in r.text
        fake.fail_with = None
        assert "failed" in tc.get(f"/confirm/{token}").text
    assert fake.sent == []


async def test_bad_token(harness):
    mcp, fake, db, s, _ = harness("v1")
    with client(mcp, s) as tc:
        assert tc.get("/confirm/nope").status_code == 404


@pytest.mark.parametrize("version", ["v2"])
async def test_v2_send_path(harness, version):
    mcp, fake, db, s, _ = harness(version)
    token, _ = await make_draft(mcp, chat="whatsapp:15550001111@s.whatsapp.net", text="hello v2")
    with client(mcp, s) as tc:
        r = tc.post(f"/confirm/{token}", data={"action": "send", "csrf": csrf_of(tc.get(f"/confirm/{token}").text)})
    assert "Sent" in r.text
    assert fake.sent == [("15550001111@s.whatsapp.net", "hello v2")]
    assert any(p.endswith("/messages/send") and "%40" not in p for _, p, _ in fake.calls)


async def test_google_mode_confirm_goes_to_google(harness):
    from conftest import OWNER
    mcp, fake, db, s, _ = harness("v1", AUTH_MODE="google", ALLOWED_EMAILS=OWNER,
                                  GOOGLE_CLIENT_ID="cid.apps.googleusercontent.com", GOOGLE_CLIENT_SECRET="g")
    token, _ = await make_draft(mcp)
    with client(mcp, s, None) as tc:
        r = tc.get(f"/confirm/{token}")
        assert r.headers["location"].startswith("https://accounts.google.com/")
    with client(mcp, s, "jesse@example.com") as tc:
        assert tc.get(f"/confirm/{token}").status_code == 302
    with client(mcp, s, OWNER) as tc:
        assert tc.get(f"/confirm/{token}").status_code == 200
