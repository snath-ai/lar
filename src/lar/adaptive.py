
import json
import logging
from typing import Dict, List, Optional, Any, Type
from .node import BaseNode, LLMNode, ToolNode, RouterNode, BatchNode
from .state import GraphState

# --- Safety/Validator ---

class SecurityError(Exception):
    """Raised when a validated subgraph injection violates safety policy."""
    pass

_SUPPORTED_NODE_TYPES = {"LLMNode", "ToolNode", "BatchNode", "AdaptiveNode", "DynamicNode"}


class TopologyValidator:
    """
    Static analysis for adaptive graphs.

    Enforces six invariants required for EU AI Act Art. 3(23) compliance
    (Substantial Modification control):

    1. No infinite loops — cycle detection via DFS.
    2. Tool allowlist — only pre-approved functions may be referenced.
    3. Structural integrity — all next_node references resolve.
    4. Node count ceiling — rejects oversized specs (resource exhaustion guard).
    5. BatchNode reference integrity — concurrent_nodes IDs must exist in spec.
    6. Supported types only — unknown node types are rejected, not silently skipped.

    Compliance tags: Art. 3(23), Art. 12 (Logging), Art. 9 (Risk Management)
    """
    def __init__(self, allowed_tools: List[callable] = None, max_nodes: int = 20):
        self.allowed_tools = {t.__name__: t for t in (allowed_tools or [])}
        self.max_nodes = max_nodes

    def validate(self, graph_spec: Dict[str, Any]) -> bool:
        """
        Validates the JSON GraphSpec.
        Raises SecurityError if any invariant is violated.
        """
        nodes = graph_spec.get("nodes", [])
        if not nodes:
            raise SecurityError("GraphSpec must contain at least one node.")

        # 0. Node count ceiling (resource exhaustion guard)
        if len(nodes) > self.max_nodes:
            raise SecurityError(
                f"GraphSpec has {len(nodes)} nodes, exceeding the limit of {self.max_nodes}. "
                f"Increase TopologyValidator(max_nodes=...) if intentional."
            )

        node_ids = {n["id"] for n in nodes}

        # 1. Supported types only — unknown types are rejected, not silently dropped
        for n in nodes:
            ntype = n.get("type")
            if ntype not in _SUPPORTED_NODE_TYPES:
                raise SecurityError(
                    f"Node '{n.get('id')}' has unsupported type '{ntype}'. "
                    f"Supported: {sorted(_SUPPORTED_NODE_TYPES)}"
                )

        # 2. Structural integrity — next pointers must resolve
        for n in nodes:
            nxt = n.get("next")
            if nxt and nxt != "__end__" and nxt not in node_ids:
                raise SecurityError(f"Node '{n.get('id')}' links to non-existent node '{nxt}'.")

        # 3. BatchNode reference integrity — concurrent_nodes must exist in spec
        for n in nodes:
            if n.get("type") == "BatchNode":
                for cid in n.get("concurrent_nodes", []):
                    if cid not in node_ids:
                        raise SecurityError(
                            f"BatchNode '{n.get('id')}' references non-existent "
                            f"concurrent node '{cid}'."
                        )

        # 4. Cycle Detection (DFS) — covers both next and concurrent_nodes edges
        adj = {n["id"]: [] for n in nodes}
        for n in nodes:
            nxt = n.get("next")
            if nxt and nxt in node_ids:
                adj[n["id"]].append(nxt)

            if n.get("type") == "RouterNode":
                for target_id in n.get("routes", {}).values():
                    if target_id in node_ids:
                        adj[n["id"]].append(target_id)

            if n.get("type") == "BatchNode":
                for cid in n.get("concurrent_nodes", []):
                    if cid in node_ids:
                        adj[n["id"]].append(cid)

        visited = set()
        path = set()

        def visit(node_id):
            visited.add(node_id)
            path.add(node_id)
            for neighbor in adj[node_id]:
                if neighbor not in visited:
                    if visit(neighbor):
                        return True
                elif neighbor in path:
                    return True
            path.remove(node_id)
            return False

        for n_id in node_ids:
            if n_id not in visited:
                if visit(n_id):
                    raise SecurityError(f"Infinite loop detected in subgraph involving node '{n_id}'.")

        # 5. Tool allowlist
        for n in nodes:
            if n.get("type") == "ToolNode":
                tool_name = n.get("tool_name")
                if not tool_name:
                    raise SecurityError(
                        f"ToolNode '{n.get('id')}' is missing required field 'tool_name'."
                    )
                if self.allowed_tools and tool_name not in self.allowed_tools:
                    raise SecurityError(f"Tool '{tool_name}' is not in the allowlist.")

        return True


# --- The Primitive ---

class AdaptiveNode(BaseNode):
    """
    Runtime graph composition primitive.

    Asks an LLM to produce a validated subgraph specification at execution time,
    passes it through TopologyValidator, instantiates the nodes, and injects the
    subgraph into the live execution path.

    The graph topology remains fully auditable: every generated spec is logged
    to the Causal Trace (Art. 12), every tool reference is checked against the
    allowlist (Art. 9), and every structural invariant (cycles, depth, dangling
    pointers) is enforced by TopologyValidator before injection.

    Use this when the *structure* of a processing step must be determined by the
    problem at hand — for example, allocating parallel workers proportional to
    query complexity, or dispatching to a domain-specific subgraph.

    Compliance tags: Art. 3(23) (Substantial Modification), Art. 12 (Logging),
                     Art. 9 (Risk Management), TopologyValidator required.
    """
    def __init__(self,
                 llm_model: str,
                 prompt_template: str,
                 validator: TopologyValidator,
                 next_node: BaseNode = None,
                 context_keys: Optional[List[str]] = None,
                 system_instruction: str = None,
                 max_depth: int = 3,
                 generation_config: Optional[Dict[str, Any]] = None):
        """
        Args:
            llm_model: Model to generate the graph JSON.
            prompt_template: Prompt requesting the JSON spec (must include schema instructions).
            validator: TopologyValidator instance — required for Art. 3(23) compliance.
            next_node: The node to resume after the injected subgraph completes.
            context_keys: State keys to pass to the LLM as context.
            system_instruction: System prompt for the graph-design LLM call.
            max_depth: Maximum recursive AdaptiveNode nesting depth. Children receive
                       max_depth - 1. When 0, the node falls through to next_node
                       instead of making an LLM call. Prevents unbounded recursion.
        """
        self.llm_node = LLMNode(
            model_name=llm_model,
            prompt_template=prompt_template,
            output_key="__graph_spec_json__",
            system_instruction=system_instruction or "You are a software architect. Output ONLY valid JSON representing a Lár Graph.",
            generation_config=generation_config or {},
        )
        self.validator = validator
        self.next_node = next_node
        self.context_keys = context_keys if context_keys is not None else []
        self.max_depth = max_depth
        self._generation_config = generation_config or {}

    def execute(self, state: GraphState):
        if self.max_depth <= 0:
            print("  [AdaptiveNode] DEPTH LIMIT reached — falling through to next_node.")
            return self.next_node

        print("\n" + "="*40)
        print(f"  [AdaptiveNode]: Composing validated subgraph (depth remaining: {self.max_depth})")
        print("="*40)

        # 1. Run LLM to get GraphSpec
        # We manually inject instructions into the prompt about the expected JSON format
        schema_instruction = (
            "\n\nOutput a JSON object with this structure:\n"
            "{\n"
            '  "nodes": [\n'
            '    {"id": "unique_id", "type": "LLMNode", "prompt": "...", "output_key": "result", "next": null}\n'
            '  ],\n'
            '  "entry_point": "unique_id"\n'
            "}\n"
            "Supported node types and their required fields:\n"
            "- LLMNode: 'prompt', 'output_key', 'next'\n"
            "- ToolNode: 'tool_name', 'input_keys' (array), 'output_key', 'next'\n"
            "- BatchNode: 'concurrent_nodes' (array of node ids), 'next'\n"
            "- AdaptiveNode: 'prompt', 'model' (optional), 'next'\n"
            "Use 'next': null to indicate the end of the subgraph (which will return to the main graph).\n"
        )

        # Inject context_keys if specified
        context_str = ""
        if self.context_keys:
            context_str = "\n\nAVAILABLE CONTEXT:\n"
            for k in self.context_keys:
                val = state.get(k, "<not found>")
                context_str += f"{k}: {val}\n"

        # We append the schema and context to the internal LLMNode's prompt template
        original_template = self.llm_node.prompt_template
        self.llm_node.prompt_template += context_str + schema_instruction

        # Execute the internal LLMNode to populate state["__graph_spec_json__"]
        self.llm_node.execute(state)

        # Restore template
        self.llm_node.prompt_template = original_template

        raw_json = state.get("__graph_spec_json__")
        # Clean markdown code blocks if present
        if "```json" in raw_json:
            raw_json = raw_json.split("```json")[1].split("```")[0]
        elif "```" in raw_json:
            raw_json = raw_json.split("```")[1].split("```")[0]

        try:
            spec = json.loads(raw_json.strip())
        except json.JSONDecodeError:
            print("  [AdaptiveNode] ERROR: LLM returned invalid JSON.")
            return self.next_node # Fallback: Skip adaptive step

        # 2. Validate (Art. 3(23) / Art. 9 guardrail)
        try:
            self.validator.validate(spec)
            print("  [TopologyValidator]: Graph Spec Verified.")
        except SecurityError as e:
            print(f"  [TopologyValidator] REJECTED: {e}")
            return self.next_node # Fallback

        # 3. Instantiate and Wire
        # We need a way to map spec "types" to actual classes and "tool_names" to functions.
        # This requires a factory context. For now, we assume simple LLMNode/ToolNode/RouterNode support.

        node_map: Dict[str, BaseNode] = {}

        # First Pass: Instantiate Nodes (without next_node pointers)
        nodes_data = spec.get("nodes", [])
        for n in nodes_data:
            nid = n["id"]
            ntype = n["type"]

            if ntype == "LLMNode":
                node_map[nid] = LLMNode(
                    model_name=n.get("model", self.llm_node.model_name), # Inherit model if not specified
                    prompt_template=n.get("prompt", ""),
                    output_key=n.get("output_key", "adaptive_out"),
                    next_node=None # Wired in Pass 2
                )
            elif ntype == "ToolNode":
                # We need the actual function from the validator's allowlist
                tname = n.get("tool_name")
                func = self.validator.allowed_tools.get(tname)
                if not func:
                    print(f"  [AdaptiveNode] Error: Tool '{tname}' not found in allowlist map.")
                    continue

                node_map[nid] = ToolNode(
                    tool_function=func,
                    input_keys=n.get("input_keys", []),
                    output_key=n.get("output_key"),
                    next_node=None # Wired in Pass 2
                )
            elif ntype == "BatchNode":
                node_map[nid] = BatchNode(
                    nodes=[], # Will be filled in Pass 2
                    next_node=None
                )
                # Store metadata to help wiring later
                node_map[nid]._pending_concurrent_ids = n.get("concurrent_nodes", [])
            elif ntype in ("AdaptiveNode", "DynamicNode"):
                # Recursive subgraph injection — inherits validator and decrements depth
                child_prompt = n.get("prompt", "Design a sub-graph.")

                node_map[nid] = AdaptiveNode(
                    llm_model=n.get("model", self.llm_node.model_name),
                    prompt_template=child_prompt,
                    validator=self.validator,
                    next_node=None,
                    max_depth=self.max_depth - 1,
                    generation_config=self._generation_config,
                )
            else:
                # TopologyValidator should have rejected this already.
                # If we reach here, validation was skipped — log and skip safely.
                print(f"  [AdaptiveNode] WARNING: Unsupported node type '{ntype}' for id '{nid}' — skipping. Run TopologyValidator first.")
                continue

        # Second Pass: Wire 'next_node' and 'BatchNode.nodes'
        for n in nodes_data:
            nid = n["id"]
            node_obj = node_map.get(nid)
            if not node_obj: continue

            # 2a. Wire 'next'
            next_id = n.get("next")
            if next_id:
                if next_id in node_map:
                    node_obj.next_node = node_map[next_id]
                else:
                    print(f"  [AdaptiveNode] Warning: Node '{nid}' points to unknown next '{next_id}'.")
            else:
                # If next is null/None, it flows to the AdaptiveNode's configured 'next_node' (Rejoining main graph)
                node_obj.next_node = self.next_node

            # 2b. Wire 'BatchNode' concurrent nodes
            if isinstance(node_obj, BatchNode) and hasattr(node_obj, "_pending_concurrent_ids"):
                concurrent_nodes = []
                for cid in node_obj._pending_concurrent_ids:
                    if cid in node_map:
                        concurrent_nodes.append(node_map[cid])
                    else:
                        print(f"  [AdaptiveNode] Warning: BatchNode '{nid}' includes unknown node '{cid}'.")
                node_obj.nodes = concurrent_nodes

        entry_id = spec.get("entry_point")
        entry_node = node_map.get(entry_id)

        if not entry_node:
            print(f"  [AdaptiveNode] Error: Entry point '{entry_id}' not found.")
            return self.next_node

        print(f"  [AdaptiveNode]: Injecting validated subgraph (Entry: {entry_id}, nodes: {len(node_map)})")
        return entry_node


# Deprecated alias — use AdaptiveNode. Will be removed in a future release.
def DynamicNode(*args, **kwargs):
    import warnings
    warnings.warn(
        "DynamicNode is deprecated. Use AdaptiveNode instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return AdaptiveNode(*args, **kwargs)
