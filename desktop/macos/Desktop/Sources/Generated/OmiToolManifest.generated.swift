import Foundation

enum OmiToolManifest {
  static let localAgentAPITools: [LocalAgentTool] = [
    LocalAgentTool(
      name: "get_local_status",
      description:
        "Report whether local Omi Desktop context is available, including screen-history counts, indexed screenshot counts, and latest capture time. Call this before local screen-history or SQL work.",
      properties: [:],
      required: [],
      annotations: ["readOnlyHint": true, "destructiveHint": false, "openWorldHint": false]
    ),
    LocalAgentTool(
      name: "execute_sql",
      description:
        "Run read-only SQL on the local Omi Desktop SQLite database. Use SELECT or WITH queries for structured questions about screenshots, transcriptions, tasks, memories, indexed files, goals, and activity.",
      properties: ["query": ["type": "string", "description": "SQL query to execute against the local Omi database"]],
      required: ["query"],
      annotations: ["readOnlyHint": true, "destructiveHint": false, "openWorldHint": false]
    ),
    LocalAgentTool(
      name: "search_screen_history",
      description:
        "Search local Rewind screen history using OCR and semantic similarity. Use for fuzzy questions about what the user saw or worked on. Results include screenshot IDs that can be opened with get_screenshot.",
      properties: [
        "query": ["type": "string", "description": "Natural language query"],
        "days": ["type": "number", "description": "Days to search back; default 7"],
        "app_filter": ["type": "string", "description": "Optional app name filter"],
      ],
      required: ["query"],
      annotations: ["readOnlyHint": true, "destructiveHint": false, "openWorldHint": false]
    ),
    LocalAgentTool(
      name: "semantic_search",
      description: "Compatibility alias for search_screen_history.",
      properties: [
        "query": ["type": "string", "description": "Natural language query"],
        "days": ["type": "number", "description": "Days to search back; default 7"],
        "app_filter": ["type": "string", "description": "Optional app name filter"],
      ],
      required: ["query"],
      annotations: ["readOnlyHint": true, "destructiveHint": false, "openWorldHint": false]
    ),
    LocalAgentTool(
      name: "get_screenshot",
      description:
        "Fetch a local Rewind screenshot image by screenshot_id. Use screenshot IDs returned by search_screen_history or execute_sql. Very recent captures may return screenshot_pending.",
      properties: [
        "screenshot_id": ["type": "number", "description": "Screenshot ID from search_screen_history or the screenshots table"]
      ],
      required: ["screenshot_id"],
      annotations: ["readOnlyHint": true, "destructiveHint": false, "openWorldHint": false]
    ),
    LocalAgentTool(
      name: "get_work_context",
      description:
        "Get the user's CURRENT screen plus a compressed timeline of recent on-screen activity. CALL THIS FIRST when seeing the user's screen or recent work would help.",
      properties: [
        "minutes": ["type": "number", "description": "Minutes of recent activity to summarize (default 10, max 120)"]
      ],
      required: [],
      annotations: ["readOnlyHint": true, "destructiveHint": false, "openWorldHint": false]
    ),
    LocalAgentTool(
      name: "get_daily_recap",
      description: "Get a formatted local activity recap for today, yesterday, or a recent range.",
      properties: ["days_ago": ["type": "number", "description": "0=today, 1=yesterday, 7=past week"]],
      required: [],
      annotations: ["readOnlyHint": true, "destructiveHint": false, "openWorldHint": false]
    ),
    LocalAgentTool(
      name: "search_tasks",
      description: "Semantic search over local Omi tasks and staged tasks.",
      properties: [
        "query": ["type": "string", "description": "Task search query"],
        "include_completed": ["type": "boolean", "description": "Include completed tasks"],
      ],
      required: ["query"],
      annotations: ["readOnlyHint": true, "destructiveHint": false, "openWorldHint": false]
    ),
    LocalAgentTool(
      name: "complete_task",
      description: "Mark a task complete. This is idempotent; already-completed tasks stay completed. Find the task id first with execute_sql or search_tasks.",
      properties: ["task_id": ["type": "string", "description": "Task backendId"]],
      required: ["task_id"],
      annotations: ["readOnlyHint": false, "destructiveHint": false, "openWorldHint": false]
    ),
    LocalAgentTool(
      name: "delete_task",
      description: "Delete a task. Find the task id first with execute_sql or search_tasks.",
      properties: ["task_id": ["type": "string", "description": "Task backendId"]],
      required: ["task_id"],
      annotations: ["readOnlyHint": false, "destructiveHint": true, "openWorldHint": false]
    ),
  ]
}
