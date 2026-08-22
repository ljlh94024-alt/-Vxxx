import re
import json
from typing import Any, Dict, Optional, Tuple


def extract_json_text(raw_text: str) -> Optional[str]:
    """Extract candidate JSON text from markdown blocks or outer curly braces."""
    if not raw_text or not raw_text.strip():
        return None

    text = raw_text.strip()

    # Match ```json ... ``` or ``` ... ```
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    matches = fence_pattern.findall(text)
    for match in matches:
        match_trimmed = match.strip()
        if match_trimmed.startswith("{") and match_trimmed.endswith("}"):
            return match_trimmed

    # Find the outermost balanced JSON object { ... }
    start_idx = text.find("{")
    if start_idx == -1:
        return None

    # Track brace balance to accurately locate the closing brace
    brace_count = 0
    in_string = False
    escape = False

    for i in range(start_idx, len(text)):
        char = text[i]
        if char == '"' and not escape:
            in_string = not in_string
        elif not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[start_idx : i + 1]

        if char == '\\' and not escape:
            escape = True
        else:
            escape = False

    return None


def parse_response(raw_text: str) -> Tuple[bool, Dict[str, Any], str]:
    """
    Parse raw response string into a structured JSON dict.
    Returns: (is_success, parsed_dict, error_message)
    """
    json_candidate = extract_json_text(raw_text)
    if not json_candidate:
        return False, {}, "No JSON object found in response"

    try:
        data = json.loads(json_candidate)
        if isinstance(data, dict):
            return True, data, ""
        return False, {}, f"Parsed JSON root is not an object: {type(data).__name__}"
    except Exception as e:
        return False, {}, f"JSON decoding failed: {str(e)}"
