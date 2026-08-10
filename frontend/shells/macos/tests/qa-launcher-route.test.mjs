import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const launcher = resolve(root, "scripts/dev-run-macos.sh");

test("macOS QA launcher freezes 5290 and accepts only named production routes", () => {
  const source = readFileSync(launcher, "utf8");
  assert.match(source, /OMI_SURFACE_PORT:-5290/);
  assert.match(source, /home\|memories\|tasks\|conversations\|listen\|chat\|settings/);
  assert.doesNotMatch(source, /qa=|rig=dev|--fixture|4841/);

  const invalidRoute = spawnSync(launcher, ["--route", "not-a-route"], { encoding: "utf8" });
  assert.equal(invalidRoute.status, 2);
  assert.match(invalidRoute.stderr, /--route must be one of/);

  const wrongOrigin = spawnSync(launcher, ["--route", "chat"], {
    encoding: "utf8",
    env: { ...process.env, OMI_SURFACE_PORT: "5291" },
  });
  assert.equal(wrongOrigin.status, 1);
  assert.match(wrongOrigin.stderr, /must remain 5290/);

  const production = spawnSync(launcher, ["--api", "https://api.omi.me", "--route", "chat"], {
    encoding: "utf8",
  });
  assert.equal(production.status, 1);
  assert.match(production.stderr, /production api\.omi\.me is forbidden/);
  // red-proof: restoring the old 4841 default, accepting an arbitrary route,
  // or allowing api.omi.me fails one of the executable rows above.
});
