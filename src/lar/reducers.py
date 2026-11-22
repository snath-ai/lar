"""Ready-made BatchNode reducers: deterministic, order-independent ways to merge disagreeing branches."""
from typing import Any, Callable, List, Sequence


def worst_of(order: Sequence[str]) -> Callable[[List[Any]], Any]:
    """Pick the highest-ranked value, e.g. ``worst_of(["LOW", "MEDIUM", "HIGH", "CRITICAL"])``.
    A value not in ``order`` raises: an unknown risk label must not quietly win or lose."""
    rank = {v: i for i, v in enumerate(order)}

    def reduce(values: List[Any]) -> Any:
        unknown = [v for v in values if v not in rank]
        if unknown:
            raise ValueError(f"worst_of: unknown value(s) {unknown}; expected one of {list(order)}")
        return max(values, key=lambda v: rank[v])
    return reduce


def any_true(values: List[Any]) -> bool:
    """True if any branch says True (e.g. 'sanctions_hit')."""
    return any(bool(v) for v in values)


def all_true(values: List[Any]) -> bool:
    """True only if every branch says True (e.g. 'all checks passed')."""
    return all(bool(v) for v in values)
