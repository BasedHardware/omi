import Foundation

// Synthetic host-side serialization evidence, not an iPhone latency gate.
@main
struct BleHistoryRingBenchmark {
    static func main() throws {
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        let history: [[String: Any]] = (0..<4096).map { index in [
            "timestamp": now - Int64(4096 - index) * 1000,
            "reason": "connection_timeout", "reasonCode": 8, "isManual": false,
            "eventType": "disconnect", "lastRssi": -70, "lastRssiAgeMs": 250,
            "audioPacketsReceived": 10000, "audioPacketsExpected": 10000,
            "connectionDurationMs": 60000, "appState": "background",
            "timeToReconnectMs": 2000, "rssiTrend": "sudden", "identity_epoch": 7,
            "app_build": "synthetic", "firmware": "synthetic", "ring_read_active": false,
        ] }
        let suite = "ble-history-benchmark-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        var cases: [[String: Any]] = []
        for limit in [500, 4096] {
            let retained = OmiBleReconnectDiagnostics().retainedHistory(
                history, nowMs: now, retentionMs: 7 * 86400000, limit: limit,
                timestampOf: OmiBleReconnectDiagnostics.retentionTimestamp)
            let json = try JSONSerialization.data(withJSONObject: retained)
            let plist = try PropertyListSerialization.data(fromPropertyList: retained, format: .binary, options: 0)
            precondition(retained.count == limit)
            var samples: [Double] = []
            for _ in 0..<12 {
                let started = ProcessInfo.processInfo.systemUptime
                _ = try PropertyListSerialization.data(fromPropertyList: retained, format: .binary, options: 0)
                defaults.set(retained, forKey: "history")
                defaults.synchronize()
                samples.append((ProcessInfo.processInfo.systemUptime - started) * 1000)
            }
            samples.sort()
            cases.append(["rows": retained.count, "json_bytes": json.count, "binary_plist_bytes": plist.count,
                          "host_plist_and_defaults_p50_ms": samples[6], "host_plist_and_defaults_max_ms": samples[11]])
        }
        let result: [String: Any] = ["captured_at": ISO8601DateFormatter().string(from: Date()),
            "host": CommandLine.arguments.dropFirst().first ?? "unspecified", "input": "synthetic native disconnect fields",
            "samples_per_case": 12, "cases": cases,
            "limits": "macOS serialization and isolated defaults only; iOS/Android disconnect-loop latency unverified"]
        let data = try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
        print(String(decoding: data, as: UTF8.self))
    }
}
