import random
import time
import os
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent / "lar" / "src"))
from lar import *

# ==============================================================================
# EXTREME PARALLEL SWARM STRESS TEST
# ==============================================================================
print("Building Extreme Parallel Swarm...")

class ParallelHierarchyBuilder:
    def __init__(self):
        self.node_count = 0

    def create_worker(self, id: str) -> BaseNode:
        self.node_count += 1
        
        def worker_task(total_completed: int) -> dict:
            time.sleep(0.01) 
            return {"total_completed": (total_completed or 0) + 1}

        return ToolNode(
            tool_function=worker_task,
            input_keys=["total_completed"],
            output_key=None,
            next_node=None
        )

    def create_manager(self, id: str, level: int, max_depth: int) -> BaseNode:
        self.node_count += 1
        
        if level >= max_depth:
            return self.create_worker(id)

        sub_1 = self.create_manager(f"{id}_1", level + 1, max_depth)
        sub_2 = self.create_manager(f"{id}_2", level + 1, max_depth)

        parallel_work = BatchNode(
            nodes=[sub_1, sub_2],
            next_node=None
        )
        
        def manager_logic(state: GraphState) -> str:
            strategy = state.get("strategy", "BLITZSCALING")
            if strategy == "AUSTERITY":
                return "EXECUTE" if random.random() > 0.5 else "PRUNE"
            return "EXECUTE"

        end_branch_node = FunctionalNode(func=lambda s: None, next_node=None)

        return RouterNode(
            decision_function=manager_logic,
            path_map={
                "EXECUTE": parallel_work,
                "PRUNE": end_branch_node
            },
            default_node=None
        )

builder = ParallelHierarchyBuilder()
# Max Depth 7 = 127 nodes. True parallel fan-out.
head_manager = builder.create_manager("VP", level=1, max_depth=7) 

ceo_node = LLMNode(
    model_name="ollama/phi4:latest",
    prompt_template="Output 'BLITZSCALING' or 'AUSTERITY'. Market: {market_condition}",
    output_key="strategy",
    next_node=head_manager
)

if __name__ == "__main__":
    executor = GraphExecutor()
    print(f"Built Parallel Swarm ({builder.node_count} nodes).")
    print("\n--- Running EXTREME SCENARIO: BLITZSCALING (True Parallelism) ---")
    
    start_time = time.time()
    initial_state = {"market_condition": "Booming", "total_completed": 0, "strategy": "BLITZSCALING"}
    
    step_count = 0
    work_count = 0
    
    for step in executor.run_step_by_step(ceo_node, initial_state):
        step_count += 1
        node = step.get('node', '')
        
        if "BatchNode" in node:
             print(f"  [Parallel] Fanning out and running batch execution...")
             
        diff = step.get("state_diff", {}).get("updated", {})
        if "total_completed" in diff:
             work_count = diff["total_completed"]
             
    duration = time.time() - start_time
    print(f"\nDone in {duration:.2f}s.")
    print(f"Total Main-Thread Steps : {step_count}")
    print(f"Nodes in Topology       : {builder.node_count}")
    print(f"Execution Latency       : {duration:.4f}s")
    print("\nStress Test Completed Successfully!")
