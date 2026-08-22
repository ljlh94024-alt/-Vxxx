import json
import re
from typing import Any, Dict, List, Tuple


def extract_expected_keys(expected_output: str) -> List[str]:
    """
    Extract required keys from expected_output definition.
    Supports either JSON schema example string (e.g. '{"answer":"", "keywords":[]}')
    or comma-separated list of key names (e.g. 'answer, keywords').
    """
    if not expected_output or not expected_output.strip():
        return []

    text = expected_output.strip()

    # Try parsing as JSON example
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return list(data.keys())
    except Exception:
        pass

    # Extract keys using regex if in format of {"key": ...}
    key_matches = re.findall(r'"([a-zA-Z0-9_]+)"\s*:', text)
    if key_matches:
        return list(dict.fromkeys(key_matches))

    # Fallback to comma/space separated tokens
    tokens = re.split(r"[,;\s]+", text)
    cleaned = [t.strip().strip('"\'') for t in tokens if t.strip()]
    return cleaned


def validate_result(data: Any, expected_output: str = "") -> Tuple[bool, str]:
    """
    Validate that data is a valid dictionary and contains all required keys.
    Returns: (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, f"Result data must be a dict, got {type(data).__name__}"

    if not data:
        return False, "Result data dictionary is empty"

    required_keys = extract_expected_keys(expected_output)
    if not required_keys:
        return True, ""

    missing_keys = [k for k in required_keys if k not in data]
    if missing_keys:
        return False, f"Missing required keys: {', '.join(missing_keys)}"

    return True, ""
