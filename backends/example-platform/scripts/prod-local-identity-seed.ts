#!/usr/bin/env bun
/**
 * Dev-only PostgreSQL authorization seed for `bun run prod-local --local-identity`.
 *
 * Lifts the revision+head recipe used by `drivers/postgres/postgresjs.real.test.ts`.
 * Refuses unless the managed local qualification harness is up. Does not insert
 * a fake restore-admission digest — generation release stays `bun run
 * test:postgres:preserve`.
 *
 * Usage:
 *   bun run scripts/prod-local-identity-seed.ts --uid <emulator-uid>
 */

import { existsSync, readFileSync, realpathSync } from "node:fs";
import { resolve } from "node:path";

import { createPostgresJsTransactionPool } from "../drivers/postgres/postgresjs";
import {
  LOCAL_APPLICATION_ID,
  LOCAL_FIREBASE_PROJECT_ID,
  LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST,
  PROD_LOCAL_AMBIENT_SELECTOR,
  PROD_LOCAL_PG_ABSENT,
  PROD_LOCAL_PG_NOT_RUNNING,
  interpretManagedPostgresState,
} from "./prod-local";
import {
  ambientPostgresSelectors,
  parsePostgresTestState,
  postgresTestConnectionString,
  postgresTestPaths,
  type PostgresTestState,
} from "./postgres-test-lifecycle";

const PROJECT_ROOT = realpathSync(resolve(import.meta.dir, ".."));
const UID_MAX = 128;
const ACCOUNT_PREFIX = "account:prod-local-identity:";
const PRINTABLE = /^[!-~]+$/;

export const PROD_LOCAL_IDENTITY_SEED_USAGE =
  "omi prod-local-identity-seed: usage: --uid <emulator-uid>";
export const PROD_LOCAL_IDENTITY_SEED_UID_INVALID =
  "omi prod-local-identity-seed: firebase uid is invalid.";
export const PROD_LOCAL_IDENTITY_SEED_GENERATION_UNRELEASED =
  "omi prod-local-identity-seed: qualification database generation is not released.";

export interface ProdLocalIdentitySeedCoordinates {
  readonly firebase_project_id: string;
  readonly firebase_uid: string;
  readonly application_id: string;
  readonly account_id: string;
  readonly principal_id: string;
  readonly credential_id: string;
  readonly grant_id: string;
}

export const parseSeedUid = (argv: readonly string[]): string | null => {
  const index = argv.indexOf("--uid");
  if (index < 0 || argv[index + 1] === undefined || argv[index + 1]!.startsWith("--")) return null;
  if (argv.filter((entry) => entry === "--uid").length !== 1) return null;
  const extra = argv.filter((entry, position) => entry.startsWith("--") && position !== index);
  if (extra.length > 0) return null;
  return argv[index + 1]!;
};

export const validFirebaseUid = (value: string): boolean =>
  value.length >= 1
  && value.length <= UID_MAX
  && PRINTABLE.test(value)
  && !/[\u0000-\u001f\u007f]/.test(value)
  && (ACCOUNT_PREFIX.length + value.length) <= 128;

export const prodLocalIdentitySeedCoordinates = (
  firebaseUid: string,
): ProdLocalIdentitySeedCoordinates => Object.freeze({
  firebase_project_id: LOCAL_FIREBASE_PROJECT_ID,
  firebase_uid: firebaseUid,
  application_id: LOCAL_APPLICATION_ID,
  account_id: `${ACCOUNT_PREFIX}${firebaseUid}`,
  principal_id: `principal:prod-local-identity:${firebaseUid}`,
  credential_id: `credential:prod-local-identity:${firebaseUid}`,
  grant_id: `grant:prod-local-identity:memories.read:${firebaseUid}`,
});

const fail = (message: string): never => {
  process.stderr.write(`\n${message}\n\n`);
  process.exit(1);
};

const loadState = (): PostgresTestState | null => {
  const paths = postgresTestPaths(PROJECT_ROOT);
  if (!existsSync(paths.stateFile)) return null;
  try {
    return parsePostgresTestState(JSON.parse(readFileSync(paths.stateFile, "utf8")), PROJECT_ROOT);
  } catch {
    return fail("omi prod-local-identity-seed: invalid managed PostgreSQL test state.");
  }
};

const passwordFrom = (state: PostgresTestState): string => {
  const line = readFileSync(state.credentialsFile, "utf8").split("\n")
    .find((entry) => entry.startsWith("POSTGRES_PASSWORD="));
  if (!line) return fail("omi prod-local-identity-seed: managed PostgreSQL credentials are missing.");
  return line.slice("POSTGRES_PASSWORD=".length);
};

const probeLoopbackPostgres = async (connectionString: string): Promise<boolean> => {
  const probe = createPostgresJsTransactionPool({
    connectionString,
    maxConnections: 1,
    connectTimeoutSeconds: 5,
  });
  try {
    return await probe.withTransaction(
      { isolationLevel: "serializable", accessMode: "read only" },
      async (connection) => {
        const rows = await connection.query<{ ok: number }>({
          name: "prod_local_identity_seed.probe",
          text: "SELECT 1 AS ok",
          values: [],
        });
        return rows[0]?.ok === 1;
      },
    );
  } catch {
    return false;
  } finally {
    await probe.close();
  }
};

const digest = (nibble: string): string => nibble.repeat(64);

export const seedProdLocalFirebaseAuthorizationSql = (
  coordinates: ProdLocalIdentitySeedCoordinates,
  nowEpochSeconds: number,
): readonly { readonly name: string; readonly text: string; readonly values: readonly (string | number)[] }[] =>
  Object.freeze([
    {
      name: "prod_local_identity_seed.account",
      text: `INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)
        ON CONFLICT (account_id) DO NOTHING`,
      values: [coordinates.account_id],
    },
    {
      name: "prod_local_identity_seed.control_revision",
      text: `INSERT INTO omi_memory.account_control_revisions
          (account_id, control_revision, account_generation, account_epoch,
           lifecycle_state, deletion_epoch, observed_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, 1, 'new', 1, 'active', NULL, transaction_timestamp(),
                'control-v1', '{}'::jsonb, $2)
        ON CONFLICT (account_id, control_revision) DO NOTHING`,
      values: [coordinates.account_id, digest("1")],
    },
    {
      name: "prod_local_identity_seed.control_head",
      text: `INSERT INTO omi_memory.account_control_heads
          (account_id, control_revision, activated_epoch, activation_control_revision)
        VALUES ($1, 1, 1, 1)
        ON CONFLICT (account_id) DO NOTHING`,
      values: [coordinates.account_id],
    },
    {
      name: "prod_local_identity_seed.credential_revision",
      text: `INSERT INTO omi_memory.application_credential_revisions
          (account_id, principal_id, application_id, credential_id,
           credential_generation, credential_kind, lifecycle,
           authentication_strength, expires_at, record_schema_version,
           record_json, content_hash)
        VALUES ($1, $2, $3, $4, 1, 'firebase', 'active', 'firebase-id-token',
                to_timestamp($5), 'credential-v1', '{}'::jsonb, $6)
        ON CONFLICT (account_id, application_id, credential_id, credential_generation) DO NOTHING`,
      values: [
        coordinates.account_id, coordinates.principal_id, coordinates.application_id,
        coordinates.credential_id, nowEpochSeconds + 31_536_000, digest("2"),
      ],
    },
    {
      name: "prod_local_identity_seed.credential_head",
      text: `INSERT INTO omi_memory.application_credential_heads
          (account_id, application_id, credential_id, credential_generation)
        VALUES ($1, $2, $3, 1)
        ON CONFLICT (account_id, application_id, credential_id) DO NOTHING`,
      values: [coordinates.account_id, coordinates.application_id, coordinates.credential_id],
    },
    {
      name: "prod_local_identity_seed.grant_revision",
      text: `INSERT INTO omi_memory.application_grant_revisions
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version, lifecycle, enabled, scopes,
           record_schema_version, record_json, content_hash)
        VALUES ($1, $2, $3, 1, 'memories.read', $4, 1, 'active', true,
                '[]'::jsonb, 'grant-v1', '{}'::jsonb, $5)
        ON CONFLICT (account_id, grant_id, grant_version) DO NOTHING`,
      values: [coordinates.account_id, coordinates.application_id, coordinates.credential_id,
        coordinates.grant_id, digest("3")],
    },
    {
      name: "prod_local_identity_seed.grant_head",
      text: `INSERT INTO omi_memory.application_grant_heads
          (account_id, application_id, credential_id, credential_generation,
           capability, grant_id, grant_version)
        VALUES ($1, $2, $3, 1, 'memories.read', $4, 1)
        ON CONFLICT (account_id, application_id, credential_id, credential_generation, capability)
          DO NOTHING`,
      values: [coordinates.account_id, coordinates.application_id, coordinates.credential_id,
        coordinates.grant_id],
    },
    {
      name: "prod_local_identity_seed.identity_binding",
      text: `INSERT INTO omi_memory.firebase_identity_bindings
          (firebase_project_id, firebase_uid, account_id, principal_id,
           source_control_revision)
        VALUES ($1, $2, $3, $4, 1)
        ON CONFLICT (firebase_project_id, firebase_uid) DO NOTHING`,
      values: [
        coordinates.firebase_project_id, coordinates.firebase_uid,
        coordinates.account_id, coordinates.principal_id,
      ],
    },
    {
      name: "prod_local_identity_seed.credential_binding",
      text: `INSERT INTO omi_memory.firebase_application_credential_bindings
          (account_id, firebase_project_id, firebase_uid, principal_id,
           application_id, credential_id)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (account_id, firebase_project_id, firebase_uid, application_id) DO NOTHING`,
      values: [
        coordinates.account_id, coordinates.firebase_project_id, coordinates.firebase_uid,
        coordinates.principal_id, coordinates.application_id, coordinates.credential_id,
      ],
    },
  ]);

const main = async (): Promise<void> => {
  if (ambientPostgresSelectors(process.env).length > 0) {
    return fail(
      `${PROD_LOCAL_AMBIENT_SELECTOR}\n`
      + "  Unset them. This script uses only the managed local PostgreSQL harness.",
    );
  }
  const uid = parseSeedUid(process.argv.slice(2));
  if (uid === null) return fail(PROD_LOCAL_IDENTITY_SEED_USAGE);
  if (!validFirebaseUid(uid)) return fail(PROD_LOCAL_IDENTITY_SEED_UID_INVALID);

  const presence = interpretManagedPostgresState(loadState());
  if (presence.kind === "absent") {
    return fail(
      `${PROD_LOCAL_PG_ABSENT}\n`
      + "  configured=false runtime=absent container=absent volume=absent\n"
      + "  Start it with: bun run test:postgres:setup",
    );
  }
  if (presence.kind === "not_ready") {
    return fail(
      `${PROD_LOCAL_PG_NOT_RUNNING}\n`
      + "  The managed harness has no loopback port yet.\n"
      + "  Start it with: bun run test:postgres:setup",
    );
  }
  const connectionString = postgresTestConnectionString(presence.state, passwordFrom(presence.state));
  if (!await probeLoopbackPostgres(connectionString)) {
    return fail(
      `${PROD_LOCAL_PG_NOT_RUNNING}\n`
      + "  configured=true container is not reachable on loopback.\n"
      + "  Start it with: bun run test:postgres:setup",
    );
  }

  const coordinates = prodLocalIdentitySeedCoordinates(uid);
  const pool = createPostgresJsTransactionPool({ connectionString, maxConnections: 1 });
  try {
    let released = false;
    try {
      released = await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read only" },
        async (connection) => {
          const rows = await connection.query<{ released: boolean }>({
            name: "prod_local_identity_seed.generation_released",
            text: `SELECT EXISTS (
              SELECT 1
              FROM omi_memory.postgres_restore_admission_heads AS head
              JOIN omi_memory.postgres_restore_admission_revisions AS release
                ON release.database_generation_digest = head.database_generation_digest
               AND release.release_revision = head.release_revision
               AND release.state = 'released'
              WHERE head.database_generation_digest = $1
            ) AS released`,
            values: [LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST],
          });
          return rows[0]?.released === true;
        },
      );
    } catch {
      released = false;
    }
    if (!released) {
      return fail(
        `${PROD_LOCAL_IDENTITY_SEED_GENERATION_UNRELEASED}\n`
        + "  Run: bun run test:postgres:preserve\n"
        + "  This script will not insert a fake restore-admission digest.",
      );
    }

    await pool.withTransaction(
      { isolationLevel: "serializable", accessMode: "read write" },
      async (connection) => {
        for (const statement of seedProdLocalFirebaseAuthorizationSql(
          coordinates,
          Math.floor(Date.now() / 1_000),
        )) {
          await connection.execute(statement);
        }
      },
    );

    let lookupCount = 0;
    try {
      lookupCount = await pool.withTransaction(
        { isolationLevel: "serializable", accessMode: "read only" },
        async (connection) => {
          await connection.query({
            name: "prod_local_identity_seed.set_application_role",
            text: "SET LOCAL ROLE omi_platform_application",
            values: [],
          });
          const rows = await connection.query<{ account_id: string }>({
            name: "prod_local_identity_seed.lookup",
            text: `SELECT account_id FROM omi_memory.lookup_released_unfenced_firebase_application_authorization(
              $1, $2, $3, 'memories.read', $4
            )`,
            values: [
              coordinates.firebase_project_id,
              coordinates.firebase_uid,
              coordinates.application_id,
              LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST,
            ],
          });
          return rows.length;
        },
      );
    } catch {
      return fail("omi prod-local-identity-seed: authorization lookup failed after seed.");
    }
    if (lookupCount !== 1) {
      return fail("omi prod-local-identity-seed: authorization lookup did not return the seeded row.");
    }
  } finally {
    await pool.close();
  }

  process.stdout.write(
    `omi prod-local-identity-seed: seeded memories.read authorization\n`
    + `  uid         ${coordinates.firebase_uid}\n`
    + `  account     ${coordinates.account_id}\n`
    + `  application ${coordinates.application_id}\n`
    + `  project     ${coordinates.firebase_project_id}\n`,
  );
};

if (import.meta.main) {
  await main();
}
