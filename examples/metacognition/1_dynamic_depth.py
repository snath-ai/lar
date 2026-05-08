
"""
Example 25: Adaptive Fan-Out

Demonstrates runtime graph composition using `AdaptiveNode`.
The agent analyses query complexity and composes a processing subgraph with
an appropriate number of worker nodes — determined at execution time, not
hardcoded at development time.

"Simple" query -> 1 worker node.
"Complex" query -> 3 sequential worker nodes.

Expected Output:
- Simple query: "What is the capital of France?" -> Single researcher chain
- Complex query: Deep geopolitical analysis -> Multiple researcher chain
- Final summary synthesised from all research steps

Note: Current implementation uses sequential chains. BatchNode factory support
is tracked separately. See README.md for details.

Compliance tags: Art. 3(23) (via TopologyValidator), Art. 12 (Causal Trace logging)
"""

import os
import json
from lar import (
    GraphExecutor, GraphState,
    AdaptiveNode, TopologyValidator,
    LLMNode, AddValueNode, ToolNode
)
from dotenv import load_dotenv

load_dotenv()

# --- 1. Define the Tools ---

def scrape_url(url: str, depth: int = 1):
    """Simulate scraping."""
    print(f"    [Tool: scrape_url] Scraping {url} (Depth {depth})...")
    return {"content": f"Scraped content from {url}"}

def summarize_results(*results):
    """Simulate summarization."""
    print(f"    [Tool: summarize] Summarizing {len(results)} items...")
    return f"Summary of {len(results)} sources."

# --- 2. Define the Validator ---

# We only allow the dynamic graph to use specific tools
validator = TopologyValidator(allowed_tools=[scrape_url, summarize_results])

# --- 3. Define the Dynamic Node ---


# This prompt teaches the LLM how to build the graph.
# It requests a JSON spec that uses "BatchNode" if high intensity is needed.
# Note: Since the simple DynamicNode primitive in `src/lar/dynamic.py` 
# currently only factory-instantiates LLMNode/ToolNode, we will demonstrate
# a dynamic chain of ToolNodes for simplicity, or we'd need to extend the factory.
#
# For this Proof of Concept, we will ask it to generate N separate ToolNodes
# wired in a chain (Sequential) or a specific branching structure supported by the basic factory.
# 
# LIMITATION CHECK: `src/lar/dynamic.py` currently only supports LLMNode and ToolNode factories.
# It does NOT support BatchNode factory yet.
# So we will demonstrate "Dynamic Depth" -> "Chain of N Researchers".

DYNAMIC_PROMPT = """
You are a Research Architect.
Analyze the user's request: "{request}"

If it is simple (e.g., "Fact check"), use 1 researcher node.
If it is complex (e.g., "Deep dive"), use 3 researcher nodes in a sequence.

You have access to these tools ONLY:
- scrape_url
- summarize_results

Output a JSON GraphSpec with this schema:
{{
  "nodes": [
    {{
        "id": "r1", 
        "type": "ToolNode", 
        "tool_name": "scrape_url", 
        "input_keys": ["url"], 
        "output_key": "res1", 
        "next": "r2" (or "final")
    }},
    ...
    {{
        "id": "final",
        "type": "ToolNode",
        "tool_name": "summarize_results",
        "input_keys": ["res1", "res2"...], # Pass available keys
        "output_key": "summary",
        "next": null # End of subgraph
    }}
  ],
  "entry_point": "r1"
}}
"""

# The exit node of the main graph (where we land after dynamic subgraph)
end_node = AddValueNode("status", "Done")

dynamic_architect = AdaptiveNode(
    llm_model="ollama/phi4",
    prompt_template=DYNAMIC_PROMPT,
    validator=validator,
    next_node=end_node,
    context_keys=["request", "url"]
)


# --- 4. Wire the Main Graph ---

entry = dynamic_architect # Start directly with the dynamic node

# --- 5. Run ---

def run_simulation(request_text, complexity_label):
    print(f"\n\n{'='*60}")
    print(f"TEST CASE: {complexity_label}")
    print(f"{'='*60}")
    print(f"Request: '{request_text}'")
    print(f"{'='*60}\n")
    
    try:
        executor = GraphExecutor()
        initial_state = {
            "request": request_text, 
            "url": "http://example.com"
        }

        print("--- Starting Execution ---\n")
        results = list(executor.run_step_by_step(entry, initial_state))
        
        final_state = results[-1].get("state_after", {})
        
        print(f"\n{'='*60}")
        print(f"RESULT")
        print(f"{'='*60}")
        print(f"Summary: {final_state.get('summary', 'No summary generated')}")
        print(f"Status: {final_state.get('status')}")
        
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        print("Note: Ensure ollama/phi4 is installed and running")

if __name__ == "__main__":
    # Test 1: Simple
    run_simulation("What is the capital of France?", "SIMPLE")
    
    # Test 2: Complex (Uncomment to test)
    # run_simulation("Analyze the geopolitical impact of quantum computing on cryptocurrency.", "COMPLEX")
