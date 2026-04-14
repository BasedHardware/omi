import { create } from "zustand";
import { useAuthStore } from "./authStore";
import { api } from "../services/api";

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
}

interface TaskState {
  tasks: Task[];
  isLoading: boolean;
  loadTasks: () => Promise<void>;
  toggleTask: (id: string) => Promise<void>;
  createTask: (description: string) => Promise<void>;
  deleteTask: (id: string) => Promise<void>;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: [],
  isLoading: false,

  loadTasks: async () => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    set({ isLoading: true });

    try {
      const data = await api.get<{ action_items: Task[]; has_more: boolean }>("/v1/action-items");
      const items = data?.action_items ?? [];
      set({
        tasks: Array.isArray(items) ? items : [],
        isLoading: false,
      });
    } catch (error) {
      console.error("Failed to load tasks:", error);
      set({ isLoading: false });
    }
  },

  toggleTask: async (id: string) => {
    const token = useAuthStore.getState().idToken;
    if (!token) return;

    const task = get().tasks.find((t) => t.id === id);
    if (!task) return;

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
