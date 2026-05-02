import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from lar import GraphExecutor, ToolNode, AddValueNode
from lar.compliance import TransparencyEngine

def send_email(to: str, subject: str, body: str):
    return {"status": f"Sent email to {to}"}

transparency = TransparencyEngine(logger_callback=lambda x: print(f"*** SYSTEM LOGGER CAUGHT EVENT: {x} ***"))

email_node = ToolNode(
    tool_function=send_email,
    input_keys=["email_to", "email_subject", "email_body"],
    output_key="email_result",
    next_node=None,
    action_type="COMMUNICATION",
    affected_parties="THIRD_PARTY",
    transparency_engine=transparency
)

setup = AddValueNode("email_to", "thirdparty@example.com", 
    AddValueNode("email_subject", "Automated Notice", 
        AddValueNode("email_body", "This is an automated decision.", email_node)))

executor = GraphExecutor(offline_mode=True)
print("Running Transparency Disclosure Example...")
for step in executor.run_step_by_step(setup, {}):
    pass
