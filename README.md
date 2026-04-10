# 360 Feedback Bot for Slack

A lightweight, self-hosted Slack bot for running continuous 360 performance feedback with your team and cross-functional stakeholders throughout the quarter.

Feedback is collected on an ongoing basis (not just at review time), surfaced through a personal Slack Home tab dashboard, and summarised using AI to highlight themes, trends, and behavioural patterns.

## Features

- **`/feedback @person`** — submit structured feedback via a Slack modal at any time
- **Private by default** — only the recipient sees their feedback; it is not visible to anyone else
- **Slack Home tab dashboard** — personal view with AI-generated theme summary, recent feedback, self-reflection editor, and quarterly goals
- **Weekly nudges** — every Monday the bot DMs you about colleagues you interacted with, prompting you to leave feedback
- **AI-powered summaries** — Claude extracts recurring themes, strengths, and growth areas from your feedback
- **Internal-only** — all processing is restricted to your workspace; external Slack Connect users and shared channels are blocked

## How it works

```
Colleague types /feedback → selects you → fills in modal
        ↓
Stored anonymously in local SQLite DB
        ↓
You open the app's Home tab in Slack
        ↓
Claude summarises themes from all your feedback this quarter
        ↓
You write a self-reflection and set goals for the quarter
```

Weekly on Monday morning, the bot checks who you've @mentioned (or been @mentioned with) in channels and sends a DM nudge to prompt feedback.

## Setup

### 1. Create the Slack App

Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From a manifest** → select your workspace → paste the manifest below:

```yaml
display_information:
  name: 360 Feedback
  description: Continuous 360 performance feedback for your team
  background_color: "#1a1a2e"
features:
  app_home:
    home_tab_enabled: true
    messages_tab_enabled: false
  slash_commands:
    - command: /feedback
      description: Give feedback to a colleague
      usage_hint: "@person"
      should_escape: false
    - command: /feedback-admin
      description: Admin commands (set managers, trigger nudge)
      usage_hint: "set-manager @user @manager"
      should_escape: false
  bot_user:
    display_name: 360 Feedback
    always_online: true
oauth_config:
  scopes:
    bot:
      - chat:write
      - commands
      - users:read
      - app_mentions:read
      - channels:history
      - groups:history
      - im:write
      - im:history
settings:
  event_subscriptions:
    bot_events:
      - app_home_opened
      - app_mention
      - message.channels
      - message.im
  interactivity:
    is_enabled: true
  socket_mode_enabled: true
  token_rotation_enabled: false
```

### 2. Enable Socket Mode and get your App Token

1. In the left sidebar → **Socket Mode** → toggle **Enable Socket Mode** ON
2. Create an App-Level Token (name it anything, scope: `connections:write`)
3. Copy the `xapp-...` token — this is your `SLACK_APP_TOKEN`

### 3. Install to workspace and get your Bot Token

1. **OAuth & Permissions** → **Install to Workspace** → **Allow**
2. Copy the `xoxb-...` token — this is your `SLACK_BOT_TOKEN`

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env with your three credentials
```

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
ANTHROPIC_API_KEY=sk-ant-...
```

Get an Anthropic API key at [console.anthropic.com](https://console.anthropic.com).

### 5. Install and run

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

The bot connects via Socket Mode — no public URL, no hosting, no ngrok needed. Just run it locally or on any machine with internet access.

## Usage

| Action | How |
|---|---|
| Give feedback | `/feedback` or `/feedback @person` or the button on your Home tab |
| View your feedback and themes | Open the **360 Feedback** app in the Slack sidebar → Home tab |
| Write your self-reflection | Home tab → *Edit reflection* |
| Set quarterly goals | Home tab → *Add goal* |
| Refresh AI theme summary | Home tab → *Refresh summary* |
| Set manager relationships | `/feedback-admin set-manager @person @manager` |
| Trigger nudge run manually | `/feedback-admin nudge-now` |

### Nudge schedule

Weekly nudges run every Monday at 09:00 by default. Override with environment variables:

```env
NUDGE_DAY=0    # 0=Monday ... 6=Sunday
NUDGE_TIME=09:00
```

### Feedback categories

Each piece of feedback is tagged with one or more categories:

- Collaboration
- Communication
- Delivery & Execution
- Technical Skills
- Leadership & Influence
- Adaptability

## Privacy model

| Who | What they can see |
|---|---|
| **Recipient** | Full feedback content, categories, and who gave it |
| **Giver** | Confirmation that their feedback was submitted |
| **Anyone else** | Nothing — feedback is private to the recipient only |

All data is stored locally in a SQLite file (`360_feedback.db`). Nothing is sent to external services except feedback text to the Anthropic API for summarisation.

AI summaries are cached locally and only regenerated when new feedback arrives or the user explicitly refreshes.

## Configuration reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | Yes | — | `xoxb-...` bot token |
| `SLACK_APP_TOKEN` | Yes | — | `xapp-...` socket mode token |
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key |
| `DB_PATH` | No | `./360_feedback.db` | SQLite database location |
| `NUDGE_DAY` | No | `0` (Monday) | Day to send weekly nudges (0=Mon, 6=Sun) |
| `NUDGE_TIME` | No | `09:00` | Time to send weekly nudges (24h) |

## Project structure

```
app.py           # Slack Bolt app — all event handlers and slash commands
db.py            # SQLite database layer
ai.py            # Claude API integration for theme summarisation
home_tab.py      # Slack Home tab Block Kit builder
modals.py        # Feedback, reflection, and goal modal definitions
weekly_nudge.py  # Background scheduler for Monday nudge DMs
```

## License

MIT
