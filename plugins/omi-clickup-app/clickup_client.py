import os
import requests
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()


def _safe_json(response) -> dict:
    """Safely extract JSON as dict from response or return empty dict on error/non-JSON."""
    try:
        data = response.json()
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {"data": data}
        return {}
    except Exception:
        return {}


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
                data = _safe_json(response)

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
                data = _safe_json(response)
                user = data.get("user") if isinstance(data.get("user"), dict) else {}
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
                data = _safe_json(response)
                raw_teams = data.get("teams")
                teams = raw_teams if isinstance(raw_teams, list) else []

                workspaces = []
                for team in teams:
                    if not isinstance(team, dict):
                        continue
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
                data = _safe_json(response)
                raw_spaces = data.get("spaces")
                spaces = raw_spaces if isinstance(raw_spaces, list) else []

                space_list = []
                for space in spaces:
                    if not isinstance(space, dict):
                        continue
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
                data = _safe_json(response)
                raw_lists = data.get("lists")
                lists = raw_lists if isinstance(raw_lists, list) else []

                list_data = []
                for lst in lists:
                    if not isinstance(lst, dict):
                        continue
                    folder_obj = lst.get("folder") if isinstance(lst.get("folder"), dict) else {}
                    list_data.append({
                        "id": lst.get("id"),
                        "name": lst.get("name"),
                        "space_id": space_id,
                        "folder_id": folder_obj.get("id") if folder_obj else None
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
            raise Exception(f"Error getting folders: {response.status_code}")

        data = _safe_json(response)
        folders = data.get("folders")
        if isinstance(folders, list):
            return [f for f in folders if isinstance(f, dict)]
        return []

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
            raise Exception(f"Error getting folder lists: {response.status_code}")

        data = _safe_json(response)
        lists = data.get("lists")
        if isinstance(lists, list):
            return [lst for lst in lists if isinstance(lst, dict)]
        return []

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
        for space in (spaces or []):
            if not isinstance(space, dict):
                continue
            space_id = space.get("id")
            space_name = space.get("name")
            if not space_id:
                continue

            # Folderless lists
            lists = self.get_lists(access_token, space_id)
            for lst in (lists or []):
                if not isinstance(lst, dict):
                    continue
                lst["space_name"] = space_name
                all_lists.append(lst)

            # Lists inside folders
            try:
                for folder in self.get_folders(access_token, space_id):
                    if not isinstance(folder, dict):
                        continue
                    folder_lists = folder.get("lists")
                    if not isinstance(folder_lists, list):
                        folder_lists = self.get_folder_lists(access_token, folder.get("id"))
                    for lst in (folder_lists or []):
                        if not isinstance(lst, dict):
                            continue
                        all_lists.append({
                            "id": lst.get("id"),
                            "name": lst.get("name"),
                            "space_id": space_id,
                            "space_name": space_name,
                            "folder_id": folder.get("id"),
                            "folder_name": folder.get("name")
                        })
            except Exception as e:
                print(f"❌ Error getting folder lists for space {space_id}: {e}", flush=True)
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
                data = _safe_json(response)
                team = data.get("team") if isinstance(data.get("team"), dict) else {}
                raw_members = team.get("members")
                members_data = raw_members if isinstance(raw_members, list) else []

                members = []
                for member in members_data:
                    if not isinstance(member, dict):
                        continue
                    user = member.get("user")
                    if not isinstance(user, dict) or not user.get("id"):
                        continue
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

    async def create_task(
        self,
        access_token: str,
        list_id: str,
        name: str,
        description: Optional[str] = None,
        priority: Optional[int] = None,
        status: Optional[str] = None,
        due_date: Optional[Any] = None,
        timezone: str = "UTC",
        assignees: Optional[List[Any]] = None
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
            task_data: dict = {
                "name": str(name or "").strip()
            }

            # Add description with "Created via Omi" footer
            if description:
                task_data["description"] = f"{description}\n\n--\nCreated via Omi"
            else:
                task_data["description"] = "Created via Omi"

            if priority is not None:
                try:
                    task_data["priority"] = int(priority)
                except (ValueError, TypeError):
                    pass

            if status:
                task_data["status"] = str(status)

            if assignees:
                # ClickUp expects list of user IDs as integers
                valid_assignees = []
                for user_id in assignees:
                    try:
                        if user_id is not None and str(user_id).strip():
                            valid_assignees.append(int(user_id))
                    except (ValueError, TypeError):
                        continue
                if valid_assignees:
                    task_data["assignees"] = valid_assignees
                    print(f"👥 Assignees: {valid_assignees}", flush=True)

            if due_date is not None:
                try:
                    if isinstance(due_date, (int, float)):
                        task_data["due_date"] = int(due_date)
                        task_data["due_date_time"] = True
                    elif isinstance(due_date, str) and due_date.strip():
                        due_str = due_date.strip()
                        if due_str.isdigit():
                            task_data["due_date"] = int(due_str)
                            task_data["due_date_time"] = True
                        else:
                            from datetime import datetime
                            try:
                                import pytz
                                tz = pytz.timezone(timezone)
                            except (ImportError, Exception):
                                tz = None

                            has_time = 'T' in due_str
                            if has_time:
                                dt_naive = datetime.fromisoformat(due_str.replace('Z', ''))
                                dt = tz.localize(dt_naive) if tz else dt_naive
                            else:
                                dt_naive = datetime.fromisoformat(due_str + 'T23:59:59')
                                dt = tz.localize(dt_naive) if tz else dt_naive

                            due_timestamp = int(dt.timestamp() * 1000)
                            task_data["due_date"] = due_timestamp
                            task_data["due_date_time"] = has_time
                            print(f"📅 Due date set: {due_timestamp} (has_time={has_time})", flush=True)
                except Exception as e:
                    print(f"⚠️  Could not parse due date: {type(e).__name__}", flush=True)

            print(f"📤 Creating task in list {list_id} (name_len={len(task_data['name'])})", flush=True)

            response = requests.post(
                f"{self.base_url}/list/{list_id}/task",
                headers=headers,
                json=task_data
            )

            if response.status_code == 200:
                data = _safe_json(response)
                task = data if isinstance(data, dict) else {}

                status_raw = task.get("status")
                if isinstance(status_raw, dict):
                    status_val = status_raw.get("status")
                elif isinstance(status_raw, str):
                    status_val = status_raw
                else:
                    status_val = None

                print(f"✅ Task created: {task.get('id')}", flush=True)

                return {
                    "success": True,
                    "task_id": task.get("id"),
                    "task_name": task.get("name"),
                    "task_url": task.get("url"),
                    "status": status_val,
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

