import os
import uuid
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Flag to track if Langfuse is enabled
LANGFUSE_ENABLED = False

# Try importing Langfuse with fallbacks for different versions
try:
    try:
        # Try importing the newer version
        from langfuse import Langfuse

        langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_API_KEY", "dummy_key"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", "dummy_secret"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
        LANGFUSE_ENABLED = True
        print("✅ Langfuse initialized successfully (newer version)")
    except Exception as e:
        # Try the older version initialization
        from langfuse import Langfuse

        langfuse = Langfuse(
            api_key=os.getenv("LANGFUSE_API_KEY", "dummy_key"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", "dummy_secret"),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
        LANGFUSE_ENABLED = True
        print("✅ Langfuse initialized successfully (older version)")
except Exception as e:
    print(f"Warning: Langfuse initialization failed: {e}")
    print("Memory generation will still work, but logging is disabled.")
    LANGFUSE_ENABLED = False


def log_to_langfuse(input, output, model="memory-generator", session_id=None):
    """
    Log memory generation to Langfuse for tracking and evaluation

    Args:
        input (dict): The input context and user_name
        output (dict): The generated interesting and system memories
        model (str): Name of the model/component
        session_id (str, optional): Session ID for grouping traces

    Returns:
        str: Trace ID if successful, None otherwise
    """
    if not LANGFUSE_ENABLED:
        return None

    try:
        # Create a unique trace ID if not provided
        trace_id = str(uuid.uuid4())

        # Create trace for the complete memory generation
        trace = langfuse.trace(
            id=trace_id,
            name="memory_generation",
            session_id=session_id or str(uuid.uuid4()),
            metadata={"user_name": input.get("user_name", "unknown")},
        )

        # Log the generation as a span
        generation = trace.span(
            name="generate_memories",
            input=input,
            output=output,
        )

        # Try different observation methods based on Langfuse version
        try:
            # Try newer Langfuse API version first
            trace.observation(
                name="memory_quality",
                input=input,
                output=output,
                model=model,
            )
        except (AttributeError, TypeError) as e:
            try:
                # Try alternate API method (older versions)
                trace.generation(
                    name="memory_quality",
                    input=input,
                    output=output,
                    model=model,
                )
            except Exception:
                # If both fail, log error but continue
                print(f"Warning: Could not log observation to Langfuse: {e}")

        return trace_id
    except Exception as e:
        print(f"Error logging to Langfuse: {e}")
        return None
