import type {
  Conversation,
  ConversationPatch,
  BridgeStreamPort,
  ChatAttachmentStagingPort,
  DeadLetter,
  Folder,
  FolderPatch,
  HttpClient,
  Memory,
  MemoryPatch,
  PlatformConversationCoverageState,
  PlatformConversationItem,
  PlatformFolderCoverageState,
  PlatformFolderItem,
  PlatformTaskCoverageState,
  PlatformTaskItem,
  StorageBridge,
  SynthesizedMemoryItem,
  SynthesizedRecallState,
  Task,
  TaskPatch,
} from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import type { StoreStatus } from "@omi-core/domain";
import {
  ConversationsStore,
  FoldersStore,
  MemoriesStore,
  MemoryCorrectionStore,
  PlatformConversationsStore,
  PlatformFoldersStore,
  PlatformTasksStore,
  SynthesizedMemoriesStore,
  TasksStore,
} from "@omi-core/domain";
import {
  WRITE_ID_ENTROPY_BYTES,
  createDevAccountEpochProvider,
} from "@omi-core/adapters-platform";
import {
  openProductionChatStore,
  type ProductionChatStore,
} from "./ProductionChatStore.js";
import {
  resolveGenerationSelection,
  type GenerationRejection,
  type GenerationSelection,
} from "@omi-core/domain";

/**
 * Re-exported so a shell composing the production surfaces needs exactly one
 * import path. The selector itself lives in `@omi-core/domain` rather than in
 * this bundle because it is a pure function over untrusted host input that
 * every shell and every test needs — and this package compiles to a Vite
 * bundle with no unit-test seam of its own.
 */
export {
  LEGACY_ONLY_GENERATION,
  PLATFORM_MEMORIES_GENERATION,
  PRODUCTION_DOMAINS,
  PRODUCTION_GENERATION_AVAILABILITY,
  describeGenerationRejections,
  parseGenerationSelectionFromEntries,
  resolveGenerationSelection,
  type BackendGeneration,
  type GenerationRejection,
  type GenerationSelection,
  type ProductionDomain,
  type ResolvedGenerationSelection,
} from "@omi-core/domain";

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

/* ── platform generation ─────────────────────────────────────────────────── */

/**
 * The platform generation's memory READ store.
 *
 * Additive and SEPARATE from `ProductionMemoryStore`, not a replacement for
 * it, because the record classes genuinely differ — see the long rationale in
 * `contracts/src/domain/synthesized-memories.ts`. The short version: the
 * ratified projection has `id` + `text` + optional lineage, and the ratified
 * conformance corpus actively REJECTS a payload carrying `content`,
 * `category`, `visibility`, `reviewed` or `locked`. Satisfying
 * `ProductionMemoryStore` would mean inventing those fields, and a fabricated
 * `locked: false` is a data-loss path, not a rendering detail.
 *
 * It is an `ObservableStore`, so `status()`, `subscribe()` and `refresh()`
 * behave identically to every other store and a surface's offline/refresh
 * rendering is unchanged across generations. It is NOT a `WriteAwareStore`:
 * there are no writes, so there are no dead letters to expose.
 */
export type ProductionSynthesizedMemoryStore = ObservableStore & {
  list(): Promise<readonly SynthesizedMemoryItem[]>;
  /** Honest coverage. `{ kind: "unknown" }` until an honest page is read. */
  recall(): SynthesizedRecallState;
  hasMore(): boolean;
  /** Append the next keyset page. No-op when there is no continuation. */
  loadMore(): Promise<void>;
};

/**
 * The correction path for platform Memories: add a fact, which is a
 * user-asserted STM note. Named separately from the synthesized READ store
 * because that projection has no writes.
 */
export type ProductionMemoryCorrectionStore = {
  submitFact(text: string): Promise<void>;
};

/**
 * The platform generation's task store.
 *
 * ADDITIVE AND SEPARATE from `ProductionTaskStore` because `id` differs:
 * `Task["id"]` is a `RecordId`; a platform task id is the ratified
 * reader-scoped opaque ref, which is not a `RecordId`. Field sets are
 * IDENTICAL by ruling — `DAVID-tasks-read-epoch-and-ci` D2 — so the surface
 * renders the same off either generation.
 *
 * Writes go through `POST /v1/tasks/ops` — the ratified ops envelope with
 * `write_id` idempotency. Completeness is the server's envelope, never
 * derived. `openTasks()` is NOT repointed at this store; the Tasks route
 * asks for it BY NAME, exactly as Conversations and Folders do.
 *
 * IT IS AN `ObservableStore`, so `status()`, `subscribe()` and `refresh()`
 * behave identically to every other store and a surface's offline/refresh
 * rendering is unchanged across generations.
 */
export type ProductionPlatformTaskStore = WriteAwareStore & {
  list(): Promise<readonly PlatformTaskItem[]>;
  /** Honest coverage. `{ kind: "unknown" }` until an honest page is read. */
  coverage(): PlatformTaskCoverageState;
  hasMore(): boolean;
  /** Append the next keyset page. No-op when there is no continuation. */
  loadMore(): Promise<void>;
  create(description: string, dueAt?: number): Promise<void>;
  patch(id: string, patch: TaskPatch): Promise<void>;
  delete(id: string): Promise<void>;
};

export type ProductionPlatformConversationStore = WriteAwareStore & {
  list(): Promise<readonly PlatformConversationItem[]>;
  coverage(): PlatformConversationCoverageState;
  hasMore(): boolean;
  loadMore(): Promise<void>;
  patch(id: Conversation["id"], patch: ConversationPatch): Promise<void>;
  delete(id: Conversation["id"]): Promise<void>;
};

export type ProductionPlatformFolderStore = WriteAwareStore & {
  list(): Promise<readonly PlatformFolderItem[]>;
  coverage(): PlatformFolderCoverageState;
  hasMore(): boolean;
  loadMore(): Promise<void>;
  create(name: string, opts?: { description?: string; color?: string; icon?: string }): Promise<void>;
  patch(id: Folder["id"], patch: FolderPatch): Promise<void>;
  delete(id: Folder["id"], moveToFolderId?: Folder["id"]): Promise<void>;
};

/**
 * A factory that can serve either generation, per domain.
 *
 * It IS a `ProductionStoreFactory` — every existing surface keeps working
 * against it unchanged — and adds the platform-only read port plus the
 * resolved selection so a shell can show what it actually got.
 */
export type PlatformProductionStoreFactory = ProductionStoreFactory & {
  readonly selection: GenerationSelection;
  /** Non-empty when the host asked for a generation it did not receive. */
  readonly rejected: readonly GenerationRejection[];
  openSynthesizedMemories(): Promise<ProductionSynthesizedMemoryStore>;
  /**
   * The correction path: `POST /v1/stm-notes/ops`. Named separately, and
   * `openMemories()` is not repointed at it. A user-asserted note is not a
   * patch of a synthesized proposition.
   */
  openMemoryCorrection(): Promise<ProductionMemoryCorrectionStore>;
  /**
   * The platform generation's tasks store.
   *
   * NAMED SEPARATELY ON PURPOSE, and `openTasks()` is NOT repointed at it.
   * David's 2026-08-16 ruling lifted the R7 park: the Tasks *route* branches
   * to this port when `selection.tasks === "platform"`, the same way Home,
   * Conversations, and Folders already branch. A factory-level flip of
   * `openTasks()` remains forbidden — that is what R7 still catches.
   */
  openPlatformTasks(): Promise<ProductionPlatformTaskStore>;
  /**
   * Named platform conversations store. `openConversations()` stays on the
   * legacy adapter. Routes that want the platform read model ask for this
   * port by name; they do not repoint `openConversations()`.
   */
  openPlatformConversations(): Promise<ProductionPlatformConversationStore>;
  /**
   * Named platform folders store. `openFolders()` stays on the legacy adapter.
   * Routes that want the platform read model ask for this port by name; they
   * do not repoint `openFolders()`.
   */
  openPlatformFolders(): Promise<ProductionPlatformFolderStore>;
  /** Named live Chat seam. C3b3 owns routing a production surface to it. */
  openChat(): Promise<ProductionChatStore>;
};

/**
 * The two transports a dual-generation client needs. Both are bound by the
 * host — base URL and credentials live in the binding, never here (ADR-008
 * §3), which is what lets a shell repoint at a local backend without a
 * rebuild.
 */
export interface ProductionTransports {
  readonly legacyHttp: HttpClient;
  /**
   * The contracts-native service. Should supply `HttpResponse.text` when it
   * can: the ratified validator is defined over the response bytes, and the
   * adapter reports which boundary it managed to use.
   */
  readonly platformHttp: HttpClient;
  /** Required only when `openChat()` is used. */
  readonly platformStream?: BridgeStreamPort;
  /** Optional native-only pick/stage port; absence remains truthfully unsupported. */
  readonly chatAttachmentStaging?: ChatAttachmentStagingPort;
}

/**
 * Build a factory from a HOST-SUPPLIED, untrusted generation selection.
 *
 * `requestedGenerations` is whatever the launcher had — parsed JSON, a query
 * string lookup, an argv value. It is validated by
 * `resolveGenerationSelection`, and anything unavailable is rejected loudly
 * and falls back to `legacy` rather than being silently downgraded.
 *
 * David's 2026-08-16 ruling retires memory editing: users correct Omi by
 * adding a fact through consolidation (`POST /v1/stm-notes/ops`). That
 * discharges the earlier note that `openMemories()` returning the legacy
 * *editable* store was "not an oversight."
 *
 * `openMemories()` STILL returns the legacy store and is NOT pointed at
 * `openSynthesizedMemories()`. The record classes still differ — the
 * synthesized projection has no `content` / `locked` / `visibility` — and
 * pointing the port at a read model would satisfy the type and break every
 * caller at runtime. If the legacy store becomes unreferenced, that is the
 * eviction lane's business. The correction path is `openMemoryCorrection()`.
 */
export function createPlatformProductionStoreFactory(
  bridge: StorageBridge,
  env: Env,
  transports: ProductionTransports,
  requestedGenerations?: unknown,
): PlatformProductionStoreFactory {
  const { selection, rejected } = resolveGenerationSelection(requestedGenerations);
  const legacy = createLegacyProductionStoreFactory(bridge, env, transports.legacyHttp);
  const epochs = createDevAccountEpochProvider();
  const entropy = (): Uint8Array => {
    const bytes = new Uint8Array(WRITE_ID_ENTROPY_BYTES);
    globalThis.crypto.getRandomValues(bytes);
    return bytes;
  };
  return {
    ...legacy,
    selection,
    rejected,
    openSynthesizedMemories: () =>
      SynthesizedMemoriesStore.open(bridge, env, transports.platformHttp),
    openMemoryCorrection: async () =>
      MemoryCorrectionStore.open(transports.platformHttp, epochs, entropy),
    openPlatformTasks: () => PlatformTasksStore.open(bridge, env, transports.platformHttp),
    openPlatformConversations: () =>
      PlatformConversationsStore.open(bridge, env, transports.platformHttp),
    openPlatformFolders: () =>
      PlatformFoldersStore.open(bridge, env, transports.platformHttp),
    openChat: () => {
      if (transports.platformStream === undefined) {
        throw new Error("live Chat unavailable: platform stream bridge is not installed");
      }
      return openProductionChatStore(
        bridge,
        env,
        transports.platformHttp,
        transports.platformStream,
        transports.chatAttachmentStaging,
      );
    },
  };
}
