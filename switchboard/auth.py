"""Who gets in: Google sign-in, and only for the emails in ALLOWED_EMAILS.

FastMCP's OAuth proxy will mint a token for any Google account by default. This module closes that
in three places, default deny:

1. At the Google callback: after Google returns, the identity is checked before the client is handed
   an authorization code. Anyone else gets a refusal page and their code is deleted, so no token can
   ever be issued for them.
2. At the token endpoint: the same check again before a token is minted (belt and braces).
3. On every request: each bearer token is re-verified against Google and the email re-checked.

The confirm page has its own browser sign-in (the same Google client, a second redirect URI) and a
signed session cookie, with the same allowlist.
"""
from __future__ import annotations

import html
import logging
import secrets
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from itsdangerous import BadSignature, URLSafeTimedSerializer
from mcp.server.auth.provider import TokenError
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from fastmcp.server.auth.providers.google import GoogleProvider, GoogleTokenVerifier

from .config import Settings

log = logging.getLogger("switchboard.auth")

SCOPES = ["openid", "email"]
# Claude's OAuth callbacks (claude.ai, Desktop, mobile, Cowork) plus Claude Code's loopback.
CLIENT_REDIRECTS = [
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
    "http://localhost:*",
    "http://127.0.0.1:*",
]


def email_allowed(claims: dict[str, Any] | None, allowed: frozenset[str]) -> bool:
    if not claims:
        return False
    email = str(claims.get("email") or "").strip().lower()
    verified = claims.get("email_verified")
    verified = verified is True or str(verified).lower() == "true"
    return bool(email) and verified and email in allowed


def refusal_page(title: str, body: str, status: int = 403) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>body{{font:16px/1.5 -apple-system,system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem;color:#222;background:#fafafa}}
h1{{font-size:1.3rem}}</style><h1>{html.escape(title)}</h1><p>{html.escape(body)}</p>""",
        status_code=status,
    )


class AllowlistGoogleProvider(GoogleProvider):
    def __init__(self, *, allowed_emails: frozenset[str], **kw):
        super().__init__(**kw)
        self._allowed = allowed_emails

    async def _identity(self, idp_tokens: dict) -> dict | None:
        token = (idp_tokens or {}).get("access_token")
        if not token:
            return None
        verified = await self._token_validator.verify_token(token)
        return verified.claims if verified else None

    async def _handle_idp_callback(self, request: Request):
        resp = await super()._handle_idp_callback(request)
        if not isinstance(resp, RedirectResponse):
            return resp
        code = parse_qs(urlsplit(resp.headers.get("location", "")).query).get("code", [None])[0]
        if not code:
            return resp  # an error being forwarded to the client: nothing to issue
        code_model = await self._code_store.get(key=code)
        claims = await self._identity(code_model.idp_tokens) if code_model else None
        if not email_allowed(claims, self._allowed):
            await self._code_store.delete(key=code)
            log.warning("auth refused at callback: identity not on the allowlist (no code, no token issued)")
            return refusal_page("Not allowed", "This connector belongs to someone else. Your account can't use it.")
        log.info("auth callback accepted for an allowlisted identity")
        return resp

    async def exchange_authorization_code(self, client, authorization_code):
        code_model = await self._code_store.get(key=authorization_code.code)
        claims = await self._identity(code_model.idp_tokens) if code_model else None
        if not email_allowed(claims, self._allowed):
            if code_model:
                await self._code_store.delete(key=authorization_code.code)
            log.warning("auth refused at token endpoint: identity not on the allowlist")
            raise TokenError("invalid_grant", "not allowed")
        log.info("token issued to an allowlisted identity")
        return await super().exchange_authorization_code(client, authorization_code)

    async def load_access_token(self, token: str):
        result = await super().load_access_token(token)
        if result is None:
            return None
        if not email_allowed(result.claims, self._allowed):
            log.warning("request refused: bearer identity not on the allowlist")
            return None
        return result


def build_mcp_auth(s: Settings, client_storage=None) -> AllowlistGoogleProvider:
    return AllowlistGoogleProvider(
        allowed_emails=s.allowed_emails,
        client_id=s.google_client_id,
        client_secret=s.google_client_secret,
        base_url=s.base_url,
        required_scopes=SCOPES,
        allowed_client_redirect_uris=CLIENT_REDIRECTS,
        jwt_signing_key=s.secret,
        client_storage=client_storage,
        cache_ttl_seconds=120,
        require_authorization_consent=True,
        extra_authorize_params={"access_type": "offline", "prompt": "consent select_account"},
    )


# ---- browser sign-in for the confirm page ------------------------------------------------------

SESSION_COOKIE = "sb_session"
STATE_COOKIE = "sb_login"
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"


class WebAuth:
    def __init__(self, s: Settings, http: httpx.AsyncClient | None = None):
        self.s = s
        self.signer = URLSafeTimedSerializer(s.secret, salt="switchboard-web")
        self.verifier = GoogleTokenVerifier(required_scopes=SCOPES, audience=s.google_client_id)
        self.http = http
        self.secure = s.base_url.startswith("https://")

    @property
    def redirect_uri(self) -> str:
        return self.s.base_url + "/web/callback"

    def current_email(self, request: Request) -> str | None:
        raw = request.cookies.get(SESSION_COOKIE)
        if not raw:
            return None
        try:
            data = self.signer.loads(raw, max_age=self.s.session_ttl_s)
        except BadSignature:
            return None
        email = (data or {}).get("e")
        return email if email in self.s.allowed_emails else None

    def csrf(self, request: Request, draft_id: str) -> str:
        return self.signer.dumps({"c": draft_id, "s": request.cookies.get(SESSION_COOKIE, "")[-24:]})

    def csrf_ok(self, request: Request, draft_id: str, token: str) -> bool:
        try:
            data = self.signer.loads(token or "", max_age=self.s.draft_ttl_s)
        except BadSignature:
            return False
        return data.get("c") == draft_id and data.get("s") == request.cookies.get(SESSION_COOKIE, "")[-24:]

    def login_redirect(self, next_path: str) -> Response:
        if not next_path.startswith("/confirm/"):
            next_path = "/"
        nonce = secrets.token_urlsafe(16)
        state = self.signer.dumps({"n": nonce, "next": next_path})
        q = urlencode({
            "client_id": self.s.google_client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "state": state,
            "prompt": "select_account",
        })
        resp = RedirectResponse(f"{GOOGLE_AUTH}?{q}", status_code=302)
        resp.set_cookie(STATE_COOKIE, nonce, max_age=600, httponly=True, secure=self.secure, samesite="lax")
        return resp

    async def callback(self, request: Request) -> Response:
        try:
            state = self.signer.loads(request.query_params.get("state", ""), max_age=600)
        except BadSignature:
            return refusal_page("Sign-in expired", "Open the confirm link again.", 400)
        if state.get("n") != request.cookies.get(STATE_COOKIE):
            return refusal_page("Sign-in mismatch", "Open the confirm link again in this browser.", 400)
        code = request.query_params.get("code")
        if not code:
            return refusal_page("Sign-in cancelled", "Nothing was sent.", 400)
        claims = None
        try:
            client = self.http or httpx.AsyncClient(timeout=10)
            try:
                r = await client.post(GOOGLE_TOKEN, data={
                    "code": code,
                    "client_id": self.s.google_client_id,
                    "client_secret": self.s.google_client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                })
            finally:
                if self.http is None:
                    await client.aclose()
            if r.status_code == 200:
                verified = await self.verifier.verify_token(r.json().get("access_token", ""))
                claims = verified.claims if verified else None
        except Exception as e:  # noqa: BLE001
            log.warning("web sign-in failed type=%s", type(e).__name__)
        if not email_allowed(claims, self.s.allowed_emails):
            log.warning("web sign-in refused: identity not on the allowlist")
            return refusal_page("Not allowed", "This account can't approve messages here.")
        resp = RedirectResponse(state.get("next", "/"), status_code=303)
        resp.set_cookie(
            SESSION_COOKIE,
            self.signer.dumps({"e": str(claims["email"]).lower(), "n": secrets.token_urlsafe(8)}),
            max_age=self.s.session_ttl_s, httponly=True, secure=self.secure, samesite="lax",
        )
        resp.delete_cookie(STATE_COOKIE)
        return resp
