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

  /// The bar carries six flat pills and no menu. The claim worth holding is not the pill count —
  /// it is that **nothing was stranded when the menu was deleted** (INV-NAV-1). `reach` names the one
  /// mechanism responsible for each destination, so this fails the moment a pill is removed without
  /// the destination being moved somewhere that exists.
  func testEveryShellDestinationIsStillReachableWithoutAMenu() {
    XCTAssertEqual(
      TopNavigationRoutes.primaryItems.map(\.index),
      [
        SidebarNavItem.dashboard.rawValue,
        SidebarNavItem.conversations.rawValue,
        SidebarNavItem.tasks.rawValue,
        SidebarNavItem.rewind.rawValue,
        SidebarNavItem.insight.rawValue,
        SidebarNavItem.apps.rawValue,
      ]
    )
    XCTAssertEqual(TopNavigationRoutes.memoryDestinations, [.memories, .conversations, .brainMap])

    // No pill may instruct the user how to operate it. The retired menu's tooltip read "hover for
    // conversations, memories, tasks, Rewind", which is chrome apologising for itself.
    for item in TopNavigationRoutes.primaryItems {
      XCTAssertFalse(
        item.tooltip.lowercased().contains("hover"),
        "\(item.title) still tells the user to hover")
      XCTAssertFalse(item.tooltip.isEmpty)
    }

    XCTAssertEqual(
      ShellDestination.unreachable(), [],
      "a destination lost the only mechanism that reached it")

    // The three the retired menu owned are the hub's own views, and the hub itself has a pill.
    XCTAssertEqual(
      ShellDestination.allCases.filter { $0.reach == .memoryHubView }.compactMap(\.memoryDestination),
      [.conversations, .memories, .brainMap])
    XCTAssertEqual(ShellDestination.insights.navItem, .insight)
    // Home is a peer pill, not a brand mark: the eight-dot mark belongs to the query bar, where it
    // animates while Omi is answering.
    XCTAssertEqual(ShellDestination.home.navItem, .dashboard)
    XCTAssertEqual(ShellDestination.home.reach, .topBar)
    XCTAssertEqual(
      TopNavigationRoutes.primaryItems.first?.icon, "magnifyingglass",
      "Home must not spend the Omi mark on a static nav glyph")

  }

  /// A destination whose `reach` points at a page the bar does not have a pill for is exactly the
  /// stranding INV-NAV-1 forbids, so the checker has to *see* it rather than pass vacuously.
  func testTheReachabilityCheckerCatchesADestinationWhosePillWasRemoved() {
    let barWithoutInsights = TopNavigationRoutes.primaryItems.filter {
      $0.index != SidebarNavItem.insight.rawValue
    }
    XCTAssertEqual(
      ShellDestination.unreachable(fromBarItems: barWithoutInsights), [.insights],
      "Insights lost its pill and nothing noticed")

    let barWithoutLibrary = TopNavigationRoutes.primaryItems.filter {
      $0.index != SidebarNavItem.conversations.rawValue
    }
    XCTAssertEqual(
      Set(ShellDestination.unreachable(fromBarItems: barWithoutLibrary)),
      [.conversations, .memories, .brainMap],
      "without the Library pill the hub's three views have no way in")
  }

  func testLibraryPillReadsAsCurrentOnEveryHubView() {
    for destination in ShellDestination.allCases where destination.reach == .memoryHubView {
      XCTAssertTrue(
        ShellDestination.isHubPage(selectedIndex: destination.navItem.rawValue),
        "\(destination.title) must light the Library pill")
    }
    XCTAssertFalse(ShellDestination.isHubPage(selectedIndex: SidebarNavItem.dashboard.rawValue))
    XCTAssertFalse(ShellDestination.isHubPage(selectedIndex: SidebarNavItem.apps.rawValue))
  }

  /// The badge used to be one number on `Library` covering conversations, memories *and* tasks,
  /// because Tasks lived inside the menu. Tasks has its own pill now, so a task counted on `Library`
  /// would point at the wrong page.
  func testNewItemCountsAreCarriedByThePillThatOwnsThem() {
    let badges = TopNavigationDestinationBadges(library: 4, tasks: 7)
    XCTAssertEqual(badges.count(forNavItemIndex: SidebarNavItem.conversations.rawValue), 4)
    XCTAssertEqual(badges.count(forNavItemIndex: SidebarNavItem.tasks.rawValue), 7)
    XCTAssertEqual(badges.count(forNavItemIndex: SidebarNavItem.apps.rawValue), 0)
    XCTAssertEqual(badges.count(forNavItemIndex: SidebarNavItem.rewind.rawValue), 0)
    XCTAssertEqual(badges.count(forNavItemIndex: SidebarNavItem.insight.rawValue), 0)
  }

  /// **The reason the flat row is allowed to exist.** A row of five named pills is only better than
  /// a menu if it actually fits — otherwise it silently becomes the compact `Navigate` menu, which is
  /// the same disclosure with a worse label.
  ///
  /// Hosts the *real* row — real labels, real icons — beside the real trailing-control widths at the
  /// narrowest window `DesktopWindowLayoutPolicy` allows, with a two-digit badge on both pills that
  /// can carry one. `ViewThatFits` picking the compact alternative is the failure.
  func testTheFlatDestinationRowFitsTheNarrowestWindowWithoutTheCompactFallback() {
    let lane = TopNavigationLayoutMetrics.contentLaneWidth(for: DesktopWindowLayoutPolicy.width)
    let inset = TopNavigationLayoutMetrics.barContentInset
    let recorder = TopNavigationLayoutRecorder()
    let host = NSHostingView(
      rootView: TopNavigationBarLayout(
        expandedNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .expanded) {
            TopNavigationDestinationRow(
              selectedIndex: SidebarNavItem.dashboard.rawValue,
              badges: TopNavigationDestinationBadges(library: 99, tasks: 99),
              onSelect: { _ in }
            )
          }
        },
        compactNavigation: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .compact) {
            Color.clear.frame(width: 68, height: 32)
          }
        },
        persistentControls: {
          Color.clear.frame(
            width: TopNavigationLayoutMetrics.persistentControlsWidth, height: 32)
        },
        settings: {
          Color.clear.frame(width: TopNavigationLayoutMetrics.settingsControlWidth, height: 32)
        }
      )
      .padding(.horizontal, inset)
      .frame(width: lane, height: TopNavigationLayoutMetrics.barHeight)
    )
    host.frame = NSRect(x: 0, y: 0, width: lane, height: TopNavigationLayoutMetrics.barHeight)
    host.layoutSubtreeIfNeeded()

    XCTAssertNil(
      recorder.frame(of: .compact),
      "the flat destination row overflowed the narrowest window and fell back to a menu")
    guard let navigation = recorder.frame(of: .expanded) else {
      return XCTFail("the expanded destination row was never placed")
    }
    XCTAssertGreaterThan(navigation.width, 0)
    XCTAssertLessThanOrEqual(navigation.width, lane - inset * 2)
  }

  func testNavigationLaneMatchesFullChatWidthAndPageInsets() {
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 1_400), 900)
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 800), 768)
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 40), 8)
  }

  /// The bar's *glass* is the lane and its controls are inset inside it — so the inset has to leave a
  /// real row behind at the narrowest window the shell allows.
  ///
  /// The failure this guards is silent: `.padding` then `.frame(width:)` clamps a negative inner width
  /// to zero rather than complaining, so an inset grown past the lane produces an empty bar and a
  /// clean build.
  func testTheBarsContentSurvivesItsInsetAtTheNarrowestWindow() {
    let lane = TopNavigationLayoutMetrics.contentLaneWidth(for: DesktopWindowLayoutPolicy.width)
    let row = lane - TopNavigationLayoutMetrics.barContentInset * 2

    XCTAssertGreaterThan(row, 0, "the bar's inset swallowed its own row")
    // Enough for the compact fallback: the menu, the status icons and the gear with their spacings.
    XCTAssertGreaterThan(
      row, 300,
      "at the minimum window width the bar must still fit its compact row without clipping")
  }

  /// The row is laid out inside the inset, not inside the glass — so the leading pill starts one
  /// spacing token in from the panel edge rather than flush against the corner.
  func testTheRowIsPlacedInsideTheBarsInsetRatherThanAgainstItsCorner() {
    let lane = TopNavigationLayoutMetrics.contentLaneWidth(for: 1_400)
    let inset = TopNavigationLayoutMetrics.barContentInset
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
      // Exactly what `DesktopTopBar` builds: the inset, then the lane, then the glass.
      .padding(.horizontal, inset)
      .frame(width: lane, height: TopNavigationLayoutMetrics.barHeight)
    )
    host.frame = NSRect(
      x: 0, y: 0, width: lane, height: TopNavigationLayoutMetrics.barHeight)
    host.layoutSubtreeIfNeeded()

    guard
      let navigation = recorder.frame(of: .expanded),
      let settings = recorder.frame(of: .settings)
    else {
      return XCTFail("expected the expanded row to be placed inside the bar")
    }
    // Measured leading-to-trailing rather than against an absolute origin: what has to be true is
    // that the row is the lane *minus its inset on both sides*, whatever coordinate space SwiftUI
    // hands the layout. Drop the padding and this is `lane`.
    XCTAssertEqual(
      settings.maxX - navigation.minX, lane - inset * 2, accuracy: 0.5,
      "the row must be laid out inside the bar's inset, not against its corner")
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
