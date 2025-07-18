import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime
import uuid
import traceback
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check if environment variables are set properly
is_openai_configured = bool(os.getenv("OPENAI_API_KEY")) and os.getenv("OPENAI_API_KEY") != "your_openai_key_here"

from dspy_react_module import MemoryReActProgram, MODEL_CONFIGURED
from prompt_tuner import tune_prompt, apply_tuned_prompt
from langfuse_logger import LANGFUSE_ENABLED

# Constants
LABEL_FILE = "label_store.jsonl"
LANGFUSE_EXPORT_SAMPLE = "example_traces.jsonl"  # Example export for demo purposes

# App configuration
st.set_page_config(page_title="OMI Memory Quality Tuner", page_icon="🧠", layout="wide")

# Initialize session state
if "page" not in st.session_state:
    st.session_state["page"] = "home"
if "entries" not in st.session_state:
    st.session_state["entries"] = []
if "current_index" not in st.session_state:
    st.session_state["current_index"] = 0
if "test_history" not in st.session_state:
    st.session_state["test_history"] = []

# Sidebar navigation
st.sidebar.title("🧠 OMI Memory Tuner")

page = st.sidebar.radio(
    "Navigation", ["Home", "Manual Data Entry", "Label Memories", "Tune Prompt", "Test Memories"], key="navigation"
)

st.session_state["page"] = page.lower()

# Display API key status in sidebar
if not is_openai_configured:
    st.sidebar.error("⚠️ OpenAI API Key not configured")
    with st.sidebar.expander("Configure API Key"):
        api_key = st.text_input("Enter OpenAI API Key:", type="password")
        if st.button("Save API Key"):
            # This is a temporary solution - the key will be lost when the app restarts
            os.environ["OPENAI_API_KEY"] = api_key
            st.success("API Key saved for this session! Restart app to apply.")
            st.experimental_rerun()
else:
    st.sidebar.success("✅ OpenAI API Key configured")


# Create example data for testing if it doesn't exist
def create_example_langfuse_export():
    if not os.path.exists(LANGFUSE_EXPORT_SAMPLE):
        example_data = [
            {
                "input": {
                    "context": "User: Hi, my name is Sarah. I've been using OMI for about 2 weeks now.\nAssistant: Hello Sarah! How's your experience been with OMI so far?\nUser: Pretty good, though I wish it remembered more about my preferences. I like to have my calendar events organized by priority, not just time.\nAssistant: That's helpful feedback! I'll note that you prefer organizing calendar events by priority. Is there anything else about your preferences I should remember?\nUser: Yes, I always want reminders at least 2 hours before meetings, not 30 minutes.",
                    "user_name": "Sarah",
                },
                "output": {
                    "interesting_memories": [
                        "Sarah has been using OMI for about 2 weeks",
                        "Sarah prefers calendar events organized by priority, not just time",
                        "Sarah wants reminders at least 2 hours before meetings, not 30 minutes",
                    ],
                    "system_memories": [
                        "User provided feedback about calendar organization features",
                        "User has specific preferences about reminder timing",
                    ],
                },
            },
            {
                "input": {
                    "context": "User: Hey, I'm Mike. This app keeps crashing when I try to upload photos.\nAssistant: I'm sorry to hear that, Mike. That definitely shouldn't be happening. Can you tell me what kind of photos you're trying to upload?\nUser: Just regular JPGs from my vacation in Colorado last month. The mountains were incredible.\nAssistant: Thanks for that detail. I'll report this issue with photo uploads. The Colorado mountains are beautiful! Did you have a favorite spot?\nUser: Definitely Maroon Bells. I wish the photo organization was better here though. I want to tag locations.",
                    "user_name": "Mike",
                },
                "output": {
                    "interesting_memories": [
                        "Mike went on vacation to Colorado last month",
                        "Mike's favorite spot in Colorado was Maroon Bells",
                        "Mike is trying to upload vacation photos",
                    ],
                    "system_memories": [
                        "User experienced app crashes when uploading photos",
                        "User wants better photo organization with location tagging",
                    ],
                },
            },
        ]

        with open(LANGFUSE_EXPORT_SAMPLE, "w") as f:
            for entry in example_data:
                f.write(json.dumps(entry) + "\n")


# Function to count labeled examples
def get_label_stats():
    if not os.path.exists(LABEL_FILE):
        return {"total": 0, "high_quality": 0, "low_quality": 0}

    try:
        total = 0
        high_quality = 0
        low_quality = 0

        with open(LABEL_FILE, "r") as f:
            for line in f:
                total += 1
                data = json.loads(line)
                if data.get("score", 0) >= 4:
                    high_quality += 1
                else:
                    low_quality += 1

        return {"total": total, "high_quality": high_quality, "low_quality": low_quality}
    except Exception as e:
        st.error(f"Error reading label file: {e}")
        return {"total": 0, "high_quality": 0, "low_quality": 0}


# Function to generate memories safely
def generate_memories_safe(conversation, user_name):
    try:
        # Check if model is properly configured
        if not MODEL_CONFIGURED:
            return {
                "input": {"context": conversation, "user_name": user_name},
                "output": {
                    "interesting_memories": ["ERROR: OpenAI API key not configured properly"],
                    "system_memories": ["ERROR: OpenAI API key not configured properly"],
                },
                "error": True,
            }

        # Generate memories using current model
        program = MemoryReActProgram()
        result = program(conversation, user_name)

        # Create entry for labeling
        return {
            "input": {"context": conversation, "user_name": user_name},
            "output": {"interesting_memories": result.interesting_memories, "system_memories": result.system_memories},
            "error": False,
        }
    except Exception as e:
        st.error(f"Error generating memories: {e}")
        traceback.print_exc()
        return {
            "input": {"context": conversation, "user_name": user_name},
            "output": {
                "interesting_memories": [f"Error: {str(e)}"],
                "system_memories": ["Error occurred during memory generation"],
            },
            "error": True,
        }


# Home page
if st.session_state["page"] == "home":
    st.title("🧠 OMI Memory Quality Tuner")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
        ## Improve OMI's Memory Quality
        
        This tool helps you improve the quality of OMI's memory generation by:
        
        1. **Collecting Memory Examples** - Upload Langfuse data or manually enter examples
        2. **Labeling Memory Quality** - Rate generated memories on a scale of 1-5
        3. **Tuning the Prompt** - Use DSPy's ReAct framework to optimize prompts
        4. **Testing Improved Memory Generation** - Test the tuned prompt with new conversations
        
        ### Getting Started
        
        Use the navigation sidebar to move between different functions.
        """
        )

    with col2:
        stats = get_label_stats()

        st.markdown("## Current Status")
        st.metric("Total Labeled Examples", stats["total"])
        st.metric("High Quality Examples (4-5 ⭐)", stats["high_quality"])
        st.metric("Low Quality Examples (1-3 ⭐)", stats["low_quality"])

        if stats["high_quality"] >= 5:
            st.success("✅ You have enough high-quality examples to start tuning!")
        else:
            st.warning(
                f"⚠️ You need at least 5 high-quality examples to start tuning. Currently have: {stats['high_quality']}"
            )

    st.markdown("---")
    create_example_langfuse_export()

    st.markdown("### System Status")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### OpenAI Integration")
        if MODEL_CONFIGURED:
            st.success("✅ OpenAI API is properly configured")
        else:
            st.error("❌ OpenAI API is not configured properly. Please check your API key.")

    with col2:
        st.markdown("#### Langfuse Integration")
        if LANGFUSE_ENABLED:
            st.success("✅ Langfuse logger is properly configured")
        else:
            st.warning(
                "⚠️ Langfuse is not configured properly. Memory generation will still work, but logging will be disabled."
            )
            st.markdown("To enable Langfuse logging, set these environment variables:")
            st.code("LANGFUSE_API_KEY=your_public_key\nLANGFUSE_SECRET_KEY=your_secret_key")

# Manual data entry page
elif st.session_state["page"] == "manual data entry":
    st.title("📝 Manual Memory Data Entry")

    if not MODEL_CONFIGURED:
        st.error("❌ OpenAI API is not configured properly. Memory generation will not work correctly.")
        st.markdown("Please set your OpenAI API key in the sidebar or through environment variables.")

    st.markdown(
        """
    Use this form to manually enter conversation data and generate memories for labeling.
    """
    )

    with st.form("memory_data_entry"):
        conversation = st.text_area(
            "Enter a conversation transcript:",
            height=200,
            help="Format should be 'User: <message>\\nAssistant: <message>' and so on",
        )

        user_name = st.text_input("User's name:", help="The name of the user in the conversation")

        submitted = st.form_submit_button("Generate Memories")

        if submitted and conversation and user_name:
            entry = generate_memories_safe(conversation, user_name)

            # Add to entries for labeling
            st.session_state["entries"] = [entry]
            st.session_state["current_index"] = 0

            if not entry["error"]:
                st.success("✅ Memories generated! Go to 'Label Memories' to rate them.")
                st.button("Go to Label Memories", on_click=lambda: setattr(st.session_state, "page", "label memories"))
            else:
                st.error("❌ Error generating memories. Please check the configuration.")

# Labeling page
elif st.session_state["page"] == "label memories":
    st.title("🏷️ Memory Quality Labeling")

    # Upload Langfuse export
    with st.expander("Upload Memories from Langfuse"):
        uploaded_file = st.file_uploader(
            "Upload Langfuse-exported JSONL file",
            type=["jsonl"],
            help="Export traces from Langfuse with memory generation results",
        )

        if uploaded_file:
            try:
                entries = [json.loads(line) for line in uploaded_file]
                st.session_state["entries"] = entries
                st.session_state["current_index"] = 0
                st.success(f"✅ Loaded {len(entries)} entries!")
            except Exception as e:
                st.error(f"Error parsing upload: {e}")

    # Use demo data
    with st.expander("Use Demo Data"):
        if st.button("Load Demo Data"):
            create_example_langfuse_export()
            try:
                with open(LANGFUSE_EXPORT_SAMPLE, "r") as f:
                    entries = [json.loads(line) for line in f]
                    st.session_state["entries"] = entries
                    st.session_state["current_index"] = 0
                    st.success(f"✅ Loaded {len(entries)} demo entries!")
            except Exception as e:
                st.error(f"Error loading demo data: {e}")

    # Labeling interface
    if "entries" in st.session_state and st.session_state["entries"]:
        entries = st.session_state["entries"]
        i = st.session_state["current_index"]

        if i < len(entries):
            entry = entries[i]

            # Progress indicator
            st.progress((i) / len(entries))
            st.markdown(f"**Entry {i+1} of {len(entries)}**")

            # Display conversation
            with st.expander("Conversation Context", expanded=True):
                st.markdown(f"```\n{entry['input']['context']}\n```")

            # Display generated memories
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Interesting Memories")
                if entry['output']['interesting_memories']:
                    for mem in entry['output']['interesting_memories']:
                        st.markdown(f"- {mem}")
                else:
                    st.markdown("*No interesting memories generated*")

            with col2:
                st.subheader("System Memories")
                if entry['output']['system_memories']:
                    for mem in entry['output']['system_memories']:
                        st.markdown(f"- {mem}")
                else:
                    st.markdown("*No system memories generated*")

            # Quality rating form
            with st.form("memory_rating_form"):
                st.markdown("### Rate Memory Quality")

                quality_score = st.slider(
                    "Overall Quality Score", min_value=1, max_value=5, value=3, help="1=Poor, 5=Excellent"
                )

                feedback = st.text_area(
                    "Optional Feedback", placeholder="What could be improved? What's missing or incorrect?"
                )

                submit_button = st.form_submit_button("Submit Rating")

                if submit_button:
                    # Save the labeled example
                    with open(LABEL_FILE, "a") as f:
                        f.write(
                            json.dumps(
                                {
                                    "input": entry["input"],
                                    "output": entry["output"],
                                    "score": quality_score,
                                    "feedback": feedback,
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                            + "\n"
                        )

                    # Move to next entry
                    st.session_state["current_index"] += 1
                    st.rerun()

            # Navigation buttons
            col1, col2 = st.columns(2)
            with col1:
                if i > 0:
                    if st.button("Previous Entry"):
                        st.session_state["current_index"] -= 1
                        st.rerun()

            with col2:
                if i < len(entries) - 1:
                    if st.button("Skip to Next"):
                        st.session_state["current_index"] += 1
                        st.rerun()
        else:
            st.success("✅ All entries have been labeled!")

            stats = get_label_stats()
            st.metric("Total Labeled Examples", stats["total"])
            st.metric("High Quality Examples (4-5 ⭐)", stats["high_quality"])

            if st.button("Start Over"):
                st.session_state["current_index"] = 0
                st.rerun()
    else:
        st.info("No memory entries to label. Please upload a Langfuse export or use the demo data.")

# Tuning page
elif st.session_state["page"] == "tune prompt":
    st.title("🔧 Tune Memory Generation Prompt")

    stats = get_label_stats()

    if stats["high_quality"] < 5:
        st.warning(
            f"⚠️ It's recommended to have at least 5 high-quality examples for tuning. Currently have: {stats['high_quality']}"
        )

    # Display labeled data summary
    with st.expander("View Labeled Data Summary"):
        try:
            if os.path.exists(LABEL_FILE):
                examples = []
                with open(LABEL_FILE, "r") as f:
                    for line in f:
                        examples.append(json.loads(line))

                df = pd.DataFrame(
                    [
                        {
                            "User": ex["input"]["user_name"],
                            "Score": ex["score"],
                            "Feedback": ex.get("feedback", ""),
                            "Timestamp": ex.get("timestamp", ""),
                            "Interesting Memories": len(ex["output"]["interesting_memories"]),
                            "System Memories": len(ex["output"]["system_memories"]),
                        }
                        for ex in examples
                    ]
                )

                st.dataframe(df)
            else:
                st.info("No labeled data available yet.")
        except Exception as e:
            st.error(f"Error displaying data summary: {e}")

    # Tuning configuration
    st.subheader("Tuning Configuration")

    col1, col2 = st.columns(2)

    with col1:
        min_quality = st.slider(
            "Minimum Quality Score",
            min_value=1,
            max_value=5,
            value=4,
            help="Only use examples with this quality score or higher",
        )

    with col2:
        optimization_rounds = st.slider(
            "Optimization Rounds",
            min_value=1,
            max_value=10,
            value=5,
            help="More rounds = better results but takes longer",
        )

    # Start tuning process
    if st.button("Start Tuning Process"):
        with st.spinner("Tuning prompt... This may take a few minutes."):
            success = tune_prompt(min_score=min_quality, rounds=optimization_rounds)

            if success:
                st.success("✅ Prompt tuning completed successfully!")
                st.balloons()
            else:
                st.error("❌ Prompt tuning failed. Check the console for error details.")

# Testing page
elif st.session_state["page"] == "test memories":
    st.title("🧪 Test Memory Generation")

    # Check if optimized prompt exists
    optimized_exists = os.path.exists("optimized_prompts.json")

    if not optimized_exists:
        st.warning("⚠️ No optimized prompt found. Please complete the tuning process first.")

    # Test form
    with st.form("test_memory_generation"):
        conversation = st.text_area(
            "Enter a conversation to test memory generation:",
            height=200,
            help="Format should be 'User: <message>\\nAssistant: <message>' and so on",
            placeholder="User: Hi, I'm Taylor. I've been having trouble with...\nAssistant: Hello Taylor! I'm sorry to hear that...\nUser: ...",
        )

        user_name = st.text_input("User's name:", help="The name of the user in the conversation")

        use_optimized = st.checkbox("Use optimized prompt", value=optimized_exists, disabled=not optimized_exists)

        submitted = st.form_submit_button("Generate Memories")

        if submitted and conversation and user_name:
            with st.spinner("Generating memories..."):
                try:
                    program = None
                    if use_optimized and optimized_exists:
                        program = apply_tuned_prompt()
                        if not program:
                            st.error("Error loading optimized prompt")
                            program = MemoryReActProgram()
                    else:
                        program = MemoryReActProgram()

                    # Generate memories
                    result = program(conversation, user_name)

                    # Display results
                    col1, col2 = st.columns(2)

                    with col1:
                        st.subheader("Interesting Memories")
                        if result.interesting_memories:
                            for mem in result.interesting_memories:
                                st.markdown(f"- {mem}")
                        else:
                            st.markdown("*No interesting memories generated*")

                    with col2:
                        st.subheader("System Memories")
                        if result.system_memories:
                            for mem in result.system_memories:
                                st.markdown(f"- {mem}")
                        else:
                            st.markdown("*No system memories generated*")

                    # Add to test history
                    st.session_state["test_history"].append(
                        {
                            "id": str(uuid.uuid4()),
                            "timestamp": datetime.now().isoformat(),
                            "input": {"context": conversation, "user_name": user_name},
                            "output": {
                                "interesting_memories": result.interesting_memories,
                                "system_memories": result.system_memories,
                            },
                            "optimized": use_optimized,
                        }
                    )

                    # Allow saving this test case as a labeled example
                    with st.expander("Save as labeled example"):
                        quality = st.slider("Quality score", 1, 5, 3)
                        comment = st.text_area("Comments")

                        if st.button("Save Example"):
                            with open(LABEL_FILE, "a") as f:
                                f.write(
                                    json.dumps(
                                        {
                                            "input": {"context": conversation, "user_name": user_name},
                                            "output": {
                                                "interesting_memories": result.interesting_memories,
                                                "system_memories": result.system_memories,
                                            },
                                            "score": quality,
                                            "feedback": comment,
                                            "timestamp": datetime.now().isoformat(),
                                        }
                                    )
                                    + "\n"
                                )
                            st.success("Example saved!")

                except Exception as e:
                    st.error(f"Error generating memories: {e}")

    # Display test history
    if st.session_state["test_history"]:
        st.markdown("---")
        st.subheader("Test History")

        for i, test in enumerate(reversed(st.session_state["test_history"])):
            with st.expander(f"Test {len(st.session_state['test_history']) - i} - {test['timestamp']}"):
                st.markdown(f"**Prompt Type:** {'Optimized' if test['optimized'] else 'Original'}")
                st.markdown(f"**User:** {test['input']['user_name']}")

                st.markdown("**Context:**")
                st.markdown(f"```\n{test['input']['context']}\n```")

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**Interesting Memories:**")
                    for mem in test['output']['interesting_memories']:
                        st.markdown(f"- {mem}")

                with col2:
                    st.markdown("**System Memories:**")
                    for mem in test['output']['system_memories']:
                        st.markdown(f"- {mem}")

                if st.button("Delete This Test", key=f"delete_{test['id']}"):
                    st.session_state["test_history"] = [
                        t for t in st.session_state["test_history"] if t['id'] != test['id']
                    ]
                    st.rerun()

        if st.button("Clear History"):
            st.session_state["test_history"] = []
            st.rerun()
else:
    st.error("Unknown page")
