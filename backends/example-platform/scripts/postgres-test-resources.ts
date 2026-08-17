import type { PostgresTestState } from "./postgres-test-lifecycle";

export interface PostgresTestCommandResult {
  readonly exitCode: number;
  readonly stdout: string;
  readonly stderr: string;
}

export type PostgresTestCommandRunner = (args: readonly string[]) => PostgresTestCommandResult;

const fail = (code: string): never => { throw new Error(code); };

const volumeOwnership = (state: PostgresTestState): string =>
  `${state.instanceId}|${state.projectKey}|${state.volumeName}`;

export const inspectOwnedVolume = (
  run: PostgresTestCommandRunner,
  state: PostgresTestState,
): "missing" | "owned" => {
  const result = run([
    "docker", "volume", "inspect", "--format",
    '{{index .Labels "dev.omi.postgres-test.instance"}}|{{index .Labels "dev.omi.postgres-test.project"}}|{{.Name}}',
    state.volumeName,
  ]);
  if (result.exitCode !== 0) return "missing";
  if (result.stdout !== volumeOwnership(state)) return fail("postgres_test_volume_ownership_mismatch");
  return "owned";
};

export const ensureOwnedVolume = (
  run: PostgresTestCommandRunner,
  state: PostgresTestState,
): void => {
  if (inspectOwnedVolume(run, state) === "missing") {
    const created = run([
      "docker", "volume", "create",
      "--label", `dev.omi.postgres-test.instance=${state.instanceId}`,
      "--label", `dev.omi.postgres-test.project=${state.projectKey}`,
      state.volumeName,
    ]);
    if (created.exitCode !== 0 || created.stdout !== state.volumeName) {
      return fail("postgres_test_volume_create_failed");
    }
  }
  if (inspectOwnedVolume(run, state) !== "owned") return fail("postgres_test_volume_create_failed");
};

export const inspectOwnedContainer = (
  run: PostgresTestCommandRunner,
  state: PostgresTestState,
): "missing" | "owned" => {
  const result = run([
    "docker", "inspect", "--format",
    '{{index .Config.Labels "dev.omi.postgres-test.instance"}}|{{index .Config.Labels "dev.omi.postgres-test.project"}}|{{.Config.Image}}|{{.Platform}}',
    state.containerName,
  ]);
  if (result.exitCode !== 0) return "missing";
  const expected = `${state.instanceId}|${state.projectKey}|${state.image}|linux`;
  if (result.stdout !== expected) return fail("postgres_test_container_ownership_mismatch");
  return "owned";
};

export const verifyOwnedContainerConfiguration = (
  run: PostgresTestCommandRunner,
  state: PostgresTestState,
): void => {
  if (inspectOwnedContainer(run, state) !== "owned") return fail("postgres_test_container_missing");
  const binding = run([
    "docker", "inspect", "--format",
    '{{json (index .HostConfig.PortBindings "5432/tcp")}}', state.containerName,
  ]);
  let parsedBinding: unknown;
  try { parsedBinding = JSON.parse(binding.stdout); } catch { return fail("postgres_test_container_configuration_mismatch"); }
  if (!Array.isArray(parsedBinding) || parsedBinding.length !== 1
    || (parsedBinding[0] as Record<string, unknown>)["HostIp"] !== "127.0.0.1"
    || typeof (parsedBinding[0] as Record<string, unknown>)["HostPort"] !== "string") {
    return fail("postgres_test_container_configuration_mismatch");
  }
  const mount = run([
    "docker", "inspect", "--format",
    '{{range .Mounts}}{{.Type}}|{{.Name}}|{{.Destination}}{{println}}{{end}}', state.containerName,
  ]);
  if (mount.stdout !== `volume|${state.volumeName}|/var/lib/postgresql`) {
    return fail("postgres_test_container_configuration_mismatch");
  }
  // The containerd image store keeps the pinned multi-architecture index as the
  // visible image object. Select the frozen child platform explicitly so the
  // check proves the executable manifest rather than inspecting the index.
  const image = run([
    "docker", "image", "inspect", "--platform", "linux/amd64",
    "--format", "{{.Os}}/{{.Architecture}}", state.image,
  ]);
  if (image.stdout !== "linux/amd64") return fail("postgres_test_container_configuration_mismatch");
  const pgdata = run(["docker", "exec", state.containerName, "printenv", "PGDATA"]);
  if (pgdata.stdout !== "/var/lib/postgresql/18/docker") {
    return fail("postgres_test_container_configuration_mismatch");
  }
};

export const removeOwnedContainer = (
  run: PostgresTestCommandRunner,
  state: PostgresTestState,
): void => {
  if (inspectOwnedContainer(run, state) === "missing") return;
  const removed = run(["docker", "rm", "--force", state.containerName]);
  if (removed.exitCode !== 0) return fail("postgres_test_container_remove_failed");
};

export const removeOwnedVolume = (
  run: PostgresTestCommandRunner,
  state: PostgresTestState,
): void => {
  if (inspectOwnedVolume(run, state) === "missing") return;
  const removed = run(["docker", "volume", "rm", state.volumeName]);
  if (removed.exitCode !== 0) return fail("postgres_test_volume_remove_failed");
};
