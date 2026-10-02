# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'
require_relative 'omi_capture_health_test'

class OmiBleConnectionPolicyTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  POLICY_SOURCE = File.join(IOS_ROOT, 'Runner', 'Ble', 'OmiBleConnectionPolicy.swift')

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
