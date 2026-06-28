import XCTest

@testable import Omi_Computer

final class DeferredUpdateInstallTests: XCTestCase {
  func testNoRecentSpeechInstallsImmediately() {
    XCTAssertNil(
      DeferredUpdateInstall.nextDelay(
        now: Date(timeIntervalSince1970: 1_000),
        lastSpeechAt: nil,
        silenceWindow: 120
      )
    )
  }

  func testExpiredSilenceWindowInstallsImmediately() {
    let now = Date(timeIntervalSince1970: 1_000)
    XCTAssertNil(
      DeferredUpdateInstall.nextDelay(
        now: now,
        lastSpeechAt: now.addingTimeInterval(-121),
        silenceWindow: 120
      )
    )
  }

  func testRecentSpeechWaitsForRemainingSilenceWindow() {
    let now = Date(timeIntervalSince1970: 1_000)
    XCTAssertEqual(
      DeferredUpdateInstall.nextDelay(
        now: now,
        lastSpeechAt: now.addingTimeInterval(-30),
        silenceWindow: 120
      ),
      90
    )
  }

  func testNearBoundaryUsesMinimumRetryDelay() {
    let now = Date(timeIntervalSince1970: 1_000)
    XCTAssertEqual(
      DeferredUpdateInstall.nextDelay(
        now: now,
        lastSpeechAt: now.addingTimeInterval(-119),
        silenceWindow: 120,
        minimumRetryDelay: 5
      ),
      5
    )
  }
}
