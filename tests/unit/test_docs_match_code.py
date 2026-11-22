"""Guards against documentation drift: documented step keys/outcomes must exist in the executor."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _scan():
    files = list((ROOT / "docs").rglob("*.md")) + list((ROOT / "examples").rglob("*.py")) + [ROOT / "README.md"]
    for f in files:
        if f.exists():
            yield f, f.read_text(errors="ignore")


def test_no_phantom_state_snapshot_key():
    # The executor yields "state_after"; "state_snapshot" never existed in a step log.
    bad = [str(f) for f, t in _scan() if re.search(r'\[\s*"state_snapshot"\s*\]|get\(\s*"state_snapshot"', t)]
    assert not bad, bad


def test_no_phantom_halted_outcome():
    # Step outcomes are pending/success/error. A pause is detected via the checkpoint store.
    bad = [str(f) for f, t in _scan() if re.search(r'outcome"?\]?\s*==\s*"halted"', t)]
    assert not bad, bad
