import Foundation
@preconcurrency import GRDB

/// S12 summarizer-only debug harness. Runs the S10 chunk-map-reduce
/// summarizer over supplied sessions (live: last K GRDB rows) and writes
/// schema-validity + timings. Memory-structure metrics and the AFM adapter
/// stay cut — S5b/S10b are not on `main`, and AFM remains a fail-closed name.
enum LocalSummaryBenchmark {
  static let reportKind = "local_summary_benchmark"
  static let reportVersion = 1
  static let maxSessions = 50

  struct Session: Sendable, Equatable {
    var sessionId: Int64
    var startedAt: Date
    var segments: [TranscriptHash.Segment]
  }

  struct Report: Codable, Equatable, Sendable {
    var kind: String
    var version: Int
    var generatedAt: String
    var engineID: String
    var cases: [Case]
  }

  struct Case: Codable, Equatable, Sendable {
    var sessionId: Int64
    var transcriptSha256: String
    var elapsedMs: Int
    var schemaValid: Bool
    var schemaErrors: [String]
    var fallback: Bool
    var runtime: String
    var titlePresent: Bool
  }

  static func evaluate(
    _ projection: OmiAPI.ClientProcessing,
    expectedDigest: String
  ) -> (schemaValid: Bool, errors: [String]) {
    var errors: [String] = []
    if projection.schemaVersion != ClientProcessingContract.schemaVersion {
      errors.append("schema_version")
    }
    if projection.transcriptSha256 != expectedDigest {
      errors.append("transcript_sha256")
    }
    if projection.structure.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      errors.append("title")
    }
    let runtime = projection.provenance.runtime
    if runtime != ClientProcessingContract.localRuntime
      && runtime != ClientProcessingContract.deterministicRuntime
    {
      errors.append("provenance.runtime")
    }
    do {
      _ = try ClientProcessingContract.decode(ClientProcessingContract.encode(projection))
    } catch {
      errors.append("round_trip")
    }
    return (errors.isEmpty, errors)
  }

  static func run(
    sessions: [Session],
    summarizer: ConversationChunkSummarizer,
    engineID: String,
    now: @escaping @Sendable () -> Date = { Date() }
  ) async -> Report {
    var cases: [Case] = []
    cases.reserveCapacity(sessions.count)
    for session in sessions {
      let digest = TranscriptHash.sha256(segments: session.segments)
      let started = ContinuousClock.now
      let stored: StoredClientProjection
      do {
        stored = try await summarizer.summarize(
          sessionId: session.sessionId,
          segments: session.segments,
          startedAt: session.startedAt
        )
      } catch {
        let elapsed = max(0, Int(started.duration(to: .now) / .milliseconds(1)))
        cases.append(
          Case(
            sessionId: session.sessionId,
            transcriptSha256: digest,
            elapsedMs: elapsed,
            schemaValid: false,
            schemaErrors: ["summarize_threw"],
            fallback: true,
            runtime: "error",
            titlePresent: false
          ))
        continue
      }
      let elapsed = max(0, Int(started.duration(to: .now) / .milliseconds(1)))
      do {
        let payload = try ClientProcessingContract.decode(stored.json)
        let judged = evaluate(payload, expectedDigest: digest)
        cases.append(
          Case(
            sessionId: session.sessionId,
            transcriptSha256: digest,
            elapsedMs: elapsed,
            schemaValid: judged.schemaValid,
            schemaErrors: judged.errors,
            fallback: payload.provenance.runtime == ClientProcessingContract.deterministicRuntime,
            runtime: payload.provenance.runtime,
            titlePresent: !payload.structure.title.trimmingCharacters(in: .whitespacesAndNewlines)
              .isEmpty
          ))
      } catch {
        cases.append(
          Case(
            sessionId: session.sessionId,
            transcriptSha256: digest,
            elapsedMs: elapsed,
            schemaValid: false,
            schemaErrors: ["decode"],
            fallback: true,
            runtime: "undecodable",
            titlePresent: false
          ))
      }
    }
    return Report(
      kind: reportKind,
      version: reportVersion,
      generatedAt: ClientProcessingContract.iso8601(now()),
      engineID: engineID,
      cases: cases
    )
  }

  static func write(_ report: Report, to url: URL) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let data = try encoder.encode(report)
    try FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(),
      withIntermediateDirectories: true
    )
    try data.write(to: url, options: .atomic)
  }

  static func defaultReportURL(now: Date = Date()) -> URL {
    let stamp = ClientProcessingContract.iso8601(now).replacingOccurrences(of: ":", with: "")
    let support =
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)
      .first
      ?? URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
    let bundle = Bundle.main.bundleIdentifier ?? "com.omi.desktop"
    return
      support
      .appendingPathComponent(bundle, isDirectory: true)
      .appendingPathComponent("local-summary-benchmark", isDirectory: true)
      .appendingPathComponent("report-\(stamp).json")
  }

  /// Last K GRDB sessions with their segments. Does not write projections back.
  static func loadRecentSessions(from db: Database, limit: Int) throws -> [Session] {
    let capped = min(max(limit, 1), maxSessions)
    let rows = try Row.fetchAll(
      db,
      sql: """
        SELECT id, startedAt
        FROM transcription_sessions
        WHERE COALESCE(deleted, 0) = 0
        ORDER BY startedAt DESC, id DESC
        LIMIT ?
        """,
      arguments: [capped]
    )
    var sessions: [Session] = []
    sessions.reserveCapacity(rows.count)
    for row in rows {
      let sessionId: Int64 = row["id"]
      let startedAt: Date = row["startedAt"] ?? Date(timeIntervalSince1970: 0)
      let segments =
        try TranscriptionSegmentRecord
        .filter(Column("sessionId") == sessionId)
        .order(Column("segmentOrder").asc)
        .fetchAll(db)
        .map(\.hashSegment)
        .filter { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
      guard !segments.isEmpty else { continue }
      sessions.append(Session(sessionId: sessionId, startedAt: startedAt, segments: segments))
    }
    return sessions
  }
}
