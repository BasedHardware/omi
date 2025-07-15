import dspy
import openai
from dspy import ReAct
from dspy.signatures import Signature
from langfuse_logger import log_to_langfuse
import os
import sys
import traceback
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Global variables
MODEL_CONFIGURED = False
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DUMMY_MODE = os.getenv("DUMMY_MODE", "false").lower() in ("true", "1", "yes")


# Configure DSPy with OpenAI
def configure_openai():
    global MODEL_CONFIGURED

    # If dummy mode is enabled, skip real configuration
    if DUMMY_MODE:
        print("🔧 Running in DUMMY MODE - No API key required")
        return True

    if not OPENAI_API_KEY or OPENAI_API_KEY == "your_openai_key_here" or OPENAI_API_KEY == "":
        print("\033[91mERROR: OPENAI_API_KEY environment variable is not set properly.\033[0m")
        print("Please set your OpenAI API key using one of these methods:")
        print("1. Create a .env file with OPENAI_API_KEY=your_key_here")
        print("2. Export the key in your shell: export OPENAI_API_KEY=your_key_here")
        print("3. Run the app with ./run.sh which will prompt for the key")
        print("4. Alternatively, set DUMMY_MODE=true to run without an API key (demo only)")
        return False

    try:
        # Configure OpenAI API key
        openai.api_key = OPENAI_API_KEY

        # Configure DSPy using LM class instead of OpenAI directly
        # Based on DSPy tutorial: https://dspy.ai/tutorials/agents/
        print("Configuring DSPy with OpenAI...")

        # Check which DSPy approach works with the installed version
        try:
            # Try first method (newer versions)
            openai_lm = dspy.LM('openai/gpt-4o', api_key=OPENAI_API_KEY)
            dspy.configure(lm=openai_lm)
        except (AttributeError, TypeError):
            try:
                # Try older approach through OpenAI class
                openai_lm = dspy.OpenAI(model="gpt-4o", api_key=OPENAI_API_KEY)
                dspy.configure(lm=openai_lm)
            except Exception as e:
                # Try direct model configuration without LM wrapper
                dspy.configure(model="gpt-4o")

        print("✅ OpenAI model configured successfully")
        return True
    except Exception as e:
        print(f"\033[91mError configuring OpenAI model: {e}\033[0m")
        traceback.print_exc()
        return False


# Try to configure the model
MODEL_CONFIGURED = configure_openai()


class GenerateMemories(Signature):
    """
    Generate up to 2 interesting and 2 system memories from a conversation between the user and 1 or more people.

    Interesting memories should:
    - Capture really interesting and exciting details from the conversation. These can be like cool facts, cool things to remember, cool things to do, etc. Something that the user would not already know and would want to come back to and refer to in the future for fun or reference.
    - These details can be about the user, the other people in the conversation, a place, something they did, something they are going to do, etc.
    - Be worthwhile for the user to come back to and refer to in the future for fun or reference.
    - Be super short and catchy and just mention the most exciting details/facts/figures in short.

    System memories should:
    - Be boring details about the conversation.
    - Be details that are not interesting to the user but are mostly boring factual details about the user, the other people in the conversation, the place, etc.
    - Be things that the user would not want to ever come back to and refer to in the future.

    All memories should be concise, clear, and directly extracted from the conversation.
    """

    context: str = dspy.InputField(description="The conversation transcript or context from which to generate memories")
    user_name: str = dspy.InputField(description="The name of the user in the conversation")
    interesting_memories: list = dspy.OutputField(
        description="List of up to 2 interesting personal memories about the user"
    )
    system_memories: list = dspy.OutputField(
        description="List of up to 2 system-relevant memories about interaction patterns"
    )


class MemoryReActProgram(dspy.Module):
    def __init__(self, max_reasoning_steps=3):
        super().__init__()
        # Initialize ReAct with our signature, trying different initialization approaches
        try:
            # Try with tools parameter (newer versions)
            self.react = ReAct(signature=GenerateMemories, tools=[])
        except TypeError as e:
            if "unexpected keyword argument 'tools'" in str(e):
                # Try without tools parameter (older versions)
                self.react = ReAct(signature=GenerateMemories)
            else:
                # Other errors - try basic initialization
                self.react = ReAct(GenerateMemories)

        # Store the maximum reasoning steps for reference
        self.max_reasoning_steps = max_reasoning_steps

    def forward(self, context, user_name):
        """
        Process the conversation context to generate memories

        Args:
            context: The conversation transcript
            user_name: The user's name

        Returns:
            A GenerateMemories object containing the memories
        """
        # If in dummy mode, return some demo memories
        if DUMMY_MODE:
            if "japan" in context.lower():
                return GenerateMemories(
                    context=context,
                    user_name=user_name,
                    interesting_memories=[
                        f"{user_name} visited Tokyo, Kyoto, and Osaka in Japan",
                        f"{user_name} enjoyed the food in Tokyo",
                    ],
                    system_memories=[
                        f"{user_name} wants better photo tagging features",
                        "User is trying to organize photos by city",
                    ],
                )
            else:
                return GenerateMemories(
                    context=context,
                    user_name=user_name,
                    interesting_memories=[f"{user_name} mentioned topic X", f"{user_name} expressed preference for Y"],
                    system_memories=[
                        "User has specific preferences about app features",
                        "User communicates in a detailed manner",
                    ],
                )

        # Check if model is configured
        if not MODEL_CONFIGURED:
            return GenerateMemories(
                context=context,
                user_name=user_name,
                interesting_memories=["ERROR: OpenAI API key not configured properly"],
                system_memories=["ERROR: OpenAI API key not configured properly"],
            )

        try:
            # Generate memories using ReAct's reasoning capabilities
            result = self.react(context=context, user_name=user_name)

            # Log the result to Langfuse for tracking
            trace_id = log_to_langfuse(
                input={"context": context, "user_name": user_name},
                output={"interesting_memories": result.interesting_memories, "system_memories": result.system_memories},
            )

            return result
        except Exception as e:
            print(f"\033[91mError generating memories: {e}\033[0m")
            return GenerateMemories(
                context=context,
                user_name=user_name,
                interesting_memories=[f"Error: {str(e)}"],
                system_memories=["Error occurred during memory generation"],
            )


# Allow direct testing when file is run
if __name__ == "__main__":
    if not MODEL_CONFIGURED and not DUMMY_MODE:
        print("Cannot run test: OpenAI API key not configured.")
        sys.exit(1)

    # Simple test case
    test_context = """
    User: Hi, I'm Alex. I've been trying to organize my photos from my trip to Japan last year.
    Assistant: Hello Alex! I'd be happy to help you organize your Japan trip photos. What kind of organization did you have in mind?
    User: I was thinking of grouping them by city. I visited Tokyo, Kyoto, and Osaka. Tokyo was my favorite because of the food.
    Assistant: That sounds like a great approach! Creating folders for Tokyo, Kyoto, and Osaka would work well. What was your favorite food in Tokyo?
    User: I loved the ramen at this small shop in Shinjuku. I wish the app had better tagging features though.
    """

    memory_program = MemoryReActProgram()
    result = memory_program(test_context, "Alex")

    print("Interesting Memories:")
    for mem in result.interesting_memories:
        print(f"- {mem}")

    print("\nSystem Memories:")
    for mem in result.system_memories:
        print(f"- {mem}")
