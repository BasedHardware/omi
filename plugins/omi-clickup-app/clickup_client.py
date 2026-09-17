import os
import requests
from typing import Optional, List, Dict, Any, Union
from dotenv import load_dotenv

load_dotenv()


class ClickUpClient:
    """Handles ClickUp API interactions."""

    def __init__(self):
        self.client_id = os.getenv("CLICKUP_CLIENT_ID")
        self.client_secret = os.getenv("CLICKUP_CLIENT_SECRET")
        self.base_url = "https://api.clickup.com/api/v2"

    @staticmethod
    def _safe_json(response: Any) -> dict:
        """
        Safely extract JSON dictionary from requests.Response.
        Guards against HTML 502/504 Bad Gateway pages, None, or non-dict payloads.
        """
        if response is None:
            return {}
        try:
            data = response.json()
            if isinstance(data, dict):
                return data
            return {"data": data}
        except Exception:
            return {}

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
                data = self._safe_json(response)
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
                data = self._safe_json(response)
                user = data.get("user")
                if not isinstance(user, dict):
                    user = {}
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
                data = self._safe_json(response)
                teams = data.get("teams", [])
                if not isinstance(teams, list):
                    teams = []

                workspaces = []
                for team in teams:
                    if isinstance(team, dict):
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
                data = self._safe_json(response)
                spaces = data.get("spaces", [])
                if not isinstance(spaces, list):
                    spaces = []

                space_list = []
                for space in spaces:
                    if isinstance(space, dict):
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
                data = self._safe_json(response)
                lists = data.get("lists", [])
                if not isinstance(lists, list):
                    lists = []

                list_data = []
                for lst in lists:
                    if isinstance(lst, dict):
                        folder = lst.get("folder")
                        folder_id = folder.get("id") if isinstance(folder, dict) else None
                        list_data.append({
                            "id": lst.get("id"),
                            "name": lst.get("name"),
                            "space_id": space_id,
                            "folder_id": folder_id
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

        folders = self._safe_json(response).get("folders", [])
        return folders if isinstance(folders, list) else []

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

        lists = self._safe_json(response).get("lists", [])
        return lists if isinstance(lists, list) else []

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
            if not isinstance(space, dict) or not space.get("id"):
                continue
            # Folderless lists
            lists = self.get_lists(access_token, space["id"])
            for lst in lists:
                if isinstance(lst, dict):
                    lst["space_name"] = space.get("name")
                    all_lists.append(lst)

            # Lists inside folders
            try:
                folders = self.get_folders(access_token, space["id"])
                for folder in folders:
                    if not isinstance(folder, dict):
                        continue
                    folder_lists = folder.get("lists")
                    if folder_lists is None and folder.get("id"):
                        folder_lists = self.get_folder_lists(access_token, folder["id"])
                    if isinstance(folder_lists, list):
                        for lst in folder_lists:
                            if isinstance(lst, dict):
                                all_lists.append({
                                    "id": lst.get("id"),
                                    "name": lst.get("name"),
                                    "space_id": space["id"],
                                    "space_name": space.get("name"),
                                    "folder_id": folder.get("id"),
                                    "folder_name": folder.get("name")
                                })
            except Exception as e:
                print(f"❌ Error getting folder lists for space {space.get('id')}: {e}", flush=True)
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
                data = self._safe_json(response)
                team = data.get("team", {})
                if not isinstance(team, dict):
                    team = {}
                members_data = team.get("members", [])
                if not isinstance(members_data, list):
                    members_data = []

                members = []
                for member in members_data:
                    if isinstance(member, dict):
                        user = member.get("user", {})
                        if isinstance(user, dict):
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
        due_date: Optional[Union[str, int, float]] = None,
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
            due_date: Optional due date in ISO format, numeric string, or Unix timestamp (ms)
            assignees: Optional list of assignee IDs

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
                "name": str(name) if name is not None else "Untitled Task"
            }

            # Add description with "Created via Omi" footer
            if description:
                task_data["description"] = f"{description}\n\n--\nCreated via Omi"
            else:
                task_data["description"] = "Created via Omi"

            if priority in [1, 2, 3, 4]:
                task_data["priority"] = priority

            if status:
                task_data["status"] = str(status)

            if assignees and isinstance(assignees, (list, tuple)):
                parsed_assignees = []
                for uid in assignees:
                    if uid is None:
                        continue
                    try:
                        parsed_assignees.append(int(uid))
                    except (ValueError, TypeError):
                        # Gracefully ignore non-numeric strings or invalid IDs
                        continue
                if parsed_assignees:
                    task_data["assignees"] = parsed_assignees
                    print(f"👥 Assignees: {parsed_assignees}", flush=True)

            if due_date is not None:
                from datetime import datetime
                try:
                    due_ts = None
                    has_time = False

                    # Check if already a number or numeric string
                    if isinstance(due_date, (int, float)):
                        due_ts = int(due_date)
                        has_time = True
                    elif isinstance(due_date, str) and due_date.strip().isdigit():
                        due_ts = int(due_date.strip())
                        has_time = True
                    elif isinstance(due_date, str):
                        due_str = due_date.strip()
                        has_time = ('T' in due_str or ':' in due_str)

                        try:
                            import pytz
                            tz = pytz.timezone(timezone)
                        except (ImportError, Exception):
                            tz = None

                        if has_time:
                            cleaned_str = due_str.replace('Z', '')
                            dt_naive = datetime.fromisoformat(cleaned_str)
                            dt = tz.localize(dt_naive) if tz else dt_naive
                        else:
                            dt_naive = datetime.fromisoformat(due_str + 'T23:59:59')
                            dt = tz.localize(dt_naive) if tz else dt_naive

                        due_ts = int(dt.timestamp() * 1000)

                    if due_ts is not None:
                        task_data["due_date"] = due_ts
                        task_data["due_date_time"] = has_time
                        print(f"📅 Due date timestamp → {due_ts} (has_time={has_time})", flush=True)

                except Exception as e:
                    print(f"⚠️  Could not parse due date: {type(e).__name__}", flush=True)

            print(f"📤 Creating task in list {list_id} (name_len={len(task_data['name'])})", flush=True)

            response = requests.post(
                f"{self.base_url}/list/{list_id}/task",
                headers=headers,
                json=task_data
            )

            if response.status_code == 200:
                data = self._safe_json(response)
                task = data if isinstance(data, dict) else {}

                print(f"✅ Task created: {task.get('id')}", flush=True)

                status_field = task.get("status")
                if isinstance(status_field, dict):
                    status_name = status_field.get("status")
                elif isinstance(status_field, str):
                    status_name = status_field
                else:
                    status_name = None

                return {
                    "success": True,
                    "task_id": task.get("id"),
                    "task_name": task.get("name"),
                    "task_url": task.get("url"),
                    "status": status_name,
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
