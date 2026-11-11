# frozen_string_literal: true

require 'json'
require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class WatchRecordingPresentationTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)
  WATCH_ROOT = File.join(IOS_ROOT, 'omiWatchApp')
  PRESENTATION_SOURCE = File.join(WATCH_ROOT, 'RecordingPresentation.swift')
  RECORDER_CONTRACT_SOURCE = File.join(WATCH_ROOT, 'WatchRecorderControlling.swift')
  VIEW_MODEL_SOURCE = File.join(WATCH_ROOT, 'WatchAudioRecorderViewModel.swift')
  CONTENT_VIEW_SOURCE = File.join(WATCH_ROOT, 'ContentView.swift')
  LOCALIZATION_CATALOG = File.join(WATCH_ROOT, 'Localizable.xcstrings')
  PROJECT_FILE = File.join(IOS_ROOT, 'Runner.xcodeproj', 'project.pbxproj')

  ACCESSIBILITY_KEYS = %w[
    watch.accessibility.elapsedRecordingTime
    watch.accessibility.recordingInProgress
    watch.accessibility.startRecording
    watch.accessibility.stopRecording
  ].freeze

  def test_actual_presentation_controller_removes_the_ripple_after_five_seconds
    Dir.mktmpdir('watch-recording-presentation') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'watch-recording-presentation-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @MainActor
        final class ControlledSleeper {
            private(set) var requestedDuration: TimeInterval?
            private var continuation: CheckedContinuation<Void, Never>?

            var isWaiting: Bool { continuation != nil }

            func sleep(for duration: TimeInterval) async throws {
                requestedDuration = duration
                await withCheckedContinuation { continuation = $0 }
            }

            func resume() {
                continuation?.resume()
                continuation = nil
            }
        }

        @main
        struct RecordingPresentationTestHarness {
            @MainActor
            static func main() async {
                let startedAt = Date(timeIntervalSinceReferenceDate: 1_000)
                let sleeper = ControlledSleeper()
                let controller = RecordingPresentationController(
                    now: { startedAt },
                    sleep: { duration in try await sleeper.sleep(for: duration) }
                )

                let transition = Task { @MainActor in
                    await controller.update(isRecording: true, startedAt: startedAt)
                }

                while !sleeper.isWaiting {
                    await Task.yield()
                }

                precondition(controller.phase == .animating)
                precondition(controller.phase.showsRecordingRipple)
                precondition(sleeper.requestedDuration == 5)

                sleeper.resume()
                await transition.value

                precondition(controller.phase == .elapsedTimer)
                precondition(!controller.phase.showsRecordingRipple)
                precondition(
                    RecordingPresentation.elapsedTime(
                        startedAt: startedAt,
                        now: startedAt.addingTimeInterval(3_661)
                    ) == 3_661
                )

                let resumedController = RecordingPresentationController(
                    now: { startedAt.addingTimeInterval(6) },
                    sleep: { _ in preconditionFailure("an elapsed recording must not restart the animation") }
                )
                await resumedController.update(isRecording: true, startedAt: startedAt)
                precondition(resumedController.phase == .elapsedTimer)
                precondition(!resumedController.phase.showsRecordingRipple)

                await resumedController.update(isRecording: false, startedAt: nil)
                precondition(resumedController.phase == .idle)
            }
        }
      SWIFT

      compile_and_run(PRESENTATION_SOURCE, harness, binary: binary)
    end
  end

  def test_view_typechecks_against_the_shared_production_recorder_contract
    Dir.mktmpdir('watch-recording-view') do |directory|
      test_recorder = File.join(directory, 'TestWatchRecorder.swift')
      File.write(test_recorder, <<~SWIFT)
        import Combine
        import Foundation

        @MainActor
        final class TestWatchRecorder: WatchRecorderControlling {
            @Published var isRecording = false
            @Published var recordingStartedAt: Date?

            func startRecording() {}
            func stopRecording() {}
        }
      SWIFT

      stdout, stderr, status = Open3.capture3(
        'swiftc',
        '-parse-as-library',
        '-typecheck',
        RECORDER_CONTRACT_SOURCE,
        PRESENTATION_SOURCE,
        test_recorder,
        CONTENT_VIEW_SOURCE,
      )
      assert status.success?, "watch recording view failed to typecheck:\n#{stdout}\n#{stderr}"
    end
  end

  def test_real_view_model_is_bound_to_the_shared_production_contract
    source = File.binread(VIEW_MODEL_SOURCE)

    assert_match(
      /class\s+WatchAudioRecorderViewModel\s*:\s*NSObject\s*,\s*WatchRecorderControlling/,
      source,
      'the real watch recorder must conform to the same compiler-checked contract used by the view',
    )
  end

  def test_accessibility_catalog_covers_every_native_project_locale
    catalog = JSON.parse(File.binread(LOCALIZATION_CATALOG))
    strings = catalog.fetch('strings')
    content_view = File.binread(CONTENT_VIEW_SOURCE)
    native_locales = native_project_locales

    ACCESSIBILITY_KEYS.each do |key|
      assert_includes content_view, %("#{key}")
      localizations = strings.fetch(key).fetch('localizations')

      native_locales.each do |locale|
        value = localizations.fetch(locale).fetch('stringUnit').fetch('value')
        refute_empty value, "#{key} must have a #{locale} translation"
      end
    end
  end

  private

  def compile_and_run(*sources, binary:)
    stdout, stderr, compile_status = Open3.capture3(
      'swiftc',
      '-parse-as-library',
      *sources,
      '-o',
      binary,
    )
    assert compile_status.success?, "swiftc failed:\n#{stdout}\n#{stderr}"

    stdout, stderr, run_status = Open3.capture3(binary)
    assert run_status.success?, "timing assertions failed:\n#{stdout}\n#{stderr}"
  end

  def native_project_locales
    project = File.binread(PROJECT_FILE)
    block = project.match(/knownRegions = \((.*?)\);/m)&.captures&.first
    refute_nil block, 'Xcode project must declare knownRegions'

    block.lines.filter_map do |line|
      locale = line.match(/^\s*"?([A-Za-z][A-Za-z0-9_-]*)"?,\s*$/)&.captures&.first
      locale unless locale == 'Base'
    end
  end
end
