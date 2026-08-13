import { randomBytes } from "node:crypto";
import {
  chmodSync, cpSync, existsSync, mkdirSync, readFileSync, realpathSync,
  renameSync, rmSync, writeFileSync,
} from "node:fs";
import { platform } from "node:os";
import { dirname, resolve } from "node:path";

import {
  POSTGRES_TEST_DATABASE, POSTGRES_TEST_ROOT, POSTGRES_TEST_USER,
  POSTGRES_TEST_BUN_IMAGE, POSTGRES_TEST_NODE_IMAGE,
  createPostgresTestState, dockerCommand, parsePostgresTestState,
  ambientPostgresSelectors,
  postgresContainerRunArguments, postgresTestConnectionString, postgresTestPaths,
  postgresTestRetention, withPostgresTestPort, withPostgresTestRuntime,
  type PostgresTestState,
} from "./postgres-test-lifecycle";
import {
  ensureOwnedVolume, inspectOwnedContainer, inspectOwnedVolume,
  removeOwnedContainer, removeOwnedVolume, verifyOwnedContainerConfiguration,
  type PostgresTestCommandRunner,
} from "./postgres-test-resources";
import { runPostgresLogicalRestoreDrill } from "./postgres-logical-restore-drill";
import { POSTGRES_MIGRATIONS } from "../drivers/postgres/migrations/manifest";

const PROJECT_ROOT = realpathSync(resolve(import.meta.dir, ".."));
const paths = postgresTestPaths(PROJECT_ROOT);

interface CommandResult {
  readonly exitCode: number;
  readonly stdout: string;
  readonly stderr: string;
}

const currentEnvironment = (): Record<string, string> => Object.fromEntries(
  Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
);

let dockerEnvironment: Record<string, string> = currentEnvironment();

const command = (
  args: readonly string[],
  options: { readonly env?: Record<string, string>; readonly inherit?: boolean } = {},
): CommandResult => {
  const result = Bun.spawnSync([...args], {
    cwd: PROJECT_ROOT,
    env: options.env ?? process.env,
    stdout: options.inherit ? "inherit" : "pipe",
    stderr: options.inherit ? "inherit" : "pipe",
  });
  return {
    exitCode: result.exitCode,
    stdout: result.stdout?.toString().trim() ?? "",
    stderr: result.stderr?.toString().trim() ?? "",
  };
};

const closedError = (code: string): never => { throw new Error(code); };

const assertNoAmbientPostgresSelectors = (): void => {
  if (ambientPostgresSelectors(process.env).length > 0) {
    return closedError("ambient_postgres_selector_forbidden");
  }
};

const loadState = (): PostgresTestState | null => {
  if (!existsSync(paths.stateFile)) return null;
  try {
    return parsePostgresTestState(JSON.parse(readFileSync(paths.stateFile, "utf8")), PROJECT_ROOT);
  } catch {
    return closedError("invalid_postgres_test_state");
  }
};

const saveState = (state: PostgresTestState): void => {
  mkdirSync(dirname(paths.stateFile), { recursive: true, mode: 0o700 });
  const temporary = `${paths.stateFile}.tmp-${process.pid}`;
  writeFileSync(temporary, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
  chmodSync(temporary, 0o600);
  renameSync(temporary, paths.stateFile);
};

const newPersistentState = (): PostgresTestState => {
  if (!existsSync("/Volumes/Ephemeral")) return closedError("ephemeral_volume_unavailable");
  const state = createPostgresTestState(PROJECT_ROOT);
  mkdirSync(state.runDirectory, { recursive: true, mode: 0o700 });
  writeFileSync(state.credentialsFile, [
    `POSTGRES_USER=${POSTGRES_TEST_USER}`,
    `POSTGRES_DB=${POSTGRES_TEST_DATABASE}`,
    `POSTGRES_PASSWORD=${randomBytes(32).toString("base64url")}`,
    "PGDATA=/var/lib/postgresql/18/docker",
    "",
  ].join("\n"), { mode: 0o600 });
  chmodSync(state.credentialsFile, 0o600);
  saveState(state);
  return state;
};

const docker = (args: readonly string[]): CommandResult =>
  command(dockerCommand(args), { env: dockerEnvironment });
const resourceRunner: PostgresTestCommandRunner = (args) => command(args, { env: dockerEnvironment });
const dockerAvailable = (): boolean => docker(["info", "--format", "{{.ServerVersion}}"]).exitCode === 0;
const commandAvailable = (name: string): boolean => command(["/usr/bin/which", name]).exitCode === 0;

const managedDockerEnvironment = (): Record<string, string> => {
  const result = command(["macctl", "container", "env"]);
  if (result.exitCode !== 0) return closedError("managed_container_environment_unavailable");
  const allowed = new Set(["COLIMA_HOME", "COLIMA_CACHE_HOME", "COLIMA_PROFILE", "DOCKER_CONFIG", "DOCKER_HOST"]);
  const environment = currentEnvironment();
  for (const line of result.stdout.split("\n")) {
    const match = /^export ([A-Z_]+)=([^\s]+)$/.exec(line);
    if (!match?.[1] || match[2] === undefined || !allowed.has(match[1])) {
      return closedError("managed_container_environment_invalid");
    }
    environment[match[1]] = match[2];
  }
  if (!environment["DOCKER_HOST"] || !environment["DOCKER_CONFIG"]) {
    return closedError("managed_container_environment_invalid");
  }
  return environment;
};

const startViaMachineConfig = (state: PostgresTestState): PostgresTestState => {
  const started = command(["macctl", "container", "start"], { inherit: true });
  if (started.exitCode !== 0) return closedError("managed_container_start_failed");
  dockerEnvironment = managedDockerEnvironment();
  if (!dockerAvailable()) return closedError("managed_docker_daemon_unavailable");
  const managed = withPostgresTestRuntime(state, { kind: "machine-config", startedByWorkflow: true });
  saveState(managed);
  return managed;
};

const ensureRuntime = (state: PostgresTestState, newlyCreated: boolean): PostgresTestState => {
  if (state.runtime.kind === "external-docker") {
    dockerEnvironment = currentEnvironment();
    if (dockerAvailable()) return state;
    if (!newlyCreated || platform() !== "darwin" || !commandAvailable("macctl")) {
      return closedError("docker_daemon_unavailable");
    }
    dockerEnvironment = managedDockerEnvironment();
    if (dockerAvailable()) {
      const managed = withPostgresTestRuntime(state, { kind: "machine-config", startedByWorkflow: false });
      saveState(managed);
      return managed;
    }
    return startViaMachineConfig(state);
  }
  if (platform() !== "darwin" || !commandAvailable("macctl")) {
    return closedError("managed_container_boundary_unavailable");
  }
  dockerEnvironment = managedDockerEnvironment();
  if (dockerAvailable()) return state;
  return startViaMachineConfig(state);
};

const containerRunning = (state: PostgresTestState): boolean => {
  if (!dockerAvailable() || inspectOwnedContainer(resourceRunner, state) === "missing") return false;
  return docker(["inspect", "--format", "{{.State.Running}}", state.containerName]).stdout === "true";
};

const waitHealthy = async (state: PostgresTestState): Promise<void> => {
  for (let attempt = 0; attempt < 240; attempt += 1) {
    const health = docker(["inspect", "--format", "{{.State.Health.Status}}", state.containerName]);
    if (health.stdout === "healthy") return;
    if (health.stdout === "unhealthy") return closedError("postgres_test_container_unhealthy");
    await Bun.sleep(250);
  }
  return closedError("postgres_test_container_health_timeout");
};

// Docker can briefly retain a healthy observation while PostgreSQL restarts
// during rapid disposable-volume cycles. Qualifying migrations requires a real
// SQL round-trip, not only the container health state.
const waitSqlReady = async (state: PostgresTestState): Promise<void> => {
  for (let attempt = 0; attempt < 240; attempt += 1) {
    const ready = docker([
      "exec", state.containerName,
      "psql", "--username", POSTGRES_TEST_USER, "--dbname", POSTGRES_TEST_DATABASE,
      "--no-password", "--tuples-only", "--no-align", "--command", "SELECT 1",
    ]);
    if (ready.exitCode === 0 && ready.stdout === "1") return;
    await Bun.sleep(250);
  }
  return closedError("postgres_test_sql_readiness_timeout");
};

const discoverPort = (state: PostgresTestState): number => {
  const result = docker(["port", state.containerName, "5432/tcp"]);
  const match = result.exitCode === 0 ? /^127\.0\.0\.1:(\d+)$/.exec(result.stdout) : null;
  if (!match?.[1]) return closedError("postgres_test_not_loopback_only");
  return Number(match[1]);
};

const setup = async (): Promise<{ readonly state: PostgresTestState; readonly started: boolean }> => {
  const loaded = loadState();
  let state = loaded ?? newPersistentState();
  state = ensureRuntime(state, loaded === null);
  const wasRunning = containerRunning(state);
  ensureOwnedVolume(resourceRunner, state);
  if (inspectOwnedContainer(resourceRunner, state) === "missing") {
    if (docker(postgresContainerRunArguments(state)).exitCode !== 0) {
      return closedError("postgres_test_container_start_failed");
    }
  } else if (!wasRunning && docker(["start", state.containerName]).exitCode !== 0) {
    return closedError("postgres_test_container_start_failed");
  }
  await waitHealthy(state);
  await waitSqlReady(state);
  verifyOwnedContainerConfiguration(resourceRunner, state);
  state = withPostgresTestPort(state, discoverPort(state));
  saveState(state);
  process.stdout.write(`${JSON.stringify({
    configured: true, runtime: state.runtime.kind, container: "running", volume: "present",
    host: "127.0.0.1", port: state.hostPort, image: state.image,
  })}\n`);
  return { state, started: !wasRunning };
};

const prepareStateRuntime = (state: PostgresTestState): boolean => {
  dockerEnvironment = state.runtime.kind === "machine-config"
    ? managedDockerEnvironment()
    : currentEnvironment();
  return dockerAvailable();
};

const status = (): void => {
  const state = loadState();
  if (!state) {
    process.stdout.write(`${JSON.stringify({ configured: false, runtime: "absent", container: "absent", volume: "absent" })}\n`);
    return;
  }
  const runtime = prepareStateRuntime(state) ? "running" : "stopped";
  const container = runtime === "running"
    ? inspectOwnedContainer(resourceRunner, state) === "owned"
      ? containerRunning(state) ? "running" : "stopped"
      : "absent"
    : "unknown-runtime-stopped";
  const volume = runtime === "running" ? inspectOwnedVolume(resourceRunner, state) : "unknown-runtime-stopped";
  process.stdout.write(`${JSON.stringify({
    configured: true, runtime, runtimeKind: state.runtime.kind, container, volume,
    host: "127.0.0.1", port: state.hostPort, image: state.image,
  })}\n`);
};

const stopOwnedContainer = (state: PostgresTestState): void => {
  if (!prepareStateRuntime(state)) {
    if (state.runtime.kind !== "machine-config") return closedError("docker_daemon_unavailable");
    startViaMachineConfig(state);
  }
  removeOwnedContainer(resourceRunner, state);
};

const stopManagedRuntimeIfOwned = (state: PostgresTestState): void => {
  if (state.runtime.kind === "machine-config" && state.runtime.startedByWorkflow) {
    if (command(["macctl", "container", "stop"], { inherit: true }).exitCode !== 0) {
      return closedError("managed_container_stop_failed");
    }
  }
};

const teardown = (): void => {
  const state = loadState();
  if (!state) { status(); return; }
  stopOwnedContainer(state);
  stopManagedRuntimeIfOwned(state);
  process.stdout.write(`${JSON.stringify({
    configured: true, runtime: state.runtime.startedByWorkflow ? "stopped" : "preserved",
    container: "absent", volume: "preserved", state: "preserved",
  })}\n`);
};

const validateRunDirectory = (state: PostgresTestState): void => {
  if (resolve(state.runDirectory) !== `${POSTGRES_TEST_ROOT}/runs/${state.instanceId}`) {
    return closedError("postgres_test_data_ownership_mismatch");
  }
};

const destroy = (confirmation: string | undefined): void => {
  if (confirmation !== "--yes") return closedError("postgres_test_destroy_requires_yes");
  const state = loadState();
  if (!state) { status(); return; }
  validateRunDirectory(state);
  stopOwnedContainer(state);
  removeOwnedVolume(resourceRunner, state);
  stopManagedRuntimeIfOwned(state);
  rmSync(state.runDirectory, { recursive: true, force: false });
  rmSync(paths.stateFile, { force: false });
  process.stdout.write(`${JSON.stringify({
    configured: false, runtime: "preserved-or-stopped", container: "absent", volume: "removed",
  })}\n`);
};

const passwordFrom = (state: PostgresTestState): string => {
  const line = readFileSync(state.credentialsFile, "utf8").split("\n")
    .find((entry) => entry.startsWith("POSTGRES_PASSWORD="));
  if (!line) return closedError("postgres_test_credentials_missing");
  return line.slice("POSTGRES_PASSWORD=".length);
};

const parityContainerOwner = (
  state: PostgresTestState,
  name: string,
  image: string,
): "missing" | "owned" => {
  const result = docker([
    "inspect", "--format",
    '{{index .Config.Labels "dev.omi.postgres-test.instance"}}|{{index .Config.Labels "dev.omi.postgres-test.project"}}|{{.Config.Image}}',
    name,
  ]);
  if (result.exitCode !== 0) return "missing";
  if (result.stdout !== `${state.instanceId}|${state.projectKey}|${image}`) {
    return closedError("postgres_parity_container_ownership_mismatch");
  }
  return "owned";
};

const removeParityContainer = (state: PostgresTestState, name: string, image: string): void => {
  if (parityContainerOwner(state, name, image) === "owned"
    && docker(["rm", "--force", name]).exitCode !== 0) {
    return closedError("postgres_parity_container_remove_failed");
  }
};

const buildParityCorpus = (state: PostgresTestState): string => {
  validateRunDirectory(state);
  const corpus = `${state.runDirectory}/runtime-parity-corpus`;
  rmSync(corpus, { recursive: true, force: true });
  mkdirSync(`${corpus}/node_modules`, { recursive: true, mode: 0o700 });
  cpSync(resolve(PROJECT_ROOT, "drivers/postgres/runtime-parity.mjs"), `${corpus}/runtime-parity.mjs`);
  cpSync(
    realpathSync(resolve(PROJECT_ROOT, "drivers/postgres/node_modules/postgres")),
    `${corpus}/node_modules/postgres`,
    { recursive: true },
  );
  return corpus;
};

const runParityContainer = (
  state: PostgresTestState,
  corpus: string,
  clientEnvironmentFile: string,
  runtime: "bun" | "node",
  image: string,
): void => {
  const name = `${state.containerName}-${runtime}-parity`;
  removeParityContainer(state, name, image);
  const created = docker([
    "create", "--name", name, "--platform", "linux/amd64",
    "--label", `dev.omi.postgres-test.instance=${state.instanceId}`,
    "--label", `dev.omi.postgres-test.project=${state.projectKey}`,
    "--network", `container:${state.containerName}`,
    "--env-file", clientEnvironmentFile, "--env", `OMI_TEST_RUNTIME=${runtime}`,
    "--workdir", "/workspace", image,
    runtime, "/workspace/runtime-parity.mjs",
  ]);
  if (created.exitCode !== 0 || parityContainerOwner(state, name, image) !== "owned") {
    return closedError("postgres_parity_container_create_failed");
  }
  try {
    const imagePlatform = docker([
      "image", "inspect", "--platform", "linux/amd64",
      "--format", "{{.Os}}/{{.Architecture}}", image,
    ]);
    if (imagePlatform.stdout !== "linux/amd64") return closedError("postgres_parity_image_platform_mismatch");
    if (docker(["cp", `${corpus}/.`, `${name}:/workspace`]).exitCode !== 0) {
      return closedError("postgres_parity_corpus_copy_failed");
    }
    const result = command(dockerCommand(["start", "--attach", name]), {
      env: dockerEnvironment, inherit: true,
    });
    if (result.exitCode !== 0) return closedError("postgres_parity_execution_failed");
  } finally {
    removeParityContainer(state, name, image);
  }
};

const runRuntimeParity = (state: PostgresTestState): void => {
  const corpus = buildParityCorpus(state);
  const clientEnvironmentFile = `${state.runDirectory}/runtime-parity.env`;
  const containerState = withPostgresTestPort(state, 5432);
  writeFileSync(clientEnvironmentFile, [
    `OMI_TEST_POSTGRES_URL=${postgresTestConnectionString(containerState, passwordFrom(state))}`,
    "",
  ].join("\n"), { mode: 0o600 });
  chmodSync(clientEnvironmentFile, 0o600);
  runParityContainer(state, corpus, clientEnvironmentFile, "bun", POSTGRES_TEST_BUN_IMAGE);
  runParityContainer(state, corpus, clientEnvironmentFile, "node", POSTGRES_TEST_NODE_IMAGE);
};

const testPostgres = async (preserve: boolean): Promise<void> => {
  const prepared = await setup();
  const childEnvironment = currentEnvironment();
  childEnvironment["OMI_TEST_POSTGRES_URL"] = postgresTestConnectionString(prepared.state, passwordFrom(prepared.state));
  childEnvironment["OMI_TEST_POSTGRES_IMAGE"] = prepared.state.image;
  try {
    const result = command(["bun", "test", "drivers/postgres/postgresjs.real.test.ts", "drivers/postgres/derived-group-dream-work-input.real.test.ts"], {
      env: childEnvironment, inherit: true,
    });
    if (result.exitCode !== 0) process.exitCode = result.exitCode;
    if (result.exitCode === 0) {
      const restoreDrill = runPostgresLogicalRestoreDrill(
        resourceRunner, prepared.state, POSTGRES_MIGRATIONS.length,
      );
      process.stdout.write(`${JSON.stringify(restoreDrill)}\n`);
      runRuntimeParity(prepared.state);
    }
  } finally {
    if (preserve) {
      if (prepared.started) teardown();
    } else {
      destroy("--yes");
    }
  }
};

const main = async (): Promise<void> => {
  assertNoAmbientPostgresSelectors();
  const [action, confirmation] = process.argv.slice(2);
  switch (action) {
    case "setup": await setup(); break;
    case "status": status(); break;
    case "test":
      await testPostgres(postgresTestRetention(confirmation) === "preserve");
      break;
    case "teardown": teardown(); break;
    case "destroy": destroy(confirmation); break;
    default: return closedError("usage_setup_status_test_test_preserve_teardown_destroy");
  }
};

await main();
