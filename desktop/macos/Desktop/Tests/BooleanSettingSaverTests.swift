import XCTest

@testable import Omi_Computer

/// Regression coverage for Settings switches that stay flipped after the account refuses the save.
///
/// Daily Summary, Store Recordings and Private Cloud Sync change on screen, then send that value to
/// the account. When the request failed, the failure was only logged: the pane kept a setting the
/// account never stored, and the next Settings load quietly put the old value back.
@MainActor
final class BooleanSettingSaverTests: XCTestCase {
  private struct SaveFailure: Error {}

  func testFailedFlipPutsBackTheValueTheAccountHolds() async {
    var stored = false
    let outcome = await BooleanSettingSaver.save(
      true,
      lastConfirmed: { false },
      isLatestEdit: { true },
      write: { _ in
        stored = false
        throw SaveFailure()
      }
    )

    XCTAssertEqual(outcome, .failed(restore: false))
    XCTAssertFalse(stored)
  }

  func testFailedFlipBeforeSettingsReadTheAccountRestoresThePreviousSide() async {
    let outcome = await BooleanSettingSaver.save(
      true,
      lastConfirmed: { nil },
      isLatestEdit: { true },
      write: { _ in throw SaveFailure() }
    )

    XCTAssertEqual(outcome, .failed(restore: false))
  }

  func testSuccessfulFlipReportsTheStoredValue() async {
    var stored = false
    let outcome = await BooleanSettingSaver.save(
      true,
      lastConfirmed: { false },
      isLatestEdit: { true },
      write: { requested in stored = requested }
    )

    XCTAssertEqual(outcome, .saved(true))
    XCTAssertTrue(stored)
  }

  func testFailureIsLeftToANewerFlip() async {
    let outcome = await BooleanSettingSaver.save(
      true,
      lastConfirmed: { false },
      isLatestEdit: { false },
      write: { _ in throw SaveFailure() }
    )

    XCTAssertEqual(outcome, .superseded)
  }
}
