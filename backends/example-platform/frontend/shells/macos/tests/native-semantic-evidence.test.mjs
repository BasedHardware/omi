import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "probes/native-semantic-evidence.swift");

test("AX probe can request trust for this binary without targeting Chat", () => {
  const text = readFileSync(source, "utf8");
  assert.match(text, /--request-trust/);
  assert.match(text, /AXIsProcessTrustedWithOptions/);
  assert.match(text, /x-apple\.systempreferences:com\.apple\.preference\.security\?Privacy_Accessibility/);
  assert.match(text, /omi\.native-semantic-trust-request\.v1/);
  assert.match(text, /probePath/);
  const launcher = readFileSync(join(root, "scripts/dev-run-macos.sh"), "utf8");
  assert.match(launcher, /OMI_AX_PROBE_PATH/);
  assert.match(launcher, /native-semantic-evidence\.swift/);
  assert.match(launcher, /OMI_HEADED/);
});

function hasNativeToolchain() {
  if (process.platform !== "darwin") return false;
  try {
    execFileSync("swiftc", ["--version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

test(
  "macOS semantic evidence probe compiles, emits honest AX JSON, and keeps key posting explicit",
  { skip: hasNativeToolchain() ? false : "macOS swiftc is unavailable" },
  () => {
    const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-evidence-"));
    try {
      const binary = join(scratch, "native-semantic-evidence");
      execFileSync(
        "swiftc",
        [
          "-O",
          "-framework",
          "AppKit",
          "-framework",
          "ApplicationServices",
          "-framework",
          "CoreGraphics",
          "-o",
          binary,
          source,
        ],
        { env: { ...process.env, CLANG_MODULE_CACHE_PATH: join(scratch, "module-cache") } },
      );

      const help = spawnSync(binary, ["--help"], { encoding: "utf8" });
      assert.equal(help.status, 0, help.stderr);
      assert.match(help.stdout, /AXUIElement/);
      assert.match(help.stdout, /--keys SPEC/);
      assert.match(help.stdout, /--request-trust/);
      assert.match(help.stdout, /does not take screenshots/);

      const missing = spawnSync(binary, ["--name", "__omi-semantic-target-does-not-exist__", "--json"], {
        encoding: "utf8",
      });
      assert.equal(missing.status, 1, missing.stderr);
      const missingDocument = JSON.parse(missing.stdout);
      assert.equal(missingDocument.schema, "omi.native-semantic-evidence.v2");
      assert.equal(missingDocument.shell, "macos");
      assert.match(missingDocument.error, /^target-not-found:/);
      assert.deepEqual(missingDocument.keys, []);

      const selfTest = spawnSync(binary, ["--self-test", "--json"], { encoding: "utf8" });
      assert.equal(selfTest.status, 0, selfTest.stderr);
      assert.deepEqual(JSON.parse(selfTest.stdout), {
        schema: "omi.native-semantic-self-test.v1",
        passed: true,
      });

      const loginPid = spawnSync("pgrep", ["-x", "loginwindow"], { encoding: "utf8" })
        .stdout.trim().split(/\s+/)[0];
      if (loginPid) {
        const observed = spawnSync(binary, ["--pid", loginPid, "--run-id", "ax-loginwindow-proof", "--json"], {
          encoding: "utf8",
        });
        const document = JSON.parse(observed.stdout);
        if (observed.status === 1) {
          assert.match(document.error, /^no-accessible-window:/);
          assert.deepEqual(document.keys, []);
        } else {
          assert.equal(observed.status, 0, `${observed.stdout}${observed.stderr}`);
          assert.equal(document.schema, "omi.native-semantic-evidence.v2");
          assert.equal(document.shell, "macos");
          assert.equal(document.runId, "ax-loginwindow-proof");
          assert.equal(document.axTrusted, true);
          assert.equal(document.evidenceClass, "supplementary_observation");
          assert.equal(document.matrixEligible, false);
          assert.equal(document.domainLandmarkFound, false);
          assert.ok(document.windows.every((window) => !Object.hasOwn(window, "title")));
          assert.ok(document.nodes.every((node) => !Object.hasOwn(node, "title") && !Object.hasOwn(node, "description") && !Object.hasOwn(node, "value") && !Object.hasOwn(node, "focusWindowContext")));
          assert.deepEqual(document.keys, []);
        }
      }

      const implicitFocusSteal = spawnSync(binary, [
        "--name",
        "__omi-semantic-target-does-not-exist__",
        "--keys",
        "cmd+k,escape",
        "--json",
      ], { encoding: "utf8" });
      assert.equal(implicitFocusSteal.status, 2);
      assert.match(implicitFocusSteal.stderr, /--keys requires --activate/);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);

test(
  "matrix mode rejects missing target/source/coordinate binding instead of downgrading to generic evidence",
  { skip: hasNativeToolchain() ? false : "macOS swiftc is unavailable" },
  () => {
    const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-binding-"));
    try {
      const binary = join(scratch, "native-semantic-evidence");
      execFileSync("swiftc", ["-O", "-framework", "AppKit", "-framework", "ApplicationServices", "-framework", "CoreGraphics", "-o", binary, source]);
      const result = spawnSync(binary, ["--name", "loginwindow", "--require-matrix", "--json"], { encoding: "utf8" });
      assert.equal(result.status, 2);
      assert.match(result.stderr, /invalid-matrix-binding/);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);

test(
  "headed shell keyboard sequence is available as an explicit operator probe",
  {
    skip:
      process.env.OMI_NATIVE_SEMANTIC_TARGET_PID &&
      process.env.OMI_ALLOW_TEMPORARY_FOCUS === "1" &&
      process.env.OMI_RUN_INTERACTIVE_FIXTURE_TESTS === "1"
        ? false
        : "set target PID plus OMI_ALLOW_TEMPORARY_FOCUS=1 and OMI_RUN_INTERACTIVE_FIXTURE_TESTS=1",
  },
  () => {
    const scratch = mkdtempSync(join(tmpdir(), "omi-native-semantic-operator-"));
    try {
      const binary = join(scratch, "native-semantic-evidence");
      execFileSync("swiftc", [
        "-O", "-framework", "AppKit", "-framework", "ApplicationServices",
        "-framework", "CoreGraphics", "-o", binary, source,
      ]);
      const result = spawnSync(binary, [
        "--pid", process.env.OMI_NATIVE_SEMANTIC_TARGET_PID,
        "--activate", "--keys", "cmd+k,escape", "--json",
      ], { encoding: "utf8" });
      assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
      const document = JSON.parse(result.stdout);
      assert.equal(document.shell, "macos");
      assert.equal(document.keys.length, 2);
      assert.deepEqual(document.keys.map((key) => key.key), ["cmd+k", "escape"]);
      assert.equal(document.focusRestored, true);
      assert.equal(document.frontmostRestored, true);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
