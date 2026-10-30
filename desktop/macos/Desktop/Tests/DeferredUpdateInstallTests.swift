import XCTest

@testable import Omi_Computer

final class DeferredUpdateInstallTests: XCTestCase {
  func testNoCaptureActivityInstallsImmediately() {
    XCTAssertNil(
      DeferredUpdateInstall.nextDelay(
        now: Date(timeIntervalSince1970: 1_000),
        lastActivityAt: nil,
        silenceWindow: 120
      )
    )
  }

  func testExpiredSilenceWindowInstallsImmediately() {
    let now = Date(timeIntervalSince1970: 1_000)
    XCTAssertNil(
      DeferredUpdateInstall.nextDelay(
        now: now,
        lastActivityAt: now.addingTimeInterval(-121),
        silenceWindow: 120
      )
    )
  }

  func testRecentActivityWaitsForRemainingSilenceWindow() {
    let now = Date(timeIntervalSince1970: 1_000)
    XCTAssertEqual(
      DeferredUpdateInstall.nextDelay(
        now: now,
        lastActivityAt: now.addingTimeInterval(-30),
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
        lastActivityAt: now.addingTimeInterval(-119),
        silenceWindow: 120,
        minimumRetryDelay: 5
      ),
      5
    )
  }

  func testCancelPreventsDeferredInstallFromFiring() {
    var installed = false
    let deferred = DeferredUpdateInstall(
      version: "0.12.149",
      silenceWindow: 120,
      lastActivityProvider: { nil },
      install: { installed = true }
    )
    deferred.cancel()
    deferred.start(now: Date(timeIntervalSince1970: 1_000))
    XCTAssertFalse(installed, "cancel() must block install even if start() runs afterward")
  }

  func testDeferralCapInstallsEvenWhileCaptureStaysActive() {
    let now = Date(timeIntervalSince1970: 20_000)
    XCTAssertEqual(
      DeferredUpdateInstall.nextDelay(
        now: now,
        lastActivityAt: now,
        silenceWindow: 120,
        deferredSince: now.addingTimeInterval(-60),
        maximumDeferral: 3_600
      ),
      120
    )
    XCTAssertNil(
      DeferredUpdateInstall.nextDelay(
        now: now,
        lastActivityAt: now,
        silenceWindow: 120,
        deferredSince: now.addingTimeInterval(-3_600),
        maximumDeferral: 3_600
      )
    )
  }

  func testCapCountsFromTheFirstDeferralWhenAnUpdateIsReoffered() {
    var installed = false
    let now = Date()
    let reoffered = DeferredUpdateInstall(
      version: "0.12.388",
      silenceWindow: 120,
      maximumDeferral: 3_600,
      deferredSince: now.addingTimeInterval(-3_600),
      lastActivityProvider: { now },
      install: { installed = true }
    )
    reoffered.start(now: now)
    XCTAssertTrue(installed, "a re-offered update must not restart the deferral cap")
  }

  func testStartInstallsOnceTheDeferralCapHasElapsed() {
    var installed = false
    let deferred = DeferredUpdateInstall(
      version: "0.12.388",
      silenceWindow: 120,
      maximumDeferral: 0,
      lastActivityProvider: { Date() },
      install: { installed = true }
    )
    deferred.start(now: Date())
    XCTAssertTrue(installed, "a zero cap must not wait on a meeting that never ends")
  }
}
