// Native side of the privileged HTTP bridge — the Swift counterpart of
// core-foundation `core/contracts/src/bridge/http.ts` (ADR-008 §3 / ADR-009 §3).
//
// This is deliberately NOT part of the codegen'd OmiShellBridge (bridge.json):
// that contract is the prototype's capture/settings bridge with its own
// string-envelope dispatcher. Privileged HTTP is defined by the CORE contract,
// so it gets its own reply-capable handler shaped by that file instead of
// inheriting an unrelated envelope.
//
// TOKEN CUSTODY: the base URL and the bearer token live here, in the shell, and
// are never sent to JS. The surface sends only a method, an origin-relative
// path, and a JSON body string. Responses carry status + body text only — no
// response headers, so `set-cookie` / `www-authenticate` cannot leak into the
// page. Dev-grade custody this wave (env vars); Keychain custody is owed.
//
// The security-bearing constants are NOT hand-copied: channel name, forbidden
// headers, and failure reasons all come from BridgeHttpContract.generated.swift,
// which `core/scripts/gen-bridge-swift.mjs` emits from the TS contract and whose
// `--check` mode fails the core DoD on drift. Reasons are a typed enum, so an
// invalid reason is a compile error rather than a runtime string typo.

import Foundation
import WebKit

struct BridgeHttpPreparedRequest {
  let id: String
  let method: String
  let url: URL
  let headers: [String: String]
  let body: String?

  /// The live URLSession path uses this factory, which in turn uses the same
  /// apply seam that conformance records. Keeping URLRequest construction in
  /// one place prevents the fixture from testing a policy-only shadow path.
  var request: URLRequest { BridgeHttpPolicy.makeRequest(self) }

  /// Kept as a descriptive compatibility property; tests must exercise
  /// `apply` rather than trust this self-report.
  var followsRedirects: Bool { BridgeHttpPolicy.followsRedirects }
  var bodyAfterHeaders: Bool { body != nil }
}

struct BridgeHttpNormalizedResponse {
  let id: String
  let status: Int
  let body: String?
  let retryAfterMs: Int?
  // Deliberately no response-header field: headers never cross into the page.
  let exposesResponseHeaders = false
}

struct BridgeHttpTransportFailure {
  let id: String
  let reason: BridgeHttpContract.FailureReason
  let detail: String
}

enum BridgeHttpPolicyDecision {
  case dispatch(BridgeHttpPreparedRequest)
  case failure(BridgeHttpContract.FailureReason, String)
}

/// Pure request/response policy used by both the live handler and the generated
/// host-conformance runner. Keeping this seam free of WebKit makes each row
/// hermetic while still exercising the exact host enforcement path.
enum BridgeHttpPolicy {
  static let followsRedirects = false

  /// Header carrying the per-run client identity (`OMI_RUN_CLIENT_ID`), so a
  /// launcher's served-read count on the backend is joinable to the exact run
  /// that made it, not just any client hitting the same endpoint. Confirmed
  /// NOT present in `BridgeHttpContract.forbiddenHeaders` (that generated set
  /// is authorization/cookie/proxy-authorization only) — so unlike those,
  /// this file must do its own case-insensitive strip of caller-supplied
  /// copies below, rather than relying on the generated contract to do it.
  static let clientIdHeader = "x-omi-client-id"

  /// Apply the exact request mutation sequence used by the live URLSession
  /// factory. The recorder in the generated conformance runner observes the
  /// calls; production passes URLRequest's setters.
  static func apply(
    _ prepared: BridgeHttpPreparedRequest,
    setHeader: (String, String) -> Void,
    setBody: (Data) -> Void
  ) {
    for (name, value) in prepared.headers {
      setHeader(name, value)
    }
    if let body = prepared.body {
      setBody(Data(body.utf8))
    }
  }

  static func makeRequest(_ prepared: BridgeHttpPreparedRequest) -> URLRequest {
    var request = URLRequest(url: prepared.url)
    request.httpMethod = prepared.method
    apply(
      prepared,
      setHeader: { name, value in request.setValue(value, forHTTPHeaderField: name) },
      setBody: { body in request.httpBody = body })
    return request
  }

  /// The live URLSession delegate calls this seam; a generated runner can
  /// invoke it without opening a socket and still prove redirects are refused.
  static func redirectedRequest(
    response: HTTPURLResponse,
    proposed: URLRequest
  ) -> URLRequest? {
    followsRedirects ? proposed : nil
  }

  /// Session custody is a live factory seam, not a runner-only declaration.
  /// The API client must never persist or accept cookies from the server.
  static func sessionConfiguration() -> URLSessionConfiguration {
    let cfg = URLSessionConfiguration.ephemeral
    cfg.timeoutIntervalForRequest = 10
    cfg.timeoutIntervalForResource = 15
    cfg.httpCookieStorage = nil
    cfg.httpShouldSetCookies = false
    cfg.httpCookieAcceptPolicy = .never
    return cfg
  }

  static func prepare(
    id: String,
    method: String,
    path: String,
    headers: [String: String],
    body: String?,
    baseURL: URL,
    token: String?,
    clientId: String? = nil
  ) -> BridgeHttpPolicyDecision {
    guard ["GET", "POST", "PATCH", "DELETE"].contains(method) else {
      return .failure(.shellError, "missing or unsupported method/path")
    }
    guard path.hasPrefix("/"), !path.hasPrefix("//"), !path.contains("://"),
      let url = URL(string: path, relativeTo: baseURL)?.absoluteURL,
      url.scheme == baseURL.scheme, url.host == baseURL.host, url.port == baseURL.port
    else {
      return .failure(.shellError, "path is not origin-relative")
    }
    guard let token, !token.isEmpty else {
      return .failure(.notAuthenticated, "shell holds no credential")
    }

    var outbound: [String: String] = [:]
    for (name, value) in headers
    where !BridgeHttpContract.forbiddenHeaders.contains(name.lowercased())
      && name.lowercased() != clientIdHeader {
      outbound[name] = value
    }
    if body != nil {
      outbound["content-type"] = "application/json"
    }
    // Set with the same precedence as `authorization` below: AFTER the page's
    // headers are copied in (and with any page-supplied copy of this same
    // header — any casing — already excluded by the loop above), so a page
    // can neither forge nor suppress the run's real client id.
    if let clientId, !clientId.isEmpty {
      outbound[clientIdHeader] = clientId
    }
    outbound["authorization"] = "Bearer \(token)"
    return .dispatch(BridgeHttpPreparedRequest(id: id, method: method, url: url, headers: outbound, body: body))
  }

  static func transportFailure(id: String, name: String) -> BridgeHttpTransportFailure {
    let reason: BridgeHttpContract.FailureReason
    switch name {
    case "offline": reason = .offline
    case "timeout": reason = .timeout
    case "cancelled": reason = .cancelled
    default: reason = .shellError
    }
    return BridgeHttpTransportFailure(id: id, reason: reason, detail: "fixture transport failure")
  }

  static func normalizeResponse(
    id: String, status: Int, body: String?, retryAfterSeconds: Int?
  ) -> BridgeHttpNormalizedResponse {
    BridgeHttpNormalizedResponse(
      id: id, status: status, body: body,
      retryAfterMs: retryAfterSeconds.map { $0 * 1000 })
  }

  /// The live reply factory deliberately carries no response headers. The
  /// generated runner calls this same factory to make header redaction
  /// executable rather than trusting the normalized value's shape.
  static func responsePayload(_ normalized: BridgeHttpNormalizedResponse) -> [String: Any] {
    var out: [String: Any] = [
      "id": normalized.id,
      "status": normalized.status,
      "body": normalized.body ?? NSNull(),
    ]
    if let retryAfterMs = normalized.retryAfterMs { out["retryAfterMs"] = retryAfterMs }
    return out
  }
}

private final class BridgeHttpURLSessionDelegate: NSObject, URLSessionTaskDelegate {
  func urlSession(
    _ session: URLSession,
    task: URLSessionTask,
    willPerformHTTPRedirection response: HTTPURLResponse,
    newRequest request: URLRequest,
    completionHandler: @escaping (URLRequest?) -> Void
  ) {
    // Redirects can move a shell-held credential to another origin. The live
    // delegate calls the policy seam, preserving Dart's followRedirects=false
    // behavior and making the redirect gate executable in conformance.
    completionHandler(BridgeHttpPolicy.redirectedRequest(response: response, proposed: request))
  }
}

@MainActor
final class BridgeHttpHandler: NSObject, WKScriptMessageHandlerWithReply {
  /// Generated from the TS contract — see BridgeHttpContract.generated.swift.
  static let channel = BridgeHttpContract.channel

  private let baseURL: URL
  private let token: String?
  /// Per-run client identity (`OMI_RUN_CLIENT_ID`), threaded in at init so
  /// `BridgeHttpPolicy.prepare` stays a pure function the generated
  /// host-conformance runner can call without reading the environment itself.
  private let clientId: String?
  private let sessionDelegate: BridgeHttpURLSessionDelegate
  private let session: URLSession

  /// Traffic counters for verification output. No URLs or tokens recorded.
  ///
  /// WHY THESE ARE SEPARATE: `servedCount` alone counts requests *dispatched*,
  /// which is incremented before the response arrives. A shell whose every
  /// request 401s therefore reports a healthy nonzero "served" count while the
  /// app renders an empty list — observed directly on this branch, and the
  /// exact false-green shape of the wave-9 bridge failure. An acceptance run
  /// must key on `succeededCount`, because that is the only counter that cannot
  /// be satisfied by a request that failed.
  private(set) var servedCount = 0
  /// Responses with a 2xx status.
  private(set) var succeededCount = 0
  /// Responses that arrived with a non-2xx status.
  private(set) var httpErrorCount = 0
  /// Requests that never produced a response at all.
  private(set) var transportFailureCount = 0
  /// Last non-2xx status seen, for a legible diagnosis. Never a URL or token.
  private(set) var lastErrorStatus: Int?

  /// One-line, secret-free traffic summary for acceptance output.
  var trafficSummary: String {
    var out =
      "dispatched=\(servedCount) succeeded=\(succeededCount) httpError=\(httpErrorCount) transportFailure=\(transportFailureCount)"
    if let lastErrorStatus { out += " lastErrorStatus=\(lastErrorStatus)" }
    return out
  }

  init(baseURL: URL, token: String?, clientId: String? = nil) {
    self.baseURL = baseURL
    self.token = (token?.isEmpty ?? true) ? nil : token
    self.clientId = (clientId?.isEmpty ?? true) ? nil : clientId
    let cfg = BridgeHttpPolicy.sessionConfiguration()
    let sessionDelegate = BridgeHttpURLSessionDelegate()
    self.sessionDelegate = sessionDelegate
    self.session = URLSession(configuration: cfg, delegate: sessionDelegate, delegateQueue: nil)
    super.init()
  }

  private func failure(
    _ id: String, _ reason: BridgeHttpContract.FailureReason, _ detail: String
  ) -> [String: Any] {
    ["ok": false, "failure": ["id": id, "reason": reason.rawValue, "detail": detail]]
  }

  func userContentController(
    _ controller: WKUserContentController,
    didReceive message: WKScriptMessage,
    replyHandler: @escaping (Any?, String?) -> Void
  ) {
    guard let body = message.body as? [String: Any],
      let id = body["id"] as? String
    else {
      // No correlation id: nothing sane to reply to.
      replyHandler(failure("?", .shellError, "malformed bridge http request"), nil)
      return
    }
    guard let method = body["method"] as? String,
      let path = body["path"] as? String
    else {
      replyHandler(failure(id, .shellError, "missing or unsupported method/path"), nil)
      return
    }
    let headers = body["headers"] as? [String: String] ?? [:]
    let bodyString = body["body"] as? String
    let decision = BridgeHttpPolicy.prepare(
      id: id, method: method, path: path, headers: headers, body: bodyString,
      baseURL: baseURL, token: token, clientId: clientId)
    guard case let .dispatch(prepared) = decision else {
      if case let .failure(reason, detail) = decision {
        replyHandler(failure(id, reason, detail), nil)
      }
      return
    }

    servedCount += 1
    let session = self.session
    Task {
      do {
        let (data, response) = try await session.data(for: prepared.request)
        guard let http = response as? HTTPURLResponse else {
          replyHandler(self.failure(id, .shellError, "non-HTTP response"), nil)
          return
        }
        if (200..<300).contains(http.statusCode) {
          self.succeededCount += 1
        } else {
          self.httpErrorCount += 1
          self.lastErrorStatus = http.statusCode
        }
        let body = data.isEmpty ? nil : String(data: data, encoding: .utf8)
        let retryAfter = http.value(forHTTPHeaderField: "retry-after").flatMap(Int.init)
        let normalized = BridgeHttpPolicy.normalizeResponse(
          id: id, status: http.statusCode, body: body, retryAfterSeconds: retryAfter)
        let out = BridgeHttpPolicy.responsePayload(normalized)
        replyHandler(["ok": true, "response": out], nil)
      } catch {
        self.transportFailureCount += 1
        let ns = error as NSError
        let reasonName: String
        switch ns.code {
        case NSURLErrorTimedOut: reasonName = "timeout"
        case NSURLErrorCancelled: reasonName = "cancelled"
        default: reasonName = "offline"
        }
        let transportFailure = BridgeHttpPolicy.transportFailure(id: id, name: reasonName)
        // Detail carries the URLError code, never the URL or the token.
        replyHandler(self.failure(id, transportFailure.reason, "URLError \(ns.code)"), nil)
      }
    }
  }
}
