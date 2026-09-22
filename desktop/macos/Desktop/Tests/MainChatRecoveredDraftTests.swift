import XCTest

@testable import Omi_Computer

@MainActor
final class MainChatRecoveredDraftTests: XCTestCase {
  func testColdComposerMergesItsRestoredDraftOnlyWhenItConsumesRecovery() {
    let store = MainChatNavigationRequestStore()
    store.request(draft: "Recovered voice question", disposition: .append)
    XCTAssertTrue(store.consume())
    // The provider may not exist when Review is clicked. Its disk draft is
    // supplied after hydration, not guessed from a weak provider reference.
    XCTAssertEqual(
      store.consumeDraft(existingDraft: "Draft restored from disk"),
      "Draft restored from disk\n\nRecovered voice question")
    XCTAssertNil(store.consumeDraft(existingDraft: "already merged"))
  }

  func testOrdinaryPrefillStillReplacesAndPlainNavigationClearsRecovery() {
    let store = MainChatNavigationRequestStore()
    store.request(draft: "Suggested question")
    XCTAssertEqual(store.consumeDraft(existingDraft: "old"), "Suggested question")
    store.request(draft: "Recovered", disposition: .append)
    store.request()
    XCTAssertNil(store.consumeDraft(existingDraft: "old"))
  }

  func testSameOwnerReauthenticationBeforeMountDropsRecoveredQuestion() throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    let snapshot = try XCTUnwrap(authority.capture(ownerID: "owner", expectedOwnerID: "owner"))
    let store = MainChatNavigationRequestStore(isAuthorized: { authority.isCurrent($0, ownerID: "owner") })
    store.request(draft: "Private question", disposition: .append, authorization: snapshot)
    authority.beginTransition()
    authority.endTransition(ownerID: "owner")
    XCTAssertNil(store.consumeDraft(existingDraft: "new session draft"))
  }

  func testRepeatedReviewDoesNotDuplicateIdenticalComposerText() {
    let store = MainChatNavigationRequestStore()
    store.request(draft: "Question", disposition: .append)
    XCTAssertEqual(store.consumeDraft(existingDraft: "Question"), "Question")
  }
}
