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
import AppKit
import CoreGraphics
import Foundation
import Vision

final class StubProtocol: URLProtocol, @unchecked Sendable {
  static let lock = NSLock()
  nonisolated(unsafe) static var frames: [[String: Any]] = []
  nonisolated(unsafe) static var retired: [[String: Any]] = []
  nonisolated(unsafe) static var lastPath = ""
  nonisolated(unsafe) static var lastMethod = ""

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() {
    Self.lock.lock()
    Self.lastPath = request.url?.path ?? ""
    Self.lastMethod = request.httpMethod ?? ""
    let method = Self.lastMethod
    let path = Self.lastPath
    let body: Data
    if let direct = request.httpBody {
      body = direct
    } else if let stream = request.httpBodyStream {
      stream.open()
      var collected = Data()
      let buf = UnsafeMutablePointer<UInt8>.allocate(capacity: 4096)
      while stream.hasBytesAvailable {
        let n = stream.read(buf, maxLength: 4096)
        if n <= 0 { break }
        collected.append(buf, count: n)
      }
      buf.deallocate()
      stream.close()
      body = collected
    } else {
      body = Data()
    }
    var payload: [String: Any] = [:]
    var status = 200
    if method == "POST" && path.hasSuffix("/v1/screen/frames") {
      if let obj = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
        let incoming = obj["frames"] as? [[String: Any]]
      {
        Self.frames.append(contentsOf: incoming)
        status = 201
        payload = [
          "capture_session_id": obj["capture_session_id"] ?? "",
          "accepted": incoming.count,
          "duplicate": 0,
          "frames": incoming.map { ["id": $0["id"] ?? "", "inserted": true] },
        ]
      } else {
        status = 400
        payload = ["error": "invalid_frame"]
      }
    } else if method == "GET" && path.hasSuffix("/v1/screen/timeline") {
      let day = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?
        .queryItems?.first(where: { $0.name == "day" })?.value ?? ""
      payload = ["day": day, "frames": Self.frames]
    } else if method == "GET" && path.hasSuffix("/v1/screen/retired") {
      payload = ["retired": Self.retired]
    } else if method == "PUT" && path.hasSuffix("/v1/screen/retention") {
      payload = ["days": 7]
    } else {
      status = 404
      payload = ["error": "missing"]
    }
    Self.lock.unlock()
    let data = try! JSONSerialization.data(withJSONObject: payload)
    let response = HTTPURLResponse(
      url: request.url!, statusCode: status, httpVersion: "HTTP/1.1",
      headerFields: ["Content-Type": "application/json"])!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: data)
    client?.urlProtocolDidFinishLoading(self)
  }
  override func stopLoading() {}
}

func textImage(_ text: String) -> CGImage {
  let size = NSSize(width: 900, height: 180)
  let image = NSImage(size: size)
  image.lockFocus()
  NSColor.white.setFill()
  NSRect(origin: .zero, size: size).fill()
  let attrs: [NSAttributedString.Key: Any] = [
    .font: NSFont.systemFont(ofSize: 64, weight: .bold),
    .foregroundColor: NSColor.black,
  ]
  (text as NSString).draw(at: NSPoint(x: 24, y: 56), withAttributes: attrs)
  image.unlockFocus()
  var rect = NSRect(origin: .zero, size: size)
  return image.cgImage(forProposedRect: &rect, context: nil, hints: nil)!
}

struct InjectedSource: ScreenFrameSource {
  let frame: ScreenCapturedFrame
  func captureFocused(excluded: Set<String>) async throws -> ScreenCapturedFrame? {
    if excluded.contains(frame.appBundleId) { return nil }
    return frame
  }
}

struct QuietEnv: ScreenEnvironmentSource {
  func snapshot() -> ScreenEnvironmentSnapshot {
    ScreenEnvironmentSnapshot(
      onBattery: false, idleSeconds: 0, mediaPlaying: false, locked: false,
      screensaver: false, loginwindow: false, frontmostIsScreenshotApp: false,
      screenSharingActive: false, frontmostBundleId: "com.example.Harborline")
  }
}

let preflight = CGPreflightScreenCaptureAccess()
print("PREFLIGHT=\(preflight)")

let root = FileManager.default.temporaryDirectory.appendingPathComponent(
  "omi-screen-pipe-\(UUID().uuidString)", isDirectory: true)
try! FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
let store = ScreenLocalStore(root: root, omiBundleId: "me.omi.shell.core-tasks.prototype")

let cg = textImage("Harborline Cafe")
let hash = ScreenImaging.dhash64(cg)
print("DHASH=\(ScreenDHash.hex(hash))")
let ocr = ScreenOCR.recognize(cg)
print("OCR-BLOCKS=\(ocr?.blocks.count ?? 0)")
print("OCR-TEXT=\(ocr?.fullText.contains("Harborline") == true)")

var fence = ScreenFence.initial
let blockedGen = fence.beginWork()
_ = fence.bump()
do {
  _ = try store.appendFrame(
    image: cg, capturedAt: Date(), appBundleId: "com.example.Harborline",
    appName: "Harborline", windowTitle: "Menu", dhash: ScreenDHash.hex(hash),
    ocr: ocr, allowWrite: fence.canWrite(capturedGeneration: blockedGen))
  print("FENCE-WRITE=leaked")
} catch {
  print("FENCE-WRITE=blocked")
}
print("FENCE-ROWS-BEFORE=\(store.framesStored)")
fence.endWork()

let cfg = URLSessionConfiguration.ephemeral
cfg.protocolClasses = [StubProtocol.self]
let session = URLSession(configuration: cfg)
let custody = ShellCredentialCustody(token: "test-token")
let client = ScreenIngestClient(
  baseURL: URL(string: "http://127.0.0.1:4851")!,
  custody: custody,
  clientId: "screen-proof",
  session: session)

let source = InjectedSource(
  frame: ScreenCapturedFrame(
    image: cg, capturedAt: Date(), appBundleId: "com.example.Harborline",
    appName: "Harborline", windowTitle: "Menu"))
let engine = ScreenCaptureEngine(
  store: store, source: source, environment: QuietEnv(), ingest: client,
  deviceName: "Test Mac")

let lock = DispatchSemaphore(value: 0)
var injectedId = ""
Task {
  let row = await engine.processInjected(
    ScreenCapturedFrame(
      image: cg, capturedAt: Date(), appBundleId: "com.example.Harborline",
      appName: "Harborline", windowTitle: "Menu"))
  print("INJECTED-ROW=\(row != nil)")
  print("INJECTED-INDEXED=\(row.map { ScreenIndexMeaning.isIndexed(ocrCompleted: $0.ocrCompleted, blockCount: $0.blockCount) } ?? false)")
  injectedId = row?.id ?? ""
  let flush = ScreenIngestSync.flush(
    store: store, client: client, sessionId: "sess-injected", deviceName: "Test Mac",
    now: Date())
  print("INGEST=\(flush)")
  let timeline = try? client.getTimeline(day: "2026-08-15")
  let body = String(data: timeline?.body ?? Data(), encoding: .utf8) ?? ""
  print("TIMELINE-STATUS=\(timeline?.status ?? -1)")
  print("TIMELINE-HAS-HARBORLINE=\(body.contains("Harborline"))")
  print("TIMELINE-HAS-PIXEL=\(body.contains("pngBase64") || body.contains("chunk_bytes"))")
  print("TIMELINE-HAS-REF=\(body.contains("opaque"))")

  StubProtocol.lock.lock()
  StubProtocol.retired = [[
    "frame_id": injectedId,
    "frame_ref": ["kind": "opaque", "ref": row?.frameRef ?? ""],
    "retired_at": ScreenTime.wireTimestamp(Date()),
  ]]
  StubProtocol.lock.unlock()
  let gc = ScreenIngestSync.collectRetired(store: store, client: client)
  print("RETIRED-GC=\(gc)")

  let excl = await engine.exclusionsSet(
    ["com.example.Harborline"], omiBundleId: "me.omi.shell.core-tasks.prototype")
  print("EXCL-RETIRED-COUNT=\(excl.retiredFrameRefs.count)")
  _ = await engine.stop()
  store.finishWriter()
  print("STOP-STATE=\(await engine.currentStatus().state.rawValue)")
  lock.signal()
}
lock.wait()

let decision = ScreenHTTPPolicy.prepare(
  method: "POST", path: "/v1/screen/frames", body: Data("{}".utf8),
  baseURL: URL(string: "http://127.0.0.1:4851")!, token: "tok", clientId: "run")
if case let .dispatch(prepared) = decision {
  print("INGEST-AUTH=\(prepared.request.value(forHTTPHeaderField: "Authorization") ?? "missing")")
  print("INGEST-PIXEL-HEADER=\(prepared.request.value(forHTTPHeaderField: "content-type") ?? "")")
} else {
  print("INGEST-AUTH=failed")
}
print("THREADS=\(Thread.isMainThread)")
print("PIPE-EXIT=clean")
try? FileManager.default.removeItem(at: root)
`;

test(
  "injected frame runs dHash → OCR → chunk write → ingest → timeline without TCC",
  { skip: hasSwiftc() ? false : "swiftc not available" },
  () => {
    // red-proof: drop OCR blocks from the ingest body, or skip the fence
    // allowWrite check, and TIMELINE-HAS-HARBORLINE / FENCE-WRITE fail.
    const scratch = mkdtempSync(join(tmpdir(), "omi-screen-pipe-"));
    try {
      const main = join(scratch, "main.swift");
      const binary = join(scratch, "harness");
      writeFileSync(main, HARNESS);
      execFileSync("swiftc", [
        "-o", binary,
        join(sources, "Bridge.generated.swift"),
        join(sources, "BridgeHttp.swift"),
        join(sources, "BridgeHttpContract.generated.swift"),
        join(sources, "ScreenPolicy.swift"),
        join(sources, "ScreenImaging.swift"),
        join(sources, "ScreenOCR.swift"),
        join(sources, "ScreenStore.swift"),
        join(sources, "ScreenIngest.swift"),
        join(sources, "ScreenCapture.swift"),
        main,
        "-framework", "Foundation",
        "-framework", "AppKit",
        "-framework", "WebKit",
        "-framework", "AVFoundation",
        "-framework", "Vision",
        "-framework", "CoreMedia",
        "-framework", "CoreVideo",
        "-framework", "CoreImage",
        "-framework", "ScreenCaptureKit",
        "-framework", "IOKit",
        "-framework", "ImageIO",
        "-framework", "UniformTypeIdentifiers",
      ], { timeout: 120_000 });
      const output = execFileSync(binary, { encoding: "utf8", timeout: 120_000 });
      assert.match(output, /^PREFLIGHT=(true|false)$/m);
      assert.match(output, /^FENCE-WRITE=blocked$/m);
      assert.match(output, /^OCR-TEXT=true$/m);
      assert.match(output, /^INJECTED-ROW=true$/m);
      assert.match(output, /^INJECTED-INDEXED=true$/m);
      assert.match(output, /^INGEST=ok:/m);
      assert.match(output, /^TIMELINE-HAS-HARBORLINE=true$/m);
      assert.match(output, /^TIMELINE-HAS-PIXEL=false$/m);
      assert.match(output, /^TIMELINE-HAS-REF=true$/m);
      assert.match(output, /^PIPE-EXIT=clean$/m);
      assert.match(output, /^INGEST-AUTH=Bearer tok$/m);
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
