import XCTest

@testable import Omi_Computer

final class ContextReminderStoreTests: XCTestCase {
  private let start = Date(timeIntervalSince1970: 1_788_230_400)

  func testMatchesPrefersBucketIdAndFallsBackToBundleAndTitle() async throws {
    let store = try makeStore()
    let key = ContextReminderKey(
      bundleID: "com.apple.dt.Xcode", normalizedTitle: "Pricing Engine", bucketID: "bucket-1")
    let reminder = try await store.create(
      text: "ping Priya", for: key, actionItemID: "task-1", now: start, id: "reminder-1")

    let sameTitle = context(app: "Xcode", bundle: key.bundleID, title: key.normalizedTitle)
    let sameBucket = context(
      app: "Code", bundle: "com.microsoft.VSCode", title: "Renamed", bucketID: "bucket-1")
    let otherPlace = context(app: "Safari", bundle: "com.apple.Safari", title: "Inbox")

    let titleMatches = try await store.dueReminders(for: sameTitle, now: start)
    let bucketMatches = try await store.dueReminders(for: sameBucket, now: start)
    let noMatch = try await store.dueReminders(for: otherPlace, now: start)
    XCTAssertEqual(titleMatches.map(\.id), [reminder.id])
    XCTAssertEqual(bucketMatches.map(\.id), [reminder.id])
    XCTAssertTrue(noMatch.isEmpty)
  }

  func testPersistenceRoundTripAndSnoozeAndCompletion() async throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("context-reminders-\(UUID().uuidString)", isDirectory: true)
    let fileURL = directory.appendingPathComponent("reminders.json")
    defer { try? FileManager.default.removeItem(at: directory) }
    let store = ContextReminderStore(fileURLProvider: { fileURL })
    let key = ContextReminderKey(
      bundleID: "com.apple.dt.Xcode", normalizedTitle: "Pricing Engine", bucketID: "bucket-1")
    let created = try await store.create(
      text: "ping Priya", for: key, actionItemID: "task-1", now: start, id: "reminder-1")
    let reloaded = ContextReminderStore(fileURLProvider: { fileURL })
    let persisted = try await reloaded.allReminders()
    XCTAssertEqual(persisted, [created])

    let place = context(app: "Xcode", bundle: key.bundleID, title: key.normalizedTitle)
    let tomorrow = start.addingTimeInterval(86_400)
    _ = try await store.snooze(id: created.id, until: tomorrow)
    let dueBeforeSnoozeExpires = try await store.dueReminders(
      for: place, now: tomorrow.addingTimeInterval(-1))
    XCTAssertTrue(dueBeforeSnoozeExpires.isEmpty)
    let dueAtSnooze = try await store.dueReminders(for: place, now: tomorrow)
    XCTAssertEqual(dueAtSnooze.map(\.id), [created.id])

    let completed = try await store.markDone(id: created.id, at: tomorrow)
    XCTAssertEqual(completed?.actionItemID, "task-1")
    let dueAfterDone = try await store.dueReminders(for: place, now: tomorrow)
    XCTAssertTrue(dueAfterDone.isEmpty)
  }

  func testOwnerChangeAfterLoadRefusesTheWrite() async throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("context-reminders-owner-\(UUID().uuidString)", isDirectory: true)
    let fileURL = directory.appendingPathComponent("reminders.json")
    defer { try? FileManager.default.removeItem(at: directory) }
    final class OwnerBox: @unchecked Sendable { var value = "owner-a" }
    let owner = OwnerBox()
    let store = ContextReminderStore(
      fileURLProvider: { fileURL },
      ownerIDProvider: { owner.value },
      beforeMutationSave: { owner.value = "owner-b" })
    let key = ContextReminderKey(bundleID: "com.apple.dt.Xcode", normalizedTitle: "Project", bucketID: nil)

    do {
      _ = try await store.create(text: "secret", for: key)
      XCTFail("owner change must reject the write")
    } catch {
      // Expected: the owner observed at load no longer owns the save boundary.
    }
    XCTAssertFalse(FileManager.default.fileExists(atPath: fileURL.path))
  }

  func testOwnerScopedFilesDoNotLeakAcrossAccounts() async throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("context-reminders-scope-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    final class OwnerBox: @unchecked Sendable { var value = "owner-a" }
    let owner = OwnerBox()
    let store = ContextReminderStore(
      fileURLProvider: {
        directory.appendingPathComponent("\(owner.value).json")
      },
      ownerIDProvider: { owner.value })
    let key = ContextReminderKey(bundleID: "com.apple.dt.Xcode", normalizedTitle: "Project", bucketID: nil)
    _ = try await store.create(text: "owner-a secret", for: key, id: "a")

    owner.value = "owner-b"
    let ownerBBeforeCreate = try await store.allReminders()
    XCTAssertTrue(ownerBBeforeCreate.isEmpty)
    _ = try await store.create(text: "owner-b note", for: key, id: "b")

    owner.value = "owner-a"
    let ownerAAfterSwitch = try await store.allReminders()
    XCTAssertEqual(ownerAAfterSwitch.map(\.text), ["owner-a secret"])
  }

  private func makeStore() throws -> ContextReminderStore {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("context-reminders-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    addTeardownBlock { try? FileManager.default.removeItem(at: directory) }
    let fileURL = directory.appendingPathComponent("reminders.json")
    return ContextReminderStore(fileURLProvider: { fileURL })
  }

  private func context(
    app: String,
    bundle: String,
    title: String,
    bucketID: String? = nil
  ) -> ContextReminderObservedContext {
    ContextReminderObservedContext(
      appName: app, bundleID: bundle, normalizedTitle: title, bucketID: bucketID)
  }
}
