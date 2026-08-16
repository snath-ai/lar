# Comparative Analysis: "Failures in the Black Box"

These scripts are **illustrative counter-examples**.

> **Note**: They are NOT feature-parity ports of the Lár examples. They are designed to demonstrate specific **failure modes** inherent to non-deterministic, LLM-driven architectures ("Black Boxes").

## Why they are different

As noted in our analysis:

1.  **Illustrative Purpose**: These scripts show *recursion limits*, *cost explosions*, and *agent mis-routing*.
2.  **Not Apples-to-Apples**: A true 1:1 match would require artificially constraining the standard frameworks to mimic Lár's rigid graph structure, which defeats the purpose of comparing "Agentic" vs "Deterministic" philosophies.
3.  **Behavioral Contrast**: The goal is to contrast the *default behavior* of a standard "Chat Loop" swarm vs. a Lár "Assembly Line" swarm.

## The Scripts

| Script | Lár Equivalent | Failure Mode Demonstrated |
| :--- | :--- | :--- |
| `autogen_langchain_crewai_vs_lar.py` | Benchmark Suite | Programmatic benchmark comparing **Prompt Injection (Art 15(5))**, **Cryptographic Audit Diffs (Art 12)**, **Retry Costs**, and **Deterministic Topology** across AutoGen, LangChain, CrewAI, and Lár. |
| `langchain_swarm_fail.py` | `examples/9_corporate_swarm.py` | Hits **RecursionLimit** at step 25. Shows inability to run long-running processes. |
| `langchain_firewall_cost.py` | `examples/10_security_firewall.py` | Shows **Cost Explosion** ($0.03 vs $0.00) because "Guardrails" are implemented as LLM calls, not code. |
| `langchain_tree_fail.py` | `examples/1_simple_triage.py` | Shows **Probabilistic Routing** failures where the agent "talks" instead of routing. |
