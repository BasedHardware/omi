```python
- For `hive_graphql_request`, replace:
  ```
  return {"errors": [{"message": f"Request failed: {str(e)}"}]}
  ```
  with:
  ```
  return {
      "errors": [{"message": "An error occurred while processing your request.", "code": "HIVE-001", "details": str(e)}]}
  }
  ```

- For `hive_get_projects`, replace:
  ```
  return ChatToolResponse(error=f"Failed to get projects: {str(e)}")
  ```
  with:
  ```
  return ChatToolResponse(
      error=f"An error occurred while getting projects: An error occurred while processing your request.", 
      error_code="HIVE-001",
      error_details=str(e)
  )
  ```

- For `hive_get_tasks`, replace:
  ```
  return ChatToolResponse(error=f"Failed to get tasks: {str(e)}")
  ```
  with:
  ```
  return ChatToolResponse(
      error=f"An error occurred while getting tasks: An error occurred while processing your request.", 
      error_code="HIVE-001",
      error_details=str(e)
  )
  ```

- For `hive_create_task`, replace:
  ```
  return ChatToolResponse(error=f"Failed to create task: {str(e)}")
  ```
  with:
  ```
  return ChatToolResponse(
      error=f"An error occurred while creating a task: An error occurred while processing your request.", 
      error_code="HIVE-001",
      error_details=str(e)
  )
  ```

- For `hive_search`, replace:
  ```
  return ChatToolResponse(error=f"Search failed: {str(e)}")
  ```
  with:
  ```
  return ChatToolResponse(
      error=f"An error occurred while performing the search: An error occurred while processing your request.", 
      error_code="HIVE-001",
      error_details=str(e)
  )
  ```

- For `hive_update_task_status`, replace:
  ```
  return ChatToolResponse(error=f"Failed to update task: {str(e)}")
  ```
  with:
  ```
  return ChatToolResponse(
      error=f"An error occurred while updating the task: An error occurred while processing your request.", 
      error_code="HIVE-001",
      error_details=str(e)
  )
  ```

- For `hive_graphql_request` in the PR #15489, ensure the response format matches:
  ```
  {
      "errors": [
          {
              "message": "An error occurred while processing your request.",
              "code": "HIVE-001",
              "details": str(e)
          }
      ]
  }
  ```
```