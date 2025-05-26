import streamlit as st
import asyncio
import shutil
from dotenv import load_dotenv

from agents import Agent, Runner, trace, ModelSettings
from agents.mcp import MCPServerStdio
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
async def process_message_with_agent(
    conversation_history: list[dict[str, any]], uid: str
):
    """
    Processes the conversation history using the OMI agent and returns the response
    along with reasoning/tool call details for the latest turn.
    """
    print(
        f"process_message_with_agent called with UID: {uid} and conversation history length: {len(conversation_history)}"
    )
    if conversation_history:
        last_msg = conversation_history[-1]
        print(
            f"Last message - Role: {last_msg.get('role')}, Content snippet: {str(last_msg.get('content'))[:100]}..."
        )

    if not uid:  # Check if agent_uid (OMI_UID from UI) was provided
        st.error("Error: OMI_UID was not provided to the agent processing function.")
        return (
            "Error: OMI_UID is not configured. Please enter it in the sidebar settings.",
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
        else:
            # Log if a message is skipped, this might indicate an issue with history state
            print(
                f"Warning: Skipping message in history due to missing 'role' or 'content': {msg}"
            )

    if not agent_input_messages:
        # This case should ideally not be reached if called after a user prompt
        st.error("Error: No valid messages to process after filtering history.")
        return ("Error: Conversation history is empty or invalid.", [])

    try:
        async with MCPServerStdio(
            cache_tools_list=False,
            params={"command": "uvx", "args": ["mcp-server-omi", "-v"]},
        ) as server:
            omi_agent = Agent(
                name="Omi Agent",
                instructions=f"You are a helpful assistant that answers questions based on my Omi data, my UID is {uid}. You are processing a conversation, the history of which is provided.",
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
            print("run_output:", run_output)

            final_response = (
                run_output.final_output
                if run_output and run_output.final_output
                else "Sorry, I couldn't process that."
            )
            reasoning_details = []

            if run_output and hasattr(run_output, "new_items") and run_output.new_items:
                for item in run_output.new_items:
                    reasoning_details.append(item.raw_item)
            elif run_output:
                print("Note: run_output.new_items was empty or not present.")
            else:
                print("Warning: run_output was None.")

            return final_response, reasoning_details

    except Exception as e:
        st.error(f"An error occurred during agent processing: {e}")
        print(
            f"Detailed error in process_message_with_agent: {e}"
        )  # Log detailed error to console
        return "An error occurred while trying to get a response.", []


# --- Streamlit App UI ---

st.set_page_config(page_title="Omi Agent Chat", layout="wide")
st.title("🤖 Omi Agent Chat")

UVX_PATH = shutil.which("uvx")
if not UVX_PATH:
    st.error(
        "Critical Error: `uvx` command not found. "
        "Please ensure it's installed and in your system's PATH. "
        "The agent cannot function without it."
    )
    st.stop()

if "user_omi_uid" not in st.session_state:
    st.session_state.user_omi_uid = ""

with st.sidebar:
    st.header("Settings")
    st.session_state.user_omi_uid = st.text_input(
        "Enter your OMI UID:",
        value=st.session_state.user_omi_uid,
        help="Your OMI Unique Identifier is required to interact with the agent.",
    )

    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

if not st.session_state.user_omi_uid.strip():
    st.warning("Please enter your OMI UID in the sidebar settings to start chatting.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display prior chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if (
            message["role"] == "assistant"
            and "reasoning" in message
            and message["reasoning"]
        ):
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

        uid = st.session_state.user_omi_uid

        if not uid.strip():
            message_placeholder.error(
                "Error: OMI_UID not set. Please enter it in the sidebar."
            )
        else:
            # Pass the entire current conversation history (including the new user prompt)
            response_text, reasoning_data = run_async_task(
                process_message_with_agent(st.session_state.messages, uid)
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
