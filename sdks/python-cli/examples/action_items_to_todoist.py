"""
Example: Convert OMI Action Items to Todoist Tasks

This script demonstrates how to use the OMI Python SDK to fetch action items
and create corresponding tasks in Todoist.

Prerequisites:
    1. Install dependencies: pip install -r requirements.txt
    2. Set environment variables:
       - OMI_API_KEY: Your OMI API key
       - TODOIST_API_KEY: Your Todoist API key
       - TODOIST_PROJECT_ID: (Optional) Specific project ID to add tasks to

Usage:
    python action_items_to_todoist.py
"""

import os
import sys
import json
import logging
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:
    logger.error("requests library not found. Please install it using: pip install requests")
    sys.exit(1)

# Try to import OMI SDK if available, otherwise use direct API calls
try:
    from omi_sdk import OMI
    OMI_SDK_AVAILABLE = True
except ImportError:
    OMI_SDK_AVAILABLE = False
    logger.warning("OMI SDK not installed. Using direct API calls.")


class TodoistClient:
    """Simple client for interacting with the Todoist API."""
    
    BASE_URL = "https://api.todoist.com/rest/v2"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def create_task(self, title: str, description: str = "", project_id: Optional[int] = None, 
                    due_string: Optional[str] = None, priority: int = 1) -> Dict[str, Any]:
        """
        Create a new task in Todoist.
        
        Args:
            title: The title of the task
            description: The description of the task
            project_id: Optional project ID to assign the task to
            due_string: Optional due date string (e.g., "2024-01-15")
            priority: Priority level (1=low, 2=medium, 3=high, 4=urgent)
            
        Returns:
            The created task object
        """
        url = f"{self.BASE_URL}/tasks"
        
        payload = {
            "content": title,
            "description": description,
            "priority": priority
        }
        
        if project_id:
            payload["project_id"] = project_id
        if due_string:
            payload["due_string"] = due_string
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        
        logger.info(f"Created Todoist task: {title}")
        return response.json()
    
    def get_projects(self) -> List[Dict[str, Any]]:
        """Fetch all projects from Todoist."""
        url = f"{self.BASE_URL}/projects"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()


class OMIActionItemFetcher:
    """Fetches action items from OMI."""
    
    def __init__(self, api_key: str, use_sdk: bool = True):
        self.api_key = api_key
        self.use_sdk = use_sdk and OMI_SDK_AVAILABLE
        
        if self.use_sdk:
            self.client = OMI(api_key=api_key)
        else:
            self.base_url = "https://api.omi.me/v1"
            self.headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
    
    def fetch_action_items(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch recent action items from OMI.
        
        Args:
            limit: Maximum number of action items to fetch
            
        Returns:
            List of action item dictionaries
        """
        if self.use_sdk:
            try:
                # Assuming OMI SDK has a method to fetch action items
                # This is a placeholder - adjust based on actual SDK API
                action_items = self.client.get_action_items(limit=limit)
                return action_items
            except Exception as e:
                logger.error(f"Error fetching action items via SDK: {e}")
                return []
        else:
            url = f"{self.base_url}/action-items"
            params = {"limit": limit}
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Handle different response formats
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "items" in data:
                return data["items"]
            else:
                logger.warning(f"Unexpected response format: {type(data)}")
                return []


def map_action_item_to_todoist(action_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map an OMI action item to a Todoist task payload.
    
    Args:
        action_item: The OMI action item dictionary
        
    Returns:
        Dictionary with Todoist task fields
    """
    # Extract relevant fields from OMI action item
    title = action_item.get("title", "Untitled Action Item")
    description = action_item.get("description", "")
    
    # Add metadata to description
    metadata_lines = []
    if "source" in action_item:
        metadata_lines.append(f"Source: {action_item['source']}")
    if "created_at" in action_item:
        metadata_lines.append(f"Created: {action_item['created_at']}")
    if "priority" in action_item:
        metadata_lines.append(f"Priority: {action_item['priority']}")
    
    if metadata_lines:
        metadata_section = "\n".join(metadata_lines)
        if description:
            description = f"{description}\n\n---\n{metadata_section}"
        else:
            description = metadata_section
    
    # Map priority (OMI priority to Todoist priority)
    omi_priority = action_item.get("priority", "medium")
    priority_map = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "urgent": 4
    }
    todoist_priority = priority_map.get(omi_priority, 2)
    
    # Extract due date if available
    due_string = None
    if "due_date" in action_item:
        due_string = action_item["due_date"]
    elif "deadline" in action_item:
        due_string = action_item["deadline"]
    
    return {
        "title": title,
        "description": description,
        "priority": todoist_priority,
        "due_string": due_string
    }


def main():
    """Main function to fetch OMI action items and create Todoist tasks."""
    
    # Get API keys from environment
    omi_api_key = os.getenv("OMI_API_KEY")
    todoist_api_key = os.getenv("TODOIST_API_KEY")
    todoist_project_id = os.getenv("TODOIST_PROJECT_ID")
    
    if not omi_api_key:
        logger.error("OMI_API_KEY environment variable not set.")
        sys.exit(1)
    
    if not todoist_api_key:
        logger.error("TODOIST_API_KEY environment variable not set.")
        sys.exit(1)
    
    # Initialize clients
    omi_fetcher = OMIActionItemFetcher(api_key=omi_api_key)
    todoist_client = TodoistClient(api_key=todoist_api_key)
    
    # Fetch action items
    logger.info("Fetching action items from OMI...")
    action_items = omi_fetcher.fetch_action_items(limit=10)
    
    if not action_items:
        logger.info("No action items found.")
        return
    
    logger.info(f"Found {len(action_items)} action items.")
    
    # Create Todoist tasks
    created_tasks = []
    for action_item in action_items:
        try:
            task_payload = map_action_item_to_todoist(action_item)
            
            if todoist_project_id:
                task_payload["project_id"] = int(todoist_project_id)
            
            created_task = todoist_client.create_task(**task_payload)
            created_tasks.append(created_task)
            
        except Exception as e:
            logger.error(f"Failed to create task for action item: {e}")
            continue
    
    # Summary
    logger.info(f"Successfully created {len(created_tasks)} Todoist tasks.")
    
    # Print summary to console
    print("\n" + "=" * 50)
    print("ACTION ITEMS TO TODOIST - SUMMARY")
    print("=" * 50)
    print(f"Total action items fetched: {len(action_items)}")
    print(f"Tasks created in Todoist: {len(created_tasks)}")
    print("=" * 50)
    
    if created_tasks:
        print("\nCreated tasks:")
        for task in created_tasks:
            print(f"  - {task.get('content', 'Unknown')}")


if __name__ == "__main__":
    main()
