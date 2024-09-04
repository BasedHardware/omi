import sys
from pathlib import Path

import streamlit as st

# Add the project root to the Python path
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

# File to store the state
STATE_FILE = 'chat_state.json'

# Add the project root to the Python path
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

from current import *
from _shared import *
from models.chat import Message
from models.memory import Memory
from models.transcript_segment import TranscriptSegment
from utils.llm import qa_rag
from utils.retrieval.rag import retrieve_rag_context

# File to store the state
STATE_FILE = 'chat_state.json'


# Custom JSON encoder to handle datetime objects and Memory objects
class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return {'__datetime__': obj.isoformat()}
        if isinstance(obj, Memory):
            return {'__memory__': obj.dict()}
        return super().default(obj)


# Custom JSON decoder to handle datetime objects and Memory objects
class CustomDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    @staticmethod
    def object_hook(dct):
        if '__datetime__' in dct:
            return datetime.fromisoformat(dct['__datetime__'])
        if '__memory__' in dct:
            return Memory(**dct['__memory__'])
        return dct


# Load state from file
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f, cls=CustomDecoder)
            return state
        except json.JSONDecodeError as e:
            st.error(f"Error loading state: {str(e)}. Starting with a fresh state.")
            os.rename(STATE_FILE, f"{STATE_FILE}.bak")
            st.info(f"The corrupted state file has been renamed to {STATE_FILE}.bak")
        except Exception as e:
            st.error(f"Unexpected error loading state: {str(e)}. Starting with a fresh state.")
    return {'messages': [], 'visualizations': {}, 'contexts': {}, 'memories': {}}


# Save state to file
def save_state():
    state = {
        'messages': st.session_state.messages,
        'visualizations': st.session_state.visualizations,
        'contexts': st.session_state.contexts,
        'memories': st.session_state.memories
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


def add_message(message: Message):
    st.session_state.messages.append(message.__dict__)
    save_state()


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
        context_str, memories, topics, dates_range = data

    response: str = qa_rag(uid, context_str, get_messages(), None)

    # Generate visualization
    ai_message_id = str(uuid.uuid4())
    if topics:
        file_name = f'{ai_message_id}.html'
        generate_visualization(topics, memories, file_name)
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
        created_at=datetime.utcnow(),
        sender='ai',
        type='text'
    )
    add_message(ai_message)
    save_state()


def clear_state():
    st.session_state.messages = []
    st.session_state.visualizations = {}
    st.session_state.contexts = {}
    st.session_state.memories = {}
    save_state()
    st.rerun()


# Custom CSS (remove table-related styles)
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
""", unsafe_allow_html=True)

# Streamlit UI
st.title("RAG Chat with Embedding Visualization")

# Clear state button
if st.button("Clear Chat History"):
    clear_state()

# Display chat messages with inline visualizations and context
for message in get_messages():
    with st.chat_message(message.sender):
        st.write(f"{message.text}")

        # Display visualization if available
        if message.id in st.session_state.visualizations:
            st.components.v1.html(st.session_state.visualizations[message.id], height=600)

        # Display context used by AI
        if message.id in st.session_state.contexts:
            with st.expander("Show Context Used"):
                st.code(st.session_state.contexts[message.id], language="")

        # Display memories used for context
        if message.id in st.session_state.memories:
            with st.expander("Show Memories Used"):
                memories = st.session_state.memories[message.id]
                for i, memory in enumerate(memories):
                    st.markdown(f"**Memory {i + 1}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Raw Transcript Segments**")
                        transcript = TranscriptSegment.segments_as_string(memory.transcript_segments).replace(
                            '\n\n', '\n')
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
