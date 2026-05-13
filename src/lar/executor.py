import copy
import uuid
import datetime
from typing import Optional
from .node import BaseNode
from .state import GraphState
from .utils import compute_state_diff
from .logger import AuditLogger
from .tracker import TokenTracker
from .compliance.runtime_versioner import RuntimeStateVersioner


class SecurityError(Exception):
    """Raised when a security policy (like Air-Gap) is violated."""
    pass

class GraphExecutor:
    """
    The \"engine\" that runs a Lár graph.
    
    This is the core execution engine that runs nodes step-by-step,
    delegating logging to AuditLogger and token tracking to TokenTracker.
    """
    def __init__(self, 
                 log_dir: str = "lar_logs", 
                 offline_mode: bool = False, 
                 user_id: Optional[str] = None,
                 logger: Optional[AuditLogger] = None,
                 tracker: Optional[TokenTracker] = None,
                 hmac_secret: Optional[str] = None,
                 max_node_fatigue: int = 20,
                 versioner: Optional[RuntimeStateVersioner] = None):
        """
        Initialize the GraphExecutor.
        
        Args:
            log_dir (str): Directory for audit logs (used if logger not provided)
            user_id (str, optional): User identifier for multi-tenant systems
            logger (AuditLogger, optional): Custom logger instance. If None, creates default.
            tracker (TokenTracker, optional): Custom tracker instance. If None, creates default.
            hmac_secret (str, optional): Secret key for cryptographically signing the log.
        """
        self.offline_mode = offline_mode
        self.user_id = user_id
        
        # Use provided instances or create defaults
        self.logger = logger if logger is not None else AuditLogger(log_dir, hmac_secret=hmac_secret)
        self.tracker = tracker if tracker is not None else TokenTracker()
        self.max_node_fatigue = max_node_fatigue
        self.versioner = versioner

    def run_step_by_step(self, start_node: BaseNode, initial_state: dict, max_steps: int = 100):
        """
        Executes a graph step-by-step, yielding the history of each step as it completes.
        This generator pattern allows for real-time observability and \"Flight Recording\".

        Args:
            start_node (BaseNode): The entry point of the graph.
            initial_state (dict): The initial dictionary to populate the GraphState.
            max_steps (int, optional): Safety circuit breaker to prevent infinite loops. Defaults to 100.
        
        Yields:
            dict: An audit log entry containing:
                - step (int): Step index.
                - node (str): Class name of the executed node.
                - state_before (dict): Full state snapshot before execution.
                - state_diff (dict): What changed in this step (added/updated/removed).
                - run_metadata (dict): Token usage and model info.
                - outcome (str): \"success\" or \"error\".
        """
        state = GraphState(initial_state)
        current_node = start_node

        # Generate a unique ID for this run (UUIDv4)
        run_id = str(uuid.uuid4())
        
        # Clear logger history for this run
        self.logger.clear_history()
        self.tracker.reset()

        step_index = 0
        node_counts = {}
        try:
            while current_node is not None:
                node_name = current_node.__class__.__name__
                
                # --- NODE FATIGUE (Economic & Loop Constraint) ---
                node_counts[node_name] = node_counts.get(node_name, 0) + 1
                state.set("__node_counts", node_counts)
                
                state_before = copy.deepcopy(state.get_all())
                
                log_entry = {
                    # ... (same log structure)
                    "step": step_index,
                    "node": node_name,
                    "state_before": state_before,
                    "state_diff": {},
                    "run_metadata": {}, 
                    "outcome": "pending"
                }
                
                if node_counts[node_name] > self.max_node_fatigue:
                    msg = f"Maximum visits ({self.max_node_fatigue}) exceeded for {node_name}."
                    print(f"  [GraphExecutor] 🛑 FATIGUE TRIPPED: {msg}")
                    log_entry["outcome"] = "error"
                    log_entry["error"] = msg
                    self.logger.log_step(log_entry)
                    yield log_entry
                    break
                
                try:
                    # Execute the node
                    next_node = current_node.execute(state)
                    
                    # Check if the node set an error in the state (graceful error handling)
                    if state.get("last_error"):
                        log_entry["outcome"] = "error"
                        log_entry["error"] = state.get("last_error")
                    else:
                        log_entry["outcome"] = "success"
                    
                except Exception as e:
                    # Handle a critical error
                    print(f"  [GraphExecutor] CRITICAL ERROR in {node_name}: {e}")
                    log_entry["outcome"] = "error"
                    log_entry["error"] = str(e)
                    next_node = None 
                
                # Capture the state *after* the node runs
                state_after = copy.deepcopy(state.get_all())
                
                # Extract metadata and track tokens
                if "__last_run_metadata" in state_after:
                    metadata = state_after.pop("__last_run_metadata")
                    log_entry["run_metadata"] = metadata
                    
                    # Delegate token tracking
                    self.tracker.add_tokens(metadata)
                
                # Clear metadata from the actual state so it doesn't persist
                state.set("__last_run_metadata", None)

                # --- Art. 12 Compliance: capture rendered prompt & system instruction ---
                # These are set by LLMNode before the API call so they are always
                # present in state_after for any step that involved an LLM call.
                if "__last_prompt" in state_after:
                    log_entry["prompt"] = state_after.pop("__last_prompt")
                    state.set("__last_prompt", None)
                if "__last_system_instruction" in state_after:
                    log_entry["system_instruction"] = state_after.pop("__last_system_instruction")
                    state.set("__last_system_instruction", None)

                # --- COMPLIANCE: Causal Trace Logging (Art. 12) ---
                if "__reasoning_trace" in state_after:
                    trace = state_after.pop("__reasoning_trace")
                    log_entry["reasoning_trace"] = trace
                    state.set("__reasoning_trace", None)

                # Compute the diff (now on the *cleaned* state_after)
                state_diff = compute_state_diff(state_before, state_after)
                log_entry["state_diff"] = state_diff
                log_entry["state_after"] = state_after

                # --- COMPLIANCE: Runtime State Versioner (Drift Detection) ---
                if self.versioner and step_index % 10 == 0:
                    tool_catalogue = state.get("tool_catalogue", [])
                    schema_keys = list(state.get_all().keys())
                    policy_bindings = state.get("policy_bindings", {})
                    snap = self.versioner.snapshot(tool_catalogue, schema_keys, policy_bindings)
                    if "drift_report" in snap:
                        state.set("drift_flag", True)
                        state.set("drift_report", snap["drift_report"])

                # Delegate logging
                self.logger.log_step(log_entry)
                yield log_entry
                
                # Resume on the next call
                current_node = next_node
                step_index += 1
                
                # --- CIRCUIT BREAKER ---
                if step_index >= max_steps:
                    print(f"  [GraphExecutor]: CIRCUIT BREAKER TRIPPED: Exceeded {max_steps} steps.")
                    
                    # Log the termination event
                    final_log = {
                        "run_id": run_id,
                        "timestamp": datetime.datetime.now().isoformat(),
                        "step": step_index,
                        "node": "CIRCUIT_BREAKER",
                        "state_before": state_after,
                        "state_diff": {}, 
                        "run_metadata": {},
                        "outcome": "error",
                        "error": f"Max steps ({max_steps}) exceeded without reaching a stop condition."
                    }
                    self.logger.log_step(final_log)
                    yield final_log
                    break

        finally:
            # --- AUTO-SAVE LOG ON FINISH (OR INTERRUPT) ---
            summary = {
                "total_steps": step_index,
                **self.tracker.get_summary()  # Unpack token summary
            }
            # Only save if we actually ran something
            if step_index >= 0:
                self.logger.save_to_file(run_id, user_id=self.user_id, summary=summary)
