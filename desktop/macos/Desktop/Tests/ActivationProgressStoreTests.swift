import XCTest

@testable import Omi_Computer

@MainActor
final class ActivationProgressStoreTests: XCTestCase {
  private lazy var defaults: UserDefaults = {
    let suiteName = "ActivationProgressStoreTests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName) ?? .standard
    addTeardownBlock {
      UserDefaults(suiteName: suiteName)?.removePersistentDomain(forName: suiteName)
    }
    return defaults
  }()

  private func makeStore(
    ownerID: @escaping () -> String? = { "user-a" },
    now: @escaping () -> Date = Date.init
  ) -> ActivationProgressStore {
    ActivationProgressStore(defaults: defaults, ownerIDProvider: ownerID, now: now)
  }

  func testFirstWinRequiresKnownCounts() {
    let store = makeStore()

    // Counts still loading (nil) — never flash the new-user surface.
    XCTAssertFalse(store.shouldShowFirstWin(countsKnown: false))
    XCTAssertTrue(store.shouldShowFirstWin(countsKnown: true))
  }

  func testMarksActivateAndPersist() {
    let store = makeStore()

    store.markAskedOmi()
    XCTAssertFalse(store.isActivated)
    store.markConversationCaptured(title: "Standup")
    XCTAssertTrue(store.isActivated)
    XCTAssertEqual(store.progress.firstConversationTitle, "Standup")
    XCTAssertFalse(store.shouldShowFirstWin(countsKnown: true))

    // A fresh store for the same owner restores the persisted state.
    let reloaded = makeStore()
    XCTAssertTrue(reloaded.isActivated)
  }

  func testLifetimeConversationHistoryGraduatesVeterans() {
    let store = makeStore()

    // A veteran signing in on a fresh Mac: history arrives, first-win never shows.
    store.applyLifetimeCounts(conversations: 2401, memories: 9000)
    XCTAssertTrue(store.isActivated)
    XCTAssertFalse(store.shouldShowFirstWin(countsKnown: true))
    // Auto-graduation is silent — no celebration for veterans.
    XCTAssertFalse(store.celebrationPending)
  }

  func testFirstConversationDuringFirstWinCompletesStepWithoutGraduating() {
    let store = makeStore()

    // First-win is on screen; the user's FIRST conversation lands and the
    // count refresh reports it. That completes the capture step but must not
    // skip the ask step (no silent graduation).
    store.noteFirstWinShown()
    store.applyLifetimeCounts(conversations: 1, memories: 45)
    XCTAssertTrue(store.progress.conversationCaptured)
    XCTAssertFalse(store.progress.graduated)
    XCTAssertFalse(store.isActivated)
    XCTAssertTrue(store.shouldShowFirstWin(countsKnown: true))

    // The ask step still completes the flow — with the celebration.
    store.markAskedOmi()
    XCTAssertTrue(store.isActivated)
    XCTAssertTrue(store.celebrationPending)
  }

  func testMemoriesAloneDoNotGraduate() {
    let store = makeStore()

    // Onboarding imports seed memories before any conversation exists.
    store.applyLifetimeCounts(conversations: 0, memories: 45)
    XCTAssertFalse(store.isActivated)
    XCTAssertTrue(store.shouldShowFirstWin(countsKnown: true))
  }

  func testTimeBoxGraduatesPermissionSkippers() {
    var currentTime = Date(timeIntervalSince1970: 1_000_000)
    let store = makeStore(now: { currentTime })

    store.noteFirstWinShown()
    XCTAssertFalse(store.isActivated)

    // 49 hours later the surface stops insisting even with nothing done.
    currentTime = currentTime.addingTimeInterval(49 * 60 * 60)
    store.noteFirstWinShown()
    XCTAssertTrue(store.isActivated)
    XCTAssertFalse(store.shouldShowFirstWin(countsKnown: true))
  }

  func testSameDayRevisitsNeverGraduate() {
    var currentTime = Date(timeIntervalSince1970: 1_000_000)
    let store = makeStore(now: { currentTime })

    // Six Home visits within one session/day: one distinct-day visit, no
    // graduation — the surface must survive normal tab switching.
    for _ in 0..<6 {
      store.noteFirstWinShown()
      currentTime = currentTime.addingTimeInterval(60)
    }
    XCTAssertFalse(store.isActivated)
    XCTAssertEqual(store.progress.firstWinVisits, 1)
  }

  func testCelebrationFiresOnceOnRealActivation() {
    let store = makeStore()

    store.markConversationCaptured(title: nil)
    XCTAssertFalse(store.celebrationPending)
    store.markAskedOmi()
    XCTAssertTrue(store.celebrationPending)
    store.consumeCelebration()
    XCTAssertFalse(store.celebrationPending)
  }

  func testOwnerScopingIsolatesProgress() {
    let storeA = makeStore(ownerID: { "user-a" })
    storeA.markAskedOmi()
    storeA.markConversationCaptured(title: nil)
    XCTAssertTrue(storeA.isActivated)

    // Another account on the same machine starts clean.
    let storeB = makeStore(ownerID: { "user-b" })
    XCTAssertFalse(storeB.isActivated)
  }

  func testInPlaceOwnerSwitchClearsCelebrationAndProgress() async {
    // Same store instance across an in-place account switch (the PR #9821
    // bleed class): owner B must inherit neither A's progress nor A's
    // transient celebration.
    var ownerID: String? = "user-a"
    let store = makeStore(ownerID: { ownerID })
    store.markConversationCaptured(title: nil)
    store.markAskedOmi()
    XCTAssertTrue(store.isActivated)
    XCTAssertTrue(store.celebrationPending)

    ownerID = "user-b"
    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
    // The owner-change observer hops through a MainActor task.
    for _ in 0..<10 {
      await Task.yield()
      if !store.celebrationPending && !store.isActivated { break }
    }

    XCTAssertFalse(store.celebrationPending)
    XCTAssertFalse(store.isActivated)
    XCTAssertEqual(store.progress, ActivationProgressStore.Progress())

    // Switching back restores A's persisted progress — without celebration.
    ownerID = "user-a"
    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
    for _ in 0..<10 {
      await Task.yield()
      if store.isActivated { break }
    }
    XCTAssertTrue(store.isActivated)
    XCTAssertFalse(store.celebrationPending)
  }

  func testSignedOutOwnerDoesNotPersist() {
    let store = makeStore(ownerID: { nil })
    store.markAskedOmi()
    store.markConversationCaptured(title: nil)
    XCTAssertTrue(store.isActivated)

    // Nothing was written for a signed-out owner; a new store starts clean.
    let reloaded = makeStore(ownerID: { nil })
    XCTAssertFalse(reloaded.isActivated)
  }
}
