import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def format_tools_for_prompt(tools: List[Dict]) -> str:
    if not tools:
        return ""
    descriptions = []
    for i, tool in enumerate(tools, 1):
        func = tool.get("function", {})
        name = func.get("name", "")
        desc = func.get("description", "")
        params = func.get("parameters", {})
        func_desc = f"{i}. Function: {name}"
        if desc:
            func_desc += f"\n   Description: {desc}"
        if params:
            props = params.get("properties", {})
            required = params.get("required", [])
            if props:
                func_desc += "\n   Parameters:"
                for param_name, param_info in props.items():
                    param_type = param_info.get("type", "string")
                    param_desc = param_info.get("description", "")
                    is_required = param_name in required
                    req_marker = " (required)" if is_required else " (optional)"
                    func_desc += f"\n     - {param_name} ({param_type}){req_marker}"
                    if param_desc:
                        func_desc += f": {param_desc}"
        descriptions.append(func_desc)
    return "\n\n".join(descriptions)

# Additional functions remain unchanged
