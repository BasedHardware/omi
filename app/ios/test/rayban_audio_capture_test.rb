# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class RayBanAudioCaptureTest < Minitest::Test
  SOURCE = ENV.fetch('OMI_RAYBAN_CAPTURE_SOURCE', File.expand_path('../Runner/RayBanMeta/RayBanMetaAudioCapture.swift', __dir__))

  def run_command(*command)
    stdout, stderr, status = Open3.capture3(*command)
    assert status.success?, "command failed:\n#{stdout}\n#{stderr}"
    stdout
  end

  def test_actual_capture_class_releases_partial_resources_and_retries
    Dir.mktmpdir('rayban-audio-capture') do |directory|
      cache = File.join(directory, 'module-cache')
      run_command('swiftc', '-swift-version', '5', '-parse-as-library', '-emit-library', '-emit-module',
                  '-module-name', 'AVFoundation', '-module-cache-path', cache,
                  File.join(__dir__, 'fixtures/rayban_audio_avfoundation.swift'),
                  '-emit-module-path', File.join(directory, 'AVFoundation.swiftmodule'),
                  '-o', File.join(directory, 'libAVFoundation.dylib'))
      binary = File.join(directory, 'capture-test')
      run_command('swiftc', '-swift-version', '5', '-parse-as-library', '-module-cache-path', cache,
                  '-I', directory, '-L', directory, '-lAVFoundation', '-Xlinker', '-rpath', '-Xlinker', directory,
                  SOURCE, File.join(__dir__, 'rayban_audio_capture_test.swift'), '-o', binary)
      assert_includes run_command(binary), '8 failure/retry scenarios passed'
    end
  end

  def test_capture_type_checks_against_the_real_ios_sdk
    sdk, _, status = Open3.capture3('xcrun', '--sdk', 'iphonesimulator', '--show-sdk-path')
    skip 'iOS simulator SDK unavailable' unless status.success?
    Dir.mktmpdir('rayban-audio-sdk') do |directory|
      run_command('xcrun', 'swiftc', '-typecheck', '-swift-version', '5', '-sdk', sdk.strip,
                  '-target', 'arm64-apple-ios15.1-simulator', '-module-cache-path', directory, SOURCE)
    end
  end
end
