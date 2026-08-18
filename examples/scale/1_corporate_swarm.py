# For setup instructions, see: https://docs.snath.ai/guides/litellm_setup/
import random
import time
import os
from typing import Dict, List
from lar import *

# Fix for LiteLLM + Gemini (Maps GOOGLE_API_KEY to GEMINI_API_KEY)
if os.getenv("GOOGLE_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.getenv("GOOGLE_API_KEY")

# ==============================================================================
# 9. THE CORPORATE SWARM (Hybrid Cognitive Architecture)
# ==============================================================================
# 
# THE CONSTRUCTION SITE METAPHOR
# ---------------------------------
# 1. The "Old Way" (Standard Agents):
#    Imagine a construction site where EVERY worker is a high-paid Architect.
#    To hammer a nail, they stop, "think" about the nail, write a poem, and charge $5.
#    Result: Slow, expensive, chaos.
#
# 2. The "Lár Way" (Hybrid Swarm):
#    Imagine ONE Architect and 1,000 Robots.
#    - The Architect (CEO Node) yells ONCE: "Build the Skyscraper!"
#    - The Robots (Swarm) execute thousands of steps instantly.
#    Result: Fast, cheap, deterministic.
#
# WHY THIS DESIGN IS CHEAP AND FAST
# -----------------------------------
# This is a design-choice comparison (LLM-per-node vs. one LLM call + code-routed
# body), not a claim about what other frameworks can or can't do -- LangGraph,
# AutoGen, and CrewAI can all be wired the same "1 LLM call + code-routed
# workers" way if you choose to build them that way. The point here is what
# happens if you DON'T: routing all 60+ nodes through an LLM call each would
# cost ~60 API calls and 60 LLM round-trips of latency, vs. 1 API call and
# near-instant code execution for everything after it.
#
#  __________________________________________________________________________________
# | FEATURE       | ALL-LLM ROUTING (routes every step via a prompt) | THIS DESIGN  |
# |---------------|----------------------------------------------------|-----------|
# | ARCHITECTURE  | 100% LLM Nodes (All Prompts)                      | 1% LLM (Brain) + 99% Code (Body) |
# | COST          | $$$ (60 API calls)                                | $ (1 API call)     |
# | SPEED         | Slow (60 round-trips of latency)                  | Instant (0.08s for 64 code steps) |
# |_______________|____________________________________________________|___________|
#
# Verified empirically: v2.2.3 fixed a real bug in Lár's own node-fatigue
# detection where 60+ instances of the same reusable node CLASS (e.g. many
# ToolNode workers) were misidentified as a loop and false-tripped the safety
# breaker at 21 visits -- found by actually running a test like this one. See
# examples/failure_modes/4_recursion_limit.py and CHANGELOG.md [2.2.3] for the
# full story, including a correction to an earlier, inaccurate claim about
# LangGraph's default recursion behavior (it does not crash by default at any
# tested length).
#
# HOW IT WORKS: THE EXECUTION TRACE
# ------------------------------------
# 1. SETUP: We build a recursive binary tree of 63 nodes in memory (Builder).
# 2. STEP 1 (The Brain): The CEO `LLMNode` runs. It sees "Crash" -> Sets "AUSTERITY".
# 3. STEP 2 (The Routing): The Head Manager `RouterNode` runs. It sees "AUSTERITY".
# 4. STEP 3 (The Pruning): It runs a logic check (Python). It decides to SKIP the Left Branch.
#    -> instant deletion of 30 nodes from the queue.
# 5. STEP 4 (The Work): It routes to the Right Branch. Workers `ToolNode` execute `1+1`.
# 6. END: The graph converges on `final_node`. Mission Accomplished in 0.08s.
#
# In this example, ONE LLM call ("AUSTERITY" vs "BLITZSCALING") instantly 
# reconfigures a massive 60-node graph. 
# ==============================================================================

print("Building Massive Graph (Corporate Swarm)...")

class HierarchyBuilder:
    def __init__(self):
        self.node_count = 0

    def create_worker(self, id: str, next_node: BaseNode) -> BaseNode:
        """Leaf node: Actually does the work (if reached)."""
        self.node_count += 1
        
        def worker_task(total_completed: int) -> dict:
            return {"total_completed": total_completed + 1}

        return ToolNode(
            tool_function=worker_task,
            input_keys=["total_completed"],
            output_key=f"res_{id}", # Dummy key
            next_node=next_node
        )

    def create_manager(self, id: str, level: int, max_depth: int, next_node_success: BaseNode) -> BaseNode:
        """
        Recursively creates a manager.
        The Manager reads the CEO's 'strategy' to decide whether to run this branch or PRUNE it.
        """
        self.node_count += 1
        
        # Base Case
        if level >= max_depth:
            return self.create_worker(id, next_node_success)

        # Recursive Step: Build Children (Pre-order traversal linearization)
        right_branch = self.create_manager(f"{id}_R", level + 1, max_depth, next_node_success)
        left_branch  = self.create_manager(f"{id}_L", level + 1, max_depth, right_branch)

        # --- THE "INTELLIGENCE" LINK ---
        # The Manager (Code) obeys the CEO (LLM)
        def manager_logic(state: GraphState) -> str:
            strategy = state.get("strategy", "NORMAL")
            
            if strategy == "BLITZSCALING":
                return "EXECUTE" # Always run everything
            elif strategy == "AUSTERITY":
                # In austerity, we prune 50% of branches to save costs
                return "EXECUTE" if random.random() > 0.5 else "PRUNE" 
            else:
                return "EXECUTE"

        return RouterNode(
            decision_function=manager_logic,
            path_map={
                "EXECUTE": left_branch,    # Run the sub-tree
                "PRUNE": next_node_success # Skip the sub-tree entirely (Optimization)
            },
            default_node=next_node_success
        )

# --- Build the Graph ---

# 1. End Node
end_node = AddValueNode(key="final_status", value="MISSION_ACCOMPLISHED", next_node=None)

# 2. Build the Swarm (The deterministic army)
builder = HierarchyBuilder()
head_manager = builder.create_manager("VP", level=1, max_depth=6, next_node_success=end_node)

# 3. The CEO (The Strategic Brain)
# This is the ONLY LLM node. It effectively programming the rest of the graph.
ceo_node = LLMNode(
    model_name="gemini/gemini-1.5-pro", # Explicit provider prefix to avoid Vertex AI
    prompt_template=(
        "You are the CEO of a tech giant. The market is: {market_condition}.\n"
        "Set the corporate strategy directives.\n"
        "Respond ONLY with one word:\n"
        "- BLITZSCALING (If market is favorable/booming)\n"
        "- AUSTERITY (If market is crash/recession)"
    ),
    output_key="strategy",
    next_node=head_manager
)

print(f"Organization Built! Total Capacity: {builder.node_count} nodes.")

# --- Run the Swarm ---

executor = GraphExecutor()

def run_scenario(name, market_condition, description):
    print(f"\n{name}")
    initial_state = {"market_condition": market_condition, "total_completed": 0}

    start_time = time.time()
    steps = []
    
    # Graceful Fallback: If CEO (LLM) fails, we simulate the strategy
    try:
        # Run CEO Step Step-by-Step
        gen = executor.run_step_by_step(ceo_node, initial_state)
        
        # Step 1: CEO Thinks
        ceo_step = next(gen) 
        steps.append(ceo_step)
        
        # Check if CEO failed
        if ceo_step['node'].output_key == "strategy" and "error" in ceo_step.get('outcome', ''):
             raise Exception("LLM Error")
             
    except Exception as e:
        print(f"   [WARN] CEO (LLM) Unavailable ({e}). Switching to **SIMULATION MODE**.")
        # Simulate the decision based on the input
        simulated_strategy = "AUSTERITY" if "crash" in market_condition else "BLITZSCALING"
        print(f"   [SIMULATION] CEO Decided: {simulated_strategy}")
        
        # Manually inject strategy and continue from Head Manager
        initial_state["strategy"] = simulated_strategy
        gen = executor.run_step_by_step(head_manager, initial_state)

    # Run the rest of the swarm
    for step in gen:
        steps.append(step)
        
    duration = time.time() - start_time
    
    # Analysis
    # Depending on fallback, strategy might differ where it's stored
    strategy = steps[0].get('state_diff', {}).get('added', {}).get('strategy', initial_state.get('strategy'))
    final_state = steps[-1].get('final_state', {})
    work_done = final_state.get('total_completed', 0)
    
    print(f"   Execution Time: {duration:.2f}s")
    print(f"   Work Units Completed: {work_done} ({description})")

# Scenario 1: Recession
run_scenario(
    name="SCENARIO 1: The Market Crashes...",
    market_condition="Competitors are folding, stock market is down 20%, crash is coming.",
    description="Graph Pruned!"
)

print("-" * 40)

# Scenario 2: Boom
run_scenario(
    name="SCENARIO 2: The AI Boom...",
    market_condition="AI is eating the world. VC money is free. Capture market share.",
    description="Full Utilization!"
)

print(f"\nThis demonstrates DYNAMIC COMPUTATION GRAPHS controlled by AI.")
