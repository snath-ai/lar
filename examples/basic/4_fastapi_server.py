# For setup instructions, see: https://docs.snath.ai/guides/litellm_setup/
"""
Example 19: Deploying Lár as an API (FastAPI)

"How do I deploy this?"
Lár is a library, not a platform. This means you wrap it in standard Python web frameworks
like FastAPI, Flask, or Django.

This example shows how to turn an Agent into a REST API in < 50 lines.

Prerequisites:
    pip install fastapi uvicorn
"""

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from lar import GraphState, GraphExecutor, LLMNode, AddValueNode
from dotenv import load_dotenv

# 1. Setup
load_dotenv()
app = FastAPI(title="Lár Agent API", version="1.0")

# 2. Define Request Schema
class AgentRequest(BaseModel):
    task: str
    user_id: str = "anon"

# 3. Build the Graph (Global Instance)
# We build the graph once at startup.
def build_agent_graph():
    # End Node
    final_node = AddValueNode(key="status", value="completed", next_node=None)
    
    # Simple Agent
    agent_node = LLMNode(
        model_name="ollama/phi4", # Or "ollama/phi4", "claude-3-opus"
        prompt_template="You are a helper API. Answer this request concisely: {task}",
        output_key="response",
        next_node=final_node
    )
    return agent_node

# Initialize
root_node = build_agent_graph()
executor = GraphExecutor()

# 4. Define the Endpoint
@app.post("/run")
async def run_agent(request: AgentRequest):
    """
    Executes the agent deterministically.
    """
    print(f"--> Received request: {request.task}")
    
    try:
        # Run the graph
        initial_state = {"task": request.task, "user_id": request.user_id}
        
        # We use list() to execute all steps synchronously for this simple example.
        # For long-running jobs, use a background task queue (Celery/Bull).
        result_log = list(executor.run_step_by_step(root_node, initial_state))
        
        if not result_log:
             return {"status": "error", "reason": "No steps executed"}

        last_step = result_log[-1]
        
        # Check for error in the last step
        if last_step.get("outcome") == "error":
             return {
                 "status": "failed",
                 "error": last_step.get("error_details", "Unknown error"),
                 "audit_log": result_log
             }

        final_state = last_step.get("state_after", {})
        
        return {
            "status": "success",
            "result": final_state.get("response"),
            "steps": len(result_log),
            "audit_log": result_log  # Full "Glass Box" audit trail
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 5. Run Server
if __name__ == "__main__":
    print("Starting Lár API server on http://localhost:8000")
    print("Test with: curl -X POST 'http://localhost:8000/run' -H 'Content-Type: application/json' -d '{\"task\": \"Hello!\"}'")
    uvicorn.run(app, host="0.0.0.0", port=8000)
