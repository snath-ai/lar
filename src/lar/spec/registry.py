import json
import os
from typing import List, Dict, Optional, Any
from deepdiff import DeepDiff
from pydantic import BaseModel
from .spec import AgentManifest
from lar._security import safe_id

class AgentDelta(BaseModel):
    """
    Represents the difference between two agent versions.
    """
    added_nodes: List[str] = []
    removed_nodes: List[str] = []
    modified_nodes: Dict[str, Dict[str, Any]] = {} # node_id -> {field: change}
    metadata_changes: Dict[str, Any] = {}

class AgentRegistry:
    """
    Manages storage, retrieval, and comparison of agents.
    Currently uses a simple file-system based approach.
    """
    def __init__(self, storage_dir: str = "./agents"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_path(self, agent_id: str, version: str) -> str:
        safe_id(str(agent_id), "agent_id")
        safe_id(str(version), "version")
        return os.path.join(self.storage_dir, f"{agent_id}_v{version}.json")

    def save_agent(self, manifest: AgentManifest):
        """Saves an agent manifest to disk."""
        path = self._get_path(str(manifest.metadata.id), manifest.version_info.version)
        with open(path, "w") as f:
            f.write(manifest.model_dump_json(indent=2, by_alias=True))

    def load_agent(self, agent_id: str, version: str) -> Optional[AgentManifest]:
        """Loads an agent manifest from disk."""
        path = self._get_path(agent_id, version)
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            data = json.load(f)
        return AgentManifest(**data)

    def list_versions(self, agent_id: str) -> List[str]:
        """Lists all available versions for an agent ID."""
        versions = []
        safe_id(str(agent_id), "agent_id")
        prefix = f"{agent_id}_v"
        for filename in os.listdir(self.storage_dir):
            if filename.startswith(prefix) and filename.endswith(".json"):
                # Extract version: id_v1.0.0.json -> 1.0.0
                v_str = filename[len(prefix):-5]
                versions.append(v_str)
        return sorted(versions)

    def diff_agents(self, v1: AgentManifest, v2: AgentManifest) -> AgentDelta:
        """
        Calculates the delta between two agent versions.
        Focuses on Graph topology and Node configuration.
        """
        delta = AgentDelta()
        
        # 1. Map nodes by ID for easy lookup
        nodes_v1 = {n.id: n for n in v1.graph.nodes}
        nodes_v2 = {n.id: n for n in v2.graph.nodes}
        
        # 2. Detect Added/Removed Nodes
        delta.added_nodes = [nid for nid in nodes_v2 if nid not in nodes_v1]
        delta.removed_nodes = [nid for nid in nodes_v1 if nid not in nodes_v2]
        
        # 3. Detect Modified Nodes
        common_nodes = set(nodes_v1.keys()) & set(nodes_v2.keys())
        for nid in common_nodes:
            n1 = nodes_v1[nid]
            n2 = nodes_v2[nid]
            
            # Use DeepDiff to find changes in the node model
            # Exclude 'position' from diff logic as it's purely visual
            d1 = n1.model_dump(exclude={"position"})
            d2 = n2.model_dump(exclude={"position"})
            
            diff = DeepDiff(d1, d2, ignore_order=True)
            if diff:
                # Simplify diff output for the delta object
                changes = {}
                if 'values_changed' in diff:
                    for key, val in diff['values_changed'].items():
                        # Clean up DeepDiff key format: root['field'] -> field
                        clean_key = key.replace("root['", "").replace("']", "")
                        changes[clean_key] = {
                            "old": val['old_value'],
                            "new": val['new_value']
                        }
                delta.modified_nodes[nid] = changes

        # 4. Metadata Changes
        meta_diff = DeepDiff(v1.metadata.model_dump(), v2.metadata.model_dump(), ignore_order=True)
        if meta_diff:
             if 'values_changed' in meta_diff:
                    for key, val in meta_diff['values_changed'].items():
                        clean_key = key.replace("root['", "").replace("']", "")
                        delta.metadata_changes[clean_key] = {
                            "old": val['old_value'],
                            "new": val['new_value']
                        }

        return delta
