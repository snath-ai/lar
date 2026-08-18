import sys
import os
from pathlib import Path

# Add Lár to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lar" / "src"))
from lar import *
from lar.compliance import AuthorityLedger

# ==============================================================================
# OMNI-PIPELINE STRESS TEST
# ==============================================================================
# This script executes EVERY Lár node primitive (except ClearErrorNode) in a
# single, unbroken pipeline.
#
# WHAT THIS PIPELINE ACTUALLY DEMONSTRATES (claims below verified or corrected
# this session -- see CHANGELOG.md and examples/failure_modes/):
# 1. Dynamic Graph Topologies (AdaptiveNode): LangGraph graphs are compiled ahead
#    of time from Python-defined nodes/edges. Asking an LLM to generate a brand
#    new subgraph as JSON at runtime, structurally validating it (cycle detection,
#    tool allowlist) BEFORE instantiation, and injecting it live is not a built-in
#    LangGraph/CrewAI/AutoGen primitive as far as this session verified. This one
#    holds up -- proven live in examples/failure_modes/3_privilege_escalation.py.
# 2. Mathematical Triage (BranchTriageNode): this node lets Lár inspect BatchNode's
#    parallel branch outputs against a threshold before consolidation. The specific
#    claim about CrewAI's internal merge-phase mechanics is NOT independently
#    verified this session -- treat it as our own node's behavior, not a confirmed
#    statement about what CrewAI can't do.
# 3. Compliance Blocking (HumanJuryNode): CORRECTED -- LangGraph has a native
#    interrupt() function for human-in-the-loop that needs a checkpointer, not
#    webhooks or an external server. Lár's HumanJuryNode blocks directly in the
#    node layer and signs the decision into an Authority Ledger, which is a real,
#    distinct design -- but "LangChain requires webhooks" was wrong and is removed.
# 4. Explicit Memory Compression (ReduceNode): LangChain/LangGraph do have their
#    own memory-management options (summarization nodes, trimming utilities) --
#    "grows until it OOMs" overstated the absence of any mitigation. What's real:
#    ReduceNode explicitly deletes the raw pre-compression keys from GraphState,
#    which is a specific, verifiable behavior of this node (see node.py).
# ==============================================================================

print("Building Omni-Pipeline...")

# 0. Compliance Infrastructure
audit_logger = AuditLogger("lar_omni_logs")
ledger = AuthorityLedger("lar_omni_logs/authority_ledger.json")
validator = TopologyValidator()

# 9. Final ToolNodes (End of Graph)
def execute_freeze(state_dict):
    print("\n   [ACTION] 🚨 EXECUTING ASSET FREEZE. Interpol notified.")
    return {"final_status": "FROZEN"}

def execute_monitor(state_dict):
    print("\n   [ACTION] 👁️  MONITORING ENTITY. No immediate action taken.")
    return {"final_status": "MONITORED"}

action_freeze = ToolNode(tool_function=execute_freeze, input_keys=["__state__"], output_key=None, next_node=None)
action_monitor = ToolNode(tool_function=execute_monitor, input_keys=["__state__"], output_key=None, next_node=None)

# 8. RouterNode
def route_action(state: GraphState) -> str:
    summary = state.get("executive_summary", "").upper()
    if "FREEZE" in summary or "DENY" in summary or "CRITICAL" in summary:
        return "FREEZE"
    return "MONITOR"

router = RouterNode(
    decision_function=route_action,
    path_map={
        "FREEZE": action_freeze,
        "MONITOR": action_monitor
    },
    default_node=action_monitor
)

# 7. ReduceNode (Memory Compression)
# We compress the heavy raw branch outputs and explicitly delete them from the graph state.
reduce_node = ReduceNode(
    model_name="ollama/phi4:latest",
    prompt_template=(
        "You are an Executive AI. Summarize the following findings into a 2-sentence executive summary.\n"
        "Adaptive Structure Check: {adaptive_investigation}\n"
        "Sanctions Check: {sanctions_check}\n"
        "Human Jury Decision (if any): {jury_decision}\n"
        "End your summary with either [RECOMMENDATION: FREEZE] or [RECOMMENDATION: MONITOR]."
    ),
    input_keys=["adaptive_investigation", "sanctions_check", "jury_decision"], # These will be deleted!
    output_key="executive_summary",
    next_node=router
)

# 6. HumanJuryNode (Early-Exit Triage Destination)
human_jury = HumanJuryNode(
    prompt="CRITICAL threshold breached. Do you authorize a full asset freeze based on the raw branch findings?",
    choices=["approve", "reject"],
    output_key="jury_decision",
    authority_ledger=ledger,
    stakeholder_id="director.smith@interpol.int",
    stakeholder_role="Director of Enforcement",
    action_description="Authorizing asset freeze on Entity 492",
    next_node=reduce_node
)

# 5. BranchTriageNode and Triage Router
triage_router = RouterNode(
    decision_function=lambda s: "CRITICAL" if s.get("branch_critical") else "NOMINAL",
    path_map={
        "CRITICAL": human_jury,
        "NOMINAL": reduce_node
    },
    default_node=reduce_node
)

triage_node = BranchTriageNode(
    branch_output_keys=["adaptive_investigation", "sanctions_check"],
    critical_threshold="CRITICAL",
    next_node=triage_router
)

# 4. BatchNode (Parallel Threads)
# Branch A: AdaptiveNode (Generates dynamic JSON subgraph)
adaptive_prompt = (
    "You are an AI Architect. We need to investigate shell company structures based on this intel: {enriched_intel}\n"
    "Design a single LLMNode graph that analyzes offshore accounts. Return ONLY valid JSON."
    """
    {
      "nodes": [
        {
          "id": "offshore_analysis_node",
          "type": "LLMNode",
          "prompt": "You are a forensic accountant. Assess: {enriched_intel}. Reply with ONLY JSON: risk_level (LOW/MEDIUM/HIGH/CRITICAL), finding (1 sentence).",
          "output_key": "adaptive_investigation",
          "next_node": null
        }
      ],
      "entry_node": "offshore_analysis_node"
    }
    """
)
branch_a_adaptive = AdaptiveNode(
    llm_model="ollama/phi4:latest",
    prompt_template=adaptive_prompt,
    validator=validator,
    next_node=None # Batch branches end in None
)

# Branch B: LLMNode (Static sanctions check)
branch_b_llm = LLMNode(
    model_name="ollama/phi4:latest",
    prompt_template=(
        "Check standard sanctions database for: {enriched_intel}. "
        "Reply with ONLY JSON: risk_level (LOW/MEDIUM/HIGH/CRITICAL), finding (1 sentence). "
        "Force a CRITICAL risk_level because Entity 492 is a known threat."
    ),
    output_key="sanctions_check",
    next_node=None
)

batch_node = BatchNode(
    nodes=[branch_a_adaptive, branch_b_llm],
    next_node=triage_node
)

# 3. ToolNode
def enrich_data(raw_intel: str) -> dict:
    return {"enriched_intel": f"[ENRICHED] {raw_intel} | Entity ID: 492 | Flags: MULTIPLE"}

tool_node = ToolNode(
    tool_function=enrich_data,
    input_keys=["raw_intel"],
    output_key=None, # Merges dict into state
    next_node=batch_node
)

# 2. AddValueNode
start_node = AddValueNode(
    key="raw_intel",
    value="Massive capital flow across Zurich shell companies. Entity 492 detected.",
    next_node=tool_node
)

# ==============================================================================
# EXECUTION
# ==============================================================================
if __name__ == "__main__":
    executor = GraphExecutor(logger=audit_logger)
    
    print("\n🚀 Executing Omni-Pipeline (9 Primitives)...\n")
    initial_state = {"token_budget": 10000}
    
    for step in executor.run_step_by_step(start_node, initial_state):
        pass # All logging is handled natively by Lár
        
    print("\n✅ Omni-Pipeline execution complete.")
    print(f"Audit log saved in {audit_logger.log_dir}")
