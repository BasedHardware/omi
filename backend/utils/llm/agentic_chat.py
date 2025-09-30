"""
Agentic Chat Implementation using OpenAI Agents SDK + MCP Server

This module implements the agentic chat system that can:
- Dynamically call tools to search conversations, create memories, manage action items
- Proactively handle user requests with reasoning
- Maintain consistent memory-driven interactions
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, List, Optional

from agents import Agent, ModelSettings, Runner
from agents.mcp import MCPServerStdio
from agents.model_settings import Reasoning

import database.users as users_db
from models.app import App
from models.chat import ChatSession, Message
from utils.llm.memory import get_prompt_memories
from utils.retrieval.graph import AsyncStreamingCallback


async def execute_agentic_chat_stream(
    uid: str,
    messages: List[Message],
    app: Optional[App] = None,
    chat_session: Optional[ChatSession] = None,
    callback_data: dict = None,
) -> AsyncGenerator[str, None]:
    """
    Execute agentic chat with streaming responses

    Args:
        uid: User ID
        messages: Conversation history
        app: Optional app/plugin configuration
        chat_session: Optional chat session context
        callback_data: Dict to store results (answer, memories_found, ask_for_nps, agent_actions)

    Yields:
        Streaming response chunks as "data: {token}" or None when complete
    """
    if callback_data is None:
        callback_data = {}

    # Get user context
    user_name, memories_str = get_prompt_memories(uid)
    user_profile = users_db.get_user(uid)
    timezone_str = user_profile.get('timezone', 'UTC') if user_profile else 'UTC'

    # Build system prompt based on context
    system_prompt = _build_system_prompt(user_name, memories_str, timezone_str, app)

    # Convert messages to agent format
    agent_messages = _convert_messages_to_agent_format(messages)

    # Initialize streaming callback
    callback = AsyncStreamingCallback()

    try:
        # Connect to MCP server and run agent
        async with MCPServerStdio(
            cache_tools_list=True,
            params={
                "command": "uvx",
                "args": ["mcp-server-omi", "-v"],
                "env": {"UID": uid}  # Pass user ID to MCP server
            }
        ) as mcp_server:

            # Create agent with MCP tools
            omi_agent = Agent(
                name="Omi Agent",
                instructions=system_prompt,
                mcp_servers=[mcp_server],
                model=os.environ.get("AGENT_MODEL", "o4-mini"),
                model_settings=ModelSettings(
                    reasoning=Reasoning(
                        effort=os.environ.get("AGENT_REASONING_EFFORT", "high"),
                        summary="auto"
                    ),
                    temperature=0.7,
                )
            )

            # Start agent execution
            task = asyncio.create_task(
                _run_agent_with_streaming(
                    omi_agent,
                    agent_messages,
                    callback,
                    callback_data
                )
            )

            # Stream response tokens to client
            while True:
                try:
                    chunk = await callback.queue.get()
                    if chunk:
                        # Remove "data: " prefix if present
                        if isinstance(chunk, str) and chunk.startswith("data: "):
                            chunk = chunk[len("data: "):]
                        yield f"data: {chunk}\n\n"
                    else:
                        break
                except asyncio.CancelledError:
                    break

            # Wait for agent to complete
            await task

            # Set default values if not set by agent
            callback_data.setdefault('ask_for_nps', True)
            callback_data.setdefault('memories_found', [])
            callback_data.setdefault('agent_actions', [])

            yield None

    except Exception as e:
        print(f"Error in execute_agentic_chat_stream: {e}")
        import traceback
        traceback.print_exc()

        # Store error in callback_data
        callback_data['error'] = str(e)
        callback_data['answer'] = "I encountered an error processing your request. Please try again."

        yield None


async def _run_agent_with_streaming(
    agent: Agent,
    messages: List[Dict],
    callback: AsyncStreamingCallback,
    callback_data: dict
) -> None:
    """
    Run the agent with streaming output

    Args:
        agent: The Omi agent instance
        messages: Formatted message history
        callback: Streaming callback for tokens
        callback_data: Dict to store results
    """
    try:
        # Run agent with streaming
        result = Runner.run_streamed(
            starting_agent=agent,
            input=messages
        )

        # Collect full response
        full_response = []
        agent_actions = []

        # Stream events
        async for event in result.stream_events():
            # Handle text delta events (streaming tokens)
            if event.type == "raw_response_event":
                if hasattr(event, 'data') and hasattr(event.data, 'delta'):
                    delta = event.data.delta
                    if isinstance(delta, str):
                        full_response.append(delta)
                        await callback.put_data(delta)

            # Track tool calls/actions
            elif event.type == "tool_call_event":
                agent_actions.append({
                    "tool": event.tool_name,
                    "arguments": event.arguments,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

        # Wait for final result
        await result.wait()

        # Get final output
        final_output = result.final_output if hasattr(result, 'final_output') else ''.join(full_response)

        # Store in callback_data
        callback_data['answer'] = final_output
        callback_data['agent_actions'] = agent_actions

        # Signal completion
        await callback.end()

    except Exception as e:
        print(f"Error in _run_agent_with_streaming: {e}")
        import traceback
        traceback.print_exc()

        callback_data['error'] = str(e)
        await callback.end()


def _build_system_prompt(
    user_name: str,
    memories_str: str,
    timezone_str: str,
    app: Optional[App] = None
) -> str:
    """
    Build the system prompt for the agent

    Args:
        user_name: User's name
        memories_str: Formatted string of user's memories
        timezone_str: User's timezone
        app: Optional app/plugin for custom prompts

    Returns:
        System prompt string
    """
    current_time = datetime.now(timezone.utc).isoformat()

    if app and app.chat_prompt:
        # Custom app prompt
        base_prompt = f"""You are '{app.name}', {app.chat_prompt}

**User Context:**
Name: {user_name}
Timezone: {timezone_str}
Current Time: {current_time}

**What you know about {user_name}:**
{memories_str}
"""
    else:
        # Default Omi prompt
        base_prompt = f"""You are Omi, an intelligent AI assistant for {user_name}.

**User Context:**
Name: {user_name}
Timezone: {timezone_str}
Current Time: {current_time}

**What you know about {user_name}:**
{memories_str}
"""

    # Add tool usage instructions
    tool_instructions = """

**Your Capabilities:**
You have access to powerful tools that let you:
- Search through past conversations to recall information
- Create and manage memories (facts about the user)
- Create and track action items/tasks
- Get user context and conversation summaries

**When to Use Tools:**
1. **search_conversations**: When the user asks about past discussions, wants to recall information, or asks "what did I say about X?"
2. **create_memory**: Proactively create memories when the user shares:
   - Personal preferences ("I love hiking")
   - Important facts ("My birthday is June 15th")
   - Goals or aspirations ("I want to learn Spanish")
   - Relationships ("My sister's name is Sarah")
3. **create_action_item**: Proactively create action items when the user mentions:
   - Tasks they need to do ("I need to buy groceries")
   - Reminders they want ("Remind me to call John")
   - Future plans ("I should exercise tomorrow")
4. **search_memories**: To recall what you know about the user before answering
5. **list_action_items**: To check what's on their todo list
6. **get_user_context**: To understand the user's current situation better

**Proactive Behavior:**
- Be helpful and anticipate user needs
- Create memories and action items without being asked explicitly
- Search conversations to provide informed responses
- Be conversational and friendly, not robotic

**Important:**
- Always be concise and natural in your responses
- Don't announce when you're using tools (just use them seamlessly)
- Combine multiple tool calls when needed (e.g., search then summarize)
- If a tool fails, gracefully continue the conversation
"""

    return base_prompt + tool_instructions


def _convert_messages_to_agent_format(messages: List[Message]) -> List[Dict]:
    """
    Convert Omi Message objects to agent format

    Args:
        messages: List of Omi Message objects

    Returns:
        List of message dicts in agent format {"role": "user"/"assistant", "content": "..."}
    """
    agent_messages = []

    for msg in messages:
        role = "assistant" if msg.sender.value == "ai" else "user"

        # Include text content
        content = msg.text

        # TODO: Handle file attachments if needed
        # if msg.files_id:
        #     content += f"\n[Attached {len(msg.files_id)} file(s)]"

        agent_messages.append({
            "role": role,
            "content": content
        })

    return agent_messages


def get_agent_config() -> dict:
    """
    Get agent configuration from environment variables

    Returns:
        Dict with agent configuration
    """
    return {
        "model": os.environ.get("AGENT_MODEL", "o4-mini"),
        "reasoning_effort": os.environ.get("AGENT_REASONING_EFFORT", "high"),
        "temperature": float(os.environ.get("AGENT_TEMPERATURE", "0.7")),
        "enabled": os.environ.get("ENABLE_AGENTIC_CHAT", "true").lower() == "true",
        "fallback_enabled": os.environ.get("AGENTIC_CHAT_FALLBACK_ENABLED", "true").lower() == "true",
    }


# For testing
if __name__ == "__main__":
    from models.chat import MessageType

    test_messages = [
        Message(
            id="1",
            sender="human",
            type=MessageType.text,
            text="I love hiking and my favorite color is blue",
            created_at=datetime.now(timezone.utc),
        ),
        Message(
            id="2",
            sender="ai",
            type=MessageType.text,
            text="That's great! I'll remember that you love hiking and blue is your favorite color.",
            created_at=datetime.now(timezone.utc),
        ),
        Message(
            id="3",
            sender="human",
            type=MessageType.text,
            text="What do you know about my preferences?",
            created_at=datetime.now(timezone.utc),
        ),
    ]

    async def test():
        callback_data = {}
        async for chunk in execute_agentic_chat_stream(
            uid="test_user_123",
            messages=test_messages,
            callback_data=callback_data
        ):
            if chunk:
                print(chunk.replace("data: ", ""), end="", flush=True)

        print("\n\nAgent Actions:", callback_data.get('agent_actions', []))

    asyncio.run(test())
