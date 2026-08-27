import XCTest

@testable import Omi_Computer

/// Prompt state must be per-account: one account's answers, dismissals, and
/// question counts on a shared Mac must not change another account's
/// eligibility (#9821 account-switch-bleed class).
@MainActor
final class PromptStateAccountScopingTests: XCTestCase {
  private var owner = "user-a"

  override func setUp() async throws {
    RatingPromptManager.shared.remoteDisableCheck = { false }
    RatingPromptManager.shared.ownerProvider = { self.owner }
    RemotePromptEngine.shared.ownerProvider = { self.owner }
    for account in ["user-a", "user-b"] {
      owner = account
      RatingPromptManager.shared.resetForTesting()
      RemotePromptEngine.shared.resetForTesting()
    }
    owner = "user-a"
  }

  override func tearDown() async throws {
    for account in ["user-a", "user-b"] {
      owner = account
      RatingPromptManager.shared.resetForTesting()
      RemotePromptEngine.shared.resetForTesting()
    }
    RatingPromptManager.shared.ownerProvider = { RuntimeOwnerIdentity.currentOwnerId() ?? "anonymous" }
    RemotePromptEngine.shared.ownerProvider = { RuntimeOwnerIdentity.currentOwnerId() ?? "anonymous" }
    RatingPromptManager.shared.remoteDisableCheck = {
      PostHogManager.shared.isFeatureEnabled(RatingPromptPolicy.killSwitchFlag)
    }
  }

  func testRatingSubmissionDoesNotSuppressTheNextAccount() {
    for _ in 1...3 { RatingPromptManager.shared.recordQuestionAsked() }
    RatingPromptManager.shared.submit(rating: 5)
    XCTAssertEqual(RatingPromptManager.shared.submittedRating, 5)

    // Switch accounts: a fresh user must start from zero, still eligible.
    owner = "user-b"
    XCTAssertEqual(RatingPromptManager.shared.questionCount, 0)
    XCTAssertEqual(RatingPromptManager.shared.submittedRating, 0)
    for _ in 1...3 { RatingPromptManager.shared.recordQuestionAsked() }
    RatingPromptManager.shared.flagsDidUpdate()
    XCTAssertTrue(RatingPromptManager.shared.isVisible)

    // And switching back preserves the first account's submission.
    owner = "user-a"
    XCTAssertEqual(RatingPromptManager.shared.submittedRating, 5)
  }

  func testRemotePromptResolutionIsPerAccount() async {
    let spec = RemotePromptSpec(
      id: "launch-note", type: "banner", question: "Hi", options: [],
      ctaLabel: "Open", ctaURL: "https://omi.me", triggerKind: "app_launch", triggerCount: 0)
    RemotePromptEngine.shared.isSignedInCheck = { true }
    RemotePromptEngine.shared.fetch = { [spec] }
    await RemotePromptEngine.shared.refreshFromServer()
    // Now that the spec is loaded, clear any resolution persisted by a
    // previous test-runner process, and free the slot for both accounts.
    for account in ["user-a", "user-b"] {
      owner = account
      RemotePromptEngine.shared.resetForTesting()
      RatingPromptManager.shared.dismiss()
    }
    owner = "user-a"

    await RemotePromptEngine.shared.refreshFromServer()
    XCTAssertEqual(RemotePromptEngine.shared.current?.id, "launch-note")
    RemotePromptEngine.shared.dismissCurrent()
    await RemotePromptEngine.shared.refreshFromServer()
    XCTAssertNil(RemotePromptEngine.shared.current)

    // The other account is still eligible for the same prompt.
    owner = "user-b"
    await RemotePromptEngine.shared.refreshFromServer()
    XCTAssertEqual(RemotePromptEngine.shared.current?.id, "launch-note")

    RemotePromptEngine.shared.fetch = { [] }
    await RemotePromptEngine.shared.refreshFromServer()
  }

  func testLegacyGlobalStateMigratesToTheFirstAccountOnly() {
    UserDefaults.standard.set(4, forKey: DefaultsKey.ratingPromptQuestionCount.rawValue)
    UserDefaults.standard.set(true, forKey: DefaultsKey.ratingPromptDismissed.rawValue)

    // First scoped read migrates the pre-scoping global keys to user-a…
    XCTAssertEqual(RatingPromptManager.shared.questionCount, 4)
    XCTAssertTrue(RatingPromptManager.shared.isDismissed)
    XCTAssertNil(UserDefaults.standard.object(forKey: DefaultsKey.ratingPromptQuestionCount.rawValue))

    // …and user-b starts clean.
    owner = "user-b"
    XCTAssertEqual(RatingPromptManager.shared.questionCount, 0)
    XCTAssertFalse(RatingPromptManager.shared.isDismissed)
  }
}
