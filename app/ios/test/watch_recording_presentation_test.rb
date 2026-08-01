# frozen_string_literal: true

require 'fileutils'
require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class WatchRecordingPresentationTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  PRODUCTION_SOURCE = File.join(IOS_ROOT, 'omiWatchApp', 'RecordingPresentation.swift')
  CONTENT_VIEW_SOURCE = File.join(IOS_ROOT, 'omiWatchApp', 'ContentView.swift')
  APP_SOURCE = File.join(IOS_ROOT, 'omiWatchApp', 'omiwatchApp.swift')

  def test_animation_boundary_and_elapsed_time_use_the_original_recording_start
    Dir.mktmpdir('watch-recording-presentation') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'watch-recording-presentation-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        let startedAt = Date(timeIntervalSinceReferenceDate: 1_000)

        precondition(
            RecordingPresentation.animationTimeRemaining(
                startedAt: startedAt,
                now: startedAt.addingTimeInterval(4.999)
            ) > 0
        )
        precondition(
            RecordingPresentation.animationTimeRemaining(
                startedAt: startedAt,
                now: startedAt.addingTimeInterval(5)
            ) == 0
        )
        precondition(
            RecordingPresentation.animationTimeRemaining(
                startedAt: startedAt,
                now: startedAt.addingTimeInterval(3_661)
            ) == 0
        )
        precondition(
            RecordingPresentation.elapsedTime(
                startedAt: startedAt,
                now: startedAt.addingTimeInterval(3_661)
            ) == 3_661
        )
        precondition(
            RecordingPresentation.elapsedTime(
                startedAt: startedAt,
                now: startedAt.addingTimeInterval(-1)
            ) == 0
        )
      SWIFT

      stdout, stderr, compile_status = Open3.capture3(
        'swiftc',
        PRODUCTION_SOURCE,
        harness,
        '-o',
        binary,
      )
      assert compile_status.success?, "swiftc failed:\n#{stdout}\n#{stderr}"

      stdout, stderr, run_status = Open3.capture3(binary)
      assert run_status.success?, "timing assertions failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_static_timer_view_typechecks_with_the_production_timing_model
    Dir.mktmpdir('watch-recording-view') do |directory|
      view_model_stub = File.join(directory, 'WatchAudioRecorderViewModel.swift')
      File.write(view_model_stub, <<~SWIFT)
        import Combine
        import Foundation

        @MainActor
        final class WatchAudioRecorderViewModel: ObservableObject {
            @Published var isRecording = false
            @Published private(set) var recordingStartedAt: Date?

            func startRecording() {}
            func stopRecording() {}
        }
      SWIFT

      stdout, stderr, status = Open3.capture3(
        'swiftc',
        '-parse-as-library',
        '-typecheck',
        PRODUCTION_SOURCE,
        view_model_stub,
        CONTENT_VIEW_SOURCE,
        APP_SOURCE,
      )
      assert status.success?, "watch recording view failed to typecheck:\n#{stdout}\n#{stderr}"
    end
  end
end
