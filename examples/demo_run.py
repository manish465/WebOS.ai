"""
Example demonstration script showing how WebOS.ai is used by external scripts.
"""

import asyncio
from src import WebRuntime, BrowserAction


async def main():
    print("Initializing WebOS.ai Runtime...")
    runtime = WebRuntime()

    try:
        # Note: Requires Chrome running with --remote-debugging-port=9222
        print("Connecting to Chrome on port 9222...")
        await runtime.connect(port=9222)

        print("Navigating to test site...")
        await runtime.navigate("https://news.ycombinator.com")

        print("Observing interactive candidates...")
        candidates = await runtime.observe(max_candidates=10)
        for c in candidates:
            print(f"  [#{c.candidate_id}] {c.role.upper()}: '{c.name}'")

        # Ground an intent
        target = await runtime.ground_intent("search", candidates)
        if target:
            print(f"Grounded target: #{target.candidate_id} '{target.name}'")
            action = BrowserAction(action_type="click", target_candidate_id=target.candidate_id)
            result = await runtime.execute_step("Click search", action, candidate=target)
            print(f"Execution result: {result.message}")

    except ConnectionError:
        print("Chrome is not running on port 9222. (Run: chrome --remote-debugging-port=9222)")
    finally:
        await runtime.close()
        print("Runtime shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
