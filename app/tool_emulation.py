"""
Tool emulation module for models that don't support native tool calling.
Emulates tool_choice: "auto" by converting tools to prompts and parsing responses.
"""
import json
import re
import logging
import time
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


def format_tools_for_prompt(tools: List[Dict]) -> str:
    """Convert tools list to human-readable prompt description"""
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


def create_tool_selection_prompt(tools: List[Dict]) -> str:
    """Create system prompt for tool selection"""
    tools_description = format_tools_for_prompt(tools)
    
    prompt = f"""You are a helpful assistant with access to the following functions:

{tools_description}

When the user's request requires calling a function, you MUST respond with a JSON object in this exact format:
{{
  "reasoning": "brief explanation of why you need to call a function",
  "tool_calls": [
    {{
      "id": "call_abc123",
      "type": "function",
      "function": {{
        "name": "function_name",
        "arguments": "{{\\"param1\\": \\"value1\\", \\"param2\\": \\"value2\\"}}"
      }}
    }}
  ]
}}

IMPORTANT RULES:
- The "arguments" field must be a valid JSON string (escaped)
- If multiple functions are needed, include all in the "tool_calls" array
- If no function is needed, respond normally with regular text (not JSON)
- Always use the exact function names from the list above
- Include all required parameters in the arguments

Example for a single function call:
{{
  "reasoning": "User wants weather information",
  "tool_calls": [
    {{
      "id": "call_123",
      "type": "function",
      "function": {{
        "name": "get_weather",
        "arguments": "{{\\"location\\": \\"Moscow\\", \\"units\\": \\"celsius\\"}}"
      }}
    }}
  ]
}}"""
    
    return prompt


def extract_json_from_text(text: str) -> Optional[Dict]:
    """Extract JSON object from text response"""
    if not text:
        return None
    
    # Try to find JSON in code blocks first (most reliable)
    code_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    matches = re.finditer(code_block_pattern, text, re.DOTALL)
    for match in matches:
        try:
            json_str = match.group(1).strip()
            parsed = json.loads(json_str)
            if "tool_calls" in parsed:
                return parsed
        except (json.JSONDecodeError, AttributeError):
            continue
    
    # Try to find JSON object with tool_calls - look for opening brace before tool_calls
    # Find all positions of "tool_calls"
    tool_calls_positions = [m.start() for m in re.finditer(r'"tool_calls"', text)]
    
    for pos in tool_calls_positions:
        # Find the opening brace before this position
        start_pos = text.rfind('{', 0, pos)
        if start_pos == -1:
            continue
        
        # Find the matching closing brace
        brace_count = 0
        end_pos = start_pos
        for i in range(start_pos, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_pos = i + 1
                    break
        
        if end_pos > start_pos:
            try:
                json_str = text[start_pos:end_pos]
                parsed = json.loads(json_str)
                if "tool_calls" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
    
    # Fallback: try to find any JSON object that might contain tool_calls
    # Look for patterns like { ... "tool_calls": ... }
    json_pattern = r'\{[^{}]*"tool_calls"[^{}]*\}'
    # Try to expand to include nested braces
    for match in re.finditer(r'\{', text):
        start = match.start()
        brace_count = 0
        end = start
        
        for i in range(start, min(start + 5000, len(text))):  # Limit search
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        
        if end > start:
            try:
                json_str = text[start:end]
                if '"tool_calls"' in json_str:
                    parsed = json.loads(json_str)
                    if "tool_calls" in parsed:
                        return parsed
            except json.JSONDecodeError:
                continue
    
    return None


def _extract_one_tool_call_from_str(json_str: str) -> Optional[Dict]:
    """Find first complete JSON object in string and parse as {name, arguments}. Returns None on failure."""
    brace_start = json_str.find("{")
    if brace_start == -1:
        return None
    brace_count = 0
    brace_end = -1
    for i in range(brace_start, len(json_str)):
        if json_str[i] == "{":
            brace_count += 1
        elif json_str[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                brace_end = i + 1
                break
    if brace_end == -1:
        return None
    try:
        parsed = json.loads(json_str[brace_start:brace_end])
        name = parsed.get("name")
        arguments = parsed.get("arguments", {})
        if name:
            return {"name": name, "arguments": arguments}
    except (json.JSONDecodeError, AttributeError):
        pass
    return None


def extract_tool_calls_from_xml_tags(text: str) -> Optional[List[Dict]]:
    """
    Extract tool calls from <tool_call>...</tool_call> tags (OpenClaw/ChainKlawd format).
    Also handles truncated stream: if </tool_call> is missing but JSON after <tool_call> is complete, parse it.
    Each block contains JSON: {"name": "func_name", "arguments": {...}}
    """
    if not text or "<tool_call>" not in text:
        return None
    
    result = []
    pos = 0
    while True:
        start_tag = text.find("<tool_call>", pos)
        if start_tag == -1:
            break
        content_start = start_tag + len("<tool_call>")
        end_tag = text.find("</tool_call>", content_start)
        if end_tag == -1:
            # Truncated or stream ended before </tool_call> - try to parse JSON from content to end of text
            json_str = text[content_start:].strip()
            pos = len(text)
        else:
            json_str = text[content_start:end_tag].strip()
            pos = end_tag + len("</tool_call>")
        
        one = _extract_one_tool_call_from_str(json_str)
        if one:
            result.append(one)
        if end_tag == -1:
            break
    
    return result if result else None


def split_content_for_streaming(content: str, original_tools: List[Dict]) -> tuple:
    """
    Split content into reasoning (text to stream) and tool_calls (to emit as delta).
    Returns (reasoning_content, tool_calls_list or None).
    If tool_calls found: reasoning = content before the tool_calls block.
    If no tool_calls: reasoning = full content, tool_calls = None.
    """
    if not content:
        return ("", None)

    tool_calls = parse_tool_calls_from_response(content, original_tools)
    if not tool_calls:
        return (content, None)

    # Find where tool_calls block starts to extract reasoning
    # Try XML format first (simpler): <tool_call>...</tool_call>
    xml_start = content.find("<tool_call>")
    if xml_start >= 0:
        return (content[:xml_start].rstrip(), tool_calls)

    # Try JSON format: {"tool_calls": [...]}
    pos = content.find('"tool_calls"')
    if pos > 0:
        start = content.rfind('{', 0, pos)
        if start >= 0:
            return (content[:start].rstrip(), tool_calls)

    return (content, tool_calls)


def parse_tool_calls_from_response(response_content: str, original_tools: List[Dict]) -> Optional[List[Dict]]:
    """Parse tool calls from model response and format as OpenAI tool_calls.
    Supports:
    1. JSON with tool_calls array (emulation prompt format)
    2. <tool_call>{"name": "...", "arguments": {...}}</tool_call> (OpenClaw/ChainKlawd format)
    """
    if not response_content:
        return None
    
    # Get available function names for validation
    available_functions = {tool["function"]["name"] for tool in original_tools}
    tool_calls_data = None
    
    # Try JSON format first ({"tool_calls": [{"function": {...}}]})
    parsed_json = extract_json_from_text(response_content)
    if parsed_json:
        tool_calls_data = parsed_json.get("tool_calls", [])
    
    # Fallback: <tool_call>{"name": "...", "arguments": {...}}</tool_call> format
    if not tool_calls_data:
        xml_calls = extract_tool_calls_from_xml_tags(response_content)
        if xml_calls:
            tool_calls_data = [
                {"function": {"name": c["name"], "arguments": c["arguments"]}, "id": None}
                for c in xml_calls
            ]
    
    if not tool_calls_data:
        return None
    
    # Format as OpenAI tool_calls
    formatted_calls = []
    for i, call in enumerate(tool_calls_data):
        func_info = call.get("function", {})
        func_name = func_info.get("name", "")
        
        # Validate function name (warn but still include so client can handle)
        if available_functions and func_name not in available_functions:
            logger.debug(f"Function {func_name} not in available tools list, including anyway")
        
        # Get arguments (should be JSON string)
        arguments = func_info.get("arguments", "{}")
        if isinstance(arguments, str):
            # Try to parse to validate
            try:
                json.loads(arguments)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in arguments for {func_name}, using as-is")
        elif isinstance(arguments, dict):
            # Convert dict to JSON string
            arguments = json.dumps(arguments)
        
        call_id = call.get("id", f"call_{i}_{int(time.time() * 1000)}")
        
        formatted_calls.append({
            "id": call_id,
            "type": "function",
            "function": {
                "name": func_name,
                "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments)
            }
        })
    
    return formatted_calls if formatted_calls else None


def emulate_tool_choice_auto(body: Dict) -> Dict:
    """Emulate tool_choice: auto by converting tools to prompt instructions"""
    tools = body.get("tools", [])
    tool_choice = body.get("tool_choice")
    
    # Only emulate if tools are present
    if not tools:
        return body
    
    # Accept "auto" or None (None means default which is "auto")
    if tool_choice is not None and tool_choice != "auto":
        return body
    
    logger.info(f"Emulating tool_choice: auto for {len(tools)} tools")
    
    # Create modified request body (deep copy to avoid modifying original)
    import copy
    modified_body = copy.deepcopy(body)
    
    # Remove tools and tool_choice from request to model
    if "tool_choice" in modified_body:
        del modified_body["tool_choice"]
    if "tools" in modified_body:
        del modified_body["tools"]
    
    # Create system prompt with tool descriptions
    system_prompt = create_tool_selection_prompt(tools)
    
    # Add or update system message
    messages = modified_body.get("messages", []).copy()
    
    # Check if there's already a system message
    has_system = messages and messages[0].get("role") == "system"
    
    if has_system:
        # Prepend tool selection instructions to existing system message
        existing_system = messages[0].get("content", "")
        messages[0]["content"] = f"{system_prompt}\n\n{existing_system}"
    else:
        # Insert new system message at the beginning
        messages.insert(0, {
            "role": "system",
            "content": system_prompt
        })
    
    modified_body["messages"] = messages
    
    # Store original tools separately (not in body, will be passed separately)
    # Don't add _original_tools to body as it will be sent to API
    
    return modified_body


def process_response_with_tool_emulation(response: Dict, original_tools: Optional[List[Dict]] = None) -> Dict:
    """Process model response and add tool_calls if detected"""
    if not original_tools:
        # Try to get from response metadata
        original_tools = response.get("_original_tools")
    
    if not original_tools:
        return response
    
    # Get response content
    choices = response.get("choices", [])
    if not choices:
        return response
    
    message = choices[0].get("message", {})
    content = message.get("content", "")
    
    # Normalize: ML nodes (vLLM etc) may return content as array
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and "text" in block:
                parts.append(block["text"])
        content = "\n".join(parts) if parts else ""
    
    if not content:
        return response
    
    # Try to parse tool calls from response
    tool_calls = parse_tool_calls_from_response(content, original_tools)
    
    if tool_calls:
        tool_names = [tc["function"]["name"] for tc in tool_calls]
        content_preview = (content or "")[:250].replace("\n", " ")
        logger.info(f"Detected {len(tool_calls)} tool call(s): {tool_names} | content preview: {content_preview!r}")
        
        # Modify response to OpenAI format with tool_calls
        # content=None: OpenAI spec - when tool_calls present, content is null
        message["tool_calls"] = tool_calls
        message["content"] = None
        message["role"] = "assistant"
        
        # Update finish_reason
        choices[0]["finish_reason"] = "tool_calls"
    
    return response


async def process_stream_with_tool_emulation(
    stream,
    original_tools: List[Dict],
    chunk_callback=None
):
    """
    Process streaming response with tool emulation.
    Streams each event to the client immediately (so client gets data and does not timeout).
    Accumulates content for parsing; when [DONE] and tool_calls are found, appends a tool_calls chunk.
    Yields: raw bytes (SSE format).
    """
    total_content = ""
    first_chunk_data = None
    sse_line_buffer = ""

    async for chunk in stream:
        try:
            chunk_str = chunk.decode("utf-8")
        except Exception:
            yield chunk
            continue

        sse_line_buffer += chunk_str

        while "\n\n" in sse_line_buffer:
            event, sse_line_buffer = sse_line_buffer.split("\n\n", 1)
            event = event.strip()
            if not event.startswith("data: "):
                continue
            data_str = event[6:].strip()
            event_bytes = f"data: {data_str}\n\n".encode("utf-8")

            if data_str == "[DONE]":
                if chunk_callback:
                    chunk_callback(total_content)
                try:
                    reasoning, tool_calls = split_content_for_streaming(total_content, original_tools)
                except Exception as e:
                    logger.warning(f"[TOOL EMULATION STREAM] Parse error: {e}")
                    tool_calls = None

                if tool_calls:
                    logger.info(f"[TOOL EMULATION STREAM] Detected {len(tool_calls)} tool call(s)")
                    try:
                        base = first_chunk_data or {
                            "id": "chatcmpl-tool-emu",
                            "object": "chat.completion.chunk",
                            "choices": [{"index": 0, "delta": {}, "finish_reason": None}],
                        }
                        if first_chunk_data and "model" in first_chunk_data:
                            base["model"] = first_chunk_data["model"]
                        tc_deltas = [
                            {
                                "index": idx,
                                "id": tc.get("id") or f"call_{idx}_{int(time.time() * 1000)}",
                                "type": "function",
                                "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]},
                            }
                            for idx, tc in enumerate(tool_calls)
                        ]
                        tc_chunk = {
                            **base,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"tool_calls": tc_deltas},
                                    "finish_reason": "tool_calls",
                                }
                            ],
                        }
                        yield f"data: {json.dumps(tc_chunk)}\n\n".encode("utf-8")
                    except Exception as e:
                        logger.exception(f"[TOOL EMULATION STREAM] Re-emit error: {e}")
                yield event_bytes
                return

            try:
                chunk_data = json.loads(data_str)
                if first_chunk_data is None:
                    first_chunk_data = chunk_data
                choices = chunk_data.get("choices", [])
                delta = choices[0].get("delta", {}) if choices else {}
                if "content" in delta:
                    total_content += delta["content"]
            except (json.JSONDecodeError, IndexError, KeyError):
                pass

            yield event_bytes

    if chunk_callback:
        chunk_callback(total_content)

    # Stream ended without [DONE] - yield remainder as-is so client gets everything
    if sse_line_buffer:
        yield sse_line_buffer.encode("utf-8")

