import XCTest

@testable import Omi_Computer

@MainActor
final class ContextReminderCoordinatorTests: XCTestCase {
  private let ownerFixture = RuntimeOwnerAuthorityTestFixture()
  private let start = Date(timeIntervalSince1970: 1_788_230_400)
  private let project = ContextReminderObservedContext(
    appName: "Xcode",
    bundleID: "com.apple.dt.Xcode",
    normalizedTitle: "Pricing Engine",
    bucketID: "bucket-1")
  private let elsewhere = ContextReminderObservedContext(
    appName: "Safari",
    bundleID: "com.apple.Safari",
    normalizedTitle: "Inbox",
    bucketID: nil)

  override func setUp() async throws {
    await ownerFixture.establish(authOwnerID: "owner-1")
  }

  override func tearDown() async throws {
    await ownerFixture.restore()
  }

  func testCreateBindsToInjectedContextAndObserveDeliversOncePerStay() async throws {
    let store = try makeStore()
    let clock = start
    var presented: [ContextReminder] = []
    let coordinator = ContextReminderCoordinator(
      store: store,
      contextProvider: { self.project },
      presenter: { _, reminder in
        presented.append(reminder)
        return true
      },
      dismisser: {},
      now: { clock },
      ownerIDProvider: { "owner-1" },
      createActionItem: { _, _, _, _ in "task-1" },
      completeActionItem: { _, _, _ in })

    let result = await coordinator.createFromCurrentContext(
      text: "ping Priya", expectedOwnerID: "owner-1")
    XCTAssertTrue(result.contains("Pricing Engine"))
    let saved = try await store.allReminders()
    XCTAssertEqual(saved.map(\.text), ["ping Priya"])
    XCTAssertEqual(saved.first?.actionItemID, "task-1")
    XCTAssertEqual(saved.first?.contextKey.bucketID, "bucket-1")

    await coordinator.observe(project)
    await coordinator.observe(project)
    XCTAssertEqual(presented.map(\.text), ["ping Priya"])

    await coordinator.observe(elsewhere)
    XCTAssertEqual(presented.count, 1)

    await coordinator.observe(project)
    XCTAssertEqual(presented.count, 2)
  }

  func testSnoozeAndDoneSuppressDueDelivery() async throws {
    let store = try makeStore()
    var clock = start
    var presented: [String] = []
    var completedActionItems: [String] = []
    let coordinator = ContextReminderCoordinator(
      store: store,
      contextProvider: { self.project },
      presenter: { _, reminder in
        presented.append(reminder.id)
        return true
      },
      dismisser: {},
      now: { clock },
      calendar: Calendar(identifier: .gregorian),
      ownerIDProvider: { "owner-1" },
      createActionItem: { _, _, _, _ in "task-1" },
      completeActionItem: { id, _, _ in completedActionItems.append(id) })

    _ = await coordinator.createFromCurrentContext(text: "ping Priya", expectedOwnerID: "owner-1")
    let createdReminders = try await store.allReminders()
    let reminderID = try XCTUnwrap(createdReminders.first?.id)

    await coordinator.resolve(id: reminderID, snoozed: true)
    let snoozedReminders = try await store.allReminders()
    let snoozedUntil = try XCTUnwrap(snoozedReminders.first?.snoozeUntil)
    clock = snoozedUntil.addingTimeInterval(-1)
    await coordinator.observe(project)
    XCTAssertTrue(presented.isEmpty)

    clock = snoozedUntil
    await coordinator.observe(project)
    XCTAssertEqual(presented, [reminderID])

    await coordinator.resolve(id: reminderID, snoozed: false)
    presented.removeAll()
    await coordinator.observe(elsewhere)
    await coordinator.observe(project)
    XCTAssertTrue(presented.isEmpty)
    XCTAssertEqual(completedActionItems, ["task-1"])
  }

  func testCreateRejectsEmptyTextAndOmiFrontmost() async throws {
    let store = try makeStore()
    let omi = ContextReminderObservedContext(
      appName: "Omi",
      bundleID: AppBuild.productionBundleIdentifier,
      normalizedTitle: "Chat",
      bucketID: nil)
    let coordinator = ContextReminderCoordinator(
      store: store,
      contextProvider: { omi },
      presenter: { _, _ in true },
      dismisser: {},
      ownerIDProvider: { "owner-1" },
      createActionItem: { _, _, _, _ in nil },
      completeActionItem: { _, _, _ in })

    let empty = await coordinator.createFromCurrentContext(text: "  ", expectedOwnerID: "owner-1")
    XCTAssertTrue(empty.contains("text is required"))

    let omiFront = await coordinator.createFromCurrentContext(
      text: "look at this", expectedOwnerID: "owner-1")
    XCTAssertTrue(omiFront.contains("not Omi"))
    let remaining = try await store.allReminders()
    XCTAssertTrue(remaining.isEmpty)
  }

  func testOwnerChangeClearsInFlightDeliveryState() async throws {
    let store = try makeStore()
    var dismissed = 0
    var presented = 0
    let coordinator = ContextReminderCoordinator(
      store: store,
      contextProvider: { self.project },
      presenter: { _, _ in
        presented += 1
        return true
      },
      dismisser: { dismissed += 1 },
      ownerIDProvider: { "owner-1" },
      createActionItem: { _, _, _, _ in nil },
      completeActionItem: { _, _, _ in })
    _ = await coordinator.createFromCurrentContext(text: "ping Priya", expectedOwnerID: "owner-1")
    await coordinator.observe(project)
    XCTAssertEqual(presented, 1)
    coordinator.resetForOwnerChange()
    XCTAssertEqual(dismissed, 1)
    // The in-flight delivery state must be cleared, not just the card: the same
    // place re-observed after the reset presents the reminder again.
    await coordinator.observe(project)
    XCTAssertEqual(presented, 2)
  }

  func testAssistantIdMapsToTaskKind() {
    XCTAssertEqual(ProactiveNotificationKind.from(assistantId: ContextReminderCoordinator.assistantID), .task)
  }

  private func makeStore() throws -> ContextReminderStore {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("context-reminder-coord-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    addTeardownBlock { try? FileManager.default.removeItem(at: directory) }
    let fileURL = directory.appendingPathComponent("reminders.json")
    return ContextReminderStore(fileURLProvider: { fileURL }, ownerIDProvider: { "owner-1" })
  }
}
