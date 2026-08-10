// domain-pending(DIV-DOMCORE-001)
// domain-pending(UNK-DOMCORE-002)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
import { createHash } from "node:crypto";
import type { Database } from "bun:sqlite";
import { Hono } from "hono";
import { websocket } from "hono/bun";

import { createSqliteQaRecallLoader } from "../../drivers/sqlite/application-recall-read";
import {
  createDevTokenIssuer,
  devPrincipalToAuthorizationRequest,
  type DevPrincipal,
} from "./auth/dev-token";
import {
  createInMemoryAccountLifecycleStore,
  type AccountLifecycleStore,
} from "./auth/account-lifecycle";
import {
  createInMemoryCurrentSessionPort,
  type CurrentSessionPort,
} from "./auth/current-session";
import { prepareMemoryRead, type CoherentQaLoad } from "./composition/memory-read";
import { createListenConversationFinalizer } from "./listen/conversation-finalizer";
import {
  createDeterministicListenConversationProcessor,
  type ListenConversationProcessorFactory,
} from "./listen/conversation-processor";
import {
  createScriptedTranscriptionSource,
  type TranscriptionSource,
} from "./listen/transcription-source";
import { createWriteFenceCounter, type WriteFenceCounter } from "./control/fence-counter";
import {
  createInMemoryAccountControlProjectionStore,
  type AccountControlProjectionStore,
} from "./control/projection-store";
import {
  createInMemorySettingsProjectionStore,
  type InMemorySettingsProjectionStore,
  type SettingsProjectionStore,
} from "./control/settings-projection";
import { DEFAULT_READ_ITEM_GRANULARITY } from "../../core/retrieve/granularity";
import { createServedCounter, type ServedCounter } from "./observability/served-count";
import {
  attributeServedReads,
  createServedReadAttribution,
  READ_CLIENT_ID_HEADER,
} from "./observability/served-read-attribution";
import { createWriteOpsCounter, type WriteOpsCounter } from "./observability/write-ops-counter";
import { QA_FIXTURE_TIME_ANCHOR_UTC, resetQaSnapshot, seedQaSnapshot } from "./qa/seed";
import {
  createChatGenerationSupervisor,
  type ChatGenerationSupervisor,
} from "./chat/generation-supervisor";
import {
  createEmptyChatGenerationContextSource,
  type ChatGenerationContextSource,
} from "./chat/generation-context";
import {
  createScriptedChatGenerationSource,
  type ChatGenerationSource,
} from "./chat/generation-source";
import { createChatHistoryCursorCodec } from "./chat/history-cursor";
import { registerChatMessagesRoutes } from "./routes/chat-messages";
import { registerConversationRoutes } from "./routes/conversations";
import { registerCurrentSessionRoutes } from "./routes/current-session";
import { registerFolderRoutes } from "./routes/folders";
import { registerMemoryRoutes } from "./routes/memories";
import {
  LISTEN_MAX_CREDENTIAL_LEASE_MILLISECONDS,
  registerListenRoutes,
} from "./routes/listen";
import { registerQaRoutes } from "./routes/qa";
import { registerQaControlRoutes } from "./routes/qa-control";
import { registerSettingsRoutes } from "./routes/settings";
import { registerTasksOpsRoutes } from "./routes/tasks-ops";
import { registerTasksReadRoutes } from "./routes/tasks-read";
import { prepareTasksRead } from "./composition/tasks-read";
import {
  createInMemoryConversationsStore,
  type ConversationRecord,
  type ConversationsStore,
} from "./stores/conversations-store";
import {
  createInMemoryFoldersStore,
  type FolderRecord,
  type FoldersStore,
} from "./stores/folders-store";
import {
  createInMemoryFolderDeletionUnitOfWork,
  type FolderDeletionUnitOfWork,
} from "./stores/folder-deletion-unit-of-work";
import { createInMemoryStragglerTable, type StragglerTable } from "./stores/straggler-table";
import { createInMemoryListenStore, type ListenStore } from "./stores/listen-store";
import {
  defineListenSegmentUnitOfWork,
  type ListenSegmentUnitOfWork,
} from "./stores/listen-segment-unit-of-work";
import { createUnitOfWorkContext, type UnitOfWorkContext } from "./stores/unit-of-work-context";
import { createInMemoryTasksStore, type TasksReadStore, type TasksStore } from "./stores/tasks-store";
import { createInMemoryWriteIdRegistry, type WriteIdRegistry } from "./stores/write-id-registry";
import { createInMemoryWriteUnitOfWork, type WriteUnitOfWork } from "./stores/write-unit-of-work";
import { createInMemoryChatAdmission, type ChatAdmission } from "./stores/chat-admission";
import {
  createInMemoryChatGenerationFinalization,
  type ChatGenerationFinalization,
} from "./stores/chat-generation-finalization";
import {
  createInMemoryChatGenerationEventsStore,
  type ChatGenerationEventsStore,
  type InMemoryChatGenerationEventsStore,
} from "./stores/chat-generation-events-store";
import {
  createInMemoryChatMessagesStore,
  type InMemoryChatMessagesStore,
  type ChatMessagesStore,
} from "./stores/chat-messages-store";

/**
 * Builds the complete app-facing service.
 *
 * This factory exists so that TESTS EXERCISE THE REAL APP. If the dev server
 * assembled its own routes inline and tests assembled a lookalike, both could
 * agree perfectly while the shipped binding was wrong - which is precisely how
 * a green hermetic suite once accompanied a bridge that served zero requests.
 * There is one wiring, here, and `bin/dev-server.ts` only adds process concerns
 * (config parsing, socket binding, printing).
 *
 * The `db` option is the local recall-fixture database. Write-path persistence
 * is supplied independently through the service store ports and their unit of
 * work; omitting it preserves the historical in-memory test/dev composition.
 */

const DEV_KEY_ID = "dev-local";
const DEV_TOKEN_TTL_SECONDS = 86_400;
const CURSOR_TTL_SECONDS = 3_600;
const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

const derive32 = (label: string): Uint8Array =>
  new Uint8Array(createHash("sha256").update(label, "utf8").digest());

export interface LocalServiceOptions {
  readonly db: Database;
  readonly ownerAccountId: string;
  readonly memoryCount: number;
  readonly accountTimezone: string;
  /** Non-secret dev label; a loopback fixture service has no real credential. */
  readonly devSecretLabel: string;
  /**
   * Write-path adapters. Omit for the historical in-memory local/test wiring.
   * The caller owns their lifecycle, including any SQLite Database handle.
   */
  readonly stores?: LocalServiceStores;
  /** Required fail-closed adapter for production-shaped composition. */
  readonly transcriptionSource: TranscriptionSource;
  /** Required downstream processing adapter factory, bound to this composition's store. */
  readonly conversationProcessorFactory: ListenConversationProcessorFactory;
  /** Dev-server-only seed. Existing Settings fixtures keep entitlement absent. */
  readonly listenDefaultUnmetered?: boolean;
  /** Required provider seam; production LLM integration is a later adapter. */
  readonly generationSource: ChatGenerationSource;
  /** Required consultation seam; memory implementation is owned outside Chat. */
  readonly generationContext: ChatGenerationContextSource;
  /** Test-only complete supervisor override. */
  readonly chatSupervisor?: ChatGenerationSupervisor;
  /** Test override; production-shaped listen authentication is rechecked at least once per second. */
  readonly listenCredentialLeaseMilliseconds?: number;
  readonly listenCredentialNowMilliseconds?: () => number;
}

/** The service stores and the tasks atomic write boundary, grouped at composition. */
export interface LocalServiceStores {
  readonly conversations: ConversationsStore;
  readonly folders: FoldersStore;
  readonly folderDeletion: FolderDeletionUnitOfWork;
  readonly tasks: TasksStore;
  readonly registry: WriteIdRegistry;
  readonly unitOfWork: WriteUnitOfWork;
  readonly stragglers: StragglerTable;
  readonly control: AccountControlProjectionStore;
  readonly settings: SettingsProjectionStore;
  readonly currentSession: CurrentSessionPort;
  readonly accountLifecycle: AccountLifecycleStore;
  readonly listen: ListenStore;
  readonly listenSegments: ListenSegmentUnitOfWork;
  readonly chatMessages: ChatMessagesStore;
  readonly chatEvents: ChatGenerationEventsStore;
  readonly chatAdmission: ChatAdmission;
  readonly chatFinalization: ChatGenerationFinalization;
}

export interface InMemoryLocalServiceStores extends LocalServiceStores {
  readonly settings: InMemorySettingsProjectionStore;
  readonly chatMessages: InMemoryChatMessagesStore;
  readonly chatEvents: InMemoryChatGenerationEventsStore;
}

const QA_FOLDER_SEED: readonly FolderRecord[] = Object.freeze([
  Object.freeze({
    id: "default-folder-qa",
    name: "Other",
    description: null,
    color: "#6B7280",
    icon: "folder",
    created_at: "2026-08-03T12:00:00.000Z",
    updated_at: QA_FIXTURE_TIME_ANCHOR_UTC,
    order: 0,
    is_default: true,
    is_system: true,
  }),
  Object.freeze({
    id: "work-folder-qa",
    name: "Work",
    description: "QA work items",
    color: "#007AFF",
    icon: "briefcase",
    created_at: "2026-08-03T12:00:00.000Z",
    updated_at: QA_FIXTURE_TIME_ANCHOR_UTC,
    order: 1,
    is_default: false,
    is_system: false,
  }),
]);

const QA_CONVERSATION_SEED: ConversationRecord = Object.freeze({
  id: "quiet-chat-qa",
  structured: Object.freeze({
    title: "QA bridge check",
    overview: "A deterministic conversation for shell acceptance.",
  }),
  created_at: "2026-08-03T12:00:00.000Z",
  updated_at: QA_FIXTURE_TIME_ANCHOR_UTC,
  started_at: "2026-08-07T11:50:00.000Z",
  finished_at: QA_FIXTURE_TIME_ANCHOR_UTC,
  source: "omi",
  status: "completed",
  discarded: false,
  starred: false,
  visibility: "private",
  is_locked: false,
  folder_id: "work-folder-qa",
});

export const createInMemoryLocalServiceStores = (): InMemoryLocalServiceStores => {
  const tasks = createInMemoryTasksStore();
  const registry = createInMemoryWriteIdRegistry();
  const folders = createInMemoryFoldersStore();
  const conversations = createInMemoryConversationsStore({
    hasFolder: (accountId, folderId) => folders.hasFolder(accountId, folderId),
  });
  const listen = createInMemoryListenStore();
  const settings = createInMemorySettingsProjectionStore();
  const listenConnection = Object.freeze({ listen, settings });
  const listenContext = createUnitOfWorkContext(listenConnection);
  const listenSegments = defineListenSegmentUnitOfWork({
    execute<Result>(
      _input,
      operation: (context: UnitOfWorkContext<typeof listenConnection>) => Result,
    ): Promise<Result> {
      return Promise.resolve(operation(listenContext));
    },
  }, {
    readEntitlement: (context, input) => context.perform(listenConnection, ({ settings }) =>
      settings.readEntitlement(input.accountId)),
    appendSegment: (context, input) => context.perform(listenConnection, ({ listen }) =>
      listen.appendSegment(input.accountId, input.sessionId, input.segment, input.at)),
    consumeTranscriptionSeconds: (context, input) => context.perform(listenConnection, ({ settings }) =>
      settings.consumeTranscriptionSeconds(input.accountId, input.consumedSeconds)),
  });
  const chatMessages = createInMemoryChatMessagesStore();
  const chatEvents = createInMemoryChatGenerationEventsStore();
  return Object.freeze({
    conversations,
    folders,
    folderDeletion: createInMemoryFolderDeletionUnitOfWork(folders, conversations),
    tasks,
    registry,
    unitOfWork: createInMemoryWriteUnitOfWork(tasks, registry),
    stragglers: createInMemoryStragglerTable(),
    control: createInMemoryAccountControlProjectionStore(),
    settings,
    currentSession: createInMemoryCurrentSessionPort(),
    accountLifecycle: createInMemoryAccountLifecycleStore(),
    listen,
    listenSegments,
    chatMessages,
    chatEvents,
    chatAdmission: createInMemoryChatAdmission(chatMessages, chatEvents, settings),
    chatFinalization: createInMemoryChatGenerationFinalization(chatMessages, chatEvents),
  });
};

export interface LocalService {
  readonly app: Hono;
  /** The Bun handler paired with `app.fetch` for real WebSocket upgrades. */
  readonly websocket: typeof websocket;
  readonly devToken: string;
  readonly counter: ServedCounter;
  readonly reseed: () => void;
  readonly seedIdentity: () => Readonly<Record<string, string | number>>;
  /**
   * The write path's stores and arbiters, exposed so a test or a booted stack
   * can drive and read them WITHOUT standing up a second server. The fence
   * harness existed because there was nowhere else to reach these; there is
   * now, which is what R5 asked for.
   *
   * `tasksRead` is deliberately typed as the READ interface: the read route
   * consumes this store read-only (R11), and the type is where that stays true.
   */
  readonly writePath: {
    readonly conversations: ConversationsStore;
    readonly folders: FoldersStore;
    readonly folderDeletion: FolderDeletionUnitOfWork;
    readonly tasks: TasksStore;
    readonly tasksRead: TasksReadStore;
    readonly registry: WriteIdRegistry;
    readonly unitOfWork: WriteUnitOfWork;
    readonly stragglers: StragglerTable;
    readonly control: AccountControlProjectionStore;
    readonly fenceCounter: WriteFenceCounter;
    readonly opsCounter: WriteOpsCounter;
    readonly settings: SettingsProjectionStore;
    readonly listen: ListenStore;
    readonly chatMessages: ChatMessagesStore;
    readonly chatEvents: ChatGenerationEventsStore;
    readonly chatAdmission: ChatAdmission;
  };
}

export type LocalDevServiceOptions = Omit<
  LocalServiceOptions,
  | "conversationProcessorFactory"
  | "transcriptionSource"
  | "generationSource"
  | "generationContext"
> & {
  /** Explicit dev/test override; omission selects the named scripted adapter. */
  readonly transcriptionSource?: TranscriptionSource;
  readonly conversationProcessorFactory?: ListenConversationProcessorFactory;
  readonly generationSource?: ChatGenerationSource;
  readonly generationContext?: ChatGenerationContextSource;
};

export const createLocalDevService = (options: LocalDevServiceOptions): LocalService =>
  createLocalService({
    ...options,
    transcriptionSource: options.transcriptionSource ?? createScriptedTranscriptionSource(),
    conversationProcessorFactory: options.conversationProcessorFactory
      ?? createDeterministicListenConversationProcessor,
    generationSource: options.generationSource ?? createScriptedChatGenerationSource(),
    generationContext: options.generationContext ?? createEmptyChatGenerationContextSource(),
  });

export const createLocalService = (options: LocalServiceOptions): LocalService => {
  if (options.transcriptionSource === undefined) {
    throw new TypeError("transcriptionSource is required");
  }
  if (options.conversationProcessorFactory === undefined) {
    throw new TypeError("conversationProcessorFactory is required");
  }
  if (options.generationSource === undefined) {
    throw new TypeError("generationSource is required");
  }
  if (options.generationContext === undefined) {
    throw new TypeError("generationContext is required");
  }
  const ownsStores = options.stores === undefined;
  const stores = options.stores ?? createInMemoryLocalServiceStores();
  const conversations = stores.conversations;
  const folders = stores.folders;
  const folderDeletion = stores.folderDeletion;
  let nextFolderId = 1;
  const reseed = (): void => {
    nextFolderId = 1;
    resetQaSnapshot(options.db);
    seedQaSnapshot(options.db, {
      owner_account_id: options.ownerAccountId,
      memory_count: options.memoryCount,
      account_timezone: options.accountTimezone,
    });
    if (ownsStores) {
      folders.reset();
      conversations.reset();
      for (const folder of QA_FOLDER_SEED) folders.upsert(options.ownerAccountId, folder);
      const seeded = conversations.upsert(options.ownerAccountId, QA_CONVERSATION_SEED);
      if (!seeded.stored) throw new TypeError("QA conversation seed references an unknown folder");
      stores.settings.putIdentity(options.ownerAccountId, {
        displayName: options.ownerAccountId,
        email: "",
      });
      stores.settings.putEntitlement(options.ownerAccountId, null);
      if (options.listenDefaultUnmetered === true) {
        stores.settings.putEntitlement(options.ownerAccountId, {
          planLabel: "Omi Plus",
          limitKey: "transcription_seconds",
          used: 0,
          limit: null,
          limitReached: false,
          upgradeAvailable: false,
        });
      }
      stores.listen.reset();
      stores.chatMessages.reset();
      stores.chatEvents.reset();
    }
  };
  reseed();

  const tasks = stores.tasks;
  const writeIdRegistry = stores.registry;
  const unitOfWork = stores.unitOfWork;
  const stragglers = stores.stragglers;
  const controlStore = stores.control;

  const readAttribution = createServedReadAttribution();
  const counter = attributeServedReads(createServedCounter(), readAttribution);
  const issuer = createDevTokenIssuer({
    signing_keyset: {
      active_key_id: DEV_KEY_ID,
      keys: [{ key_id: DEV_KEY_ID, secret: derive32(options.devSecretLabel) }],
    },
    ttl_seconds: DEV_TOKEN_TTL_SECONDS,
  });

  // A fixed instant keeps the token stable across restarts and keeps the whole
  // read path hermetic - no wall clock anywhere in the flow.
  const anchorEpochSeconds = Math.floor(Date.parse(QA_FIXTURE_TIME_ANCHOR_UTC) / 1000);
  const devToken = issuer.issue(options.ownerAccountId, anchorEpochSeconds);
  const resolveDevToken = (token: string): DevPrincipal | null =>
    issuer.resolve(token, anchorEpochSeconds);
  // Signature, TTL, revocation, and account existence are one authentication
  // result. Routes receive only the resolved principal/null boundary, so a
  // later production lifecycle source is an adapter swap rather than a route
  // retrofit.
  const resolveActiveDevToken = (token: string): DevPrincipal | null => {
    const principal = resolveDevToken(token);
    if (principal === null) return null;
    return stores.accountLifecycle.readLifecycle(principal.uid) === "active"
      ? principal
      : null;
  };
  const resolvePrincipal = (token: string): DevPrincipal | null =>
    stores.currentSession.authenticate(token, resolveActiveDevToken);

  const codecRootSecret = derive32(`${options.devSecretLabel}:codec-root`);
  const cursorSigningKeyset = {
    active_key_id: DEV_KEY_ID,
    keys: [{ key_id: DEV_KEY_ID, secret: derive32(`${options.devSecretLabel}:cursor`) }],
  };
  const chatCursor = createChatHistoryCursorCodec({
    activeId: DEV_KEY_ID,
    keys: [{ id: DEV_KEY_ID, secret: derive32(`${options.devSecretLabel}:chat-cursor`) }],
  });
  const opaqueChatId = (kind: string, ...parts: readonly string[]): string =>
    `${kind}_${createHash("sha256")
      .update(`${options.devSecretLabel}:chat:${kind}\0${parts.join("\0")}`, "utf8")
      .digest("hex")}`;
  const chatSupervisor = options.chatSupervisor ?? createChatGenerationSupervisor({
    source: options.generationSource,
    context: options.generationContext,
    messages: stores.chatMessages,
    events: stores.chatEvents,
    finalization: stores.chatFinalization,
    nowEpochMilliseconds: () => anchorEpochSeconds * 1_000,
    assistantMessageId: (accountId, generationId) =>
      opaqueChatId("assistant", accountId, generationId),
    eventId: (accountId, generationId, kind, sequence) =>
      opaqueChatId("event", accountId, generationId, kind, String(sequence)),
    revision: (accountId, messageId, payloadHash) =>
      opaqueChatId("revision", accountId, messageId, payloadHash),
  });
  chatSupervisor.recoverInterrupted();

  const prepareRead = async (principal: DevPrincipal) => {
    const loader = createSqliteQaRecallLoader({
      db: options.db,
      owner_account_id: principal.uid,
      account_timezone: options.accountTimezone,
      limits: { max_items: 512, max_bytes: 4_000_000 },
      // The seeder owns the whole corpus and writes no accepted work, so
      // "no eligible accepted work" is declared evidence here, not a guess.
      accepted_fixture_state: {
        state: "no_eligible",
        declared_frontier: null,
        searched_frontier: null,
        candidates: [],
      },
    });
    return prepareMemoryRead({
      loadCoherent: loader as unknown as () => CoherentQaLoad,
      // A thunk, not a value: the read core crosses the authorization boundary
      // twice per page, and passing a captured request meant a grant revoked
      // between the two loads was never observed.
      resolveAuthorization: () => devPrincipalToAuthorizationRequest(principal, {
        app_id: "omi-local-dev-app",
        key_id: DEV_KEY_ID,
      }),
      codecRootSecret,
      cursorSigningKeyset,
      cursorTtlSeconds: CURSOR_TTL_SECONDS,
      // Passed EXPLICITLY, never left to be implied by which handler is
      // running. The value is the app-facing default, but the read is told
      // which granularity it is serving rather than inferring it.
      // domain-pending(DIV-DOMCORE-008)
      granularity: DEFAULT_READ_ITEM_GRANULARITY,
      // DECLARED coverage, not counted at request time.
      //
      // This service owns its entire fixture: `reseed()` runs on construction
      // and on every /v1/qa/reset, `resetQaSnapshot` clears `stm_items`, and the
      // seeder never inserts an STM row. So "no eligible short-term material" is
      // true by construction here, and `app-facing.test.ts` asserts that
      // property of the seeder rather than trusting this comment.
      //
      // The distinction matters: deriving these from a row count would make a
      // wire-visible completeness field vary with rows outside the authorized
      // closure. A static declaration cannot.
      // domain-pending(DIV-DOMCORE-006)
      acceptedCoverageState: "no_eligible",
      // domain-pending(DIV-DOMCORE-006)
      stmCoverageState: "no_eligible",
      readTimestampEpochSeconds: anchorEpochSeconds,
      // Opaque references only, and this server has no reason to retain even those.
      traceSink: () => {},
    });
  };

  /**
   * The tasks read's prepared ports, per principal.
   *
   * `appliedFrontierState` is DECLARED here, and this call site is where the
   * declaration is earned rather than asserted: `registerTasksOpsRoutes` applies
   * into `tasks` SYNCHRONOUSLY, in-process, before it answers — so at the moment
   * this read runs there is no applied write that is not already in the store it
   * serves from. `caught_up` is therefore a property of this wiring, not a
   * guess, and `no_applied_writes` is the honest answer for an account the write
   * door has never touched. Deriving either from a row count would be the oracle
   * `composition/tasks-read.ts` refuses: a count varies with rows the reader is
   * not authorized to see.
   *
   * A deployment that ever applies writes ASYNCHRONOUSLY must declare `lagging`
   * here instead. That is the whole reason the state is a caller declaration and
   * not something the composition works out for itself.
   */
  const prepareTasksReadFor = (principal: DevPrincipal) => prepareTasksRead({
    store: tasks as TasksReadStore,
    resolveAuthorization: () => ({
      owner_account_id: principal.uid,
      app_id: "omi-local-dev-app",
      key_id: DEV_KEY_ID,
    }),
    codecRootSecret,
    cursorSigningKeyset,
    cursorTtlSeconds: CURSOR_TTL_SECONDS,
    readTimestampEpochSeconds: anchorEpochSeconds,
    appliedFrontierState: tasks.listRecords(principal.uid).length === 0
      ? "no_applied_writes"
      : "caught_up",
  });

  const seedIdentity = () => Object.freeze({
    owner_account_id: options.ownerAccountId,
    memory_count: options.memoryCount,
    account_timezone: options.accountTimezone,
    fixture_time_anchor_utc: QA_FIXTURE_TIME_ANCHOR_UTC,
  });

  // ── The write path ────────────────────────────────────────────────────────
  //
  // Constructed here for the same reason everything else is: TESTS EXERCISE THE
  // REAL APP. There is one wiring of the write door, and it is this one.
  //
  // The control projection starts EMPTY on purpose. Nothing in platform mints
  // control state (`EPOCH-fence-interface.md`), so every write denies
  // `control_unavailable` until a dev account is seeded through
  // `/v1/qa/control/*` (R3). Seeding it here by default would make the local
  // service disagree with the fail-closed posture the fence is built on.
  const fenceCounter = createWriteFenceCounter();
  const opsCounter = createWriteOpsCounter();

  const app = new Hono({ strict: true });
  app.use("*", (context, next) =>
    readAttribution.withRun(context.req.header(READ_CLIENT_ID_HEADER), next));
  app.get("/health", () => {
    counter.recordNonDomainRequest();
    return new Response(JSON.stringify({ status: "ok" }), { status: 200, headers: JSON_HEADERS });
  });
  app.get("/ready", () => {
    counter.recordNonDomainRequest();
    return new Response(JSON.stringify({ status: "ready" }), { status: 200, headers: JSON_HEADERS });
  });
  registerMemoryRoutes(app, { resolvePrincipal, prepareRead, counter });
  registerConversationRoutes(app, {
    resolvePrincipal,
    store: conversations,
    counter,
    now: () => QA_FIXTURE_TIME_ANCHOR_UTC,
  });
  registerFolderRoutes(app, {
    resolvePrincipal,
    store: folders,
    deletion: folderDeletion,
    counter,
    now: () => QA_FIXTURE_TIME_ANCHOR_UTC,
    createId: () => `qa-folder-created-${String(nextFolderId++).padStart(3, "0")}`,
  });
  registerTasksOpsRoutes(app, {
    resolvePrincipal,
    unitOfWork,
    stragglers,
    fence: {
      store: controlStore,
      entitlement: stores.settings,
      counter: fenceCounter,
    },
    counter: opsCounter,
    // The same fixed instant the read path uses. No wall clock anywhere.
    now: () => anchorEpochSeconds,
  });
  registerTasksReadRoutes(app, {
    resolvePrincipal,
    prepareRead: prepareTasksReadFor,
    fence: { store: controlStore },
    counter,
  });
  registerSettingsRoutes(app, {
    resolvePrincipal,
    projections: stores.settings,
    counter,
  });
  registerListenRoutes(app, {
    resolvePrincipal,
    entitlement: stores.settings,
    store: stores.listen,
    segments: stores.listenSegments,
    transcription: options.transcriptionSource,
    conversations: createListenConversationFinalizer(
      conversations,
      options.conversationProcessorFactory(conversations),
    ),
    now: () => QA_FIXTURE_TIME_ANCHOR_UTC,
    credentialLeaseMilliseconds: options.listenCredentialLeaseMilliseconds
      ?? LISTEN_MAX_CREDENTIAL_LEASE_MILLISECONDS,
    credentialNowMilliseconds: options.listenCredentialNowMilliseconds ?? Date.now,
  });
  registerChatMessagesRoutes(app, {
    resolvePrincipal,
    messages: stores.chatMessages,
    control: controlStore,
    admission: stores.chatAdmission,
    supervisor: chatSupervisor,
    events: stores.chatEvents,
    cursor: chatCursor,
    counter,
    nowEpochMilliseconds: () => anchorEpochSeconds * 1_000,
    nowEpochSeconds: () => anchorEpochSeconds,
    cursorTtlSeconds: CURSOR_TTL_SECONDS,
    generationId: (accountId, messageId) => opaqueChatId("generation", accountId, messageId),
    acceptedEventId: (accountId, generationId) =>
      opaqueChatId("event", accountId, generationId, "accepted"),
    revision: (accountId, messageId, journalRevision, payloadHash) =>
      opaqueChatId("revision", accountId, messageId, String(journalRevision), payloadHash),
  });
  registerCurrentSessionRoutes(app, {
    sessions: stores.currentSession,
    resolveDevToken: resolveActiveDevToken,
  });
  registerQaControlRoutes(app, {
    resolvePrincipal,
    fence: { store: controlStore, counter: fenceCounter },
    writeOpsCounter: opsCounter,
    readAttribution,
    stragglers,
    tasksRead: tasks,
    collectWriteIdsBelowEpoch: (accountId, activeEpoch) =>
      writeIdRegistry.collectBelowEpoch(accountId, activeEpoch),
    resetWriteState: () => {
      tasks.reset();
      writeIdRegistry.reset();
      stragglers.reset();
    },
  });
  registerQaRoutes(app, {
    counter,
    resetSeed: reseed,
    isAuthorizedControlToken: (token) => resolvePrincipal(token) !== null,
    seedIdentity,
  });
  app.notFound(() => {
    counter.recordNonDomainRequest();
    return new Response(JSON.stringify({ error: "not_found" }), { status: 404, headers: JSON_HEADERS });
  });

  return Object.freeze({
    app,
    websocket,
    devToken,
    counter,
    reseed,
    seedIdentity,
    writePath: Object.freeze({
      conversations,
      folders,
      folderDeletion,
      tasks,
      tasksRead: tasks,
      registry: writeIdRegistry,
      unitOfWork,
      stragglers,
      control: controlStore,
      fenceCounter,
      opsCounter,
      settings: stores.settings,
      listen: stores.listen,
      chatMessages: stores.chatMessages,
      chatEvents: stores.chatEvents,
      chatAdmission: stores.chatAdmission,
      chatFinalization: stores.chatFinalization,
    }),
  });
};
