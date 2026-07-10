import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.litellm import LiteLLMModel

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ---------------------------------------------------------------------------
# 1. Environment + config
# ---------------------------------------------------------------------------
load_dotenv()

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]

# Google OAuth files. NOTE: the client-secrets file on disk is named
# 'credientials.json' (as downloaded), so we point at that exact name.
CREDENTIALS_FILE = "credientials.json"
TOKEN_FILE = "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


# ---------------------------------------------------------------------------
# 2. Google OAuth helper
# ---------------------------------------------------------------------------
def get_google_credentials():
    """Return valid Google OAuth credentials.

    Reads cached credentials from token.json if present, refreshes them when
    expired, and otherwise runs the interactive browser OAuth flow. The
    resulting credentials are always written back to token.json.
    """
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return creds


# ---------------------------------------------------------------------------
# 3. Tools
# ---------------------------------------------------------------------------
@tool
def check_gmail(hours_back: int = 12) -> str:
    """Fetch unread Gmail messages from the last `hours_back` hours.

    Returns the sender, subject, date, and a 200-character snippet for each
    unread email. Use this to surface what landed in the inbox overnight.
    """
    try:
        service = build("gmail", "v1", credentials=get_google_credentials())

        after = int((datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp())
        query = f"is:unread after:{after}"

        results = service.users().messages().list(
            userId="me", q=query, maxResults=25
        ).execute()
        messages = results.get("messages", [])

        if not messages:
            return f"No unread emails in the last {hours_back} hours."

        lines = [f"Unread emails (last {hours_back}h): {len(messages)}"]
        for msg in messages:
            detail = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()

            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            sender = headers.get("From", "(unknown sender)")
            subject = headers.get("Subject", "(no subject)")
            date = headers.get("Date", "(no date)")
            snippet = detail.get("snippet", "")[:200]

            lines.append(
                f"- From: {sender}\n  Subject: {subject}\n  Date: {date}\n  Snippet: {snippet}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch Gmail: {e}"


@tool
def check_calendar(hours_ahead: int = 24) -> str:
    """Fetch upcoming Google Calendar events in the next `hours_ahead` hours.

    Returns the title, start, end, location, and attendees for each event.
    Use this to report what is scheduled for the day ahead.
    """
    try:
        service = build("calendar", "v3", credentials=get_google_credentials())

        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(hours=hours_ahead)).isoformat()

        results = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=25,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = results.get("items", [])

        if not events:
            return f"No calendar events in the next {hours_ahead} hours."

        lines = [f"Upcoming events (next {hours_ahead}h): {len(events)}"]
        for event in events:
            title = event.get("summary", "(no title)")
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))
            location = event.get("location", "(no location)")
            attendees = [a.get("email", "") for a in event.get("attendees", [])]
            attendees_str = ", ".join(a for a in attendees if a) or "(none listed)"

            lines.append(
                f"- Title: {title}\n  Start: {start}\n  End: {end}\n"
                f"  Location: {location}\n  Attendees: {attendees_str}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to fetch Calendar: {e}"


@tool
def check_slack(hours_back: int = 12, max_channels: int = 5) -> str:
    """Fetch recent Slack messages from the most recently active channels.

    Looks at up to `max_channels` (default 5) of the most recently active
    channels the bot can see, and returns the channel name plus up to 5 recent
    messages (from the last `hours_back` hours) per channel.
    """
    try:
        client = WebClient(token=SLACK_BOT_TOKEN)
        oldest = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp()

        convos = client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
            limit=200,
        )
        channels = convos.get("channels", [])

        # Most recently active channels first (falls back to 0 if unavailable).
        channels.sort(key=lambda c: float(c.get("updated", 0)), reverse=True)
        channels = channels[:max_channels]

        if not channels:
            return "No accessible Slack channels found."

        lines = [f"Slack (last {hours_back}h, top {len(channels)} channels):"]
        for ch in channels:
            name = ch.get("name", ch.get("id", "unknown"))
            try:
                history = client.conversations_history(
                    channel=ch["id"], oldest=str(oldest), limit=5
                )
                msgs = history.get("messages", [])
            except SlackApiError as e:
                # Bot likely isn't a member of this channel.
                lines.append(f"#{name}: (unable to read — {e.response.get('error', 'error')})")
                continue

            if not msgs:
                lines.append(f"#{name}: (no recent messages)")
                continue

            lines.append(f"#{name}:")
            for m in msgs[:5]:
                text = (m.get("text", "") or "").replace("\n", " ")[:200]
                user = m.get("user") or m.get("bot_id") or "unknown"
                lines.append(f"  - {user}: {text}")
        return "\n".join(lines)
    except SlackApiError as e:
        return f"Failed to fetch Slack: {e.response.get('error', e)}"
    except Exception as e:
        return f"Failed to fetch Slack: {e}"


# ---------------------------------------------------------------------------
# 4. Agent
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a Morning Briefing Agent.

When asked for a briefing, you MUST call all three tools in this exact order,
every time, before answering:
  1. check_gmail
  2. check_calendar
  3. check_slack

After gathering the data from all three tools, synthesize a single concise
morning briefing. Use these EXACT section headers, in this order:

URGENT
UPCOMING EVENTS
SLACK HIGHLIGHTS
OTHER EMAILS
SUGGESTED ACTIONS

Guidelines:
- URGENT: anything time-sensitive or needing a fast response (deadlines,
  meetings starting soon, direct asks).
- UPCOMING EVENTS: today's calendar, in chronological order.
- SLACK HIGHLIGHTS: notable channel activity and messages worth attention.
- OTHER EMAILS: unread mail that is not urgent.
- SUGGESTED ACTIONS: a short bulleted list of concrete next steps.
If a section has nothing to report, still include the header and write "Nothing to report."
Keep it skimmable and to the point.
"""

model = LiteLLMModel(
    client_args={"api_key": OPENROUTER_API_KEY},
    model_id="openrouter/meta-llama/llama-3.3-70b-instruct:free",
    params={"max_tokens": 4096},
)


def run():
    """Create the briefing agent and generate today's morning briefing."""
    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[check_gmail, check_calendar, check_slack],
    )
    return agent("What did I miss? Give me my morning briefing.")


if __name__ == "__main__":
    print("Generating your morning briefing...\n")
    result = run()
    print("\n--- Morning Briefing ---")
    print(result)
