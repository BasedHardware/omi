```python
def _error_message(error, response=None):
    if response and hasattr(response, 'text'):
        return f"HTTP {response.status_code}: {response.text}"
    return f"HTTP {error.status_code}: {error.message if 'message' in error else 'Unknown error'}"

def list_issues():
    try:
        issues = github_client.list_issues()
        return {"result": {"issues": issues}}
    except Exception as e:
        return {"error": f"Error listing issues: {str(e)}"}

def get_issue(issue_number):
    try:
        issue = github_client.get_issue(issue_number)
        return {"result": issue}
    except Exception as e:
        return {"error": f"Error getting issue {issue_number}: {str(e)}"}
```