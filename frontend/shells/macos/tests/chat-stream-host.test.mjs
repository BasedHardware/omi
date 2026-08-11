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
import JavaScriptCore

var failed = false
func check(_ name: String, _ value: Bool) {
  print(value ? "OK: \(name)" : "FAIL: \(name)")
  if !value { failed = true }
}

func encodedPath(_ url: URL?) -> String {
  guard let url else { return "" }
  return URLComponents(url: url, resolvingAgainstBaseURL: false)?.percentEncodedPath ?? ""
}

final class StubProtocol: URLProtocol, @unchecked Sendable {
  static let lock = NSLock()
  nonisolated(unsafe) static var bodies: [String: Data] = [:]
  nonisolated(unsafe) static var statuses: [String: Int] = [:]
  nonisolated(unsafe) static var requests: [URLRequest] = []
  nonisolated(unsafe) static var stopCount = 0

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() {
    Self.lock.lock()
    Self.requests.append(request)
    let path = encodedPath(request.url)
    let body = Self.bodies[path] ?? Data()
    let status = Self.statuses[path] ?? 200
    Self.lock.unlock()
    let response = HTTPURLResponse(
      url: request.url!, statusCode: status, httpVersion: "HTTP/1.1",
      headerFields: ["Content-Type": status == 200 ? "text/event-stream" : "application/json"]
    )!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    if path == "/v1/chat-generations/manual-credit/events" { return }
    for byte in body {
      client?.urlProtocol(self, didLoad: Data([byte]))
      if path == "/v1/chat-generations/cancel/events" { return }
    }
    client?.urlProtocolDidFinishLoading(self)
  }
  override func stopLoading() {
    Self.lock.lock()
    Self.stopCount += 1
    Self.lock.unlock()
  }
}

func eventually(_ condition: () -> Bool) -> Bool {
  let deadline = Date().addingTimeInterval(3)
  while Date() < deadline {
    if condition() { return true }
    RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.01))
  }
  return false
}

func framesFor(_ id: String, in frames: [[String: Any]]) -> [[String: Any]] {
  frames.filter { $0["id"] as? String == id }
}

let utf8BoundaryFixture = "data: hé🙂\n\n"
let utf8BoundaryBytes = Data(utf8BoundaryFixture.utf8)
var everyUTF8BoundaryPassed = true
for boundary in 0...utf8BoundaryBytes.count {
  var decoder = IncrementalUTF8Decoder()
  do {
    let prefix = utf8BoundaryBytes.prefix(boundary)
    let suffix = utf8BoundaryBytes.suffix(from: boundary)
    let decoded = (try decoder.push(Data(prefix)) ?? "")
      + (try decoder.push(Data(suffix)) ?? "")
    _ = try decoder.finish()
    if decoded != utf8BoundaryFixture { everyUTF8BoundaryPassed = false }
  } catch {
    everyUTF8BoundaryPassed = false
  }
}
check("stateful-utf8-survives-every-byte-boundary", everyUTF8BoundaryPassed)

let configuration = ChatStreamPolicy.sessionConfiguration()
configuration.protocolClasses = [StubProtocol.self]
let base = URL(string: "https://service.example.test/base")!
let custody = ShellCredentialCustody(token: "secret-token")
let context = JSContext()!
var frames: [[String: Any]] = []
let recorder: @convention(block) (String) -> Void = { raw in
  if let data = raw.data(using: .utf8),
    let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
  { frames.append(value) }
}
context.setObject(recorder, forKeyedSubscript: "__record" as NSString)
context.evaluateScript("globalThis.__omiStreamFrame = function(raw) { __record(raw); }")
let host = ChatStreamHandler(
  baseURL: base, custody: custody, runId: "run-stream-proof",
  configuration: configuration,
  evaluateJavaScript: { script in context.evaluateScript(script) })

let generation = "generation/reconnect"
let encoded = "generation%2Freconnect"
let path = "/v1/chat-generations/\(encoded)/events"
let sse = """
event: snapshot\nid: event-snapshot\ndata: {"kind":"snapshot","text":""}\n\nevent: delta\nid: event-delta-1\ndata: {"kind":"delta","text":"hé🙂"}\n\nevent: delta\nid: event-delta-2\ndata: {"kind":"delta","text":" live"}\n\n
"""
StubProtocol.bodies[path] = Data(sse.utf8)
let open = #"{"t":"open","id":"s-boundary","channel":"chat-generation-events","params":"{\"generationId\":\"generation/reconnect\",\"lastEventId\":\"event-delta-0\"}","credit":1000}"#
host.receive(raw: open)
check("byte-boundary-stream-terminates", eventually {
  framesFor("s-boundary", in: frames).contains { $0["t"] as? String == "end" }
})
let boundaryFrames = framesFor("s-boundary", in: frames)
let boundaryPayload = boundaryFrames.compactMap { $0["payload"] as? String }.joined()
check("split-multibyte-scalar-round-trips", boundaryPayload == sse)
check("two-deltas-reach-js-sink-before-terminal", boundaryPayload.components(separatedBy: "event: delta").count - 1 == 2 && boundaryFrames.last?["t"] as? String == "end")
check("one-terminal-end", boundaryFrames.filter { $0["t"] as? String == "end" }.count == 1)
check("no-terminal-error", !boundaryFrames.contains { $0["t"] as? String == "error" })
check("frames-hide-origin-and-token", !String(describing: boundaryFrames).contains("service.example") && !String(describing: boundaryFrames).contains("secret-token"))

StubProtocol.lock.lock()
let boundaryRequest = StubProtocol.requests.first { encodedPath($0.url) == path }
StubProtocol.lock.unlock()
check("fixed-generation-get", boundaryRequest?.httpMethod == "GET" && boundaryRequest?.url?.absoluteString == "https://service.example.test/v1/chat-generations/generation%2Freconnect/events")
check("last-event-id-exact", boundaryRequest?.value(forHTTPHeaderField: "Last-Event-ID") == "event-delta-0")
check("host-injected-auth", boundaryRequest?.value(forHTTPHeaderField: "Authorization") == "Bearer secret-token")
check("host-injected-contract", boundaryRequest?.value(forHTTPHeaderField: "x-omi-contract-version") == "1.0.0")
check("host-injected-run-shell", boundaryRequest?.value(forHTTPHeaderField: "x-omi-client-id") == "run-stream-proof::macos")

let agentPath = "/v1/chat-generations/generation-agent/agent-events"
StubProtocol.bodies[agentPath] = Data(#"event: status\nid: run-event-1\ndata: {"runId":"generation-agent"}\n\n"#.utf8)
host.receive(raw: #"{"t":"open","id":"s-agent","channel":"chat-agent-run-events","params":"{\"generationId\":\"generation-agent\",\"lastEventId\":\"run-before\"}","credit":2}"#)
check("agent-run-stream-terminates", eventually {
  framesFor("s-agent", in: frames).last?["t"] as? String == "end"
})
StubProtocol.lock.lock()
let agentRequest = StubProtocol.requests.first { encodedPath($0.url) == agentPath }
StubProtocol.lock.unlock()
check("fixed-agent-run-get", agentRequest?.httpMethod == "GET" && agentRequest?.url?.path == agentPath)
check("agent-last-event-id-exact", agentRequest?.value(forHTTPHeaderField: "Last-Event-ID") == "run-before")
check("agent-frames-keep-channel", framesFor("s-agent", in: frames).allSatisfy { $0["channel"] as? String == "chat-agent-run-events" })
check("agent-frames-hide-custody", !String(describing: framesFor("s-agent", in: frames)).contains("secret-token"))

let malformedRequestCount: Int
StubProtocol.lock.lock(); malformedRequestCount = StubProtocol.requests.count; StubProtocol.lock.unlock()
let terminalMalformedFrames = [
  ("s-extra-open", "chat-generation-events", #"{"t":"open","id":"s-extra-open","channel":"chat-generation-events","params":"{\"generationId\":\"unused\"}","credit":1,"extra":true}"#),
  ("s-invalid-params", "chat-generation-events", #"{"t":"open","id":"s-invalid-params","channel":"chat-generation-events","params":"{\"generationId\":7}","credit":1}"#),
  ("s-invalid-agent-params", "chat-agent-run-events", #"{"t":"open","id":"s-invalid-agent-params","channel":"chat-agent-run-events","params":"{\"generationId\":7}","credit":1}"#),
  ("s-wrong-channel", "chat-generation-events", #"{"t":"open","id":"s-wrong-channel","channel":"other-events","params":"{\"generationId\":\"unused\"}","credit":1}"#),
  ("s-unknown-type", "chat-generation-events", #"{"t":"unknown","id":"s-unknown-type","channel":"chat-generation-events"}"#),
]
for (id, expectedChannel, raw) in terminalMalformedFrames {
  host.receive(raw: raw)
  check("malformed-\(id)-is-terminal", eventually {
    let routed = framesFor(id, in: frames)
    return routed.count == 1
      && routed[0]["t"] as? String == "error"
      && routed[0]["channel"] as? String == expectedChannel
      && routed[0]["failure"] as? String == "invalid-frame"
  })
}
host.receive(raw: #"{"t":"open","channel":"chat-generation-events","params":"{}","credit":1}"#)
check("no-id-garbage-remains-unrouteable", frames.filter { $0["failure"] as? String == "invalid-frame" }.count == terminalMalformedFrames.count)
StubProtocol.lock.lock(); let malformedRequestCountAfter = StubProtocol.requests.count; StubProtocol.lock.unlock()
check("malformed-routable-frames-do-not-dispatch", malformedRequestCountAfter == malformedRequestCount)

let creditPath = "/v1/chat-generations/manual-credit/events"
host.receive(raw: #"{"t":"open","id":"s-credit","channel":"chat-generation-events","params":"{\"generationId\":\"manual-credit\"}","credit":1}"#)
check("credit-stream-response-started", eventually {
  StubProtocol.lock.lock(); defer { StubProtocol.lock.unlock() }
  return StubProtocol.requests.contains { encodedPath($0.url) == creditPath }
})
check("credit-enqueue-a", eventually { host.enqueuePayloadForConformance(id: "s-credit", payload: "a") })
for payload in ["b", "c", "d", "e", "f"] {
  check("credit-enqueue-\(payload)", host.enqueuePayloadForConformance(id: "s-credit", payload: payload))
}
check("credit-first-frame", framesFor("s-credit", in: frames).filter { $0["t"] as? String == "data" }.count == 1)
_ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.05))
check("credit-zero-pauses-delivery", framesFor("s-credit", in: frames).filter { $0["t"] as? String == "data" }.count == 1)
host.receive(raw: #"{"t":"grant","id":"s-credit","channel":"chat-generation-events","credit":2}"#)
check("grant-resumes-exact-count", framesFor("s-credit", in: frames).filter { $0["t"] as? String == "data" }.count == 3)
host.receive(raw: #"{"t":"grant","id":"s-credit","channel":"chat-generation-events","credit":3}"#)
check("second-grant-resumes-exact-count", framesFor("s-credit", in: frames).filter { $0["t"] as? String == "data" }.count == 6)
check("credit-completion-accepted", host.finishForConformance(id: "s-credit"))
check("remaining-credit-reaches-end", framesFor("s-credit", in: frames).last?["t"] as? String == "end")
check("credit-delivery-preserves-all-bytes", framesFor("s-credit", in: frames).compactMap { $0["payload"] as? String }.joined() == "abcdef")

let isolationPath = "/v1/chat-generations/isolation/events"
StubProtocol.bodies[isolationPath] = Data("xyz".utf8)
host.receive(raw: #"{"t":"open","id":"s-one","channel":"chat-generation-events","params":"{\"generationId\":\"isolation\"}","credit":1}"#)
host.receive(raw: #"{"t":"open","id":"s-two","channel":"chat-generation-events","params":"{\"generationId\":\"isolation\"}","credit":1}"#)
check("two-sessions-start", eventually {
  framesFor("s-one", in: frames).filter { $0["t"] as? String == "data" }.count == 1
    && framesFor("s-two", in: frames).filter { $0["t"] as? String == "data" }.count == 1
})
StubProtocol.lock.lock(); let requestsBeforeInvalid = StubProtocol.requests.count; StubProtocol.lock.unlock()
host.receive(raw: #"{"t":"grant","id":"s-one","channel":"chat-generation-events","credit":"99"}"#)
StubProtocol.lock.lock(); let requestsAfterInvalid = StubProtocol.requests.count; StubProtocol.lock.unlock()
check("malformed-active-frame-does-not-dispatch", requestsAfterInvalid == requestsBeforeInvalid)
check("malformed-active-frame-retires-only-matching-session", eventually {
  let own = framesFor("s-one", in: frames)
  return own.filter { $0["t"] as? String == "data" }.count == 1
    && own.last?["t"] as? String == "error"
    && own.last?["failure"] as? String == "invalid-frame"
    && !framesFor("s-two", in: frames).contains { $0["t"] as? String == "error" }
})
host.receive(raw: #"{"t":"grant","id":"s-two","channel":"chat-generation-events","credit":2}"#)
check("other-session-resumes-independently", eventually { framesFor("s-two", in: frames).last?["t"] as? String == "end" })

let cancelPath = "/v1/chat-generations/cancel/events"
StubProtocol.bodies[cancelPath] = Data("cancel-me".utf8)
host.receive(raw: #"{"t":"open","id":"s-cancel","channel":"chat-generation-events","params":"{\"generationId\":\"cancel\"}","credit":1}"#)
check("cancel-stream-started", eventually { framesFor("s-cancel", in: frames).count == 1 })
StubProtocol.lock.lock(); let stopsBefore = StubProtocol.stopCount; StubProtocol.lock.unlock()
host.receive(raw: #"{"t":"cancel","id":"s-cancel","channel":"chat-generation-events","reason":"consumer-return"}"#)
check("cancel-closes-underlying-task", eventually {
  StubProtocol.lock.lock(); defer { StubProtocol.lock.unlock() }
  return StubProtocol.stopCount > stopsBefore
})
StubProtocol.lock.lock()
let cancelMethods = StubProtocol.requests.filter { $0.url?.path == cancelPath }.map { $0.httpMethod ?? "" }
StubProtocol.lock.unlock()
check("disconnect-never-dispatches-generation-delete", cancelMethods == ["GET"])

let leasedCustody = ShellCredentialCustody(token: "leased-token")
let leasedHost = ChatStreamHandler(
  baseURL: base, custody: leasedCustody, runId: "run-lease",
  configuration: configuration,
  evaluateJavaScript: { script in context.evaluateScript(script) })
let leasePath = "/v1/chat-generations/lease/events"
StubProtocol.bodies[leasePath] = Data("leased".utf8)
leasedHost.receive(raw: #"{"t":"open","id":"s-lease","channel":"chat-generation-events","params":"{\"generationId\":\"lease\"}","credit":1}"#)
check("leased-stream-starts", eventually { framesFor("s-lease", in: frames).filter { $0["t"] as? String == "data" }.count == 1 })
leasedCustody.observe(method: "DELETE", path: "/v1/session/current", status: 204)
leasedHost.receive(raw: #"{"t":"grant","id":"s-lease","channel":"chat-generation-events","credit":5}"#)
check("already-leased-stream-survives-signout", eventually { framesFor("s-lease", in: frames).last?["t"] as? String == "end" })
StubProtocol.lock.lock(); let beforeSignedOutOpen = StubProtocol.requests.count; StubProtocol.lock.unlock()
leasedHost.receive(raw: #"{"t":"open","id":"s-after-signout","channel":"chat-generation-events","params":"{\"generationId\":\"lease\"}","credit":1}"#)
check("signed-out-open-errors-locally", framesFor("s-after-signout", in: frames).last?["failure"] as? String == "not-authenticated")
StubProtocol.lock.lock(); let afterSignedOutOpen = StubProtocol.requests.count; StubProtocol.lock.unlock()
check("signed-out-open-does-not-dispatch", afterSignedOutOpen == beforeSignedOutOpen)

let failurePath = "/v1/chat-generations/failure/events"
StubProtocol.statuses[failurePath] = 503
StubProtocol.bodies[failurePath] = Data("secret server detail".utf8)
host.receive(raw: #"{"t":"open","id":"s-failure","channel":"chat-generation-events","params":"{\"generationId\":\"failure\"}","credit":4}"#)
check("http-failure-is-one-bounded-error", eventually {
  let failureFrames = framesFor("s-failure", in: frames)
  return failureFrames.count == 1 && failureFrames[0]["t"] as? String == "error"
    && failureFrames[0]["failure"] as? String == "request-refused"
})

host.cancelAll()
leasedHost.cancelAll()
exit(failed ? 1 : 0)
`;

test(
  "macOS Chat stream host enforces native custody, byte-safe SSE delivery, credit, and isolation",
  { skip: hasSwiftc() ? false : "swiftc not available" },
  () => {
    const scratch = mkdtempSync(join(tmpdir(), "omi-chat-stream-host-"));
    try {
      const main = join(scratch, "main.swift");
      const binary = join(scratch, "harness");
      writeFileSync(main, HARNESS);
      execFileSync("swiftc", [
        "-o", binary,
        join(sources, "BridgeHttpContract.generated.swift"),
        join(sources, "BridgeHttp.swift"),
        join(sources, "ChatStream.swift"),
        main,
        "-framework", "Foundation",
        "-framework", "WebKit",
        "-framework", "JavaScriptCore",
      ], { env: { ...process.env, CLANG_MODULE_CACHE_PATH: join(scratch, "module-cache") } });
      const result = spawnSync(binary, { encoding: "utf8", timeout: 20_000 });
      assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
      for (const line of result.stdout.trim().split("\n")) {
        assert.match(line, /^OK:/, result.stdout);
      }
      // red-proof: replacing IncrementalUTF8Decoder.push with
      // `String(decoding: data, as: UTF8.self)` corrupts the split scalar and
      // fails `split-multibyte-scalar-round-trips`; removing task suspension
      // fails `credit-zero-pauses-delivery`.
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  },
);
