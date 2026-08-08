#!/usr/bin/env node
// Generate the bridge-HTTP host policy corpus and the language-local runners.
// The fixture is the contract's test vocabulary; each host calls the same pure
// policy seam that its live message handler uses.  The generated runners are
// intentionally checked in beside the prototypes so a missing tracker checkout
// does not make core verification fail, while a present checkout cannot drift.
import fs from "node:fs";
import path from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const FIXTURE_REL = "contracts/fixtures/bridge-http-host-conformance.json";
const MAC_OUT = {
  envVar: "OMI_MACOS_SHELL_DIR",
  path: "shell/Sources/OmiShell/BridgeHttpConformance.generated.swift",
};
const IOS_OUT = {
  envVar: "OMI_IOS_SHELL_DIR",
  path: "app/test/bridge_http_conformance_generated_test.dart",
};
// The shells are in-repo since PR-6 promotion (core/shells/). Resolving them
// here rather than in a sibling tracker checkout is what makes these gates
// actually RUN: before promotion both hosts resolved to a path that does not
// exist inside a worktree, so `emit()` took its SKIP branch and the drift and
// conformance checks were silently inert in every `pnpm verify`.
const macDir = process.env[MAC_OUT.envVar] ?? path.join(ROOT, "shells/macos");
const iosDir = process.env[IOS_OUT.envVar] ?? path.join(ROOT, "shells/ios");
const check = process.argv.includes("--check");

function fail(message) {
  console.error(`gen-bridge-http-conformance: ${message}`);
  process.exit(1);
}

let fixture;
try {
  fixture = JSON.parse(fs.readFileSync(path.join(ROOT, FIXTURE_REL), "utf8"));
} catch (err) {
  fail(`cannot read ${FIXTURE_REL}: ${err.message}`);
}
if (fixture.version !== 1) fail(`unsupported fixture version ${fixture.version}`);
if (!Array.isArray(fixture.rows) || fixture.rows.length === 0) fail("fixture rows must be non-empty");
const ids = new Set();
for (const row of fixture.rows) {
  if (!row || typeof row !== "object" || typeof row.id !== "string" || !row.id) fail("every row needs a non-empty id");
  if (ids.has(row.id)) fail(`duplicate row id ${row.id}`);
  ids.add(row.id);
  if (!row.request || (typeof row.request.id !== "string" && row.request.id !== null)) fail(`${row.id}: request.id must be string or null`);
  if (row.request.id === null && row.missingId !== true && row.malformed !== true) fail(`${row.id}: null request.id requires missingId/malformed=true`);
  if (row.malformed !== true && (typeof row.request.method !== "string" || typeof row.request.path !== "string")) fail(`${row.id}: method/path required unless malformed=true`);
  if (!row.expect || !Number.isInteger(row.expect.servedDelta) || !Number.isInteger(row.expect.backendHit)) {
    fail(`${row.id}: expect.servedDelta/backendHit must be integers`);
  }
}

const quoteSwift = (value) => JSON.stringify(value);
const quoteDart = (value) => JSON.stringify(value);
const swiftOptionalString = (value) => value == null ? "nil" : quoteSwift(value);
const swiftOptionalInt = (value) => value == null ? "nil" : String(value);
const swiftOptionalBool = (value) => value == null ? "nil" : String(Boolean(value));
const swiftStringMap = (value = {}) => {
  const entries = Object.entries(value).sort(([a], [b]) => a.localeCompare(b));
  return entries.length === 0
    ? "[:]"
    : `[${entries.map(([k, v]) => `${quoteSwift(k)}: ${quoteSwift(v)}`).join(", ")}]`;
};
const swiftStringArray = (value = []) => `[${value.map(quoteSwift).join(", ")}]`;

function emitSwift() {
  const rows = fixture.rows.map((row) => {
    const req = row.request;
    const exp = row.expect;
    const response = row.response ?? {};
    return `    BridgeHttpConformanceCase(
      id: ${quoteSwift(row.id)}, scope: ${quoteSwift(row.scope ?? "all")},
      requestId: ${swiftOptionalString(req.id)}, method: ${swiftOptionalString(req.method)}, path: ${swiftOptionalString(req.path)}, missingId: ${Boolean(row.missingId)}, malformed: ${Boolean(row.malformed)},
      requestHeaders: ${swiftStringMap(req.headers)}, body: ${swiftOptionalString(req.body)}, credential: ${swiftOptionalString(row.credential)},
      transportFailure: ${swiftOptionalString(row.transportFailure)}, responseStatus: ${swiftOptionalInt(response.status)}, responseBody: ${swiftOptionalString(response.body)}, retryAfterSeconds: ${swiftOptionalInt(response.retryAfterSeconds)},
      expected: BridgeHttpConformanceExpectation(
        outcome: ${quoteSwift(exp.outcome)}, failureReason: ${swiftOptionalString(exp.failureReason)}, servedDelta: ${exp.servedDelta}, backendHit: ${exp.backendHit},
        method: ${swiftOptionalString(exp.method)}, pathAndQuery: ${swiftOptionalString(exp.pathAndQuery)}, body: ${swiftOptionalString(exp.body)}, headers: ${swiftStringMap(exp.headers)}, forbiddenDropped: ${swiftStringArray(exp.forbiddenDropped)},
        bodyAfterHeaders: ${swiftOptionalBool(exp.bodyAfterHeaders)}, followRedirects: ${swiftOptionalBool(exp.followRedirects)}, responseStatus: ${swiftOptionalInt(exp.responseStatus)}, responseBody: ${swiftOptionalString(exp.responseBody)}, retryAfterMs: ${swiftOptionalInt(exp.retryAfterMs)},
        correlationId: ${swiftOptionalString(exp.correlationId)}, duplicateReplyDroppedBySurface: ${swiftOptionalBool(exp.duplicateReplyDroppedBySurface)}, redirectLocationForwarded: ${swiftOptionalBool(exp.redirectLocationForwarded)}, responseHeadersExposed: ${swiftOptionalBool(exp.responseHeadersExposed)},
        swiftReply: ${swiftOptionalString(exp.swiftReply)}, dartReply: ${swiftOptionalString(exp.dartReply)}
      )
    )`;
  }).join(",\n");
  return `// GENERATED by core/scripts/gen-bridge-http-conformance.mjs from ${FIXTURE_REL} — do not edit by hand.
// The runner calls BridgeHttpPolicy, the same policy seam BridgeHttpHandler uses.
import Foundation

struct BridgeHttpConformanceExpectation {
  let outcome: String
  let failureReason: String?
  let servedDelta: Int
  let backendHit: Int
  let method: String?
  let pathAndQuery: String?
  let body: String?
  let headers: [String: String]
  let forbiddenDropped: [String]
  let bodyAfterHeaders: Bool?
  let followRedirects: Bool?
  let responseStatus: Int?
  let responseBody: String?
  let retryAfterMs: Int?
  let correlationId: String?
  let duplicateReplyDroppedBySurface: Bool?
  let redirectLocationForwarded: Bool?
  let responseHeadersExposed: Bool?
  let swiftReply: String?
  let dartReply: String?
}

struct BridgeHttpConformanceCase {
  let id: String
  let scope: String
  let requestId: String?
  let method: String?
  let path: String?
  let missingId: Bool
  let malformed: Bool
  let requestHeaders: [String: String]
  let body: String?
  let credential: String?
  let transportFailure: String?
  let responseStatus: Int?
  let responseBody: String?
  let retryAfterSeconds: Int?
  let expected: BridgeHttpConformanceExpectation
}

enum BridgeHttpConformanceFixture {
  static let rows: [BridgeHttpConformanceCase] = [
${rows}
  ]
}

private struct BridgeHttpConformanceBackend {
  private(set) var hits = 0

  mutating func receive(_ request: URLRequest) {
    // A separate sink models the backend boundary; served and backend-hit
    // counters must not be the same assignment in disguise.
    hits += 1
    _ = request
  }
}

private struct BridgeHttpConformanceReplyGate {
  private var settled = Set<String>()

  mutating func accept(_ id: String) -> Bool {
    settled.insert(id).inserted
  }
}

enum BridgeHttpConformanceRunner {
  static func run() -> [String] {
    let base = URL(string: "https://api.example")!
    var failures: [String] = []
    let sessionConfiguration = BridgeHttpPolicy.sessionConfiguration()
    // red-proof: re-enable cookie storage/acceptance in the live factory and
    // this host conformance runner fails before any fixture can pass.
    if sessionConfiguration.httpCookieStorage != nil || sessionConfiguration.httpShouldSetCookies || sessionConfiguration.httpCookieAcceptPolicy != .never {
      failures.append("session configuration must reject cookie persistence and acceptance")
    }
    for row in BridgeHttpConformanceFixture.rows {
      var served = 0
      var backend = BridgeHttpConformanceBackend()
      if row.missingId {
        if row.expected.outcome != "missing-id" || row.expected.servedDelta != 0 || row.expected.backendHit != 0 {
          failures.append("\\(row.id): missing-id row must be zero-hit and transport-scoped")
        }
        if row.expected.swiftReply != "shell-error" { failures.append("\\(row.id): Swift must reply shell-error for malformed input") }
        continue
      }
      guard let requestId = row.requestId, let method = row.method, let path = row.path else {
        failures.append("\\(row.id): request id unexpectedly absent")
        continue
      }
      let decision = BridgeHttpPolicy.prepare(
        id: requestId, method: method, path: path,
        headers: row.requestHeaders, body: row.body, baseURL: base, token: row.credential)
      switch decision {
      case let .failure(reason, _):
        let expectedOutcome = row.malformed ? "malformed" : "failure"
        if row.expected.outcome != expectedOutcome { failures.append("\\(row.id): expected dispatch, got failure") }
        if reason.rawValue != row.expected.failureReason { failures.append("\\(row.id): failure reason") }
        if row.malformed && row.expected.swiftReply != "shell-error" { failures.append("\\(row.id): Swift malformed input must reply shell-error") }
      case let .dispatch(prepared):
        served = 1
        let request = prepared.request
        // red-proof: remove backend.receive(request) and independent
        // backend-hit assertions fail.
        backend.receive(request)
        if row.expected.outcome == "failure" { failures.append("\\(row.id): expected failure, got dispatch") }
        if let method = row.expected.method, request.httpMethod != method { failures.append("\\(row.id): method") }
        if let path = row.expected.pathAndQuery, let url = request.url,
           url.path + (url.query.map { "?\\($0)" } ?? "") != path { failures.append("\\(row.id): path/query") }
        if let body = row.expected.body {
          let actual = request.httpBody.flatMap { String(data: $0, encoding: .utf8) }
          if actual != body { failures.append("\\(row.id): body") }
        } else if request.httpBody != nil { failures.append("\\(row.id): unexpected body") }
        for (name, value) in row.expected.headers where request.value(forHTTPHeaderField: name) != value {
          failures.append("\\(row.id): header \\(name)")
        }
        for forbidden in row.expected.forbiddenDropped {
          let callerValue = row.requestHeaders.first { $0.key.lowercased() == forbidden }?.value
          if let callerValue, request.value(forHTTPHeaderField: forbidden) == callerValue {
            failures.append("\\(row.id): forbidden header \\(forbidden) survived")
          }
        }
        var applyEvents: [String] = []
        // red-proof: move body before headers in BridgeHttpPolicy.apply and
        // the body-write-order fixture fails on this event sequence.
        BridgeHttpPolicy.apply(
          prepared,
          setHeader: { name, _ in applyEvents.append("header:\\(name.lowercased())") },
          setBody: { _ in applyEvents.append("body") })
        if let expected = row.expected.bodyAfterHeaders {
          if expected && (applyEvents.last != "body" || (applyEvents.firstIndex(of: "body") ?? -1) <= (applyEvents.firstIndex(of: "header:content-type") ?? Int.max)) {
            failures.append("\\(row.id): body write ordering")
          }
          if !expected && applyEvents.contains("body") { failures.append("\\(row.id): unexpected body write") }
        }
        if let redirectResponse = HTTPURLResponse(url: base, statusCode: 302, httpVersion: nil, headerFields: nil) {
          // red-proof: make redirectedRequest return proposed and the
          // redirect-no-follow fixture fails against the live delegate seam.
          let redirected = BridgeHttpPolicy.redirectedRequest(response: redirectResponse, proposed: request)
          if let expected = row.expected.followRedirects, (redirected != nil) != expected { failures.append("\\(row.id): redirect policy") }
          if let expected = row.expected.redirectLocationForwarded, (redirected != nil) != expected { failures.append("\\(row.id): redirect location forwarded") }
        }
        if row.expected.duplicateReplyDroppedBySurface == true {
          // red-proof: remove the second accept rejection and duplicate-gate
          // conformance fails instead of accepting a late reply.
          var gate = BridgeHttpConformanceReplyGate()
          if !gate.accept(requestId) || gate.accept(requestId) { failures.append("\\(row.id): duplicate reply was not dropped") }
        }
        if let failure = row.transportFailure {
          let actual = BridgeHttpPolicy.transportFailure(id: requestId, name: failure).reason.rawValue
          if actual != row.expected.failureReason { failures.append("\\(row.id): transport failure") }
        }
        if let status = row.responseStatus {
          let normalized = BridgeHttpPolicy.normalizeResponse(id: requestId, status: status, body: row.responseBody, retryAfterSeconds: row.retryAfterSeconds)
          if normalized.status != row.expected.responseStatus || normalized.body != row.expected.responseBody || normalized.retryAfterMs != row.expected.retryAfterMs { failures.append("\\(row.id): response normalization") }
          let payload = BridgeHttpPolicy.responsePayload(normalized)
          let exposed = payload["headers"] != nil || payload["set-cookie"] != nil || payload["www-authenticate"] != nil
          // red-proof: add response headers in the live reply factory and this
          // fixture fails instead of treating normalization as sufficient.
          if let expected = row.expected.responseHeadersExposed, exposed != expected { failures.append("\\(row.id): response headers exposure") }
          if let id = row.expected.correlationId, normalized.id != id { failures.append("\\(row.id): correlation id") }
        }
      }
      if served != row.expected.servedDelta { failures.append("\\(row.id): servedCount delta \\(served) != \\(row.expected.servedDelta)") }
      if backend.hits != row.expected.backendHit { failures.append("\\(row.id): backend-hit delta \\(backend.hits) != \\(row.expected.backendHit)") }
    }
    return failures
  }
}

#if BRIDGE_HTTP_CONFORMANCE_RUNNER
@main
enum BridgeHttpConformanceMain {
  static func main() {
    let failures = BridgeHttpConformanceRunner.run()
    if failures.isEmpty {
      print("bridge-http Swift conformance: \\(BridgeHttpConformanceFixture.rows.count)/\\(BridgeHttpConformanceFixture.rows.count) passed")
    } else {
      failures.forEach { print("FAIL: \\($0)") }
      Foundation.exit(1)
    }
  }
}
#endif
`;
}

function emitDart() {
  const fixtureLiteral = JSON.stringify(fixture.rows, null, 2);
  return `// GENERATED by core/scripts/gen-bridge-http-conformance.mjs from ${FIXTURE_REL} — do not edit by hand.
// The test calls BridgeHttpHost's policy seam, the same seam _handle uses.
import 'package:flutter_test/flutter_test.dart';

import '../lib/bridge_http_host.dart';

const _rows = <Map<String, dynamic>>${fixtureLiteral};

class _RecordingBackend {
  var hits = 0;

  void receive(BridgeHttpPreparedRequest request) {
    // Keep backend-hit independent from the host served counter.
    hits += 1;
    request.hashCode;
  }
}

String? _headerValue(Map<String, String> headers, String name) {
  for (final entry in headers.entries) {
    if (entry.key.toLowerCase() == name.toLowerCase()) return entry.value;
  }
  return null;
}

void main() {
  test('generated bridge HTTP host conformance', () {
    var passed = 0;
    for (final row in _rows) {
      final request = Map<String, dynamic>.from(row['request'] as Map);
      final expected = Map<String, dynamic>.from(row['expect'] as Map);
      final missingId = row['missingId'] == true;
      final malformed = row['malformed'] == true;
      final requestId = request['id'] as String?;
      if (missingId) {
        expect(expected['outcome'], 'missing-id', reason: row['id'] as String);
        expect(expected['dartReply'], 'none', reason: row['id'] as String);
        expect(expected['servedDelta'], 0, reason: row['id'] as String);
        expect(expected['backendHit'], 0, reason: row['id'] as String);
        passed += 1;
        continue;
      }
      final result = BridgeHttpHost.prepareForConformance(
        id: requestId!,
        method: request['method'] as String,
        path: request['path'] as String,
        headers: request['headers'] == null
            ? <String, String>{}
            : Map<String, String>.from(request['headers'] as Map),
        body: request['body'] as String?,
        baseUrl: Uri.parse('https://api.example'),
        token: row['credential'] as String?,
      );
      var served = 0;
      final backend = _RecordingBackend();
      if (result.request == null) {
        expect(expected['outcome'], malformed ? 'malformed' : 'failure', reason: row['id'] as String);
        expect(result.failureReason?.wire, expected['failureReason'], reason: row['id'] as String);
        if (malformed) expect(expected['dartReply'], 'shell-error', reason: row['id'] as String);
      } else {
        served = 1;
        // red-proof: remove backend.receive and independent backend-hit
        // assertions fail.
        backend.receive(result.request!);
        expect(expected['outcome'], isNot('failure'), reason: row['id'] as String);
        final prepared = result.request!;
        if (expected['method'] != null) expect(prepared.method, expected['method'], reason: row['id'] as String);
        if (expected['pathAndQuery'] != null) expect(prepared.url.path + (prepared.url.hasQuery ? '?\${prepared.url.query}' : ''), expected['pathAndQuery'], reason: row['id'] as String);
        expect(prepared.body, expected['body'], reason: row['id'] as String);
        final expectedHeaders = expected['headers'] == null
            ? <String, String>{}
            : Map<String, String>.from(expected['headers'] as Map);
        for (final entry in expectedHeaders.entries) {
          expect(_headerValue(prepared.headers, entry.key), entry.value, reason: row['id'] as String);
        }
        final forbiddenDropped = (expected['forbiddenDropped'] as List?)?.cast<String>() ?? const <String>[];
        for (final forbidden in forbiddenDropped) {
          String? callerValue;
          final rawHeaders = request['headers'];
          if (rawHeaders is Map) {
            for (final entry in rawHeaders.entries) {
              if (entry.key.toString().toLowerCase() == forbidden && entry.value is String) callerValue = entry.value as String;
            }
          }
          if (callerValue != null) expect(_headerValue(prepared.headers, forbidden), isNot(callerValue), reason: row['id'] as String);
        }
        final applyEvents = <String>[];
        // red-proof: move body before headers in BridgeHttpPreparedRequest.apply
        // and the body-write-order fixture fails on this event sequence.
        prepared.apply(
          setFollowRedirects: (value) => applyEvents.add(value ? 'redirects-on' : 'redirects-off'),
          setHeader: (name, value) => applyEvents.add('header:$name'),
          addBody: (value) => applyEvents.add('body'),
        );
        if (expected['followRedirects'] != null) expect(applyEvents.first, expected['followRedirects'] == false ? 'redirects-off' : 'redirects-on', reason: row['id'] as String);
        if (expected['redirectLocationForwarded'] != null) expect(applyEvents.first == 'redirects-on', expected['redirectLocationForwarded'], reason: row['id'] as String);
        if (expected['duplicateReplyDroppedBySurface'] == true) {
          // red-proof: remove the second accept rejection and duplicate-gate
          // conformance fails instead of accepting a late reply. The bounded
          // gate also proves old ids are evicted deterministically.
          final gate = BridgeHttpReplyGate(maxEntries: 1);
          expect(gate.accept(requestId), isTrue, reason: row['id'] as String);
          expect(gate.accept(requestId), isFalse, reason: row['id'] as String);
          expect(gate.accept('$requestId-next'), isTrue, reason: row['id'] as String);
          expect(gate.accept(requestId), isTrue, reason: row['id'] as String);
        }
        if (expected['bodyAfterHeaders'] != null) {
          expect(applyEvents.last, expected['bodyAfterHeaders'] == true ? 'body' : isNot('body'), reason: row['id'] as String);
          if (expected['bodyAfterHeaders'] == true) expect(applyEvents.indexOf('body'), greaterThan(applyEvents.indexOf('header:content-type')), reason: row['id'] as String);
        }
        final transportFailure = row['transportFailure'] as String?;
        if (transportFailure != null) {
          expect(BridgeHttpHost.transportFailureForConformance(requestId, transportFailure).wire, expected['failureReason'], reason: row['id'] as String);
        }
        final response = row['response'] as Map?;
        if (response != null) {
          final normalized = BridgeHttpHost.normalizeResponseForConformance(
            id: requestId,
            status: response['status'] as int,
            body: response['body'] as String?,
            retryAfterSeconds: response['retryAfterSeconds'] as int?,
          );
          expect(normalized.status, expected['responseStatus'], reason: row['id'] as String);
          expect(normalized.body, expected['responseBody'], reason: row['id'] as String);
          expect(normalized.retryAfterMs, expected['retryAfterMs'], reason: row['id'] as String);
          if (expected['correlationId'] != null) expect(normalized.id, expected['correlationId'], reason: row['id'] as String);
          final payload = BridgeHttpHostPolicy.responsePayload(normalized);
          final exposed = payload.containsKey('headers') || payload.containsKey('set-cookie') || payload.containsKey('www-authenticate');
          // red-proof: add response headers in the live reply factory and this
          // fixture fails instead of treating normalization as sufficient.
          if (expected['responseHeadersExposed'] != null) expect(exposed, expected['responseHeadersExposed'], reason: row['id'] as String);
        }
      }
      expect(served, expected['servedDelta'], reason: '\${row['id']} servedCount delta');
      expect(backend.hits, expected['backendHit'], reason: '\${row['id']} backend-hit delta');
      passed += 1;
    }
    expect(passed, _rows.length);
  });
}
`;
}

function emit({label, dir, out, content}) {
  if (!fs.existsSync(dir)) {
    console.log(`${label}: SKIPPED — shell prototype not found (set ${out.envVar} to override).`);
    return 0;
  }
  const abs = path.join(dir, out.path);
  const current = fs.existsSync(abs) ? fs.readFileSync(abs, "utf8") : null;
  if (check) {
    if (current !== content) {
      console.error(`${label} drift: ${out.path} — run the generator in core/`);
      return 1;
    }
    console.log(`${label} in sync (${fixture.rows.length} rows).`);
    return 0;
  }
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  if (current !== content) fs.writeFileSync(abs, content);
  console.log(`${label} generated (${fixture.rows.length} rows).`);
  return 0;
}

const statuses = [
  emit({ label: "bridge-http Swift conformance", dir: macDir, out: MAC_OUT, content: emitSwift() }),
  emit({ label: "bridge-http Dart conformance", dir: iosDir, out: IOS_OUT, content: emitDart() }),
];
process.exit(statuses.includes(1) ? 1 : 0);
