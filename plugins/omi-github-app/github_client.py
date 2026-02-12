import os
import requests
from typing import Optional, List, Dict
from dotenv import load_dotenv

load_dotenv()


class GitHubClient:
    """Handles GitHub API interactions."""
    
    def __init__(self):
        self.client_id = os.getenv("GITHUB_CLIENT_ID")
        self.client_secret = os.getenv("GITHUB_CLIENT_SECRET")
        self.api_base = "https://api.github.com"
    
    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """
        Generate GitHub OAuth authorization URL.
        Scopes: repo (for creating issues in public/private repos)
        """
        scopes = "repo"
        auth_url = (
            f"https://github.com/login/oauth/authorize?"
            f"client_id={self.client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"scope={scopes}&"
            f"state={state}"
        )
        return auth_url
    
    def exchange_code_for_token(self, code: str) -> dict:
        """
        Exchange authorization code for access token.
        Returns token data including access_token.
        """
        try:
            response = requests.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code
                }
            )
            
            if response.status_code == 200:
                token_data = response.json()
                if "access_token" in token_data:
                    return token_data
                else:
                    raise Exception(f"No access token in response: {token_data}")
            else:
                raise Exception(f"Token exchange failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"❌ Token exchange error: {e}")
            raise
    
    def get_user_info(self, access_token: str) -> dict:
        """Get authenticated user's GitHub info."""
        try:
            response = requests.get(
                f"{self.api_base}/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Failed to get user info: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error getting user info: {e}")
            raise
    
    def list_user_repos(self, access_token: str, per_page: int = 100) -> List[Dict]:
        """
        List all repositories the user has access to (owned + collaborator).
        Returns list of {name, full_name, owner, private, description}
        """
        try:
            repos = []
            
            # Get user's own repos
            response = requests.get(
                f"{self.api_base}/user/repos",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                params={"per_page": per_page, "sort": "updated"}
            )
            
            if response.status_code == 200:
                user_repos = response.json()
                for repo in user_repos:
                    repos.append({
                        "name": repo["name"],
                        "full_name": repo["full_name"],
                        "owner": repo["owner"]["login"],
                        "private": repo["private"],
                        "description": repo.get("description", ""),
                        "url": repo["html_url"]
                    })
            
            return repos
            
        except Exception as e:
            print(f"❌ Error listing repos: {e}")
            return []
    
    def get_repo_labels(self, access_token: str, repo_full_name: str) -> List[str]:
        """
        Fetch all labels from a repository.
        Returns list of label names.
        """
        try:
            response = requests.get(
                f"{self.api_base}/repos/{repo_full_name}/labels",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                params={"per_page": 100}
            )
            
            if response.status_code == 200:
                labels = response.json()
                return [label["name"] for label in labels]
            else:
                print(f"⚠️  Could not fetch labels: {response.status_code}")
                return []
                
        except Exception as e:
            print(f"⚠️  Error fetching labels: {e}")
            return []
    
    async def create_issue(
        self,
        access_token: str,
        repo_full_name: str,
        title: str,
        body: str,
        labels: Optional[List[str]] = None
    ) -> Optional[dict]:
        """
        Create an issue in the specified repository.
        repo_full_name: "owner/repo"
        Returns issue data if successful.
        """
        try:
            issue_data = {
                "title": title,
                "body": body
            }

            if labels:
                issue_data["labels"] = labels

            response = requests.post(
                f"{self.api_base}/repos/{repo_full_name}/issues",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                json=issue_data
            )

            if response.status_code == 201:
                issue = response.json()
                return {
                    "success": True,
                    "issue_number": issue["number"],
                    "issue_url": issue["html_url"],
                    "title": issue["title"]
                }
            else:
                error_msg = response.json().get("message", response.text)
                print(f"❌ GitHub API error: {response.status_code} - {error_msg}")
                return {
                    "success": False,
                    "error": f"GitHub API error: {error_msg}"
                }

        except Exception as e:
            print(f"❌ Error creating issue: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }

    def list_issues(
        self,
        access_token: str,
        repo_full_name: str,
        state: str = "open",
        per_page: int = 10
    ) -> List[Dict]:
        """
        List issues in a repository.
        Returns list of issue dicts.
        """
        try:
            response = requests.get(
                f"{self.api_base}/repos/{repo_full_name}/issues",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                params={
                    "state": state,
                    "per_page": per_page,
                    "sort": "created",
                    "direction": "desc"
                }
            )

            if response.status_code == 200:
                issues = response.json()
                return [
                    {
                        "number": issue["number"],
                        "title": issue["title"],
                        "state": issue["state"],
                        "body": issue.get("body", ""),
                        "labels": [label["name"] for label in issue.get("labels", [])],
                        "url": issue["html_url"],
                        "created_at": issue["created_at"],
                        "user": issue["user"]["login"] if issue.get("user") else None
                    }
                    for issue in issues
                    if "pull_request" not in issue  # Filter out PRs
                ]
            else:
                print(f"❌ Error listing issues: {response.status_code}")
                return []

        except Exception as e:
            print(f"❌ Error listing issues: {e}")
            return []

    def get_issue(
        self,
        access_token: str,
        repo_full_name: str,
        issue_number: int
    ) -> Optional[Dict]:
        """
        Get details of a specific issue.
        Returns issue dict if successful.
        """
        try:
            response = requests.get(
                f"{self.api_base}/repos/{repo_full_name}/issues/{issue_number}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )

            if response.status_code == 200:
                issue = response.json()
                return {
                    "number": issue["number"],
                    "title": issue["title"],
                    "state": issue["state"],
                    "body": issue.get("body", ""),
                    "labels": [label["name"] for label in issue.get("labels", [])],
                    "url": issue["html_url"],
                    "created_at": issue["created_at"],
                    "updated_at": issue["updated_at"],
                    "user": issue["user"]["login"] if issue.get("user") else None,
                    "assignees": [a["login"] for a in issue.get("assignees", [])],
                    "comments": issue.get("comments", 0)
                }
            elif response.status_code == 404:
                return None
            else:
                print(f"❌ Error getting issue: {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Error getting issue: {e}")
            return None

    def add_issue_comment(
        self,
        access_token: str,
        repo_full_name: str,
        issue_number: int,
        body: str
    ) -> Optional[Dict]:
        """
        Add a comment to an issue.
        Returns comment data if successful.
        """
        try:
            response = requests.post(
                f"{self.api_base}/repos/{repo_full_name}/issues/{issue_number}/comments",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                json={"body": body}
            )

            if response.status_code == 201:
                comment = response.json()
                return {
                    "success": True,
                    "comment_id": comment["id"],
                    "comment_url": comment["html_url"]
                }
            else:
                error_msg = response.json().get("message", response.text)
                print(f"❌ GitHub API error: {response.status_code} - {error_msg}")
                return {
                    "success": False,
                    "error": f"GitHub API error: {error_msg}"
                }

        except Exception as e:
            print(f"❌ Error adding comment: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_repo_labels_with_details(
        self,
        access_token: str,
        repo_full_name: str
    ) -> List[Dict]:
        """
        Fetch all labels from a repository with full details.
        Returns list of label dicts with name, color, description.
        """
        try:
            response = requests.get(
                f"{self.api_base}/repos/{repo_full_name}/labels",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                params={"per_page": 100}
            )

            if response.status_code == 200:
                labels = response.json()
                return [
                    {
                        "name": label["name"],
                        "color": label["color"],
                        "description": label.get("description", "")
                    }
                    for label in labels
                ]
            else:
                print(f"⚠️  Could not fetch labels: {response.status_code}")
                return []

        except Exception as e:
            print(f"⚠️  Error fetching labels: {e}")
            return []

    def get_repo_permissions(self, access_token: str, repo_full_name: str) -> Optional[Dict]:
        """
        Get repository permissions for the authenticated user.
        Returns permissions dict (admin/push/pull) if successful.
        """
        try:
            response = requests.get(
                f"{self.api_base}/repos/{repo_full_name}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )

            if response.status_code == 200:
                repo = response.json()
                return repo.get("permissions", {})
            else:
                error_msg = None
                try:
                    error_msg = response.json().get("message")
                except Exception:
                    error_msg = response.text
                print(f"⚠️  Could not fetch repo permissions: {response.status_code} - {error_msg}")
                return {
                    "_error": error_msg or "Unknown error",
                    "_status": response.status_code
                }

        except Exception as e:
            print(f"⚠️  Error fetching repo permissions: {e}")
            return None

