import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.litellm import LiteLLMModel
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 1. Initialize environment config
load_dotenv()

# Google API read-only scope configuration
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/gmail.readonly',
]

def get_calendar_service():
    """Manages the automatic Google OAuth browser window login."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Matches the actual filename on disk: credientials.json
            flow = InstalledAppFlow.from_client_secrets_file('credientials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('calendar', 'v3', credentials=creds)

# 2. Turn a standard Python function into a tool capability using the decorator
@tool
def fetch_today_calendar_events() -> str:
    """
    Fetches scheduled meetings and calendar events for the current day.
    Use this tool whenever the user asks about their schedule or briefing.
    """
    try:
        service = get_calendar_service()
        now = datetime.now(timezone.utc).isoformat()
        
        events_result = service.events().list(
            calendarId='primary', 
            timeMin=now,
            maxResults=5, 
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        if not events:
            return "Your calendar is completely clear for today."
            
        summary = "Today's Schedule:\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary += f"- {event['summary']} (Starts: {start})\n"
        return summary
    except Exception as e:
        return f"Failed to retrieve calendar events: {str(e)}"

# 3. Build your LiteLLM instance matching your assignment specifications
model = LiteLLMModel(
    client_args={
        "api_key": os.environ["OPENROUTER_API_KEY"],
    },
    model_id="openrouter/openrouter/free",
    params={"max_tokens": 1024},
)

# 4. Bind the tool function array directly to the Agent initialization parameter
agent = Agent(
    model=model, 
    tools=[fetch_today_calendar_events]
)

if __name__ == "__main__":
    print("Starting Morning Briefing Agent...")
    print("Asking the agent to review your day...")
    
    # Trigger the agent loop
    result = agent("Look at my calendar and tell me what my schedule looks like today.")
    print("\n--- Final Briefing Summary ---")
    print(result)



# import os
# from dotenv import load_dotenv
# from strands import Agent
# from strands.models.litellm import LiteLLMModel

# load_dotenv()

# # Let LiteLLM look up OpenRouter natively using the prefix
# model = LiteLLMModel(
#     client_args={
#         "api_key": os.environ["OPENROUTER_API_KEY"],
#     },
#     model_id="openrouter/openrouter/free",  # Direct target to the free models router
#     params={"max_tokens": 1024},
# )

# agent = Agent(model=model, tools=[])

# result = agent("Say hello and tell me what model you are in one sentence.")
# print(result)

# import os

# from dotenv import load_dotenv
# from strands import Agent
# from strands.models.litellm import LiteLLMModel

# load_dotenv()

# model = LiteLLMModel(
#     client_args={
#         "api_key": os.environ["OPENROUTER_API_KEY"],
#         "base_url": "https://openrouter.ai/api/v1",
#     },
#     model_id="openrouter/openrouter/free",
#     params={"max_tokens": 1024},
# )

# agent = Agent(model=model, tools=[])

# result = agent("Say hello and tell me what model you are in one sentence.")
# print(result)
# import os
# from dotenv import load_dotenv
# from strands import Agent

# # 1. Force load the .env file containing your keys
# load_dotenv()

# # Double check that your key is actually loading from your hidden .env file
# if not os.getenv("OPENROUTER_API_KEY"):
#     raise ValueError("ERROR: OPENROUTER_API_KEY is missing from your .env file!")

# # 2. Tell LiteLLM backend to look at OpenRouter's cloud routing network
# os.environ["OPENROUTER_API_BASE"] = "https://openrouter.ai"

# # 3. Correctly initialize the Strands Agent instance
# # We explicitly set the system_prompt context parameters
# agent = Agent(
#     model="openrouter/openai/gpt-4o",
#     system_prompt="You are a personal assistant. Keep your responses short and punchy."
# )

# # 4. Execute the runtime loop
# if __name__ == "__main__":
#     print("Sending live request to OpenRouter network...")
    
#     # We pass the instruction message directly as an argument call
#     response = agent("What is the capital of France?")
    
#     print("\n--- Live AI Response ---")
#     print(response)
    