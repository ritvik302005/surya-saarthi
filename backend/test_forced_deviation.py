from dotenv import load_dotenv
load_dotenv()

from graph import graph

# Live script (one real Groq call). Deliberately start with a wildly wrong "previous
# forecast", so sensing detects a forecast miss before the decision and the agent is
# told to plan this hour cautiously. The graph no longer loops: the hour is decided
# and applied exactly once.
result = graph.invoke({"forecast_solar_kw": 99.0})

print("Final decision:", result["decision"])
print("Reasoning:", result["reasoning"])
print("Forecast missed this cycle:", result["report"]["replanned_this_cycle"],
      f"({result['report']['forecast_miss_kw']} kW)")
print("Report:", result["report"])
