# Deploying Lár Agents (Production Guide)

One of the most common questions is: *"How do I deploy this?"*

Lár is an **Engine** (like PyTorch or Flask), not an **Application** (like ChatGPT).
To deploy it, you simply wrap it in a standard Python web server.

---

## 1. The Strategy: "Headless" Engine

You should run your agent as a **stateless REST API**.
*   **Input:** JSON (The User Task)
*   **Output:** JSON (The Final State)
*   **Audit Log:** Save the `result_log` to a database (Postgres/Mongo) for compliance.

---

## 2. Using FastAPI (Recommended)

Deep within the `examples/` folder is **Example 4**. It is a complete, copy-pasteable implementation of a Lár Agent running on FastAPI.

**[`examples/basic/4_fastapi_server.py`](https://github.com/snath-ai/lar/blob/main/examples/basic/4_fastapi_server.py)**

### Quick Start

1.  **Install FastAPI**:
    ```bash
    pip install fastapi uvicorn
    ```

2.  **Paste this code**:
    ```python
    import uvicorn
    from fastapi import FastAPI
    from lar import LLMNode, GraphExecutor
    
    app = FastAPI()
    executor = GraphExecutor()
    
    # Define a simple agent
    agent = LLMNode(
        model_name="gpt-4o", 
        prompt_template="Echo: {task}", 
        output_key="response"
    )
    
    @app.post("/run")
    def run_agent(task: str):
        # Run standard Lár execution
        result = list(executor.run_step_by_step(agent, {"task": task}))
        return result[-1]["state_after"]
        
    if __name__ == "__main__":
        uvicorn.run(app, port=8000)
    ```

3.  **Deploy**:
    Run this script on **Heroku**, **AWS Lambda**, **Railway**, or **Render** just like any other Python app.

---

## 3. Why not LangServe?

Frameworks like LangChain force you to use their proprietary "Serving" layers (`LangServe`) which often lock you into their ecosystem.

By using standard **FastAPI**, you essentially "own" the deployment. You can:

*   Add custom Authentication (OAuth2, JWT).
*   Rate Limit users by IP.
*   Save logs to your own SQL database.
*   Integrate with existing Stripe payment flows.
