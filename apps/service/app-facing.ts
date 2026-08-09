// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
import { createHash } from "node:crypto";
import type { Database } from "bun:sqlite";
import { Hono } from "hono";

import { createSqliteQaRecallLoader } from "../../drivers/sqlite/application-recall-read";
import {
  createDevTokenIssuer,
  devPrincipalToAuthorizationRequest,
  type DevPrincipal,
} from "./auth/dev-token";
import { prepareMemoryRead, type CoherentQaLoad } from "./composition/memory-read";
import { createWriteFenceCounter, type WriteFenceCounter } from "./control/fence-counter";
import {
  createInMemoryAccountControlProjectionStore,
  type AccountControlProjectionStore,
} from "./control/projection-store";
import { DEFAULT_READ_ITEM_GRANULARITY } from "../../core/retrieve/granularity";
import { createServedCounter, type ServedCounter } from "./observability/served-count";
import { createWriteOpsCounter, type WriteOpsCounter } from "./observability/write-ops-counter";
import { QA_FIXTURE_TIME_ANCHOR_UTC, resetQaSnapshot, seedQaSnapshot } from "./qa/seed";
import { registerMemoryRoutes } from "./routes/memories";
import { registerQaRoutes } from "./routes/qa";
import { registerQaControlRoutes } from "./routes/qa-control";
import { registerTasksOpsRoutes } from "./routes/tasks-ops";
import { registerTasksReadRoutes } from "./routes/tasks-read";
import { prepareTasksRead } from "./composition/tasks-read";
import { createInMemoryStragglerTable, type StragglerTable } from "./stores/straggler-table";
import { createInMemoryTasksStore, type TasksReadStore, type TasksStore } from "./stores/tasks-store";
import { createInMemoryWriteIdRegistry, type WriteIdRegistry } from "./stores/write-id-registry";
import { createInMemoryWriteUnitOfWork, type WriteUnitOfWork } from "./stores/write-unit-of-work";

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
 * is supplied independently through the four store ports and their unit of
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
}

/** The four stores and their atomic write boundary, grouped at composition. */
export interface LocalServiceStores {
  readonly tasks: TasksStore;
  readonly registry: WriteIdRegistry;
  readonly unitOfWork: WriteUnitOfWork;
  readonly stragglers: StragglerTable;
  readonly control: AccountControlProjectionStore;
}

export const createInMemoryLocalServiceStores = (): LocalServiceStores => {
  const tasks = createInMemoryTasksStore();
  const registry = createInMemoryWriteIdRegistry();
  return Object.freeze({
    tasks,
    registry,
    unitOfWork: createInMemoryWriteUnitOfWork(tasks, registry),
    stragglers: createInMemoryStragglerTable(),
    control: createInMemoryAccountControlProjectionStore(),
  });
};

export interface LocalService {
  readonly app: Hono;
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
    readonly tasks: TasksStore;
    readonly tasksRead: TasksReadStore;
    readonly registry: WriteIdRegistry;
    readonly unitOfWork: WriteUnitOfWork;
    readonly stragglers: StragglerTable;
    readonly control: AccountControlProjectionStore;
    readonly fenceCounter: WriteFenceCounter;
    readonly opsCounter: WriteOpsCounter;
  };
}

export const createLocalService = (options: LocalServiceOptions): LocalService => {
  const reseed = (): void => {
    resetQaSnapshot(options.db);
    seedQaSnapshot(options.db, {
      owner_account_id: options.ownerAccountId,
      memory_count: options.memoryCount,
      account_timezone: options.accountTimezone,
    });
  };
  reseed();

  const stores = options.stores ?? createInMemoryLocalServiceStores();
  const tasks = stores.tasks;
  const writeIdRegistry = stores.registry;
  const unitOfWork = stores.unitOfWork;
  const stragglers = stores.stragglers;
  const controlStore = stores.control;

  const counter = createServedCounter();
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
  const resolvePrincipal = (token: string): DevPrincipal | null =>
    issuer.resolve(token, anchorEpochSeconds);

  const codecRootSecret = derive32(`${options.devSecretLabel}:codec-root`);
  const cursorSigningKeyset = {
    active_key_id: DEV_KEY_ID,
    keys: [{ key_id: DEV_KEY_ID, secret: derive32(`${options.devSecretLabel}:cursor`) }],
  };

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
  app.get("/health", () => {
    counter.recordNonDomainRequest();
    return new Response(JSON.stringify({ status: "ok" }), { status: 200, headers: JSON_HEADERS });
  });
  app.get("/ready", () => {
    counter.recordNonDomainRequest();
    return new Response(JSON.stringify({ status: "ready" }), { status: 200, headers: JSON_HEADERS });
  });
  registerMemoryRoutes(app, { resolvePrincipal, prepareRead, counter });
  registerTasksOpsRoutes(app, {
    resolvePrincipal,
    unitOfWork,
    stragglers,
    fence: { store: controlStore, counter: fenceCounter },
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
  registerQaControlRoutes(app, {
    resolvePrincipal,
    fence: { store: controlStore, counter: fenceCounter },
    writeOpsCounter: opsCounter,
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
    devToken,
    counter,
    reseed,
    seedIdentity,
    writePath: Object.freeze({
      tasks,
      tasksRead: tasks,
      registry: writeIdRegistry,
      unitOfWork,
      stragglers,
      control: controlStore,
      fenceCounter,
      opsCounter,
    }),
  });
};
