# Morning Briefing Agent

An AI agent that answers "what did I miss?" every morning. It reads your **unread Gmail**, **today's Google Calendar**, and **recent Slack messages**, then writes one skimmable briefing:

```
URGENT
UPCOMING EVENTS
SLACK HIGHLIGHTS
OTHER EMAILS
SUGGESTED ACTIONS
```

Built in July 2026 with [Strands Agents](https://strandsagents.com) and a free Llama 3.3 70B model through [OpenRouter](https://openrouter.ai).

## How it works

The agent has three tools: `check_gmail`, `check_calendar`, and `check_slack`. The system prompt tells it to call all three, then write the briefing under fixed section headers, with "Nothing to report." for empty sections, so the format is the same every day.

## Safety by design

- **Read-only.** Google access uses the `gmail.readonly` and `calendar.readonly` scopes, and the Slack tools only list and read channels. Even a confused model can't send, delete, or post anything.
- **Treats incoming text as data.** Emails and Slack messages are written by other people, so the prompt tells the model never to follow instructions inside them and to flag phishing as urgent. The demo inbox includes a phishing email that tries exactly this.
- **Secrets stay local.** `.env`, `token.json`, and the Google OAuth client file are all git-ignored, under both spellings of the client file's name, along with saved briefings.

## Try it with sample data (no Google or Slack needed)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add a free OPENROUTER_API_KEY
python agent.py --demo
```

## Use it with your own accounts

1. **OpenRouter:** get a free key at https://openrouter.ai/keys and put it in `.env`.
2. **Google:** in Google Cloud Console, enable the Gmail and Calendar APIs, create an OAuth client (desktop app), and save the file here as `credentials.json`. The first run opens a browser to sign in; after that `token.json` keeps you signed in.
3. **Slack:** create a Slack app with the `channels:read`, `channels:history`, `groups:read`, and `groups:history` scopes, install it, invite it to the channels you want covered, and put its `xoxb-` token in `.env` as `SLACK_BOT_TOKEN`.

```bash
python agent.py           # print today's briefing
python agent.py --save    # also save it to briefings/YYYY-MM-DD.md
```

Free models are often busy. When the model is rate-limited, the agent retries automatically with growing waits (15s, 30s, 45s, then 60s).

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

15 tests, using fake Google, Slack, and model clients, so no accounts or keys are needed. They cover the tools' formatting and error handling, retries, setup messages, the prompt's sections and injection guard, and that every secret file is git-ignored.
