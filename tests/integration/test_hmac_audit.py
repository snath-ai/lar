import pytest
import os
import json
import hmac
import hashlib
from lar import GraphExecutor, FunctionalNode

@pytest.fixture
def clean_logs():
    log_dir = "test_hmac_logs"
    if os.path.exists(log_dir):
        for f in os.listdir(log_dir):
            os.remove(os.path.join(log_dir, f))
    else:
        os.makedirs(log_dir)
    yield log_dir
    # Cleanup after test
    if os.path.exists(log_dir):
        for f in os.listdir(log_dir):
            os.remove(os.path.join(log_dir, f))
        os.rmdir(log_dir)

def test_hmac_signing(clean_logs):
    log_dir = clean_logs
    
    # Setup standard graph
    def dummy_func(state: dict) -> dict:
        state["hmac_tested"] = True
        return state

    process = FunctionalNode(func=dummy_func)

    secret = "my_super_secret_key"
    executor = GraphExecutor(log_dir=log_dir, hmac_secret=secret)

    # Run
    for _ in executor.run_step_by_step(process, {}):
        pass

    # Find the log file
    files = os.listdir(log_dir)
    assert len(files) == 1
    log_file = os.path.join(log_dir, files[0])

    with open(log_file, "r") as f:
        log_data = json.load(f)

    # Verify signature exists
    assert "signature" in log_data
    saved_signature = log_data["signature"]

    # Manually compute signature to verify
    clean_payload = {k: v for k, v in log_data.items() if k != "signature"}
    payload_str = json.dumps(clean_payload, sort_keys=True, separators=(',', ':'))
    
    mac = hmac.new(
        key=secret.encode('utf-8'),
        msg=payload_str.encode('utf-8'),
        digestmod=hashlib.sha256,
    )
    computed_signature = mac.hexdigest()

    assert saved_signature == computed_signature, "Signatures do not match!"

    # Intentionally break the payload to ensure validation works
    broken_payload = clean_payload.copy()
    broken_payload["tampered"] = True

    broken_str = json.dumps(broken_payload, sort_keys=True, separators=(',', ':'))
    broken_mac = hmac.new(
        key=secret.encode('utf-8'),
        msg=broken_str.encode('utf-8'),
        digestmod=hashlib.sha256,
    )
    assert saved_signature != broken_mac.hexdigest(), "Broken payload should not match!"
