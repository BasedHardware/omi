import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const appDelegate = await readFile(resolve(ROOT, "app/ios/Runner/AppDelegate.swift"), "utf8");
const dartHost = await readFile(resolve(ROOT, "app/lib/listen_socket_host.dart"), "utf8");

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
  assert.match(dartHost, /permission.*unavailable/s);
  assert.doesNotMatch(dartHost, /device(?:Id|UUID|Uid)\b|serial(?:number)?\b/i);
});
