# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'
require 'json'

# Replays the canonical phone-mic-native-events/v1 vectors through the
# PRODUCTION PhoneMicController + PhoneMicEventEmitter (SCA-491 / C5). Only OS
# audio/permission/session I/O is faked, via the PhoneMicControllerSeams
# injection points; the lifecycle policy under test is the shipping code.
#
# The Pigeon contract types (PhoneMicCaptureState/Mode, PhoneMicPigeonError)
# cannot compile on macOS (the generated file imports Flutter), so this test
# EXTRACTS those definitions from the generated file at run time into a stub.
# The extraction itself is the drift guard: when Pigeon regenerates the file
# with a different layout, this test fails loudly instead of testing stale
# copies.
class PhoneMicLifecycleReplayTest < Minitest::Test
  IOS_ROOT = File.expand_path('..', __dir__)

  def test_native_lifecycle_replay_vectors
    sources = %w[
      Runner/PhoneMic/PhoneMicController.swift
      Runner/PhoneMic/PhoneMicEventEmitter.swift
      Runner/PhoneMic/PhoneMicControllerSeams.swift
      Runner/PhoneMic/PhoneMicCaptureEngine.swift
      Runner/PhoneMic/PhoneMicConverterPipeline.swift
      test/phone_mic_lifecycle_replay_test.swift
    ].map { |path| File.join(IOS_ROOT, path) }
    Dir.mktmpdir('omi-phonemic-replay') do |directory|
      stub = File.join(directory, 'pigeon_stub.swift')
      File.write(stub, extract_pigeon_contract_stub)
      binary = File.join(directory, 'phonemic-replay-test')
      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library', *sources, stub, '-o', binary)
      assert status.success?, "swiftc failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(binary)
      assert status.success?, "native lifecycle replay failed:\n#{stdout}\n#{stderr}"
      assert_includes stdout, 'all 8 canonical vectors passed'
      # The optional hardware trace is prevalidated by the offline checker.
      # Always exercise the replay adapter with a synthetic foreground
      # sequence, including a stimulus whose unnecessary rebuild must fail.
      trace = File.join(directory, 'foreground-trace.json')
      File.write(trace, JSON.generate({
        schema: 'phone-mic-device-probe/v1', scope: 'native-stream-only', audio_retained: false, session_id: 1,
        events: [
          {kind: 'start_requested'}, {kind: 'state', state: 'starting'}, {kind: 'state', state: 'running'},
          {kind: 'sample'}, {kind: 'os_signal', signal: 'appBecameActive'}, {kind: 'sample'},
          {kind: 'stop_requested'}, {kind: 'state', state: 'idle'}, {kind: 'observation_completed'}
        ]
      }))
      stdout, stderr, status = Open3.capture3(binary, '--device-trace', trace)
      assert status.success?, "foreground trace replay failed:\n#{stdout}\n#{stderr}"
      assert_includes stdout, 'lifecycle policy replay passed'
      # Independent interruption oracle: interrupted -> running with a new
      # engine, stale epoch dropped, both shouldResume values supported.
      [false, true].each do |resume|
        doc = JSON.parse(File.read(trace))
        doc['events'].insert(5,
          {kind: 'os_signal', signal: 'interruptionBegan'}, {kind: 'state', state: 'interrupted'},
          {kind: 'sample'}, {kind: 'os_signal', signal: 'interruptionEnded', should_resume: resume},
          {kind: 'state', state: 'running'})
        interruption = File.join(directory, "interruption-#{resume}.json")
        File.write(interruption, JSON.generate(doc))
        stdout, stderr, status = Open3.capture3(binary, '--device-trace', interruption)
        assert status.success?, "interruption trace replay failed:\n#{stdout}\n#{stderr}"
      end
      denial = File.join(directory, 'denied-trace.json')
      File.write(denial, JSON.generate({
        schema: 'phone-mic-device-probe/v1', scope: 'native-stream-only', audio_retained: false, session_id: 1,
        events: [{kind: 'start_requested'}, {kind: 'state', state: 'starting'},
          {kind: 'state', state: 'idle'}, {kind: 'capture_error', code: 'permission_denied'},
          {kind: 'start_failed', code: 'permission_denied'}, {kind: 'stop_requested'},
          {kind: 'observation_completed'}]
      }))
      stdout, stderr, status = Open3.capture3(binary, '--device-trace', denial)
      assert status.success?, "denied trace replay failed:\n#{stdout}\n#{stderr}"
      # The granted foreground fixture is the recovery process after iOS
      # terminates an app on a Settings permission change.
      stdout, stderr, status = Open3.capture3(binary, '--device-trace', trace)
      assert status.success?, "granted recovery replay failed:\n#{stdout}\n#{stderr}"
      if ENV['OMI_PHONE_MIC_PERMISSION_BEFORE']
        stdout, stderr, status = Open3.capture3(binary, '--device-trace', ENV.fetch('OMI_PHONE_MIC_PERMISSION_BEFORE'))
        assert status.success?, "physical denied trace policy replay failed:\n#{stdout}\n#{stderr}"
      end
      if ENV['OMI_PHONE_MIC_DEVICE_TRACE']
        stdout, stderr, status = Open3.capture3(binary, '--device-trace', ENV.fetch('OMI_PHONE_MIC_DEVICE_TRACE'))
        assert status.success?, "physical trace policy replay failed:\n#{stdout}\n#{stderr}"
        assert_includes stdout, 'lifecycle policy replay passed'
      end

    end
  end

  private

  # Extract the enum + error-type definitions the controller compiles against.
  # Anchored, greedy-until-brace-close; fails when Pigeon's layout changes.
  def extract_pigeon_contract_stub
    generated = File.read(File.join(IOS_ROOT, 'Runner/PhoneMic/PhoneMicPigeon.g.swift'), encoding: 'UTF-8')
    blocks = [
      /enum PhoneMicCaptureState: Int \{.*?\n\}/m,
      /enum PhoneMicCaptureMode: Int \{.*?\n\}/m,
      /final class PhoneMicPigeonError: Error \{.*?\n\}/m
    ].map do |pattern|
      match = generated.match(pattern)
      refute_nil match, "Pigeon contract block #{pattern.source[0, 40]}… no longer matches PhoneMicPigeon.g.swift; regenerate this stub"
      match[0]
    end
    "import Foundation\n\n// Extracted from PhoneMicPigeon.g.swift at test time (drift-guarded).\n\n#{blocks.join("\n\n")}\n"
  end
end
