import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

@MainActor
final class TopNavigationBarLayoutTests: XCTestCase {
  func testExpandedNavigationUsesLaneLeadingEdgeAndPinsPersistentControlsToTrailingEdge() {
    let laneWidth = TopNavigationLayoutMetrics.contentLaneWidth(for: 1_400)
    let recorder = TopNavigationLayoutRecorder()
    let host = NSHostingView(
      rootView: TopNavigationBarLayout(
        expandedNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .expanded) {
            Color.clear.frame(width: 420, height: 32)
          }
        },
        compactNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .compact) {
            Color.clear.frame(width: 68, height: 32)
          }
        },
        persistentControls: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .persistentControls) {
            Color.clear.frame(width: 150, height: 32)
          }
        },
        settings: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .settings) {
            Color.clear.frame(width: 32, height: 32)
          }
        }
      )
      .frame(width: laneWidth, height: 44)
    )
    host.frame = NSRect(x: 0, y: 0, width: laneWidth, height: 44)
    host.layoutSubtreeIfNeeded()

    guard
      let navigation = recorder.frame(of: .expanded),
      let persistentControls = recorder.frame(of: .persistentControls),
      let settings = recorder.frame(of: .settings)
    else {
      return XCTFail("expected expanded navigation and persistent controls to be placed")
    }
    XCTAssertEqual(navigation.minX, 0, accuracy: 0.5)
    XCTAssertEqual(settings.maxX, laneWidth, accuracy: 0.5)
    XCTAssertEqual(persistentControls.maxX, settings.minX - OmiSpacing.md, accuracy: 0.5)
  }

  func testCompactNavigationIsPlacedWhenTheFullTopBarWouldOverflow() {
    let recorder = TopNavigationLayoutRecorder()
    let host = NSHostingView(
      rootView: TopNavigationBarLayout(
        expandedNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .expanded) {
            Color.clear.frame(width: 420, height: 32)
          }
        },
        compactNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .compact) {
            Color.clear.frame(width: 68, height: 32)
          }
        },
        persistentControls: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .persistentControls) {
            Color.clear.frame(width: 150, height: 32)
          }
        },
        settings: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .settings) {
            Color.clear.frame(width: 32, height: 32)
          }
        }
      )
      .frame(width: 300, height: 44)
    )
    host.frame = NSRect(x: 0, y: 0, width: 300, height: 44)
    host.layoutSubtreeIfNeeded()

    XCTAssertNil(recorder.frame(of: .expanded))
    guard let compact = recorder.frame(of: .compact) else {
      return XCTFail("the compact navigation was never placed")
    }
    XCTAssertEqual(compact.minX, 0, accuracy: 0.5)
    XCTAssertLessThanOrEqual(compact.maxX, 300.5)

    guard
      let persistentControls = recorder.frame(of: .persistentControls),
      let settings = recorder.frame(of: .settings)
    else {
      return XCTFail("the persistent controls were never placed")
    }
    XCTAssertGreaterThan(persistentControls.minX, compact.maxX)
    XCTAssertEqual(persistentControls.maxX, settings.minX - OmiSpacing.md, accuracy: 0.5)
    XCTAssertGreaterThanOrEqual(settings.maxX, 299)
    XCTAssertLessThanOrEqual(settings.maxX, 300.5)
  }

  func testNavigationIsClippedRatherThanOverlappingPersistentControlsWhenCompactRowOverflows() {
    // Expanded = 500pt nav, compact = 200pt nav, controls = 200pt, settings = 32pt.
    // At a 300pt host the compact row (200 + spacing*3 + 200 + spacing + 32 ≈ 642)
    // still overflows. Verify navigation does not overlap the persistent controls.
    let recorder = TopNavigationLayoutRecorder()
    let host = NSHostingView(
      rootView: TopNavigationBarLayout(
        expandedNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .expanded) {
            Color.clear.frame(width: 500, height: 32)
          }
        },
        compactNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .compact) {
            Color.clear.frame(width: 200, height: 32)
          }
        },
        persistentControls: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .persistentControls) {
            Color.clear.frame(width: 200, height: 32)
          }
        },
        settings: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .settings) {
            Color.clear.frame(width: 32, height: 32)
          }
        }
      )
      .frame(width: 300, height: 44)
    )
    host.frame = NSRect(x: 0, y: 0, width: 300, height: 44)
    host.layoutSubtreeIfNeeded()

    guard
      let navigation = recorder.frame(of: .compact),
      let controls = recorder.frame(of: .persistentControls)
    else {
      return XCTFail("expected compact navigation and persistent controls to be placed")
    }
    // Navigation's proposed width must not cause it to overlap the controls.
    XCTAssertLessThanOrEqual(
      navigation.maxX,
      controls.minX,
      "compact navigation must not overlap persistent controls even when the row overflows"
    )
  }

  func testCompactNavigationRetainsEveryPrimaryRouteAndMemoryDestination() {
    XCTAssertEqual(
      TopNavigationRoutes.primaryItems.map(\.index),
      [
        SidebarNavItem.dashboard.rawValue,
        SidebarNavItem.conversations.rawValue,
        SidebarNavItem.tasks.rawValue,
        SidebarNavItem.apps.rawValue,
      ]
    )
    XCTAssertEqual(TopNavigationRoutes.memoryDestinations, [.memories, .conversations, .brainMap])
  }

  func testNavigationLaneMatchesFullChatWidthAndPageInsets() {
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 1_400), 900)
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 800), 768)
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 40), 8)
  }

  func testListeningHoverControlsHaveAStableReservedSlot() {
    // The secondary mode toggle is conditional on hover, so the slot—not the
    // conditional child—owns the measured width used by the right nav group.
    XCTAssertEqual(CaptureListeningControlsLayout.listeningSlotWidth, 136)
    XCTAssertGreaterThan(CaptureListeningControlsLayout.listeningSlotWidth, 104)
  }
}

private enum TopNavigationLayoutSlot: Hashable {
  case expanded
  case compact
  case persistentControls
  case settings
}

private final class TopNavigationLayoutRecorder: @unchecked Sendable {
  private var frames: [TopNavigationLayoutSlot: CGRect] = [:]

  func record(_ slot: TopNavigationLayoutSlot, _ frame: CGRect) {
    frames[slot] = frame
  }

  func frame(of slot: TopNavigationLayoutSlot) -> CGRect? {
    frames[slot]
  }
}

private struct TopNavigationLayoutProbe: Layout {
  let recorder: TopNavigationLayoutRecorder
  let slot: TopNavigationLayoutSlot

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
    recorder.record(slot, bounds)
    for subview in subviews {
      subview.place(at: bounds.origin, proposal: ProposedViewSize(bounds.size))
    }
  }
}
