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
      `${root}/apps/service/stores/type-tests/tsconfig.json`,
      "--noEmit",
    ],
    cwd: root,
    stdout: "pipe",
    stderr: "pipe",
  });
  const output = `${result.stdout.toString()}${result.stderr.toString()}`;
  // Assert on diagnostics from OUR sources only.
  //
  // `skipLibCheck` is deliberately false so this gate checks real declarations,
  // which also means tsc reports diagnostics inside dependency `.d.ts` files.
  // Those are not a statement about the unit-of-work connection contract, and
  // they are not stable across layouts: when this package is vendored into a
  // workspace that carries its own `@types/node` (omi-v5 ships 22.20.1, this
  // repo ships none) `node:util` resolves to that copy instead of bun-types'
  // shims, emitting four errors inside `node_modules/**/bun-types/*.d.ts`.
  // Asserting on raw output therefore failed purely because of the enclosing
  // workspace's dependency set, with nothing in this package changed. Filtering
  // to our own files keeps the contract this test defends — a type error in the
  // fixture still fails it — without making the gate an assertion about a
  // dependency's declarations.
  const ownDiagnostics = output
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .filter((line) => !line.includes("node_modules/"));
  expect(ownDiagnostics).toEqual([]);
  // spawnSync already waits for tsc to exit. This number is a hung-process
  // ceiling, not a speed budget: bun's default 5000ms killed this test at
  // ~5037ms under machine load (rule18-honesty + coordinator landing) while
  // the same file isolated on the same tree finished in ~1.8s.
}, 30_000);
