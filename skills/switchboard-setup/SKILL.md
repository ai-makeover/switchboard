---
name: switchboard-setup
description: Walk a founder through setting up Switchboard, their own private connector that lets Claude read their WhatsApp, LinkedIn and Instagram DMs and draft replies. Beginner-friendly, about 25 minutes, Claude does most of the clicking in Chrome. Use for /switchboard-setup, "connect my WhatsApp", "set up Switchboard", or the AI Makeover workshop messaging add-on.
---

# Switchboard setup

Version 2, 14 Nov 2026. Rewritten from a real setup run, for AI Makeover workshops.

## What this is (say this to them first, in your own words)

"Switchboard lets Claude read your WhatsApp, LinkedIn and Instagram messages and write replies for you. It runs
on your own small server, uses your own messaging account, and is locked with a password only you know. Claude
can never send anything by itself. Every reply waits for you to check it and tap Send. Setup takes about 25
minutes. I'll do most of the clicking. I'll tell you exactly when it's your turn."

## How to run this

- **Plain words.** No jargon. If you must use a word like "server" or "API key", explain it in one short line
  the first time ("an API key is like a password that lets one app talk to another").
- **One step at a time.** Say what you're doing, do it, then say exactly what they need to do next. Wait for
  "done" before moving on.
- **Do it for them.** Use Claude in Chrome to open pages, click through menus and fill in anything that isn't a
  secret. Hand over only for: creating accounts, paying, scanning a QR code, creating and pasting secrets, and
  final "Add" or "Save" clicks that change their settings.
- **Hand-offs sound like this:** "Your turn: click the black Add button." Point at what they'll see.
- **Explain the why** at the moments noted below. People trust a setup more when they know why each piece is
  there.
- Use AskUserQuestion for choices and yes/no checks when you have it.

## Safety rules (never break these)

1. **No secret ever goes into the chat.** That means the Unipile API key and the Switchboard password. If they
   paste one here, stop. Tell them it's exposed and have them make a new one before carrying on.
2. **Don't look while a secret is on screen.** Before they create the API key or the password, stop taking
   screenshots or reading that page. Start again only after they say "done" and the secret is gone from view.
3. **Never type, pass or store a secret yourself**, in the browser or in any tool. They copy and paste it.
4. Never ask for their phone number or what their messages say.
5. Ask before anything that costs money, creates an account, or changes a setting. Anything they asked you to
   do in this setup counts as asked, but confirm the first time you click Add or Save on their behalf.

## Before you start (2 minutes)

Check, and fix anything missing:

- **Claude in Chrome is connected.** Look for the `claude-in-chrome` browser tools (load them with ToolSearch).
  If they aren't there or don't respond, explain: "I need a browser connection so I can do most of the clicking
  for you." Ask them to set up Claude in Chrome (the card that appears, or the Chrome Web Store) and sign in
  with the same Claude account, then tell you when it's done. If they really can't, carry on and give them
  click-by-click directions instead.
- **The Railway connector is connected.** Look for the `Railway` tools. If missing: Customize > Connectors >
  Browse > Railway > Connect. They'll need a Railway account; the Hobby plan is about 5 USD a month.
- **A password manager.** Ask which one they use (see step 1).
- **Their phone, with WhatsApp open**, if they're connecting WhatsApp.
- **Costs, said plainly:** Railway about 5 USD a month, Unipile from about 55 USD a month (up to 10 accounts).

## 1. Make the password (3 minutes)

**Why (say this):** "This password is what keeps Switchboard yours. Anyone in your Claude workspace might see
Switchboard in their list, but without this password they can't open it. We'll keep it only in your password
manager, never in a chat or a note."

Ask which password manager they use, then guide them. They do this part themselves.

**1Password**
1. Click **+ New Item** and choose **Login**.
2. **Title:** `Switchboard`
3. **Username:** your email. Switchboard only asks for the password, but this keeps it tidy.
4. **Password:** click into the field, choose **Create a New Password**. Set **Random Password**, length
   **32**, **Numbers on**, **Symbols off**.
5. Leave **Website** blank for now. We'll add it once we have your Switchboard address.
6. Click **Save**.

**Bitwarden:** New item > Login. Name `Switchboard`, username your email. Click the generate icon in the password
field: length 32, uppercase, lowercase and numbers on, special characters off. Save.

**Apple Passwords (Mac or iPhone):** Passwords app > **+** > Website or label `Switchboard`, user name your email.
Use the suggested strong password, or type a 32-character mix of letters and numbers. Save.

**Google Password Manager or something else:** make a login called `Switchboard`, with your email as the
username and a generated password of at least 32 letters and numbers, no symbols.

**No password manager?** Recommend one before going on (1Password or their device's built-in one). Don't use a
notes app or a document.

## 2. Unipile: connect your messaging accounts (8 minutes, with your phone)

**Why (say this):** "Unipile is the service that safely connects to WhatsApp, LinkedIn and Instagram for us. It's
your own account, so your messages never pass through anyone else's."

Ask first: "Do you already have Unipile?" If they're on the older dashboard (dashboard.unipile.com), see
"Older Unipile accounts" at the bottom. Everyone else uses the new dashboard:

1. Open **dashboardv2.unipile.com** in Chrome for them. "Your turn: sign up and pick a plan." Wait for done.
2. Ask which accounts they want Claude to read: WhatsApp, LinkedIn, Instagram, or a mix.
3. Go to **Accounts > Connect an account** for them, then hand over for each one:
   - **WhatsApp:** "On your phone, open WhatsApp > Settings > Linked devices > Link a device, and scan the code
     on screen." Keep the phone on and online.
   - **LinkedIn / Instagram:** "Sign in with your account in the window that opens." Approve any app prompt.
4. Wait until each shows **Connected**. Then read each account's **account ID** from the dashboard yourself.
   Account IDs aren't secret.
5. **The API key.** Go to **API Keys > Account API Keys** for them. Then hand over and stop looking (safety
   rule 2): "Your turn: click **Create API Key**, choose **Limit to a scope**, make a new scope called
   `switchboard` with only the accounts you just connected, pick the longest expiry, and create it. Copy the key,
   and leave that tab open. Don't paste it here."

Say these warnings plainly:
- Use established numbers and accounts. A brand-new WhatsApp number can get blocked after a few new chats.
- For the first 24 hours, don't start chats with strangers from these accounts.
- Don't link any other automation tool to the same WhatsApp.

## 3. Build their Switchboard (you do this, 4 minutes)

**Why (say this):** "Now I'm setting up your own small server on Railway. It's in your account, so only you
control it."

With the Railway connector:

1. `list-workspaces`. Show the names and ask which one only they can see. Don't trust the "personal" label: a
   shared workspace can show it too. If every workspace is shared, have them create a personal one first
   (Railway > New workspace).
2. `create-project` named `switchboard` in that workspace.
3. `create-service` named `switchboard`, then `connect-service-source` with image
   `ghcr.io/ai-makeover/switchboard:latest`. This needs no GitHub access. If the image won't deploy, open the
   **Deploy on Railway** template link instead (https://railway.com/deploy/switchboard), fill in the account IDs, deploy, then carry on
   from step 4 below.
4. `create-volume` on the service: mount path `/data`, 1024 MB. This is where Switchboard keeps its sign-in data.
5. `generate-domain` on the service, target port `8000`. Note the address.
6. `set-variables` on the service. None of these are secret:
   - `AUTH_MODE=password`, `PORT=8000`
   - `ENABLED_CHANNELS` = the ones they connected, for example `whatsapp,linkedin,instagram`
   - `UNIPILE_API_VERSION=v2`, `UNIPILE_API_BASE=https://api.unipile.com`
   - One per connected account: `WHATSAPP_ACCOUNT_ID`, `LINKEDIN_ACCOUNT_ID`, `INSTAGRAM_ACCOUNT_ID`
   - The daily send cap, 30 on every channel: `WHATSAPP_SENDS_PER_DAY=30`, `LINKEDIN_SENDS_PER_DAY=30`,
     `INSTAGRAM_SENDS_PER_DAY=30`
7. Check `list-deployments` until it says `SUCCESS`, then open `https://<address>/healthz` in Chrome. It should
   say `{"ok":true}`.

If no deployment appears after a minute, check `describe-service`. A source with no image means step 3 didn't
take.

## 4. Add the two secrets (3 minutes)

**Why (say this):** "Two things only you should handle: the Unipile key and your password. I'll get everything
ready, and you just paste."

1. Open the service's **Variables** page in Chrome
   (`railway.com/project/<project id>/service/<service id>/variables`).
2. Click **New Variable**, type the name `UNIPILE_API_KEY`, and click into the empty value box.
   "Your turn: paste the key from your Unipile tab, then click **Add**. You can close the Unipile tab now."
3. Click **New Variable** again, type `SWITCHBOARD_PASSWORD`, and click into the value box.
   "Your turn: copy the password from your Switchboard login in your password manager, paste it here, and click
   **Add**."
4. Railway restarts Switchboard by itself after each Add. Check it shows both names (`list-variables` shows
   names only, never values), then wait for `SUCCESS`.
5. "Last thing in your password manager: edit the Switchboard login and set **Website** to
   `https://<address>`. It'll then fill the password in for you."

## 5. Add Switchboard to Claude (3 minutes)

Ask which plan they're on.

**Team or Enterprise.** Only an Owner can add it. Open claude.ai > **Admin settings > Connectors** in Chrome and
click **Add custom connector**. Fill in:
- **Name:** `Switchboard (<their first name> only)`
- **URL:** `https://<address>/mcp`
- **Authentication:** leave on **Sign in now** (it says "Detected").
- **OAuth client:** leave on **Register automatically** (also "Detected").
- **Request headers:** leave empty. Never put the password here.
"Your turn: check it and click **Add**."

**Pro or Max.** Same, from **Settings > Connectors > Add custom connector**.

**Why (say this):** "Your teammates may see Switchboard in their list. If they click Connect, they get your
password page, and without the password they can't get in. Your messages stay yours."

Then:
1. Open Switchboard in the connectors list. "Your turn: click **Connect**. A Switchboard sign-in page opens. Let
   your password manager fill the password, then click **Sign in**."
2. Tool permissions. Ask before changing them, then set them yourself in Chrome:
   - **Always allow:** `status`, `inbox`, `waiting_on_me`, `read_thread`, `list_group_members`, `search_contacts`
     (these only read).
   - **Needs approval:** `draft_reply`.
3. If adding fails with a vague error, wait an hour and try again before changing anything.

## 6. Try it (3 minutes)

1. Run `status`. You want a line starting `Switchboard OK`. If not, see "When something goes wrong".
2. "Ask me who's waiting on you." Run `waiting_on_me`.
3. A test reply: `draft_reply` to someone they trust, "Switchboard test, ignore". "Your turn: open the link, check
   the name, number and message, tap **Send**, and check it arrived." This is the only way anything ever sends.
4. Offer a morning check-in as a scheduled task: "Check Switchboard's status, list who's waiting on me, and
   suggest three replies. Don't draft or send anything."

## What to tell them about how it works

- **Reading:** Claude can read your chats, threads, groups and contacts on every connected account, any time.
- **Sending:** Claude only drafts. You check the exact text and recipient on a page and tap Send yourself.
- **Safety limits:** at most 30 sends a day on each platform, with a gap between sends (40 seconds on WhatsApp,
  60 on LinkedIn and Instagram). It's for replies, not campaigns. These limits keep your accounts from being
  flagged.
- **Groups:** WhatsApp hides some members' numbers. They show by name, marked as hidden.
- **Voice notes** show as "(voice note)", with no transcript.

## When something goes wrong

| What happened | What you do | What they do |
|---|---|---|
| Railway made the service but never deployed | Check the source in `describe-service`; reconnect the image, or use the template link (https://railway.com/deploy/switchboard) | Nothing |
| `status` says `key_missing` | Check `UNIPILE_API_KEY` is in Variables | Paste the key again, click Add |
| `status` says `key_rejected` | Ask them for a new key | Make a new key in Unipile, paste it into `UNIPILE_API_KEY` |
| `status` says `needs_relink` | Tell them plainly | Unipile > Accounts > Reconnect, scan the code or sign in again |
| Claude asks to connect again | Nothing | Connectors > Switchboard > Connect, password from the password manager |
| Forgot or leaked the password | Open Variables for them, ready to paste | New 32-character password in the password manager, paste into `SWITCHBOARD_PASSWORD`, then Connect again |
| Adding the connector fails with a vague error | Wait an hour, then retry | Nothing |

## Older Unipile accounts (dashboard.unipile.com)

Only if they already use the older dashboard and don't want to move:
- Key: dashboard.unipile.com/access-tokens > generate a token named `switchboard` (same "don't look" rule).
- Ask them to read you the **DSN** from the dashboard home (like `api12.unipile.com:14234`). It isn't secret.
- Variables: `UNIPILE_API_VERSION=v1` and `UNIPILE_API_BASE=https://<DSN>`. No account IDs needed, as long as they
  have one account of each type.

## Facilitator notes (workshops)

- Ask people to arrive with Claude in Chrome installed, the Railway connector added, a password manager, and their
  phone. That saves the first 10 minutes.
- Railway and Unipile both need a card. Mention it before the session.
- The most common stall is the browser not being connected. Check it first.
