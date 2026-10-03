# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class NativeHomeContractTest < Minitest::Test
  def test_production_decoder_and_revision_fence
    ios = File.expand_path('..', __dir__)
    fixture = File.expand_path('../../test/fixtures/native_home_v1.json', __dir__)
    sources = %w[Runner/SafeFoundationSinks.swift Runner/NativeUI/NativeHomeContract.swift test/native_home_contract_test.swift].map { |path| File.join(ios, path) }
    Dir.mktmpdir('omi-native-home-contract') do |directory|
      binary = File.join(directory, 'contract-test')
      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library', *sources, '-o', binary)
      assert status.success?, "swiftc failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(binary, fixture)
      assert status.success?, "native home contract failed:\n#{stdout}\n#{stderr}"
    end
  end
end
