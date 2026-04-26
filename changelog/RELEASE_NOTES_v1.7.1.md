# Lár v1.7.1 Release Notes

## What's New

### 1. The Validation Suite (Kitchen Sink)
* **Complete Framework Exercises**: Added `examples/validation_suite/` containing robust `kitchen_sink` agents.
* **Kitchen Sink 1**: Verifies fallback dynamic subgraph handling.
* **Kitchen Sink 2**: Successfully maps complex DynamicNode LLM sub-graph generation using explicit prompt rails.
* **Kitchen Sink 3**: Implements explicit Adversarial Payload validation testing for `TopologyValidator`.

### 2. Minor Refactors & Fixes
* **DynamicNode**: Fixed schema parsing instructions to prevent 3B parameter models from hallucinating unapproved tools inside subgraphs.
