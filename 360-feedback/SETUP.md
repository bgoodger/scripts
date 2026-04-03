# 360 Feedback Bot — Setup Guide

## 1. Create the Slack App

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Name it "360 Feedback", pick your workspace

### OAuth & Permissions — Bot Token Scopes

Add these under **OAuth & Permissions → Scopes → Bot Token Scopes**:

| Scope | Why |
|---|---|
| `chat:write` | Send DM nudges and confirmations |
| `commands` | Register slash commands |
| `users:read` | Look up user display names |
| `app_mentions:read` | Track @mentions for interaction scoring |
| `channels:history` | Read messages for @mention tracking |
| `groups:history` | Same for private channels (optional) |
| `im:write` | Open DM channels for nudges |

### Event Subscriptions

Enable **Socket Mode** (under *Socket Mode* in the sidebar) and create an **App-Level Token** with the `connections:write` scope. Copy the `xapp-...` token.

Then enable **Event Subscriptions** and subscribe to:
- `app_home_opened`
- `app_mention`
- `message.channels`

### Slash Commands

Create two slash commands (under *Slash Commands*):

| Command | Description |
|---|---|
| `/feedback` | Give feedback to a colleague |
| `/feedback-admin` | Admin: set managers, trigger nudge |

### App Home

Under **App Home**, enable the **Home Tab**.

### Install the App

Install to your workspace. Copy the `xoxb-...` **Bot User OAuth Token**.

---

## 2. Configure environment

```bash
cd 360-feedback
cp .env.example .env
# Edit .env and fill in SLACK_BOT_TOKEN, SLACK_APP_TOKEN, ANTHROPIC_API_KEY
```

## 3. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Run the bot

```bash
python app.py
```

The bot connects via Socket Mode — no public URL or ngrok needed.

---

## Usage

| Action | How |
|---|---|
| Give feedback | `/feedback` or `/feedback @person` or the button in your Home tab |
| View your feedback | Open the **360 Feedback** app in Slack sidebar → Home tab |
| Write self-reflection | Home tab → *Edit reflection* button |
| Set goals | Home tab → *Add goal* button |
| Refresh AI summary | Home tab → *Refresh summary* button |
| Set manager relationships | `/feedback-admin set-manager @person @manager` |
| Trigger nudges manually | `/feedback-admin nudge-now` |

Weekly nudges run every Monday at 09:00 by default.  
Override with `NUDGE_DAY` (0=Mon…6=Sun) and `NUDGE_TIME` (HH:MM) in `.env`.

---

## Data & Privacy

- Feedback is stored locally in `360_feedback.db` (SQLite)
- Recipients see feedback as **anonymous** — giver identity is never shown in their view
- Manager attribution is stored in the DB and visible only to future manager-view features
- AI summaries are generated via the Claude API (Anthropic) and cached locally
