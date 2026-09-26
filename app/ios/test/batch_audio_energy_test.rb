# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class BatchAudioEnergyTest < Minitest::Test
  def test_native_batch_writes_settings_and_location
    ios_root = File.expand_path('..', __dir__)
    sources = %w[
      Runner/Batch/BaseBatchAudioWriter.swift
      Runner/Batch/BatchAudioWriter.swift
      Runner/PhoneMic/PhoneMicBatchAudioWriter.swift
      test/batch_audio_energy_test.swift
    ].map { |path| File.join(ios_root, path) }
    Dir.mktmpdir('omi-batch-energy') do |directory|
      binary = File.join(directory, 'batch-energy-test')
      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library', *sources, '-o', binary)
      assert status.success?, "swiftc failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(binary)
      assert status.success?, "native batch assertions failed:\n#{stdout}\n#{stderr}"
    end
  end
end
