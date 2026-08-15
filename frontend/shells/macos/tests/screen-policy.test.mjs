import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function hasSwiftc() {
  try { execFileSync("swiftc", ["--version"], { stdio: "ignore" }); return true; }
  catch { return false; }
}

const HARNESS = String.raw`
import Foundation

func check(_ name: String, _ cond: Bool) {
  print(cond ? "OK: \(name)" : "FAIL: \(name)")
  if !cond { exit(1) }
}

let now = Date(timeIntervalSince1970: 1_700_000_000)
func input(
  last: TimeInterval? = 0,
  anchor: TimeInterval? = 0,
  app: String = "com.apple.Safari",
  lastApp: String? = "com.apple.Safari",
  title: String = "Home",
  lastTitle: String? = "Home",
  battery: Bool = false,
  idle: TimeInterval = 0,
  media: Bool = false,
  locked: Bool = false,
  screensaver: Bool = false,
  login: Bool = false,
  screenshot: Bool = false,
  sharing: Bool = false,
  sharingUntil: Date? = nil,
  excluded: Bool = false,
  hamming: Int? = 20,
  heartbeat: TimeInterval = 3,
  tick: Int = 0
) -> ScreenCadenceInput {
  ScreenCadenceInput(
    now: now,
    lastCaptureAt: last.map { now.addingTimeInterval(-$0) },
    lastAnchorAt: anchor.map { now.addingTimeInterval(-$0) },
    lastAppBundleId: lastApp,
    lastWindowTitle: lastTitle,
    appBundleId: app,
    windowTitle: title,
    onBattery: battery,
    idleSeconds: idle,
    mediaPlaying: media,
    locked: locked,
    screensaver: screensaver,
    loginwindow: login,
    frontmostIsScreenshotApp: screenshot,
    screenSharingActive: sharing,
    sharingBackoffUntil: sharingUntil,
    excluded: excluded,
    dhashHammingFromLastStored: hamming,
    heartbeatSeconds: heartbeat,
    videoCallTick: tick)
}

switch ScreenCadencePolicy.decide(input(locked: true)) {
case .skip(let r): check("lock", r == "lock")
default: check("lock", false)
}
switch ScreenCadencePolicy.decide(input(screensaver: true)) {
case .skip(let r): check("screensaver", r == "screensaver")
default: check("screensaver", false)
}
switch ScreenCadencePolicy.decide(input(login: true)) {
case .skip(let r): check("loginwindow", r == "loginwindow")
default: check("loginwindow", false)
}
switch ScreenCadencePolicy.decide(input(screenshot: true)) {
case .skip(let r): check("screenshot-app", r == "screenshot-app")
default: check("screenshot-app", false)
}
switch ScreenCadencePolicy.decide(input(sharing: true)) {
case .skip(let r): check("screen-sharing", r == "screen-sharing")
default: check("screen-sharing", false)
}
switch ScreenCadencePolicy.decide(input(excluded: true)) {
case .skip(let r): check("excluded", r == "excluded")
default: check("excluded", false)
}
switch ScreenCadencePolicy.decide(input(idle: 90, media: false)) {
case .skip(let r): check("idle", r == "idle")
default: check("idle", false)
}
switch ScreenCadencePolicy.decide(input(last: 10, anchor: 10, idle: 90, media: true)) {
case .capture: check("idle-media-exempt", true)
case .skip(let r): check("idle-media-exempt", r != "idle")
}
switch ScreenCadencePolicy.decide(input(app: "com.apple.Mail", lastApp: "com.apple.Safari")) {
case .capture(let r): check("app-change", r == "app-or-title-change")
default: check("app-change", false)
}
switch ScreenCadencePolicy.decide(input(title: "B", lastTitle: "A")) {
case .capture(let r): check("title-change", r == "app-or-title-change")
default: check("title-change", false)
}
switch ScreenCadencePolicy.decide(input(last: 1, anchor: 1)) {
case .skip(let r): check("heartbeat-wait", r == "heartbeat")
default: check("heartbeat-wait", false)
}
switch ScreenCadencePolicy.decide(input(last: 4, anchor: 4)) {
case .capture(let r): check("heartbeat-fire", r == "heartbeat")
default: check("heartbeat-fire", false)
}
switch ScreenCadencePolicy.decide(input(last: 8, anchor: 8, battery: true)) {
case .skip(let r): check("battery-x3", r == "heartbeat")
default: check("battery-x3", false)
}
switch ScreenCadencePolicy.decide(input(last: 10, anchor: 10, battery: true)) {
case .capture: check("battery-x3-elapsed", true)
default: check("battery-x3-elapsed", false)
}
switch ScreenCadencePolicy.decide(input(last: 5, anchor: 5, app: "com.apple.Music", lastApp: "com.apple.Music")) {
case .skip(let r): check("music-override", r == "heartbeat")
default: check("music-override", false)
}
switch ScreenCadencePolicy.decide(input(last: 11, anchor: 11, app: "com.apple.Music", lastApp: "com.apple.Music")) {
case .capture: check("music-override-elapsed", true)
default: check("music-override-elapsed", false)
}
switch ScreenCadencePolicy.decide(input(last: 15, anchor: 15, app: "com.apple.iBooksX", lastApp: "com.apple.iBooksX")) {
case .skip(let r): check("books-override", r == "heartbeat")
default: check("books-override", false)
}
switch ScreenCadencePolicy.decide(input(last: 25, anchor: 25, app: "com.apple.TV", lastApp: "com.apple.TV")) {
case .skip(let r): check("tv-override", r == "heartbeat")
default: check("tv-override", false)
}
switch ScreenCadencePolicy.decide(input(last: 10, anchor: 10, app: "us.zoom.xos", lastApp: "us.zoom.xos", tick: 1)) {
case .skip(let r): check("zoom-1-in-5", r == "video-call-sample")
default: check("zoom-1-in-5", false)
}
switch ScreenCadencePolicy.decide(input(last: 10, anchor: 10, app: "us.zoom.xos", lastApp: "us.zoom.xos", tick: 5)) {
case .capture: check("zoom-1-in-5-keep", true)
default: check("zoom-1-in-5-keep", false)
}
switch ScreenCadencePolicy.decide(input(last: 10, anchor: 10, hamming: 3)) {
case .skip(let r): check("dhash-static", r == "dhash-static")
default: check("dhash-static", false)
}
switch ScreenCadencePolicy.decide(input(last: 4, anchor: 4, hamming: 3)) {
case .skip(let r): check("dhash-stretch", r == "heartbeat")
default: check("dhash-stretch", false)
}
switch ScreenCadencePolicy.decide(input(last: 40, anchor: 40, hamming: 0)) {
case .capture(let r): check("anchor-overrides-static", r == "anchor")
default: check("anchor-overrides-static", false)
}

var gray = [UInt8](repeating: 0, count: 72)
for i in 0..<72 { gray[i] = UInt8(i) }
let a = ScreenDHash.hash64(gray9x8: gray)
var gray2 = gray
gray2[0] = 255
let b = ScreenDHash.hash64(gray9x8: gray2)
check("dhash-stable", a == ScreenDHash.hash64(gray9x8: gray))
check("dhash-differs", a != b)
check("hamming-zero", ScreenDHash.hamming(a, a) == 0)
check("hamming-positive", ScreenDHash.hamming(a, b) > 0)
check("hamming-skip-ocr", ScreenDHash.hamming(a, a) <= 5)
check("hex-roundtrip", ScreenDHash.parseHex(ScreenDHash.hex(a)) == a)

check("ocr-first", ScreenCadencePolicy.shouldOCR(capturedCount: 0, hammingFromLastOCR: nil))
check("ocr-skip-1", !ScreenCadencePolicy.shouldOCR(capturedCount: 1, hammingFromLastOCR: nil))
check("ocr-skip-2", !ScreenCadencePolicy.shouldOCR(capturedCount: 2, hammingFromLastOCR: nil))
check("ocr-every-3", ScreenCadencePolicy.shouldOCR(capturedCount: 3, hammingFromLastOCR: nil))
check("ocr-hamming", !ScreenCadencePolicy.shouldOCR(capturedCount: 3, hammingFromLastOCR: 2))

check("perm-granted", ScreenPermissionPolicy.map(preflightGranted: true, hasRequested: false) == "granted")
check("perm-undetermined", ScreenPermissionPolicy.map(preflightGranted: false, hasRequested: false) == "undetermined")
check("perm-denied", ScreenPermissionPolicy.map(preflightGranted: false, hasRequested: true) == "denied")
check("perm-engine-failure-not-denied", ScreenPermissionPolicy.engineFailureNeverDenied(permission: "granted", engineFailed: true) == "granted")

check("ret-7", ScreenRetentionPolicy.normalize(7) == 7)
check("ret-0", ScreenRetentionPolicy.normalize(0) == 0)
check("ret-invalid", ScreenRetentionPolicy.normalize(9) == 0)
check("ret-negative", ScreenRetentionPolicy.normalize(-1) == 0)
check("ret-default", ScreenRetentionPolicy.defaultDays == 7)
check("ret-not-expired-unlimited", !ScreenRetentionPolicy.isExpired(capturedAt: now.addingTimeInterval(-86_400 * 400), now: now, days: 0))
check("ret-expired-7", ScreenRetentionPolicy.isExpired(capturedAt: now.addingTimeInterval(-86_400 * 8), now: now, days: 7))
check("sweep-due-nil", ScreenRetentionPolicy.shouldSweep(lastSweepAt: nil, now: now))
check("sweep-not-due", !ScreenRetentionPolicy.shouldSweep(lastSweepAt: now.addingTimeInterval(-60), now: now))

let merged = ScreenExclusionPolicy.mergeDefaults(
  stored: ["com.example.extra"],
  userRemoved: ["com.lastpass.LastPass"],
  omiBundleId: "me.omi.shell.core-tasks.prototype")
check("excl-keeps-extra", merged.contains("com.example.extra"))
check("excl-remerges-1p", merged.contains("com.1password.1password"))
check("excl-respects-removed", !merged.contains("com.lastpass.LastPass"))
check("excl-omi", merged.contains("me.omi.shell.core-tasks.prototype"))
let removed = ScreenExclusionPolicy.removedDefaults(
  previous: ["com.1password.1password", "com.example.extra"],
  next: ["com.example.extra"])
check("excl-removed-default", removed.contains("com.1password.1password"))
check("excl-not-removed-extra", !removed.contains("com.example.extra"))

var fence = ScreenFence.initial
let g0 = fence.beginWork()
check("fence-inflight", fence.inFlight == 1)
let g1 = fence.bump()
check("fence-bumped", g1 == g0 + 1)
check("fence-blocks-old", !fence.canWrite(capturedGeneration: g0))
check("fence-allows-new", fence.canWrite(capturedGeneration: g1))
fence.endWork()
check("fence-drained", fence.isDrained)

check("indexed-true", ScreenIndexMeaning.isIndexed(ocrCompleted: true, blockCount: 2))
check("indexed-false-skip", !ScreenIndexMeaning.isIndexed(ocrCompleted: false, blockCount: 0))
check("indexed-false-empty", !ScreenIndexMeaning.isIndexed(ocrCompleted: true, blockCount: 0))

var cursor = ScreenIngestCursor.empty
let pending = (0..<250).map { "id-\($0)" }
check("batch-cap", cursor.nextBatch(from: pending).count == 100)
check("can-attempt", cursor.canAttempt(now: now))
cursor = cursor.afterFailure(now: now)
check("backoff-set", cursor.backoffUntil != nil && !cursor.canAttempt(now: now))
check("backoff-elapsed", cursor.canAttempt(now: now.addingTimeInterval(5)))
cursor = cursor.afterSuccess(acceptedIds: ["id-0", "id-1"])
check("cursor-advanced", cursor.lastAcceptedId == "id-1")
check("cursor-reset-fail", cursor.failureCount == 0)

let iso = ScreenTime.wireTimestamp(now)
check("iso-z", iso.hasSuffix("Z") && iso.contains("."))
check("iso-parse", ScreenTime.parse(iso) != nil)

print("POLICY-DONE")
`;

test(
  "screen cadence, dHash, Hamming, fence, ingest cursor, permission, retention are pure and testable",
  { skip: hasSwiftc() ? false : "swiftc not available" },
  () => {
    // red-proof: flip the idle gate, the Hamming threshold, or retention fail-safe
    // to 7 (a deleting window) and a named OK line below fails.
    const scratch = mkdtempSync(join(tmpdir(), "omi-screen-policy-"));
    try {
      const main = join(scratch, "main.swift");
      const binary = join(scratch, "harness");
      writeFileSync(main, HARNESS);
      execFileSync("swiftc", [
        "-o", binary,
        join(root, "shell/Sources/OmiShell/ScreenPolicy.swift"),
        main,
        "-framework", "Foundation",
      ]);
      const output = execFileSync(binary, { encoding: "utf8" });
      const fails = output.split("\n").filter((l) => l.startsWith("FAIL:"));
      assert.equal(fails.length, 0, output);
      assert.match(output, /^POLICY-DONE$/m);
      assert.match(output, /^OK: lock$/m);
      assert.match(output, /^OK: dhash-static$/m);
      assert.match(output, /^OK: anchor-overrides-static$/m);
      assert.match(output, /^OK: ret-invalid$/m);
      assert.match(output, /^OK: perm-engine-failure-not-denied$/m);
      assert.match(output, /^OK: fence-blocks-old$/m);
      assert.match(output, /^OK: indexed-false-skip$/m);
      assert.match(output, /^OK: batch-cap$/m);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
