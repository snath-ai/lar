"""
Failure Mode 4: Recursion / Step-Limit Behaviour on Long-Running Processes
============================================================================
Both sides of this test actually execute. Nothing here is assumed -- and the
real result corrects two wrong assumptions that were made before running it.

SCENARIO: a workflow that legitimately needs to run 60 sequential steps
(e.g. a 60-stage document pipeline, a 60-node organisational hierarchy walk).

CORRECTION #1 -- LangGraph does NOT crash by default. An earlier version of
this comparison (since deleted) claimed LangGraph's default `recursion_limit`
of 25 would crash a 60-step graph. Verified directly: 25, 26, 100, and 500
step linear graphs all complete fine with zero explicit config.
`recursion_limit` is a real, opt-in LangGraph safety feature -- it is not
active by default. That original claim only "worked" because the script
explicitly forced `config={"recursion_limit": 25}` to manufacture a crash.

CORRECTION #2 -- Lár's own `max_node_fatigue` (default 20) DID have a real
default-active false positive, found by actually running this exact test: it
identified nodes by `_node_id` or, absent that, by *class name*. 60 distinct
`AddValueNode` instances in a legitimate linear pipeline all shared the name
"AddValueNode" and the breaker fired at the 21st, even though nothing was
looping. Fixed in v2.2.3: fatigue is now tracked per node *instance* by
default (id-based, labelled `ClassName#N` for audit-log readability), so
distinct instances of the same reusable node type no longer collide, while a
genuine cycle -- the same node object actually revisited -- is still caught
(verified separately: a self-returning node trips the breaker at visit 21,
labelled consistently across all 21 visits since it's really the same
instance every time).

The honest takeaway is not "Lár wins, LangGraph loses" -- it's that neither
framework's real behaviour matched the original assumption, and only running
both for real revealed that.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from lar import GraphExecutor, AddValueNode

STEPS = 60

print("=" * 70)
print(f"  Building a {STEPS}-step linear pipeline, running it for real on both sides")
print("=" * 70)

# --- Side 1: LangGraph, default recursion_limit ---
print("\n--- LangGraph (default recursion_limit=25) ---")
from langgraph.graph import StateGraph, END
from typing import TypedDict


class S(TypedDict):
    count: int


builder = StateGraph(S)


def make_node(i):
    def fn(state: S):
        return {"count": state["count"] + 1}
    return fn


names = [f"step_{i}" for i in range(STEPS)]
for n in names:
    builder.add_node(n, make_node(n))
for a, b in zip(names, names[1:]):
    builder.add_edge(a, b)
builder.set_entry_point(names[0])
builder.set_finish_point(names[-1])
app = builder.compile()

try:
    result = app.invoke({"count": 0})
    print(f"  Result: completed, count={result['count']}")
except Exception as e:
    print(f"  CRASHED: {type(e).__name__}: {e}")

# --- Side 2: Lár, default max_node_fatigue ---
print("\n--- Lár (default max_node_fatigue=20, but this is per-node, not per-step) ---")

# Build 60 distinct AddValueNode instances chained linearly -- same shape as the LangGraph side.
lar_nodes = []
prev = None
for i in range(STEPS):
    n = AddValueNode(key=f"step_{i}", value=i, next_node=None)
    if prev is not None:
        prev.next_node = n
    lar_nodes.append(n)
    prev = n

executor = GraphExecutor(log_dir="/tmp/lar_failure_mode_4_logs")
step_count = 0
try:
    for step in executor.run_step_by_step(lar_nodes[0], {}):
        step_count += 1
    print(f"  Result: completed, {step_count} steps executed, no ceiling hit")
except Exception as e:
    print(f"  CRASHED: {type(e).__name__}: {e}")

print("\n" + "=" * 70)
print("  DONE — both sides actually ran. See output above for the real result.")
print("=" * 70)
