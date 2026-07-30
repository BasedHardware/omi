import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class OnboardingPinnedActionsLayoutTests: XCTestCase {
  func testActionsStayInsideCompactViewportWhenContentOverflows() {
    let recorder = OnboardingActionLayoutRecorder()
    let host = NSHostingView(
      rootView: OnboardingContentWithPinnedActions {
        Color.clear.frame(width: 280, height: 600)
      } actions: {
        OnboardingActionLayoutProbe(recorder: recorder) {
          Color.clear.frame(width: 160, height: 40)
        }
      }
      .frame(width: 320, height: 180)
    )
    host.frame = NSRect(x: 0, y: 0, width: 320, height: 180)
    host.layoutSubtreeIfNeeded()

    guard let actionFrame = recorder.frame else {
      return XCTFail("the pinned action row was never placed")
    }
    XCTAssertGreaterThanOrEqual(actionFrame.minY, -0.5)
    XCTAssertLessThanOrEqual(actionFrame.maxY, 180.5)
  }
}

private final class OnboardingActionLayoutRecorder: @unchecked Sendable {
  private(set) var frame: CGRect?

  func record(_ frame: CGRect) {
    self.frame = frame
  }
}

private struct OnboardingActionLayoutProbe: Layout {
  let recorder: OnboardingActionLayoutRecorder

  func sizeThatFits(
    proposal: ProposedViewSize,
    subviews: Subviews,
    cache: inout ()
  ) -> CGSize {
    subviews.first?.sizeThatFits(proposal) ?? .zero
  }

  func placeSubviews(
    in bounds: CGRect,
    proposal: ProposedViewSize,
    subviews: Subviews,
    cache: inout ()
  ) {
    recorder.record(bounds)
    for subview in subviews {
      subview.place(at: bounds.origin, proposal: ProposedViewSize(bounds.size))
    }
  }
}
