import XCTest

@testable import Omi_Computer

/// Regression coverage for `OnboardingPagedIntroCoordinator.fileScanReachedTerminalState`.
/// The onboarding file-scan step used to gate its Continue button on
/// `scanSnapshot != nil`. But a failed scan (`.failed`) and a scan that indexed
/// zero files (`.complete` with a nil snapshot — e.g. the user skipped Full Disk
/// Access) both leave `scanSnapshot` nil, so the button never appeared and the
/// user was trapped on a perpetual "Scanning…" screen. Continue must open on any
/// terminal scan state.
@MainActor
final class OnboardingFileScanGateTests: XCTestCase {
  func testContinueGateStaysClosedWhileScanning() {
    XCTAssertFalse(OnboardingPagedIntroCoordinator.fileScanReachedTerminalState(.idle))
    XCTAssertFalse(OnboardingPagedIntroCoordinator.fileScanReachedTerminalState(.scanning))
  }

  func testContinueGateOpensOnEveryTerminalState() {
    // Complete (incl. the zero-indexed-files case that leaves scanSnapshot nil).
    XCTAssertTrue(OnboardingPagedIntroCoordinator.fileScanReachedTerminalState(.complete))
    // Failed — the previous dead-end. The user must still be able to continue.
    XCTAssertTrue(
      OnboardingPagedIntroCoordinator.fileScanReachedTerminalState(.failed("scan_files error: no access")))
  }
}
