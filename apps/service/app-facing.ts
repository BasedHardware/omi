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
import { DEFAULT_APP_FACING_MEMORY_READ_GRANULARITY } from "./composition/granularity";
import { createServedCounter, type ServedCounter } from "./observability/served-count";
import { QA_FIXTURE_TIME_ANCHOR_UTC, resetQaSnapshot, seedQaSnapshot } from "./qa/seed";
import { registerMemoryRoutes } from "./routes/memories";
import { registerQaRoutes } from "./routes/qa";

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
 * SQLite is QA fixture storage only and is never production authority.
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
}

export interface LocalService {
  readonly app: Hono;
  readonly devToken: string;
  readonly counter: ServedCounter;
  readonly reseed: () => void;
  readonly seedIdentity: () => Readonly<Record<string, string | number>>;
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
      authorizationRequest: devPrincipalToAuthorizationRequest(principal, {
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
      granularity: DEFAULT_APP_FACING_MEMORY_READ_GRANULARITY,
      readTimestampEpochSeconds: anchorEpochSeconds,
      // Opaque references only, and this server has no reason to retain even those.
      traceSink: () => {},
    });
  };

  const seedIdentity = () => Object.freeze({
    owner_account_id: options.ownerAccountId,
    memory_count: options.memoryCount,
    account_timezone: options.accountTimezone,
    fixture_time_anchor_utc: QA_FIXTURE_TIME_ANCHOR_UTC,
  });

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

  return Object.freeze({ app, devToken, counter, reseed, seedIdentity });
};
