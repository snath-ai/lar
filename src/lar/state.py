# src/lar/state.py

class GraphState:
    """
    A simple class to manage and pass state between nodes.
    It's a wrapper around a Python dictionary.
    """
    def __init__(self, initial_state: dict = None):
        """
        Initializes the state.
        
        Args:
            initial_state (dict, optional): A dictionary of initial data.
        """
        self._state = initial_state or {}
        # How many times each key has been written through set(). The executor uses this to tell a
        # NEW error from a stale ``last_error`` left over from an earlier, already-handled step.
        self._set_counts: dict = {}

    def set(self, key: str, value: any):
        """Sets a key-value pair in the state."""
        self._state[key] = value
        self._set_counts[key] = self._set_counts.get(key, 0) + 1

    def set_count(self, key: str) -> int:
        """Number of writes to ``key`` through set()/state[key]=... since this state was created."""
        return self._set_counts.get(key, 0)

    def __setitem__(self, key: str, value: any):
        """Allows state['key'] = value syntax."""
        self.set(key, value)

    def __getitem__(self, key: str):
        """Allows value = state['key'] syntax."""
        return self._state[key]

    def delete(self, key: str):
        """Deletes a key from the state if it exists."""
        if key in self._state:
            del self._state[key]

    def get(self, key: str, default: any = None):
        """
        Gets a value from the state by its key.
        
        Args:
            key (str): The key to retrieve.
            default (any, optional): The value to return if the key is not found.
        
        Returns:
            any: The value from the state, or the default value.
        """
        return self._state.get(key, default)

    def get_all(self) -> dict:
        """Returns a copy of the entire state dictionary."""
        return self._state.copy()

    def __repr__(self):
        """Provides a clean string representation for logging."""
        return f"GraphState({self._state})"