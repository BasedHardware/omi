# frozen_string_literal: true
require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class NativeSurfaceContractTest < Minitest::Test
  def test_typed_commands_and_invalidation
    ios = File.expand_path('..', __dir__)
    sources = %w[Runner/SafeFoundationSinks.swift Runner/NativeUI/NativeSurfaceContract.swift test/native_surface_contract_test.swift].map { |path| File.join(ios, path) }
    Dir.mktmpdir('omi-native-surface') do |directory|
      binary = File.join(directory, 'contract')
      out, err, status = Open3.capture3('swiftc', '-parse-as-library', *sources, '-o', binary)
      assert status.success?, "#{out}\n#{err}"
      out, err, status = Open3.capture3(binary)
      assert status.success?, "#{out}\n#{err}"
    end
  end
end
