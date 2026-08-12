import { describe, expect, test } from "bun:test";

import {
  POSTGRES_TEST_IMAGE,
  POSTGRES_TEST_BUN_IMAGE,
  POSTGRES_TEST_NODE_IMAGE,
  POSTGRES_TEST_PLATFORM,
  createPostgresTestState,
  dockerCommand,
  parsePostgresTestState,
  postgresContainerRunArguments,
  postgresTestConnectionString,
  postgresTestPaths,
  withPostgresTestPort,
  withPostgresTestRuntime,
  ambientPostgresSelectors,
} from "./postgres-test-lifecycle";

const projectRoot = "/Volumes/Ephemeral/scratch/worktrees/omi-memory-productionization";
const state = () => createPostgresTestState(projectRoot, () => Uint8Array.from({ length: 12 }, () => 0xab));

describe("hermetic PostgreSQL lifecycle plan", () => {
  test("pins PostgreSQL 18.4 Bookworm, linux/amd64, loopback, and the PG18 volume root", () => {
    const value = state();
    const args = postgresContainerRunArguments(value);
    expect(value.image).toBe(POSTGRES_TEST_IMAGE);
    expect(value.platform).toBe(POSTGRES_TEST_PLATFORM);
    expect(args).toContain("127.0.0.1::5432");
    expect(args).toContain(`type=volume,source=${value.volumeName},target=/var/lib/postgresql`);
    expect(args.join(" ")).not.toContain("/var/lib/postgresql/data");
    expect(args.at(-1)).toBe("postgres:18.4-bookworm@sha256:882236b897e39051d2368c5ccc6cda944904723506b2dfc97f2a8f5bc9afa382");
    expect(POSTGRES_TEST_BUN_IMAGE).toContain("oven/bun:1.3.14-slim@sha256:");
    expect(POSTGRES_TEST_NODE_IMAGE).toContain("node:24.19.0-bookworm-slim@sha256:");
  });

  test("derives exact per-worktree resources and rejects drifted cleanup state", () => {
    const value = state();
    expect(parsePostgresTestState(JSON.parse(JSON.stringify(value)), projectRoot)).toEqual(value);
    expect(value.runDirectory).toBe("/Volumes/Ephemeral/scratch/omi-postgres-tests/runs/abababababababababababab");
    expect(value.containerName).toBe("omi-memory-postgres-abababababababababababab");
    expect(postgresTestPaths(projectRoot).stateFile).toMatch(/\/state\/[a-f0-9]{16}\.json$/);
    expect(() => parsePostgresTestState({ ...value, runDirectory: "/tmp" }, projectRoot))
      .toThrow("invalid_postgres_test_state");
    expect(() => parsePostgresTestState({ ...value, containerName: "postgres" }, projectRoot))
      .toThrow("invalid_postgres_test_state");
  });

  test("tracks machine-config ownership and never reads an ambient database URL", () => {
    const managed = withPostgresTestRuntime(state(), {
      kind: "machine-config", startedByWorkflow: true,
    });
    expect(dockerCommand(["info"])).toEqual(["docker", "info"]);
    const ready = withPostgresTestPort(managed, 15_432);
    const connection = postgresTestConnectionString(ready, "random-password-with-at-least-32-characters");
    expect(connection).toContain("@127.0.0.1:15432/omi_test?sslmode=disable");
    expect(connection).not.toContain(String(process.env["DATABASE_URL"]));
    expect(ambientPostgresSelectors({ DATABASE_URL: "secret", PGHOST: "prod", PGSERVICE: "live", PATH: "/bin" }))
      .toEqual(["DATABASE_URL", "PGHOST", "PGSERVICE"]);
  });
});
