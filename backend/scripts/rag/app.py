import sys
from pathlib import Path

import streamlit as st

# Add the project root to the Python path
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

from current import *
from _shared import *
from models.chat import Message
from utils.llm import qa_rag
from utils.retrieval.rag import retrieve_rag_context

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'visualizations' not in st.session_state:
    st.session_state.visualizations = {}
if 'contexts' not in st.session_state:
    st.session_state.contexts = {}


def add_message(message: Message):
    st.session_state.messages.append(message.__dict__)


def get_messages(limit: int = 10) -> List[Message]:
    return [Message(**msg) for msg in st.session_state.messages[-limit:]]


def send_message(text: str):
    human_message = Message(
        id=str(uuid.uuid4()),
        text=text,
        created_at=datetime.utcnow(),
        sender='human',
        type='text'
    )
    add_message(human_message)

    # Retrieve context and generate response
    data = retrieve_rag_context(uid, get_messages(), return_context_params=True)
    topics, dates_range = [], []

    if len(data) == 2:
        context_str, memories = data
    else:
        # noinspection PyTupleAssignmentBalance
        context_str, memories, topics, dates_range = data

    response: str = qa_rag(context_str, get_messages(), None)

    # Generate visualization
    ai_message_id = str(uuid.uuid4())
    if topics:
        file_name = f'{ai_message_id}.html'
        generate_topics_visualization(topics, file_name)
        visualization_path = os.path.join(project_root, 'scripts', 'rag', file_name)
        if os.path.exists(visualization_path):
            with open(visualization_path, 'r') as f:
                st.session_state.visualizations[ai_message_id] = f.read()

    # Store context
    st.session_state.contexts[ai_message_id] = context_str

    ai_message = Message(
        id=ai_message_id,
        text=response,
        created_at=datetime.utcnow(),
        sender='ai',
        type='text'
    )
    add_message(ai_message)


# Remove horizontal padding
st.markdown("""
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
</style>
""", unsafe_allow_html=True)

# Streamlit UI
st.title("RAG Chat with Embedding Visualization")

# Display chat messages with inline visualizations and context
for message in get_messages():
    with st.chat_message(message.sender):
        st.write(f"{message.sender}: {message.text}")

        # Display visualization if available
        if message.id in st.session_state.visualizations:
            st.components.v1.html(st.session_state.visualizations[message.id], height=400)

            # Display context used by AI
            if message.id in st.session_state.contexts:
                with st.expander("Show Context Used"):
                    st.text(st.session_state.contexts[message.id])

# Chat input
user_input = st.chat_input("Type your message here...")
if user_input:
    send_message(user_input)
    st.rerun()  # Rerun the app to display the new message

# Display current user ID
# st.sidebar.write(f"Current User ID: {uid}")
