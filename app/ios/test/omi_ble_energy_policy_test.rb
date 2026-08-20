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
                precondition(!OmiBleEnergyPolicy.shouldPollRssi(
                    diagnosticsEnabled: false,
                    peripheralConnected: true
                ))
                precondition(!OmiBleEnergyPolicy.shouldPollRssi(
                    diagnosticsEnabled: true,
                    peripheralConnected: false
                ))
                precondition(OmiBleEnergyPolicy.shouldPollRssi(
                    diagnosticsEnabled: true,
                    peripheralConnected: true
                ))

                let minute: Int64 = 60_000
                precondition(OmiBleEnergyPolicy.shouldPersistBatteryReading(
                    previousLevel: nil,
                    previousTimestampMs: nil,
                    level: 80,
                    nowMs: 0
                ))
                precondition(!OmiBleEnergyPolicy.shouldPersistBatteryReading(
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
                    level: 79,
                    nowMs: 15 * minute
                ))
                precondition(OmiBleEnergyPolicy.shouldPersistBatteryReading(
                    previousLevel: 20,
                    previousTimestampMs: 0,
                    level: 19,
                    nowMs: minute
                ))
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
