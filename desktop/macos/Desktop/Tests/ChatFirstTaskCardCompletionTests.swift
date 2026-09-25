import XCTest

@testable import Omi_Computer

/// Ticking a task card in the transcript.
///
/// The card has no list to fall back on: it names one task by id and draws
/// whatever the store says that task is. Completion is the one gesture that
/// moves a task between the store's two arrays, so it is also the one gesture
/// that can lose it — and a card that loses its task does not show a ticked
/// box, it shows "Task is no longer available", which reads as if the task had
/// been deleted rather than done.
@MainActor
final class ChatFirstTaskCardCompletionTests: XCTestCase {
  private var fixture: RewindStorageTestIsolation.Fixture?
  private var previousOwnerID: String?
  private var previousAuth: RewindStorageTestIsolation.AuthSnapshot?

  override func setUp() async throws {
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "task-card-completion")
    self.fixture = fixture
    previousAuth = RewindStorageTestIsolation.captureAuthSnapshot()
    previousOwnerID = RuntimeOwnerIdentity.currentOwnerId()
    await transitionOwner(to: fixture.testUserId)
    RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId)
    TasksStore.shared.resetSessionState()
  }

  override func tearDown() async throws {
    TasksStore.shared.resetSessionState()
    if let previousAuth { RewindStorageTestIsolation.restoreAuthSnapshot(previousAuth) }
    await transitionOwner(to: previousOwnerID)
    await RewindStorageTestIsolation.tearDown(userDir: fixture?.userDir)
    fixture = nil
  }

  /// The card reads `TasksStore.tasks`. Completing has to leave the task
  /// somewhere in there, still not retired, or the card has nothing to draw.
  func testACompletedTaskIsStillTheTaskTheCardNames() async throws {
    let store = TasksStore.shared
    try await ActionItemStorage.shared.syncTaskActionItems(
      [
        TaskActionItem(
          id: "card-task",
          description: "Attend the Claw hackathon",
          completed: false,
          createdAt: Date(),
          dueAt: nil,
          source: "manual")
      ],
      authorization: .unrestricted)

    let hydrated = await store.resolveCanonicalTask(id: "card-task")
    let task = try XCTUnwrap(hydrated, "the card hydrates its task before it can draw one")
    XCTAssertFalse(task.completed)

    await toggleWithRemoteAccepting(task, store: store)

    let afterToggle = store.tasks.first { $0.id == "card-task" }
    let stillThere = try XCTUnwrap(
      afterToggle, "completing a task must not take it out of the store the card reads")
    XCTAssertTrue(stillThere.completed, "the box is ticked, not emptied")
    XCTAssertFalse(stillThere.isRetired, "completing is not retiring")
  }

  /// What the card actually renders, through its own presentation rule.
  func testTheCardShowsTheTickedTaskRatherThanAnUnavailablePlaceholder() async throws {
    let store = TasksStore.shared
    try await ActionItemStorage.shared.syncTaskActionItems(
      [
        TaskActionItem(
          id: "card-task",
          description: "Implement one-click summary email",
          completed: false,
          createdAt: Date(),
          dueAt: nil,
          source: "manual")
      ],
      authorization: .unrestricted)

    let resolved = await store.resolveCanonicalTask(id: "card-task")
    let task = try XCTUnwrap(resolved)
    await toggleWithRemoteAccepting(task, store: store)

    let liveTask = store.tasks.first { $0.id == "card-task" && !$0.isRetired }
    let displayed = ChatFirstTaskCardPresentation.displayTask(
      liveTask: liveTask,
      retainedCompletedTask: nil
    )
    let shown = try XCTUnwrap(
      displayed,
      "a task the reader just ticked is done, not gone — the card must not fall through to "
        + "\"Task is no longer available\"")
    XCTAssertTrue(shown.completed)
  }

  /// The card re-hydrates by id whenever it loses the row — after a relaunch,
  /// or when the store's arrays are rebuilt under it. A completed task has to
  /// come back from that lookup too.
  func testAFreshCardStillResolvesATaskThatWasAlreadyCompleted() async throws {
    let store = TasksStore.shared
    try await ActionItemStorage.shared.syncTaskActionItems(
      [
        TaskActionItem(
          id: "card-task",
          description: "Get the agent ecosystem working again",
          completed: true,
          createdAt: Date(),
          dueAt: nil,
          source: "manual")
      ],
      authorization: .unrestricted)
    store.resetSessionState()

    let resolved = await store.resolveCanonicalTask(id: "card-task")
    let task = try XCTUnwrap(
      resolved, "a completed task is still a task the card can name and draw")
    XCTAssertTrue(task.completed)
    XCTAssertFalse(task.isRetired)
  }

  /// The toggle with its network legs stubbed to succeed — the production case,
  /// where the backend accepts the completion. A failed remote leg is a
  /// different behaviour (rollback) with its own coverage.
  private func toggleWithRemoteAccepting(
    _ task: TaskActionItem,
    store: TasksStore
  ) async {
    await store.toggleTask(
      task,
      operationOverrides: TasksStore.ToggleOperationOverrides(
        updateLocal: { completed, _ in
          try await ActionItemStorage.shared.updateCompletionStatus(
            backendId: task.id, completed: completed, authorization: .unrestricted)
          guard
            let stored = try await ActionItemStorage.shared.getLocalActionItem(
              byBackendId: task.id)
          else { throw CocoaError(.fileNoSuchFile) }
          return stored
        },
        refreshDashboard: { _ in await store.loadDashboardTasks() },
        updateRemote: { _, _ in
          guard
            let stored = try await ActionItemStorage.shared.getLocalActionItem(
              byBackendId: task.id)
          else { throw CocoaError(.fileNoSuchFile) }
          return stored
        },
        syncRemote: { _, _ in },
        rollbackLocal: {}
      ))
  }

  /// The card's own state machine, driven through the interleaving that made a
  /// ticked task read as a deleted one.
  ///
  /// Ticking moves the task between the store's two arrays, and the toggle
  /// awaits SQLite before it does — so `liveTask` can be nil for a moment. The
  /// card's `hydrationKey` flips on exactly that, SwiftUI cancels the in-flight
  /// hydration, and `TasksStore.isCurrent` folds `!Task.isCancelled` into its
  /// lease check, so `resolveCanonicalTask` answers nil by construction. The
  /// old code published that nil.
  func testACancelledHydrationDoesNotSpeakForTheCard() {
    XCTAssertEqual(
      ChatFirstTaskCardHydration.resolution(isCancelled: true, hasLiveTask: false),
      .abandon,
      "a hydration SwiftUI has already superseded must not write the card's state")
    XCTAssertEqual(
      ChatFirstTaskCardHydration.resolution(isCancelled: true, hasLiveTask: true),
      .abandon)
    XCTAssertEqual(
      ChatFirstTaskCardHydration.resolution(isCancelled: false, hasLiveTask: true),
      .settle,
      "the store already has the task — there is nothing left to hydrate")
    XCTAssertEqual(
      ChatFirstTaskCardHydration.resolution(isCancelled: false, hasLiveTask: false),
      .adopt,
      "an uncontested hydration is the card's answer")
  }

  /// The whole point, stated as the reader sees it: a task ticked and then
  /// abandoned by a late nil is still shown, ticked.
  func testATickedTaskSurvivesALateNilFromASupersededHydration() async throws {
    let store = TasksStore.shared
    try await ActionItemStorage.shared.syncTaskActionItems(
      [
        TaskActionItem(
          id: "card-task",
          description: "Attend the Claw hackathon",
          completed: false,
          createdAt: Date(),
          dueAt: nil,
          source: "manual")
      ],
      authorization: .unrestricted)
    let resolved = await store.resolveCanonicalTask(id: "card-task")
    let task = try XCTUnwrap(resolved)
    await toggleWithRemoteAccepting(task, store: store)

    let ticked = try XCTUnwrap(store.tasks.first { $0.id == "card-task" })
    XCTAssertTrue(ticked.completed)

    // The card has retained the ticked row. A hydration that started before the
    // tick now returns nil, cancelled.
    var retained: TaskActionItem? = ticked
    switch ChatFirstTaskCardHydration.resolution(isCancelled: true, hasLiveTask: false) {
    case .abandon:
      break
    case .settle, .adopt:
      retained = nil  // what the old code did with a nil answer
    }

    XCTAssertNotNil(
      ChatFirstTaskCardPresentation.displayTask(liveTask: nil, retainedCompletedTask: retained),
      "the reader ticked this task — the card owes them a ticked box, not "
        + "\"Task is no longer available\"")
  }

  /// The reader's own tick outranks a store row that reads retired.
  ///
  /// This is the field failure: the Removed lane tombstoned live tasks in the
  /// local cache, so completing one of them read the row back retired and the
  /// card swapped the reader's ticked box for "Task is no longer available".
  /// The lane no longer fabricates those tombstones and a migration clears the
  /// ones it left, but a completion the app accepted must never be erasable by
  /// a later read — whatever put the retirement there.
  func testAReaderCompletionSurvivesARowThatReadsRetired() throws {
    let tombstoned = TaskActionItem(
      id: "card-task",
      description: "Fix Omi tasks being too noisy",
      completed: true,
      createdAt: Date(),
      source: "manual"
    ).retired()
    XCTAssertTrue(tombstoned.isRetired, "fixture must carry the stale tombstone that caused this")

    XCTAssertNil(
      ChatFirstTaskCardPresentation.displayTask(
        liveTask: tombstoned,
        retainedCompletedTask: tombstoned),
      "without the reader's own completion, a retired row is still grounds for taking the card away")

    let shown = try XCTUnwrap(
      ChatFirstTaskCardPresentation.displayTask(
        liveTask: tombstoned,
        retainedCompletedTask: nil,
        locallyCompletedTask: tombstoned),
      "the reader ticked this card — a retirement found afterwards does not get to undo that")
    XCTAssertTrue(shown.completed)
  }

  /// Unticking is the one gesture that clears it: the card follows the reader,
  /// not a completion it has decided to keep forever.
  func testUntickingDropsTheRetainedReaderCompletion() {
    XCTAssertNil(
      ChatFirstTaskCardPresentation.displayTask(
        liveTask: nil,
        retainedCompletedTask: nil,
        locallyCompletedTask: nil),
      "the toggle clears the local completion when the reader unticks, leaving the store to answer")
  }

  private func transitionOwner(to ownerID: String?) async {
    do {
      _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        plannedNextOwner: { _, _ in ownerID },
        quiesceVoice: { _, _ in },
        retargetLocalStorage: { _, _ in },
        ownerDidChange: {},
        { defaults in
          defaults.removeObject(forKey: .automationOwnerOverride)
          if let ownerID {
            defaults.set(ownerID, forKey: .authUserId)
          } else {
            defaults.removeObject(forKey: .authUserId)
          }
        })
    } catch {
      XCTFail("owner transition failed: \(error)")
    }
  }
}
