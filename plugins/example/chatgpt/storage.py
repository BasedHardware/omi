import json
import os
from typing import Dict, Optional
from models import Memory
from datetime import datetime

# Helper function for logging with timestamps
def log_with_timestamp(message: str):
    """Log a message with the current timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Millisecond precision
    print(f"[{timestamp}] {message}")

# Define the storage directory
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
log_with_timestamp(f"Using data directory: {DATA_DIR}")

# In-memory storage for testing (temporary)
# Structure: {uid: {memory_id: Memory}}
MEMORY_STORE: Dict[str, Dict[str, Memory]] = {}

# Load existing memories from disk
def load_memories_from_disk():
    """Load all memories from disk into memory"""
    global MEMORY_STORE
    
    if not os.path.exists(DATA_DIR):
        log_with_timestamp(f"Data directory {DATA_DIR} does not exist, creating it")
        os.makedirs(DATA_DIR, exist_ok=True)
        return
    
    # Iterate through user directories
    for user_dir in os.listdir(DATA_DIR):
        user_path = os.path.join(DATA_DIR, user_dir)
        if os.path.isdir(user_path):
            uid = user_dir
            MEMORY_STORE[uid] = {}
            
            # Load each memory file
            for memory_file in os.listdir(user_path):
                if memory_file.endswith('.json'):
                    memory_id = memory_file[:-5]  # Remove .json extension
                    file_path = os.path.join(user_path, memory_file)
                    
                    try:
                        with open(file_path, 'r') as f:
                            memory_data = json.load(f)
                            memory = Memory(**memory_data)
                            MEMORY_STORE[uid][memory_id] = memory
                            log_with_timestamp(f"Loaded memory {memory_id} for user {uid} from disk")
                    except Exception as e:
                        log_with_timestamp(f"Error loading memory file {file_path}: {str(e)}")

# Initialize by loading from disk
load_memories_from_disk()

def store_memory(uid: str, memory_id: str, memory: Memory) -> None:
    """
    Store memory data in memory store and on disk
    
    Args:
        uid: User ID
        memory_id: Unique identifier for the memory
        memory: Memory object to store
    """
    # Store in memory
    if uid not in MEMORY_STORE:
        MEMORY_STORE[uid] = {}
    
    MEMORY_STORE[uid][memory_id] = memory
    
    # Store on disk
    user_dir = os.path.join(DATA_DIR, uid)
    os.makedirs(user_dir, exist_ok=True)
    
    file_path = os.path.join(user_dir, f"{memory_id}.json")
    
    try:
        # Convert to dict and save as JSON
        memory_dict = memory.dict()
        with open(file_path, 'w') as f:
            json.dump(memory_dict, f, indent=2)
        log_with_timestamp(f"Stored memory {memory_id} for user {uid} to disk at {file_path}")
    except Exception as e:
        log_with_timestamp(f"Error saving memory to disk: {str(e)}")
    
    log_with_timestamp(f"Stored memory {memory_id} for user {uid}")

def get_memory(uid: str, memory_id: str) -> Optional[Memory]:
    """
    Retrieve a specific memory by ID
    
    Args:
        uid: User ID
        memory_id: Memory ID to retrieve
        
    Returns:
        Memory object if found, None otherwise
    """
    if uid not in MEMORY_STORE or memory_id not in MEMORY_STORE[uid]:
        return None
    
    return MEMORY_STORE[uid][memory_id]

def get_memories_by_uid(uid: str) -> Dict[str, Memory]:
    """
    Get all memories for a specific user
    
    Args:
        uid: User ID
        
    Returns:
        Dictionary of memory_id to Memory objects
    """
    if uid not in MEMORY_STORE:
        return {}
    
    return MEMORY_STORE[uid]

def delete_memory(uid: str, memory_id: str) -> bool:
    """
    Delete a memory by ID from memory and disk
    
    Args:
        uid: User ID
        memory_id: Memory ID to delete
        
    Returns:
        True if deleted, False if not found
    """
    if uid not in MEMORY_STORE or memory_id not in MEMORY_STORE[uid]:
        return False
    
    # Delete from memory
    del MEMORY_STORE[uid][memory_id]
    
    # Delete from disk
    file_path = os.path.join(DATA_DIR, uid, f"{memory_id}.json")
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            log_with_timestamp(f"Deleted memory file {file_path}")
        except Exception as e:
            log_with_timestamp(f"Error deleting memory file {file_path}: {str(e)}")
    
    return True

# TODO: Implement Supabase storage when ready
# Below are placeholder functions for Supabase implementation

def init_supabase_client():
    """Initialize Supabase client when ready to migrate"""
    # from supabase import create_client
    # url = os.environ.get("SUPABASE_URL")
    # key = os.environ.get("SUPABASE_KEY")
    # return create_client(url, key)
    pass

def store_memory_supabase(uid: str, memory_id: str, memory: Memory) -> None:
    """
    Store memory in Supabase
    
    This will be implemented when ready to switch from in-memory to Supabase
    """
    # supabase = init_supabase_client()
    # memory_data = {
    #     "id": memory_id,
    #     "user_id": uid,
    #     "memory": memory.json(),
    #     "created_at": memory.created_at.isoformat()
    # }
    # supabase.table("memories").insert(memory_data).execute()
    pass

def get_memory_supabase(uid: str, memory_id: str) -> Optional[Memory]:
    """
    Get memory from Supabase
    
    This will be implemented when ready to switch from in-memory to Supabase
    """
    # supabase = init_supabase_client()
    # response = supabase.table("memories").select("*").eq("id", memory_id).eq("user_id", uid).execute()
    # if len(response.data) == 0:
    #     return None
    # memory_data = response.data[0]
    # return Memory.parse_raw(memory_data["memory"])
    pass

def get_memories_by_uid_supabase(uid: str) -> Dict[str, Memory]:
    """
    Get all memories for user from Supabase
    
    This will be implemented when ready to switch from in-memory to Supabase
    """
    # supabase = init_supabase_client()
    # response = supabase.table("memories").select("*").eq("user_id", uid).execute()
    # memories = {}
    # for item in response.data:
    #     memory = Memory.parse_raw(item["memory"])
    #     memories[item["id"]] = memory
    # return memories
    pass 