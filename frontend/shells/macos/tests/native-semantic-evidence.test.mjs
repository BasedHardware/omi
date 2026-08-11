import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "probes/native-semantic-evidence.swift");

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
      assert.match(help.stdout, /does not take screenshots/);

      const missing = spawnSync(binary, ["--name", "__omi-semantic-target-does-not-exist__", "--json"], {
        encoding: "utf8",
      });
      assert.equal(missing.status, 1, missing.stderr);
      const missingDocument = JSON.parse(missing.stdout);
      assert.equal(missingDocument.schema, "omi.native-semantic-evidence.v1");
      assert.equal(missingDocument.shell, "macos");
      assert.match(missingDocument.error, /^target-not-found:/);
      assert.deepEqual(missingDocument.keys, []);

      const loginPid = spawnSync("pgrep", ["-x", "loginwindow"], { encoding: "utf8" })
        .stdout.trim().split(/\s+/)[0];
      if (loginPid) {
        const observed = spawnSync(binary, ["--pid", loginPid, "--run-id", "ax-loginwindow-proof", "--json"], {
          encoding: "utf8",
        });
        assert.equal(observed.status, 0, `${observed.stdout}${observed.stderr}`);
        const document = JSON.parse(observed.stdout);
        assert.equal(document.schema, "omi.native-semantic-evidence.v1");
        assert.equal(document.shell, "macos");
        assert.equal(document.runId, "ax-loginwindow-proof");
        assert.equal(document.axTrusted, true);
        assert.ok(document.windows.some((window) => window.role === "AXWindow"));
        assert.deepEqual(document.keys, []);
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
  "headed shell keyboard sequence is available as an explicit operator probe",
  { skip: process.env.OMI_NATIVE_SEMANTIC_TARGET_PID ? false : "set OMI_NATIVE_SEMANTIC_TARGET_PID for headed-shell evidence" },
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
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
