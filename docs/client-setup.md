# Switchboard: founder setup

*Written 2026-11-14. About 30 minutes, plus a 24-hour wait before the first brand-new chat.*

You'll end up with your own WhatsApp inside Claude. Claude reads your chats and writes drafts. Nothing sends until
you tap Send on a confirm page that shows the exact message, the name and the number.

Everything here runs in **your** accounts: your Unipile, your Railway, your Google. Nobody at AI Makeover holds your
keys. Do it on a laptop, with your phone next to you.

**The one rule:** keys and secrets go straight into the website that asks for them. Never paste them into Claude,
an email, Slack, WhatsApp or a document.

---

## 1. Unipile (the bridge to WhatsApp)

1. Go to **dashboardv2.unipile.com** and sign up. The plan is 55 USD a month for up to 10 accounts.
2. Open your Application (one is created for you). Go to **Accounts > Connect an account > WhatsApp**.
3. On your phone: WhatsApp > Settings > **Linked devices > Link a device**, and scan the QR code on screen.
4. Wait for the account to show **Connected** and for the initial sync to finish. Keep your phone on and online.
5. Copy the **account id** shown for WhatsApp. It's not a secret; keep it in a note for step 4.
6. **API Keys > Account API Keys > Create API Key.** Tick **Limit to a scope**, choose **New scope**, name it
   `switchboard`, and put only your WhatsApp account in it (add LinkedIn and Instagram later if you want them).
   Pick the longest expiry and put a calendar reminder a week before it.
7. Leave that tab open. You'll copy the key in step 4 and nowhere else.

**Don't** start new chats with strangers for the first 24 hours after linking. WhatsApp watches new linked devices,
and a burst of first messages is how numbers get banned. Replies to people already in your chats are fine.

Don't link the same WhatsApp to a second tool (Beeper, a bridge, another bot) at the same time. Two unofficial
linked devices raises the ban risk.

## 2. Railway (where Switchboard runs)

1. Sign up at **railway.com** (Hobby plan, about 5 USD a month). Use your own account, not a shared team.
2. Open the Switchboard template link we sent you and click **Deploy Now**.
3. Railway asks for variables. Fill in what you have now; the rest comes in step 4:
   - `ALLOWED_EMAILS`: the Google address you'll sign in with. Only this address will ever get in.
   - `UNIPILE_API_VERSION`: `v2`
   - `ENABLED_CHANNELS`: `whatsapp`
   - `SWITCHBOARD_SECRET`: leave the generated value.
4. Click **Deploy**. It shows as failed until the keys go in at step 4; that's expected. Open the service > **Settings > Networking** and copy the domain
   (something like `switchboard-production-1234.up.railway.app`).

The template already includes a volume at `/data`. Don't remove it: it holds your drafts and sign-in state.

## 3. Google sign-in

This is what stops anyone else using your connector.

1. Go to **console.cloud.google.com**, signed in with the address you put in `ALLOWED_EMAILS`.
2. Create a project called `switchboard`.
3. **APIs & Services > OAuth consent screen** (Google Auth Platform):
   - User type **External**. App name `Switchboard`. Your email as support and developer contact.
   - Data access / scopes: add `openid` and `.../auth/userinfo.email`. Nothing else.
   - Audience: leave it in **Testing**, and add your own address as the only **test user**.
4. **Clients > Create client > Web application.** Name it `switchboard`. Under **Authorised redirect URIs** add both:
   - `https://<your-domain>/auth/callback`
   - `https://<your-domain>/web/callback`
5. Click **Create**. Google shows a client ID and a client secret. Keep that window open for step 4.

Why Testing and not Internal: Internal would let in every account on your Google Workspace. Testing with only
`openid` and `email` doesn't hit Google's 7-day refresh limit.

## 4. Paste your keys into Railway

Railway > your Switchboard service > **Variables**. Add each one by typing or pasting straight from the other tab:

| Variable | From |
|---|---|
| `UNIPILE_API_KEY` | Unipile, step 1.6 |
| `UNIPILE_API_BASE` | `https://api.unipile.com` |
| `WHATSAPP_ACCOUNT_ID` | Unipile, step 1.5 |
| `GOOGLE_CLIENT_ID` | Google, step 3.5 |
| `GOOGLE_CLIENT_SECRET` | Google, step 3.5 |

Click **Deploy** to apply. Open `https://<your-domain>/healthz`: it should say `{"ok":true}`.

## 5. Add it to Claude

**On a Team or Enterprise plan** (an Owner does this once):
1. claude.ai > **Organization settings > Connectors > Add custom connector**.
2. Name: `Switchboard (<your name> only)`. URL: `https://<your-domain>/mcp`.
3. Authentication: sign in when needed, register automatically (dynamic client registration). Never "request
   headers" or "no sign-in".
4. Tool permissions: set `draft_reply` to **Needs approval**. Leave the read tools as they are.
5. Tell your team: it shows in their Connectors list as Custom, and Connect will refuse them. That's by design.

**On Pro or Max:** Settings > Connectors > **Add custom connector**, same URL.

Then on your own seat: **Customize > Connectors > Switchboard > Connect**, approve the consent screen, and sign in
with Google. In the connector's tool settings, set the five read tools to **Always allow** so triage doesn't ask
every time and scheduled tasks don't stall.

**Claude Code:**

```bash
claude mcp add --transport http --scope user switchboard https://<your-domain>/mcp
```

If adding the connector fails with a generic error, retry in an hour before changing anything. Anthropic's
custom-connector flow has had intermittent failures (Nov 2026).

## 6. Try it

- "Who's waiting on me on WhatsApp?"
- "Read my last 20 messages with <name>."
- "Who's in the <group> group? How many numbers are hidden?"
- "Draft a reply to <name> saying I'm free at 3."

The draft comes back with a link. Open it, check the text, the name and the number, tap **Send**. One tap per
message. A link works once and expires in 24 hours. If you sign in with any other Google account, it refuses.

A morning triage is a good first scheduled task (Cowork > Scheduled): "Using Switchboard read tools only, list who's
waiting on me, what's new in my key groups, and suggest three replies. Don't draft or send anything."

## 7. After setup

- **Rotate the Unipile key** once everything works: create a new one, paste it into Railway, redeploy, delete the
  old one. The old key has been on screen and in your clipboard.
- Keep your phone on and online. If WhatsApp signs the Unipile device out, Switchboard returns
  `upstream_auth` or `upstream_error` until you re-link in the Unipile dashboard.
- LinkedIn and Instagram: link them in Unipile, add them to the `switchboard` scope, add `LINKEDIN_ACCOUNT_ID` /
  `INSTAGRAM_ACCOUNT_ID` and set `ENABLED_CHANNELS=whatsapp,linkedin,instagram`.

## Limits worth knowing

- Some group members' numbers are hidden by WhatsApp (Communities, hidden-number groups). Switchboard shows their
  name and marks them `number_hidden`. No connector can get those numbers.
- Voice notes show as `(voice note)`. There's no transcript.
- There's no message search, only search by chat name.
- Sends are paced: 40 seconds apart, 20 an hour, 30 a day on WhatsApp. Switchboard is for replies, not campaigns.
