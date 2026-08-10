import { expect, test } from "bun:test";

import {
  createUnitOfWorkContext,
  UnitOfWorkConnectionMismatchError,
} from "./unit-of-work-context";
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
