import os
import requests
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()


class ClickUpClient:
    """Handles ClickUp API interactions."""
    
    def __init__(self):
        self.client_id = os.getenv("CLICKUP_CLIENT_ID")
        self.client_secret = os.getenv("CLICKUP_CLIENT_SECRET")
        self.base_url = "https://api.clickup.com/api/v2"
    
    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Generate ClickUp OAuth authorization URL."""
        auth_url = (
            f"https://app.clickup.com/api?"
            f"client_id={self.client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"state={state}"
        )
        return auth_url
    
    def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for access token."""
        try:
            response = requests.post(
                "https://api.clickup.com/api/v2/oauth/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                
                return {
                    "access_token": data.get("access_token"),
                    "token_type": data.get("token_type", "Bearer")
                }
            else:
                raise Exception(f"Token exchange failed: {response.status_code}")
                
        except requests.RequestException as e:
            print(f"❌ Token exchange error: {type(e).__name__}", flush=True)
            raise Exception(f"Token exchange request failed: {type(e).__name__}") from e
        except Exception:
            raise
    
    def get_authorized_user(self, access_token: str) -> dict:
        """Get the authenticated user's information."""
        try:
            headers = {"Authorization": access_token}
            response = requests.get(
                f"{self.base_url}/user",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                user = data.get("user", {})
                return {
                    "id": user.get("id"),
                    "username": user.get("username"),
                    "email": user.get("email")
                }
            else:
                print(f"❌ Error getting user: {response.status_code}", flush=True)
                return {}
                
        except Exception as e:
            print(f"❌ Error getting user: {type(e).__name__}", flush=True)
            return {}
    
    def get_workspaces(self, access_token: str) -> List[Dict]:
        """Get all teams/workspaces the user has access to."""
        try:
            headers = {"Authorization": access_token}
            response = requests.get(
                f"{self.base_url}/team",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                teams = data.get("teams", [])
                
                workspaces = []
                for team in teams:
                    workspaces.append({
                        "id": team.get("id"),
                        "name": team.get("name"),
                        "color": team.get("color"),
                        "avatar": team.get("avatar")
                    })
                
                return workspaces
            else:
                print(f"❌ Error getting workspaces: {response.status_code}", flush=True)
                return []
                
        except Exception as e:
            print(f"❌ Error getting workspaces: {type(e).__name__}", flush=True)
            return []
    
    def get_spaces(self, access_token: str, team_id: str) -> List[Dict]:
        """Get all spaces in a workspace."""
        try:
            headers = {"Authorization": access_token}
            response = requests.get(
                f"{self.base_url}/team/{team_id}/space",
                headers=headers,
                params={"archived": "false"}
            )
            
            if response.status_code == 200:
                data = response.json()
                spaces = data.get("spaces", [])
                
                space_list = []
                for space in spaces:
                    space_list.append({
                        "id": space.get("id"),
                        "name": space.get("name"),
                        "private": space.get("private", False),
                        "color": space.get("color")
                    })
                
                return space_list
            else:
                print(f"❌ Error getting spaces: {response.status_code}", flush=True)
                return []
                
        except Exception as e:
            print(f"❌ Error getting spaces: {type(e).__name__}", flush=True)
            return []
    
    def get_lists(self, access_token: str, space_id: str) -> List[Dict]:
        """Get all lists in a space."""
        try:
            headers = {"Authorization": access_token}
            response = requests.get(
                f"{self.base_url}/space/{space_id}/list",
                headers=headers,
                params={"archived": "false"}
            )
            
            if response.status_code == 200:
                data = response.json()
                lists = data.get("lists", [])
                
                list_data = []
                for lst in lists:
                    list_data.append({
                        "id": lst.get("id"),
                        "name": lst.get("name"),
                        "space_id": space_id,
                        "folder_id": lst.get("folder", {}).get("id") if lst.get("folder") else None
                    })
                
                return list_data
            else:
                print(f"❌ Error getting lists: {response.status_code}", flush=True)
                return []
                
        except Exception as e:
            print(f"❌ Error getting lists: {type(e).__name__}", flush=True)
            return []
    
    def get_folders(self, access_token: str, space_id: str) -> List[Dict]:
        """
        Get all folders in a space. ClickUp embeds each folder's lists in this
        response, so it is one call per space rather than one per folder.

        Unlike the sibling getters this raises on failure: get_all_lists has to
        tell "no folders" from "the folder request failed", or a transient error
        would silently drop every folder list from the picker.
        """
        headers = {"Authorization": access_token}
        response = requests.get(
            f"{self.base_url}/space/{space_id}/folder",
            headers=headers,
            params={"archived": "false"}
        )

        if response.status_code != 200:
            raise Exception(f"Error getting folders: {response.status_code} - {response.text}")

        return response.json().get("folders", [])

    def get_folder_lists(self, access_token: str, folder_id: str) -> List[Dict]:
        """
        Get the lists inside one folder. Only needed when a folder from
        get_folders arrived without its embedded lists. Raises on failure,
        for the same reason as get_folders.
        """
        headers = {"Authorization": access_token}
        response = requests.get(
            f"{self.base_url}/folder/{folder_id}/list",
            headers=headers,
            params={"archived": "false"}
        )

        if response.status_code != 200:
            raise Exception(f"Error getting folder lists: {response.status_code} - {response.text}")

        return response.json().get("lists", [])

    def get_all_lists(self, access_token: str, team_id: str) -> List[Dict]:
        """
        Get every list across all spaces in a workspace.

        GET /space/{id}/list returns only folderless lists — ClickUp v2 keeps
        lists that live inside a folder behind GET /space/{id}/folder — so each
        space's folders are walked as well. Folder lists carry `folder_name` so
        a picker can show "Folder / List"; `name` stays the bare list name
        because task_detector matches spoken list names against it.

        Returns [] if any folder request fails: a picker silently missing whole
        folders misleads more than an empty one.
        """
        all_lists = []
        
        # Get all spaces
        spaces = self.get_spaces(access_token, team_id)
        
        # Get lists for each space
        for space in spaces:
            # Folderless lists
            lists = self.get_lists(access_token, space["id"])
            for lst in lists:
                lst["space_name"] = space["name"]
                all_lists.append(lst)

            # Lists inside folders
            try:
                for folder in self.get_folders(access_token, space["id"]):
                    folder_lists = folder.get("lists")
                    if folder_lists is None:
                        folder_lists = self.get_folder_lists(access_token, folder["id"])
                    for lst in folder_lists:
                        all_lists.append({
                            "id": lst.get("id"),
                            "name": lst.get("name"),
                            "space_id": space["id"],
                            "space_name": space["name"],
                            "folder_id": folder.get("id"),
                            "folder_name": folder.get("name")
                        })
            except Exception as e:
                print(f"❌ Error getting folder lists for space {space['id']}: {e}", flush=True)
                return []
        
        return all_lists
    
    def get_workspace_members(self, access_token: str, team_id: str) -> List[Dict]:
        """Get all members in a workspace."""
        try:
            headers = {"Authorization": access_token}
            response = requests.get(
                f"{self.base_url}/team/{team_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                team = data.get("team", {})
                members_data = team.get("members", [])
                
                members = []
                for member in members_data:
                    user = member.get("user", {})
                    members.append({
                        "id": user.get("id"),
                        "username": user.get("username"),
                        "email": user.get("email"),
                        "initials": user.get("initials", ""),
                        "color": user.get("color"),
                        "profilePicture": user.get("profilePicture")
                    })
                
                print(f"✅ Found {len(members)} workspace members", flush=True)
                return members
            else:
                print(f"❌ Error getting members: {response.status_code}", flush=True)
                return []
                
        except Exception as e:
            print(f"❌ Error getting members: {type(e).__name__}", flush=True)
            return []
    
    @staticmethod
    def _coerce_assignee_ids(assignees: Optional[List[Any]]) -> List[int]:
        """
        Safely extract and coerce integer ClickUp user IDs.
        Filters out invalid strings, None, whitespace, negative IDs, and non-numeric tokens
        without raising exceptions. Preserves unique IDs in order of appearance.
        """
        if not assignees:
            return []

        cleaned: List[int] = []
        seen = set()
        for item in assignees:
            if item is None or isinstance(item, (dict, list, set, bool)):
                continue
            try:
                if isinstance(item, str):
                    s = item.strip()
                    if not s or s.lower() == "none":
                        continue
                    val = int(s)
                elif isinstance(item, (int, float)):
                    val = int(item)
                else:
                    continue

                if val > 0 and val not in seen:
                    seen.add(val)
                    cleaned.append(val)
            except (ValueError, TypeError, OverflowError):
                continue
        return cleaned

    async def create_task(
        self,
        access_token: str,
        list_id: str,
        name: str,
        description: Optional[str] = None,
        priority: Optional[int] = None,
        status: Optional[str] = None,
        due_date: Optional[str] = None,
        timezone: str = "UTC",
        assignees: Optional[List[str]] = None
    ) -> Optional[dict]:
        """
        Create a task in ClickUp.
        
        Args:
            access_token: User's OAuth token
            list_id: ID of the list to create task in
            name: Task name/title
            description: Optional task description
            priority: Priority (1=urgent, 2=high, 3=normal, 4=low)
            status: Optional status name
            due_date: Optional due date in ISO format or Unix timestamp (milliseconds)
            
        Returns:
            Task data if successful, None otherwise
        """
        try:
            headers = {
                "Authorization": access_token,
                "Content-Type": "application/json"
            }
            
            # Build task data
            task_data = {
                "name": name
            }
            
            # Add description with "Created via Omi" footer
            if description:
                task_data["description"] = f"{description}\n\n--\nCreated via Omi"
            else:
                task_data["description"] = "Created via Omi"
            
            if priority is not None:
                try:
                    if isinstance(priority, bool):
                        raise ValueError("Priority cannot be boolean")
                    if isinstance(priority, float) and not priority.is_integer():
                        raise ValueError("Priority cannot be fractional float")
                    if isinstance(priority, str):
                        s = priority.strip()
                        if not s.isdigit() and not (s.startswith("-") and s[1:].isdigit()):
                            raise ValueError("Priority string must be integer")
                        p_val = int(s)
                    elif isinstance(priority, (int, float)):
                        p_val = int(priority)
                    else:
                        raise ValueError("Invalid priority type")

                    if 1 <= p_val <= 4:
                        task_data["priority"] = p_val
                    else:
                        print(f"⚠️  Priority {priority} outside valid range 1-4, omitting", flush=True)
                except (ValueError, TypeError, OverflowError):
                    print(f"⚠️  Non-numeric priority '{priority}' omitted", flush=True)
            
            if status:
                task_data["status"] = str(status).strip()
            
            if assignees:
                valid_assignees = self._coerce_assignee_ids(assignees)
                if valid_assignees:
                    task_data["assignees"] = valid_assignees
                    print(f"👥 Assignees: {valid_assignees}", flush=True)
                else:
                    print(f"⚠️  No valid integer assignee IDs found in: {assignees}", flush=True)
            
            if due_date is not None:
                from datetime import datetime
                try:
                    is_numeric_ts = False
                    due_timestamp = None
                    if isinstance(due_date, (int, float)) and not isinstance(due_date, bool):
                        due_timestamp = int(due_date)
                        is_numeric_ts = True
                    elif isinstance(due_date, str) and due_date.strip().isdigit():
                        due_timestamp = int(due_date.strip())
                        is_numeric_ts = True

                    if is_numeric_ts and due_timestamp is not None:
                        task_data["due_date"] = due_timestamp
                        task_data["due_date_time"] = True
                        print(f"📅 Due date (timestamp): {due_timestamp}", flush=True)
                    else:
                        due_str = str(due_date).strip()
                        # Try to use timezone if pytz is available
                        try:
                            import pytz
                            tz = pytz.timezone(timezone)
                        except (ImportError, Exception):
                            # Fallback to no timezone (naive datetime)
                            tz = None

                        # Check if time is included in the date string
                        has_time = 'T' in due_str

                        # Try parsing as ISO format
                        if has_time:
                            # Full datetime - preserve offset and normalize trailing Z
                            iso_str = due_str if not due_str.endswith('Z') else due_str[:-1] + '+00:00'
                            dt = datetime.fromisoformat(iso_str)
                            if dt.tzinfo is None and tz:
                                dt = tz.localize(dt)
                        else:
                            # Just date, set time to end of day
                            dt_naive = datetime.fromisoformat(due_str + 'T23:59:59')
                            if tz:
                                dt = tz.localize(dt_naive)
                            else:
                                dt = dt_naive

                        # Convert to Unix timestamp in milliseconds
                        due_timestamp = int(dt.timestamp() * 1000)
                        task_data["due_date"] = due_timestamp
                        task_data["due_date_time"] = has_time
                        print(f"📅 Due date ({'with TIME' if has_time else 'no time'}): {due_str} ({timezone if tz else 'system'}) → {due_timestamp}", flush=True)
                except Exception as e:
                    print(f"⚠️  Could not parse due date: {type(e).__name__}", flush=True)
            
            print(f"📤 Creating task in list {list_id} (name_len={len(name)})", flush=True)
            
            response = requests.post(
                f"{self.base_url}/list/{list_id}/task",
                headers=headers,
                json=task_data
            )
            
            if response.status_code == 200:
                data = response.json()
                task = data
                
                print(f"✅ Task created: {task.get('id')}", flush=True)
                
                return {
                    "success": True,
                    "task_id": task.get("id"),
                    "task_name": task.get("name"),
                    "task_url": task.get("url"),
                    "status": task.get("status", {}).get("status"),
                    "list_id": list_id
                }
            else:
                error_msg = f"HTTP {response.status_code}"
                print(f"❌ Error creating task: {error_msg}", flush=True)
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except Exception as e:
            print(f"❌ Error creating task: {type(e).__name__}", flush=True)
            return {
                "success": False,
                "error": type(e).__name__
            }

