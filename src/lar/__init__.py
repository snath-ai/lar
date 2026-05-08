"""
Lár: A "Define-by-Run" Agentic Framework.

This file makes the core classes and utilities available for easy import
by any developer who runs `pip install lar-engine`.
"""
__version__ = "2.0.0"

# Import the core classes to the top level of the package
from .state import GraphState
from .node import (
    BaseNode,
    AddValueNode,
    LLMNode,
    RouterNode,
    ToolNode,
    ClearErrorNode,
    BatchNode,
    HumanJuryNode,
    FunctionalNode,
    ReduceNode,
    node
)
from .dynamic import AdaptiveNode, DynamicNode, TopologyValidator
from .executor import GraphExecutor
from .logger import AuditLogger
from .tracker import TokenTracker
from .utils import compute_state_diff, apply_diff
from .formatter import build_log_table, summarize_diff




# Define what happens when a user types `from lar import *`
# This is the "public API" of your framework.
__all__ = [
    # Core Components
    "GraphState",
    "GraphExecutor",
    "AuditLogger",
    "TokenTracker",
    
    # Node "Lego Bricks"
    "BaseNode",
    "AddValueNode",
    "LLMNode",
    "RouterNode",
    "ToolNode",
    "BatchNode", 
    "HumanJuryNode",
    "FunctionalNode",
    "ReduceNode",
    "node",
    "AdaptiveNode",
    "DynamicNode",  # Deprecated alias for AdaptiveNode
    "TopologyValidator",
    "ClearErrorNode",
    "__version__",
    
    # Utility Functions
    "compute_state_diff",
    "apply_diff",
    
    # Formatter Functions
    "build_log_table",
    "summarize_diff",


]

# that they are running the correct, new version.
print(f"\n---- Lár Engine v{__version__} Successfully Imported ------\n")