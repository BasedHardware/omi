# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class WatchAudioChunkRelayTest < Minitest::Test
  RUNNER_ROOT = File.expand_path('../Runner', __dir__)
  RELAY_SOURCE = File.join(RUNNER_ROOT, 'WatchAudioChunkRelay.swift')
  APP_DELEGATE_SOURCE = File.join(RUNNER_ROOT, 'AppDelegate.swift')

  def test_every_watch_chunk_is_forwarded_as_it_arrives_and_the_end_marker_is_dropped
    Dir.mktmpdir('omi-watch-chunk-relay') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'watch-chunk-relay-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct Harness {
            static func main() {
                // One Watch session: 1.5 s chunks of 16 kHz 16-bit mono, then the empty end marker.
                let chunks = (0..<40).map { index in Data(repeating: UInt8(index), count: 48_000) }
                var forwardedBytes = 0
                for chunk in chunks {
                    guard let payload = WatchAudioChunkRelay.flutterPayload(for: chunk) else {
                        preconditionFailure("An audio chunk must reach Flutter when it arrives")
                    }
                    precondition(payload.prefix(3) == Data([0x00, 0x00, 0x00]), "Flutter strips 3 header bytes")
                    precondition(payload.dropFirst(3) == chunk, "Chunk bytes must pass through unchanged")
                    forwardedBytes += payload.count - 3
                }
                precondition(forwardedBytes == chunks.reduce(0) { $0 + $1.count }, "No audio may be held back")
                precondition(WatchAudioChunkRelay.flutterPayload(for: Data()) == nil, "The end marker carries no audio")
                print("ok")
            }
        }
      SWIFT

      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library', RELAY_SOURCE, harness, '-o', binary)
      assert status.success?, "compile failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(binary)
      assert status.success?, "relay contract failed:\n#{stdout}\n#{stderr}"
      assert_equal "ok\n", stdout
    end
  end

  def test_app_delegate_forwards_through_the_relay_without_keeping_the_recording
    source = File.read(APP_DELEGATE_SOURCE, encoding: 'UTF-8')
    assert source.include?('WatchAudioChunkRelay.flutterPayload(for: audioChunk)'), 'Watch chunks must go through the relay'
    refute source.match?(/audioChunks\s*[:\[]/), 'the iPhone must not store Watch chunks (#20479)'
  end
end
