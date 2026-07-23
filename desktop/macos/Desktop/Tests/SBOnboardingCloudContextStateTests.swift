import XCTest

@testable import Omi_Computer

/// Regression coverage for the onboarding ChatGPT/Claude connect chip (#new-onboarding).
///
/// The connect flow opens the provider's OAuth page in the browser and used to
/// check the local connection status immediately after — which always read "not
/// connected" (OAuth hadn't happened yet) and silently reset the chip to
/// "Connect", never flipping to "✓ on" even after a successful authorization.
/// Resolution now happens through a backend grant refresh when the app becomes
/// active again, mapped through `cloudContextState`.
final class SBOnboardingCloudContextStateTests: XCTestCase {

  func testConnectedFlipsChipOnFromAnyState() {
    for current in [nil, "idle", "connecting", "needsSignIn", "on"] {
      XCTAssertEqual(SBOnboardingModel.cloudContextState(current: current, connected: true), "on")
    }
  }

  func testUnfinishedConnectingResolvesToIdleSoConnectButtonReturns() {
    XCTAssertEqual(SBOnboardingModel.cloudContextState(current: "connecting", connected: false), "idle")
  }

  func testNotConnectedLeavesNonConnectingStatesUntouched() {
    for current in [nil, "idle", "on", "unavailable"] {
      XCTAssertNil(SBOnboardingModel.cloudContextState(current: current, connected: false))
    }
  }
}
