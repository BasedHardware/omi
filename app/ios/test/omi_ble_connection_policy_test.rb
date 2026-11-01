# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'
class OmiBleConnectionPolicyTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  POLICY_SOURCE = File.join(IOS_ROOT, 'Runner', 'Ble', 'OmiBleConnectionPolicy.swift')

  def test_saved_reconnect_manager_callbacks_with_suspended_timers
    manager = File.read(File.join(IOS_ROOT, 'Runner/Ble/OmiBleManager.swift'))
    signatures = [
      'private func scheduleSavedRetry(', 'private func setupRetryRemaining(',
      'private func issueConnect(', 'private func reconcileSavedReconnect(',
      'private func runSavedScanWindow(', 'private func endSavedScan(',
      'private func updateReconnectScan(', 'private func reportDiscoveryFailure(',
      'private func recoverCaptureConnection(', 'func disconnectPeripheral(',
      'func centralManager(_ central: CBCentralManager, didDiscover ',
      'func centralManager(_ central: CBCentralManager, didFailToConnect ',
      'func centralManager(_ central: CBCentralManager, didDisconnectPeripheral ',
    ]
    methods = signatures.map do |signature|
      start = manager.index("    #{signature}")
      raise "missing production method #{signature}" unless start
      finish = manager.index("\n    }", start) + "\n    }".length
      manager[start...finish]
    end.join("\n")
    # Replace only radio/scheduler boundaries, preserving production control flow.
    methods = methods.gsub('private func', 'func')
      .gsub(/\bCBCentralManager\b/, 'TestCentral').gsub(/\bCBPeripheral\b/, 'TestPeripheral')
      .gsub('DispatchWorkItem', 'TestWorkItem')
      .gsub('DispatchQueue.main.asyncAfter', 'self.queue.asyncAfter')
      .gsub('ProcessInfo.processInfo.systemUptime', 'self.queue.now')
      .gsub('.now()', 'self.queue.now').gsub('.milliseconds(200)', '0.2')
    template = File.read(File.join(__dir__, 'omi_saved_reconnect_manager_test.swift'))
    harness = template.sub('    // Production methods are inserted here by the Ruby runner.', methods)
    Dir.mktmpdir('omi-reconnect-manager') do |directory|
      source = File.join(directory, 'harness.swift')
      binary = File.join(directory, 'test')
      File.write(source, harness)
      stdout, stderr, compile = Open3.capture3('swiftc', '-parse-as-library', POLICY_SOURCE,
        File.join(IOS_ROOT, 'Runner/SafeFoundationSinks.swift'),
        File.join(IOS_ROOT, 'Runner/Ble/OmiCaptureHealth.swift'), source, '-o', binary)
      assert compile.success?, "manager harness compile failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, run = Open3.capture3(binary)
      assert run.success?, "manager callback assertions failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_pairing_recovery_classifies_only_authentication_and_encryption_att_errors
    Dir.mktmpdir('omi-ble-connection-policy') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'omi-ble-connection-policy-test')
      File.write(harness, <<~SWIFT)
        import CoreBluetooth
        import Foundation

        @main
        struct OmiBleConnectionPolicyTestHarness {
            static func main() {
                let suite = "omi-reconnect-test-" + UUID().uuidString
                let defaults = UserDefaults(suiteName: suite)!
                defer { defaults.removePersistentDomain(forName: suite) }
                let saved = "00000000-0000-0000-0000-000000000001"
                let other = "00000000-0000-0000-0000-000000000002"
                var intent = OmiSavedReconnectIntent(defaults: defaults)
                intent.configure(saved, enabled: true)
                // A remote disconnect owes a request immediately, irrespective of capture.
                precondition(intent.action(saved, poweredOn: true, state: .disconnected) == .connect)
                // A cancelled capture-recovery continuation cannot turn native
                // transport release into a persisted manual disconnect.
                precondition(intent.releaseTransport(saved))
                intent = OmiSavedReconnectIntent(defaults: defaults)
                precondition(intent.action(saved, poweredOn: true, state: .connecting) == .keepPending)
                precondition(!intent.blocked.contains(saved))
                // applicationWillTerminate cleanup must preserve saved OS requests
                // without turning termination into a durable manual disconnect.
                precondition(intent.terminationTargets([saved, other]) == [other])
                // Kill/relaunch without Flutter or a restored peripheral: scan until found.
                intent = OmiSavedReconnectIntent(defaults: defaults)
                precondition(intent.action(saved, poweredOn: true, state: nil) == .scan)
                precondition(intent.action(saved, poweredOn: false, state: nil) == .waitForAdapter)
                // State restoration retains the pending request rather than timing it out.
                for _ in 0..<1000 {
                    precondition(intent.action(saved, poweredOn: true, state: .connecting) == .keepPending)
                }
                precondition(intent.action(saved, poweredOn: true, state: .disconnecting) == .keepPending)
                precondition(intent.action(saved, poweredOn: true, state: .connected) == .connected)
                precondition(intent.action(other, poweredOn: true, state: .disconnected) == .suppressed)
                // A capture health denial is not a change to native reconnect intent.
                let health = OmiCaptureHealth(persist: { _ in true })
                health.authorize(true, now: 100)
                health.disconnected(recovering: false, now: 101)
                health.authorize(false, now: 102)
                precondition(health.reason == "capture_denied")
                precondition(intent.action(saved, poweredOn: true, state: .disconnected) == .connect)
                // Explicit suppression survives a new process and stale restoration.
                intent.configure(saved, enabled: false)
                precondition(!intent.releaseTransport(saved))
                precondition(intent.terminationTargets([saved, other]) == [saved, other])
                intent = OmiSavedReconnectIntent(defaults: defaults)
                precondition(intent.action(saved, poweredOn: true, state: .connecting) == .suppressed)
                precondition(intent.action(saved, poweredOn: true, state: .connected) == .suppressed)
                intent.configure(saved, enabled: true)
                precondition(intent.action(saved, poweredOn: true, state: .disconnected) == .suppressed)
                intent.resume(saved) // Only explicit manageDevice clears the native user block.
                precondition(intent.action(saved, poweredOn: true, state: .disconnected) == .connect)
                intent.configure(saved, enabled: false)
                intent.configure(other, enabled: true)
                intent = OmiSavedReconnectIntent(defaults: defaults)
                precondition(intent.action(saved, poweredOn: true, state: nil) == .suppressed)
                precondition(intent.action(other, poweredOn: true, state: nil) == .scan)

                var telemetry = OmiSavedReconnectTelemetry()
                precondition(telemetry.admit("attempted"))
                for _ in 0..<10000 { precondition(!telemetry.admit("attempted")) }
                for i in 0..<6 { precondition(telemetry.admit("failed:" + String(i))) }
                precondition(!telemetry.admit("failed:extra"))
                precondition(telemetry.admit("connected"))
                precondition(!telemetry.admit("connected"))

                precondition(OmiBleConnectionPolicy.savedRetryAllowed(saved: true, everConnected: false, manual: false, pairingLost: false))
                precondition(!OmiBleConnectionPolicy.savedRetryAllowed(saved: false, everConnected: false, manual: false, pairingLost: false))
                precondition(!OmiBleConnectionPolicy.savedRetryAllowed(saved: true, everConnected: true, manual: true, pairingLost: false))
                precondition(!OmiBleConnectionPolicy.savedRetryAllowed(saved: true, everConnected: true, manual: false, pairingLost: true))
                precondition(OmiBleConnectionPolicy.savedRetryDelay(attempt: 1) == 1)
                precondition(OmiBleConnectionPolicy.savedRetryDelay(attempt: 1000) == 60)
                precondition(OmiBleConnectionPolicy.readyRecoveryAction(
                    peripheralState: .connected,
                    nativeReady: true,
                    hasCompleteServices: true,
                    discoveryInFlight: false
                ) == .replayReady)
                precondition(OmiBleConnectionPolicy.readyRecoveryAction(
                    peripheralState: .connected,
                    nativeReady: false,
                    hasCompleteServices: true,
                    discoveryInFlight: false
                ) == .hydrateReady)
                precondition(OmiBleConnectionPolicy.readyRecoveryAction(
                    peripheralState: .connected,
                    nativeReady: false,
                    hasCompleteServices: true,
                    discoveryInFlight: true
                ) == .hydrateReady)
                precondition(OmiBleConnectionPolicy.readyRecoveryAction(
                    peripheralState: .connected,
                    nativeReady: true,
                    hasCompleteServices: false,
                    discoveryInFlight: false
                ) == .discoverServices)
                precondition(OmiBleConnectionPolicy.readyRecoveryAction(
                    peripheralState: .connected,
                    nativeReady: false,
                    hasCompleteServices: false,
                    discoveryInFlight: true
                ) == .awaitDiscovery)
                precondition(OmiBleConnectionPolicy.readyRecoveryAction(
                    peripheralState: .disconnected,
                    nativeReady: true,
                    hasCompleteServices: true,
                    discoveryInFlight: true
                ) == .connect)
                precondition(OmiBleConnectionPolicy.discoveryIsActive(startedAt: 100, now: 114))
                precondition(!OmiBleConnectionPolicy.discoveryIsActive(startedAt: 100, now: 115))
                precondition(OmiBleConnectionPolicy.discoveryFailureAction(
                    peripheralState: .connected, nativeReady: false, requestPending: true, retries: 0
                ) == .retry)
                precondition(OmiBleConnectionPolicy.discoveryFailureAction(
                    peripheralState: .connected, nativeReady: false, requestPending: true, retries: 1
                ) == .fail)
                precondition(OmiBleConnectionPolicy.discoveryFailureAction(
                    peripheralState: .connected, nativeReady: false, requestPending: false, retries: 0
                ) == .ignore)
                precondition(OmiBleConnectionPolicy.discoveryFailureAction(
                    peripheralState: .disconnected, nativeReady: false, requestPending: true, retries: 0
                ) == .ignore)

                // A cached live link is never reused during a physical capture reset.
                precondition(OmiBleConnectionPolicy.readyRecoveryAction(
                    peripheralState: .connected, nativeReady: true, hasCompleteServices: true,
                    discoveryInFlight: false, captureResetInProgress: true
                ) == .awaitCaptureReset)
                precondition(!OmiBleConnectionPolicy.captureResetCanConnect(
                    disconnectObserved: false, alreadyReconnected: false, authorized: true, pairingLost: false
                ))
                precondition(OmiBleConnectionPolicy.captureResetCanConnect(
                    disconnectObserved: true, alreadyReconnected: false, authorized: true, pairingLost: false
                ))
                precondition(!OmiBleConnectionPolicy.captureResetCanConnect(
                    disconnectObserved: true, alreadyReconnected: true, authorized: true, pairingLost: false
                ))
                precondition(!OmiBleConnectionPolicy.captureResetCanConnect(
                    disconnectObserved: true, alreadyReconnected: false, authorized: false, pairingLost: false
                ))
                precondition(!OmiBleConnectionPolicy.captureResetCanConnect(
                    disconnectObserved: true, alreadyReconnected: false, authorized: true, pairingLost: true
                ))
                for source in ["restore", "replay", "hydrate"] {
                    precondition(!OmiBleConnectionPolicy.captureResetReady(
                        disconnectObserved: true, freshConnection: true, source: source
                    ))
                }
                precondition(!OmiBleConnectionPolicy.captureResetReady(
                    disconnectObserved: false, freshConnection: true, source: "discovery"
                ))
                precondition(!OmiBleConnectionPolicy.captureResetReady(
                    disconnectObserved: true, freshConnection: false, source: "discovery"
                ))
                precondition(OmiBleConnectionPolicy.captureResetReady(
                    disconnectObserved: true, freshConnection: true, source: "discovery"
                ))

                let recoveryCodes = [
                    CBATTError.insufficientAuthentication.rawValue,
                    CBATTError.insufficientAuthorization.rawValue,
                    CBATTError.insufficientEncryptionKeySize.rawValue,
                    CBATTError.insufficientEncryption.rawValue,
                ]
                for code in recoveryCodes {
                    let error = NSError(domain: CBATTErrorDomain, code: code)
                    precondition(OmiBleConnectionPolicy.requiresPairingRecovery(error))
                }

                precondition(!OmiBleConnectionPolicy.requiresPairingRecovery(nil))
                precondition(!OmiBleConnectionPolicy.requiresPairingRecovery(
                    NSError(domain: CBATTErrorDomain, code: CBATTError.attributeNotFound.rawValue)
                ))
                precondition(!OmiBleConnectionPolicy.requiresPairingRecovery(
                    NSError(domain: "unrelated", code: CBATTError.insufficientAuthentication.rawValue)
                ))
            }
        }
      SWIFT

      stdout, stderr, compile_status = Open3.capture3(
        'swiftc',
        '-parse-as-library',
        POLICY_SOURCE,
        File.join(IOS_ROOT, 'Runner', 'SafeFoundationSinks.swift'),
        File.join(IOS_ROOT, 'Runner', 'Ble', 'OmiCaptureHealth.swift'),
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
