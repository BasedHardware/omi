# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

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
