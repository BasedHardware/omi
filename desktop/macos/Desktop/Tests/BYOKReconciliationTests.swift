import XCTest

@testable import Omi_Computer

/// The developer-keys fields are `SecureField`s bound straight to `@AppStorage`,
/// so the binding is written on every character. Reconciling on each of those
/// writes sent half-typed keys to provider auth endpoints and flapped the
/// backend free-plan flag once per keystroke; simply opening the pane with no
/// keys at all still spent a `deactivateBYOK` + plan refetch. These pin the
/// decision the settled key set drives, separately from performing it.
final class BYOKReconciliationTests: XCTestCase {
  func testSelectedLLMKeyIsValidatedBeforeActivationWithoutDeepgram() {
    XCTAssertEqual(
      BYOKReconciliation.action(
        forKeys: ["sk-a"],
        hasCheckedStatuses: false,
        hasActivationError: false),
      .validateAndActivate)
  }

  func testUntouchedEmptyFormNeverReachesTheNetwork() {
    XCTAssertEqual(
      BYOKReconciliation.action(
        forKeys: [""],
        hasCheckedStatuses: false,
        hasActivationError: false),
      .none,
      "opening Advanced with no BYOK keys must not spend a deactivate + plan refetch")
  }

  func testClearingKeysStillDeactivates() {
    XCTAssertEqual(
      BYOKReconciliation.action(
        forKeys: [""],
        hasCheckedStatuses: true,
        hasActivationError: false),
      .deactivate,
      "keys that were just cleared have a free plan to turn back off")

    XCTAssertEqual(
      BYOKReconciliation.action(
        forKeys: [""],
        hasCheckedStatuses: false,
        hasActivationError: true),
      .deactivate,
      "a standing activation error is state to reconcile away")
  }

  func testWhitespaceOnlyKeyDoesNotCount() {
    XCTAssertEqual(
      BYOKReconciliation.action(
        forKeys: ["   \n"],
        hasCheckedStatuses: true,
        hasActivationError: false),
      .deactivate,
      "a field holding only whitespace is not a key — `APIKeyService.byokKey` trims it away too")
  }
}
