import sys
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

# Add the project root to the Python path
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

from _shared import *
from models.chat import Message
from utils.llm import qa_rag
from utils.retrieval.rag import retrieve_rag_context

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []


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

    # Simulating the AI response (replace this with your actual AI logic)
    context_str, memories = retrieve_rag_context(uid, get_messages())
    response: str = qa_rag(context_str, get_messages(), None)

    ai_message = Message(
        id=str(uuid.uuid4()),
        text=response,
        created_at=datetime.utcnow(),
        sender='ai',
        type='text'
    )
    add_message(ai_message)


# Streamlit UI
st.title("Simple Chat Application")

# Display chat messages
for message in get_messages():
    with st.chat_message(message.sender):
        st.write(f"{message.sender}: {message.text}")

# Chat input
user_input = st.chat_input("Type your message here...")
if user_input:
    send_message(user_input)
    st.rerun()  # Rerun the app to display the new message

# Display current user ID
st.sidebar.write(f"Current User ID: {uid}")
