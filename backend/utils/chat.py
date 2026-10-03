<content>
from backend.models.chat import MessageConversation

# ... (other imports and code) ...

def process_message(...) -> ...:
    # ... (existing code) ...
    
    # Replace raw dictionary comprehension with safe_build_many
    memories = ...  # existing memories list
    try:
        processed_memories = MessageConversation.safe_build_many(memories)
    except Exception as e:
        # Log the error but continue with empty list to prevent crash
        logger.error(f"Error processing memories: {str(e)}")
        processed_memories = []
    
    # ... (rest of the function using processed_memories) ...
</content>