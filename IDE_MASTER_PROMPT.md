# Lár Framework — Master Context for AI Coding Assistants
> **Note to AI**: You are coding with **Lár**, a deterministic graph-based agent framework.
> Before generating any code you MUST ingest this full context. Violating the rules below will produce broken code.

---

## Core Principles

1. **Forward Definition & Wiring (CRITICAL)**: Define your nodes first with `next_node=None`, and then wire them forward in execution order (e.g., `node_a.next_node = node_b`). This is much cleaner than reverse-definition.
2. **Strict Typing**: Every node argument and tool function MUST have Python type hints.
3. **Explicit Linking**: Connect nodes with `node_a.next_node = node_b` or `RouterNode(path_map={...})`. There is no auto-wiring.
4. **No Magic State**: Always `state.get("key")` and `state.set("key", value)`. Never assume a key exists.
5. **No Hidden Prompts**: Every prompt must be visible in `prompt_template`. No prompts buried in tool functions.
6. **Token Budget First**: Always seed `token_budget` in `initial_state`. The executor enforces it automatically.

---

## EU AI Act & Enterprise Compliance (CRITICAL)

Lár is designed to be fully compliant with the **EU AI Act (enforceable Aug 2026)**. When building enterprise systems or integrations, you MUST prioritize the following:

1. **Causal Audit Trails**: All state changes MUST be routed through standard Lár nodes to ensure the `AuditLogger` captures the state diff. If you build a custom integration or third-party API call, wrap it in a `ToolNode` or `@node` so the deterministic state change is recorded and cryptographically signed. Integrations MUST be audited.
2. **Third-Party Integrations**: Integrations (e.g., Slack bots, web scrapers, database writers) are **external actions** that must be audited. Do not bypass the Lár state object. Return integration results as a dict so they merge into the state and appear in the `state_diff`.
3. **High-Risk Actions**: For any action that modifies production data or makes critical decisions (finance, healthcare, HR), inject a `HumanJuryNode` before the action executes to fulfill the **Art. 14 Human Oversight** requirement.
4. **No Hidden Logic**: Do not hide LLM calls inside regular Python functions. Use `LLMNode` so the prompt and generation are exposed to the `AuditLogger`.
5. **Fractal & Parallel Agents**: When using `BatchNode` with parallel branches that each produce a risk assessment, insert a `BranchTriageNode` between `BatchNode` and `RouterNode`. It parses all branch outputs, builds `branch_findings_summary` (so the human jury sees per-dimension evidence, not just the consolidated score), and sets `branch_critical=True` if any branch breaches the threshold. This is what makes Art. 14 oversight *meaningful* in multi-branch pipelines.
6. **Resumable Graphs & Asynchronous HitL**: For enterprise workloads, do not block the Python process on `HumanJuryNode`. Instead, inject a `SuspendNode` (a `FunctionalNode` that calls `sys.exit(0)`) to gracefully exit the script, and dump the state to JSON *cryptographically signed with HMAC-SHA256*. When resuming, mathematically verify the HMAC, inject the CLI response into a native `HumanJuryNode`, and execute the remainder of the graph.
7. **Lethal Trifecta Guard**: Any external execution tool MUST be verified by a `LethalTrifectaGuard` before execution (AEPD Rule of 2 compliance).
8. **Session Memory Erasure**: To comply with GDPR Art 17, use `SessionMemoryNode` with `mode="erase"` at the very end of the pipeline to purge intermediate PII.

---

## Model Name Conventions (LiteLLM Prefixes)

Lár uses **LiteLLM** for all LLM calls. Always use the correct provider prefix:

| Provider | Model string |
|---|---|
| Ollama (local) | `"ollama/llama3.2"`, `"ollama/qwen2.5:14b"`, `"ollama/deepseek-r1:7b"` |
| Google AI Studio | `"gemini/gemini-2.0-flash"`, `"gemini/gemini-1.5-pro"` |
| OpenAI | `"gpt-4o"`, `"gpt-4o-mini"` |
| Anthropic | `"claude-3-5-sonnet-20241022"` |
| DeepSeek | `"deepseek/deepseek-chat"` |
| Vertex AI | `"vertex_ai/gemini-2.0-flash"` |

> **Ollama Note**: Ollama runs locally. No API key needed. Ollama must be running (`ollama serve`) before graph execution. Use it for air-gapped / sovereign deployments.

---

## Complete Node Reference

### `AddValueNode` — Seed or Copy State Values
```python
from lar import AddValueNode

# Set a literal value
seed_topic = AddValueNode(key="topic", value="My research question", next_node=next_step)

# Copy one state key to another (use {source_key} syntax)
copy_node = AddValueNode(key="input", value="{raw_input}", next_node=next_step)
```

---

### `LLMNode` — Full Option Set
```python
from lar import LLMNode

node = LLMNode(
    model_name      = "ollama/llama3.2",          # Any LiteLLM prefix
    prompt_template = "Analyze {topic} and return findings.",
    output_key      = "analysis",
    next_node       = next_step,

    # Optional — Behavior
    system_instruction = "You are a senior research analyst.",
    generation_config  = {"temperature": 0.3, "max_tokens": 1024},
    max_retries        = 3,       # Auto-retry on rate limits (exponential backoff)

    # Optional — Streaming (prints tokens to stdout as they arrive)
    stream = True,

    # Optional — Structured JSON output (pass a Pydantic model class)
    response_format = MyPydanticSchema,

    # Optional — Enterprise (Snath Cloud / LiteLLM Proxy)
    fallbacks         = ["gpt-4o-mini"],    # Auto-failover if primary fails
    caching           = True,               # Semantic / exact-match caching
    success_callbacks = ["langfuse"],       # Observability dashboard hooks
)
```

**Key behaviours:**
- `token_budget` in state is **automatically deducted** after each call. Execution halts if budget hits 0.
- `<think>...</think>` tags are **automatically parsed** out of reasoning models (DeepSeek R1, o1). Clean answer saved to `output_key`; reasoning trace saved in `__last_run_metadata["reasoning_content"]`.
- `{variable}` and `{{variable}}` syntax both work in `prompt_template`.
- Missing template keys log a warning and use the raw template — they do **not** crash.

---

### `ToolNode` — Run Any Python Function
```python
from lar import ToolNode

# Mode 1: Positional inputs, single output key
tool = ToolNode(
    tool_function = my_function,         # def my_function(text: str) -> str
    input_keys    = ["synthesis"],        # State keys passed as positional args
    output_key    = "word_count",
    next_node     = next_step,
    error_node    = error_handler,       # Optional: jump here if function raises
)

# Mode 2: Full state access
tool_full = ToolNode(
    tool_function = process_state,       # def process_state(state: GraphState) -> str
    input_keys    = ["__state__"],        # "__state__" passes the entire GraphState object
    output_key    = "result",
    next_node     = next_step,
)

# Mode 3: Dict-merge (output_key=None + function returns dict)
# The returned dict is merged directly into state — no single output key
tool_merge = ToolNode(
    tool_function = multi_output_fn,     # def multi_output_fn(...) -> dict
    input_keys    = ["input"],
    output_key    = None,                # Triggers dict-merge mode
    next_node     = next_step,
)
```

**Error handling:** If `tool_function` raises any exception, `state["last_error"]` is set and execution jumps to `error_node`. If `error_node` is None, execution stops.

---

### `RouterNode` — Conditional Branching
```python
from lar import RouterNode

def decide(state: GraphState) -> str:
    if state.get("confidence", 0) > 0.8:
        return "high"
    return "low"

router = RouterNode(
    decision_function = decide,
    path_map = {
        "high": approved_node,
        "low":  review_node,
    },
    default_node = fallback_node,  # Used when decision_function returns an unknown key
)
```

> RouterNode logs the decision to `state["_router_decision"]` automatically — visible in the audit diff.

---

### `BatchNode` — Parallel Fan-Out
```python
from lar import BatchNode, LLMNode

# Workers are independent nodes (can be full subgraph chains, not just single nodes)
worker_a = LLMNode(model_name="ollama/llama3.2", ..., output_key="perspective_a")
worker_b = LLMNode(model_name="ollama/llama3.2", ..., output_key="perspective_b")

batch = BatchNode(
    nodes     = [worker_a, worker_b],  # Run in parallel threads
    next_node = aggregator_node,
)
```

**Key behaviours:**
- Each worker gets a **deep copy** of the state — full thread isolation.
- Non-conflicting state updates are **merged back** after all workers finish.
- `token_budget` is **reconciled mathematically** across all threads (sum of all deltas deducted).
- Workers can themselves be full subgraph chains — `BatchNode` runs a mini-executor per thread.
- Worker errors set `state["last_error"]` but do **not** stop other threads.

---

### `ReduceNode` — Map-Reduce / Context Compression
```python
from lar import ReduceNode

# Inherits all LLMNode options (system_instruction, generation_config, etc.)
compressor = ReduceNode(
    model_name      = "ollama/llama3.2",
    prompt_template = (
        "Synthesise these two perspectives into one 200-word summary:\n"
        "A: {perspective_a}\nB: {perspective_b}"
    ),
    input_keys  = ["perspective_a", "perspective_b"],  # DELETED from state after run
    output_key  = "synthesis",
    next_node   = next_step,
    system_instruction = "You are a senior researcher.",
    generation_config  = {"temperature": 0.4, "max_tokens": 512},
)
```

> `input_keys` are **deleted from state** after the LLM call succeeds. This is the primary mechanism for preventing context window bloat in Map-Reduce pipelines.

---

### `ClearErrorNode` — Error Janitor
```python
from lar import ClearErrorNode

# One argument only. Sets state["last_error"] = None and proceeds.
cleanup = ClearErrorNode(next_node=retry_node)
```

> Always place `ClearErrorNode` between an error-producing `ToolNode` and the retry/recovery path.

---

### `HumanJuryNode` & `SuspendNode` — Human-in-the-Loop (EU AI Act Article 14)

In high-risk enterprise graphs, execution should **suspend to disk** rather than block the process.

```python
import sys, json, hmac, hashlib
from lar import HumanJuryNode, FunctionalNode, GraphState

# 1. The HMAC Suspend Node (Pauses execution and exits)
def suspend_logic(state: GraphState):
    raw_state = state.get_all()
    sig = hmac.new(b"secret", json.dumps(raw_state, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    with open("suspend.json", "w") as f:
        json.dump({"signature": sig, "state": raw_state}, f)
    sys.exit(0)

suspend_node = FunctionalNode(func=suspend_logic, next_node=None)

# 2. The Native Human Jury (Resumes execution)
jury = HumanJuryNode(
    prompt       = "Approve deployment of this AI recommendation?",
    choices      = ["approve", "reject"],
    output_key   = "jury_verdict",
    context_keys = ["synthesis", "risk_score"],
    next_node    = None,
)

suspend_node.next_node = jury
```

> **Resuming**: When you restart the script with `--resume approve`, load `suspend.json`, verify the HMAC signature with `hmac.compare_digest`, mock `builtins.input` to return the CLI argument, and pass the state directly to `executor.run_step_by_step(jury, state)`.

---

### `FunctionalNode` / `@node` Decorator — Lightweight Custom Logic
```python
from lar import node, GraphState

# Option A: @node decorator (preferred for simple functions)
# IMPORTANT: Wire .next_node AFTER graph construction (decorator runs at definition time)
@node(output_key="normalised_input")
def normalise(state: GraphState) -> str:
    return state.get("raw_input", "").strip().lower()

normalise.next_node = batch_node   # Wire after all downstream nodes are created

# Option B: FunctionalNode class directly
from lar import FunctionalNode

fn_node = FunctionalNode(
    func       = normalise,
    output_key = "normalised_input",
    next_node  = batch_node,
)
```

---

### `AdaptiveNode` + `TopologyValidator` — Runtime Graph Composition (Art. 3(23) Compliant)
```python
from lar import AdaptiveNode, TopologyValidator

# 1. Allowlist: Only these functions can be used as ToolNodes in the generated subgraph
def safe_search(query: str) -> str: ...
def safe_summarise(text: str) -> str: ...

validator = TopologyValidator(allowed_tools=[safe_search, safe_summarise])

# 2. AdaptiveNode: LLM designs a subgraph at runtime; TopologyValidator rejects unsafe graphs
adaptive = AdaptiveNode(
    llm_model       = "ollama/qwen2.5:14b",
    prompt_template = "Design a Lár subgraph to solve: {task}",
    validator       = validator,
    next_node       = rejoin_node,        # Where the subgraph exits back to
    context_keys    = ["task", "budget"], # State keys injected into the prompt
    system_instruction = "Output ONLY valid JSON. Use only LLMNode and ToolNode types.",
)
```

**Supported subgraph node types**: `LLMNode`, `ToolNode`, `BatchNode`, `AdaptiveNode` (recursive composition).
**Note**: `DynamicNode` is a deprecated alias for `AdaptiveNode` — existing code continues to work but will emit a `DeprecationWarning`.

---

### `BranchTriageNode` — Post-BatchNode HITL Evidence Builder (Art. 14)

```python
from lar.compliance import BranchTriageNode
from lar import RouterNode

# Place between BatchNode and RouterNode in fractal/parallel agent graphs.
# Parses branch outputs, flags CRITICAL, builds summary for jury context.
node_triage = BranchTriageNode(
    branch_output_keys=["safety_analysis", "efficacy_analysis", "regulatory_analysis"],
    risk_level_key="risk_level",      # JSON field in each branch output
    finding_key="finding",            # JSON field for the 1-sentence finding
    critical_threshold="CRITICAL",    # Set to "HIGH" to escalate earlier
    summary_state_key="branch_findings_summary",  # Include in HumanJuryNode context_keys
    critical_flag_key="branch_critical",          # RouterNode reads this key
    next_node=node_branch_router,
)

node_branch_router = RouterNode(
    decision_function=lambda s: "critical" if s.get("branch_critical") else "ok",
    path_map={
        "critical": node_jury_early,  # Fire HumanJuryNode BEFORE ReduceNode
        "ok":       node_reduce,      # All clear — proceed to consolidation
    },
)

# In the HumanJuryNode, include branch_findings_summary in context_keys:
jury = HumanJuryNode(
    ...
    context_keys=["risk_level", "recommendation", "branch_findings_summary"],
)
```

**Why this matters**: Without `BranchTriageNode`, a human approving a consolidated score has no visibility into which individual dimension triggered a HIGH or CRITICAL flag. The PI sees "MEDIUM overall" but safety said "CRITICAL". That is not meaningful oversight under Art. 14. `BranchTriageNode` preserves the evidence before `ReduceNode` compresses it away.

**Regulatory basis**: EU AI Act Art. 14 (human oversight must be meaningful); Art. 3(23) (runtime graph composition in fractal agents is a substantial modification candidate — each branch finding must be preserved for the conformity trail).

---

## Running Agents — Correct Executor API

```python
from lar import GraphExecutor, AuditLogger, TokenTracker
from rich.console import Console

executor = GraphExecutor(
    log_dir          = "lar_logs",
    offline_mode     = False,              # True = block all external calls (air-gap enforcement)
    user_id          = "user-123",         # Multi-tenant label on audit logs
    logger           = AuditLogger(
        log_dir     = "secure_logs",
        hmac_secret = "sk_prod_secret",   # HMAC-SHA256 signs every log file
    ),
    tracker          = TokenTracker(),
    hmac_secret      = "sk_prod_secret",
    max_node_fatigue = 20,                 # Max times any single node type can run (loop guard)
)

initial_state = {
    "user_query":   "What is deterministic AI?",
    "token_budget": 100_000,   # ALWAYS set — auto-deducted by every LLMNode call
}

# run_step_by_step() is a GENERATOR. It yields one step_log dict per node.
# The audit log is auto-saved to disk in the finally block.
history = []
for step_log in executor.run_step_by_step(
    start_node    = entry_node,
    initial_state = initial_state,
    max_steps     = 50,               # Circuit breaker — hard stop at N steps
):
    history.append(step_log)
    node_name   = step_log["node"]        # Class name of the node that just ran
    outcome     = step_log["outcome"]     # "success" or "error"
    diff        = step_log["state_diff"]  # What changed: {"added": {}, "updated": {}, "removed": {}}
    metadata    = step_log.get("run_metadata") or {}   # Token usage (None on non-LLM steps)
    tokens_used = metadata.get("total_tokens", 0)
    print(f"Step {step_log['step']:02d} | {node_name} | {outcome} | tokens: {tokens_used}")
```

**`step_log` dict schema:**
```python
{
    "step":         int,          # Step index
    "node":         str,          # Node class name
    "outcome":      str,          # "success" | "error"
    "state_before": dict,         # Full state snapshot before execution
    "state_after":  dict,         # Full state snapshot after execution
    "state_diff":   dict,         # {"added": {}, "updated": {}, "removed": {}}
    "run_metadata": dict | None,  # LLM token usage (None for non-LLM nodes)
    "error":        str | None,   # Error message if outcome == "error"
}
```

---

## Post-Run Utilities and Formatters

```python
from lar import compute_state_diff, apply_diff, build_log_table, summarize_diff
from rich.console import Console

# Audit table — returns a rich.Table object, MUST use Console().print(), not print()
Console().print(build_log_table(history))

# Diff summary string (contains Rich markup — strip if printing to plain stdout)
import re
raw = summarize_diff(diff)
clean = re.sub(r"\[/?[a-zA-Z_ ]+\]", "", str(raw))  # strip [green], [/green] etc.
print(clean)

# Round-trip utility: reconstruct state_after from state_before + diff
state_after_reconstructed = apply_diff(state_before, state_diff)

# Generate a diff manually between two state snapshots
diff = compute_state_diff(state_before_dict, state_after_dict)

# Token summary (from TokenTracker)
summary = tracker.get_summary()
# Keys: total_prompt_tokens, total_completion_tokens, total_tokens, tokens_by_model (dict)
```

---

## Executor Safety Mechanisms

| Mechanism | Config | Behaviour |
|---|---|---|
| **Token Budget** | `initial_state["token_budget"]` | `LLMNode` deducts usage each call. Execution stops when ≤ 0. |
| **Circuit Breaker** | `max_steps=N` in `run_step_by_step` | Hard stop after N total node executions. |
| **Node Fatigue** | `max_node_fatigue=N` in `GraphExecutor` | Stops if any single node class runs more than N times. |
| **Offline Mode** | `offline_mode=True` in `GraphExecutor` | Blocks external API calls at the executor level. |
| **TopologyValidator** | `DynamicNode(validator=...)` | Rejects LLM-generated subgraphs with cycles, unknown tools, or structural errors. |
| **HMAC Audit Log** | `hmac_secret=...` in `AuditLogger` | Every log file is HMAC-SHA256 signed. Tamper-evident. |

---

## Complete Minimal Example (End-to-End)

```python
from lar import (
    GraphState, AddValueNode, LLMNode, ToolNode, RouterNode,
    BatchNode, ReduceNode, ClearErrorNode, HumanJuryNode,
    GraphExecutor, AuditLogger, TokenTracker, node,
)
from rich.console import Console

# ── Tools ────────────────────────────────────────────────────────────────────
def word_count(text: str) -> dict:
    words = text.split()
    return {"word_count": len(words)}

# ── @node decorator ───────────────────────────────────────────────────────────
@node(output_key="clean_query")
def sanitise(state: GraphState) -> str:
    return state.get("raw_query", "").strip().lower()

# ── Graph (Forward Wiring) ────────────────────────────────────────────────────
seed = AddValueNode(key="token_budget", value=50_000, next_node=None)

# We use the @node decorator defined above, its next_node is wired later.
# sanitise is already defined

view_a = LLMNode(model_name="ollama/llama3.2",
                  prompt_template="Optimistic view of {clean_query}", output_key="view_a", next_node=None)
view_b = LLMNode(model_name="ollama/llama3.2",
                  prompt_template="Critical view of {clean_query}", output_key="view_b", next_node=None)

batch = BatchNode(nodes=[view_a, view_b], next_node=None)

reducer = ReduceNode(
    model_name="ollama/llama3.2",
    prompt_template="Merge: {view_a}\n{view_b}",
    input_keys=["view_a", "view_b"], output_key="synthesis", next_node=None,
)

jury = HumanJuryNode(
    prompt="Approve this synthesis?", choices=["approve", "reject"],
    output_key="verdict", context_keys=["synthesis"], next_node=None,
)

final = LLMNode(
    model_name="ollama/llama3.2",
    prompt_template="Write a report on: {synthesis}",
    output_key="report", next_node=None
)

# ── Wire the Graph Forward ────────────────────────────────────────────────────
seed.next_node = sanitise
sanitise.next_node = batch
batch.next_node = reducer
reducer.next_node = jury
jury.next_node = final

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    executor = GraphExecutor(
        logger=AuditLogger("logs", hmac_secret="dev_secret"),
        tracker=TokenTracker(),
        max_node_fatigue=15,
    )

    for step_log in executor.run_step_by_step(
        start_node=seed,
        initial_state={"raw_query": "deterministic AI in healthcare"},
        max_steps=30,
    ):
        metadata = step_log.get("run_metadata") or {}
        print(f"  [{step_log['step']:02d}] {step_log['node']} "
              f"| {step_log['outcome']} | {metadata.get('total_tokens', 0)} tokens")
```

---

## Common Mistakes to Avoid

| ❌ Wrong | ✅ Correct |
|---|---|
| `ClearErrorNode(error_key="error", next_node=x)` | `ClearErrorNode(next_node=x)` — no `error_key` arg |
| `for state, _ in executor.run(...)` | `for step_log in executor.run_step_by_step(...)` |
| `metadata.get(...)` without guard | `(step_log.get("run_metadata") or {}).get("total_tokens", 0)` |
| `print(build_log_table(history))` | `Console().print(build_log_table(history))` — Rich Table object |
| `normalise.next_node = x` before `x` exists | Use forward definition! Define `normalise` and `x` with `next_node=None`, then wire `normalise.next_node = x` later. |
| Using `gemini/gemini-1.5-pro` for local runs | Use `ollama/llama3.2` or `ollama/qwen2.5:14b` for local/air-gapped |
