# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class SyncTransferBackgroundLeaseTest < Minitest::Test
  SOURCE = File.expand_path('../Runner/SyncTransferBackgroundLease.swift', __dir__)

  def test_expiration_and_invalid_creation_both_allow_fresh_reacquisition
    Dir.mktmpdir('omi-sync-transfer-lease') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'sync-transfer-lease-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct Harness {
          static func main() {
            var starts = 0
            var ends = 0
            var notifications: [String] = []
            var expiration: (() -> Void)?
            var admit = true
            let lease = SyncTransferBackgroundLease(
              begin: { callback in
                starts += 1
                expiration = callback
                return admit
              },
              end: { ends += 1 },
              notifyExpired: { notifications.append($0) }
            )

            lease.start()
            lease.start()
            precondition(starts == 1 && lease.isActive)
            expiration!()
            precondition(ends == 1 && notifications == ["expired"] && !lease.isActive)

            lease.start()
            precondition(starts == 2 && lease.isActive, "expiration must permit a fresh native task")
            lease.stop()
            precondition(ends == 2 && !lease.isActive)

            admit = false
            lease.start()
            precondition(starts == 3 && notifications == ["expired", "invalid"] && !lease.isActive)

            admit = true
            lease.start()
            precondition(starts == 4 && lease.isActive, ".invalid creation must not poison reacquisition")
            lease.stop()
            precondition(ends == 3)
          }
        }
      SWIFT

      stdout, stderr, compile_status = Open3.capture3(
        'swiftc', '-parse-as-library', SOURCE, harness, '-o', binary
      )
      assert compile_status.success?, "compile failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, run_status = Open3.capture3(binary)
      assert run_status.success?, "lease behavior failed:\n#{stdout}\n#{stderr}"
    end
  end
end
