/**
 * User-facing labels and one-line summaries for chat tool calls. Keeps
 * presentation logic out of the message renderer and the tool executor.
 */

export interface ToolPresentation {
  /** Title shown in the tool card header. */
  title: string;
  /** Verb form shown while the tool is running ("Searching tasks…"). */
  runningLabel: string;
}

const TOOL_PRESENTATION: Record<string, ToolPresentation> = {
  loaded_context: { title: "Loaded context", runningLabel: "Loading context" },
  search_tasks: { title: "Tasks", runningLabel: "Searching tasks" },
  search_memories: { title: "Memories", runningLabel: "Searching memories" },
  search_goals: { title: "Goals", runningLabel: "Searching goals" },
  search_screen_history: {
    title: "Screen history",
    runningLabel: "Searching screen history",
  },
  get_recent_screen_activity: {
    title: "Recent screen activity",
    runningLabel: "Reading recent screen activity",
  },
  complete_task: { title: "Update task", runningLabel: "Updating task" },
  delete_task: { title: "Delete task", runningLabel: "Deleting task" },
  create_task: { title: "Create task", runningLabel: "Creating task" },
  update_task: { title: "Update task", runningLabel: "Updating task" },
  create_goal: { title: "Create goal", runningLabel: "Creating goal" },
  update_goal_progress: { title: "Update goal", runningLabel: "Updating goal" },
  add_memory: { title: "Save memory", runningLabel: "Saving memory" },

  // Legacy / pre-claude path
  search_screen_activity: {
    title: "Screen activity",
    runningLabel: "Reading screen activity",
  },
};

export function presentTool(name: string): ToolPresentation {
  return (
    TOOL_PRESENTATION[name] ?? {
      title: name,
      runningLabel: `Running ${name}`,
    }
  );
}
