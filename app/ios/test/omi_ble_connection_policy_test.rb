# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

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
