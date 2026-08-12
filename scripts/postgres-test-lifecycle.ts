import { createHash, randomBytes } from "node:crypto";
import { resolve } from "node:path";

export const POSTGRES_TEST_IMAGE = "postgres:18.4-bookworm@sha256:882236b897e39051d2368c5ccc6cda944904723506b2dfc97f2a8f5bc9afa382" as const;
export const POSTGRES_TEST_PLATFORM = "linux/amd64" as const;
export const POSTGRES_TEST_SERVER_VERSION_NUM = 180004 as const;
export const POSTGRES_TEST_BUN_IMAGE = "oven/bun:1.3.14-slim@sha256:d56a2534ffd262e92c12fd3249d3924d296d97086da773f821d7d0477435ea04" as const;
export const POSTGRES_TEST_NODE_IMAGE = "node:24.19.0-bookworm-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03" as const;
export const POSTGRES_TEST_ROOT = "/Volumes/Ephemeral/scratch/omi-postgres-tests" as const;
export const POSTGRES_TEST_USER = "omi_test" as const;
export const POSTGRES_TEST_DATABASE = "omi_test" as const;

export type PostgresTestRuntime =
  | { readonly kind: "external-docker"; readonly startedByWorkflow: false }
  | { readonly kind: "machine-config"; readonly startedByWorkflow: boolean };

export interface PostgresTestState {
  readonly version: "omi-postgres-test-state-v1";
  readonly projectKey: string;
  readonly instanceId: string;
  readonly containerName: string;
  readonly image: typeof POSTGRES_TEST_IMAGE;
  readonly platform: typeof POSTGRES_TEST_PLATFORM;
  readonly runDirectory: string;
  readonly volumeName: string;
  readonly credentialsFile: string;
  readonly hostPort: number | null;
  readonly runtime: PostgresTestRuntime;
}

export interface PostgresTestPaths {
  readonly projectKey: string;
  readonly stateFile: string;
  readonly runsRoot: string;
}

export const ambientPostgresSelectors = (
  environment: Readonly<Record<string, string | undefined>>,
): readonly string[] => Object.freeze(Object.keys(environment)
  .filter((name) => name === "DATABASE_URL" || /^PG[A-Z0-9_]+$/.test(name))
  .sort());

const safeId = /^[a-f0-9]{12,32}$/;
const safePort = (value: unknown): value is number =>
  Number.isSafeInteger(value) && (value as number) >= 1_024 && (value as number) <= 65_535;

export const postgresTestPaths = (projectRoot: string): PostgresTestPaths => {
  const projectKey = createHash("sha256").update(resolve(projectRoot)).digest("hex").slice(0, 16);
  return Object.freeze({
    projectKey,
    stateFile: `${POSTGRES_TEST_ROOT}/state/${projectKey}.json`,
    runsRoot: `${POSTGRES_TEST_ROOT}/runs`,
  });
};

export const createPostgresTestState = (
  projectRoot: string,
  entropy: () => Uint8Array = () => randomBytes(12),
): PostgresTestState => {
  const paths = postgresTestPaths(projectRoot);
  const instanceId = Buffer.from(entropy()).toString("hex");
  if (!safeId.test(instanceId)) throw new TypeError("invalid_postgres_test_entropy");
  const runDirectory = `${paths.runsRoot}/${instanceId}`;
  return Object.freeze({
    version: "omi-postgres-test-state-v1",
    projectKey: paths.projectKey,
    instanceId,
    containerName: `omi-memory-postgres-${instanceId}`,
    image: POSTGRES_TEST_IMAGE,
    platform: POSTGRES_TEST_PLATFORM,
    runDirectory,
    volumeName: `omi-memory-postgres-data-${instanceId}`,
    credentialsFile: `${runDirectory}/credentials.env`,
    hostPort: null,
    runtime: Object.freeze({ kind: "external-docker", startedByWorkflow: false }),
  });
};

export const parsePostgresTestState = (
  value: unknown,
  projectRoot: string,
): PostgresTestState => {
  if (!value || typeof value !== "object" || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype) throw new TypeError("invalid_postgres_test_state");
  const input = value as Record<string, unknown>;
  const expected = [
    "version", "projectKey", "instanceId", "containerName", "image", "platform",
    "runDirectory", "volumeName", "credentialsFile", "hostPort", "runtime",
  ].sort();
  if (Object.keys(input).sort().join("\0") !== expected.join("\0")) {
    throw new TypeError("invalid_postgres_test_state");
  }
  const paths = postgresTestPaths(projectRoot);
  const instanceId = input["instanceId"];
  const exactRunDirectory = `${paths.runsRoot}/${String(instanceId)}`;
  const runtime = input["runtime"] as Record<string, unknown> | null;
  const runtimeValid = runtime !== null && typeof runtime === "object" && !Array.isArray(runtime)
    && Object.getPrototypeOf(runtime) === Object.prototype
    && (runtime["kind"] === "external-docker"
      ? runtime["startedByWorkflow"] === false
      : runtime["kind"] === "machine-config" && typeof runtime["startedByWorkflow"] === "boolean");
  if (input["version"] !== "omi-postgres-test-state-v1"
    || input["projectKey"] !== paths.projectKey
    || typeof instanceId !== "string" || !safeId.test(instanceId)
    || input["containerName"] !== `omi-memory-postgres-${instanceId}`
    || input["image"] !== POSTGRES_TEST_IMAGE || input["platform"] !== POSTGRES_TEST_PLATFORM
    || input["runDirectory"] !== exactRunDirectory
    || input["volumeName"] !== `omi-memory-postgres-data-${instanceId}`
    || input["credentialsFile"] !== `${exactRunDirectory}/credentials.env`
    || (input["hostPort"] !== null && !safePort(input["hostPort"]))
    || !runtimeValid) throw new TypeError("invalid_postgres_test_state");
  return Object.freeze(input as unknown as PostgresTestState);
};

export const withPostgresTestRuntime = (
  state: PostgresTestState,
  runtime: PostgresTestRuntime,
): PostgresTestState => Object.freeze({ ...state, runtime: Object.freeze(runtime) });

export const withPostgresTestPort = (
  state: PostgresTestState,
  hostPort: number,
): PostgresTestState => safePort(hostPort)
  ? Object.freeze({ ...state, hostPort })
  : (() => { throw new TypeError("invalid_postgres_test_port"); })();

export const dockerCommand = (
  args: readonly string[],
): readonly string[] => Object.freeze(["docker", ...args]);

export const postgresContainerRunArguments = (state: PostgresTestState): readonly string[] => Object.freeze([
  "run", "--detach",
  "--name", state.containerName,
  "--platform", POSTGRES_TEST_PLATFORM,
  "--label", `dev.omi.postgres-test.instance=${state.instanceId}`,
  "--label", `dev.omi.postgres-test.project=${state.projectKey}`,
  "--publish", "127.0.0.1::5432",
  "--env-file", state.credentialsFile,
  "--mount", `type=volume,source=${state.volumeName},target=/var/lib/postgresql`,
  "--health-cmd", `pg_isready -U ${POSTGRES_TEST_USER} -d ${POSTGRES_TEST_DATABASE}`,
  "--health-interval", "1s", "--health-timeout", "3s", "--health-retries", "60",
  POSTGRES_TEST_IMAGE,
]);

export const postgresTestConnectionString = (
  state: PostgresTestState,
  password: string,
): string => {
  if (state.hostPort === null || password.length < 32) throw new TypeError("postgres_test_not_ready");
  return `postgres://${encodeURIComponent(POSTGRES_TEST_USER)}:${encodeURIComponent(password)}`
    + `@127.0.0.1:${state.hostPort}/${encodeURIComponent(POSTGRES_TEST_DATABASE)}?sslmode=disable`;
};
