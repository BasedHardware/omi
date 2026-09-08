# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class SpeechDeadlineTest < Minitest::Test
  SOURCE = File.expand_path('../Runner/SpeechDeadline.swift', __dir__)

  def test_deadline_returns_without_waiting_for_shared_work_and_owns_cleanup
    Dir.mktmpdir('omi-speech-deadline') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'speech-deadline-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct Harness {
            @MainActor
            static func main() async {
                let success: Int = await SpeechDeadline.run(seconds: 60, operation: { 7 }, onTimeout: {
                    preconditionFailure("Successful work must cancel the deadline")
                })
                precondition(success == 7)

                var release: CheckedContinuation<Int, Never>?
                let shared = Task { @MainActor in
                    await withCheckedContinuation { release = $0 }
                }
                let timeout = await SpeechDeadline.run(seconds: 0, operation: {
                    await shared.value
                }, onTimeout: { -1 })
                precondition(timeout == -1)
                precondition(!shared.isCancelled, "An availability timeout must not cancel a shared download")
                release!.resume(returning: 9)
                let downloaded = await shared.value
                precondition(downloaded == 9)

                var finishRecognition: CheckedContinuation<Int, Never>?
                var cleanupFinished = false
                let result = await SpeechDeadline.run(seconds: 0, operation: {
                    await withCheckedContinuation { finishRecognition = $0 }
                }, onTimeout: {
                    // Recognition answers during cleanup. It must neither win
                    // completion nor allow a retry before cleanup has finished.
                    finishRecognition!.resume(returning: 7)
                    await Task.yield()
                    cleanupFinished = true
                    return -2
                })
                precondition(result == -2 && cleanupFinished)
                print("speech deadline: success, shared download, late result, cleanup ordering passed")
            }
        }
      SWIFT
      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library', SOURCE, harness, '-o', binary)
      assert status.success?, "compile failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(binary)
      assert status.success?, "deadline behavior failed:\n#{stdout}\n#{stderr}"
    end
  end
end
