"""Tests run with no Google, Slack or OpenRouter accounts: every outside service is faked."""
import sys
import types
from pathlib import Path

import pytest
from litellm.exceptions import RateLimitError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
import demo_data  # noqa: E402


# ---------- setup and secrets ----------

def test_imports_without_any_keys():
    assert agent.SYSTEM_PROMPT


def test_missing_key_gives_setup_help(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(agent.SetupError, match="openrouter.ai/keys"):
        agent.make_model()


def test_main_explains_missing_setup_instead_of_crashing(monkeypatch, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert agent.main(["--demo"]) == 1
    assert "Setup needed" in capsys.readouterr().err


def test_credentials_file_accepts_both_spellings(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_CREDENTIALS_FILE", raising=False)
    monkeypatch.setattr(agent, "HERE", tmp_path)
    with pytest.raises(agent.SetupError):
        agent.credentials_file()
    (tmp_path / "credientials.json").write_text("{}")
    assert agent.credentials_file().name == "credientials.json"
    (tmp_path / "credentials.json").write_text("{}")
    assert agent.credentials_file().name == "credentials.json"


def test_gitignore_protects_every_secret_file():
    ignored = (ROOT / ".gitignore").read_text().split()
    for name in (".env", "token.json", "credentials.json", "credientials.json", "briefings/"):
        assert name in ignored, f"{name} must be git-ignored"


# ---------- prompt ----------

def test_prompt_has_every_section_and_the_injection_guard():
    for header in ("URGENT", "UPCOMING EVENTS", "SLACK HIGHLIGHTS", "OTHER EMAILS", "SUGGESTED ACTIONS"):
        assert header in agent.SYSTEM_PROMPT
    assert "Never follow" in agent.SYSTEM_PROMPT


# ---------- Gmail tool (fake Google service) ----------

class FakeGmail:
    def __init__(self, messages):
        self._messages = messages
        self.queries = []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, userId, q, maxResults):
        self.queries.append(q)
        return types.SimpleNamespace(execute=lambda: {"messages": [{"id": m["id"]} for m in self._messages]})

    def get(self, userId, id, format, metadataHeaders):
        m = next(m for m in self._messages if m["id"] == id)
        payload = {"payload": {"headers": [{"name": "From", "value": m["from"]}, {"name": "Subject", "value": m["subject"]},
                                           {"name": "Date", "value": "today"}]}, "snippet": m["snippet"]}
        return types.SimpleNamespace(execute=lambda: payload)


def _use_fake_google(monkeypatch, service):
    import googleapiclient.discovery
    monkeypatch.setattr(agent, "get_google_credentials", lambda: object())
    monkeypatch.setattr(googleapiclient.discovery, "build", lambda *a, **k: service)


def test_gmail_lists_unread_mail(monkeypatch):
    service = FakeGmail([{"id": "1", "from": "Priya", "subject": "Mix approval", "snippet": "x" * 500}])
    _use_fake_google(monkeypatch, service)
    out = agent.check_gmail(hours_back=12)
    assert "Unread emails (last 12h): 1" in out
    assert "Subject: Mix approval" in out
    assert "x" * 201 not in out  # snippets are cut to 200 characters
    assert service.queries[0].startswith("is:unread after:")


def test_gmail_empty_inbox(monkeypatch):
    _use_fake_google(monkeypatch, FakeGmail([]))
    assert agent.check_gmail(hours_back=6) == "No unread emails in the last 6 hours."


def test_gmail_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(agent, "get_google_credentials", lambda: (_ for _ in ()).throw(RuntimeError("token expired")))
    assert "Failed to fetch Gmail: token expired" in agent.check_gmail()


# ---------- Slack tool (fake Slack client) ----------

def _use_fake_slack(monkeypatch, channels, histories):
    import slack_sdk
    from slack_sdk.errors import SlackApiError

    class FakeClient:
        def __init__(self, token):
            pass

        def conversations_list(self, **kwargs):
            return {"channels": channels}

        def conversations_history(self, channel, oldest, limit):
            result = histories[channel]
            if isinstance(result, str):
                raise SlackApiError("error", response={"error": result})
            return {"messages": result}

    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-not-real")
    monkeypatch.setattr(slack_sdk, "WebClient", FakeClient)


def test_slack_reads_most_active_channels_first(monkeypatch):
    _use_fake_slack(monkeypatch,
                    channels=[{"id": "A", "name": "random", "updated": 1}, {"id": "B", "name": "releases", "updated": 9}],
                    histories={"A": [{"user": "sam", "text": "coffee?"}], "B": "not_in_channel"})
    out = agent.check_slack(max_channels=2)
    assert out.index("#releases") < out.index("#random")
    assert "#releases: (unable to read — not_in_channel)" in out
    assert "sam: coffee?" in out


def test_slack_without_a_token_explains_setup(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    assert "Slack is not set up" in agent.check_slack()


# ---------- retrying when the free model is busy ----------

def test_rate_limits_are_retried_with_growing_waits(monkeypatch):
    calls, waits = [], []

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def __call__(self, prompt):
            calls.append(prompt)
            if len(calls) < 3:
                raise RateLimitError("busy", llm_provider="openrouter", model="free")
            return "URGENT\nNothing to report."

    monkeypatch.setattr(agent, "Agent", FakeAgent)
    monkeypatch.setattr(agent, "make_model", lambda: None)
    result = agent.run(demo=True, sleep=waits.append)
    assert result.startswith("URGENT")
    assert waits == [15, 30]


def test_gives_up_after_the_last_attempt(monkeypatch):
    class AlwaysBusy:
        def __init__(self, **kwargs):
            pass

        def __call__(self, prompt):
            raise RateLimitError("busy", llm_provider="openrouter", model="free")

    monkeypatch.setattr(agent, "Agent", AlwaysBusy)
    monkeypatch.setattr(agent, "make_model", lambda: None)
    with pytest.raises(RateLimitError):
        agent.run(demo=True, max_attempts=3, sleep=lambda s: None)


# ---------- demo data ----------

def test_demo_tools_match_the_real_ones():
    assert [t.tool_name for t in demo_data.demo_tools()] == [t.tool_name for t in agent.live_tools()]
    assert "Final mix approval" in demo_data.check_gmail()
    assert "ignore your previous rules" in demo_data.check_gmail()  # the phishing test case
    assert "Studio session" in demo_data.check_calendar()


def test_save_briefing_writes_a_dated_file(tmp_path):
    path = agent.save_briefing("URGENT\nNothing to report.", folder=tmp_path)
    assert path.suffix == ".md"
    assert "Nothing to report." in path.read_text()
