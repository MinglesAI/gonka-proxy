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
    
    assert "get_weather" in result, "Function name not found in prompt"
    assert "Get current weather" in result, "Function description not found"
    assert "location" in result, "Parameter not found"
    
    print("✓ Tools formatted correctly")
    print(f"Prompt preview: {result[:100]}...")
    print("✓ Test 1 passed!\n")
    

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
    
    assert "calculate" in prompt, "Function name not in prompt"
    assert "tool_calls" in prompt, "tool_calls format not in prompt"
    assert "JSON" in prompt, "JSON format instruction not in prompt"
    
    print("✓ Tool selection prompt created correctly")
    print("✓ Test 2 passed!\n")
    return True


def test_extract_json_from_text():
    """Test JSON extraction from text"""
    print("=" * 50)
    print("Test 3: Extract JSON from Text")
    print("=" * 50)
    
    text1 = 'Here is the response: {"tool_calls": [{"id": "call_1", "function": {"name": "test"}}]}'
    result1 = extract_json_from_text(text1)
    assert result1 and "tool_calls" in result1, "Failed to extract simple JSON"
    print("✓ Simple JSON extracted")
    
    text2 = '```json\n{"tool_calls": [{"id": "call_2"}]}```'
    result2 = extract_json_from_text(text2)
    assert result2 and "tool_calls" in result2, "Failed to extract JSON from code block"
    print("✓ JSON from code block extracted")
    
    text3 = "Just regular text without JSON"
    result3 = extract_json_from_text(text3)
    assert result3 is None, "Should return None for text without JSON"
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
    
    response1 = '''{"reasoning": "User wants weather","tool_calls": [{"id": "call_123","type": "function","function": {"name": "get_weather","arguments": "{\\\"location\\\": \\\"Moscow\\\"}"}}]}'''  
    
    result1 = parse_tool_calls_from_response(json.loads(response1), original_tools)
    assert result1, "Failed to parse valid tool calls"
    assert len(result1) == 1, f"Expected 1 tool call, got {len(result1)}"
    assert result1[0]["function"]["name"] == "get_weather", "Wrong function name"
    print("✓ Valid tool calls parsed correctly")
    
    response2 = '''{"tool_calls": [{"id": "call_456","function": {"name": "unknown_function","arguments": "{}"}}]}'''   
    result2 = parse_tool_calls_from_response(json.loads(response2), original_tools)
    assert result2 is None, "Should skip invalid function names"
    print("✓ Invalid function names correctly skipped")
    
    response3 = {"content": "Just a regular text response"}
    result3 = parse_tool_calls_from_response(response3, original_tools)
    assert result3 is None, "Should return None when no tool calls found"
    print("✓ Correctly returns None when no tool calls")
    
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
    
    assert "tool_choice" not in result, "tool_choice not removed"
    assert "tools" not in result, "tools not removed"
    assert len(result.get("messages", [])) > 0
    assert result["messages"][0].get("role") == "system", "System message not added"
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
    
    assert result == body, "Request modified when no tools present"
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
        "arguments": "{\\\"location\\\": \\\"Paris\\\"}"
      }
    }
  ]
}'''
            }
        }]
    }
    
    result1 = process_response_with_tool_emulation(response1, original_tools)
    
    message = result1["choices"][0]["message"]
    assert "tool_calls" in message, "tool_calls not added to response"
    assert message.get("content") is None, "content should be None when tool_calls present"
    assert len(message["tool_calls"]) == 1, f"Expected 1 tool call, got {len(message['tool_calls'])}"
    print("✓ Response processed correctly with tool calls")
    
    response2 = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Just a regular response"
            }
        }]
    }
    
    result2 = process_response_with_tool_emulation(response2, original_tools)
    assert "tool_calls" not in result2["choices"][0]["message"], "tool_calls should not be added when not present"
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
