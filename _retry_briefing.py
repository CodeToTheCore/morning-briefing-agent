"""Temporary helper: retry the morning briefing until the free tier lets us through."""
import time
import agent
from litellm.exceptions import RateLimitError

DEADLINE_ATTEMPTS = 120  # ~ up to ~30 min at 15s spacing
for attempt in range(1, DEADLINE_ATTEMPTS + 1):
    try:
        print(f"[attempt {attempt}] calling agent...", flush=True)
        result = agent.run()
        with open("briefing_output.txt", "w") as f:
            f.write(str(result))
        print("\n=== SUCCESS — saved to briefing_output.txt ===", flush=True)
        print(result, flush=True)
        break
    except RateLimitError:
        print(f"  attempt {attempt}: rate-limited, waiting 15s...", flush=True)
        time.sleep(15)
    except Exception as e:
        print(f"  attempt {attempt}: non-rate-limit error: {type(e).__name__}: {e}", flush=True)
        break
else:
    print("STILL_RATE_LIMITED_AFTER_ALL_RETRIES", flush=True)
