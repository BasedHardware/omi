"""
Simple storage with file persistence - survives server restarts!
Stores user OAuth tokens and selected repositories.
"""
from typing import Dict, Optional
from datetime import datetime
import json
import os

# Storage file paths - use /app/data for Railway persistence
STORAGE_DIR = os.getenv("STORAGE_DIR", os.path.dirname(os.path.abspath(__file__)))
# Check if we're on Railway (has /app/data volume)
if os.path.exists("/app/data"):
    STORAGE_DIR = "/app/data"
    print(f"Using persistent storage at: /app/data", flush=True)
else:
    STORAGE_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"Using local storage at: {STORAGE_DIR}", flush=True)

USERS_FILE = os.path.join(STORAGE_DIR, "users_data.json")

# In-memory storage
users: Dict[str, dict] = {}


def load_storage():
    """Load user data from file on startup."""
    global users
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
                print(f"Loaded {len(users)} users from storage")
    except Exception as e:
        print(f"Could not load users: {e}")


def save_users():
    """Save user data to file."""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, default=str, indent=2)
    except Exception as e:
        print(f"Could not save users: {e}")


# Load on module import
load_storage()


class SimpleUserStorage:
    """Store user OAuth tokens and repository preferences."""

    @staticmethod
    def save_user(
        uid: str,
        access_token: str,
        github_username: Optional[str] = None,
        selected_repo: Optional[str] = None,
        available_repos: Optional[list] = None
    ):
        """Save or update user data."""
        if uid not in users:
            users[uid] = {
                "uid": uid,
                "created_at": datetime.utcnow().isoformat()
            }

        users[uid].update({
            "access_token": access_token,
            "updated_at": datetime.utcnow().isoformat()
        })

        if github_username:
            users[uid]["github_username"] = github_username
        if selected_repo:
            users[uid]["selected_repo"] = selected_repo
        if available_repos is not None:
            users[uid]["available_repos"] = available_repos

        save_users()
        print(f"Saved data for user {uid[:10]}...")

    @staticmethod
    def update_repo_selection(uid: str, selected_repo: str):
        """Update user's selected repository."""
        if uid in users:
            users[uid]["selected_repo"] = selected_repo
            users[uid]["updated_at"] = datetime.utcnow().isoformat()
            save_users()
            print(f"Updated repo for {uid[:10]}... to {selected_repo}")
            return True
        return False

    @staticmethod
    def get_user(uid: str) -> Optional[dict]:
        """Get user by uid."""
        return users.get(uid)

    @staticmethod
    def is_authenticated(uid: str) -> bool:
        """Check if user is authenticated."""
        user = users.get(uid)
        return user is not None and user.get("access_token") is not None

    @staticmethod
    def has_selected_repo(uid: str) -> bool:
        """Check if user has selected a repository."""
        user = users.get(uid)
        return user is not None and user.get("selected_repo") is not None

    @staticmethod
    def save_agent_provider(uid: str, provider: str):
        """Save user's selected agent provider."""
        if uid in users:
            users[uid]["agent_provider"] = provider
            users[uid]["updated_at"] = datetime.utcnow().isoformat()
            save_users()
            print(f"Saved agent provider for {uid[:10]}...: {provider}")
            return True
        return False

    @staticmethod
    def get_agent_provider(uid: str) -> Optional[str]:
        """Get user's selected agent provider."""
        user = users.get(uid)
        return user.get("agent_provider") if user else None

    @staticmethod
    def save_agent_api_key(uid: str, provider: str, api_key: str):
        """Save user's API key for an agent provider."""
        if uid in users:
            if "agent_api_keys" not in users[uid]:
                users[uid]["agent_api_keys"] = {}
            users[uid]["agent_api_keys"][provider] = api_key
            users[uid]["updated_at"] = datetime.utcnow().isoformat()
            save_users()
            print(f"Saved {provider} key for {uid[:10]}...")
            return True
        return False

    @staticmethod
    def get_agent_api_key(uid: str, provider: str) -> Optional[str]:
        """Get user's API key for an agent provider."""
        user = users.get(uid)
        if not user:
            return None
        return user.get("agent_api_keys", {}).get(provider)

    @staticmethod
    def delete_agent_api_key(uid: str, provider: str):
        """Delete user's API key for an agent provider."""
        if uid in users and "agent_api_keys" in users[uid]:
            if provider in users[uid]["agent_api_keys"]:
                del users[uid]["agent_api_keys"][provider]
                users[uid]["updated_at"] = datetime.utcnow().isoformat()
                save_users()
                print(f"Deleted {provider} key for {uid[:10]}...")
                return True
        return False
