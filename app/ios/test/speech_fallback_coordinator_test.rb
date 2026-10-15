require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class SpeechFallbackCoordinatorTest < Minitest::Test
  def test_actual_coordinator_install_recognition_permission_and_rollback_paths
    Dir.mktmpdir('speech-coordinator') do |dir|
      source = File.expand_path('../Runner/SpeechDeadline.swift', __dir__)
      harness = File.join(dir, 'Harness.swift')
      File.write(harness, <<~SWIFT)
        import Foundation
        @main struct Harness {
          @MainActor static func main() async throws {
            var analyzerAvailable = true
            var legacyStatus = "permission_denied"
            var failRecognition = false
            var analyzerCalls = 0
            var legacyCalls = 0
            enum Fault: Error { case recognition }
            let coordinator = SpeechFallbackCoordinator(analyzerReady: { analyzerAvailable },
              legacyReady: { LocalSpeechReadiness(engine: "sfspeech", status: legacyStatus) },
              analyze: { analyzerCalls += 1; if failRecognition { throw Fault.recognition }; return "new engine" },
              legacy: { legacyCalls += 1; return "legacy engine" })
            let ready = await coordinator.readiness(preferAnalyzer: true)
            precondition(ready.ready && ready.engine == "speech_analyzer")
            let newText = try await coordinator.transcribe(preferAnalyzer: true)
            precondition(newText == "new engine" && legacyCalls == 0)
            // Actual rollback: denied permission must not execute legacy or claim readiness.
            let denied = await coordinator.readiness(preferAnalyzer: false)
            precondition(!denied.ready && denied.status == "permission_denied")
            do { _ = try await coordinator.transcribe(preferAnalyzer: false); preconditionFailure() }
            catch let error as LocalSpeechUnavailable { precondition(error.readiness.status == "permission_denied") }
            precondition(legacyCalls == 0 && analyzerCalls == 1)
            // Install/hardware failure checks the usable fallback and executes it.
            analyzerAvailable = false; legacyStatus = "ready"
            let oldText = try await coordinator.transcribe(preferAnalyzer: true)
            precondition(oldText == "legacy engine" && legacyCalls == 1)
            // A native recognition error takes the same verified fallback.
            analyzerAvailable = true; failRecognition = true
            let recovered = try await coordinator.transcribe(preferAnalyzer: true)
            precondition(recovered == "legacy engine" && legacyCalls == 2)
            // Neither engine works: actionable unavailability, no false empty success.
            legacyStatus = "unavailable"
            do { _ = try await coordinator.transcribe(preferAnalyzer: true); preconditionFailure() }
            catch let error as LocalSpeechUnavailable { precondition(error.readiness.status == "unavailable") }
            precondition(legacyCalls == 2)
            print("fallback behavioral paths passed")
          }
        }
      SWIFT
      output, status = Open3.capture2e('swiftc', '-parse-as-library', source, harness, '-o', File.join(dir, 'test'))
      assert status.success?, output
      output, status = Open3.capture2e(File.join(dir, 'test'))
      assert status.success?, output
    end
  end
end
