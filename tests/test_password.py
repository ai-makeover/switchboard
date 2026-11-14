"""Password mode, end to end over HTTP: the same OAuth handshake Claude's connector runs."""
import base64
import hashlib
import re
import secrets
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from starlette.testclient import TestClient

from conftest import PASSWORD, FakeUnipile, make_settings
from switchboard.server import build
from switchboard.store import Store
from switchboard.unipile import Unipile

CB = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture
def app(tmp_path):
    opened = []

    def make(**over):
        s = make_settings(tmp_path, "v1", **over)
        fake = FakeUnipile("v1")
        up = Unipile(s, transport=httpx.MockTransport(fake.handler))
        db = Store(tmp_path / "sb.db")
        mcp = build(s, unipile=up, store=db, with_auth=True)
        tc = TestClient(mcp.http_app(path="/mcp", stateless_http=True), base_url=s.base_url, follow_redirects=False)
        tc.__enter__()
        opened.append(tc)
        return tc, db, s, fake
    yield make
    for tc in opened:
        tc.__exit__(None, None, None)


def register(tc, redirect=CB):
    return tc.post("/register", json={"redirect_uris": [redirect], "token_endpoint_auth_method": "none",
                                      "grant_types": ["authorization_code", "refresh_token"],
                                      "response_types": ["code"], "client_name": "Claude"})


def start(tc):
    client_id = register(tc).json()["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    r = tc.get("/authorize", params={"response_type": "code", "client_id": client_id, "redirect_uri": CB,
                                     "code_challenge": challenge, "code_challenge_method": "S256", "state": "st8"})
    assert r.status_code == 302, r.text
    loc = r.headers["location"]
    assert "/login?req=" in loc, "authorize must go to Switchboard's password page, not an outside provider"
    return client_id, verifier, loc.split("/login", 1)[1]


def login_form(tc, path):
    r = tc.get("/login" + path)
    assert r.status_code == 200
    assert "Claude" in r.text and "wants to connect" in r.text
    return re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)


def submit(tc, csrf, password):
    return tc.post("/login", data={"csrf": csrf, "password": password})


def token(tc, client_id, code, verifier):
    return tc.post("/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": CB,
                                   "client_id": client_id, "code_verifier": verifier})


def list_tools(tc, bearer):
    return tc.post("/mcp", headers={"authorization": f"Bearer {bearer}", "accept": "application/json, text/event-stream",
                                    "content-type": "application/json"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})


def connect(tc):
    client_id, verifier, path = start(tc)
    r = submit(tc, login_form(tc, path), PASSWORD)
    assert r.status_code == 302 and r.headers["location"].startswith(CB)
    q = parse_qs(urlsplit(r.headers["location"]).query)
    assert q["state"] == ["st8"]
    t = token(tc, client_id, q["code"][0], verifier)
    assert t.status_code == 200, t.text
    return client_id, t.json()


def test_full_flow_then_tools(app):
    tc, db, s, _ = app()
    assert tc.post("/mcp", json={}).status_code == 401
    _, tok = connect(tc)
    r = list_tools(tc, tok["access_token"])
    assert r.status_code == 200 and "draft_reply" in r.text and "status" in r.text
    assert list_tools(tc, "made-up-token").status_code == 401


def test_metadata_points_at_switchboard(app):
    tc, *_ = app()
    meta = tc.get("/.well-known/oauth-authorization-server").json()
    assert meta["authorization_endpoint"] == "https://sb.example.test/authorize"
    assert meta["registration_endpoint"] == "https://sb.example.test/register"
    assert "S256" in meta["code_challenge_methods_supported"]
    prm = tc.get("/.well-known/oauth-protected-resource/mcp").json()
    assert prm["resource"] == "https://sb.example.test/mcp"


def test_wrong_password_gets_no_code(app):
    tc, db, s, _ = app()
    _, _, path = start(tc)
    r = submit(tc, login_form(tc, path), PASSWORD + "x")
    assert r.status_code == 401 and "Wrong password" in r.text and "location" not in r.headers
    assert db.db.execute("SELECT COUNT(*) FROM oauth_codes").fetchone()[0] == 0


def test_lockout_after_five_wrong_tries(app):
    tc, db, s, _ = app()
    _, _, path = start(tc)
    csrf = login_form(tc, path)
    for _ in range(5):
        assert submit(tc, csrf, "nope").status_code == 401
    r = submit(tc, csrf, PASSWORD)  # right password, but locked
    assert r.status_code == 429 and "locked" in r.text
    assert db.db.execute("SELECT COUNT(*) FROM oauth_codes").fetchone()[0] == 0
    db.db.execute("UPDATE login_attempts SET at = at - 1000")  # 15 minutes later
    assert submit(tc, csrf, PASSWORD).status_code == 302


def test_global_lockout(app):
    tc, db, s, _ = app()
    for i in range(20):
        db.record_login(f"10.0.0.{i}", False)
    _, _, path = start(tc)
    assert submit(tc, login_form(tc, path), PASSWORD).status_code == 429


def test_code_is_single_use_and_pkce_checked(app):
    tc, db, s, _ = app()
    client_id, verifier, path = start(tc)
    r = submit(tc, login_form(tc, path), PASSWORD)
    code = parse_qs(urlsplit(r.headers["location"]).query)["code"][0]
    assert token(tc, client_id, code, "wrong-verifier-" + "x" * 40).status_code in (400, 401)
    assert token(tc, client_id, code, verifier).status_code == 200
    assert token(tc, client_id, code, verifier).status_code in (400, 401)


def test_refresh_rotates(app):
    tc, db, s, _ = app()
    client_id, tok = connect(tc)
    r = tc.post("/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": client_id})
    assert r.status_code == 200, r.text
    new = r.json()
    assert list_tools(tc, new["access_token"]).status_code == 200
    assert list_tools(tc, tok["access_token"]).status_code == 401  # old pair revoked
    r = tc.post("/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": client_id})
    assert r.status_code in (400, 401)


def test_password_reset_signs_everyone_out(app, tmp_path):
    tc, db, s, fake = app()
    _, tok = connect(tc)
    cookie = tc.cookies.get("sb_session")
    assert cookie
    # same database, new password
    s2 = make_settings(tmp_path, "v1", SWITCHBOARD_PASSWORD="a-completely-new-password-7781")
    mcp2 = build(s2, unipile=Unipile(s2, transport=httpx.MockTransport(fake.handler)), store=db, with_auth=True)
    with TestClient(mcp2.http_app(path="/mcp", stateless_http=True), base_url=s2.base_url, follow_redirects=False) as tc2:
        assert list_tools(tc2, tok["access_token"]).status_code == 401
        tc2.cookies.set("sb_session", cookie)
        assert tc2.get("/signed-in").status_code == 302  # old browser session dropped too


def test_evil_redirect_cannot_register(app):
    tc, *_ = app()
    r = register(tc, "https://evil.example.com/cb")
    assert r.status_code == 400


def test_expired_request(app):
    tc, db, s, _ = app()
    _, _, path = start(tc)
    db.db.execute("UPDATE oauth_requests SET expires_at = 0")
    assert tc.get("/login" + path).status_code == 400


def test_https_only(app):
    tc, db, s, _ = app()
    plain = TestClient(tc.app, base_url="http://sb.example.test", follow_redirects=False)
    r = plain.get("/login?next=/confirm/x")
    token_ = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
    r = plain.post("/login", data={"csrf": token_, "password": PASSWORD})
    assert r.status_code == 400 and "HTTPS" in r.text


def test_browser_login_for_confirm_page(app):
    tc, db, s, _ = app()
    r = tc.get("/login?next=/confirm/abc")
    csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
    r = submit(tc, csrf, PASSWORD)
    assert r.status_code == 303 and r.headers["location"] == "/confirm/abc"
    assert tc.get("/signed-in").status_code == 200
    # next can't be pointed anywhere else
    r = tc.get("/login?next=https://evil.example.com")
    csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
    assert submit(tc, csrf, PASSWORD).headers["location"] == "/signed-in"


def test_no_password_yet_boots_and_says_so(app):
    tc, db, s, _ = app(SWITCHBOARD_PASSWORD="")
    assert tc.get("/healthz").status_code == 200
    _, _, path = start(tc)
    r = tc.get("/login" + path)
    assert r.status_code == 503 and "SWITCHBOARD_PASSWORD" in r.text
    r = tc.post("/login", data={"csrf": "x", "password": ""})
    assert r.status_code == 503
    assert db.db.execute("SELECT COUNT(*) FROM oauth_codes").fetchone()[0] == 0


def test_secret_is_generated_and_kept(tmp_path):
    s1 = make_settings(tmp_path, "v1", SWITCHBOARD_SECRET="")
    s2 = make_settings(tmp_path, "v1", SWITCHBOARD_SECRET="")
    assert len(s1.secret) >= 32 and s1.secret == s2.secret
    assert oct((tmp_path / ".switchboard_secret").stat().st_mode)[-3:] == "600"
