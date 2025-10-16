#!/usr/bin/env python3
"""
End-to-End Test Script for Agentic Chat

This script tests the complete agentic chat flow including:
1. Agent proactively creates memories
2. Agent creates action items
3. Agent searches conversations
4. Agent provides contextual responses

Usage:
    python scripts/test_agentic_chat_e2e.py [--uid USER_ID] [--verbose]

Requirements:
    - Backend server must be running
    - MCP server must be accessible (uvx mcp-server-omi)
    - Test user must exist in database
"""

import argparse
import asyncio
import sys
import os
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.chat import Message, MessageType
from utils.llm.agentic_chat import execute_agentic_chat_stream


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 70}")
    print(f"{text}")
    print(f"{'=' * 70}{Colors.END}\n")


def print_test(test_name, passed=None, details=""):
    """Print test result"""
    if passed is None:
        # Test is running
        print(f"{Colors.CYAN}[TEST] {test_name}...{Colors.END}")
    elif passed:
        print(f"{Colors.GREEN}[PASS] {test_name}{Colors.END}")
        if details:
            print(f"       {details}")
    else:
        print(f"{Colors.RED}[FAIL] {test_name}{Colors.END}")
        if details:
            print(f"       {details}")


def print_agent_action(action):
    """Print agent tool call"""
    tool = action.get('tool', 'unknown')
    print(f"{Colors.YELLOW}[TOOL] {tool}{Colors.END}")
    if 'arguments' in action:
        args = action['arguments']
        for key, value in args.items():
            print(f"       {key}: {value}")


async def test_memory_creation(uid: str, verbose: bool = False):
    """
    Test 1: Agent proactively creates memory when user shares personal info
    """
    test_name = "Proactive Memory Creation"
    print_test(test_name)

    messages = [
        Message(
            id="test_mem_1",
            sender="human",
            type=MessageType.text,
            text="I love hiking and my favorite color is blue",
            created_at=datetime.now(timezone.utc)
        )
    ]

    callback_data = {}
    response_text = ""

    try:
        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            if chunk:
                token = chunk.replace("data: ", "").replace("__CRLF__", "\n")
                response_text += token
                if verbose:
                    print(token, end="", flush=True)

        if verbose:
            print()  # Newline after response

        # Check agent actions
        agent_actions = callback_data.get('agent_actions', [])
        tool_calls = [a.get('tool') for a in agent_actions]

        # Verify memory creation
        if 'create_memory' in tool_calls:
            print_test(test_name, True, f"Agent created {tool_calls.count('create_memory')} memory/memories")
            if verbose:
                for action in agent_actions:
                    if action.get('tool') == 'create_memory':
                        print_agent_action(action)
            return True
        else:
            print_test(test_name, False, "Agent did not create memory")
            return False

    except Exception as e:
        print_test(test_name, False, f"Error: {str(e)}")
        return False


async def test_action_item_creation(uid: str, verbose: bool = False):
    """
    Test 2: Agent creates action item when user mentions task
    """
    test_name = "Action Item Extraction"
    print_test(test_name)

    messages = [
        Message(
            id="test_action_1",
            sender="human",
            type=MessageType.text,
            text="I need to call John tomorrow at 3pm and send the report to Sarah",
            created_at=datetime.now(timezone.utc)
        )
    ]

    callback_data = {}
    response_text = ""

    try:
        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            if chunk:
                token = chunk.replace("data: ", "").replace("__CRLF__", "\n")
                response_text += token
                if verbose:
                    print(token, end="", flush=True)

        if verbose:
            print()

        agent_actions = callback_data.get('agent_actions', [])
        tool_calls = [a.get('tool') for a in agent_actions]

        if 'create_action_item' in tool_calls:
            count = tool_calls.count('create_action_item')
            print_test(test_name, True, f"Agent created {count} action item(s)")
            if verbose:
                for action in agent_actions:
                    if action.get('tool') == 'create_action_item':
                        print_agent_action(action)
            return True
        else:
            print_test(test_name, False, "Agent did not create action item")
            return False

    except Exception as e:
        print_test(test_name, False, f"Error: {str(e)}")
        return False


async def test_conversation_search(uid: str, verbose: bool = False):
    """
    Test 3: Agent searches conversations when answering questions
    """
    test_name = "Conversation Search"
    print_test(test_name)

    messages = [
        Message(
            id="test_search_1",
            sender="human",
            type=MessageType.text,
            text="What did I discuss with Sarah last week?",
            created_at=datetime.now(timezone.utc)
        )
    ]

    callback_data = {}
    response_text = ""

    try:
        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            if chunk:
                token = chunk.replace("data: ", "").replace("__CRLF__", "\n")
                response_text += token
                if verbose:
                    print(token, end="", flush=True)

        if verbose:
            print()

        agent_actions = callback_data.get('agent_actions', [])
        tool_calls = [a.get('tool') for a in agent_actions]

        if 'search_conversations' in tool_calls:
            print_test(test_name, True, "Agent searched conversations")
            if verbose:
                for action in agent_actions:
                    if action.get('tool') == 'search_conversations':
                        print_agent_action(action)
            return True
        else:
            print_test(test_name, False, "Agent did not search conversations")
            return False

    except Exception as e:
        print_test(test_name, False, f"Error: {str(e)}")
        return False


async def test_memory_retrieval(uid: str, verbose: bool = False):
    """
    Test 4: Agent retrieves memories to provide context
    """
    test_name = "Memory Retrieval"
    print_test(test_name)

    messages = [
        Message(
            id="test_mem_retrieve_1",
            sender="human",
            type=MessageType.text,
            text="What do you know about my hobbies and preferences?",
            created_at=datetime.now(timezone.utc)
        )
    ]

    callback_data = {}
    response_text = ""

    try:
        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            if chunk:
                token = chunk.replace("data: ", "").replace("__CRLF__", "\n")
                response_text += token
                if verbose:
                    print(token, end="", flush=True)

        if verbose:
            print()

        agent_actions = callback_data.get('agent_actions', [])
        tool_calls = [a.get('tool') for a in agent_actions]

        if 'search_memories' in tool_calls or 'get_user_context' in tool_calls:
            print_test(test_name, True, "Agent retrieved user context/memories")
            if verbose:
                for action in agent_actions:
                    if action.get('tool') in ['search_memories', 'get_user_context']:
                        print_agent_action(action)
            return True
        else:
            print_test(test_name, False, "Agent did not retrieve memories")
            return False

    except Exception as e:
        print_test(test_name, False, f"Error: {str(e)}")
        return False


async def test_multi_turn_conversation(uid: str, verbose: bool = False):
    """
    Test 5: Agent maintains context across multiple turns
    """
    test_name = "Multi-turn Context"
    print_test(test_name)

    messages = [
        Message(
            id="test_multi_1",
            sender="human",
            type=MessageType.text,
            text="I love Python programming",
            created_at=datetime.now(timezone.utc)
        ),
        Message(
            id="test_multi_2",
            sender="ai",
            type=MessageType.text,
            text="That's great! I'll remember that you love Python programming.",
            created_at=datetime.now(timezone.utc)
        ),
        Message(
            id="test_multi_3",
            sender="human",
            type=MessageType.text,
            text="What programming languages do I know?",
            created_at=datetime.now(timezone.utc)
        )
    ]

    callback_data = {}
    response_text = ""

    try:
        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            if chunk:
                token = chunk.replace("data: ", "").replace("__CRLF__", "\n")
                response_text += token
                if verbose:
                    print(token, end="", flush=True)

        if verbose:
            print()

        response = callback_data.get('answer', '')

        # Check if response mentions Python
        if 'python' in response.lower():
            print_test(test_name, True, "Agent maintained context across turns")
            return True
        else:
            print_test(test_name, False, "Agent lost context")
            return False

    except Exception as e:
        print_test(test_name, False, f"Error: {str(e)}")
        return False


async def test_graceful_fallback(uid: str, verbose: bool = False):
    """
    Test 6: Agent handles questions without tools gracefully
    """
    test_name = "Graceful Fallback (No Tools)"
    print_test(test_name)

    messages = [
        Message(
            id="test_fallback_1",
            sender="human",
            type=MessageType.text,
            text="What's the capital of France?",
            created_at=datetime.now(timezone.utc)
        )
    ]

    callback_data = {}
    response_text = ""

    try:
        async for chunk in execute_agentic_chat_stream(uid, messages, callback_data=callback_data):
            if chunk:
                token = chunk.replace("data: ", "").replace("__CRLF__", "\n")
                response_text += token
                if verbose:
                    print(token, end="", flush=True)

        if verbose:
            print()

        response = callback_data.get('answer', '')

        # Should respond even without tool calls
        if response and len(response) > 10:
            print_test(test_name, True, "Agent responded without tools")
            return True
        else:
            print_test(test_name, False, "Agent failed to respond")
            return False

    except Exception as e:
        print_test(test_name, False, f"Error: {str(e)}")
        return False


async def run_all_tests(uid: str, verbose: bool = False):
    """Run all E2E tests"""
    print_header("AGENTIC CHAT END-TO-END TESTS")
    print(f"Testing with UID: {uid}")
    print(f"Verbose: {verbose}\n")

    results = []

    # Run tests sequentially
    results.append(("Memory Creation", await test_memory_creation(uid, verbose)))
    results.append(("Action Item Creation", await test_action_item_creation(uid, verbose)))
    results.append(("Conversation Search", await test_conversation_search(uid, verbose)))
    results.append(("Memory Retrieval", await test_memory_retrieval(uid, verbose)))
    results.append(("Multi-turn Context", await test_multi_turn_conversation(uid, verbose)))
    results.append(("Graceful Fallback", await test_graceful_fallback(uid, verbose)))

    # Print summary
    print_header("TEST SUMMARY")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = f"{Colors.GREEN}✓{Colors.END}" if result else f"{Colors.RED}✗{Colors.END}"
        print(f"{status} {test_name}")

    print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.END}")

    if passed == total:
        print(f"{Colors.GREEN}All tests passed! 🎉{Colors.END}\n")
        return 0
    else:
        print(f"{Colors.RED}Some tests failed. Please review.{Colors.END}\n")
        return 1


def main():
    parser = argparse.ArgumentParser(description="E2E tests for agentic chat")
    parser.add_argument(
        '--uid',
        type=str,
        default='test_user_e2e',
        help='User ID for testing (default: test_user_e2e)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show full agent responses and tool calls'
    )

    args = parser.parse_args()

    # Run tests
    exit_code = asyncio.run(run_all_tests(args.uid, args.verbose))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
