import Foundation

/// Fixture comparison for exact client contributions. Zero stage durations stay on the
/// observation and do not enter histograms. This is not a live canary receipt.
enum ClientTelemetryParity {
  static let bucketEdgesMilliseconds: [(label: String, milliseconds: Int)] = [
    ("0.05", 50), ("0.1", 100), ("0.25", 250), ("0.5", 500), ("1", 1_000), ("2", 2_000), ("5", 5_000),
    ("10", 10_000), ("30", 30_000), ("60", 60_000), ("120", 120_000), ("300", 300_000), ("900", 900_000),
    ("3600", 3_600_000), ("86400", 86_400_000),
  ]

  static func histogram(milliseconds values: [Int]) -> [String: Any] {
    histogram(milliseconds: values, dropZeros: true)
  }

  /// sol blocker: only screen-stage zeros mean "stage not completed" and are
  /// excluded; a successful voice latency of 0ms is a real sample and must be
  /// kept in count/sum/buckets.
  static func histogram(milliseconds values: [Int], dropZeros: Bool) -> [String: Any] {
    let positive = dropZeros ? values.filter { $0 > 0 } : values
    var buckets: [[String: Any]] = bucketEdgesMilliseconds.map { edge in
      [
        "count": positive.filter { $0 <= edge.milliseconds }.count,
        "le_seconds": leSeconds(edge.label),
      ]
    }
    buckets.append(["count": positive.count, "le_seconds": "+Inf"])
    return ["buckets": buckets, "count": positive.count, "sum_ms": positive.reduce(0, +)]
  }

  static func receipt(observations: [ClientTelemetryObservation]) -> [String: Any] {
    [
      "fallback": fallbackSection(observations.filter { $0.family == "fallback" }),
      "screen_task": screenSection(observations.filter { $0.family == "screen_task" }),
      "voice": voiceSection(observations.filter { $0.family == "voice_turn" }),
    ]
  }

  static func canonicalData(_ object: Any) -> Data? {
    guard JSONSerialization.isValidJSONObject(object) else { return nil }
    return try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .prettyPrinted])
  }

  private static func voiceSection(_ observations: [ClientTelemetryObservation]) -> [String: Any] {
    var section: [String: Any] = [:]
    for population in ["physical_shortcut", "floating_voice"] {
      let rows = observations.filter { string($0, "population") == population }
      let terminals = rows.filter { string($0, "phase") == "terminal" }
      let latencies = terminals.compactMap { observation -> Int? in
        guard string(observation, "outcome") == "success" else { return nil }
        return integer(observation, "latency_ms")
      }
      let startedCount = rows.filter { string($0, "phase") == "started" }.count
      let excludedCount = terminals.filter { string($0, "outcome") == "excluded" }.count
      let failureCount = terminals.filter { string($0, "outcome") == "failure" }.count
      let successCount = terminals.filter { string($0, "outcome") == "success" }.count
      let unknownCount = terminals.filter { string($0, "outcome") == "unknown" }.count
      let latencyHistogram = histogram(milliseconds: latencies, dropZeros: false)
      var payload: [String: Any] = [:]
      payload["latency_count"] = latencies.count
      payload["latency_sum_ms"] = latencies.reduce(0, +)
      payload["started"] = startedCount
      payload["terminal_excluded"] = excludedCount
      payload["terminal_failure"] = failureCount
      payload["terminal_success"] = successCount
      payload["terminal_unknown"] = unknownCount
      payload["latency_histogram"] = latencyHistogram
      section[population] = payload
    }
    return section
  }

  private static func fallbackSection(_ observations: [ClientTelemetryObservation]) -> [String: Any] {
    var areas: [String: Any] = [:]
    for observation in observations {
      let area = string(observation, "area") ?? "other"
      let count = (areas[area] as? Int) ?? 0
      areas[area] = count + 1
    }
    return [
      "areas": areas,
      "degraded": observations.filter { string($0, "outcome") == "degraded" }.count,
      "exhausted": observations.filter { string($0, "outcome") == "exhausted" }.count,
      "recovered": observations.filter { string($0, "outcome") == "recovered" }.count,
    ]
  }

  private static func screenSection(_ observations: [ClientTelemetryObservation]) -> [String: Any] {
    let rejected = observations.filter { string($0, "outcome") == "gate_rejected" }.count
    let preUpload = observations.filter { observation in
      string(observation, "outcome") == "failed"
        && integer(observation, "extraction_attempts") == 0
        && integer(observation, "legacy_attempts") == 0
        && string(observation, "extractor") == "none"
    }.count
    var durations: [String: Any] = [:]
    for key in [
      "ocr_ms", "retrieval_ms", "gate_ms", "extraction_ms", "delivery_ms", "capture_to_terminal_ms",
    ] {
      durations[key] = histogram(milliseconds: observations.map { integer($0, key) ?? 0 })
    }
    return [
      "durations": durations,
      "eligible_frames": observations.reduce(0) { $0 + (integer($1, "eligible_frames") ?? 0) },
      "policy_rejected": observations.reduce(0) { $0 + (integer($1, "policy_rejected") ?? 0) },
      "pre_upload_failed": preUpload,
      "rejected": rejected,
      "terminals": observations.count,
    ]
  }

  private static func string(_ observation: ClientTelemetryObservation, _ key: String) -> String? {
    if case .string(let value) = observation.attributes[key] { return value }
    return nil
  }

  private static func integer(_ observation: ClientTelemetryObservation, _ key: String) -> Int? {
    if case .int(let value) = observation.attributes[key] { return value }
    return nil
  }

  private static func leSeconds(_ label: String) -> Any {
    if label.contains(".") { return Double(label) ?? 0 }
    return Int(label) ?? 0
  }
}
