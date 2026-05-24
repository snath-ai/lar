# For setup instructions, see: https://docs.snath.ai/guides/litellm_setup/
import os
import json
import sys
from lar import GraphState, GraphExecutor, LLMNode, ToolNode

# ------------------------------------------------------------------------------
# Example 18: The Time Traveller (Persistence)
# ------------------------------------------------------------------------------
# Use Case: Long-running agents that need to pause, sleep, or recover from crashes.
# Pattern:  Serialize State -> Save -> Load -> Resume.
# ------------------------------------------------------------------------------

SAVE_FILE = "lar_time_machine.json"

# 1. Define Final Step (The destination)
final_step_llm = LLMNode(
    model_name="ollama/phi4:latest",
    prompt_template="Summarize this historical data: {data}",
    output_key="history_summary",
    next_node=None
)

# 2. Define Crasher Logic
def crasher_logic(state):
    # Simulate a "Crash" or Stop point
    print("\n💥 CRASH! Saving state and exiting...")
    # Serialize state
    # NOTE: In a real app, you'd save to DB. Here we use JSON.
    with open(SAVE_FILE, "w") as f:
        json.dump(state.get_all(), f, indent=2)
    print(f"💾 State saved to {SAVE_FILE}. Run script again to resume.")
    sys.exit(0) 

# 3. Define Crasher Node
crasher = ToolNode(
    tool_function=crasher_logic,
    input_keys=["__state__"], # Access full state object
    output_key=None,
    next_node=final_step_llm    # This is skipped in the first run due to sys.exit
)

# 4. Define Step 1 Logic
def step_1_logic():
    print("\n[Step 1] Executing initial logic...")
    return {"data": "Pre-Crash Data: The user visited page A."}

# 5. Define Step 1 Node (The Start)
step_1 = ToolNode(
    tool_function=step_1_logic,
    input_keys=[],
    output_key=None, # Merge dict into state
    next_node=crasher
)

def run_time_travel():
    executor = GraphExecutor()

    # 1. Check if a save file exists (Resume Mode)
    if os.path.exists(SAVE_FILE):
        print(f"\n⏳ FOUND SAVE FILE: {SAVE_FILE}")
        print("🔄 RESUMING GRAPH...")
        
        with open(SAVE_FILE, "r") as f:
            restored_data = json.load(f)
        
        print(f"📊 Restored Data: {restored_data}")
        
        # Start immediately at the next node (Final Step)
        # Note: In a real 'resumer', the serialization would include the 'next_step' pointer.
        # Here we manually know it's 'final_step_llm'.
        
        final_step = None
        for step in executor.run_step_by_step(final_step_llm, restored_data):
             print(f"Step {step['step']} (RESUMED): {step['node']} -> {step['outcome']}")
             final_step = step
        
        print("\n✅ GRAPH FINISHED SUCCESSFULLY")
        if final_step:
            print(f"📝 Final Output: {final_step['state_after'].get('history_summary')}")
        
        # Cleanup
        if os.path.exists(SAVE_FILE):
            os.remove(SAVE_FILE)
            print("\n🧹 Cleanup: Time machine destroyed.")
        
    else:
        # 2. Fresh Run (Start Mode)
        print("\n🟢 STARTING FRESH RUN")
        
        try:
            for step in executor.run_step_by_step(step_1, {}):
                print(f"Step {step['step']}: {step['node']} -> {step['outcome']}")
        except SystemExit:
            pass # Expected behavior

if __name__ == "__main__":
    run_time_travel()
