# Switchboard: founder setup

*Written 2026-11-14, updated the same day for password sign-in. About 20 minutes, no IT needed.*

You'll end up with your own WhatsApp inside Claude. Claude reads your chats and writes drafts. Nothing sends until
you tap Send on a page that shows the exact message, the name and the number.

Everything runs in **your** accounts: your Unipile and your Railway. Nobody at AI Makeover holds your keys.
The easy way is to run the `switchboard-setup` skill in Cowork, which does the Railway part for you. These are the
same steps by hand.

**The one rule:** keys and passwords go straight into the website that asks for them, or your password manager.
Never paste them into Claude, an email, Slack, WhatsApp or a document.

---

## 1. Unipile (8 minutes, with your phone)

1. Go to **dashboardv2.unipile.com** and sign up (55 USD a month for up to 10 accounts).
2. **Accounts > Connect an account > WhatsApp.** On your phone: WhatsApp > Settings > **Linked devices > Link a
   device**, and scan the QR code.
3. Wait for **Connected** and the initial sync. Keep your phone on and online.
4. Note the WhatsApp **account id**. It isn't a secret.
5. **API Keys > Account API Keys > Create API Key.** Tick **Limit to a scope**, choose **New scope**, name it
   `switchboard`, and put only your WhatsApp account in it. Pick the longest expiry and set a calendar reminder a
   week before it. Leave the tab open.

For the first 24 hours after linking, don't start new chats with strangers. Don't link the same WhatsApp to another
tool (Beeper, a bot) at the same time.

## 2. Railway (5 minutes)

1. Sign up at **railway.com** (Hobby plan, about 5 USD a month) on your own account.
2. Click **Deploy on Railway** on the link AI Makeover sent you (or let Cowork deploy it, see the skill).
3. Fill in `WHATSAPP_ACCOUNT_ID` from step 1.4 and click **Deploy**. Railway creates your password and server secret.
4. Open the service > **Variables**:
   - `UNIPILE_API_KEY`: paste the key from the Unipile tab. Click **Deploy** on the banner.
   - `SWITCHBOARD_PASSWORD`: click the copy icon and save it in your password manager as "Switchboard".
5. **Settings > Networking:** copy the domain (like `switchboard-production-1234.up.railway.app`).

## 3. Add it to Claude (3 minutes)

**Team or Enterprise plan:** an Owner goes to claude.ai > **Admin settings > Connectors > Add custom connector**.
- Name: `Switchboard (<your name> only)`
- URL: `https://<your-domain>/mcp`
- Leave the OAuth fields empty. Add.
- Tool permissions: `draft_reply` = **Needs approval**.

Teammates will see it in their Connectors list. If they click Connect, they hit your password page and can't get
past it.

**Pro or Max:** Settings > Connectors > **Add custom connector**, same URL.

Then on your own account: **Customize > Connectors > Switchboard > Connect.** A Switchboard page opens and asks for
the password: paste it from your password manager. Then set `status`, `inbox`, `waiting_on_me`, `read_thread`,
`list_group_members` and `search_contacts` to **Always allow**.

**Claude Code:**

```bash
claude mcp add --transport http --scope user switchboard https://<your-domain>/mcp
```

## 4. Try it

- "Check Switchboard status." It should start with `Switchboard OK`.
- "Who's waiting on me on WhatsApp?"
- "Who's in the <group> group? How many numbers are hidden?"
- "Draft a reply to <someone you trust> saying this is a test." Open the link, sign in with the same password if
  asked, check the name, number and text, tap **Send**.

A good first scheduled task (Cowork > Scheduled): "Call Switchboard status and show the heartbeat. Then, using read
tools only, list who's waiting on me and suggest three replies. Don't draft or send anything."

## 5. When something needs re-doing

| What happened | Fix | Who |
|---|---|---|
| Claude asks you to connect again | Customize > Connectors > Switchboard > Connect, paste the password | You |
| `status` says WhatsApp needs re-linking | Unipile dashboard > Accounts > Reconnect, then scan the QR from WhatsApp > Linked devices | You (phone). Cowork tells you it happened |
| New Unipile key | Paste it into Railway > Variables > `UNIPILE_API_KEY`, Deploy | You paste; Cowork can redeploy and check `status` |
| New password | Generate 32 characters in your password manager, paste into `SWITCHBOARD_PASSWORD`, Deploy, Connect again | You paste; Cowork can redeploy |

Once everything works, **rotate the Unipile key** once: new key into Railway, Deploy, delete the old one.

## Limits

- Some group members' numbers are hidden by WhatsApp. Switchboard shows the name and marks them `number_hidden`.
- Voice notes show as `(voice note)`, no transcript.
- Search is by chat name only.
- Sends are paced: 40 seconds apart, 20 an hour, 30 a day on WhatsApp. It's for replies, not campaigns.
