# Switchboard: founder setup

*Written 2026-11-14, rewritten the same day to match the v2 `switchboard-setup` skill. About 25 minutes, no IT,
no GitHub.*

You'll end up with Claude reading your WhatsApp, LinkedIn and Instagram messages and writing replies. Nothing sends
until you tap Send on a page that shows the exact message, the name and the number.

Everything runs in **your** accounts: your password manager, your Unipile, your Railway. Nobody at AI Makeover
holds your keys. The easy way is the `switchboard-setup` skill in Cowork with Claude in Chrome, which does most of
the clicking. These are the same steps by hand.

**The one rule:** the Unipile key and your Switchboard password go straight from where they're made into the page
that asks for them. Never paste them into Claude, an email, Slack, WhatsApp or a document.

**Costs:** Railway about 5 USD a month (Hobby), Unipile from about 55 USD a month (up to 10 accounts). Both need a
card.

---

## 1. Make the password (3 minutes)

This password is what keeps Switchboard yours. Teammates on the same Claude org may see Switchboard in their list,
but without the password they can't open it.

In your password manager, make a new login:
- **Title:** `Switchboard`
- **Username:** your email
- **Password:** generated, **32 characters, letters and numbers, no symbols**
- Leave the website blank for now; you'll add your Switchboard address in step 4.

No password manager? Set one up first (1Password, Bitwarden, or Apple Passwords). Not a notes app.

## 2. Unipile (8 minutes, with your phone)

1. Sign up at **dashboardv2.unipile.com**.
2. **Accounts > Connect an account**, for each one you want:
   - **WhatsApp:** on your phone, WhatsApp > Settings > **Linked devices > Link a device**, and scan the code.
     Keep the phone on and online.
   - **LinkedIn / Instagram:** sign in in the window that opens and approve any prompt.
3. Wait for **Connected** on each, then note each **account ID**. They aren't secret.
4. **API Keys > Account API Keys > Create API Key.** Choose **Limit to a scope**, make a new scope called
   `switchboard` with only the accounts you just connected, pick the longest expiry, and create it. Copy the key and
   leave the tab open.

Use established numbers and accounts (a brand-new WhatsApp number can be blocked after a few new chats). For the
first 24 hours, don't start chats with strangers. Don't link another automation tool to the same WhatsApp.

## 3. Railway (5 minutes)

1. Sign up at **railway.com** on your own account (Hobby plan). Use a workspace only you can see.
2. Deploy Switchboard, either way:
   - **Template:** open the **Deploy on Railway** link AI Makeover gave you
     (https://railway.com/deploy/TzEHkA), fill in the account IDs, and Deploy.
   - **By hand:** New project > **Docker image** > `ghcr.io/ai-makeover/switchboard:latest`. Add a **volume** at
     `/data` (1 GB). **Settings > Networking > Generate domain** on port `8000`.
3. Service > **Variables**. None of these are secret:
   - `AUTH_MODE=password`, `PORT=8000`
   - `ENABLED_CHANNELS` = what you connected, for example `whatsapp,linkedin,instagram`
   - `UNIPILE_API_VERSION=v2`, `UNIPILE_API_BASE=https://api.unipile.com`
   - `WHATSAPP_ACCOUNT_ID`, `LINKEDIN_ACCOUNT_ID`, `INSTAGRAM_ACCOUNT_ID`, one per connected account
4. Open `https://<your-domain>/healthz`. It should say `{"ok":true}`.

## 4. The two secrets (3 minutes)

Same Variables screen:
1. New Variable `UNIPILE_API_KEY`: paste the key from the Unipile tab, Add. Close the Unipile tab.
2. New Variable `SWITCHBOARD_PASSWORD`: paste the password from your password manager, Add.

Railway restarts Switchboard after each Add. Then set the Switchboard login's **website** in your password manager
to `https://<your-domain>`, so it fills the password in for you.

## 5. Add it to Claude (3 minutes)

**Team or Enterprise:** an Owner goes to claude.ai > **Admin settings > Connectors > Add custom connector**.
- Name: `Switchboard (<your first name> only)`
- URL: `https://<your-domain>/mcp`
- Authentication: leave on **Sign in now**. OAuth client: leave on **Register automatically**. Request headers:
  leave empty (never put the password there). Add.

**Pro or Max:** Settings > Connectors > **Add custom connector**, same URL.

Then: **Connectors > Switchboard > Connect.** A Switchboard sign-in page opens: let your password manager fill the
password and click **Sign in**. Set tool permissions:
- **Always allow:** `status`, `inbox`, `waiting_on_me`, `read_thread`, `list_group_members`, `search_contacts`
- **Needs approval:** `draft_reply`

If adding fails with a vague error, wait an hour and retry before changing anything.

**Claude Code:**

```bash
claude mcp add --transport http --scope user switchboard https://<your-domain>/mcp
```

## 6. Try it

- "Check Switchboard status." It should start with `Switchboard OK`.
- "Who's waiting on me?"
- "Draft a reply to <someone you trust> saying this is a test." Open the link, sign in if asked, check the name,
  number and text, tap **Send**, and check it arrived.

A good first scheduled task: "Check Switchboard's status, list who's waiting on me, and suggest three replies.
Don't draft or send anything."

## 7. When something needs re-doing

| What happened | Fix |
|---|---|
| `status` says `key_missing` | `UNIPILE_API_KEY` didn't save: paste it again in Railway Variables |
| `status` says `key_rejected` | Make a new key in Unipile and paste it over `UNIPILE_API_KEY` |
| `status` says `needs_relink` | Unipile > Accounts > Reconnect, then scan the code or sign in again |
| Claude asks you to connect again | Connectors > Switchboard > Connect, password from the password manager |
| Forgot or leaked the password | New 32-character password in the password manager, paste over `SWITCHBOARD_PASSWORD`, Connect again |
| Railway made the service but never deployed | Check the service's source is the image above, or use the template link |

Once everything works, **rotate the Unipile key** once: new key into Railway, then delete the old one.

## Limits

- At most **30 sends a day on each platform**, with a gap between sends: 40 seconds on WhatsApp (and 20 an hour),
  60 seconds on LinkedIn and Instagram (10 an hour). It's for replies, not campaigns. Change any of them with
  `<CHANNEL>_SENDS_PER_DAY`, `<CHANNEL>_SENDS_PER_HOUR` and `<CHANNEL>_MIN_GAP_SECONDS`.
- Some WhatsApp group members' numbers are hidden. Switchboard shows the name and marks them `number_hidden`.
- Voice notes show as `(voice note)`, no transcript.
- Search is by chat name only.

## Older Unipile accounts (dashboard.unipile.com)

Key from dashboard.unipile.com/access-tokens. Set `UNIPILE_API_VERSION=v1` and `UNIPILE_API_BASE=https://<your DSN>`
(the DSN is on the dashboard home, like `api12.unipile.com:14234`). No account IDs needed.
