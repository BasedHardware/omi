import XCTest

@testable import Omi_Computer

/// The decision that keeps "what's on my screen?" from being answered with a
/// photograph of the window it was typed into. Pure and clock-free: every age
/// is an input, so the staleness boundary is asserted exactly.
final class ScreenContextFallbackPolicyTests: XCTestCase {
  func testNonMainChatOwnersKeepTurnScopedLiveCapture() {
    // Voice and floating surfaces interject while the user is *inside* the
    // other app, so the live capture is the subject they mean. No age, however
    // fresh or stale, changes that.
    let owners: [ChatTurnOwner] = [
      .floatingDefault,
      .floatingVoice,
      .taskChat("task-1"),
      .agentPill(UUID()),
    ]
    for owner in owners {
      XCTAssertEqual(
        ScreenContextFallbackPolicy.evidenceSource(
          turnOwner: owner, lastExternalFrameAgeSeconds: 0),
        .turnScopedLiveCapture,
        "\(owner) must never fall back to a stored frame"
      )
      XCTAssertEqual(
        ScreenContextFallbackPolicy.evidenceSource(
          turnOwner: owner, lastExternalFrameAgeSeconds: nil),
        .turnScopedLiveCapture
      )
    }
  }

  func testMainChatWithoutFrameIsUnavailableRatherThanSelfPortrait() {
    XCTAssertEqual(
      ScreenContextFallbackPolicy.evidenceSource(
        turnOwner: .mainChat, lastExternalFrameAgeSeconds: nil),
      .unavailable(.noAttachableFrame)
    )
  }

  func testMainChatFreshFrameStandsInForTheScreen() {
    XCTAssertEqual(
      ScreenContextFallbackPolicy.evidenceSource(
        turnOwner: .mainChat, lastExternalFrameAgeSeconds: 30),
      .lastExternalFrame
    )
  }

  func testMainChatStalenessBoundaryIsInclusive() {
    let maxAge = ScreenContextFallbackPolicy.maxFallbackFrameAgeSeconds
    XCTAssertEqual(
      ScreenContextFallbackPolicy.evidenceSource(
        turnOwner: .mainChat, lastExternalFrameAgeSeconds: maxAge),
      .lastExternalFrame
    )
    XCTAssertEqual(
      ScreenContextFallbackPolicy.evidenceSource(
        turnOwner: .mainChat,
        lastExternalFrameAgeSeconds: maxAge.nextUp
      ),
      .unavailable(.frameTooStale(ageSeconds: Int(maxAge.nextUp.rounded())))
    )
  }

  func testMainChatNegativeAgeIsTreatedAsFresh() {
    // A clock skew between the frame store and this decision must not read as
    // staleness.
    XCTAssertEqual(
      ScreenContextFallbackPolicy.evidenceSource(
        turnOwner: .mainChat, lastExternalFrameAgeSeconds: -5),
      .lastExternalFrame
    )
  }

  func testCustomBoundOverridesTheDefault() {
    XCTAssertEqual(
      ScreenContextFallbackPolicy.evidenceSource(
        turnOwner: .mainChat, lastExternalFrameAgeSeconds: 90, maxAgeSeconds: 60),
      .unavailable(.frameTooStale(ageSeconds: 90))
    )
  }
}
