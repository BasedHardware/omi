require 'minitest/autorun'
require 'open3'
require 'tmpdir'

class SiriSnapshotDeltaTest < Minitest::Test
  SOURCE = File.expand_path('../Runner/SiriIntegration/SiriSnapshotStore.swift', __dir__)

  def test_reconcile_delta_preserves_unchanged_rows_and_includes_deletes
    swift = File.read(SOURCE)
    helper = swift[/enum SiriSnapshotDelta \{.*?\n\}/m]
    refute_nil helper
    harness = <<~SWIFT
      import Foundation
      #{helper}
      @main struct Harness {
          static func main() {
              let before = ["same": "a", "edited": "old", "deleted": "gone"]
              let after = ["same": "a", "edited": "new", "added": "new"]
              precondition(SiriSnapshotDelta.changedIDs(from: before, to: after) == ["added", "deleted", "edited"])
              precondition(SiriSnapshotDelta.changedIDs(from: after, to: after).isEmpty)
          }
      }
    SWIFT
    Dir.mktmpdir('siri-delta') do |dir|
      path = File.join(dir, 'main.swift')
      File.write(path, harness)
      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library', path, '-o', File.join(dir, 'delta'))
      assert status.success?, "swiftc failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(File.join(dir, 'delta'))
      assert status.success?, "delta failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_all_reconciles_apply_the_delta_without_rebuilding_the_index
    swift = File.read(SOURCE)
    %w[SiriConversation SiriMemory SiriTask].each do |entity|
      body = swift[/func reconcile\(_ values: \[#{entity}\].*?\n    \}/m]
      refute_nil body, entity
      assert_includes body, 'SiriSnapshotDelta.changedIDs', entity
      refute_includes body, 'rebuildIndex()', entity
    end
  end
end
