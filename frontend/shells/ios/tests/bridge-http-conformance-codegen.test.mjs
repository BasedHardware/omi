import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const core = path.resolve(here, "../../..");
const generator = path.join(core, "scripts/gen-bridge-http-conformance.mjs");

function run(iosDir, macDir, check = false) {
  return spawnSync(process.execPath, [generator, ...(check ? ["--check"] : [])], {
    cwd: core,
    encoding: "utf8",
    env: {
      ...process.env,
      OMI_IOS_SHELL_DIR: iosDir,
      OMI_MACOS_SHELL_DIR: macDir,
    },
  });
}

test("Dart conformance generator owns the analyzer-safe package import", () => {
  const root = mkdtempSync(path.join(tmpdir(), "omi-bridge-http-dart-drift-"));
  try {
    const iosDir = path.join(root, "ios");
    const macDir = path.join(root, "missing-macos");
    mkdirSync(path.join(iosDir, "app/test"), { recursive: true });
    const generated = run(iosDir, macDir);
    assert.equal(generated.status, 0, generated.stderr || generated.stdout);
    const output = path.join(
      iosDir,
      "app/test/bridge_http_conformance_generated_test.dart",
    );
    const source = readFileSync(output, "utf8");
    assert.match(
      source,
      /import 'package:omi_webview_proto\/bridge_http_host\.dart';/,
    );

    writeFileSync(
      output,
      source.replace(
        "import 'package:omi_webview_proto/bridge_http_host.dart';",
        "import '../lib/bridge_http_host.dart';",
      ),
    );
    const drift = run(iosDir, macDir, true);
    assert.equal(drift.status, 1, drift.stderr || drift.stdout);
    assert.match(drift.stderr, /bridge-http Dart conformance drift/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
