import XCTest

@testable import Omi_Computer

/// Remote "after Nth question" prompts must read the PERSISTED accepted-
/// question ledger (the same key the rating prompt and history seed write) —
/// an engine-local counter would reset every launch and demand N fresh
/// questions per session.
@MainActor
final class RemotePromptLedgerTests: XCTestCase {
  private let spec = RemotePromptSpec(
    id: "q3-survey", type: "stars", question: "Useful?", options: [],
    ctaLabel: nil, ctaURL: nil, triggerKind: "question_count", triggerCount: 3)

  override func setUp() async throws {
    RatingPromptManager.shared.remoteDisableCheck = { false }
    RatingPromptManager.shared.resetForTesting()
    // The built-in ask must not own the slot in this test.
    UserDefaults.standard.set(true, forKey: DefaultsKey.ratingPromptDismissed.rawValue)
    RemotePromptEngine.shared.isSignedInCheck = { true }
    RemotePromptEngine.shared.fetch = { [self.spec] }
    RemotePromptEngine.shared.resetForTesting()
    await RemotePromptEngine.shared.refreshFromServer()
  }

  override func tearDown() async throws {
    RemotePromptEngine.shared.isSignedInCheck = { AuthState.shared.isSignedIn }
    RemotePromptEngine.shared.fetch = { [] }
    RemotePromptEngine.shared.isSignedInCheck = { true }
    await RemotePromptEngine.shared.refreshFromServer()
    RemotePromptEngine.shared.resetForTesting()
    RatingPromptManager.shared.resetForTesting()
    RatingPromptManager.shared.remoteDisableCheck = {
      PostHogManager.shared.isFeatureEnabled(RatingPromptPolicy.killSwitchFlag)
    }
  }

  func testPersistedLedgerArmsPromptWithoutNewSessionQuestions() async {
    XCTAssertNil(RemotePromptEngine.shared.current)
    // Questions persisted by a PREVIOUS session (or the history seed) — write
    // the ledger key directly, then simulate the relaunch-time fetch.
    UserDefaults.standard.set(3, forKey: DefaultsKey.ratingPromptQuestionCount.rawValue)
    await RemotePromptEngine.shared.refreshFromServer()
    XCTAssertEqual(RemotePromptEngine.shared.current?.id, "q3-survey")
  }

  func testLedgerBelowThresholdStaysHidden() async {
    UserDefaults.standard.set(2, forKey: DefaultsKey.ratingPromptQuestionCount.rawValue)
    await RemotePromptEngine.shared.refreshFromServer()
    XCTAssertNil(RemotePromptEngine.shared.current)
  }
}
