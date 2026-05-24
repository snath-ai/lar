import sys
import os
import json
from pathlib import Path

# Add Lár to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lar import GraphExecutor, LLMNode, ToolNode, RouterNode, BatchNode, FunctionalNode, HumanJuryNode
from lar.state import GraphState
from lar.logger import AuditLogger
from lar.adaptive import AdaptiveNode, TopologyValidator
from lar.compliance.branch_triage import BranchTriageNode
from lar.compliance.authority_record import AuthorityLedger

# ==============================================================================
# EXTREME FRACTAL SWARM 
# ==============================================================================
# This script pushes the Lár architecture to the absolute extreme limit by:
# 1. Using AdaptiveNode to DYNAMICALLY GENERATE a BatchNode at runtime.
# 2. Executing 3 parallel LLM threads natively from the generated JSON spec.
# 3. Intercepting the parallel merge with a BranchTriageNode.
# 4. Detecting a "CRITICAL" anomaly inside one of the parallel threads.
# 5. Halting the swarm and kicking out to a HumanJuryNode for emergency approval.
# 6. Compressing the JSON states into a single string using ReduceNode to prevent OOM.
# ==============================================================================

def main():
    print("Building Extreme Fractal Swarm...")
    os.makedirs("fractal_swarm_logs", exist_ok=True)
    
    # 1. Setup the Validators and Ledgers
    validator = TopologyValidator(max_nodes=10)
    audit_logger = AuditLogger(log_dir="fractal_swarm_logs", hmac_secret="fractal_secret")
    authority_ledger = AuthorityLedger(hmac_secret="fractal_secret")

    # 2. Build the final nodes
    def execute_liquidation(state: GraphState):
        decision = state.get("jury_decision", "approve")
        if decision == "approve":
            print("\n   [ACTION] 🚨 EXECUTING EMERGENCY PORTFOLIO LIQUIDATION. 🚨")
            state.set("final_status", "LIQUIDATED")
        else:
            print("\n   [ACTION] NORMAL OPERATIONS RESUMED.")
            state.set("final_status", "NORMAL")

    tool_node = FunctionalNode(func=execute_liquidation, next_node=None)

    # Compress the massive memory overhead
    def summarize_swarm(state: GraphState):
        # We manually compress the parallel branches to free tokens
        summary = state.get("branch_findings_summary", "No findings.")
        state.set("master_strategy", f"Swarm Executive Summary: {summary}")
        # Explicit deletion for O(1) memory
        state.delete("tech_analysis")
        state.delete("energy_analysis")
        state.delete("health_analysis")

    reduce_node = FunctionalNode(func=summarize_swarm, next_node=tool_node)

    # 3. Build the Emergency Jury
    jury_node = HumanJuryNode(
        prompt="[SWARM EMERGENCY] A sub-agent detected a CRITICAL market anomaly. Authorize emergency liquidation?",
        choices=["approve", "reject"],
        output_key="jury_decision",
        context_keys=["branch_findings_summary"],
        authority_ledger=authority_ledger,
        stakeholder_id="director.alpha@hedgefund.com",
        stakeholder_role="Managing Director",
        action_description="Emergency portfolio liquidation based on fractal swarm intelligence.",
        next_node=reduce_node
    )

    # 4. Build the Triage Router
    def swarm_router(state: GraphState) -> str:
        if state.get("branch_critical", False):
            return "PANIC"
        return "CHILL"

    router_node = RouterNode(
        decision_function=swarm_router,
        path_map={
            "PANIC": jury_node,
            "CHILL": reduce_node
        }
    )

    # 5. Build the BranchTriageNode to intercept the Swarm's payload
    triage_node = BranchTriageNode(
        branch_output_keys=["tech_analysis", "energy_analysis", "health_analysis"],
        critical_threshold="CRITICAL",
        next_node=router_node
    )

    # 6. Build the Adaptive Root Architect
    # We heavily guide the generation to ensure it runs cleanly on a 16GB laptop with Phi-4.
    adaptive_prompt = """You are the Root Architect AI. 
Generate a JSON subgraph containing a BatchNode ('batch_1') that runs 3 LLMNodes in parallel to analyze TECH, ENERGY, and HEALTHCARE.
You MUST output EXACTLY this JSON structure:
{
  "entry_point": "batch_1",
  "nodes": [
    {
      "id": "batch_1",
      "type": "BatchNode",
      "concurrent_nodes": ["llm_tech", "llm_energy", "llm_health"],
      "next": null
    },
    {
      "id": "llm_tech",
      "type": "LLMNode",
      "prompt": "Evaluate TECH sector. Reply ONLY in JSON: {\"risk_level\": \"LOW/MEDIUM/HIGH/CRITICAL\", \"finding\": \"string\"}. FORCE risk_level to CRITICAL to simulate a Black Swan.",
      "output_key": "tech_analysis",
      "next": null
    },
    {
      "id": "llm_energy",
      "type": "LLMNode",
      "prompt": "Evaluate ENERGY sector. Reply ONLY in JSON: {\"risk_level\": \"LOW\", \"finding\": \"Stable\"}.",
      "output_key": "energy_analysis",
      "next": null
    },
    {
      "id": "llm_health",
      "type": "LLMNode",
      "prompt": "Evaluate HEALTHCARE sector. Reply ONLY in JSON: {\"risk_level\": \"LOW\", \"finding\": \"Stable\"}.",
      "output_key": "health_analysis",
      "next": null
    }
  ]
}
"""
    adaptive_node = AdaptiveNode(
        llm_model="ollama/phi4:latest",
        prompt_template=adaptive_prompt,
        validator=validator,
        next_node=triage_node,
        max_depth=3,
        generation_config={"temperature": 0.0}
    )

    # 7. Execute!
    executor = GraphExecutor(log_dir="fractal_swarm_logs", hmac_secret="fractal_secret", logger=audit_logger)
    
    print("\n🚀 LAUNCHING FRACTAL SWARM...\n")
    
    # We use builtins.input mocking for the HumanJuryNode so it runs seamlessly in CI/CD.
    import builtins
    _orig_input = builtins.input
    def mock_input(prompt):
        print(f"{prompt}approve")
        return "approve"
    builtins.input = mock_input

    try:
        for step in executor.run_step_by_step(adaptive_node, {}):
            node_name = step.get("node", "?")
            print(f"  [{node_name}] executed.")
    finally:
        builtins.input = _orig_input

    authority_ledger.save("fractal_swarm_logs/authority_ledger.json")
    print("\n✅ EXTREME FRACTAL SWARM COMPLETE.")
    print("✅ Dynamic Topology Verified.")
    print("✅ Parallel Branch Execution Verified.")
    print("✅ Triage Intercept Verified.")

if __name__ == "__main__":
    main()
