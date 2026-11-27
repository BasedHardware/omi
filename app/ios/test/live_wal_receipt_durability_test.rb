# frozen_string_literal: true

require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class LiveWalReceiptDurabilityTest < Minitest::Test
  SOURCE = File.expand_path('../Runner/LiveWalReceiptDurability.swift', __dir__)
  DELEGATE = File.expand_path('../Runner/AppDelegate.swift', __dir__)

  def test_directory_sync_succeeds_inside_documents_and_rejects_outside_paths
    delegate = File.read(DELEGATE)
    assert_includes delegate, 'DispatchQueue.global(qos: .utility).async'
    assert_includes delegate, 'LiveWalReceiptDurability.syncDirectory(rawPath, documentsURL: documentsURL)'

    Dir.mktmpdir('omi-live-wal-durability') do |directory|
      harness = File.join(directory, 'main.swift')
      binary = File.join(directory, 'live-wal-durability-test')
      File.write(harness, <<~SWIFT)
        import Foundation

        @main
        struct Harness {
          static func main() throws {
            let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
            let documents = root.appendingPathComponent("documents", isDirectory: true)
            let nested = documents.appendingPathComponent("nested", isDirectory: true)
            let outside = root.appendingPathComponent("outside", isDirectory: true)
            try FileManager.default.createDirectory(at: nested, withIntermediateDirectories: true)
            try FileManager.default.createDirectory(at: outside, withIntermediateDirectories: true)

            try LiveWalReceiptDurability.syncDirectory(nested.path, documentsURL: documents)
            do {
              try LiveWalReceiptDurability.syncDirectory(outside.path, documentsURL: documents)
              fatalError("outside path was accepted")
            } catch LiveWalReceiptDurabilityError.invalidPath {
              print("live WAL durability path checks passed")
            }
          }
        }
      SWIFT
      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library', SOURCE, harness, '-o', binary)
      assert status.success?, "compile failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(binary, directory)
      assert status.success?, "durability behavior failed:\n#{stdout}\n#{stderr}"
      assert_includes stdout, 'live WAL durability path checks passed'
    end
  end
end
