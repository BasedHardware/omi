import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sources = join(root, "shell/Sources/OmiShell");

function hasSwiftc() {
  try { execFileSync("swiftc", ["--version"], { stdio: "ignore" }); return true; }
  catch { return false; }
}

const HARNESS = String.raw`
import CoreGraphics
import Foundation

let root = FileManager.default.temporaryDirectory.appendingPathComponent(
  "omi-screen-demo-seed-\(UUID().uuidString)", isDirectory: true)
try! FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
let store = ScreenLocalStore(root: root, omiBundleId: "me.omi.shell.core-tasks.prototype")

let known = ScreenDemoSeed.harborlineId
print("PLANT-UNKNOWN=\(try ScreenDemoSeed.plantIfKnown(store: store, frameRef: "chunks/demo/\(known).hevc"))")
do {
  _ = try store.decodeFrame(frameRef: "chunks/demo/\(known).hevc", maxLongEdge: nil)
  print("DECODE-DANGLING=leaked")
} catch {
  print("DECODE-DANGLING=unknown")
}

print("PLANT-KNOWN=\(try ScreenDemoSeed.plantIfKnown(store: store, frameRef: known))")
let (image, width, height) = try store.decodeFrame(frameRef: known, maxLongEdge: 80)
print("DECODE-KNOWN=\(width)x\(height)")
print("DECODE-PIXELS=\(image.width > 1 && image.height > 1)")
print("PLANT-IDEMPOTENT=\(try ScreenDemoSeed.plantIfKnown(store: store, frameRef: known))")
print("ROWS=\(store.framesStored)")

try? FileManager.default.removeItem(at: root)
print("SEED-EXIT=clean")
`;

test(
  "demo opaque refs plant synthetic HEVC; a dangling chunk path stays undecodable",
  { skip: hasSwiftc() ? false : "swiftc not available" },
  () => {
    // red-proof: restore demo frame_ref kind:"chunk" path chunks/demo/${id}.hevc.
    // PLANT-UNKNOWN stays false, DECODE-DANGLING=unknown, and Rewind shows
    // "Frame image is not available here."
    const scratch = mkdtempSync(join(tmpdir(), "omi-screen-demo-seed-"));
    try {
      const main = join(scratch, "main.swift");
      const binary = join(scratch, "harness");
      writeFileSync(main, HARNESS);
      execFileSync("swiftc", [
        "-o", binary,
        join(sources, "BridgeHttp.swift"),
        join(sources, "BridgeHttpContract.generated.swift"),
        join(sources, "ScreenPolicy.swift"),
        join(sources, "ScreenImaging.swift"),
        join(sources, "ScreenOCR.swift"),
        join(sources, "ScreenStore.swift"),
        join(sources, "ScreenIngest.swift"),
        join(sources, "ScreenDemoSeed.swift"),
        main,
        "-framework", "Foundation",
        "-framework", "AppKit",
        "-framework", "WebKit",
        "-framework", "AVFoundation",
        "-framework", "Vision",
        "-framework", "CoreMedia",
        "-framework", "CoreVideo",
        "-framework", "ImageIO",
        "-framework", "UniformTypeIdentifiers",
      ], { timeout: 120_000 });
      const output = execFileSync(binary, { encoding: "utf8", timeout: 60_000 });
      assert.match(output, /^PLANT-UNKNOWN=false$/m);
      assert.match(output, /^DECODE-DANGLING=unknown$/m);
      assert.match(output, /^PLANT-KNOWN=true$/m);
      assert.match(output, /^DECODE-KNOWN=/m);
      assert.match(output, /^DECODE-PIXELS=true$/m);
      assert.match(output, /^PLANT-IDEMPOTENT=true$/m);
      assert.match(output, /^SEED-EXIT=clean$/m);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
