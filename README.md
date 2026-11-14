# Switchboard

*Written 2026-11-14. v0.1.0.*

Your own WhatsApp in Claude, for you only. Switchboard is a small remote MCP server that sits in front of your
Unipile account. Claude (chat, Cowork, scheduled tasks, Duet, Claude Code) can read your chats and write drafts.
It can't send. A message goes out only when you open a confirm page, see the exact text, the recipient's name and
number, and tap Send.

LinkedIn and Instagram DMs run on the same server once you switch them on.

## Why it's built this way

A connector added to a Claude Team org shows up for every member. Switchboard makes that safe by refusing everyone
who isn't on its allowlist:

- **Sign-in is Google, and only `ALLOWED_EMAILS` get through.** The check runs three times: when Google hands the
  identity back (anyone else gets a refusal page and their authorization code is destroyed, so no token is ever
  issued), again at the token endpoint, and again on every request.
- **No send tool.** `draft_reply` stores the exact chat and text on the server and returns a confirm link. Nothing
  the model says afterwards can change a stored draft. The confirm page needs its own Google sign-in, a POST with a
  CSRF token, and works once. Links in a draft are called out, and group sends are flagged.
- **Drafts only go to chats that already exist.** A raw number, or a chat id the provider doesn't know, is refused.
- **Pacing on the server.** WhatsApp: 40 s between sends, 20 an hour, 30 a day. LinkedIn and Instagram: 60 s,
  10 an hour, 50 a day. Inside Unipile's published guidance (WhatsApp 10 to 20 s between messages; LinkedIn and
  Instagram 100 actions a day). Override per channel with variables.
- **Inbound text is treated as hostile.** Links become `[link: domain]`; zero-width, bidi and tag characters are
  stripped; long whitespace collapses; every result carries a note that the content is data, not instructions.
  This answers the published Invariant Labs WhatsApp MCP exfiltration (Apr 2025).
- **Fixed error codes.** A tool never returns exception text. Upstream errors become `upstream_error`,
  `upstream_auth`, `not_found` and so on.
- **IDs are validated before any URL is built**, then percent-encoded. No dot-segments, slashes or query characters.
- **No message content or numbers in logs.** Request access logs are off (confirm URLs carry a token). A draft's
  text is wiped from the database once it's sent, discarded or expired.

What's out on purpose: first-contact waves, deletes, leaving groups, attachments.

## Tools

| Tool | Kind | What it does |
|---|---|---|
| `inbox` | read | Latest chats: name, who spoke last, unread, short preview |
| `waiting_on_me` | read | Chats where the other person spoke last, within N days |
| `read_thread` | read | Last N messages of one chat. Voice notes show as `(voice note)` |
| `list_group_members` | read | Names, saved contact names, numbers where WhatsApp exposes them, and a count of hidden numbers |
| `search_contacts` | read | Find a person or group by name in the latest 500 chats |
| `draft_reply` | write (needs approval) | Store a reply to an existing chat and return a confirm link. Never sends |

Read tools carry `readOnlyHint: true`, so Claude runs them without prompting and scheduled tasks don't stall.
Set `draft_reply` to **Needs approval** in the org's tool permissions.

Chat ids look like `whatsapp:<id>` and come from `inbox`, `waiting_on_me` or `search_contacts`.

## Deploy on Railway

1. Deploy the template (or *New project > Deploy from GitHub repo* on this repo). Add a volume mounted at `/data`.
   Generate a public domain.
2. Create a Google OAuth client: see [docs/client-setup.md](docs/client-setup.md#3-google-sign-in). Redirect URIs:
   `https://<domain>/auth/callback` and `https://<domain>/web/callback`.
3. Fill the variables (names in [.env.example](.env.example)). Type secrets straight into Railway, never into chat
   or a file.
4. Add the connector in Claude: URL `https://<domain>/mcp`, sign in when needed, dynamic client registration.

The full founder walkthrough is [docs/client-setup.md](docs/client-setup.md).

### Unipile v1 and v2

`UNIPILE_API_VERSION=v1` uses your per-customer DSN (`UNIPILE_API_BASE=https://apiNN.unipile.com:PORT`) and can
find your WhatsApp account by itself. `v2` uses `https://api.unipile.com` and needs the account ids. A v2
**scoped key** limited to your messaging accounts is the better key: it can't touch anything else on the
Unipile account. No Unipile key is read-only, which is why the send gate lives here.

## Distributing it to founders: can a client deploy from a private repo without GitHub?

**No.** Railway lets a template point at a private GitHub repo, but the person deploying it has to connect GitHub to
Railway and grant access to that repo (Railway docs, "Create a Template > Private repo support", read 14 Nov 2026:
"To deploy a template that includes a private repo, look for the GitHub panel in the Account Integrations section
... select Edit Scope to grant Railway access to the desired private repos"). So a private-repo template means every
founder needs a GitHub account and an invite to this repo.

The options:

| Route | Founder needs | Source exposed | Updates |
|---|---|---|---|
| Template on this private repo | Railway + GitHub + repo invite | To each invitee | Railway's update prompts |
| Public template repo | Railway only | To everyone | Railway's update prompts |
| **Private Docker image in a Railway template** | **Railway only** | **No** | Redeploy pulls `:latest` |
| Founder forks into their own GitHub | Railway + GitHub | To them | They pull |

**Recommendation: private Docker image.** The workflow in `.github/workflows/image.yml` tests and pushes
`ghcr.io/ai-makeover/switchboard` on every push to `main`. In Railway's template editor, set the service source to that
image and enter a GHCR username plus a read-only `read:packages` token. Railway stores those credentials hidden
(founders can't see them, can't SSH in, can't change the image source; "Templates > Private Docker Images", read
14 Nov 2026). The founder clicks Deploy, pastes their own Unipile key, Google client and email, and never touches
GitHub. The trade-off: Railway doesn't prompt founders about image updates, so a fix ships when they hit Redeploy.

One caveat either way: whoever deploys the template owns the service and its variables, so each founder's key stays
in their Railway account, not ours.

## Develop

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[test]"
PYTHONPATH=tests .venv/bin/python -m pytest -q
```

Tests stub Unipile and Google entirely. They never touch a real account.

## Rotating keys

- Unipile: create a new key, paste it into Railway's `UNIPILE_API_KEY`, redeploy, delete the old key.
- Google client secret: add a new secret in the Google console, update Railway, then disable the old one.
- `SWITCHBOARD_SECRET`: changing it signs everyone out (you reconnect once) and voids open confirm links.
