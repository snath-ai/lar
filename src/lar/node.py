import time
import copy
import json
import concurrent.futures
from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Any 
 
# --- Multi-Provider Imports ---
from litellm import completion, ModelResponse, utils
from litellm.exceptions import APIError
# ------------------------------
from .state import GraphState
from .utils import truncate_for_log

# --- The Core API "Contract" ---
class BaseNode(ABC):
    """
    This is the "master blueprint" or "contract" for all other nodes.
    It forces all other node classes to have an `execute` method.
    """
    
    def _validate_next_node(self, next_node: Optional['BaseNode'], param_name: str = "next_node") -> None:
        """
        Validates that next_node is either None or a BaseNode instance.
        
        Args:
            next_node: The node to validate
            param_name: Name of the parameter for error messages
            
        Raises:
            ValueError: If next_node is not None and not a BaseNode instance
        """
        if next_node is not None and not isinstance(next_node, BaseNode):
            raise ValueError(
                f"{param_name} must be a BaseNode instance or None, "
                f"got {type(next_node).__name__}"
            )
    
    @abstractmethod
    def execute(self, state: GraphState):
        """
        Executes the node's logic.
        Returns:
            BaseNode | None: The next node to execute, or None to stop.
        """
        pass

# --- Node Implementations (The "Lego Bricks") ---

class AddValueNode(BaseNode):
    """
    A utility node for adding or *copying* data into the state.
    """
    
    def __init__(self, key: str, value: any, next_node: BaseNode = None):
        # Validation
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        self._validate_next_node(next_node)
        
        self.key = key
        self.value = value
        self.next_node = next_node

    def execute(self, state: GraphState):
        value_to_set = self.value
        
        if isinstance(self.value, str) and self.value.startswith("{") and self.value.endswith("}"):
            key_to_copy = self.value.strip("{}")
            if state.get(key_to_copy) is not None:
                value_to_set = state.get(key_to_copy)
                print(f"  [AddValueNode]: Copying state['{key_to_copy}'] to state['{self.key}']")
            else:
             print(f"  [AddValueNode] WARN: Key '{key_to_copy}' not in state. Setting literal value.")
        else:
             print(f"  [AddValueNode]: Setting state['{self.key}'] = {truncate_for_log(value_to_set)}")

        state.set(self.key, value_to_set)
        return self.next_node

class LLMNode(BaseNode):
    """
    This is the agent's "brain." It supports multiple LLM providers (Gemini, OpenAI, Anthropic, etc.) 
     via the LiteLLM adapter for consistent usage, logging, and error handling.
    """
    # Class variable to store shared model configurations (caching)
    _model_cache: Dict[str, str] = {}
    
    def __init__(self, 
                 model_name: str, 
                 prompt_template: str, 
                 output_key: str, 
                 next_node: BaseNode = None,
                 max_retries: int = 3,
                 system_instruction: Optional[str] = None, 
                 generation_config: Optional[Dict[str, Any]] = None,
                 stream: bool = False,
                 response_format: Optional[Any] = None,
                 fallbacks: Optional[List[str]] = None,
                 caching: bool = False,
                 success_callbacks: Optional[List[str]] = None
                 ):
        """
        Initialize an LLM Execution Node.

        Args:
            model_name (str): The model identifier (e.g., "gpt-4", "gemini/gemini-1.5-flash").
            prompt_template (str): A string template using {variable} syntax for state substitution.
            output_key (str): The key in the GraphState where the result will be stored.
            next_node (BaseNode, optional): The next node to execute after this one.
            max_retries (int, optional): Number of times to retry on API errors. Defaults to 3.
            system_instruction (str, optional): System prompt to steer the model's behavior.
            generation_config (dict, optional): LiteLLM-specific parameters (temperature, max_tokens, etc).
            stream (bool): Stream output chunk-by-chunk to sys.stdout.
            response_format (type): Pydantic model for structured JSON output.
            
            # --- Enterprise --- 
            # These parameters hook directly into Snath Cloud infrastructure.
            # For managed failover, caching, and observability, see https://snath.ai/enterprise
            fallbacks (list): Backup models for auto-recovery.
            caching (bool): Enable semantic/exact match caching.
            success_callbacks (list): Observability dashboards (e.g., langfuse, datadog).
        """
        
        # Validation
        if not isinstance(model_name, str) or not model_name:
            raise ValueError("model_name must be a non-empty string")
        if not isinstance(prompt_template, str) or not prompt_template:
            raise ValueError("prompt_template must be a non-empty string")
        if not isinstance(output_key, str) or not output_key:
            raise ValueError("output_key must be a non-empty string")
        if not isinstance(max_retries, int) or max_retries < 1:
            raise ValueError("max_retries must be a positive integer")
        self._validate_next_node(next_node)
        
        # 1. Store configuration as instance variables
        self.model_name = model_name
        self.prompt_template = prompt_template
        self.output_key = output_key
        self.next_node = next_node
        self.max_retries = max_retries
        self.system_instruction = system_instruction
        self.generation_config_dict = generation_config or {}
        
        # --- Enterprise Configuration & Streaming Options ---
        self.stream = stream
        self.response_format = response_format
        self.fallbacks = fallbacks
        self.caching = caching
        self.success_callbacks = success_callbacks

        # 2. Check Cache Key (Identifies the unique model configuration)
        # The key includes model name and system instruction for unique caching
        
        # --- FIX: Google Provider Conflict Resolution ---
        # Problem: If the environment has GOOGLE_APPLICATION_CREDENTIALS (for Firestore),
        # LiteLLM defaults to using Vertex AI for Gemini models.
        # However, users often provide a GOOGLE_API_KEY expecting to use Google AI Studio.
        # This causes a "Vertex AI API disabled" error if the project doesn't have it enabled.
        #
        # Solution: We detect if GOOGLE_API_KEY is present. If so, we force the 'gemini/' prefix,
        # which tells LiteLLM to use the Google AI Studio provider instead of Vertex AI.
        import os
        if self.model_name.startswith("gemini") and "gemini/" not in self.model_name and "vertex_ai/" not in self.model_name:
            if os.environ.get("GOOGLE_API_KEY"):
                print(f"  [LLMNode]: Detected GOOGLE_API_KEY. Forcing AI Studio (gemini/) for model '{self.model_name}'...")
                self.model_name = f"gemini/{self.model_name}"

        cache_key = f"{self.model_name}:{self.system_instruction}" 
        
        # 3. Cache the model name for faster access (LiteLLM handles the actual client instantiation)
        if cache_key not in LLMNode._model_cache:
            print(f"  [LLMNode]: Caching new model configuration for {self.model_name}...")
            # We skip genai.configure() here; LiteLLM handles all key loading via environment variables.
            LLMNode._model_cache[cache_key] = self.model_name
        
        # 4. Assign the model identifier from the cache
        self.model_identifier = LLMNode._model_cache[cache_key]

    
    def execute(self, state: GraphState):
        # --- Token Budget Check (Economic Constraint) ---
        budget = state.get("token_budget")
        if budget is not None and budget <= 0:
            msg = f"Token budget exceeded (Remaining: {budget}). Halting execution."
            print(f"  [LLMNode] ERROR: {msg}")
            state.set("last_error", msg)
            return None # Stop executing or rely on error_node if implemented in future

        # 1. Build the prompt (the "contents")
        # Support both {var} and {{var}} syntax by normalizing double braces to single braces
        # This is user-friendly for those used to Jinja2/Mustache
        template = self.prompt_template.replace("{{", "{").replace("}}", "}")
        try:
            prompt = template.format(**state.get_all())
        except KeyError as e:
            # Fallback: If a key is missing, don't crash, just leave it as is or warn
            print(f"  [LLMNode] WARN: Missing key {e} for prompt template. Using raw template.")
            prompt = template

        print(f"  [LLMNode]: Sending prompt to {self.model_identifier}: {truncate_for_log(prompt)}")

        # --- Art. 12 Compliance: persist the full prompt & system instruction to state ---
        # The executor's state_diff will capture these, making the exact LLM call
        # reproducible by auditors without needing to re-run the agent.
        state.set("__last_prompt", prompt)
        if self.system_instruction:
            state.set("__last_system_instruction", self.system_instruction)

        retries = 0
        base_delay = 1
        
        # Prepare LiteLLM messages format (required for all chat-based models)
        messages = [{"role": "user", "content": prompt}]
        
        # Build LiteLLM optional parameters
        litellm_kwargs = self.generation_config_dict.copy()
        
        # Inject Enterprise & Structured Options
        if getattr(self, "response_format", None):
            litellm_kwargs["response_format"] = self.response_format
        if getattr(self, "fallbacks", None):
            litellm_kwargs["fallbacks"] = self.fallbacks
        if getattr(self, "caching", None):
            litellm_kwargs["caching"] = self.caching
        if getattr(self, "success_callbacks", None):
            litellm_kwargs["success_callbacks"] = self.success_callbacks

        if self.system_instruction:
             # LiteLLM handles system instructions by injecting a system message
             messages.insert(0, {"role": "system", "content": self.system_instruction})

        while retries < self.max_retries:
            try:
                if getattr(self, "stream", False):
                    # --- STREAMING EXECUTION PATH ---
                    import sys
                    stream_kwargs = litellm_kwargs.copy()
                    stream_kwargs["stream"] = True
                    stream_kwargs["stream_options"] = {"include_usage": True}
                    
                    response_gen = completion(
                        model=self.model_identifier, 
                        messages=messages,
                        **stream_kwargs
                    )
                    
                    llm_response_text = ""
                    usage_dict = None
                    reasoning = ""
                    
                    print(f"  [LLMNode]: Streaming response from {self.model_identifier}:\n  >> ", end="")
                    
                    for chunk in response_gen:
                        delta = chunk.choices[0].delta if getattr(chunk, "choices", None) else None
                        if delta:
                            content = getattr(delta, "content", None)
                            if content:
                                llm_response_text += content
                                sys.stdout.write(content)
                                sys.stdout.flush()
                                
                            reasoning_delta = getattr(delta, "reasoning_content", None)
                            if reasoning_delta:
                                reasoning += reasoning_delta
                        
                        chunk_usage = getattr(chunk, "usage", None)
                        if chunk_usage:
                            usage_dict = {
                                "prompt_tokens": chunk_usage.prompt_tokens,
                                "completion_tokens": chunk_usage.completion_tokens,
                            }

                    print("\n") # Formatting barrier after stream finishes
                    
                    if not llm_response_text:
                        raise ValueError("LLM streaming response was empty or blocked by safety filters.")
                        
                    # Mock Response object to seamlessly integrate with v1.6.0 parsing code below
                    class MockMessage:
                        def __init__(self, c, r):
                            self.content = c
                            self.reasoning_content = r
                    class MockChoice:
                        def __init__(self, msg):
                            self.message = msg
                    class MockUsage:
                        def __init__(self, p_t, c_t):
                            self.prompt_tokens = p_t
                            self.completion_tokens = c_t
                    class MockResponse:
                        def __init__(self, choices, usage):
                            self.choices = choices
                            self.usage = usage
                            
                    u_obj = MockUsage(usage_dict["prompt_tokens"], usage_dict["completion_tokens"]) if usage_dict else None
                    response = MockResponse([MockChoice(MockMessage(llm_response_text, reasoning if reasoning else None))], u_obj)

                else:
                    # --- SYNCHRONOUS EXECUTION PATH (V1.6.0 Logic) ---
                    # 2. Call the LiteLLM completion API
                    response = completion(
                        model=self.model_identifier, 
                        messages=messages,
                        **litellm_kwargs
                    )
                
                # 3. Extract the response text
                if not response.choices or not response.choices[0].message.content:
                    raise ValueError("LLM response was empty or blocked by safety filters.")
                
                llm_response_text = response.choices[0].message.content
                # Save the initial raw response to state (will be overwritten if reasoning trace exists)
                state.set(self.output_key, llm_response_text)
                
                # 4. Extract and Log Unified Metadata (CRITICAL for Glass Box)
                if response.usage:
                    # LiteLLM provides a unified usage object
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "output_tokens": response.usage.completion_tokens,
                        # FIX: Enforce correct total token sum for transparency
                        "total_tokens": response.usage.prompt_tokens + response.usage.completion_tokens, 
                        "model": self.model_identifier # Log the model used
                    }

                    # --- Reasoning Content Support (DeepSeek R1, o1, etc.) ---
                    # 1. Check for "reasoning_content" in the message object (Standard API)
                    reasoning = getattr(response.choices[0].message, "reasoning_content", None)
                    
                    # 2. Robust Regex Fallback (Handling malformed tags)
                    clean_answer = llm_response_text.strip() # Initialize with full text
                    if not reasoning: # Only attempt regex if not already found via standard API
                        import re
                        # Case A: Standard <think> content </think>
                        match = re.search(r"<think>(.*?)</think>", llm_response_text, flags=re.DOTALL)
                        if match:
                            reasoning = match.group(1).strip()
                            # Remove the thought block from the final answer
                            clean_answer = re.sub(r"<think>.*?</think>", "", llm_response_text, flags=re.DOTALL).strip()
                        
                        # Case B: Opening tag only (Model cutoff or ongoing thought)
                        elif "<think>" in llm_response_text:
                            parts = llm_response_text.split("<think>", 1)
                            # Everything after <think> is reasoning
                            reasoning = parts[1].strip()
                            # Everything before is the answer (usually empty, but safe to keep)
                            clean_answer = parts[0].strip()
                        
                        # Case C: Closing tag only (Model started thinking "internally" or hallucinated start)
                        elif "</think>" in llm_response_text:
                            parts = llm_response_text.split("</think>", 1)
                            # Everything before </think> is reasoning
                            reasoning = parts[0].strip()
                            # Everything after is the answer
                            clean_answer = parts[1].strip()
                        
                        # Case D: No reasoning tags -> clean_answer remains llm_response_text.strip()
                    
                    if reasoning:
                        usage["reasoning_content"] = reasoning
                        print(f"  [LLMNode]: Captured {len(reasoning)} chars of reasoning trace (Regex).")

                    # Set the (potentially cleaned) answer to the state
                    state.set(self.output_key, clean_answer)
                    print(f"  [LLMNode]: Saved response to state['{self.output_key}']")

                    state.set("__last_run_metadata", usage)
                    print(f"  [LLMNode]: Logged {usage['total_tokens']} tokens.")
                    
                    # --- Token Budget (Economic Constraint) ---
                    budget = state.get("token_budget")
                    if budget is not None:
                        new_budget = budget - usage['total_tokens']
                        state.set("token_budget", new_budget)
                        print(f"  [LLMNode]: Token Budget: {budget} -> {new_budget} remaining.")

                return self.next_node

            except APIError as e:
                # LiteLLM APIError handles rate limits (429) from ALL providers uniformly.
                if "429" in str(e):
                    retries += 1
                    print(f"  [LLMNode] WARN: Rate limit hit. (Attempt {retries}/{self.max_retries}). Retrying in {base_delay}s...")
                    time.sleep(base_delay)
                    base_delay *= 2
                else:
                    raise e
            
            except Exception as e:
                print(f"  [LLMNode] CRITICAL ERROR: {e}")
                raise e

        print(f"  [LLMNode] FATAL: Failed after {self.max_retries} retries.")
        raise APIError(f"LLMNode failed after {self.max_retries} retries.", status_code=429)

class RouterNode(BaseNode):
    """
    This is the agent's "if/else" statement or "choice" logic.
    """
    def __init__(self,
                 decision_function: Callable[[GraphState], str],
                 path_map: Dict[str, BaseNode],
                 default_node: BaseNode = None):
        """
        Initialize a Router (Switch) Node.

        Args:
            decision_function (Callable[[GraphState], str]): A function that takes the state and returns a string key.
            path_map (Dict[str, BaseNode]): A mapping of return keys to the respective Next Node.
            default_node (BaseNode, optional): Fallback node if the returned key is not in path_map.
        """
        # Validation
        if not callable(decision_function):
            raise ValueError("decision_function must be callable")
        if not isinstance(path_map, dict):
            raise ValueError("path_map must be a dictionary")
        if not path_map:
            raise ValueError("path_map cannot be empty")
        
        # Validate all path_map values are BaseNode instances
        for key, node in path_map.items():
            if not isinstance(key, str):
                raise ValueError(f"path_map keys must be strings, got {type(key).__name__}")
            if not isinstance(node, BaseNode):
                raise ValueError(
                    f"path_map[\"{key}\"] must be a BaseNode instance, "
                    f"got {type(node).__name__}"
                )
        
        self._validate_next_node(default_node, "default_node")
        
        self.decision_function = decision_function
        self.path_map = path_map
        self.default_node = default_node

    def execute(self, state: GraphState):
        route_key = self.decision_function(state)
        print(f"  [RouterNode]: Decision function returned '{route_key}'")
        
        # Log the decision to state so it appears in the diff
        state.set("_router_decision", route_key)
        
        next_node = self.path_map.get(route_key)

        if next_node:
            print(f"  [RouterNode]: Routing to {next_node.__class__.__name__}")
            return next_node
        elif self.default_node:
            print(f"  [RouterNode]: Route '{route_key}' not found. Using default path.")
            return self.default_node
        else:
            print(f"  [RouterNode] ERROR: Route '{route_key}' not found and no default path set.")
            return None

class ToolNode(BaseNode):
    """
    This is the agent's "hands." It runs any Python function.
    """
    def __init__(self,
                 tool_function: Callable,
                 input_keys: List[str],
                 output_key: str,
                 next_node: BaseNode,
                 error_node: BaseNode = None,
                 action_type: str = None,
                 credential_vault: Any = None,
                 credential_key: str = None,
                 affected_parties: str = "USER_ONLY",
                 transparency_engine: Any = None):
        """
        Initialize a Tool Execution Node.

        Args:
            tool_function (Callable): The Python function to execute.
            input_keys (List[str]): List of state keys to extract as positional arguments.
                Use ["__state__"] to pass the entire GraphState object.
            output_key (str): The state key to store the return value.
                If None, and the function returns a dict, the dict is merged into the state.
            next_node (BaseNode): The next node to execute on success.
            error_node (BaseNode, optional): The node to jump to if an exception occurs. To use this,
                check 'last_error' in the state.
        """
        
        # Validation
        if not callable(tool_function):
            raise ValueError("tool_function must be callable")
        if not isinstance(input_keys, list):
            raise ValueError("input_keys must be a list")
        for key in input_keys:
            if not isinstance(key, str):
                raise ValueError(f"input_keys must contain only strings, got {type(key).__name__}")
        if output_key is not None and not isinstance(output_key, str):
            raise ValueError("output_key must be a string or None")
        self._validate_next_node(next_node, "next_node")
        self._validate_next_node(error_node, "error_node")
        
        self.tool_function = tool_function
        self.input_keys = input_keys
        self.output_key = output_key
        self.next_node = next_node
        self.error_node = error_node
        self.action_type = action_type
        self.credential_vault = credential_vault
        self.credential_key = credential_key
        self.affected_parties = affected_parties
        self.transparency_engine = transparency_engine

    def execute(self, state: GraphState):
        try:
            func_name = getattr(self.tool_function, "__name__", str(self.tool_function))
            
            # --- COMPLIANCE: Credential Vault (JIT Provisioning) ---
            if self.credential_vault and self.credential_key:
                cred = self.credential_vault.get(tool_name=func_name, scope=self.action_type or "default", credential_key=self.credential_key)
                state.set(self.credential_key, cred)
                
            # --- COMPLIANCE: Transparency Engine ---
            if self.affected_parties in ["THIRD_PARTY", "BOTH"] and self.transparency_engine:
                self.transparency_engine.flag(
                    action_type=self.action_type or "unknown",
                    tool_name=func_name,
                    affected_description=f"Action '{self.action_type}' affects third parties."
                )

            # Special handling for full state access
            if self.input_keys == ["__state__"]:
                inputs = [state]
            else:
                inputs = [state.get(key) for key in self.input_keys]
            
            func_name = getattr(self.tool_function, "__name__", str(self.tool_function))
            
            # For clean logging, hide internal __ variables
            log_inputs = []
            for arg in inputs:
                if hasattr(arg, 'get_all'):
                    # It's a GraphState object
                    clean_state = {k: v for k, v in arg.get_all().items() if not k.startswith('__')}
                    log_inputs.append(f"GraphState({clean_state})")
                else:
                    log_inputs.append(arg)
                    
            print(f"  [ToolNode]: Running {func_name} with inputs: {truncate_for_log(log_inputs)}")
            result = self.tool_function(*inputs)
            
            # Special handling for merging dict results
            if self.output_key is None and isinstance(result, dict):
                print(f"  [ToolNode]: Merging result dict into state: {list(result.keys())}")
                for k, v in result.items():
                    state.set(k, v)
            elif self.output_key:
                state.set(self.output_key, result)
                print(f"  [ToolNode]: Saved result to state['{self.output_key}']")

            return self.next_node
        except Exception as e:
            func_name = getattr(self.tool_function, "__name__", str(self.tool_function))
            print(f"  [ToolNode] ERROR: {func_name} failed: {e}")
            state.set("last_error", str(e))
            if self.error_node:
                return self.error_node
            else:
                return None

class ClearErrorNode(BaseNode):
    """
    A simple "janitor" node. Its only job is to clean up
    the 'last_error' key from the state.
    """
    def __init__(self, next_node: BaseNode):
        # Validation
        if not isinstance(next_node, BaseNode):
            raise ValueError(f"next_node must be a BaseNode instance, got {type(next_node).__name__}")
        
        self.next_node = next_node

    def execute(self, state: GraphState):
        if state.get("last_error") is not None:
            print("  [ClearErrorNode]: Clearing 'last_error' from state.")
            state.set("last_error", None)
        return self.next_node

class BatchNode(BaseNode):
    """
    Executes a list of nodes in parallel using threads.
    Useful for Fan-Out patterns where branches are independent.
    Each node runs in its own thread with a *copy* of the state.
    Non-conflicting updates are merged back into the main state.
    """
    def __init__(self, nodes: List[BaseNode], next_node: BaseNode = None):
        """
        Args:
            nodes: List of nodes to execute in parallel.
            next_node: The single node to execute after all parallel nodes finish.
        """
        # Validation
        if not isinstance(nodes, list):
            raise ValueError("nodes must be a list")
        # Relaxed validation: Allow empty list for dynamic graph construction (lazy loading)
        # if not nodes:
        #    raise ValueError("nodes list cannot be empty")
        for i, node in enumerate(nodes):
            if not isinstance(node, BaseNode):
                raise ValueError(
                    f"nodes[{i}] must be a BaseNode instance, got {type(node).__name__}"
                )
        self._validate_next_node(next_node)
        
        self.nodes = nodes
        self.next_node = next_node

    def execute(self, state: GraphState):
        MAX_STEPS = 50
        MAX_WORKERS = min(32, len(self.nodes) + 4)
        print(f"  [BatchNode]: Starting parallel execution of {len(self.nodes)} nodes...")

        def run_node_safe(node, base_state_dict):
            local_state = GraphState(copy.deepcopy(base_state_dict))
            current_node = node
            steps = 0
            while current_node and steps < MAX_STEPS:
                current_node = current_node.execute(local_state)
                steps += 1
            if steps >= MAX_STEPS:
                print(f"  [BatchNode] WARN: Thread hit MAX_STEPS ({MAX_STEPS}). Potential infinite loop.")
            return local_state

        base_state_dict = state.get_all()
        base_budget = base_state_dict.get("token_budget")

        # Collect results in deterministic insertion order, not as_completed order
        ordered_results: List[tuple] = []
        failed_branches: List[str] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_node = {
                executor.submit(run_node_safe, node, base_state_dict): (i, node)
                for i, node in enumerate(self.nodes)
            }
            pending = {f: meta for f, meta in future_to_node.items()}
            for future in concurrent.futures.as_completed(pending):
                i, node = pending[future]
                node_name = getattr(node, "__name__", node.__class__.__name__)
                try:
                    ordered_results.append((i, future.result()))
                    print(f"  [BatchNode]: Branch {i} ({node_name}) completed.")
                except Exception as e:
                    failed_branches.append(node_name)
                    print(f"  [BatchNode] ERROR in branch {i} ({node_name}): {e}")

        if failed_branches:
            state.set("last_error", f"BatchNode: {len(failed_branches)} branch(es) failed: {failed_branches}")

        # Sort by original insertion order so merge is deterministic regardless of completion order
        ordered_results.sort(key=lambda x: x[0])
        local_states = [r for _, r in ordered_results]

        print(f"  [BatchNode]: Merging {len(local_states)} branch results (deterministic order)...")

        # First pass — detect conflicts across branches before writing anything
        seen: dict = {}
        conflicts: set = set()
        for local_state in local_states:
            for k, v in local_state.get_all().items():
                if k in ("token_budget", "last_error"):
                    continue
                if k not in base_state_dict or base_state_dict[k] != v:
                    if k in seen and seen[k] != v:
                        conflicts.add(k)
                    seen[k] = v

        if conflicts:
            print(f"  [BatchNode] WARN: Merge conflict on keys {conflicts} — first writer wins (branch 0 priority).")
            state.set("_batch_conflicts", list(conflicts))

        # Second pass — write in order; first writer wins on conflicts
        written: set = set()
        updates_count = 0
        total_budget_spent = 0

        for local_state in local_states:
            local_dict = local_state.get_all()

            if base_budget is not None and "token_budget" in local_dict:
                spent = base_budget - local_dict["token_budget"]
                if spent > 0:
                    total_budget_spent += spent

            for k, v in local_dict.items():
                if k in ("token_budget", "last_error"):
                    continue
                if k not in base_state_dict or base_state_dict[k] != v:
                    if k not in written:
                        state.set(k, v)
                        written.add(k)
                        updates_count += 1

        if base_budget is not None:
            new_budget = base_budget - total_budget_spent
            state.set("token_budget", new_budget)
            print(f"  [BatchNode]: Reconciled Token Budget: {base_budget} -> {new_budget} remaining.")

        print(f"  [BatchNode]: Merged {updates_count} updates. Conflicts: {len(conflicts)}. Failed branches: {len(failed_branches)}.")
        return self.next_node

class ReduceNode(LLMNode):
    """
    Memory Compression Node (Map-Reduce).
    Reads multiple keys from state, passes them to an LLM to generate a summary/extracted insight,
    saves the output, and explicitly deletes the raw data keys from the state to free up context window.
    """
    def __init__(self, 
                 model_name: str, 
                 prompt_template: str, 
                 input_keys: List[str], 
                 output_key: str, 
                 next_node: BaseNode = None,
                 **kwargs):
        super().__init__(model_name=model_name, prompt_template=prompt_template, output_key=output_key, next_node=next_node, **kwargs)
        if not isinstance(input_keys, list) or not input_keys:
            raise ValueError("input_keys must be a non-empty list of strings")
        self.input_keys = input_keys

    def execute(self, state: GraphState):
        # First, run the normal LLMNode execution (it will read the current state)
        next_n = super().execute(state)
        
        # Then, if successful (no last_error set by this step), explicitly delete the raw keys
        if not state.get("last_error"):
            print(f"  [ReduceNode]: Compressing memory: Deleting raw keys {self.input_keys}")
            for key in self.input_keys:
                state.delete(key)
                
        return next_n

class HumanJuryNode(BaseNode):
    """
    A blocking node that pauses execution to request Human-in-the-Loop feedback via the CLI.
    
    Satisfies:
      - EU AI Act Art. 14 (Human Oversight / Automation Boundary)
      - EU AI Act Art. 12 (Action-level Authority Record — Fourth Tier Governance)

    When an AuthorityLedger is attached, every human decision produces an immutable,
    timestamped, cryptographically-signable AuthorityRecord — the evidence chain that
    Articles 12-14 require and that the paper (Section 9, Finding 10) identifies as
    absent from all current governance tooling.
    """
    def __init__(self, 
                 prompt: str, 
                 choices: List[str], 
                 output_key: str, 
                 context_keys: List[str] = [],
                 next_node: BaseNode = None,
                 # --- Art. 12/14 Authority Record ---
                 authority_ledger: Optional[Any] = None,
                 stakeholder_id: str = "UNKNOWN",
                 stakeholder_role: str = "REVIEWER",
                 action_description: str = None,
                 risk_score_key: str = None):
        """
        Args:
            prompt: The question to ask the human stakeholder.
            choices: List of valid lowercase strings (e.g. ['approve', 'reject']).
            output_key: Where to store the human's choice in state.
            context_keys: Keys from state to display to the stakeholder for context.
            next_node: The next node to execute.
            authority_ledger: An AuthorityLedger instance. If provided, every decision
                is recorded with stakeholder identity, role, rationale, and timestamp.
                Required for full Art. 12/14 compliance under the paper's Finding (10).
            stakeholder_id: Email/ID of the human stakeholder (for the authority record).
            stakeholder_role: Job role/title of the stakeholder (e.g., 'CFO', 'Clinician').
            action_description: Description of the AI-proposed action under review.
                Defaults to the prompt text if not provided.
            risk_score_key: Optional state key containing the risk score from a
                RiskScorerNode, to include in the authority record for full evidence chain.
        """
        # Validation
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("prompt must be a non-empty string")
        if not isinstance(choices, list) or not choices:
            raise ValueError("choices must be a non-empty list")
        for choice in choices:
            if not isinstance(choice, str):
                raise ValueError(f"choices must contain only strings, got {type(choice).__name__}")
        if not isinstance(output_key, str) or not output_key:
            raise ValueError("output_key must be a non-empty string")
        if not isinstance(context_keys, list):
            raise ValueError("context_keys must be a list")
        self._validate_next_node(next_node)
        
        self.prompt = prompt
        self.choices = [c.lower() for c in choices]
        self.output_key = output_key
        self.context_keys = context_keys
        self.next_node = next_node
        # Authority Record fields
        self.authority_ledger = authority_ledger
        self.stakeholder_id = stakeholder_id
        self.stakeholder_role = stakeholder_role
        self.action_description = action_description or prompt
        self.risk_score_key = risk_score_key

    def execute(self, state: GraphState):
        print("\n" + "="*60)
        print("  [!] HUMAN JURY INTERVENTION REQUIRED")
        if self.authority_ledger:
            print(f"  [!] Stakeholder: {self.stakeholder_id} ({self.stakeholder_role})")
        print("="*60)
        
        # 1. Show Context
        if self.context_keys:
            print("CONTEXT:")
            for key in self.context_keys:
                val = state.get(key)
                if isinstance(val, (dict, list)):
                    val_str = json.dumps(val, indent=2)
                else:
                    val_str = str(val)
                print(f"  - {key}: {val_str}")
            print("-" * 60)
            
        # 2. Loop until valid input
        rationale = ""
        while True:
            user_input = input(f"{self.prompt} ({'/'.join(self.choices)}): ").strip().lower()
            if user_input in self.choices:
                print(f"  [HumanJuryNode]: Stakeholder selected '{user_input}'")
                state.set(self.output_key, user_input)
                # Capture rationale for authority record
                if self.authority_ledger:
                    rationale = input("  Rationale (required for compliance record): ").strip()
                    if not rationale:
                        rationale = f"No rationale provided. Decision: {user_input}."
                break
            else:
                print(f"  [HumanJuryNode]: Invalid input. Please type one of: {self.choices}")
                
        # 3. Write Authority Record to ledger (Art. 12/14 Fourth Tier)
        if self.authority_ledger:
            risk_score = None
            if self.risk_score_key:
                risk_score = state.get(self.risk_score_key)
            self.authority_ledger.record(
                action_description=self.action_description,
                stakeholder_id=self.stakeholder_id,
                stakeholder_role=self.stakeholder_role,
                decision=user_input,
                rationale=rationale,
                context_snapshot={k: state.get(k) for k in self.context_keys},
                risk_score=risk_score,
            )
                
        print("="*60 + "\n")
        return self.next_node

class FunctionalNode(BaseNode):
    """
    Wrapper for a simple function to act as a Node.
    Created via the @node decorator.
    """
    def __init__(self, func: Callable, output_key: str = None, next_node: BaseNode = None):
        if not callable(func):
            raise ValueError("func must be callable")
        
        self.func = func
        self.output_key = output_key
        self.next_node = next_node
        # Try to adopt the function's name and docs
        self.__name__ = getattr(func, "__name__", "anonymous_func")
        self.__doc__ = getattr(func, "__doc__", "")

    def execute(self, state: GraphState):
        func_name = getattr(self.func, "__name__", "anonymous_func")
        print(f"  [FunctionalNode]: Executing {func_name}...")
        
        # Pass state to the function
        # Expectation: function(state: GraphState) -> result
        result = self.func(state)
        
        if self.output_key:
            state.set(self.output_key, result)
            print(f"  [FunctionalNode]: Saved result to state['{self.output_key}']")
            
        return self.next_node

def node(output_key: str = None, next_node: BaseNode = None):
    """
    Decorator to convert a function into a Node instance.
    
    Usage:
    @node(output_key="summary")
    def summarize_text(state):
        return llm.generate(state.get("text"))
        
    # summarize_text is now a FunctionalNode instance
    """
    def decorator(func):
        return FunctionalNode(func, output_key=output_key, next_node=next_node)
    return decorator