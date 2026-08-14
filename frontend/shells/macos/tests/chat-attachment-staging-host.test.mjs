import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
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
import Foundation

var failed = false
func check(_ name: String, _ value: Bool) {
  print(value ? "OK: \(name)" : "FAIL: \(name)")
  if !value { failed = true }
}

func eventually(_ condition: () -> Bool) -> Bool {
  let deadline = Date().addingTimeInterval(5)
  while !condition() && Date() < deadline {
    RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.01))
  }
  return condition()
}

final class FakeUploadTask: ChatAttachmentUploadCancelling, @unchecked Sendable {
  var cancelled = false
  func cancel() { cancelled = true }
}

try MainActor.assumeIsolated {
let scratch = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
  .appendingPathComponent("omi-attachment-harness-\(UUID().uuidString)", isDirectory: true)
try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)
defer { try? FileManager.default.removeItem(at: scratch) }
let large = scratch.appendingPathComponent("large fixture.pdf")
FileManager.default.createFile(atPath: large.path, contents: nil)
let largeHandle = try FileHandle(forWritingTo: large)
try largeHandle.truncate(atOffset: 50 * 1_024 * 1_024)
try largeHandle.close()

let multipart = try ChatMultipartBodyBuilder.build(sourceURL: large, temporaryDirectory: scratch)
defer { try? FileManager.default.removeItem(at: multipart.fileURL) }
check("large-file-copied-in-bounded-chunks", multipart.sourceSize == 50 * 1_024 * 1_024 && multipart.copiedBytes == multipart.sourceSize && multipart.maximumChunkBytes <= 64 * 1_024)
check("multipart-length-is-source-plus-bounded-envelope", multipart.contentLength > multipart.sourceSize && multipart.contentLength - multipart.sourceSize < 4_096)
let bodyHandle = try FileHandle(forReadingFrom: multipart.fileURL)
let prefix = try bodyHandle.read(upToCount: 1_024)!
try bodyHandle.seek(toOffset: UInt64(max(0, multipart.contentLength - 1_024)))
let suffix = try bodyHandle.readToEnd()!
try bodyHandle.close()
let prefixText = String(data: prefix, encoding: .utf8) ?? ""
let suffixText = String(data: suffix, encoding: .utf8) ?? ""
check("multipart-has-exactly-one-file-part", prefixText.components(separatedBy: "name=\"file\"").count - 1 == 1 && !suffixText.contains("name=\"file\""))
check("multipart-uses-generic-filename", prefixText.contains("filename=\"upload\"") && !prefixText.contains("large fixture.pdf"))
check("multipart-omits-part-content-type", !prefixText.contains("Content-Type:"))
check("multipart-closes-with-own-boundary", suffixText.hasSuffix("--\(multipart.boundary)--\r\n"))

let mutationScratch = scratch.appendingPathComponent("mutations", isDirectory: true)
try FileManager.default.createDirectory(at: mutationScratch, withIntermediateDirectories: true)

func mutationFixture(_ name: String) throws -> URL {
  let url = mutationScratch.appendingPathComponent(name)
  let bytes = Data(repeating: 0x41, count: ChatMultipartBodyBuilder.chunkBytes * 2 + 17)
  try bytes.write(to: url, options: .atomic)
  return url
}

func temporaryMultipartArtifacts() -> [URL] {
  (try? FileManager.default.contentsOfDirectory(
    at: mutationScratch, includingPropertiesForKeys: nil
  ).filter { $0.lastPathComponent.hasPrefix("omi-chat-multipart-") }) ?? []
}

func rejectsMutation(
  _ name: String,
  mutate: @escaping (URL) throws -> Void
) throws -> Bool {
  let source = try mutationFixture(name)
  var changed = false
  do {
    _ = try ChatMultipartBodyBuilder.build(
      sourceURL: source, temporaryDirectory: mutationScratch,
      afterChunk: { _ in
        guard !changed else { return }
        changed = true
        try! mutate(source)
      })
    return false
  } catch {
    return changed && temporaryMultipartArtifacts().isEmpty
  }
}

check("growth-is-rejected-and-cleaned", try rejectsMutation("grow.bin") { source in
  let handle = try FileHandle(forWritingTo: source)
  try handle.seekToEnd()
  try handle.write(contentsOf: Data([0x42]))
  try handle.close()
})
check("shrink-is-rejected-and-cleaned", try rejectsMutation("shrink.bin") { source in
  let handle = try FileHandle(forWritingTo: source)
  try handle.truncate(atOffset: UInt64(ChatMultipartBodyBuilder.chunkBytes))
  try handle.close()
})
check("replacement-is-rejected-and-cleaned", try rejectsMutation("replace.bin") { source in
  let moved = source.appendingPathExtension("original")
  try FileManager.default.moveItem(at: source, to: moved)
  let bytes = Data(repeating: 0x41, count: ChatMultipartBodyBuilder.chunkBytes * 2 + 17)
  try bytes.write(to: source)
})
check("same-size-mutation-is-rejected-and-cleaned", try rejectsMutation("same-size.bin") { source in
  let handle = try FileHandle(forWritingTo: source)
  try handle.seek(toOffset: UInt64(ChatMultipartBodyBuilder.chunkBytes + 1))
  try handle.write(contentsOf: Data([0x43]))
  try handle.close()
  try FileManager.default.setAttributes(
    [.modificationDate: Date(timeIntervalSince1970: 1)], ofItemAtPath: source.path)
})

let cancellationSource = try mutationFixture("cancel-copy.bin")
var cancellationRequested = false
var cancellationRejected = false
do {
  _ = try ChatMultipartBodyBuilder.build(
    sourceURL: cancellationSource, temporaryDirectory: mutationScratch,
    cancelled: { cancellationRequested },
    afterChunk: { _ in cancellationRequested = true })
} catch ChatMultipartBodyError.cancelled {
  cancellationRejected = true
}
check("copy-cancellation-is-rejected-and-cleaned", cancellationRejected && temporaryMultipartArtifacts().isEmpty)

let base = URL(string: "https://service.example.test/base")!
let custody = ShellCredentialCustody(token: "attachment-token")
var uploadCount = 0
var capturedRequest: URLRequest?
var capturedBodyURL: URL?
var replies: [[String: Any]] = []
let p7 = Data(#"{"attachment":{"id":"attachment-opaque-01","mimeType":"application/pdf","sizeBytes":52428800,"state":"staged","expiresAt":"2026-08-10T08:00:00.000Z"}}"#.utf8)
let successUploader: ChatAttachmentUploadStarter = { request, bodyURL, completion in
  uploadCount += 1
  capturedRequest = request
  capturedBodyURL = bodyURL
  let task = FakeUploadTask()
  let response = HTTPURLResponse(
    url: request.url!, statusCode: 201, httpVersion: "HTTP/1.1",
    headerFields: ["Content-Type": "application/json"])
  DispatchQueue.main.async { completion(p7, response, nil) }
  return task
}

let cancelPicker = ChatAttachmentStagingHandler(
  baseURL: base, custody: custody, runId: "run-attachment-proof",
  picker: { nil }, startUpload: successUploader)
cancelPicker.receive(body: ["t": "pick-and-stage", "id": "a-cancel"]) { value, _ in
  replies.append(value as! [String: Any])
}
check("picker-cancel-replies-cancelled", replies.last?["reason"] as? String == "cancelled")
check("picker-cancel-performs-no-upload", uploadCount == 0)

let directoryPicker = ChatAttachmentStagingHandler(
  baseURL: base, custody: custody, runId: "run-attachment-proof",
  picker: { scratch }, startUpload: successUploader)
directoryPicker.receive(body: ["t": "pick-and-stage", "id": "a-directory"]) { value, _ in
  replies.append(value as! [String: Any])
}
check("picker-refuses-non-regular-file", eventually {
  replies.last?["reason"] as? String == "shell-error" && uploadCount == 0
})

let handler = ChatAttachmentStagingHandler(
  baseURL: base, custody: custody, runId: "run-attachment-proof",
  picker: { large }, startUpload: successUploader)
handler.receive(body: [
  "t": "pick-and-stage", "id": "a-extra", "path": large.path,
]) { value, _ in replies.append(value as! [String: Any]) }
check("caller-metadata-is-refused", replies.last?["reason"] as? String == "shell-error" && uploadCount == 0)
handler.receive(body: ["t": "pick-and-stage", "id": "attachment-token/unsafe"]) { value, _ in
  replies.append(value as! [String: Any])
}
check("unsafe-caller-id-is-not-reflected", replies.last?["id"] as? String == "?" && !String(describing: replies.last!).contains("attachment-token"))

handler.receive(body: ["t": "pick-and-stage", "id": "a-success"]) { value, _ in
  replies.append(value as! [String: Any])
}
check("exact-p7-response-completes", eventually { replies.contains { $0["ok"] as? Bool == true } })
let success = replies.first { $0["ok"] as? Bool == true }!
let descriptor = success["attachment"] as! [String: Any]
check("reply-is-exact-name-less-descriptor", Set(descriptor.keys) == ["id", "mimeType", "sizeBytes", "state", "expiresAt"] && descriptor["displayName"] == nil)
check("reply-hides-file-origin-and-token", !String(describing: success).contains(large.path) && !String(describing: success).contains("service.example") && !String(describing: success).contains("attachment-token"))
check("upload-target-is-fixed", capturedRequest?.httpMethod == "POST" && capturedRequest?.url?.absoluteString == "https://service.example.test/v1/chat-attachments")
check("upload-auth-is-host-injected", capturedRequest?.value(forHTTPHeaderField: "Authorization") == "Bearer attachment-token")
check("upload-contract-is-host-injected", capturedRequest?.value(forHTTPHeaderField: "x-omi-contract-version") == "1.0.0")
check("upload-run-shell-is-host-injected", capturedRequest?.value(forHTTPHeaderField: "x-omi-client-id") == "run-attachment-proof::macos")
check("upload-content-type-has-one-boundary", capturedRequest?.value(forHTTPHeaderField: "Content-Type") == "multipart/form-data; boundary=\(multipartBoundary(capturedRequest))")
check("temporary-multipart-is-removed-after-success", capturedBodyURL.map { !FileManager.default.fileExists(atPath: $0.path) } == true)

func multipartBoundary(_ request: URLRequest?) -> String {
  let value = request?.value(forHTTPHeaderField: "Content-Type") ?? ""
  return value.components(separatedBy: "boundary=").last ?? ""
}

let exactResponse = HTTPURLResponse(
  url: base, statusCode: 201, httpVersion: nil,
  headerFields: ["Content-Type": "Application/JSON; Charset=UTF-8"])!
let wrongMimeResponse = HTTPURLResponse(
  url: base, statusCode: 201, httpVersion: nil,
  headerFields: ["Content-Type": "text/plain"])!
let missingMimeResponse = HTTPURLResponse(
  url: base, statusCode: 201, httpVersion: nil, headerFields: nil)!
let redirectResponse = HTTPURLResponse(url: base, statusCode: 302, httpVersion: nil, headerFields: nil)!
func parsed(_ object: Any, response: URLResponse = exactResponse, expectedSize: Int64 = 50 * 1_024 * 1_024) -> Bool {
  let data = try! JSONSerialization.data(withJSONObject: object)
  return ChatAttachmentStagingPolicy.parseResponse(data: data, response: response, expectedSize: expectedSize) != nil
}
let exactAttachment: [String: Any] = [
  "id": "attachment-opaque-01", "mimeType": "application/pdf",
  "sizeBytes": NSNumber(value: Int64(50 * 1_024 * 1_024)), "state": "staged",
  "expiresAt": "2026-08-10T08:00:00.000Z",
]
check("exact-p7-fixture-parses-without-name", parsed(["attachment": exactAttachment]))
var platformScan = exactAttachment
platformScan["scanState"] = "clean"
platformScan["scannerId"] = "dev-noop-scanner"
check("platform-scan-metadata-parses", parsed(["attachment": platformScan]))
var bogusScan = exactAttachment
bogusScan["scanState"] = "antivirus-clean"
check("reject-unknown-scan-state", !parsed(["attachment": bogusScan]))
for (name, mutation) in [
  ("unsafe-id", { var value = exactAttachment; value["id"] = "../secret"; return value }),
  ("extra-display-name", { var value = exactAttachment; value["displayName"] = "secret.pdf"; return value }),
  ("extra-path", { var value = exactAttachment; value["path"] = "/tmp/secret"; return value }),
  ("extra-token", { var value = exactAttachment; value["token"] = "secret"; return value }),
  ("missing-mime", { var value = exactAttachment; value.removeValue(forKey: "mimeType"); return value }),
  ("mismatched-size", { var value = exactAttachment; value["sizeBytes"] = 1; return value }),
] as [(String, () -> [String: Any])] {
  check("reject-\(name)", !parsed(["attachment": mutation()]))
}
check("reject-extra-envelope-field", !parsed(["attachment": exactAttachment, "name": "forbidden"]))
check("reject-redirect", !parsed(["attachment": exactAttachment], response: redirectResponse))
check("reject-wrong-response-mime", !parsed(["attachment": exactAttachment], response: wrongMimeResponse))
check("reject-missing-response-mime", !parsed(["attachment": exactAttachment], response: missingMimeResponse))
check("reject-malformed-json", ChatAttachmentStagingPolicy.parseResponse(data: Data("{".utf8), response: exactResponse, expectedSize: 50 * 1_024 * 1_024) == nil)

let redirectDelegate = ChatAttachmentUploadDelegate()
let redirectSession = URLSession(configuration: .ephemeral)
let redirectTask = redirectSession.dataTask(with: base)
var delegateAcceptedRedirect = true
redirectDelegate.urlSession(
  redirectSession, task: redirectTask,
  willPerformHTTPRedirection: redirectResponse,
  newRequest: URLRequest(url: URL(string: "https://redirect.example.test/elsewhere")!),
  completionHandler: { delegateAcceptedRedirect = $0 != nil })
check("actual-upload-delegate-refuses-redirect", !delegateAcceptedRedirect)
redirectSession.invalidateAndCancel()

let signedOutCustody = ShellCredentialCustody(token: "gone")
signedOutCustody.observe(method: "DELETE", path: "/v1/session/current", status: 204)
var signedOutUploads = 0
var signedOutPicked = 0
let signedOutHandler = ChatAttachmentStagingHandler(
  baseURL: base, custody: signedOutCustody, runId: "run-signed-out",
  picker: { signedOutPicked += 1; return large },
  startUpload: { _, _, _ in signedOutUploads += 1; return FakeUploadTask() })
signedOutHandler.receive(body: ["t": "pick-and-stage", "id": "a-signed-out"]) { value, _ in
  replies.append(value as! [String: Any])
}
check("signout-fails-upload-locally", replies.last?["reason"] as? String == "unavailable" && signedOutPicked == 0 && signedOutUploads == 0)

handler.teardown()
cancelPicker.teardown()
directoryPicker.teardown()
signedOutHandler.teardown()
exit(failed ? 1 : 0)
}
`;

test(
  "macOS attachment host streams one native file and returns only the exact safe P7 descriptor",
  { skip: hasSwiftc() ? false : "swiftc not available" },
  () => {
    const scratch = mkdtempSync(join(tmpdir(), "omi-chat-attachment-host-"));
    try {
      const main = join(scratch, "main.swift");
      const binary = join(scratch, "harness");
      writeFileSync(main, HARNESS);
      execFileSync("swiftc", [
        "-o", binary,
        join(sources, "BridgeHttpContract.generated.swift"),
        join(sources, "BridgeHttp.swift"),
        join(sources, "ChatAttachmentStaging.swift"),
        main,
        "-framework", "Foundation",
        "-framework", "AppKit",
        "-framework", "WebKit",
      ], { env: { ...process.env, CLANG_MODULE_CACHE_PATH: join(scratch, "module-cache") } });
      const result = spawnSync(binary, { encoding: "utf8", timeout: 30_000 });
      assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
      for (const line of result.stdout.trim().split("\n")) {
        assert.match(line, /^OK:/, result.stdout);
      }
      // red-proof: replacing the chunk loop with Data(contentsOf: sourceURL)
      // makes `large-file-copied-in-bounded-chunks` lose its production metric;
      // accepting any extra response field fails the named strict-shape rows.
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
