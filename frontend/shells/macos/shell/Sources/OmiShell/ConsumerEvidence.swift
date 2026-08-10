import Foundation

let consumerEvidenceSchema = "omi.consumer-evidence.v1"

enum ConsumerEvidenceRoute: String, CaseIterable, Codable {
  case memories
  case tasks
  case conversations
  case folders
  case listen
  case chat
  case settings
}

struct RenderedConsumerObservation: Codable, Equatable {
  let route: ConsumerEvidenceRoute
  let state: String
  let semantic: String
  let transcript: String?

  static func decodeRenderedJSON(_ data: Data) throws -> RenderedConsumerObservation {
    let raw = try JSONSerialization.jsonObject(with: data)
    guard let object = raw as? [String: Any] else {
      throw ConsumerEvidenceError.invalidObservation("observation is not an object")
    }
    let routeValue = object["route"] as? String
    let expectedKeys: Set<String> = routeValue == ConsumerEvidenceRoute.listen.rawValue
      ? ["route", "state", "semantic", "transcript"]
      : ["route", "state", "semantic"]
    guard Set(object.keys) == expectedKeys else {
      throw ConsumerEvidenceError.invalidObservation("observation keys are not exact")
    }
    guard let routeValue, let route = ConsumerEvidenceRoute(rawValue: routeValue),
      object["state"] as? String == "ready",
      let semantic = object["semantic"] as? String,
      !semantic.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      semantic.utf8.count <= 256
    else {
      throw ConsumerEvidenceError.invalidObservation("observation is not rendered-ready")
    }
    let transcript = object["transcript"] as? String
    if route == .listen {
      guard let transcript,
        !transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
        transcript.utf8.count <= 1_024
      else {
        throw ConsumerEvidenceError.invalidObservation("Listen needs a bounded transcript")
      }
    } else if transcript != nil {
      throw ConsumerEvidenceError.invalidObservation("non-Listen transcript leaked")
    }
    return RenderedConsumerObservation(
      route: route, state: "ready", semantic: semantic, transcript: transcript)
  }
}

struct ConsumerEvidenceTreeHashes: Equatable {
  let shell: String
  let surface: String

  static func load(shellStamp: URL?, surfaceStamp: URL?) throws -> Self {
    Self(
      shell: try readTreeHash(at: shellStamp, artifact: "macos-app"),
      surface: try readTreeHash(at: surfaceStamp, artifact: "surfaces-dist"))
  }

  private static func readTreeHash(at url: URL?, artifact: String) throws -> String {
    guard let url, let data = try? Data(contentsOf: url),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      object["artifact"] as? String == artifact,
      object["unavailable"] == nil,
      let value = object["treeHash"] as? String,
      value.range(of: "^[0-9a-f]{40}$", options: .regularExpression) != nil
    else {
      throw ConsumerEvidenceError.invalidTreeHash(artifact)
    }
    return value
  }
}

struct ConsumerEvidenceRow: Codable, Equatable {
  let runId: String
  let shell: String
  let domain: String
  let fixture: String
  let evidence: String
  let observation: RenderedConsumerObservation
  let shellTreeHash: String
  let surfaceTreeHash: String
}

struct ConsumerEvidenceDocument: Codable, Equatable {
  let schema: String
  let runId: String
  let rows: [ConsumerEvidenceRow]
}

enum ConsumerEvidenceError: Error, CustomStringConvertible {
  case invalidRunId
  case invalidShell
  case invalidTreeHash(String)
  case invalidObservation(String)
  case unexpectedRoute(expected: ConsumerEvidenceRoute, actual: ConsumerEvidenceRoute)
  case duplicateRoute(ConsumerEvidenceRoute)
  case missingRoutes

  var description: String {
    switch self {
    case .invalidRunId: return "invalid run id"
    case .invalidShell: return "invalid shell"
    case .invalidTreeHash(let artifact): return "invalid or stale \(artifact) tree hash"
    case .invalidObservation(let reason): return reason
    case .unexpectedRoute(let expected, let actual):
      return "expected rendered route \(expected.rawValue), got \(actual.rawValue)"
    case .duplicateRoute(let route): return "duplicate rendered route \(route.rawValue)"
    case .missingRoutes: return "all seven rendered routes are required"
    }
  }
}

final class ConsumerEvidenceCollector {
  let resultURL: URL
  let runId: String
  let shell: String
  let hashes: ConsumerEvidenceTreeHashes
  private var rowsByRoute: [ConsumerEvidenceRoute: ConsumerEvidenceRow] = [:]
  private(set) var didWrite = false

  init(resultURL: URL, runId: String, shell: String, hashes: ConsumerEvidenceTreeHashes) throws {
    try? FileManager.default.removeItem(at: resultURL)
    guard runId.range(of: "^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$", options: .regularExpression) != nil,
      runId != "anonymous", runId != "overflow", !runId.hasPrefix("__")
    else { throw ConsumerEvidenceError.invalidRunId }
    guard shell == "macos" else { throw ConsumerEvidenceError.invalidShell }
    self.resultURL = resultURL
    self.runId = runId
    self.shell = shell
    self.hashes = hashes
  }

  func accept(_ observation: RenderedConsumerObservation, expected: ConsumerEvidenceRoute) throws {
    guard observation.state == "ready",
      !observation.semantic.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      observation.semantic.utf8.count <= 256,
      (expected == .listen
        ? observation.transcript.map {
            !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && $0.utf8.count <= 1_024
          } == true
        : observation.transcript == nil)
    else { throw ConsumerEvidenceError.invalidObservation("observation is not rendered-ready") }
    guard observation.route == expected else {
      throw ConsumerEvidenceError.unexpectedRoute(expected: expected, actual: observation.route)
    }
    guard rowsByRoute[expected] == nil else { throw ConsumerEvidenceError.duplicateRoute(expected) }
    rowsByRoute[expected] = ConsumerEvidenceRow(
      runId: runId,
      shell: shell,
      domain: expected.rawValue,
      fixture: "none",
      evidence: "rendered-semantic",
      observation: observation,
      shellTreeHash: hashes.shell,
      surfaceTreeHash: hashes.surface)
  }

  func finish() throws {
    let rows = try ConsumerEvidenceRoute.allCases.map { route -> ConsumerEvidenceRow in
      guard let row = rowsByRoute[route] else { throw ConsumerEvidenceError.missingRoutes }
      return row
    }
    let document = ConsumerEvidenceDocument(schema: consumerEvidenceSchema, runId: runId, rows: rows)
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .prettyPrinted]
    let data = try encoder.encode(document) + Data("\n".utf8)
    try FileManager.default.createDirectory(
      at: resultURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try data.write(to: resultURL, options: .atomic)
    didWrite = true
  }

  func teardown() {
    if !didWrite { try? FileManager.default.removeItem(at: resultURL) }
  }
}
