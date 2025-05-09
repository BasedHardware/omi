#!/usr/bin/env python3

import argparse
import uuid
from datetime import datetime, timezone

# Import required models and database functions
from models.memories import Memory, MemoryDB, MemoryCategory
import database.memories as memories_db
from database._client import document_id_from_seed

def create_test_memories(uid, num_memories=5, manually_added=True):
    """
    Create test memories for a user

    Parameters:
        uid (str): User ID
        num_memories (int): Number of memories to create (max 10)
        manually_added (bool): Whether to mark memories as manually added

    Returns:
        list: Created memory objects
    """
    test_memories = []
    categories = [
        MemoryCategory.core,
        MemoryCategory.hobbies,
        MemoryCategory.lifestyle,
        MemoryCategory.interests,
        MemoryCategory.work,
        MemoryCategory.skills,
        MemoryCategory.learnings,
        MemoryCategory.habits,
        MemoryCategory.other
    ]

    sample_contents = [
        "I enjoy hiking in the mountains every weekend",
        "I've been learning to play the piano for 2 years",
        "I prefer working early in the morning around 6 AM",
        "My favorite food is sushi, especially salmon nigiri",
        "I'm interested in quantum physics and read books about it",
        "I'm allergic to peanuts and need to avoid them",
        "I graduated from MIT with a computer science degree",
        "I've traveled to 15 different countries in the past 5 years",
        "I meditate for 20 minutes every morning to start my day",
        "My goal is to run a marathon before turning 40"
    ]

    print(f"Creating {min(num_memories, len(sample_contents))} test memories for user {uid}")

    for i in range(min(num_memories, len(sample_contents))):
        content = sample_contents[i]
        category = categories[i % len(categories)]
        visibility = "public" if i % 2 == 0 else "private"

        # Create Memory object
        memory = Memory(
            content=content,
            category=category,
            visibility=visibility
        )

        # Generate a unique conversation ID
        conversation_id = str(uuid.uuid4())

        # Convert to MemoryDB object
        memory_db = MemoryDB(
            id=document_id_from_seed(memory.content),
            uid=uid,
            content=memory.content,
            category=memory.category,
            tags=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            conversation_id=conversation_id,
            manually_added=manually_added,
            user_review=True if manually_added else None,
            reviewed=True if manually_added else False,
            visibility=memory.visibility,
        )

        # Calculate scoring
        memory_db.scoring = MemoryDB.calculate_score(memory_db)

        # Save to database
        memories_db.create_memory(uid, memory_db.dict())

        print(f"  Created memory: {memory.content} (Category: {memory.category}, Visibility: {memory.visibility})")
        test_memories.append(memory_db)

    return test_memories

def main():
    parser = argparse.ArgumentParser(description='Create mock memories for testing')
    parser.add_argument('--uid', type=str, required=True, help='User ID to create memories for')
    parser.add_argument('--count', type=int, default=5, help='Number of memories to create (max 10, default: 5)')
    parser.add_argument('--manual', action='store_true', help='Mark memories as manually added')

    args = parser.parse_args()

    if args.count > 10:
        print("Warning: Maximum allowed memories is 10. Setting count to 10.")
        args.count = 10

    try:
        memories = create_test_memories(args.uid, args.count, args.manual)
        print(f"Successfully created {len(memories)} test memories for user {args.uid}")
    except Exception as e:
        print(f"Error creating test memories: {e}")

if __name__ == "__main__":
    main()