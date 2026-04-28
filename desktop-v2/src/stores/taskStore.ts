import { create } from "zustand";
import { useAuthStore } from "./authStore";
import { api, dispatchIntegrationToggle } from "../services/api";
import { useAppStore, isTwoWaySyncEnabled } from "./appStore";

/** Native = Nooto action items (`/v1/action-items`). Anything else came from
 *  the integration aggregator and is read-only by default. */
export type TaskSource = "native" | "jira" | "linear" | string;

export interface Task {
  id: string;
  description: string;
  completed: boolean;
  created_at: string | null;
  updated_at?: string | null;
  due_at?: string | null;
  completed_at?: string | null;
  conversation_id?: string | null;
  sort_order?: number;
  indent_level?: number;

  // Integration-only fields. Absent (== "native") for action items.
  source?: TaskSource;
  source_app_id?: string;
  source_app_name?: string;
  source_app_image?: string;
  external_id?: string;
  external_url?: string;
  status_label?: string;
  status_type?: "todo" | "in_progress" | "done" | "canceled";
  priority?: string;
  project?: string;
  assignee?: string;
}

// Wire shape returned by `GET /v1/integrations/tasks` (see backend's
// NormalizedTask). Kept private — `loadTasks` flattens these into the local
// `Task` type so the rest of the UI can treat all rows uniformly.
interface IntegrationTaskWire {
  external_id: string;
  title: string;
  status: string;
  status_type?: "todo" | "in_progress" | "done" | "canceled";
  due_at?: string | null;
  priority?: string | null;
  url?: string;
  project?: string | null;
  assignee?: string | null;
  updated_at?: string | null;
  source_app_id: string;
  source_app_name: string;
  source_app_image?: string | null;
}

interface AggregatedTasksResponse {
  tasks: IntegrationTaskWire[];
  errors: Record<string, string>;
}

/** Map an app id / name to the local `TaskSource` discriminator the UI uses
 *  to pick icons + behavior. Falls back to the source_app_id so unknown apps
 *  still render with a generic badge. */
function inferSource(appName: string, appId: string): TaskSource {
  const n = appName.toLowerCase();
  if (n.includes("jira")) return "jira";
  if (n.includes("linear")) return "linear";
  return appId;
}

interface TaskState {
  tasks: Task[];
  isLoading: boolean;
  /** Per-app errors from the latest `/v1/integrations/tasks` call (e.g.
   *  "http 401" if the user's Linear token expired). UI can surface a banner. */
  integrationErrors: Record<string, string>;
  loadTasks: () => Promise<void>;
  toggleTask: (id: string) => Promise<void>;
  createTask: (description: string) => Promise<void>;
  deleteTask: (id: string) => Promise<void>;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: [],
  isLoading: false,
  integrationErrors: {},

  loadTasks: async () => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    set({ isLoading: true });

    // Fetch native action items + integration tasks in parallel. Either side
    // can fail independently — we never want a Linear/Jira hiccup to hide
    // the user's native tasks.
    const [nativeRes, integrationsRes] = await Promise.allSettled([
      api.get<{ action_items: Task[]; has_more: boolean }>("/v1/action-items"),
      api.get<AggregatedTasksResponse>("/v1/integrations/tasks"),
    ]);

    const native: Task[] =
      nativeRes.status === "fulfilled" && Array.isArray(nativeRes.value?.action_items)
        ? nativeRes.value.action_items
        : [];
    if (nativeRes.status === "rejected") {
      console.error("Failed to load native tasks:", nativeRes.reason);
    }

    const integrationErrors: Record<string, string> = {};
    let integration: Task[] = [];
    if (integrationsRes.status === "fulfilled") {
      const payload = integrationsRes.value;
      Object.assign(integrationErrors, payload?.errors ?? {});
      integration = (payload?.tasks ?? []).map((t) => ({
        // Synthetic id — stable per (app, ticket), kept distinct from native
        // UUIDs so PATCH/DELETE guards can pick it out by `source !== native`.
        id: `${t.source_app_id}:${t.external_id}`,
        description: t.title,
        completed: t.status_type === "done" || t.status_type === "canceled",
        created_at: null,
        updated_at: t.updated_at ?? null,
        due_at: t.due_at ?? null,
        source: inferSource(t.source_app_name, t.source_app_id),
        source_app_id: t.source_app_id,
        source_app_name: t.source_app_name,
        source_app_image: t.source_app_image ?? undefined,
        external_id: t.external_id,
        external_url: t.url || undefined,
        status_label: t.status,
        status_type: t.status_type,
        priority: t.priority ?? undefined,
        project: t.project ?? undefined,
        assignee: t.assignee ?? undefined,
      }));
    } else {
      console.warn("Failed to load integration tasks:", integrationsRes.reason);
    }

    set({
      tasks: [...native, ...integration],
      integrationErrors,
      isLoading: false,
    });
  },

  toggleTask: async (id: string) => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    const task = get().tasks.find((t) => t.id === id);
    if (!task) return;

    // Integration task: read-only unless the user has explicitly turned on
    // two-way sync for this app (Settings → Apps → <app> → Two-way sync).
    // When on, dispatch a writeback to the plugin's update_*_status tool.
    if (task.source && task.source !== "native") {
      if (!isTwoWaySyncEnabled(task.source_app_id)) return;
      await syncIntegrationToggle(task, set, get);
      return;
    }

    const newCompleted = !task.completed;

    // Optimistic update
    set((state) => ({
      tasks: state.tasks.map((t) =>
        t.id === id ? { ...t, completed: newCompleted } : t,
      ),
    }));

    try {
      await api.patch(`/v1/action-items/${id}`, {
        completed: newCompleted,
      });
    } catch (error) {
      console.error("Failed to toggle task:", error);
      // Rollback
      set((state) => ({
        tasks: state.tasks.map((t) =>
          t.id === id ? { ...t, completed: task.completed } : t,
        ),
      }));
    }
  },

  createTask: async (description: string) => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    try {
      const task = await api.post<Task>("/v1/action-items", { description });
      set((state) => ({ tasks: [task, ...state.tasks] }));
    } catch (error) {
      console.error("Failed to create task:", error);
    }
  },

  deleteTask: async (id: string) => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    const target = get().tasks.find((t) => t.id === id);
    if (target?.source && target.source !== "native") return; // can't delete external tickets from here

    const prev = get().tasks;
    set({ tasks: prev.filter((t) => t.id !== id) });

    try {
      await api.delete(`/v1/action-items/${id}`);
    } catch (error) {
      console.error("Failed to delete task:", error);
      set({ tasks: prev });
    }
  },
}));

// ---------------------------------------------------------------------------
// Integration writeback ("two-way sync") helper. Picks the right plugin tool
// off the app's chat_tools manifest, dispatches via the api helper, and
// optimistically flips the local task's `completed` flag. Rolls back on error.
// ---------------------------------------------------------------------------

const _UPDATE_STATUS_SUFFIX = "update_issue_status";

function _findUpdateStatusEndpoint(appId: string | undefined): string | null {
  if (!appId) return null;
  const app = useAppStore.getState().apps.find((a) => a.id === appId);
  if (!app?.chat_tools) return null;
  const tool = app.chat_tools.find((t) => (t.name || "").toLowerCase().endsWith(_UPDATE_STATUS_SUFFIX));
  return tool?.endpoint || null;
}

async function syncIntegrationToggle(
  task: Task,
  set: (fn: (state: TaskState) => Partial<TaskState> | TaskState) => void,
  _get: () => TaskState,
) {
  const userId = useAuthStore.getState().userId;
  if (!userId || !task.source_app_id || !task.external_id) return;

  const endpoint = _findUpdateStatusEndpoint(task.source_app_id);
  if (!endpoint) {
    console.warn(`[taskStore] no update_issue_status tool on ${task.source_app_name}; skipping writeback`);
    return;
  }

  // Strip "/tools/<name>" suffix to recover the plugin's origin so we can
  // hand the dispatch helper a clean (origin, toolName) pair.
  const m = endpoint.match(/^(.*)\/tools\/([^/]+)$/);
  if (!m) {
    console.warn("[taskStore] unexpected tool endpoint shape:", endpoint);
    return;
  }
  const [, appHomeUrl, toolName] = m;

  // Optimistic flip — we toggle in the UI immediately and roll back if the
  // plugin returns an error. v1 only handles "mark done"; un-completing a
  // ticket from Plan view is left to a follow-up.
  const newCompleted = !task.completed;
  set((state) => ({
    tasks: state.tasks.map((t) => (t.id === task.id ? { ...t, completed: newCompleted } : t)),
  }));

  const result = await dispatchIntegrationToggle({
    appHomeUrl,
    toolName,
    uid: userId,
    externalId: task.external_id,
    newStatus: newCompleted ? "Done" : "To Do",
  });

  if (!result.ok) {
    console.warn(`[taskStore] writeback to ${task.source_app_name} failed: ${result.error}`);
    set((state) => ({
      tasks: state.tasks.map((t) => (t.id === task.id ? { ...t, completed: task.completed } : t)),
    }));
  }
}
