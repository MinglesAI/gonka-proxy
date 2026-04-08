#!/usr/bin/env python3
"""
Test script for tool emulation functionality
Tests the emulation of tool_choice: "auto" for models that don't support native tool calling
"""
import sys
import os
import json

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.tool_emulation import (
    format_tools_for_prompt,
    create_tool_selection_prompt,
    extract_json_from_text,
    extract_tool_calls_from_xml_tags,
    parse_tool_calls_from_response,
    emulate_tool_choice_auto,
    process_response_with_tool_emulation
)


def test_format_tools_for_prompt():
    """Test formatting tools into prompt description"""
    print("=" * 50)
    print("Test 1: Format Tools for Prompt")
    print("=" * 50)
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name"
                        },
                        "units": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Temperature units"
                        }
                    },
                    "required": ["location"]
                }
            }
        }
    ]
    
    result = format_tools_for_prompt(tools)
    
    if "get_weather" not in result:
        print("✗ Function name not found in prompt")
        return False
    
    if "Get current weather" not in result:
        print("✗ Function description not found")
        return False
    
    if "location" not in result:
        print("✗ Parameter not found")
        return False
    
    print("✓ Tools formatted correctly")
    print(f"Prompt preview: {result[:100]}...")
    print("✓ Test 1 passed!\n")
    return True


def test_create_tool_selection_prompt():
    """Test creation of tool selection prompt"""
    print("=" * 50)
    print("Test 2: Create Tool Selection Prompt")
    print("=" * 50)
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Perform calculation",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "Math expression"}
                    },
                    "required": ["expression"]
                }
            }
        }
    ]
    
    prompt = create_tool_selection_prompt(tools)
    
    if "calculate" not in prompt:
        print("✗ Function name not in prompt")
        return False
    
    if "tool_calls" not in prompt:
        print("✗ tool_calls format not in prompt")
        return False
    
    if "JSON" not in prompt:
        print("✗ JSON format instruction not in prompt")
        return False
    
    print("✓ Tool selection prompt created correctly")
    print("✓ Test 2 passed!\n")
    return True


def test_extract_json_from_text():
    """Test JSON extraction from text"""
    print("=" * 50)
    print("Test 3: Extract JSON from Text")
    print("=" * 50)
    
    # Test 1: Simple JSON
    text1 = 'Here is the response: {"tool_calls": [{"id": "call_1", "function": {"name": "test"}}]}'
    result1 = extract_json_from_text(text1)
    if not result1 or "tool_calls" not in result1:
        print("✗ Failed to extract simple JSON")
        return False
    print("✓ Simple JSON extracted")
    
    # Test 2: JSON in code block
    text2 = '```json\n{"tool_calls": [{"id": "call_2"}]}\n```'
    result2 = extract_json_from_text(text2)
    if not result2 or "tool_calls" not in result2:
        print("✗ Failed to extract JSON from code block")
        return False
    print("✓ JSON from code block extracted")
    
    # Test 3: No JSON
    text3 = "Just regular text without JSON"
    result3 = extract_json_from_text(text3)
    if result3 is not None:
        print("✗ Should return None for text without JSON")
        return False
    print("✓ Correctly returns None for text without JSON")
    
    print("✓ Test 3 passed!\n")
    return True


def test_parse_tool_calls_from_response():
    """Test parsing tool calls from response"""
    print("=" * 50)
    print("Test 4: Parse Tool Calls from Response")
    print("=" * 50)
    
    original_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather"
            }
        },
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Calculate"
            }
        }
    ]
    
    # Test 1: Valid JSON response
    response1 = '''{
  "reasoning": "User wants weather",
  "tool_calls": [
    {
      "id": "call_123",
      "type": "function",
      "function": {
        "name": "get_weather",
        "arguments": "{\\"location\\": \\"Moscow\\"}"
      }
    }
  ]
}'''
    
    result1 = parse_tool_calls_from_response(response1, original_tools)
    if not result1:
        print("✗ Failed to parse valid tool calls")
        return False
    
    if len(result1) != 1:
        print(f"✗ Expected 1 tool call, got {len(result1)}")
        return False
    
    if result1[0]["function"]["name"] != "get_weather":
        print("✗ Wrong function name")
        return False
    
    print("✓ Valid tool calls parsed correctly")
    
    # Test 2: Invalid function name
    response2 = '''{
  "tool_calls": [
    {
      "id": "call_456",
      "function": {
        "name": "unknown_function",
        "arguments": "{}"
      }
    }
  ]
}'''
    
    result2 = parse_tool_calls_from_response(response2, original_tools)
    if result2 and len(result2) > 0:
        print("✗ Should skip invalid function names")
        return False
    
    print("✓ Invalid function names correctly skipped")
    
    # Test 3: No tool calls
    response3 = "Just a regular text response"
    result3 = parse_tool_calls_from_response(response3, original_tools)
    if result3 is not None:
        print("✗ Should return None when no tool calls found")
        return False
    
    print("✓ Correctly returns None when no tool calls")
    
    # Test 4: OpenClaw/ChainKlawd <tool_call> format
    response4 = '''I'll check the file.
<tool_call>
{"name": "read", "arguments": {"path": "/root/.openclaw/workspace/BOOTSTRAP.md"}}
</tool_call>'''
    original_tools_read = [{"type": "function", "function": {"name": "read", "description": "Read file"}}]
    result4 = parse_tool_calls_from_response(response4, original_tools_read)
    if not result4 or len(result4) != 1:
        print(f"✗ Failed to parse <tool_call> format, got {result4}")
        return False
    if result4[0]["function"]["name"] != "read":
        print(f"✗ Wrong function name: {result4[0]['function']['name']}")
        return False
    args = json.loads(result4[0]["function"]["arguments"])
    if args.get("path") != "/root/.openclaw/workspace/BOOTSTRAP.md":
        print(f"✗ Wrong arguments: {args}")
        return False
    print("✓ <tool_call> format parsed correctly")
    
    print("✓ Test 4 passed!\n")
    return True


def test_emulate_tool_choice_auto():
    """Test emulation of tool_choice: auto"""
    print("=" * 50)
    print("Test 5: Emulate Tool Choice Auto")
    print("=" * 50)
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "test_func",
                "description": "Test function"
            }
        }
    ]
    
    body = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "Hello"}],
        "tool_choice": "auto",
        "tools": tools
    }
    
    result = emulate_tool_choice_auto(body)
    
    # Check that tool_choice and tools are removed
    if "tool_choice" in result:
        print("✗ tool_choice not removed")
        return False
    
    if "tools" in result:
        print("✗ tools not removed")
        return False
    
    # Check that system message is added
    messages = result.get("messages", [])
    if not messages or messages[0].get("role") != "system":
        print("✗ System message not added")
        return False
    
    # Check that system message contains tool descriptions
    system_content = messages[0].get("content", "")
    if "test_func" not in system_content:
        print("✗ Tool description not in system message")
        return False
    
    if "tool_calls" not in system_content:
        print("✗ Tool calls format not in system message")
        return False
    
    print("✓ Tool choice emulation works correctly")
    print("✓ Test 5 passed!\n")
    return True


def test_emulate_without_tools():
    """Test that emulation doesn't modify request without tools"""
    print("=" * 50)
    print("Test 6: Emulate Without Tools")
    print("=" * 50)
    
    body = {
        "model": "test-model",
        "messages": [{"role": "user", "content": "Hello"}]
    }
    
    result = emulate_tool_choice_auto(body)
    
    if result != body:
        print("✗ Request modified when no tools present")
        return False
    
    print("✓ Request unchanged when no tools")
    print("✓ Test 6 passed!\n")
    return True


def test_process_response_with_tool_emulation():
    """Test processing response with tool emulation"""
    print("=" * 50)
    print("Test 7: Process Response with Tool Emulation")
    print("=" * 50)
    
    original_tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather"
            }
        }
    ]
    
    # Test 1: Response with tool calls
    response1 = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": '''{
  "tool_calls": [
    {
      "id": "call_1",
      "function": {
        "name": "get_weather",
        "arguments": "{\\"location\\": \\"Paris\\"}"
      }
    }
  ]
}'''
            }
        }]
    }
    
    result1 = process_response_with_tool_emulation(response1, original_tools)
    
    message = result1["choices"][0]["message"]
    if "tool_calls" not in message:
        print("✗ tool_calls not added to response")
        return False
    
    if message.get("content") is not None:
        print("✗ content should be None when tool_calls present")
        return False
    
    if len(message["tool_calls"]) != 1:
        print(f"✗ Expected 1 tool call, got {len(message['tool_calls'])}")
        return False
    
    print("✓ Response processed correctly with tool calls")
    
    # Test 2: Response without tool calls
    response2 = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Just a regular response"
            }
        }]
    }
    
    result2 = process_response_with_tool_emulation(response2, original_tools)
    
    if "tool_calls" in result2["choices"][0]["message"]:
        print("✗ tool_calls should not be added when not present")
        return False
    
    print("✓ Response unchanged when no tool calls")
    print("✓ Test 7 passed!\n")
    return True


def run_all_tests():
    """Run all tool emulation tests"""
    print("\n" + "=" * 50)
    print("Testing Tool Emulation Functionality")
    print("=" * 50 + "\n")
    
    tests = [
        test_format_tools_for_prompt,
        test_create_tool_selection_prompt,
        test_extract_json_from_text,
        test_parse_tool_calls_from_response,
        test_emulate_tool_choice_auto,
        test_emulate_without_tools,
        test_process_response_with_tool_emulation
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} raised exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("=" * 50)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 50)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)


