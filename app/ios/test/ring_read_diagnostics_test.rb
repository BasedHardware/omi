# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

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
                let begin = Data([0x05] + Array(repeating: 0, count: 12))
                let done = Data([0x04] + Array(repeating: 0, count: 9))
                precondition(state.disconnected("restored", now: 0).isEmpty)
                state.connected("a")
                state.received("a", characteristic: characteristic, data: Data([0x11]), now: 1)
                precondition(state.disconnected("a", now: 2)["ring_read_active"] as? Bool == false)
                state.connected("a")
                state.received("a", characteristic: "other", data: begin, now: 1)
                state.received("a", characteristic: characteristic, data: Data([0x05]), now: 1)
                precondition(state.disconnected("a", now: 2)["ring_read_active"] as? Bool == false)
                state.connected("a")
                state.connected("b")
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
                    state.received("a", characteristic: characteristic, data: begin, now: 8)
                    var terminal = done
                    terminal[1] = status
                    state.received("a", characteristic: characteristic, data: terminal, now: 9)
                    let stopped = state.disconnected("a", now: 10)
                    precondition(stopped["ring_read_active"] as? Bool == false)
                    precondition(stopped["ring_read_age_ms"] == nil)
                }
                state.received("a", characteristic: characteristic, data: begin, now: 1)
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
