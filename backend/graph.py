from langgraph.graph import StateGraph, END
from state import GridState
from nodes.sensing import read_and_forecast_node
from nodes.decide import decide_node
from nodes.safety import enforce_safety_node
from nodes.apply import apply_decision_node
from nodes.report import generate_report_node

# One pass per simulated hour. The forecast check lives in "sense" (before the
# decision), so the hour is decided and applied exactly once. "allocate" asks the
# session's controller (optimizer, AI or fixed rule); safety checks all of them alike.
builder = StateGraph(GridState)

builder.add_node("sense", read_and_forecast_node)
builder.add_node("allocate", decide_node)
builder.add_node("safety", enforce_safety_node)
builder.add_node("apply", apply_decision_node)
builder.add_node("report", generate_report_node)

builder.set_entry_point("sense")
builder.add_edge("sense", "allocate")
builder.add_edge("allocate", "safety")
builder.add_edge("safety", "apply")
builder.add_edge("apply", "report")
builder.add_edge("report", END)

graph = builder.compile()
