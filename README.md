# Discordant v1.0.0

> ⚠️ **Note:** This plugin was built with AI assistance (Claude). I'm not a Python expert — there may be bugs or rough edges. Feedback welcome!

Hands-free Discord DM integration for [COVAS:NEXT](https://ratherrude.github.io/Elite-Dangerous-AI-Integration/). Hear incoming DMs announced by your AI and dictate replies by voice — no headset flip required.

Built for VR players who can't easily check their phone mid-session.

## What It Does

- **Real-time DM notifications** — COVAS announces incoming DMs as they arrive
- **Voice replies** — dictate your reply word for word, COVAS sends it
- **Check recent DMs** — ask COVAS to summarise your recent messages on demand
- **Read a conversation** — ask COVAS to read back a thread with a specific person

## How It Works

Discordant connects to Discord using a bot token. This means your friends message **your bot** rather than your personal Discord account. You can name the bot anything you like (your gamertag, a callsign, whatever makes sense to your crew) so it feels natural to them.

This approach was chosen deliberately — it is the only way to receive Discord DMs programmatically without risking your personal account under Discord's Terms of Service.

> **Important:** Discord requires users to share a server with a bot before they can DM it. You'll need to create a private server, add the bot to it, and have your friends join it once. After that initial setup, everyone can DM the bot directly and never needs to use the server again.

---

## Setup

### Step 1 — Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** and give it a name your friends will recognise (e.g. your gamertag)
3. Go to **Bot** in the left sidebar
4. Click **Add Bot** → confirm
5. Under **Privileged Gateway Intents**, enable **all three**:
   - **Presence Intent**
   - **Server Members Intent**
   - **Message Content Intent**
6. Click **Reset Token** → copy and save your bot token somewhere safe  
   *(You'll only see it once — if you lose it, you'll need to reset it again)*

### Step 2 — Set a Profile Picture (Optional but Recommended)

Still in the Developer Portal under **General Information**, upload a profile picture for the bot. Using your gaming avatar or something recognisable makes it less confusing for friends when they search for it.

### Step 3 — Create a Private Server and Add the Bot

Discord requires users to share a server with a bot before DMs are permitted. You only need to do this once.

1. In Discord, click the **+** button in your server list → **Create My Own** → **For me and my friends**
2. Name it anything — "Relay" or your gamertag works fine
3. Back in the Developer Portal, go to **OAuth2** → **URL Generator**
4. Under **Scopes** check `bot`
5. Under **Bot Permissions** check `Send Messages` and `Read Message History`
6. Copy the generated URL at the bottom, open it in your browser, and add the bot to your new private server

### Step 4 — Invite Your Friends to the Server

Send your friends an invite link to the private server. They only need to join once — after that they can DM the bot directly without ever using the server.

> **Tip:** Let them know to save the bot as a contact after their first DM so they can find it easily in future.

### Step 5 — Install the Plugin

1. Place the `Discordant` folder in:
   ```
   %appdata%\com.covas-next.ui\plugins\
   ```
***IMPORTANT: The folder must be named "Discordant" no version numbers - Github automatically adds a -X.x version number to the folder***
2. Restart COVAS:NEXT
3. Open the COVAS:NEXT menu → navigate to **Discordant - Discord DM Integration** settings
4. Paste your bot token into the **Bot Token** field
5. Start your COVAS chat session — the bot will connect automatically

---

## Voice Commands

### Incoming DMs

Short messages are read out immediately. Longer messages get a brief summary first — ask to hear the full thing if you want it.

```
"Read the full message"           # Hear the complete DM
"Who was that from?"              # If you missed the announcement
```

### Replying
```
"Reply: yeah I'll be on around 9"
"Reply: give me 5 minutes"
"Send a message saying I'm in the middle of a mission"
```
Replies are sent verbatim — COVAS will not paraphrase or add to your message.

### Checking Messages
```
"Check my Discord"                # Recent DMs summary
"Any Discord messages?"
"Read my messages from Jordan"    # Full thread with a specific person
"What did Sarah say?"
```

---

## Troubleshooting
**Plugin Fails to load**
- Double check the name of the folder in your addons folder. It should be "Discordant" nothing else.

**Bot doesn't connect on startup**
- Check your bot token is correctly pasted in the plugin settings (no extra spaces)
- Make sure all three Privileged Gateway Intents are enabled in the Developer Portal
- Restart COVAS:NEXT after saving settings

**Friend can't DM the bot**
- They need to be in a shared server with the bot first — invite them to your private relay server
- Once they've joined the server they can DM the bot directly from then on

**DMs aren't being announced**
- Confirm your friend is messaging the bot, not your personal Discord account
- The bot only receives messages while COVAS is running — messages sent while it's offline won't be announced retroactively, but you can ask COVAS to check recent DMs

**"Not connected to Discord"**
- Your bot token may have been reset in the Developer Portal — generate a new one and update the plugin settings
- Check COVAS:NEXT logs for connection errors

**Reply goes to the wrong person**
- Replies always go to the most recent DM received. If you've received DMs from multiple people, ask COVAS to read a specific person's messages first to confirm before replying.

---

## Files

```
Discordant/
  Discordant.py        # Main plugin
  manifest.json        # Plugin metadata
  deps/                # Bundled Python dependencies (discord.py + deps)
```

---

## Version History

**v1.0.0** — Initial release

---

## Credits

**Author**: Lag0matic  
**COVAS:NEXT**: https://ratherrude.github.io/Elite-Dangerous-AI-Integration/  
**Discord API**: discord.py library
