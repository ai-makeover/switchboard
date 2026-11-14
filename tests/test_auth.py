"""The allowlist is enforced at the Google callback, at the token endpoint and on every request."""
import time

import pytest
from mcp.server.auth.provider import TokenError
from starlette.responses import RedirectResponse

from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.oauth_proxy.models import ClientCode
from fastmcp.server.auth.providers.google import GoogleProvider

from conftest import OWNER, make_settings
from switchboard.auth import build_mcp_auth, email_allowed


def test_email_allowed():
    allowed = frozenset({OWNER})
    assert email_allowed({"email": OWNER, "email_verified": "true"}, allowed)
    assert email_allowed({"email": OWNER.upper(), "email_verified": True}, allowed)
    assert not email_allowed({"email": OWNER, "email_verified": "false"}, allowed)
    assert not email_allowed({"email": OWNER}, allowed)
    assert not email_allowed({"email": "jesse@example.com", "email_verified": True}, allowed)
    assert not email_allowed({"email": OWNER + ".evil.com", "email_verified": True}, allowed)
    assert not email_allowed({}, allowed)
    assert not email_allowed(None, allowed)


@pytest.fixture
def provider(tmp_path):
    from key_value.aio.stores.memory import MemoryStore
    s = make_settings(tmp_path, AUTH_MODE="google", ALLOWED_EMAILS=OWNER,
                      GOOGLE_CLIENT_ID="cid.apps.googleusercontent.com", GOOGLE_CLIENT_SECRET="g")
    p = build_mcp_auth(s, client_storage=MemoryStore())
    p.set_mcp_path("/mcp")
    return p


def claims_for(email):
    async def verify(token):
        return AccessToken(token=token, client_id="cid", scopes=["openid"], expires_at=int(time.time()) + 3600,
                           claims={"email": email, "email_verified": "true", "sub": "1"})
    return verify


async def put_code(p, code="client-code-1"):
    await p._code_store.put(key=code, value=ClientCode(
        code=code, client_id="c", redirect_uri="https://claude.ai/api/mcp/auth_callback", code_challenge="x",
        code_challenge_method="S256", scopes=["openid"], idp_tokens={"access_token": "g-at", "expires_in": 3600},
        expires_at=time.time() + 300, created_at=time.time()), ttl=300)
    return code


@pytest.mark.parametrize("email,allowed", [("jesse@example.com", False), (OWNER, True)])
async def test_callback_refuses_strangers_and_deletes_code(provider, monkeypatch, email, allowed):
    code = await put_code(provider)

    async def fake_super(self, request):
        return RedirectResponse(f"https://claude.ai/api/mcp/auth_callback?code={code}&state=s", status_code=302)

    monkeypatch.setattr(GoogleProvider, "_handle_idp_callback", fake_super)
    monkeypatch.setattr(provider._token_validator, "verify_token", claims_for(email))
    resp = await provider._handle_idp_callback(None)
    if allowed:
        assert resp.status_code == 302 and code in resp.headers["location"]
        assert await provider._code_store.get(key=code) is not None
    else:
        assert resp.status_code == 403
        assert "location" not in resp.headers
        assert await provider._code_store.get(key=code) is None, "a stranger's code must be destroyed"


async def test_token_endpoint_refuses_strangers(provider, monkeypatch):
    code = await put_code(provider)
    monkeypatch.setattr(provider._token_validator, "verify_token", claims_for("jesse@example.com"))

    class AC:
        pass
    ac = AC()
    ac.code = code
    ac.scopes = ["openid"]
    with pytest.raises(TokenError):
        await provider.exchange_authorization_code(None, ac)
    assert await provider._code_store.get(key=code) is None


async def test_every_request_rechecks_identity(provider, monkeypatch):
    async def upstream_ok(self, token):
        return AccessToken(token=token, client_id="c", scopes=["openid"], expires_at=None,
                           claims={"email": "jesse@example.com", "email_verified": True})
    from fastmcp.server.auth.oauth_proxy.proxy import OAuthProxy
    monkeypatch.setattr(OAuthProxy, "load_access_token", upstream_ok)
    assert await provider.load_access_token("t") is None

    async def owner_ok(self, token):
        return AccessToken(token=token, client_id="c", scopes=["openid"], expires_at=None,
                           claims={"email": OWNER, "email_verified": True})
    monkeypatch.setattr(OAuthProxy, "load_access_token", owner_ok)
    assert (await provider.load_access_token("t")).claims["email"] == OWNER


def test_redirect_allowlist_and_scopes(provider):
    assert provider._validate_client_redirect_uri("https://claude.ai/api/mcp/auth_callback")
    assert provider._validate_client_redirect_uri("http://localhost:53682/callback")
    assert not provider._validate_client_redirect_uri("https://evil.example.com/cb")


def test_config_refuses_empty_allowlist(tmp_path):
    from switchboard.config import ConfigError
    with pytest.raises(ConfigError):
        make_settings(tmp_path, AUTH_MODE="google", ALLOWED_EMAILS="", GOOGLE_CLIENT_ID="x", GOOGLE_CLIENT_SECRET="y")
    with pytest.raises(ConfigError):
        make_settings(tmp_path, AUTH_MODE="google", ALLOWED_EMAILS=OWNER)  # no client
    with pytest.raises(ConfigError):
        make_settings(tmp_path, SWITCHBOARD_PASSWORD="too-short")
    with pytest.raises(ConfigError):
        make_settings(tmp_path, SWITCHBOARD_SECRET="short")


def test_github_mode(tmp_path):
    from switchboard.auth import AllowlistGitHubProvider, identity_from_claims
    from key_value.aio.stores.memory import MemoryStore
    s = make_settings(tmp_path, AUTH_MODE="github", ALLOWED_GITHUB_USERS="@Wombyz", GITHUB_CLIENT_ID="i", GITHUB_CLIENT_SECRET="s")
    assert s.allowed == frozenset({"github:wombyz"})
    p = build_mcp_auth(s, client_storage=MemoryStore())
    assert isinstance(p, AllowlistGitHubProvider)
    assert p._sb_ok({"login": "Wombyz"}) and not p._sb_ok({"login": "jesse"}) and not p._sb_ok({})
    assert identity_from_claims("password", {"sub": "owner"}) == "owner"
    assert identity_from_claims("password", {"sub": "someone"}) is None
