# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class OmiBleEnergyPolicyTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  POLICY_SOURCE = File.join(IOS_ROOT, 'Runner', 'Ble', 'OmiBleEnergyPolicy.swift')

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
                precondition(OmiBleFirmwareDiagnostics.parse(Data(repeating: 0, count: 24), timestampMs: 1) == nil)
                precondition(OmiBleFirmwareDiagnostics.parse(Data(repeating: 0, count: 25), timestampMs: 1) == nil)
                var diagnostic = Data(repeating: 0, count: 30)
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
