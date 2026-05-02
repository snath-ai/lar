import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from lar import GraphExecutor, ToolNode, AddValueNode
from lar.compliance import CredentialVault

def call_api(url: str, **kwargs):
    # This tool simulates needing an API key from state
    return {"status": "Success, called API"}

vault = CredentialVault(logger_callback=lambda x: print(f"*** SYSTEM LOGGER CAUGHT NHI AUDIT: {x} ***"))
vault.register_credential("SECRET_API_KEY", "sk-123456789")

api_node = ToolNode(
    tool_function=call_api,
    input_keys=["api_url"],
    output_key="api_result",
    next_node=None,
    action_type="EXTERNAL_API",
    credential_vault=vault,
    credential_key="SECRET_API_KEY"
)

setup = AddValueNode("api_url", "https://example.com/api", api_node)

executor = GraphExecutor(offline_mode=True)
print("Running JIT Credential Vault Example...")
for step in executor.run_step_by_step(setup, {}):
    pass
