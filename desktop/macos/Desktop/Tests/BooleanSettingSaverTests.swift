import XCTest

@testable import Omi_Computer

/// Regression coverage for Settings toggles (Daily Summary, Store Recordings, Private Cloud Sync)
/// that bind straight to the switch shown on screen.
///
/// A failed save used to be only logged: the switch stayed on the side the user picked while the
/// account kept its old value, and the next Settings load quietly flipped it back with no message.
/// The fake account below refuses saves while offline; the switch used to keep the user's pick
/// whatever the save answered, which in these terms is `.saved` for a save the account refused.
/// That fails `testFailedSavePutsBackTheValueTheAccountHolds`.
@MainActor
final class BooleanSettingSaverTests: XCTestCase {

  /// The account's stored value. A save replaces it.
  private final class FakeAccount {
    private(set) var value: Bool
    var isOffline = false

    init(value: Bool) {
      self.value = value
    }

    func save(_ newValue: Bool) throws {
      guard !isOffline else { throw SaveFailure() }
      value = newValue
    }
  }

  private struct SaveFailure: Error {}

  func testFailedSavePutsBackTheValueTheAccountHolds() async {
    let account = FakeAccount(value: false)
    account.isOffline = true

    // The switch is already flipped on; Settings read `false` from the account.
    let outcome = await BooleanSettingSaver.save(
      true,
      description: "store recordings",
      lastConfirmed: { false },
      write: { try account.save($0) }
    )

    XCTAssertEqual(outcome, .failed(restore: false))
    XCTAssertEqual(account.value, false)
  }

  func testFailureIsReportedEvenBeforeSettingsReadTheAccount() async {
    let account = FakeAccount(value: false)
    account.isOffline = true

    // Settings has not read the account's value, so no value is known to put back.
    let outcome = await BooleanSettingSaver.save(
      true,
      description: "store recordings",
      lastConfirmed: { nil },
      write: { try account.save($0) }
    )

    XCTAssertEqual(outcome, .failed(restore: nil))
  }

  func testSavedValueIsTheValueTheAccountHolds() async {
    let account = FakeAccount(value: false)

    let outcome = await BooleanSettingSaver.save(
      true,
      description: "store recordings",
      lastConfirmed: { false },
      write: { try account.save($0) }
    )

    XCTAssertEqual(outcome, .saved(true))
    XCTAssertEqual(account.value, true)
  }
}
