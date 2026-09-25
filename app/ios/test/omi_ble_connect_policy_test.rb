# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

# FC-already-satisfied-request-as-noop: an iOS relaunch restores a pendant that
# is already connected before Flutter listens. connectPeripheral used to return
# early for it, so Flutter never saw onDeviceReady and showed "disconnected".
class OmiBleConnectPolicyTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  POLICY_SOURCE = File.join(IOS_ROOT, 'Runner', 'Ble', 'OmiBleConnectPolicy.swift')

  def test_already_connected_request_redelivers_readiness
    Dir.mktmpdir('omi-ble-connect-policy') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'omi-ble-connect-policy-test')
      File.write(harness, <<~SWIFT)
        @main
        struct OmiBleConnectPolicyTestHarness {
            static func main() {
                typealias P = OmiBleConnectPolicy
                // Restored and fully discovered: replay the ready event now.
                precondition(P.action(link: .connected, servicesDiscovered: true) == .announceReady)
                // Restored before discovery finished: discovery ends in the ready event.
                precondition(P.action(link: .connected, servicesDiscovered: false) == .discoverServices)
                // Not yet connected: connect, and didConnect announces.
                precondition(P.action(link: .disconnected, servicesDiscovered: false) == .connect)
                precondition(P.action(link: .disconnected, servicesDiscovered: true) == .connect)
                precondition(P.action(link: .connecting, servicesDiscovered: false) == .connect)
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

  def test_manager_routes_connect_requests_through_the_policy
    manager = File.read(File.join(IOS_ROOT, 'Runner', 'Ble', 'OmiBleManager.swift'))
    body = manager[/func connectPeripheral\(uuid: String\) \{.*?\n    \}\n/m]
    refute_nil body, 'connectPeripheral not found'
    assert_includes body, 'OmiBleConnectPolicy.action('
    refute_match(/already connected, skipping/, body)
  end
end
