# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class OmiBlePairingPolicyTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  POLICY_SOURCE = File.join(IOS_ROOT, 'Runner', 'Ble', 'OmiBlePairingPolicy.swift')

  def test_detects_peer_removed_pairing_information
    Dir.mktmpdir('omi-ble-pairing-policy') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'omi-ble-pairing-policy-test')
      File.write(harness, <<~SWIFT)
        import Foundation
        import CoreBluetooth

        @main
        struct OmiBlePairingPolicyTestHarness {
            static func main() {
                let code = CBError.Code.peerRemovedPairingInformation.rawValue
                let cbDomain = CBError.errorDomain
                let cbError = NSError(domain: cbDomain, code: code, userInfo: nil)
                precondition(OmiBlePairingPolicy.isPairingLost(cbError))
                precondition(OmiBlePairingPolicy.isPairingLost(
                    NSError(domain: "CBErrorDomain", code: code, userInfo: nil)
                ))
                let wrapped = NSError(
                    domain: "SomeWrapper",
                    code: 1,
                    userInfo: [NSUnderlyingErrorKey: cbError]
                )
                precondition(OmiBlePairingPolicy.isPairingLost(wrapped))
                precondition(!OmiBlePairingPolicy.isPairingLost(
                    NSError(domain: cbDomain, code: CBError.Code.connectionTimeout.rawValue, userInfo: nil)
                ))
                precondition(!OmiBlePairingPolicy.isPairingLost(nil))
            }
        }
      SWIFT

      stdout, stderr, compile_status = Open3.capture3(
        'swiftc',
        '-parse-as-library',
        POLICY_SOURCE,
        harness,
        '-o',
        binary
      )
      assert compile_status.success?, "compile failed: #{stderr}\n#{stdout}"

      stdout, stderr, run_status = Open3.capture3(binary)
      assert run_status.success?, "run failed: #{stderr}\n#{stdout}"
    end
  end
end
