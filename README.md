# Switchboard

*Written 2026-11-14, updated 2026-11-14 (password sign-in, status tool). v0.2.0.*

Your own WhatsApp in Claude, for you only. Switchboard is a small remote MCP server in front of your Unipile
account. Claude (chat, Cowork, scheduled tasks, Duet, Claude Code) can read your chats and write drafts. It can't
send. A message goes out only when you open a confirm page, see the exact text and the recipient's name and number,
and tap Send.

The name is the old telephone switchboard, where an operator connected every call by hand. LinkedIn and Instagram
DMs run on the same server once you switch them on.

## Sign-in

Every custom connector on a Claude Team org shows up for every member, so the server decides who gets in.

**`AUTH_MODE=password` (default).** Switchboard runs its own small OAuth server, so Claude's connector flow
(automatic registration, PKCE, refresh tokens) works unchanged. When you click Connect, the page that opens is
Switchboard's, and it asks for the owner password: 32 random characters that Railway generates at deploy and that
you keep in your password manager.
- 5 wrong tries from one address locks that address out for 15 minutes; 20 wrong tries from anywhere locks all
  sign-in for an hour. Each wrong try also waits most of a second.
- The comparison is constant-time, and the form only works over HTTPS.
- Only Claude's callbacks (`claude.ai`, `claude.com`) and Claude Code's localhost loopback can register.
- Changing the password signs out every connected client and every browser.

**`AUTH_MODE=google` or `github`.** FastMCP's OAuth proxy in front of Google or GitHub, with an allowlist
(`ALLOWED_EMAILS` or `ALLOWED_GITHUB_USERS`). The allowlist is checked when the provider returns (anyone else's
code is destroyed, so no token is ever issued), again at the token endpoint, and again on every request. Use this
when the owner already lives in a Google Workspace or GitHub account and IT can create an OAuth client.

The confirm page uses the same sign-in through a signed session cookie.

## Safety

- **No send tool.** `draft_reply` stores the exact chat and text on the server and returns a confirm link. Nothing
  the model says afterwards can change a stored draft. Sending needs a signed-in browser, a POST with a CSRF token,
  and works once. Links in a draft are called out, and group sends are flagged.
- **Drafts only go to chats that already exist.** A raw number, or a chat id the provider doesn't know, is refused.
- **Pacing on the server.** WhatsApp: 40 s between sends, 20 an hour, 30 a day. LinkedIn and Instagram: 60 s,
  10 an hour, 30 a day. Inside Unipile's published guidance. Override per channel with variables.
- **Inbound text is treated as hostile.** Links become `[link: domain]`; zero-width, bidi and tag characters are
  stripped; long whitespace collapses; every result says the content is data, not instructions (the Invariant Labs
  WhatsApp MCP exfiltration, Apr 2025).
- **Fixed error codes.** Tools never return exception text.
- **IDs are validated before any URL is built**, then percent-encoded.
- **No message content or numbers in logs.** Access logs are off (confirm URLs carry a token). A draft's text is
  wiped once it's sent, discarded or expired.

Out on purpose: first-contact waves, deletes, leaving groups, attachments.

## Tools

| Tool | Kind | What it does |
|---|---|---|
| `status` | read | Is the Unipile key good and WhatsApp still linked? Sends left today, the exact fix if something dropped, and a one-line `heartbeat` for a morning brief |
| `inbox` | read | Latest chats: name, who spoke last, unread, short preview |
| `waiting_on_me` | read | Chats where the other person spoke last, within N days |
| `read_thread` | read | Last N messages of one chat. Voice notes show as `(voice note)` |
| `list_group_members` | read | Names, saved contact names, numbers where WhatsApp exposes them, and a count of hidden numbers |
| `search_contacts` | read | Find a person or group by name in the latest 500 chats |
| `draft_reply` | write (needs approval) | Store a reply to an existing chat and return a confirm link. Never sends |

Read tools carry `readOnlyHint: true`, so Claude runs them without prompting and scheduled tasks don't stall.
Set `draft_reply` to **Needs approval** in the org's tool permissions.

A morning brief can start with: "Call Switchboard `status` and show its heartbeat line. If it starts with ALERT,
say so first."

## Deploy on Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/switchboard)

1. In your password manager, generate a 32-character password (letters and numbers) called "Switchboard".
2. Deploy the template. It runs the public image `ghcr.io/ai-makeover/switchboard:latest` with a volume at `/data`
   and a domain on port 8000. Fill in the account IDs for the channels you use.
3. In Railway > switchboard > Variables, add `UNIPILE_API_KEY` (your Unipile key) and `SWITCHBOARD_PASSWORD` (the
   password from step 1).
4. In Claude, add a custom connector with the URL `https://<domain>/mcp`, then Connect and enter the password.

The server boots without the Unipile key or the password: `status` tells you the key is missing, and the sign-in
page tells you to set `SWITCHBOARD_PASSWORD`. Without `SWITCHBOARD_SECRET` it makes its own on first boot and keeps
it on the volume.

**From Cowork with the Railway connector** (no template needed): create a project, `create-service`, then
`connect-service-source` with the image above, attach a volume at `/data`, generate a domain on port 8000, and set the non-secret variables. The founder then pastes
`UNIPILE_API_KEY` and `SWITCHBOARD_PASSWORD` into Railway themselves. The `switchboard-setup` skill does exactly this. Founder walkthrough:
[docs/client-setup.md](docs/client-setup.md).

### Unipile v1 and v2

`UNIPILE_API_VERSION=v1` uses your per-customer DSN (`UNIPILE_API_BASE=https://apiNN.unipile.com:PORT`) and finds
your WhatsApp account by itself. `v2` uses `https://api.unipile.com` and needs `WHATSAPP_ACCOUNT_ID`. On v2, use a
**scoped key** limited to your messaging accounts. No Unipile key is read-only, which is why the send gate lives here.

## When something needs re-doing

| What happened | What you see | Fix | Can Cowork do it through the Railway connector? |
|---|---|---|---|
| Claude's connection to Switchboard expired (refresh lapses after 90 days, or the password changed) | Claude asks you to connect again, or tools fail to authorise | Customize > Connectors > Switchboard > Connect, paste the password | No. It's your click and your password |
| WhatsApp got unlinked (phone offline for weeks, device removed) | `status` says `needs_relink` and its heartbeat starts with ALERT | Unipile dashboard > Accounts > Reconnect, then WhatsApp > Linked devices > Link a device and scan the QR | Cowork can spot it (`status`) and tell you. The re-scan needs your phone |
| Unipile key rotated or expired | `status` says `key_rejected` or `key_missing` | Paste the new key into Railway > Variables > `UNIPILE_API_KEY`, Deploy | Partly. You paste the key (the connector never handles secrets); Cowork can then redeploy and run `status` to confirm |
| Password reset | Old password stops working everywhere | Generate a new 32-character password in your password manager, paste it into `SWITCHBOARD_PASSWORD`, Deploy, then Connect again in Claude | Partly. You paste the password; Cowork can redeploy |

## The image and the template

This repo and its image are public, so a founder needs only Railway: no GitHub account, no repo invite. Every push to
`main` builds `ghcr.io/ai-makeover/switchboard:latest` (and a tag per commit) through `.github/workflows/image.yml`.

The template is published on Railway's marketplace as **Switchboard** (https://railway.com/deploy/switchboard),
owned by the AI Makeover Railway workspace. It runs the image above with a volume at `/data` and a domain on port 8000.
Its defaults are `AUTH_MODE=password`, `PORT=8000`, `ENABLED_CHANNELS=whatsapp`, `UNIPILE_API_VERSION=v2`,
`UNIPILE_API_BASE=https://api.unipile.com` and `*_SENDS_PER_DAY=30`; `WHATSAPP_ACCOUNT_ID` is the one required input.
Secrets never go in the template: the founder adds `UNIPILE_API_KEY` and `SWITCHBOARD_PASSWORD` after deploy. Edit it
at railway.com > AI Makeover workspace > Templates.

## Develop

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[test]"
PYTHONPATH=tests .venv/bin/python -m pytest -q
```

Tests stub Unipile, Google and GitHub entirely, and include the full password OAuth handshake over HTTP.
