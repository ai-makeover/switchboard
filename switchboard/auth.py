"""Who gets in.

AUTH_MODE=password (the default). Switchboard runs its own small OAuth server, so Claude's connector flow
(dynamic registration, PKCE, refresh) works unchanged, but the sign-in step is a Switchboard page that asks for
the owner password. The password is long and random, set once as a Railway variable. Wrong tries are rate
limited per address and globally, comparison is constant-time, and the form only works over HTTPS.

AUTH_MODE=google / github. FastMCP's OAuth proxy in front of Google or GitHub, plus an allowlist (emails or
GitHub logins). The proxy would mint a token for any account by default, so the allowlist is checked at the
provider callback (anyone else's code is destroyed, so no token is ever issued), at the token endpoint and on
every request.

The same sign-in also guards the draft confirm page, through a signed session cookie.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import logging
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import httpx
from itsdangerous import BadSignature, URLSafeTimedSerializer
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from fastmcp.server.auth.auth import AccessToken, OAuthProvider
from fastmcp.server.auth.providers.github import GitHubProvider, GitHubTokenVerifier
from fastmcp.server.auth.providers.google import GoogleProvider, GoogleTokenVerifier
from fastmcp.server.auth.redirect_validation import matches_allowed_pattern

from .config import Settings
from .pages import message, page

log = logging.getLogger("switchboard.auth")

# Claude's OAuth callbacks (claude.ai, Desktop, mobile, Cowork) plus Claude Code's loopback.
CLIENT_REDIRECTS = [
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
    "http://localhost:*",
    "http://127.0.0.1:*",
]
GOOGLE_SCOPES = ["openid", "email"]
GITHUB_SCOPES = ["read:user"]


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_fingerprint(s: Settings) -> str:
    """Changes whenever the password changes, so a reset signs every client and browser out."""
    return hmac.new(s.secret.encode(), ("pw:" + s.password).encode(), hashlib.sha256).hexdigest()[:24]


def password_matches(s: Settings, attempt: str) -> bool:
    return hmac.compare_digest(_h("sb:" + (attempt or "")), _h("sb:" + s.password))


def identity_from_claims(mode: str, claims: dict[str, Any] | None) -> str | None:
    """The identity string a token carries: "owner", an email, or "github:<login>"."""
    if not claims:
        return None
    if mode == "password":
        return "owner" if claims.get("sub") == "owner" else None
    if mode == "google":
        verified = claims.get("email_verified")
        if not (verified is True or str(verified).lower() == "true"):
            return None
        email = str(claims.get("email") or "").strip().lower()
        return email or None
    login = str(claims.get("login") or "").strip().lower()
    return f"github:{login}" if login else None


def email_allowed(claims: dict[str, Any] | None, allowed: frozenset[str]) -> bool:
    """Google-mode check, kept for callers and tests."""
    ident = identity_from_claims("google", claims)
    return ident is not None and ident in allowed


# ---- password mode: Switchboard's own OAuth server -------------------------------------------------

class PasswordOAuthProvider(OAuthProvider):
    ACCESS_TTL = 3600
    REFRESH_TTL = 90 * 86400
    CODE_TTL = 300
    REQUEST_TTL = 900

    def __init__(self, s: Settings, store):
        super().__init__(
            base_url=s.base_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=True),
        )
        self.s = s
        self.db = store.db
        self.fp = password_fingerprint(s)

    # clients
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        row = self.db.execute("SELECT data FROM oauth_clients WHERE client_id=?", (client_id,)).fetchone()
        return OAuthClientInformationFull.model_validate_json(row[0]) if row else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [str(u) for u in (client_info.redirect_uris or [])]
        if not uris or not all(any(matches_allowed_pattern(u, p) for p in CLIENT_REDIRECTS) for u in uris):
            raise RegistrationError(error="invalid_redirect_uri", error_description="redirect URI not allowed")
        self.db.execute("INSERT OR REPLACE INTO oauth_clients (client_id, data, created_at) VALUES (?,?,?)",
                        (client_info.client_id, client_info.model_dump_json(), time.time()))

    # authorize -> our login page
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        rid = secrets.token_urlsafe(24)
        data = {
            "client_id": client.client_id,
            "client_name": client.client_name or "",
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "state": params.state,
            "code_challenge": params.code_challenge,
            "scopes": params.scopes or [],
            "resource": params.resource,
        }
        now = time.time()
        self.db.execute("DELETE FROM oauth_requests WHERE expires_at < ?", (now,))
        self.db.execute("INSERT INTO oauth_requests (id, data, expires_at) VALUES (?,?,?)",
                        (rid, json.dumps(data), now + self.REQUEST_TTL))
        return f"{self.s.base_url}/login?req={quote(rid)}"

    def pending(self, rid: str) -> dict | None:
        row = self.db.execute("SELECT data FROM oauth_requests WHERE id=? AND expires_at > ?",
                              (rid or "", time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def complete(self, rid: str) -> str | None:
        """After the password is right: one-time code, back to the client's redirect URI."""
        req = self.pending(rid)
        self.db.execute("DELETE FROM oauth_requests WHERE id=?", (rid or "",))
        if not req:
            return None
        code = secrets.token_urlsafe(32)
        ac = AuthorizationCode(
            code=code, scopes=req["scopes"], expires_at=time.time() + self.CODE_TTL,
            client_id=req["client_id"], code_challenge=req["code_challenge"], redirect_uri=req["redirect_uri"],
            redirect_uri_provided_explicitly=req["redirect_uri_provided_explicitly"], resource=req.get("resource"),
            subject="owner",
        )
        self.db.execute("INSERT INTO oauth_codes (code_hash, data, expires_at) VALUES (?,?,?)",
                        (_h(code), ac.model_dump_json(), ac.expires_at))
        return construct_redirect_uri(req["redirect_uri"], code=code, state=req["state"])

    async def load_authorization_code(self, client, authorization_code: str) -> AuthorizationCode | None:
        row = self.db.execute("SELECT data FROM oauth_codes WHERE code_hash=? AND expires_at > ?",
                              (_h(authorization_code), time.time())).fetchone()
        if not row:
            return None
        ac = AuthorizationCode.model_validate_json(row[0])
        return ac if ac.client_id == client.client_id else None

    async def exchange_authorization_code(self, client, authorization_code: AuthorizationCode) -> OAuthToken:
        cur = self.db.execute("DELETE FROM oauth_codes WHERE code_hash=?", (_h(authorization_code.code),))
        if cur.rowcount != 1:
            raise TokenError("invalid_grant", "authorization code already used")
        log.info("token issued after a password sign-in")
        return self._issue(client.client_id, authorization_code.scopes)

    def _issue(self, client_id: str, scopes: list[str]) -> OAuthToken:
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = time.time()
        sc = " ".join(scopes)
        self.db.execute("INSERT INTO oauth_tokens VALUES (?,?,?,?,?,?,?)",
                        (_h(access), "access", client_id, sc, now + self.ACCESS_TTL, _h(refresh), self.fp))
        self.db.execute("INSERT INTO oauth_tokens VALUES (?,?,?,?,?,?,?)",
                        (_h(refresh), "refresh", client_id, sc, now + self.REFRESH_TTL, _h(access), self.fp))
        self.db.execute("DELETE FROM oauth_tokens WHERE expires_at < ?", (now,))
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=self.ACCESS_TTL,
                          refresh_token=refresh, scope=sc or None)

    def _row(self, token: str, kind: str):
        row = self.db.execute("SELECT * FROM oauth_tokens WHERE token_hash=? AND kind=?", (_h(token), kind)).fetchone()
        if not row or (row["expires_at"] and row["expires_at"] < time.time()) or row["pw_fp"] != self.fp:
            return None
        return row

    async def load_refresh_token(self, client, refresh_token: str) -> RefreshToken | None:
        row = self._row(refresh_token, "refresh")
        if not row or row["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, client_id=row["client_id"],
                            scopes=row["scopes"].split() if row["scopes"] else [], expires_at=int(row["expires_at"]))

    async def exchange_refresh_token(self, client, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        if not set(scopes) <= set(refresh_token.scopes):
            raise TokenError("invalid_scope", "scope exceeds the original grant")
        self._revoke(_h(refresh_token.token))
        return self._issue(client.client_id, scopes or refresh_token.scopes)

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = self._row(token, "access")
        if not row:
            return None
        return AccessToken(token=token, client_id=row["client_id"], scopes=row["scopes"].split() if row["scopes"] else [],
                           expires_at=int(row["expires_at"]), subject="owner", claims={"sub": "owner"})

    async def verify_token(self, token: str) -> AccessToken | None:
        return await self.load_access_token(token)

    def _revoke(self, token_hash: str) -> None:
        row = self.db.execute("SELECT pair_hash FROM oauth_tokens WHERE token_hash=?", (token_hash,)).fetchone()
        self.db.execute("DELETE FROM oauth_tokens WHERE token_hash=?", (token_hash,))
        if row and row[0]:
            self.db.execute("DELETE FROM oauth_tokens WHERE token_hash=?", (row[0],))

    async def revoke_token(self, token) -> None:
        self._revoke(_h(token.token))


# ---- google / github modes ---------------------------------------------------------------------------

class AllowlistMixin:
    """Mixed into FastMCP's OAuthProxy providers. Default deny, three checks."""

    _sb_mode: str
    _sb_allowed: frozenset[str]

    def _sb_ok(self, claims) -> bool:
        ident = identity_from_claims(self._sb_mode, claims)
        return ident is not None and ident in self._sb_allowed

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
        if not self._sb_ok(claims):
            await self._code_store.delete(key=code)
            log.warning("auth refused at callback: identity not on the allowlist (no code, no token issued)")
            return message("Not allowed", "This connector belongs to someone else. Your account can't use it.", 403)
        log.info("auth callback accepted for an allowlisted identity")
        return resp

    async def exchange_authorization_code(self, client, authorization_code):
        code_model = await self._code_store.get(key=authorization_code.code)
        claims = await self._identity(code_model.idp_tokens) if code_model else None
        if not self._sb_ok(claims):
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
        if not self._sb_ok(result.claims):
            log.warning("request refused: bearer identity not on the allowlist")
            return None
        return result


class AllowlistGoogleProvider(AllowlistMixin, GoogleProvider):
    def __init__(self, *, allowed: frozenset[str], **kw):
        super().__init__(**kw)
        self._sb_mode, self._sb_allowed = "google", allowed


class AllowlistGitHubProvider(AllowlistMixin, GitHubProvider):
    def __init__(self, *, allowed: frozenset[str], **kw):
        super().__init__(**kw)
        self._sb_mode, self._sb_allowed = "github", allowed


def build_mcp_auth(s: Settings, store=None, client_storage=None):
    if s.auth_mode == "password":
        return PasswordOAuthProvider(s, store)
    common = dict(
        allowed=s.allowed, client_id=s.oauth_client_id, client_secret=s.oauth_client_secret, base_url=s.base_url,
        allowed_client_redirect_uris=CLIENT_REDIRECTS, jwt_signing_key=s.secret, client_storage=client_storage,
        cache_ttl_seconds=120, require_authorization_consent=True,
    )
    if s.auth_mode == "google":
        return AllowlistGoogleProvider(required_scopes=GOOGLE_SCOPES,
                                       extra_authorize_params={"access_type": "offline", "prompt": "consent select_account"},
                                       **common)
    return AllowlistGitHubProvider(required_scopes=GITHUB_SCOPES, **common)


# ---- browser sign-in (login page, confirm page) ----------------------------------------------------------

SESSION_COOKIE = "sb_session"
STATE_COOKIE = "sb_login"
UPSTREAM = {
    "google": ("https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token", GOOGLE_SCOPES),
    "github": ("https://github.com/login/oauth/authorize", "https://github.com/login/oauth/access_token", GITHUB_SCOPES),
}


class WebAuth:
    def __init__(self, s: Settings, store=None, provider=None, http: httpx.AsyncClient | None = None):
        self.s = s
        self.store = store
        self.provider = provider
        self.signer = URLSafeTimedSerializer(s.secret, salt="switchboard-web")
        self.http = http
        self.secure = s.base_url.startswith("https://")
        self.fp = password_fingerprint(s) if s.auth_mode == "password" else "-"
        if s.auth_mode == "google":
            self.verifier = GoogleTokenVerifier(required_scopes=GOOGLE_SCOPES, audience=s.oauth_client_id)
        elif s.auth_mode == "github":
            self.verifier = GitHubTokenVerifier(required_scopes=GITHUB_SCOPES)
        else:
            self.verifier = None

    # session
    def session_cookie(self, identity: str) -> str:
        return self.signer.dumps({"i": identity, "f": self.fp, "n": secrets.token_urlsafe(6)})

    def set_session(self, resp: Response, identity: str) -> None:
        resp.set_cookie(SESSION_COOKIE, self.session_cookie(identity), max_age=self.s.session_ttl_s,
                        httponly=True, secure=self.secure, samesite="lax")

    def current_identity(self, request: Request) -> str | None:
        raw = request.cookies.get(SESSION_COOKIE)
        if not raw:
            return None
        try:
            data = self.signer.loads(raw, max_age=self.s.session_ttl_s)
        except BadSignature:
            return None
        ident = (data or {}).get("i")
        if data.get("f") != self.fp or ident not in self.s.allowed:
            return None
        return ident

    def csrf(self, request: Request, purpose: str) -> str:
        return self.signer.dumps({"c": purpose, "s": request.cookies.get(SESSION_COOKIE, "")[-24:]})

    def csrf_ok(self, request: Request, purpose: str, token: str, max_age: int | None = None) -> bool:
        try:
            data = self.signer.loads(token or "", max_age=max_age or self.s.draft_ttl_s)
        except BadSignature:
            return False
        return data.get("c") == purpose and data.get("s") == request.cookies.get(SESSION_COOKIE, "")[-24:]

    def login_redirect(self, next_path: str) -> Response:
        if not next_path.startswith("/confirm/"):
            next_path = "/"
        if self.s.auth_mode == "password":
            return RedirectResponse(f"/login?next={quote(next_path, safe='/')}", status_code=302)
        auth_url, _, scopes = UPSTREAM[self.s.auth_mode]
        nonce = secrets.token_urlsafe(16)
        q = {"client_id": self.s.oauth_client_id, "redirect_uri": self.s.base_url + "/web/callback",
             "scope": " ".join(scopes), "state": self.signer.dumps({"n": nonce, "next": next_path})}
        if self.s.auth_mode == "google":
            q.update({"response_type": "code", "prompt": "select_account"})
        resp = RedirectResponse(f"{auth_url}?{urlencode(q)}", status_code=302)
        resp.set_cookie(STATE_COOKIE, nonce, max_age=600, httponly=True, secure=self.secure, samesite="lax")
        return resp

    # password login page (serves both Claude's connector sign-in and the confirm page)
    def _login_form(self, request: Request, req: str, nxt: str, client_name: str, error: str = "") -> Response:
        who = ""
        if req:
            label = html.escape(client_name[:60] or "An app")
            who = (f'<p><b>{label}</b> wants to connect to your Switchboard. Only continue if you just clicked '
                   f'Connect in Claude yourself.</p>')
        err = f'<div class="warn"><b>{html.escape(error)}</b></div>' if error else ""
        csrf = self.signer.dumps({"c": "login", "r": req, "x": nxt})
        body = f"""<div class="card"><h1>Switchboard sign-in</h1>{who}
<form method="post" action="/login">
<input type="hidden" name="csrf" value="{csrf}">
<label class="k" for="pw">Owner password</label>
<input id="pw" type="password" name="password" autocomplete="current-password" required autofocus>{err}
<div class="row"><button class="go">Sign in</button></div></form></div>"""
        return page("Switchboard sign-in", body, 401 if error else 200)

    async def login(self, request: Request) -> Response:
        if self.s.auth_mode != "password":
            return message("Not available", "This server signs in with " + self.s.auth_mode.title() + ".", 404)
        if request.method == "GET":
            req = request.query_params.get("req", "")
            nxt = request.query_params.get("next", "")
            pend = self.provider.pending(req) if req else None
            if req and not pend:
                return message("Sign-in expired", "Go back to Claude and click Connect again.", 400)
            return self._login_form(request, req, nxt, (pend or {}).get("client_name", "Claude"))

        if not self.secure or request.url.scheme != "https":
            if not self.s.base_url.startswith("http://localhost"):
                return message("HTTPS only", "Open this page over https.", 400)
        form = await request.form()
        try:
            meta = self.signer.loads(str(form.get("csrf", "")), max_age=900)
        except BadSignature:
            return message("Form expired", "Go back and try again.", 400)
        if meta.get("c") != "login":
            return message("Form expired", "Go back and try again.", 400)
        req, nxt = meta.get("r") or "", meta.get("x") or ""
        pend = self.provider.pending(req) if req else None
        ip = (request.client.host if request.client else "unknown")[:64]

        wait = self.store.login_blocked(ip)
        if wait:
            log.warning("login refused: locked out")
            return message("Too many tries", f"Sign-in is locked. Try again in {max(1, wait // 60)} minutes.", 429)
        if not password_matches(self.s, str(form.get("password", ""))):
            self.store.record_login(ip, False)
            log.warning("login failed: wrong password")
            await asyncio.sleep(0.75)
            return self._login_form(request, req, nxt, (pend or {}).get("client_name", ""), "Wrong password.")
        self.store.record_login(ip, True)
        log.info("login succeeded")

        if req:
            target = self.provider.complete(req)
            if not target:
                return message("Sign-in expired", "Go back to Claude and click Connect again.", 400)
            resp = RedirectResponse(target, status_code=302)
        else:
            resp = RedirectResponse(nxt if nxt.startswith("/confirm/") else "/signed-in", status_code=303)
        self.set_session(resp, "owner")
        return resp

    # google / github browser callback
    async def callback(self, request: Request) -> Response:
        if self.s.auth_mode == "password":
            return message("Not available", "This server uses a password.", 404)
        try:
            state = self.signer.loads(request.query_params.get("state", ""), max_age=600)
        except BadSignature:
            return message("Sign-in expired", "Open the confirm link again.", 400)
        if state.get("n") != request.cookies.get(STATE_COOKIE):
            return message("Sign-in mismatch", "Open the confirm link again in this browser.", 400)
        code = request.query_params.get("code")
        if not code:
            return message("Sign-in cancelled", "Nothing was sent.", 400)
        _, token_url, _ = UPSTREAM[self.s.auth_mode]
        claims = None
        try:
            client = self.http or httpx.AsyncClient(timeout=10)
            try:
                r = await client.post(token_url, headers={"Accept": "application/json"}, data={
                    "code": code, "client_id": self.s.oauth_client_id, "client_secret": self.s.oauth_client_secret,
                    "redirect_uri": self.s.base_url + "/web/callback", "grant_type": "authorization_code"})
            finally:
                if self.http is None:
                    await client.aclose()
            if r.status_code == 200:
                verified = await self.verifier.verify_token(r.json().get("access_token", ""))
                claims = verified.claims if verified else None
        except Exception as e:  # noqa: BLE001
            log.warning("web sign-in failed type=%s", type(e).__name__)
        ident = identity_from_claims(self.s.auth_mode, claims)
        if not ident or ident not in self.s.allowed:
            log.warning("web sign-in refused: identity not on the allowlist")
            return message("Not allowed", "This account can't approve messages here.", 403)
        resp = RedirectResponse(state.get("next", "/"), status_code=303)
        self.set_session(resp, ident)
        resp.delete_cookie(STATE_COOKIE)
        return resp
