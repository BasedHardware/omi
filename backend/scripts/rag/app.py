import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Tuple, cast

import streamlit as st
import streamlit.components.v1 as components

# Add the project root to the Python path
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

from current import *  # noqa: F401, F403
from _shared import *  # noqa: F401, F403
from database.auth import get_user_name
from models.chat import Message, MessageSender, MessageType
from models.conversation import Conversation
from models.transcript_segment import TranscriptSegment
from utils.llm.chat import qa_rag

from utils.retrieval import rag as _rag_module

# retrieve_rag_context was removed from utils.retrieval.rag; keep a typed alias for this legacy script.
retrieve_rag_context: Any = cast(Any, getattr(_rag_module, 'retrieve_rag_context', None))
STATE_FILE = 'chat_state.json'


# Custom JSON encoder to handle datetime objects and Memory objects
class CustomEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            return {'__datetime__': o.isoformat()}
        if isinstance(o, Conversation):
            return {'__memory__': o.dict()}
        return super().default(o)


# Custom JSON decoder to handle datetime objects and Memory objects
class CustomDecoder(json.JSONDecoder):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, dct: dict[str, Any]) -> Any:  # type: ignore[override]
        if '__datetime__' in dct:
            return datetime.fromisoformat(str(dct['__datetime__']))
        if '__memory__' in dct:
            return Conversation(**cast(dict[str, Any], dct['__memory__']))
        return dct


# Load state from file
def load_state() -> dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                state: Any = json.load(f, cls=CustomDecoder)
            return cast(dict[str, Any], state)
        except json.JSONDecodeError as e:
            st.error(f"Error loading state: {str(e)}. Starting with a fresh state.")
            os.rename(STATE_FILE, f"{STATE_FILE}.bak")
            st.info(f"The corrupted state file has been renamed to {STATE_FILE}.bak")
        except Exception as e:
            st.error(f"Unexpected error loading state: {str(e)}. Starting with a fresh state.")
    return {'messages': [], 'visualizations': {}, 'contexts': {}, 'memories': {}}


# Save state to file
def save_state() -> None:
    state: dict[str, Any] = {
        'messages': st.session_state.messages,
        'visualizations': st.session_state.visualizations,
        'contexts': st.session_state.contexts,
        'memories': st.session_state.memories,
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, cls=CustomEncoder)


# Initialize session state
state = load_state()
if 'messages' not in st.session_state:
    st.session_state.messages = state['messages']
if 'visualizations' not in st.session_state:
    st.session_state.visualizations = state['visualizations']
if 'contexts' not in st.session_state:
    st.session_state.contexts = state['contexts']
if 'memories' not in st.session_state:
    st.session_state.memories = state['memories']


def add_message(message: Message) -> None:
    st.session_state.messages.append(message.__dict__)
    save_state()


def get_messages(limit: int = 10) -> List[Message]:
    return [Message(**msg) for msg in cast(List[Any], st.session_state.messages)[-limit:]]


def send_message(text: str) -> None:
    human_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.human,
        type=MessageType.text,
    )
    add_message(human_message)

    # Retrieve context and generate response
    data: Any = retrieve_rag_context(uid, get_messages(), return_context_params=True)
    topics: List[str] = []

    context_str: str
    memories: Any
    if len(data) == 2:
        context_str, memories = cast(Tuple[str, Any], data)
    else:
        context_str, memories, topics, _ = cast(Tuple[str, Any, List[str], Any], data)

    response: str = qa_rag(uid, context_str, context_str, None, messages=get_messages())

    # Generate visualization
    ai_message_id = str(uuid.uuid4())
    if topics:
        file_name = f'{ai_message_id}.html'
        generate_visualization(topics, cast(List[Conversation], memories), file_name)
        visualization_path = os.path.join(project_root, 'scripts', 'rag', 'visualizations', file_name)
        if os.path.exists(visualization_path):
            with open(visualization_path, 'r') as f:
                st.session_state.visualizations[ai_message_id] = f.read()

    # Store context and memories
    st.session_state.contexts[ai_message_id] = context_str
    st.session_state.memories[ai_message_id] = memories

    ai_message = Message(
        id=ai_message_id,
        text=response,
        created_at=datetime.now(timezone.utc),
        sender=MessageSender.ai,
        type=MessageType.text,
    )
    add_message(ai_message)
    save_state()


def clear_state() -> None:
    st.session_state.messages = []
    st.session_state.visualizations = {}
    st.session_state.contexts = {}
    st.session_state.memories = {}
    save_state()
    st.rerun()


# Custom CSS (remove table-related styles)
st.markdown(
    """
<style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    .main .block-container {
        max-width: 100%;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    .stChatMessage {
        padding-left: 0px;
        padding-right: 0px;
    }
    .stChatMessage .stChatMessageContent {
        padding-left: 0.5rem;
        padding-right: 0.5rem;
    }
    .stChatInputContainer {
        padding-left: 0px;
        padding-right: 0px;
    }
    .stChatInputContainer textarea {
        width: 100%;
    }
    .st-expander {
        width: 100%;
    }
    pre {
        white-space: pre-wrap;
        word-wrap: break-word;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Streamlit UI
st.title("RAG Chat with Embedding Visualization")

# Clear state button
if st.button("Clear Chat History"):
    clear_state()

# Display chat messages with inline visualizations and context
visualizations = cast(dict[str, str], st.session_state.visualizations)
contexts = cast(dict[str, str], st.session_state.contexts)
memories_state = cast(dict[str, List[Conversation]], st.session_state.memories)

for message in get_messages():
    with st.chat_message(message.sender):
        st.write(f"{message.text}")

        # Display visualization if available
        if message.id in visualizations:
            components.html(visualizations[message.id], height=600)

        # Display context used by AI
        if message.id in contexts:
            with st.expander("Show Context Used"):
                st.code(contexts[message.id], language="")

        # Display memories used for context
        if message.id in memories_state:
            with st.expander("Show Memories Used"):
                msg_memories = memories_state[message.id]
                for i, memory in enumerate(msg_memories):
                    st.markdown(f"**Memory {i + 1}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Raw Transcript Segments**")
                        transcript = TranscriptSegment.segments_as_string(
                            memory.transcript_segments, user_name=get_user_name(uid, use_default=False)
                        ).replace('\n\n', '\n')
                        lines = transcript.count('\n')
                        ten_lines = transcript.split('\n')[:10]
                        st.text('\n'.join(ten_lines))
                        if lines > 10:
                            st.write(f"(Showing 10 out of {len(memory.transcript_segments)} segments)")

                    with col2:
                        st.markdown("**Structured Details**")
                        st.text(str(memory.structured))
                    st.markdown("---")

# Chat input
user_input = st.chat_input("Type your message here...")
if user_input:
    send_message(user_input)
    st.rerun()  # Rerun the app to display the new message
