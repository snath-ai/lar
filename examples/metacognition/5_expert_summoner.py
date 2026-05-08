
"""
Example 29: Domain Subgraph Dispatch

Demonstrates pre-defined expert subgraph injection. Instead of the LLM generating
graph structure from scratch, the AdaptiveNode selects and injects a pre-approved
domain-specific subgraph based on query classification.

Scenario:
User asks a legal question.
1. AdaptiveNode classifies the query domain
2. Selects the appropriate pre-defined expert specification (legal_expert)
3. The validated Legal Expert subgraph executes

Expected Output:
Query detected as "Legal" -> Legal expert loaded -> Legal research performed -> Advice provided

Note: This uses a simplified approach where the expert spec is embedded in the prompt.
A production system would load from a directory of expert JSON files.
"""

import json
import os
from contextlib import contextmanager
from lar import (
    GraphExecutor, GraphState, 
    AdaptiveNode, TopologyValidator,
    AddValueNode, ToolNode, LLMNode
)
from dotenv import load_dotenv

load_dotenv()

# --- 1. File Management Helper ---

@contextmanager
def temporary_expert_file(filename: str, content: dict):
    """Context manager for safe file creation and cleanup."""
    try:
        with open(filename, "w") as f:
            json.dump(content, f, indent=2)
        print(f"    [System] Created expert file: {filename}")
        yield filename
    finally:
        if os.path.exists(filename):
            os.remove(filename)
            print(f"    [System] Cleaned up expert file: {filename}")

# --- 2. Define the Expert Tools ---

def cite_law(code_section: str = "Section 230") -> str:
    """Simulate looking up a legal code section."""
    print(f"    [LegalExpert] Citing Law: {code_section}")
    return f"According to {code_section}, digital platforms have certain protections..."

# --- 3. Define the Validator ---

validator = TopologyValidator(allowed_tools=[cite_law])

# --- 4. Create the Expert Agent Specification ---

# This would normally be loaded from a files like:
# - experts/legal_expert.json
# - experts/medical_expert.json
# - experts/financial_expert.json

LEGAL_EXPERT_SPEC = {
  "nodes": [
    {
      "id": "research",
      "type": "ToolNode",
      "tool_name": "cite_law",
      "input_keys": [], 
      "output_key": "law_context",
      "next": "advice"
    },
    {
      "id": "advice",
      "type": "LLMNode",
      "prompt": "Based on this legal context: {law_context}, answer the question: {query}. Provide brief advice.",
      "output_key": "final_advice",
      "next": None
    }
  ],
  "entry_point": "research"
}

# --- 5. Define the Summoner (Dynamic Node) ---

# The summoner analyzes the query and outputs the appropriate expert spec
# In this simplified version, we embed the spec in the prompt
# A production version would have the LLM output {"expert": "legal"} 
# and then load from disk

SUMMONER_PROMPT = """
You are a Staffing Manager.
Query: "{query}"

If the query is about Law, Lawyers, Legal issues, Courts, etc:
Output this EXACT JSON (no modifications):
""" + json.dumps(LEGAL_EXPERT_SPEC, indent=2) + """

If the query is about Medicine or Health:
Output a simple single-node spec that says "Medical expert not available".

IMPORTANT: Output ONLY valid JSON, no explanations.
"""

end_node = AddValueNode("status", "Done")

summoner = AdaptiveNode(
    llm_model="ollama/phi4",
    prompt_template=SUMMONER_PROMPT,
    validator=validator,
    next_node=end_node,
    context_keys=["query"]
)

# --- 6. Run with Proper Cleanup ---

entry = summoner

if __name__ == "__main__":
    print("\n" + "="*60)
    print("TEST CASE: Expert Summoner")
    print("="*60)
    print("Query: 'My landlord evicted me without notice.'")
    print("Expected: Detect legal domain -> Load legal expert -> Provide advice")
    print("="*60)
    
    # Use context manager for safe file handling
    expert_filename = "legal_expert.json"
    
    try:
        with temporary_expert_file(expert_filename, LEGAL_EXPERT_SPEC):
            executor = GraphExecutor()
            initial_state = {
                "query": "My landlord evicted me without notice. What are my rights?"
            }

            print("\n--- Starting Execution ---\n")
            results = list(executor.run_step_by_step(entry, initial_state))
            
            final_state = results[-1].get("state_after", {})
            
            print("\n" + "="*60)
            print("RESULT")
            print("="*60)
            print(f"Expert Summoned: Legal Expert")
            print(f"Law Context: {final_state.get('law_context', 'N/A')[:80]}...")
            print(f"\nFinal Advice:\n{final_state.get('final_advice', 'No advice generated')}")
            print(f"\nStatus: {final_state.get('status')}")
            
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        print("Note: Ensure ollama/phi4 is installed and running")
    
    # File cleanup happens automatically via context manager
