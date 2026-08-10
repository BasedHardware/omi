import { expect, test } from "bun:test";

import {
  createUnitOfWorkContext,
  UnitOfWorkConnectionMismatchError,
} from "./unit-of-work-context";

import {
  FOLDER_DELETION_REPLAY_SEMANTICS,
  FOLDER_DELETION_RETRY_POLICY,
  FolderDeletionRetryExhaustedError,
} from "./folder-deletion-unit-of-work";

test("folder deletion pins retry exhaustion and non-idempotent replay", () => {
  expect(FOLDER_DELETION_RETRY_POLICY).toEqual({
    maximumAttempts: 3,
    backoffMilliseconds: [25, 100],
  });
  expect(FOLDER_DELETION_REPLAY_SEMANTICS).toBe("non_idempotent");
  const cause = new Error("serialization failure");
  const exhausted = new FolderDeletionRetryExhaustedError(cause);
  expect(exhausted.attempts).toBe(3);
  expect(exhausted.lastCause).toBe(cause);
  expect(exhausted.cause).toBe(cause);
});

test("rejects two same-typed runtime connection instances", () => {
  interface Connection {
    readonly label: string;
  }
  const first: Connection = { label: "first" };
  const second: Connection = { label: "second" };
  const context = createUnitOfWorkContext(first);

  expect(() => context.perform(second, () => "wrong connection ran"))
    .toThrow(UnitOfWorkConnectionMismatchError);

  const otherContext = createUnitOfWorkContext(second);
  const otherEffect = otherContext.perform(second, () => "wrong effect");
  expect(() => context.resolve(otherEffect)).toThrow(UnitOfWorkConnectionMismatchError);
});

test("unit-of-work adapters share one compile-time connection context", () => {
  const root = new URL("../../..", import.meta.url).pathname;
  const result = Bun.spawnSync({
    cmd: [
      `${root}/node_modules/.bin/tsc`,
      "-p",
      `${root}/tsconfig.unit-of-work.json`,
      "--noEmit",
    ],
    cwd: root,
    stdout: "pipe",
    stderr: "pipe",
  });
  const output = `${result.stdout.toString()}${result.stderr.toString()}`;
  expect(output).toBe("");
  expect(result.exitCode).toBe(0);
});
