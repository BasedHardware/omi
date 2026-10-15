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
                    timestampOf: { $0["timestamp"] as? Int64 ?? 0 }
                )
            }

            mutating func recover(_ timestamp: Int64, hadConnection: Bool = true) -> [[String: Any]]? {
                // Use the native persisted shape, including its plist round trip.
                let bytes = try! PropertyListSerialization.data(fromPropertyList: events, format: .binary, options: 0)
                let stored = try! PropertyListSerialization.propertyList(from: bytes, options: [], format: nil) as! [[String: Any]]
                return diagnostics.backfilledHistory(
                    stored, nowMs: timestamp, hadConnection: hadConnection,
                    timestampOf: { $0["timestamp"] as? Int64 ?? 0 },
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
