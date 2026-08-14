import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import test from "node:test";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const appDelegate = await readFile(resolve(ROOT, "app/ios/Runner/AppDelegate.swift"), "utf8");
const dartHost = await readFile(resolve(ROOT, "app/lib/listen_socket_host.dart"), "utf8");

function hasDart() {
  try { execFileSync("dart", ["--version"], { stdio: "ignore" }); return true; }
  catch { return false; }
}

test("iOS Listen preflight uses native permission APIs and never exposes hardware ids", () => {
  // red-proof: replacing the native check with a hard-coded grant or adding a
  // device identifier to the callback must make this conformance assertion fail.
  assert.match(appDelegate, /AVAudioSession\.sharedInstance\(\)/);
  assert.match(appDelegate, /requestRecordPermission/);
  assert.match(appDelegate, /openSettingsURLString/);
  assert.match(appDelegate, /Default microphone/);
  assert.doesNotMatch(appDelegate, /device(?:Id|UUID|Uid)\b|serial(?:number)?\b/i);
  assert.match(dartHost, /omi\/listen-preflight/);
  assert.match(dartHost, /__omiListenPreflightEvent/);
  assert.match(dartHost, /listenPreflightCanOpen/);
  assert.match(dartHost, /_listenPreflightReady/);
  assert.match(dartHost, /'type': 'close', 'code': 1008/);
  assert.match(dartHost, /permission.*unavailable/s);
  assert.doesNotMatch(dartHost, /device(?:Id|UUID|Uid)\b|serial(?:number)?\b/i);
});

test(
  "iOS Listen native open gate distinguishes denied and granted preflight",
  { skip: hasDart() ? false : "dart not available" },
  () => {
    const scratch = mkdtempSync(join(tmpdir(), "omi-ios-listen-preflight-"));
    try {
      const main = join(scratch, "main.dart");
      writeFileSync(main, `import '${resolve(ROOT, "app/lib/listen_preflight_policy.dart")}' as policy;
void main() {
  print('DENIED=' + policy.listenPreflightCanOpen(<Object?, Object?>{'permission': 'denied', 'deviceState': 'unavailable'}).toString());
  print('GRANTED=' + policy.listenPreflightCanOpen(<Object?, Object?>{'permission': 'granted', 'deviceState': 'available'}).toString());
}
`);
      const output = execFileSync("dart", ["run", main], { encoding: "utf8" });
      assert.match(output, /DENIED=false/);
      assert.match(output, /GRANTED=true/);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
