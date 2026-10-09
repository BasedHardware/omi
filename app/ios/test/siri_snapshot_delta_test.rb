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

  def test_late_spotlight_repair_keeps_the_owner_marker_until_delete_succeeds
    swift = File.read(SOURCE)
    helper = swift[/enum SiriLateRepairLedger \{.*?\n\}/m]
    refute_nil helper
    harness = <<~SWIFT
      import Foundation
      enum PlistValue { case string(String); case array([PlistValue]) }
      enum SafeDefaults {
          static func store(_ value: PlistValue, forKey key: String, in defaults: UserDefaults) throws {
              guard case .array(let values) = value else { fatalError("array expected") }
              defaults.set(values.map { value in
                  guard case .string(let text) = value else { fatalError("string expected") }
                  return text
              }, forKey: key)
          }
      }
      #{helper}
      enum TestFailure: Error { case unavailable }
      @main struct Harness {
          static func main() async throws {
              let suite = "siri-late-repair-\\(UUID().uuidString)"
              let defaults = UserDefaults(suiteName: suite)!
              defer { defaults.removePersistentDomain(forName: suite) }
              let key = "pending-owner-index-delete"
              try SiriLateRepairLedger.mark("old-owner", defaults: defaults, key: key)
              try SiriLateRepairLedger.mark("old-owner", defaults: defaults, key: key)
              precondition(defaults.stringArray(forKey: key) == ["old-owner"])
              do {
                  _ = try await SiriLateRepairLedger.drain(defaults: defaults, key: key) { _ in
                      throw TestFailure.unavailable
                  }
                  fatalError("delete should fail")
              } catch TestFailure.unavailable {}
              precondition(defaults.stringArray(forKey: key) == ["old-owner"])
              var deleted = [String]()
              _ = try await SiriLateRepairLedger.drain(defaults: defaults, key: key) { deleted.append($0) }
              precondition(deleted == ["old-owner"])
              precondition(defaults.stringArray(forKey: key) == nil)
          }
      }
    SWIFT
    Dir.mktmpdir('siri-late-repair') do |dir|
      path = File.join(dir, 'main.swift')
      File.write(path, harness)
      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library', path, '-o', File.join(dir, 'repair'))
      assert status.success?, "swiftc failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(File.join(dir, 'repair'))
      assert status.success?, "repair failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_owner_repair_clears_snapshot_with_marker_and_retains_marker_if_delete_fails
    swift = File.read(SOURCE)
    helper = swift[/enum SiriLateRepairLedger \{.*?\n\}/m]
    repair = swift[/func repairOwnerIndex\(uid: String\).*?\n    \}/m]
    refute_nil helper
    refute_nil repair
    assert_includes repair, 'requireValidOwner(uid, allowPendingLateRepair: true)'
    assert_includes repair, 'mutateForOwner(uid, allowPendingLateRepair: true)'
    assert_includes repair, 'SiriLateRepairLedger.repair(uid'
    harness = <<~SWIFT
      import Foundation
      enum PlistValue { case string(String); case array([PlistValue]) }
      enum SafeDefaults {
          static func store(_ value: PlistValue, forKey key: String, in defaults: UserDefaults) throws {
              guard case .array(let values) = value else { fatalError("array expected") }
              defaults.set(values.map { value in
                  guard case .string(let text) = value else { fatalError("string expected") }
                  return text
              }, forKey: key)
          }
      }
      #{helper}
      enum TestFailure: Error { case unavailable }
      @main struct Harness {
          static func main() async throws {
              let suite = "siri-owner-repair-\\(UUID().uuidString)"
              let defaults = UserDefaults(suiteName: suite)!
              defer { defaults.removePersistentDomain(forName: suite) }
              let key = "pending-owner-index-delete"
              var snapshot = ["old-row"]
              var searchable = ["old-row"]
              var boundOwner = "owner-a"
              try SiriLateRepairLedger.mark(boundOwner, defaults: defaults, key: key)
              func clearSnapshot() throws {
                  precondition(defaults.stringArray(forKey: key) == ["owner-a"])
                  precondition(boundOwner == "owner-a")
                  snapshot.removeAll()
              }
              do {
                  try await SiriLateRepairLedger.repair("owner-a", defaults: defaults, key: key,
                      clearSnapshot: clearSnapshot, delete: { _ in throw TestFailure.unavailable })
                  fatalError("delete should fail")
              } catch TestFailure.unavailable {}
              precondition(snapshot.isEmpty)
              precondition(searchable == ["old-row"])
              precondition(defaults.stringArray(forKey: key) == ["owner-a"])
              try await SiriLateRepairLedger.repair("owner-a", defaults: defaults, key: key,
                  clearSnapshot: clearSnapshot, delete: { uid in
                      precondition(uid == boundOwner)
                      precondition(defaults.stringArray(forKey: key) == [uid])
                      searchable.removeAll()
                  })
              precondition(searchable.isEmpty)
              precondition(defaults.stringArray(forKey: key) == nil)
          }
      }
    SWIFT
    Dir.mktmpdir('siri-owner-repair') do |dir|
      path = File.join(dir, 'main.swift')
      File.write(path, harness)
      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library', path, '-o', File.join(dir, 'repair'))
      assert status.success?, "swiftc failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(File.join(dir, 'repair'))
      assert status.success?, "repair failed:\n#{stdout}\n#{stderr}"
    end
  end

  def test_late_spotlight_completion_starts_a_new_serialized_turn
    swift = File.read(SOURCE)
    context = swift[/private enum SiriSnapshotQueueContext \{.*?\n\}/m]
    deadline = swift[/private actor SiriSpotlightDeadline \{.*?\n\}/m]
    refute_nil context
    refute_nil deadline
    deadline = deadline.sub('12_000_000_000', '20_000_000')
    harness = <<~SWIFT
      import Foundation
      enum SiriSession { enum Failure: Error { case server } }
      #{context}
      #{deadline}
      actor Probe {
          private var observed: Bool?
          func record(_ value: Bool) { observed = value }
          func read() -> Bool? { observed }
      }
      @main struct Harness {
          static func main() async throws {
              let probe = Probe()
              await SiriSnapshotQueueContext.$active.withValue(true) {
                  do {
                      try await SiriSpotlightDeadline.run({
                          try await Task.sleep(nanoseconds: 80_000_000)
                      }, onLateCompletion: {
                          await probe.record(SiriSnapshotQueueContext.active)
                      })
                      fatalError("operation should time out")
                  } catch {}
              }
              try await Task.sleep(nanoseconds: 200_000_000)
              let observed = await probe.read()
              precondition(observed == false)
          }
      }
    SWIFT
    Dir.mktmpdir('siri-late-queue') do |dir|
      path = File.join(dir, 'main.swift')
      File.write(path, harness)
      stdout, stderr, status = Open3.capture3('swiftc', '-parse-as-library', path, '-o', File.join(dir, 'queue'))
      assert status.success?, "swiftc failed:\n#{stdout}\n#{stderr}"
      stdout, stderr, status = Open3.capture3(File.join(dir, 'queue'))
      assert status.success?, "queue failed:\n#{stdout}\n#{stderr}"
    end
  end
end
