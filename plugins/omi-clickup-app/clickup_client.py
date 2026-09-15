import os
from datetime import datetime
import requests
from typing import Optional, List, Dict, Tuple
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
                params={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"🔍 OAuth Response: {data}", flush=True)
                
                return {
                    "access_token": data.get("access_token"),
                    "token_type": data.get("token_type", "Bearer")
                }
            else:
                raise Exception(f"Token exchange failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"❌ Token exchange error: {e}", flush=True)
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
            print(f"❌ Error getting user: {e}", flush=True)
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
            print(f"❌ Error getting workspaces: {e}", flush=True)
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
            print(f"❌ Error getting spaces: {e}", flush=True)
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
            print(f"❌ Error getting lists: {e}", flush=True)
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
            print(f"❌ Error getting members: {e}", flush=True)
            return []

    @staticmethod
    def _coerce_assignee_ids(assignees) -> List[int]:
        """
        Coerce raw assignee values into ClickUp user IDs (positive integers).

        The AI extractor and the Omi backend can hand over member names, JSON
        nulls, "None"/"null" sentinel strings, or floats instead of numeric
        IDs; int() on any of those raises and would abort task creation.
        Invalid tokens are skipped and the result is deduplicated, preserving
        order. Never raises.
        """
        if not assignees:
            return []
        # A lone value instead of a list is coerced rather than iterated
        # char-by-char (a bare string) or crashing (a bare int).
        if not isinstance(assignees, (list, tuple, set)):
            assignees = [assignees]

        user_ids = []
        for raw in assignees:
            # bool is an int subclass but is never a user ID
            if raw is None or isinstance(raw, bool):
                continue
            if isinstance(raw, int):
                user_id = raw
            elif isinstance(raw, float):
                if not raw.is_integer():
                    continue
                user_id = int(raw)
            elif isinstance(raw, str):
                token = raw.strip()
                if not token or token.lower() in ("none", "null", "nil"):
                    continue
                if not token.isdigit():
                    continue
                user_id = int(token)
            else:
                continue
            if user_id > 0 and user_id not in user_ids:
                user_ids.append(user_id)
        return user_ids

    @staticmethod
    def _coerce_priority(priority) -> Optional[int]:
        """
        Coerce a raw priority onto ClickUp's 1-4 scale.

        Returns None for anything that is not a usable integer in range, so a
        wrong-typed or out-of-range value drops the field instead of being
        forwarded to ClickUp (where it would 400 the request or silently
        misbehave). Never raises.
        """
        # bool is an int subclass but "priority: true" is not a priority
        if priority is None or isinstance(priority, bool):
            return None
        if isinstance(priority, int):
            value = priority
        elif isinstance(priority, float):
            if not priority.is_integer():
                return None
            value = int(priority)
        elif isinstance(priority, str):
            token = priority.strip()
            if not token.isdigit():
                return None
            value = int(token)
        else:
            return None
        return value if 1 <= value <= 4 else None

    @staticmethod
    def _coerce_due_date_ms(due_date, tz) -> Tuple[Optional[int], bool]:
        """
        Coerce a raw due date into (Unix milliseconds timestamp, has_time).

        Accepts ISO strings with or without a time component and numeric
        millisecond timestamps (int, float, digit string) — the form ClickUp
        stores natively. A numeric input denotes an exact instant, so it
        reports has_time=True. Returns (None, False) for values that carry no
        interpretable date; malformed ISO strings still raise for the caller
        to log. Never raises on wrong-typed input alone.
        """
        # bool is an int subclass but never a timestamp
        if due_date is None or isinstance(due_date, bool):
            return None, False

        if isinstance(due_date, (int, float)):
            timestamp = int(due_date)
            return (timestamp, True) if timestamp > 0 else (None, False)

        if not isinstance(due_date, str):
            return None, False

        token = due_date.strip()
        if not token:
            return None, False

        if token.isdigit():
            timestamp = int(token)
            return (timestamp, True) if timestamp > 0 else (None, False)

        # ISO format: 'T' separates a full datetime from a bare date
        has_time = 'T' in token
        if has_time:
            dt_naive = datetime.fromisoformat(token.replace('Z', ''))
        else:
            # Just a date — set time to end of day
            dt_naive = datetime.fromisoformat(token + 'T23:59:59')
        dt = tz.localize(dt_naive) if tz else dt_naive
        return int(dt.timestamp() * 1000), has_time

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
            priority: Priority coerced to ClickUp's 1-4 scale (1=urgent, 2=high, 3=normal, 4=low); invalid values are ignored
            status: Optional status name
            due_date: Optional due date — ISO format ("2025-09-15" or "2025-09-15T17:00:00") or Unix timestamp in milliseconds (int, float, or digit string); unparseable values are ignored
            assignees: Optional user IDs — non-numeric tokens are skipped rather than failing task creation
            
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
                priority_value = self._coerce_priority(priority)
                if priority_value is not None:
                    task_data["priority"] = priority_value
                else:
                    print(f"⚠️  Ignoring invalid priority {priority!r} (expected 1-4)", flush=True)

            if status:
                task_data["status"] = status

            assignee_ids = self._coerce_assignee_ids(assignees)
            if assignee_ids:
                # ClickUp expects list of user IDs as integers
                task_data["assignees"] = assignee_ids
                print(f"👥 Assignees: {assignee_ids}", flush=True)
            elif assignees:
                # Values arrived but none resolved to an ID — continue
                # unassigned rather than aborting task creation.
                print(f"⚠️  No usable assignee IDs in {assignees!r}; creating task unassigned", flush=True)

            if due_date:
                # ClickUp stores due dates as Unix milliseconds. ISO strings
                # (with or without time) and numeric ms timestamps are
                # accepted; anything else is dropped with a warning instead of
                # failing task creation.
                # Try to use timezone if pytz is available
                try:
                    import pytz
                    tz = pytz.timezone(timezone)
                except (ImportError, Exception):
                    # Fallback to no timezone (naive datetime)
                    tz = None

                try:
                    due_timestamp, has_time = self._coerce_due_date_ms(due_date, tz)
                except Exception as e:
                    print(f"⚠️  Could not parse due date '{due_date}': {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                    due_timestamp, has_time = None, False

                if due_timestamp is not None:
                    task_data["due_date"] = due_timestamp
                    # CRITICAL: due_date_time=true tells ClickUp to display the
                    # time, not just the date
                    task_data["due_date_time"] = has_time
                    if has_time:
                        print(f"📅 Due date with TIME: {due_date} ({timezone if tz else 'system'}) → {due_timestamp}", flush=True)
                    else:
                        print(f"📅 Due date (no time): {due_date} ({timezone if tz else 'system'}) → {due_timestamp}", flush=True)
                else:
                    print(f"⚠️  Ignoring invalid due date {due_date!r}", flush=True)
            
            print(f"📤 Creating task: {name} in list {list_id}", flush=True)
            
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
                error_msg = f"{response.status_code} - {response.text}"
                print(f"❌ Error creating task: {error_msg}", flush=True)
                return {
                    "success": False,
                    "error": error_msg
                }
                
        except Exception as e:
            print(f"❌ Error creating task: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }

