import type {
  Conversation,
  ConversationPatch,
  DeadLetter,
  Folder,
  HttpClient,
  Memory,
  MemoryPatch,
  StorageBridge,
  Task,
  TaskPatch,
} from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import type { StoreStatus } from "@omi-core/domain";
import { ConversationsStore, FoldersStore, MemoriesStore, TasksStore } from "@omi-core/domain";

type ObservableStore = {
  status(): StoreStatus;
  subscribe(listener: () => void): () => void;
  refresh(): Promise<void>;
};

type WriteAwareStore = ObservableStore & {
  deadLetters(): Promise<DeadLetter[]>;
  discardDeadLetter(opId: string): Promise<void>;
};

export type ProductionMemoryStore = WriteAwareStore & {
  list(): Promise<Memory[]>;
  create(content: string, opts?: { visibility?: "public" | "private" }): Promise<void>;
  patch(id: Memory["id"], patch: MemoryPatch): Promise<void>;
  delete(id: Memory["id"]): Promise<void>;
};

export type ProductionConversationStore = WriteAwareStore & {
  list(): Promise<Conversation[]>;
  patch(id: Conversation["id"], patch: ConversationPatch): Promise<void>;
  delete(id: Conversation["id"]): Promise<void>;
};

export type ProductionFolderStore = ObservableStore & {
  list(): Promise<Folder[]>;
};

export type ProductionTaskStore = WriteAwareStore & {
  list(): Promise<Task[]>;
  create(description: string, dueAt?: number): Promise<void>;
  patch(id: Task["id"], patch: TaskPatch): Promise<void>;
  delete(id: Task["id"]): Promise<void>;
};

/**
 * Composition boundary between production UI and a backend generation.
 * Fixtures and the current legacy adapter satisfy the same surface-facing
 * ports; the rewritten backend can provide another factory without changing
 * product components or their offline/status behavior.
 */
export type ProductionStoreFactory = {
  openMemories(): Promise<ProductionMemoryStore>;
  openConversations(): Promise<ProductionConversationStore>;
  openFolders(): Promise<ProductionFolderStore>;
  openTasks(): Promise<ProductionTaskStore>;
};

export function createLegacyProductionStoreFactory(
  bridge: StorageBridge,
  env: Env,
  http: HttpClient,
): ProductionStoreFactory {
  return {
    openMemories: () => MemoriesStore.open(bridge, env, http),
    openConversations: () => ConversationsStore.open(bridge, env, http),
    openFolders: () => FoldersStore.open(bridge, env, http),
    openTasks: () => TasksStore.open(bridge, env, http),
  };
}
