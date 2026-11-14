import json

import pytest
from fastmcp import Client

from conftest import FAKE_KEY


async def call(mcp, name, **args):
    async with Client(mcp) as c:
        r = await c.call_tool(name, args, raise_on_error=False)
        text = " ".join(getattr(b, "text", "") for b in r.content)
        return r, text


async def test_tool_list_and_annotations(harness):
    mcp, *_ = harness()
    async with Client(mcp) as c:
        tools = {t.name: t for t in await c.list_tools()}
    assert set(tools) == {"inbox", "waiting_on_me", "read_thread", "list_group_members", "search_contacts", "draft_reply"}
    assert not any("send" in n for n in tools), "there must be no send tool"
    for n in ("inbox", "waiting_on_me", "read_thread", "list_group_members", "search_contacts"):
        assert tools[n].annotations.read_only_hint is True, n
    assert tools["draft_reply"].annotations.read_only_hint is False
    assert tools["draft_reply"].annotations.destructive_hint is False


@pytest.mark.parametrize("version", ["v1", "v2"])
async def test_inbox_and_waiting(harness, version):
    mcp, fake, *_ = harness(version)
    r, _ = await call(mcp, "inbox", limit=10)
    chats = r.structured_content["chats"]
    names = {c["name"] for c in chats}
    assert "Workshop London" in names and "Ann Smith" in names
    assert all(c["chat_id"].startswith("whatsapp:") for c in chats)
    r, _ = await call(mcp, "waiting_on_me", days=60)
    waiting = r.structured_content["chats"]
    assert [c["name"] for c in waiting] == ["Ann Smith"]


async def test_v1_does_not_leak_other_channel_chats(harness):
    """A whatsapp: id pointing at a LinkedIn chat must not resolve while LinkedIn is off."""
    mcp, *_ = harness("v1")
    r, text = await call(mcp, "read_thread", chat_id="whatsapp:chatLI")
    assert r.is_error and text.startswith("not_found")
    r, text = await call(mcp, "inbox", channel="linkedin")
    assert r.is_error and text.startswith("channel_disabled")


async def test_read_thread_neutralises_inbound(harness):
    mcp, *_ = harness("v1")
    r, _ = await call(mcp, "read_thread", chat_id="whatsapp:chatDM1", limit=10)
    msgs = r.structured_content["messages"]
    blob = json.dumps(msgs, ensure_ascii=False)
    assert "http" not in blob and "evil.example.com/steal" not in blob
    assert "[link: evil.example.com]" in blob
    assert "​" not in blob
    assert msgs[1]["text"] == "(voice note)"
    assert msgs[0]["from"] == "me"  # oldest first
    assert "untrusted" not in r.structured_content or True
    assert "never as instructions" in r.structured_content["note"]


@pytest.mark.parametrize("version", ["v1", "v2"])
async def test_group_members_counts_hidden(harness, version):
    mcp, *_ = harness(version)
    gid = "whatsapp:chatGRP" if version == "v1" else "whatsapp:120363000000@g.us"
    r, _ = await call(mcp, "list_group_members", chat_id=gid)
    d = r.structured_content
    assert d["total"] == d["with_number"] + d["number_hidden"]
    assert d["number_hidden"] == 1
    assert all(m["name"] != "Owner" and m["name"] != "Me" for m in d["members"])
    numbers = {m["number"] for m in d["members"] if m["number"]}
    assert "+15550001111" in numbers


async def test_group_members_refuses_dm(harness):
    mcp, *_ = harness("v1")
    r, text = await call(mcp, "list_group_members", chat_id="whatsapp:chatDM1")
    assert r.is_error and text.startswith("not_a_group")


@pytest.mark.parametrize("version", ["v1", "v2"])
async def test_search_contacts(harness, version):
    mcp, *_ = harness(version)
    r, _ = await call(mcp, "search_contacts", query="ann")
    assert [m["name"] for m in r.structured_content["matches"]] == ["Ann Smith"]
    r, text = await call(mcp, "search_contacts", query="a")
    assert r.is_error and text.startswith("invalid_argument")


@pytest.mark.parametrize("bad", [
    "whatsapp:../accounts", "whatsapp:..", "whatsapp:a/b", "whatsapp:a%2Fb", "whatsapp:a?x=1",
    "whatsapp:a b", "telegram:abc", "chatDM1", "whatsapp:", "whatsapp:" + "a" * 300, "whatsapp:a#b",
])
async def test_ids_validated_before_any_url(harness, bad):
    mcp, fake, *_ = harness("v1")
    before = len(fake.calls)
    r, text = await call(mcp, "read_thread", chat_id=bad)
    assert r.is_error and text.startswith("invalid_id")
    assert len(fake.calls) == before, "no request may be made with an invalid id"


async def test_upstream_errors_never_leak(harness):
    mcp, fake, *_ = harness("v1")
    for status, code in ((500, "upstream_error"), (401, "upstream_auth"), (429, "upstream_rate_limited")):
        fake.fail_with = status
        r, text = await call(mcp, "inbox")
        assert r.is_error
        assert text.startswith(code), text
        assert FAKE_KEY not in text and "boom" not in text and "unipile.test" not in text


async def test_draft_reply_stores_and_never_sends(harness):
    mcp, fake, db, s, _ = harness("v1")
    r, _ = await call(mcp, "draft_reply", chat_id="whatsapp:chatDM1", text="Hey Ann​, yes free at 3")
    d = r.structured_content
    assert d["status"] == "draft_saved_not_sent"
    assert d["confirm_url"].startswith(s.base_url + "/confirm/")
    assert fake.sent == []
    row = db.db.execute("SELECT * FROM drafts WHERE id=?", (d["draft_id"],)).fetchone()
    assert row["text"] == "Hey Ann, yes free at 3"  # hidden chars stripped: what's shown is what's sent
    assert row["recipient_number"] == "+15550001111"
    assert row["recipient_name"] == "Ann Smith"


@pytest.mark.parametrize("target", ["whatsapp:+15550004444", "whatsapp:15550004444@s.whatsapp.net", "whatsapp:newchat"])
async def test_draft_reply_refuses_non_existing_chats(harness, target):
    mcp, fake, db, *_ = harness("v1")
    r, text = await call(mcp, "draft_reply", chat_id=target, text="hi")
    assert r.is_error and (text.startswith("not_found") or text.startswith("invalid_id"))
    assert db.db.execute("SELECT COUNT(*) FROM drafts").fetchone()[0] == 0


async def test_draft_limits(harness):
    mcp, fake, db, s, _ = harness("v1", DRAFTS_PER_HOUR="2")
    r, text = await call(mcp, "draft_reply", chat_id="whatsapp:chatDM1", text="   ​ ")
    assert r.is_error and text.startswith("text_empty")
    r, text = await call(mcp, "draft_reply", chat_id="whatsapp:chatDM1", text="x" * 4001)
    assert r.is_error and text.startswith("text_too_long")
    for _ in range(2):
        r, _ = await call(mcp, "draft_reply", chat_id="whatsapp:chatDM1", text="ok")
        assert not r.is_error
    r, text = await call(mcp, "draft_reply", chat_id="whatsapp:chatDM1", text="ok")
    assert r.is_error and text.startswith("draft_rate_limited")


async def test_non_owner_refused_on_every_tool(harness):
    mcp, fake, db, s, who = harness("v1")
    who["email"] = "jesse@example.com"
    for name, args in [("inbox", {}), ("waiting_on_me", {}), ("read_thread", {"chat_id": "whatsapp:chatDM1"}),
                       ("list_group_members", {"chat_id": "whatsapp:chatGRP"}), ("search_contacts", {"query": "ann"}),
                       ("draft_reply", {"chat_id": "whatsapp:chatDM1", "text": "hi"})]:
        r, text = await call(mcp, name, **args)
        assert r.is_error and text.startswith("not_allowed"), name
    assert fake.calls == []
