"""Settings, all from environment variables. Nothing secret has a default."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

CHANNELS = ("whatsapp", "linkedin", "instagram")

# Per-channel send limits. Defaults sit inside Unipile's published guidance (provider limits page,
# v2 docs updated 2026-11-13): WhatsApp 10-20 s between messages, LinkedIn 100 actions a day,
# Instagram 100 a day and 10 an hour. The WhatsApp gap is wider on purpose (40 s): a burst from an
# API client is what gets a personal number flagged.
DEFAULT_LIMITS = {
    "whatsapp": {"min_gap_s": 40, "per_hour": 20, "per_day": 30},
    "linkedin": {"min_gap_s": 60, "per_hour": 10, "per_day": 50},
    "instagram": {"min_gap_s": 60, "per_hour": 10, "per_day": 50},
}


class ConfigError(RuntimeError):
    pass


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


AUTH_MODES = ("password", "google", "github")
MIN_PASSWORD = 20


@dataclass
class Settings:
    base_url: str
    auth_mode: str
    allowed: frozenset[str]          # identities: "owner" (password), emails (google), "github:<login>" (github)
    password: str
    oauth_client_id: str
    oauth_client_secret: str
    secret: str
    unipile_version: str
    unipile_base: str
    unipile_key: str
    enabled: tuple[str, ...]
    account_ids: dict[str, str]
    data_dir: Path
    limits: dict[str, dict[str, int]] = field(default_factory=dict)
    drafts_per_hour: int = 30
    draft_ttl_s: int = 24 * 3600
    session_ttl_s: int = 12 * 3600

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get

        base = env("BASE_URL", "").strip()
        if not base and env("RAILWAY_PUBLIC_DOMAIN"):
            base = "https://" + env("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if not base:
            raise ConfigError("BASE_URL is unset (or deploy on Railway with a public domain)")

        mode = env("AUTH_MODE", "password").strip().lower() or "password"
        if mode not in AUTH_MODES:
            raise ConfigError("AUTH_MODE must be password, google or github")
        password, client_id, client_secret = "", "", ""
        if mode == "password":
            password = env("SWITCHBOARD_PASSWORD", "").strip()
            if len(password) < MIN_PASSWORD:
                raise ConfigError(f"SWITCHBOARD_PASSWORD must be at least {MIN_PASSWORD} characters")
            allowed = frozenset({"owner"})
        elif mode == "google":
            allowed = frozenset(e.strip().lower() for e in env("ALLOWED_EMAILS", "").split(",") if e.strip())
            client_id, client_secret = env("GOOGLE_CLIENT_ID", "").strip(), env("GOOGLE_CLIENT_SECRET", "").strip()
        else:
            allowed = frozenset("github:" + u.strip().lower().lstrip("@")
                                for u in env("ALLOWED_GITHUB_USERS", "").split(",") if u.strip())
            client_id, client_secret = env("GITHUB_CLIENT_ID", "").strip(), env("GITHUB_CLIENT_SECRET", "").strip()
        if not allowed:
            raise ConfigError("the allowlist is empty: refusing to start with nobody allowed in")
        if mode != "password" and not (client_id and client_secret):
            raise ConfigError(f"{mode.upper()}_CLIENT_ID and {mode.upper()}_CLIENT_SECRET are required in {mode} mode")

        version = env("UNIPILE_API_VERSION", "v1").strip().lower()
        if version not in ("v1", "v2"):
            raise ConfigError("UNIPILE_API_VERSION must be v1 or v2")
        ubase = env("UNIPILE_API_BASE", "").strip() or env("UNIPILE_DSN", "").strip()
        if not ubase and version == "v2":
            ubase = "https://api.unipile.com"
        if not ubase:
            raise ConfigError("UNIPILE_API_BASE (your v1 DSN) is unset")
        if not ubase.startswith("http"):
            ubase = "https://" + ubase
        ubase = ubase.rstrip("/")
        # Accept a base with or without the version suffix.
        for suffix in ("/api/v1", "/v2"):
            if ubase.endswith(suffix):
                ubase = ubase[: -len(suffix)]

        enabled = tuple(c.strip().lower() for c in env("ENABLED_CHANNELS", "whatsapp").split(",") if c.strip())
        bad = [c for c in enabled if c not in CHANNELS]
        if bad or not enabled:
            raise ConfigError("ENABLED_CHANNELS must list whatsapp, linkedin and/or instagram")

        accounts = {c: env(f"{c.upper()}_ACCOUNT_ID", "").strip() for c in CHANNELS}

        limits = {}
        for c, d in DEFAULT_LIMITS.items():
            p = c.upper()
            limits[c] = {
                "min_gap_s": _int(f"{p}_MIN_GAP_SECONDS", d["min_gap_s"]),
                "per_hour": _int(f"{p}_SENDS_PER_HOUR", d["per_hour"]),
                "per_day": _int(f"{p}_SENDS_PER_DAY", d["per_day"]),
            }

        required = {
            "UNIPILE_API_KEY": env("UNIPILE_API_KEY", "").strip(),
            "SWITCHBOARD_SECRET": env("SWITCHBOARD_SECRET", "").strip(),
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ConfigError("missing required variables: " + ", ".join(missing))
        if len(required["SWITCHBOARD_SECRET"]) < 32:
            raise ConfigError("SWITCHBOARD_SECRET must be at least 32 characters")

        return cls(
            base_url=base.rstrip("/"),
            auth_mode=mode,
            allowed=allowed,
            password=password,
            oauth_client_id=client_id,
            oauth_client_secret=client_secret,
            secret=required["SWITCHBOARD_SECRET"],
            unipile_version=version,
            unipile_base=ubase,
            unipile_key=required["UNIPILE_API_KEY"],
            enabled=enabled,
            account_ids=accounts,
            data_dir=Path(env("DATA_DIR", "/data")),
            limits=limits,
            drafts_per_hour=_int("DRAFTS_PER_HOUR", 30),
        )
