import XCTest

@testable import Omi_Computer

/// Active Neo is paid even when its non-premium Desktop capabilities use the
/// Free-tier floor. It must clear a stale trial flag before audio admission.
@MainActor
final class NeoDesktopPaywallTests: XCTestCase {
  private let paywallKey = "desktop_isPaywalled"

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: paywallKey)
    super.tearDown()
  }

  func testActiveNeoClearsStickyPaywallBeforeAudioStartAdmission() {
    let state = AppState()
    state.isPaywalled = true
    XCTAssertTrue(state.blockIfPaywalled(), "setup: stale paywall blocks audio admission")

    let limiter = FloatingBarUsageLimiter()
    limiter.applyPlan(plan: .unlimited, status: .active)

    XCTAssertFalse(state.isPaywalled)
    XCTAssertFalse(UserDefaults.standard.bool(forKey: paywallKey))
    XCTAssertFalse(state.blockIfPaywalled(), "active Neo must pass the audio-start paywall guard")
  }
}
