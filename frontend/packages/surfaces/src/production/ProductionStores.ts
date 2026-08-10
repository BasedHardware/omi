import type {
  Conversation,
  ConversationPatch,
  BridgeStreamPort,
  ChatAttachmentStagingPort,
  DeadLetter,
  Folder,
  HttpClient,
  Memory,
  MemoryPatch,
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
  PlatformTasksStore,
  SynthesizedMemoriesStore,
  TasksStore,
} from "@omi-core/domain";
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
 * The platform generation's task READ store.
 *
 * ADDITIVE AND SEPARATE from `ProductionTaskStore`, and the reason is NOT the
 * one that separates the two memory stores. There the record classes genuinely
 * differ and no honest mapping exists. Here the field sets are IDENTICAL by
 * ruling — `DAVID-tasks-read-epoch-and-ci` D2 ratifies all thirteen precisely so
 * the surface renders the same off either generation.
 *
 * What differs is `id`, and it is enough. `Task["id"]` is a `RecordId`; a
 * platform task id is the ratified reader-scoped opaque ref, which is not a
 * `RecordId`, does not parse as one, and is not stable across readers. And this
 * store has no writes: `ProductionTaskStore` is a `WriteAwareStore` with
 * `create`/`patch`/`delete` and dead letters, and satisfying that surface here
 * would mean either inventing writes this wire does not have or handing back a
 * store whose methods throw at runtime while satisfying the type.
 *
 * Writes for this generation go through `POST /v1/tasks/ops` — a separate
 * ratified wire with its own envelope and idempotency, which is CLIENT's seam,
 * not this one.
 *
 * IT IS AN `ObservableStore`, so `status()`, `subscribe()` and `refresh()`
 * behave identically to every other store and a surface's offline/refresh
 * rendering is unchanged across generations. That uniformity is the flip's
 * precondition, not a nicety.
 */
export type ProductionPlatformTaskStore = ObservableStore & {
  list(): Promise<readonly PlatformTaskItem[]>;
  /** Honest coverage. `{ kind: "unknown" }` until an honest page is read. */
  coverage(): PlatformTaskCoverageState;
  hasMore(): boolean;
  /** Append the next keyset page. No-op when there is no continuation. */
  loadMore(): Promise<void>;
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
   * The platform generation's tasks READ store.
   *
   * NAMED SEPARATELY ON PURPOSE, and `openTasks()` is NOT repointed at it. Fable
   * pre-ruled the flip PARKED for the wave-3 run (R7): production has no
   * control-state publisher, so every platform-generation write denies, and no
   * ratified path puts a real account's existing tasks behind the platform
   * generation — a flip today serves an empty list to a real account and refuses
   * every write. That is an outage, not a product event.
   *
   * So a surface that wants the platform read model asks for it BY NAME, exactly
   * as `openSynthesizedMemories()` works. When David ratifies the data path, the
   * flip is `openTasks: () => PlatformTasksStore.open(...)` — one line, and the
   * rollback is the same line, which is what D2's parity bought.
   */
  openPlatformTasks(): Promise<ProductionPlatformTaskStore>;
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
 * Note what the legacy ports do under a platform selection for memories:
 * `openMemories()` still returns the LEGACY editable store. That is not an
 * oversight. The two record classes coexist, and a surface that wants the
 * platform read model asks for it by name via `openSynthesizedMemories()`.
 * Pointing `openMemories()` at a read model that cannot create, patch or
 * delete would satisfy the type and break every caller at runtime.
 */
export function createPlatformProductionStoreFactory(
  bridge: StorageBridge,
  env: Env,
  transports: ProductionTransports,
  requestedGenerations?: unknown,
): PlatformProductionStoreFactory {
  const { selection, rejected } = resolveGenerationSelection(requestedGenerations);
  const legacy = createLegacyProductionStoreFactory(bridge, env, transports.legacyHttp);
  return {
    ...legacy,
    selection,
    rejected,
    openSynthesizedMemories: () =>
      SynthesizedMemoriesStore.open(bridge, env, transports.platformHttp),
    openPlatformTasks: () => PlatformTasksStore.open(bridge, env, transports.platformHttp),
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
