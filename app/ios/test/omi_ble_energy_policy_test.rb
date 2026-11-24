# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class OmiBleEnergyPolicyTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  POLICY_SOURCE = File.join(IOS_ROOT, 'Runner', 'Ble', 'OmiBleEnergyPolicy.swift')

  def test_recovery_backfills_retained_history_after_retry_storms
    Dir.mktmpdir('omi-ble-recovery-history') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'omi-ble-recovery-history-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        struct History {
            var diagnostics = OmiBleReconnectDiagnostics()
            var events: [[String: Any]] = []
            let retentionMs: Int64 = 7 * 24 * 3600 * 1_000

            mutating func append(_ timestamp: Int64, _ type: String, manual: Bool = false) {
                diagnostics.recordEvent(timestampMs: timestamp, eventType: type, isManual: manual)
                events.append(["timestamp": timestamp, "eventType": type, "timeToReconnectMs": Int64(0)])
                events = diagnostics.retainedHistory(
                    events, nowMs: timestamp, retentionMs: retentionMs, limit: 500,
                    timestampOf: OmiBleReconnectDiagnostics.eventTimestamp
                )
            }

            mutating func recover(_ timestamp: Int64, hadConnection: Bool = true) -> [[String: Any]]? {
                // Use the native persisted shape, including its plist round trip.
                let bytes = try! PropertyListSerialization.data(fromPropertyList: events, format: .binary, options: 0)
                let stored = try! PropertyListSerialization.propertyList(from: bytes, options: [], format: nil) as! [[String: Any]]
                return diagnostics.backfilledHistory(
                    stored, nowMs: timestamp, hadConnection: hadConnection,
                    timestampOf: OmiBleReconnectDiagnostics.eventTimestamp,
                    resolvedAtOf: { $0["lostAudioResolvedAt"] as? Int64 },
                    onLookupMiss: { _ in },
                    withDuration: { event, duration in
                        var updated = event
                        updated["timeToReconnectMs"] = duration
                        return updated
                    }
                )
            }
        }

        @main
        struct RecoveryHistoryHarness {
            static func main() {
                var history = History()
                history.append(1_000, "disconnect")
                for attempt in 1...1_000 {
                    history.append(1_000 + Int64(attempt) * 3_000, "fail_to_connect")
                    precondition(history.events.count <= 500)
                }
                guard let updated = history.recover(3_004_000) else {
                    fatalError("Original disconnect was evicted before recovery")
                }
                precondition(updated.count == 500)
                precondition(updated[0]["timestamp"] as? Int64 == 1_000)
                precondition(updated[0]["eventType"] as? String == "disconnect")
                precondition(updated[0]["timeToReconnectMs"] as? Int64 == 3_003_000)
                let retries = Array(updated.dropFirst())
                precondition(retries.compactMap { $0["timestamp"] as? Int64 } == (502...1_000).map { 1_000 + Int64($0) * 3_000 })
                precondition(retries.allSatisfy { ($0["timeToReconnectMs"] as? Int64) == 0 })
                precondition(history.recover(3_005_000) == nil)

                // Protected does not mean retained beyond the seven-day boundary.
                history = History()
                history.append(1_000, "disconnect")
                history.append(1_000 + history.retentionMs, "fail_to_connect")
                precondition(history.events.first?["timestamp"] as? Int64 == 1_000)
                history.append(1_001 + history.retentionMs, "fail_to_connect")
                precondition(history.events.count == 2)
                precondition(history.recover(2_000 + history.retentionMs) == nil)
                precondition(history.events.allSatisfy { ($0["timeToReconnectMs"] as? Int64) == 0 })
                precondition(history.recover(3_000 + history.retentionMs) == nil)

                // Initial success consumes the marker without manufacturing a reconnect.
                history = History()
                for attempt in 1...501 { history.append(Int64(attempt), "fail_to_connect") }
                precondition(history.recover(502, hadConnection: false) == nil)
                precondition(history.recover(503) == nil)
                history.append(1_000, "disconnect")
                history.append(1_500, "fail_to_connect")
                let reconnected = history.recover(2_000)!
                let timed = reconnected.filter { ($0["timeToReconnectMs"] as? Int64 ?? 0) > 0 }
                precondition(timed.count == 1 && timed[0]["timestamp"] as? Int64 == 1_000)
                precondition(timed[0]["timeToReconnectMs"] as? Int64 == 1_000)
                precondition(!reconnected.contains { $0["timestamp"] as? Int64 == 1 })

                // Manual cancellation releases the slot for newest history.
                history = History()
                history.append(1_000, "disconnect")
                for attempt in 1...500 { history.append(1_000 + Int64(attempt), "fail_to_connect") }
                history.append(2_000, "disconnect", manual: true)
                precondition(history.events.count == 500)
                precondition(!history.events.contains { $0["timestamp"] as? Int64 == 1_000 })
                precondition(history.recover(3_000) == nil)
            }
        }
      SWIFT
      stdout, stderr, compile = Open3.capture3('swiftc', '-parse-as-library', POLICY_SOURCE, harness, '-o', binary)
      assert compile.success?, "swiftc failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, run = Open3.capture3(binary)
      assert run.success?, "recovery history assertions failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_resolved_outage_ages_from_resolution_and_unresolved_start_still_prunes
    Dir.mktmpdir('omi-ble-resolution-retention') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'omi-ble-resolution-retention-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct ResolutionRetentionHarness {
            static func main() {
                let hour: Int64 = 3_600_000
                let day: Int64 = 24 * hour
                let now: Int64 = 10 * day
                let retentionMs: Int64 = 7 * day
                var diagnostics = OmiBleReconnectDiagnostics()
                let resolvedStart = now - 8 * day
                let resolvedAt = now - hour
                let unresolvedStart = resolvedStart - 1
                let events: [[String: Any]] = [
                    ["timestamp": resolvedStart, "lostAudioResolvedAt": resolvedAt, "eventType": "disconnect"],
                    ["timestamp": unresolvedStart, "eventType": "disconnect"],
                ]
                precondition(OmiBleReconnectDiagnostics.retentionTimestamp(events[0]) == resolvedAt)
                precondition(OmiBleReconnectDiagnostics.retentionTimestamp(events[1]) == unresolvedStart)
                let kept = diagnostics.retainedHistory(
                    events, nowMs: now, retentionMs: retentionMs, limit: 500,
                    timestampOf: OmiBleReconnectDiagnostics.retentionTimestamp
                )
                precondition(kept.count == 1)
                precondition(kept[0]["timestamp"] as? Int64 == resolvedStart)
                precondition(kept[0]["lostAudioResolvedAt"] as? Int64 == resolvedAt)

                // Resolution outside the window still prunes; the count cap is unchanged.
                let staleResolved: [String: Any] = [
                    "timestamp": now - 20 * day,
                    "lostAudioResolvedAt": now - 8 * day,
                ]
                let pruned = diagnostics.retainedHistory(
                    [staleResolved], nowMs: now, retentionMs: retentionMs, limit: 500,
                    timestampOf: OmiBleReconnectDiagnostics.retentionTimestamp
                )
                precondition(pruned.isEmpty)

                // Unresolved reconnect matching still keys off the start.
                diagnostics.recordEvent(timestampMs: 1_000, eventType: "disconnect", isManual: false)
                let open: [[String: Any]] = [["timestamp": Int64(1_000), "timeToReconnectMs": Int64(0)]]
                let backfilled = diagnostics.backfilledHistory(
                    open, nowMs: 2_000, hadConnection: true,
                    timestampOf: OmiBleReconnectDiagnostics.eventTimestamp,
                    resolvedAtOf: { $0["lostAudioResolvedAt"] as? Int64 },
                    onLookupMiss: { _ in },
                    withDuration: { event, duration in
                        var updated = event
                        updated["timeToReconnectMs"] = duration
                        return updated
                    }
                )
                precondition(backfilled?[0]["timeToReconnectMs"] as? Int64 == 1_000)

                // Resolved reconnect matching must also key off the start timestamp,
                // not lostAudioResolvedAt.
                diagnostics.recordEvent(timestampMs: 1_000, eventType: "disconnect", isManual: false)
                let resolvedHistory: [[String: Any]] = [["timestamp": Int64(1_000), "lostAudioResolvedAt": Int64(1_500), "timeToReconnectMs": Int64(0)]]
                let backfilledResolved = diagnostics.backfilledHistory(
                    resolvedHistory, nowMs: 2_000, hadConnection: true,
                    timestampOf: OmiBleReconnectDiagnostics.eventTimestamp,
                    resolvedAtOf: { $0["lostAudioResolvedAt"] as? Int64 },
                    onLookupMiss: { _ in },
                    withDuration: { event, duration in
                        var updated = event
                        updated["timeToReconnectMs"] = duration
                        return updated
                    }
                )
                guard let resolvedUpdated = backfilledResolved, !resolvedUpdated.isEmpty else {
                    fatalError("Resolved outage row was not found because lookup used retentionTimestamp")
                }
                precondition(resolvedUpdated[0]["timeToReconnectMs"] as? Int64 == 500)

                var misses: [Int64] = []
                func recover(_ history: [[String: Any]]) -> [[String: Any]]? {
                    diagnostics.recordEvent(timestampMs: 1_000, eventType: "disconnect", isManual: false)
                    return diagnostics.backfilledHistory(
                        history, nowMs: 1_000, hadConnection: true,
                        timestampOf: OmiBleReconnectDiagnostics.eventTimestamp,
                        resolvedAtOf: { $0["lostAudioResolvedAt"] as? Int64 },
                        onLookupMiss: { misses.append($0) },
                        withDuration: { event, duration in
                            var updated = event
                            updated["timeToReconnectMs"] = duration
                            return updated
                        }
                    )
                }
                let immediate = recover([["timestamp": Int64(1_000)]])
                precondition(immediate?[0]["timeToReconnectMs"] as? Int64 == 0)
                precondition(misses.isEmpty)
                precondition(recover([["timestamp": Int64(999)]]) == nil)
                precondition(misses == [1_000])
            }
        }
      SWIFT
      stdout, stderr, compile = Open3.capture3('swiftc', '-parse-as-library', POLICY_SOURCE, harness, '-o', binary)
      assert compile.success?, "swiftc failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, run = Open3.capture3(binary)
      assert run.success?, "resolution retention assertions failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_recovery_latency_tracks_the_disconnect_across_failed_retries
    Dir.mktmpdir('omi-ble-recovery') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'omi-ble-recovery-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct RecoveryHarness {
            static func main() {
                var recovery = OmiBleReconnectDiagnostics()
                recovery.recordEvent(timestampMs: 1_000, eventType: "disconnect", isManual: false)
                recovery.recordEvent(timestampMs: 2_000, eventType: "fail_to_connect", isManual: false)
                recovery.recordEvent(timestampMs: 5_000, eventType: "fail_to_connect", isManual: false)
                let reconnected = recovery.recovered(atMs: 9_000, hadConnection: true)!
                precondition(reconnected.eventTimestampMs == 1_000)
                precondition(reconnected.durationMs == 8_000)
                precondition(recovery.recovered(atMs: 10_000, hadConnection: true) == nil)

                // Failure before the first successful connection must be
                // consumed, so a later link loss starts a new recovery.
                recovery.recordEvent(timestampMs: 11_000, eventType: "fail_to_connect", isManual: false)
                precondition(recovery.recovered(atMs: 12_000, hadConnection: false) == nil)
                precondition(recovery.recovered(atMs: 13_000, hadConnection: true) == nil)
                recovery.recordEvent(timestampMs: 20_000, eventType: "disconnect", isManual: false)
                recovery.recordEvent(timestampMs: 21_000, eventType: "fail_to_connect", isManual: false)
                let laterRecovery = recovery.recovered(atMs: 25_000, hadConnection: true)!
                precondition(laterRecovery.eventTimestampMs == 20_000)
                precondition(laterRecovery.durationMs == 5_000)

                recovery.recordEvent(timestampMs: 30_000, eventType: "disconnect", isManual: false)
                recovery.recordEvent(timestampMs: 31_000, eventType: "disconnect", isManual: true)
                precondition(recovery.recovered(atMs: 35_000, hadConnection: true) == nil)

                // A new physical disconnect supersedes an earlier attempt;
                // clock adjustments must not produce negative durations.
                recovery.recordEvent(timestampMs: 40_000, eventType: "fail_to_connect", isManual: false)
                recovery.recordEvent(timestampMs: 45_000, eventType: "disconnect", isManual: false)
                let newLoss = recovery.recovered(atMs: 44_000, hadConnection: true)!
                precondition(newLoss.eventTimestampMs == 45_000)
                precondition(newLoss.durationMs == 0)
            }
        }
      SWIFT
      stdout, stderr, compile = Open3.capture3('swiftc', '-parse-as-library', POLICY_SOURCE, harness, '-o', binary)
      assert compile.success?, "swiftc failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, run = Open3.capture3(binary)
      assert run.success?, "recovery assertions failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_rssi_polling_and_battery_history_policy
    Dir.mktmpdir('omi-ble-energy-policy') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'omi-ble-energy-policy-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct OmiBleEnergyPolicyTestHarness {
            static func main() {
                let minute: Int64 = 60_000
                precondition(OmiBleEnergyPolicy.shouldPersistBatteryReading(
                    previousLevel: nil,
                    previousTimestampMs: nil,
                    level: 80,
                    nowMs: 0
                ))
                precondition(OmiBleEnergyPolicy.shouldPersistBatteryReading(
                    previousLevel: 80,
                    previousTimestampMs: 0,
                    level: 79,
                    nowMs: 14 * minute
                ))
                // A process relaunch rehydrates the last persisted sample into
                // this same baseline; an unchanged first notification must
                // remain throttled rather than rewriting the history ring.
                precondition(!OmiBleEnergyPolicy.shouldPersistBatteryReading(
                    previousLevel: 72,
                    previousTimestampMs: 10 * minute,
                    level: 72,
                    nowMs: 11 * minute
                ))
                precondition(OmiBleEnergyPolicy.shouldPersistBatteryReading(
                    previousLevel: 80,
                    previousTimestampMs: 0,
                    level: 75,
                    nowMs: minute
                ))
                precondition(OmiBleEnergyPolicy.shouldPersistBatteryReading(
                    previousLevel: 80,
                    previousTimestampMs: 0,
                    level: 80,
                    nowMs: 60 * minute
                ))
                precondition(OmiBleEnergyPolicy.shouldPersistBatteryReading(
                    previousLevel: 20,
                    previousTimestampMs: 0,
                    level: 19,
                    nowMs: minute
                ))
                let suiteName = "omi-ble-plist-\(UUID().uuidString)"
                let defaults = UserDefaults(suiteName: suiteName)!
                defer { defaults.removePersistentDomain(forName: suiteName) }
                for charging in [true, false, nil] as [Bool?] {
                    let entry = OmiBleEnergyPolicy.batteryHistoryEntry(timestampMs: 123, level: 80, charging: charging)
                    precondition(entry["charging"] as? Bool == charging)
                    precondition(entry.keys.contains("charging") == (charging != nil))
                    let history = [entry]
                    precondition((try? PropertyListSerialization.data(fromPropertyList: history, format: .binary, options: 0)) != nil)
                    defaults.set(history, forKey: "battery_history_test")
                    precondition((defaults.array(forKey: "battery_history_test") as? [[String: Any]])?.count == 1)
                }
                for charging in [true, false] {
                    let history = [
                        OmiBleEnergyPolicy.batteryHistoryEntry(timestampMs: 0, level: 100, charging: nil),
                        OmiBleEnergyPolicy.batteryHistoryEntry(timestampMs: 5, level: 45, charging: nil),
                    ]
                    let updated = OmiBleEnergyPolicy.backfillLatestBatteryCharging(history, charging: charging, nowMs: 5 + OmiBleEnergyPolicy.batteryBackfillMaxAgeMs)!
                    precondition(updated.count == 2)
                    precondition(updated[0]["charging"] == nil)
                    precondition(updated[1]["ts"] as? Int64 == 5)
                    precondition(updated[1]["level"] as? Int == 45)
                    precondition(updated[1]["charging"] as? Bool == charging)
                    precondition(OmiBleEnergyPolicy.backfillLatestBatteryCharging(updated, charging: !charging, nowMs: 5 + OmiBleEnergyPolicy.batteryBackfillMaxAgeMs) == nil)
                    // A point older than the backfill window stays unknown.
                    precondition(OmiBleEnergyPolicy.backfillLatestBatteryCharging(history, charging: charging, nowMs: 6 + OmiBleEnergyPolicy.batteryBackfillMaxAgeMs) == nil)
                    defaults.set(updated, forKey: "battery_history_backfill")
                    precondition((defaults.array(forKey: "battery_history_backfill") as? [[String: Any]])?.last?["charging"] as? Bool == charging)
                }
                precondition(OmiBleEnergyPolicy.backfillLatestBatteryCharging([], charging: true, nowMs: 0) == nil)
                precondition(OmiBleFirmwareDiagnostics.parse(Data(repeating: 0, count: 24), timestampMs: 1) == nil)
                precondition(OmiBleFirmwareDiagnostics.parse(Data(repeating: 0, count: 25), timestampMs: 1) == nil)
                var diagnostic = Data(repeating: 0, count: 25)
                diagnostic[0] = 1
                diagnostic[1] = 0x11 // RESET_PIN | RESET_WATCHDOG
                diagnostic[5] = 42
                diagnostic[9] = 0x34
                diagnostic[10] = 0x12
                diagnostic[11] = 1
                let parsed = OmiBleFirmwareDiagnostics.parse(diagnostic, timestampMs: 123)!
                precondition(parsed["version"] as? Int == 1)
                precondition(parsed["reset_cause_names"] as? [String] == ["RESET_PIN", "RESET_WATCHDOG"])
                precondition(parsed["uptime_s"] as? UInt32 == 42)
                precondition(parsed["battery_mv"] as? NSNumber == 0x1234)
                precondition(parsed["charging"] as? NSNumber == true)
                for key in ["last_off_charger_mv", "charge_pin_edges", "soc_frozen"] { precondition(parsed[key] == nil) }
                var tail = diagnostic
                tail.append(contentsOf: [0x34, 0x12, 0x78, 0x56, 1])
                let extended = OmiBleFirmwareDiagnostics.parse(tail, timestampMs: 123)!
                for (key, value) in parsed { precondition((value as AnyObject).isEqual(extended[key])) }
                precondition(extended["last_off_charger_mv"] as? NSNumber == 0x1234)
                precondition(extended["charge_pin_edges"] as? NSNumber == 0x5678)
                precondition(extended["soc_frozen"] as? Bool == true)
                tail.append(contentsOf: [1, 2, 3])
                precondition(NSDictionary(dictionary: extended).isEqual(to: OmiBleFirmwareDiagnostics.parse(tail, timestampMs: 123)!))
                tail[29] = 0
                precondition(OmiBleFirmwareDiagnostics.parse(tail, timestampMs: 123)!["soc_frozen"] as? Bool == false)
                for offset in 25...29 { tail[offset] = 0xff }
                let unknownTail = OmiBleFirmwareDiagnostics.parse(tail, timestampMs: 123)!
                for key in ["last_off_charger_mv", "charge_pin_edges", "soc_frozen"] { precondition(unknownTail[key] == nil) }
                for length in 26...29 {
                    let partial = OmiBleFirmwareDiagnostics.parse(Data(tail.prefix(length)), timestampMs: 123)!
                    precondition(partial["last_off_charger_mv"] == nil)
                }
                precondition((try? PropertyListSerialization.data(fromPropertyList: [parsed], format: .binary, options: 0)) != nil)
                let connectionKeys = ["conn_interval", "conn_latency", "conn_timeout", "tx_phy", "rx_phy"]
                for length in [25, 30, 31, 32, 33, 34, 35, 36, 37] {
                    var incomplete = diagnostic
                    incomplete.append(Data(repeating: 0xff, count: length - 25))
                    let p = OmiBleFirmwareDiagnostics.parse(incomplete, timestampMs: 1)!
                    for key in connectionKeys { precondition(p[key] == nil) }
                }
                var connection = diagnostic
                connection.append(contentsOf: [255, 255, 255, 255, 255, 0x34, 0x12, 0x78, 0x56, 0x58, 2, 2, 4])
                let conn = OmiBleFirmwareDiagnostics.parse(connection, timestampMs: 123)!
                for (key, value) in zip(connectionKeys, [0x1234, 0x5678, 600, 2, 4]) {
                    precondition(conn[key] as? NSNumber == NSNumber(value: value))
                }
                for (key, value) in parsed { precondition((value as AnyObject).isEqual(conn[key])) }
                for key in ["last_off_charger_mv", "charge_pin_edges", "soc_frozen"] { precondition(conn[key] == nil) }
                precondition((try? PropertyListSerialization.data(fromPropertyList: [conn], format: .binary, options: 0)) != nil)
                connection.append(contentsOf: [99, 98])
                precondition(NSDictionary(dictionary: conn).isEqual(to: OmiBleFirmwareDiagnostics.parse(connection, timestampMs: 123)!))
                for offset in 30...37 { connection[offset] = 0xff }
                let noConnection = OmiBleFirmwareDiagnostics.parse(connection, timestampMs: 123)!
                for key in connectionKeys { precondition(noConnection[key] == nil) }
                // Zero latency and 1M PHY are real values, not unavailable.
                for offset in 30...37 { connection[offset] = 0 }
                connection[36] = 1; connection[37] = 1
                let zero = OmiBleFirmwareDiagnostics.parse(connection, timestampMs: 123)!
                precondition(zero["conn_latency"] as? NSNumber == 0 && zero["tx_phy"] as? NSNumber == 1)
                var unknown = Data(repeating: 0xff, count: 25)
                unknown[0] = 1
                let unknownParsed = OmiBleFirmwareDiagnostics.parse(unknown, timestampMs: 456)!
                for key in ["reset_cause_raw", "battery_mv", "charging", "mic_overrun_count", "ble_tx_drop_count", "storage_error_count"] {
                    precondition(unknownParsed[key] == nil)
                }
                precondition((try? PropertyListSerialization.data(fromPropertyList: [unknownParsed], format: .binary, options: 0)) != nil)
                defaults.set([unknownParsed], forKey: "ble_diagnostics_firmware_test")
                precondition((defaults.array(forKey: "ble_diagnostics_firmware_test") as? [[String: Any]])?.count == 1)
                precondition(OmiBleRssiDiagnostics.trend(samples: [], nowMs: 100_000) == "gap")
                precondition(OmiBleRssiDiagnostics.trend(samples: [(99_000, -55)], nowMs: 100_000) == "unknown")
                let samples: [(ts: Int64, rssi: Int64)] = [(90_000, -55), (99_000, -72)]
                precondition(OmiBleRssiDiagnostics.trend(samples: samples, nowMs: 100_000) == "fading")
                precondition(OmiBleRssiDiagnostics.ageMs(samples: samples, nowMs: 100_000) == 1_000)
                precondition(OmiBleRssiDiagnostics.ageMs(samples: [], nowMs: 100_000) == -1)
            }
        }
      SWIFT

      stdout, stderr, compile_status = Open3.capture3(
        'swiftc',
        '-parse-as-library',
        POLICY_SOURCE,
        harness,
        '-o',
        binary,
      )
      assert compile_status.success?, "swiftc failed:\n#{stdout}\n#{stderr}"

      stdout, stderr, run_status = Open3.capture3(binary)
      assert run_status.success?, "policy assertions failed:\n#{stdout}\n#{stderr}"
    end
  end
end


# Ring-read metadata shares this gate and its existing path trigger.
class RingReadDiagnosticsTest < Minitest::Test
  def test_disconnect_snapshot_and_plist_round_trip
    Dir.mktmpdir('ring-read-diagnostics') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'test')
      File.write(harness, <<~SWIFT)
        import Foundation
        @main struct Test {
            static func main() throws {
                let state = OmiRingReadDiagnostics()
                let characteristic = OmiRingReadDiagnostics.characteristic
                let read = Data([0x11] + Array(repeating: 0, count: 8))
                let begin = Data([0x05] + Array(repeating: 0, count: 12))
                let done = Data([0x04] + Array(repeating: 0, count: 9))
                precondition(state.disconnected("restored", now: 0).isEmpty)
                state.connected("a")
                state.requested("a", characteristic: characteristic, data: read)
                precondition(state.disconnected("a", now: 2)["ring_read_active"] as? Bool == false)
                state.connected("a")
                state.requested("a", characteristic: characteristic, data: Data([0x11] + Array(repeating: 0, count: 5)))
                state.received("a", characteristic: characteristic, data: Data([0x05] + Array(repeating: 0, count: 82)), now: 1)
                state.received("a", characteristic: characteristic, data: begin, now: 1)
                precondition(state.disconnected("a", now: 2)["ring_read_active"] as? Bool == false)
                state.connected("a")
                state.received("a", characteristic: "other", data: begin, now: 1)
                state.received("a", characteristic: characteristic, data: Data([0x05]), now: 1)
                precondition(state.disconnected("a", now: 2)["ring_read_active"] as? Bool == false)
                state.connected("a")
                state.requested("a", characteristic: characteristic, data: read)
                state.rejected("a", characteristic: characteristic, data: read)
                state.received("a", characteristic: characteristic, data: begin, now: 1)
                precondition(state.disconnected("a", now: 2)["ring_read_active"] as? Bool == false)
                state.connected("a")
                state.requested("a", characteristic: characteristic, data: read)
                var mismatch = begin
                mismatch[8] = 1
                state.received("a", characteristic: characteristic, data: mismatch, now: 1)
                precondition(state.disconnected("a", now: 2)["ring_read_active"] as? Bool == false)
                state.connected("a")
                state.connected("b")
                state.requested("a", characteristic: characteristic, data: read)
                state.received("a", characteristic: characteristic, data: begin, now: 1)
                state.received("a", characteristic: characteristic, data: Data([0x04]), now: 2)
                let snapshot = state.disconnected("a", now: 5.5)
                precondition(snapshot["ring_read_active"] as? Bool == true)
                precondition(snapshot["ring_read_age_ms"] as? Int64 == 4500)
                precondition(state.disconnected("b", now: 5.5)["ring_read_active"] as? Bool == false)
                precondition(state.disconnected("a", now: 6).isEmpty)
                state.connected("a")
                precondition(state.disconnected("a", now: 7)["ring_read_active"] as? Bool == false)
                for status in [UInt8(0), 1, 2, 6] {
                    state.requested("a", characteristic: characteristic, data: read)
                    state.received("a", characteristic: characteristic, data: begin, now: 8)
                    var terminal = done
                    terminal[1] = status
                    state.received("a", characteristic: characteristic, data: terminal, now: 9)
                    let stopped = state.disconnected("a", now: 10)
                    precondition(stopped["ring_read_active"] as? Bool == false)
                    precondition(stopped["ring_read_age_ms"] == nil)
                }
                state.requested("a", characteristic: characteristic, data: read)
                state.received("a", characteristic: characteristic, data: begin, now: 1)
                state.requested("a", characteristic: characteristic, data: read)
                state.received("a", characteristic: characteristic, data: begin, now: 3)
                precondition(state.disconnected("a", now: 5)["ring_read_age_ms"] as? Int64 == 2000)
                precondition(OmiRingReadDiagnostics().disconnected("a", now: 5).isEmpty)
                let bytes = try PropertyListSerialization.data(fromPropertyList: snapshot, format: .binary, options: 0)
                let stored = try PropertyListSerialization.propertyList(from: bytes, options: [], format: nil) as! [String: Any]
                precondition(stored["ring_read_active"] as? Bool == true)
                precondition(stored["ring_read_age_ms"] as? Int64 == 4500)
            }
        }
      SWIFT
      source = File.expand_path('../Runner/Ble/OmiBleEnergyPolicy.swift', __dir__)
      stdout, stderr, compile = Open3.capture3('swiftc', '-parse-as-library', source, harness, '-o', binary)
      assert compile.success?, "#{stdout}\n#{stderr}"
      stdout, stderr, run = Open3.capture3(binary)
      assert run.success?, "#{stdout}\n#{stderr}"
    end
  end
end

class RingReadRecoveryWindowTest < Minitest::Test
  def test_production_notification_guards_observe_ring_during_capture_cancel
    manager = File.read(File.expand_path('../Runner/Ble/OmiBleManager.swift', __dir__))
    start = manager.index('        // Handle notification')
    finish = manager.index('        let wasTransferring', start)
    guards = manager[start...finish].gsub('OmiRingReadDiagnostics.now()', 'testNow')
    Dir.mktmpdir('ring-recovery-window') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'test')
      File.write(harness, <<~SWIFT)
        import Foundation
        enum State { case connected, disconnected }
        final class Peripheral { var state = State.connected }
        struct Characteristic { let value: Data? }
        struct Recovery { let disconnected: Bool }
        @main struct Test {
            static func main() {
                let uuid = "a"
                let charUuid = OmiRingReadDiagnostics.characteristic
                let peripheral = Peripheral()
                var peripherals = [uuid: peripheral]
                let captureReconnects = [uuid: Recovery(disconnected: false)]
                let ringReadDiagnostics = OmiRingReadDiagnostics()
                var testNow = 1.0
                let read = Data([0x11] + Array(repeating: 0, count: 8))
                let begin = Data([0x05] + Array(repeating: 0, count: 12))
                let done = Data([0x04] + Array(repeating: 0, count: 9))
                func deliver(_ data: Data, error: Error? = nil) {
                    let characteristic = Characteristic(value: data)
        #{guards}
                }
                ringReadDiagnostics.connected(uuid)
                ringReadDiagnostics.requested(uuid, characteristic: charUuid, data: read)
                deliver(begin)
                let active = ringReadDiagnostics.disconnected(uuid, now: 5.5)
                precondition(active["ring_read_active"] as? Bool == true)
                precondition(active["ring_read_age_ms"] as? Int64 == 4500)
                ringReadDiagnostics.connected(uuid)
                ringReadDiagnostics.requested(uuid, characteristic: charUuid, data: read)
                deliver(begin)
                testNow = 2
                deliver(done)
                precondition(ringReadDiagnostics.disconnected(uuid, now: 3)["ring_read_active"] as? Bool == false)
                ringReadDiagnostics.connected(uuid)
                ringReadDiagnostics.requested(uuid, characteristic: charUuid, data: read)
                deliver(begin, error: NSError(domain: "test", code: 1))
                precondition(ringReadDiagnostics.disconnected(uuid, now: 3)["ring_read_active"] as? Bool == false)
                ringReadDiagnostics.connected(uuid)
                ringReadDiagnostics.requested(uuid, characteristic: charUuid, data: read)
                peripherals[uuid] = Peripheral()
                deliver(begin)
                precondition(ringReadDiagnostics.disconnected(uuid, now: 3)["ring_read_active"] as? Bool == false)
            }
        }
      SWIFT
      source = File.expand_path('../Runner/Ble/OmiBleEnergyPolicy.swift', __dir__)
      stdout, stderr, compile = Open3.capture3('swiftc', '-parse-as-library', source, harness, '-o', binary)
      assert compile.success?, "#{stdout}\n#{stderr}"
      stdout, stderr, run = Open3.capture3(binary)
      assert run.success?, "#{stdout}\n#{stderr}"
    end
  end
end
