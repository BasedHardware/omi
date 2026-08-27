import XCTest

@testable import Omi_Computer

/// The developer-keys section hints which BYOK keys are still missing while
/// only some of the four are entered, so someone who pastes a single key
/// learns the free plan needs all four at the same time.
final class BYOKIncompleteHintTests: XCTestCase {
  func testHintOnlyForPartiallyFilledKeySet() {
    let hint = byokMissingKeysHint(["sk-test", "", "", ""])
    XCTAssertEqual(
      hint,
      "Still missing: OpenAI, Anthropic, Gemini. All 4 keys must be entered at the same time to activate the free plan."
    )
    XCTAssertNil(byokMissingKeysHint(["", "", "", ""]), "blank form shows no hint")
    XCTAssertNil(byokMissingKeysHint(["a", "b", "c", "d"]), "complete form shows no hint")
  }
}

/// The developer-keys fields are `SecureField`s bound straight to `@AppStorage`,
/// so the binding is written on every character. Reconciling on each of those
/// writes sent half-typed keys to four provider auth endpoints and flapped the
/// backend free-plan flag once per keystroke; simply opening the pane with no
/// keys at all still spent a `deactivateBYOK` + plan refetch. These pin the
/// decision the settled key set drives, separately from performing it.
final class BYOKReconciliationTests: XCTestCase {
  func testCompleteKeySetIsValidatedBeforeActivation() {
    XCTAssertEqual(
      BYOKReconciliation.action(
        forKeys: ["sk-a", "sk-b", "sk-c", "sk-d"],
        hasCheckedStatuses: false,
        hasActivationError: false),
      .validateAndActivate)
  }

  func testUntouchedEmptyFormNeverReachesTheNetwork() {
    XCTAssertEqual(
      BYOKReconciliation.action(
        forKeys: ["", "", "", ""],
        hasCheckedStatuses: false,
        hasActivationError: false),
      .none,
      "opening Advanced with no BYOK keys must not spend a deactivate + plan refetch")
  }

  func testClearingKeysStillDeactivates() {
    XCTAssertEqual(
      BYOKReconciliation.action(
        forKeys: ["", "", "", ""],
        hasCheckedStatuses: true,
        hasActivationError: false),
      .deactivate,
      "keys that were just cleared have a free plan to turn back off")

    XCTAssertEqual(
      BYOKReconciliation.action(
        forKeys: ["", "", "", ""],
        hasCheckedStatuses: false,
        hasActivationError: true),
      .deactivate,
      "a standing activation error is state to reconcile away")
  }

  func testPartialKeySetCannotActivate() {
    XCTAssertEqual(
      BYOKReconciliation.action(
        forKeys: ["sk-a", "", "", ""],
        hasCheckedStatuses: false,
        hasActivationError: false),
      .deactivate)
  }

  func testWhitespaceOnlyKeyDoesNotCount() {
    XCTAssertEqual(
      BYOKReconciliation.action(
        forKeys: ["sk-a", "sk-b", "sk-c", "   \n"],
        hasCheckedStatuses: false,
        hasActivationError: false),
      .deactivate,
      "a field holding only whitespace is not a key — `APIKeyService.byokKey` trims it away too")
  }
}
