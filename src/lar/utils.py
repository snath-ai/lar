import json

def compute_state_diff(before: dict, after: dict) -> dict:
    """
    Calculates the diff between two state dictionaries.
    Returns a dictionary with "added", "removed", and "modified" keys.
    """
    diff = {"added": {}, "removed": {}, "updated": {}}
    all_keys = set(before.keys()) | set(after.keys())
    
    for key in all_keys:
        if key not in before:
            diff["added"][key] = after[key]
        elif key not in after:
            diff["removed"][key] = before[key]
        else:
            try:
                are_equal = bool(before[key] == after[key])
            except Exception:
                are_equal = False

            if not are_equal:
                # Use JSON dumps for a more robust comparison of complex types
                try:
                    before_json = json.dumps(before[key], sort_keys=True)
                    after_json = json.dumps(after[key], sort_keys=True)
                    
                    if before_json != after_json:
                        diff["updated"][key] = after[key]
                except TypeError:
                    # Fallback for non-serializable objects
                    diff["updated"][key] = after[key]
            
    return diff

# Diff Function
def apply_diff(state: dict, diff: dict) -> dict:
    """
    Applies a 'state_diff' object to a state dictionary
    to reconstruct the 'state_after'.
    """
    # Start with a copy of the old state
    new_state = state.copy()
    
    # Apply all changes from the diff
    # Apply all changes from the diff
    for key in diff.get("removed", {}):
        new_state.pop(key, None)
    for key, value in diff.get("added", {}).items():
        new_state[key] = value
    
    # FIX: Changed "modified" to "updated" to match frontend (RunPanel.tsx) expectations
    # and consistency with compute_state_diff
    for key, value in diff.get("updated", {}).items():
        new_state[key] = value 
    return new_state

def truncate_for_log(data: any, max_length: int = 500) -> str:
    """
    Safely stringifies and truncates data for console logging.
    Preserves type hints in the output string (e.g., '<dict with 5 keys>').
    """
    if data is None:
        return "None"
    
    if isinstance(data, (dict, list)):
        try:
            # Try pretty printing first
            text = json.dumps(data, indent=2)
        except (TypeError, OverflowError):
            text = str(data)
    else:
        text = str(data)
        
    if len(text) <= max_length:
        return text
    
    # Create a helpful truncated string
    suffix = f"... [truncated, total len: {len(text)} chars]"
    preview_len = max_length - len(suffix)
    if preview_len < 0: 
        # Fallback if max_length is absurdly small
        return text[:max_length] + "..."
        
    return text[:preview_len] + suffix
