import os
import streamlit as st
import asyncio
from dotenv import load_dotenv

from agents import Agent, Runner, trace, ModelSettings
from agents.mcp import MCPServerStreamableHttp
from openai.types.shared import Reasoning

load_dotenv()


def run_async_task(coro):
    """
    Runs an asynchronous coroutine, managing the event loop.
    This creates a new event loop for each task, which is robust
    if Streamlit's environment has an existing, potentially conflicting, loop.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(coro)
    finally:
        loop.close()
        try:
            main_loop = asyncio.get_event_loop_policy().get_event_loop()
            asyncio.set_event_loop(main_loop)
        except RuntimeError:
            asyncio.set_event_loop(None)
    return result


# --- Agent Interaction Logic ---
async def process_message_with_agent(conversation_history: list[dict[str, any]], api_key: str):
    """
    Processes the conversation history using the OMI agent and returns the response
    along with reasoning/tool call details for the latest turn.
    """
    if not api_key:
        st.error("Error: OMI_MCP_API_KEY was not provided to the agent processing function.")
        return (
            "Error: OMI_MCP_API_KEY is not configured. Please enter it in the sidebar settings.",
            [],
        )

    # Prepare input for the agent by formatting the conversation history.
    # Runner.run expects a list of message-like dicts, typically {"role": ..., "content": ...}.
    agent_input_messages = []
    for msg in conversation_history:
        role = msg.get("role")
        content = msg.get("content")
        # Ensure essential parts of a message are present
        if role and content is not None:
            agent_input_messages.append({"role": role, "content": content})

    if not agent_input_messages:
        # This case should ideally not be reached if called after a user prompt
        st.error("Error: No valid messages to process after filtering history.")
        return ("Error: Conversation history is empty or invalid.", [])

    try:
        # Hosted Streamable HTTP endpoint — Bearer MCP key auth, no local process.
        async with MCPServerStreamableHttp(
            cache_tools_list=False,
            params={
                "url": "https://api.omi.me/v1/mcp",
                "headers": {"Authorization": f"Bearer {api_key}"},
            },
        ) as server:
            omi_agent = Agent(
                name="Omi Agent",
                instructions="You are a helpful assistant that answers questions based on my Omi data. You are processing a conversation, the history of which is provided.",
                mcp_servers=[server],
                model="o3",
                # model="litellm/anthropic/claude-3-7-sonnet-20250219",
                model_settings=ModelSettings(reasoning=Reasoning(effort="high")),
            )

            with trace(workflow_name="Stramlit Omi MCP Example"):
                run_output = await Runner.run(
                    starting_agent=omi_agent,
                    input=agent_input_messages,  # Pass the formatted conversation history
                )

            final_response = (
                run_output.final_output if run_output and run_output.final_output else "Sorry, I couldn't process that."
            )
            reasoning_details = []

            if run_output and hasattr(run_output, "new_items") and run_output.new_items:
                for item in run_output.new_items:
                    reasoning_details.append(item.raw_item)

            return final_response, reasoning_details

    except Exception:
        # Exception text can carry user data or the API key — surface a
        # constant message instead of the raw error.
        st.error("An error occurred while processing the request.")
        return "An error occurred while trying to get a response.", []


# --- Streamlit App UI ---

if __name__ == "__main__":
    st.set_page_config(page_title="Omi Agent Chat", layout="wide")
    st.title("🤖 Omi Agent Chat")

    if "mcp_api_key" not in st.session_state:
        st.session_state.mcp_api_key = os.getenv("OMI_MCP_API_KEY", "")

    with st.sidebar:
        st.header("Settings")
        st.session_state.mcp_api_key = st.text_input(
            "Enter your Omi MCP API key:",
            value=st.session_state.mcp_api_key,
            type="password",
            help="An `omi_mcp_...` key from Settings → Developer Settings → MCP Server → API Keys in the Omi app.",
        )

        if st.button("Clear Chat History"):
            st.session_state.messages = []
            st.rerun()

    if not st.session_state.mcp_api_key.strip():
        st.warning("Please enter your Omi MCP API key in the sidebar settings to start chatting.")
        st.stop()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display prior chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant" and "reasoning" in message and message["reasoning"]:
                with st.expander("View Reasoning/Tool Calls", expanded=False):
                    for i, detail in enumerate(message["reasoning"]):
                        # Using str(detail) for broader compatibility, language="json" for Pydantic models
                        st.code(str(detail), language="json")
                        if i < len(message["reasoning"]) - 1:
                            st.markdown("---")


    if prompt := st.chat_input("Ask Omi about your data..."):
        # Add user message to session state and display it
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Process message with agent and display assistant response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            message_placeholder.markdown("Thinking...")

            api_key = st.session_state.mcp_api_key

            if not api_key.strip():
                message_placeholder.error("Error: OMI_MCP_API_KEY not set. Please enter it in the sidebar.")
            else:
                # Pass the entire current conversation history (including the new user prompt)
                response_text, reasoning_data = run_async_task(
                    process_message_with_agent(st.session_state.messages, api_key)
                )
                message_placeholder.markdown(response_text)

                # Add assistant's response to session state
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": response_text,
                        "reasoning": reasoning_data,
                    }
                )
                # Display reasoning for the latest assistant response, if any
                if reasoning_data:
                    with st.expander(
                        "View Reasoning/Tool Calls", expanded=False
                    ):  # Display immediately, not just on next reload
                        for i, detail in enumerate(reasoning_data):
                            st.code(str(detail), language="json")
                            if i < len(reasoning_data) - 1:
                                st.markdown("---")
