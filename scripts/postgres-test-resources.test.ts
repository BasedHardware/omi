import { describe, expect, test } from "bun:test";

import { createPostgresTestState } from "./postgres-test-lifecycle";
import {
  ensureOwnedVolume,
  removeOwnedContainer,
  removeOwnedVolume,
  verifyOwnedContainerConfiguration,
  type PostgresTestCommandRunner,
} from "./postgres-test-resources";

const state = createPostgresTestState("/workspace", () => Uint8Array.from({ length: 12 }, () => 0xcd));

describe("executable PostgreSQL resource lifecycle", () => {
  test("creates, verifies, preserves, then explicitly removes only the exact labelled volume", () => {
    const calls: readonly string[][] = [];
    let volume = false;
    const run: PostgresTestCommandRunner = (args) => {
      (calls as string[][]).push([...args]);
      if (args[1] === "volume" && args[2] === "inspect") return volume
        ? { exitCode: 0, stdout: `${state.instanceId}|${state.projectKey}|${state.volumeName}`, stderr: "" }
        : { exitCode: 1, stdout: "", stderr: "missing" };
      if (args[1] === "volume" && args[2] === "create") {
        volume = true;
        return { exitCode: 0, stdout: state.volumeName, stderr: "" };
      }
      if (args[1] === "volume" && args[2] === "rm") {
        volume = false;
        return { exitCode: 0, stdout: state.volumeName, stderr: "" };
      }
      return { exitCode: 1, stdout: "", stderr: "unexpected" };
    };

    ensureOwnedVolume(run, state);
    expect(volume).toBe(true);
    removeOwnedVolume(run, state);
    expect(volume).toBe(false);
    expect(calls.some((args) => args.includes("--label"))).toBe(true);
    expect(calls.at(-1)).toEqual(["docker", "volume", "rm", state.volumeName]);
  });

  test("verifies digest, platform, loopback, exact volume target, and PGDATA before use", () => {
    const run: PostgresTestCommandRunner = (args) => {
      if (args[1] === "inspect" && args.some((arg) => arg.includes(".Config.Image}}|{{.Platform"))) {
        return { exitCode: 0, stdout: `${state.instanceId}|${state.projectKey}|${state.image}|linux`, stderr: "" };
      }
      if (args[1] === "inspect" && args.some((arg) => arg.includes(".HostConfig.PortBindings"))) {
        return { exitCode: 0, stdout: '[{"HostIp":"127.0.0.1","HostPort":"15432"}]', stderr: "" };
      }
      if (args[1] === "inspect" && args.some((arg) => arg.includes("{{range .Mounts}}"))) {
        return { exitCode: 0, stdout: `volume|${state.volumeName}|/var/lib/postgresql`, stderr: "" };
      }
      if (args[1] === "image") return { exitCode: 0, stdout: "linux/amd64", stderr: "" };
      if (args[1] === "exec") return { exitCode: 0, stdout: "/var/lib/postgresql/18/docker", stderr: "" };
      return { exitCode: 1, stdout: "", stderr: "unexpected" };
    };
    expect(() => verifyOwnedContainerConfiguration(run, state)).not.toThrow();
    expect(() => verifyOwnedContainerConfiguration((args) => {
      const result = run(args);
      return args[1] === "inspect" && args.some((arg) => arg.includes(".HostConfig.PortBindings"))
        ? { ...result, stdout: '[{"HostIp":"0.0.0.0","HostPort":"15432"}]' }
        : result;
    }, state)).toThrow("postgres_test_container_configuration_mismatch");
  });

  test("refuses to remove a container or volume whose labels drift", () => {
    const mismatch: PostgresTestCommandRunner = (args) => ({
      exitCode: 0,
      stdout: args[1] === "volume" ? `other|${state.projectKey}|${state.volumeName}` : `other|${state.projectKey}|${state.image}|linux`,
      stderr: "",
    });
    expect(() => removeOwnedContainer(mismatch, state)).toThrow("postgres_test_container_ownership_mismatch");
    expect(() => removeOwnedVolume(mismatch, state)).toThrow("postgres_test_volume_ownership_mismatch");
  });
});
