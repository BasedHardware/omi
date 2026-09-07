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

  /// The bar carries four flat destination pills and no destination menu. The claim worth holding is not the pill count —
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
        SidebarNavItem.apps.rawValue,
      ]
    )
    XCTAssertEqual(
      TopNavigationRoutes.memoryDestinations,
      [.memories, .conversations, .brainMap, .activity, .rewind])

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

    // The hub's other four pages are reached from Brain's section row, on the page the pill opens.
    // `Activity` itself is what the pill opens, so the bar is its own door.
    XCTAssertEqual(
      ShellDestination.allCases.filter { $0.reach == .activityChipRow }
        .compactMap(\.memoryDestination),
      [.conversations, .memories, .brainMap, .rewind])
    // The claim is checkable because the row and the model read one value. A page dropped from the
    // chip row is unreachable here rather than silently stranded in the app.
    for destination in ShellDestination.allCases where destination.reach == .activityChipRow {
      guard let hubView = destination.memoryDestination else {
        return XCTFail("\(destination.title) claims the chip row reaches it but names no hub page")
      }
      XCTAssertTrue(
        ActivityDestinationChip.reachableHubDestinations.contains(hubView),
        "\(destination.title) claims the chip row reaches it, but the row does not offer it")
    }
    XCTAssertEqual(ShellDestination.activity.reach, .topBar)

    // The pill names the view it opens. It used to say `Memories` and open whichever hub view was
    // persisted last, so the word on the bar and the page you got were only sometimes the same.
    let hubPill = TopNavigationRoutes.primaryItems.first {
      $0.index == SidebarNavItem.conversations.rawValue
    }
    XCTAssertEqual(hubPill?.title, "Memories")
    XCTAssertNotEqual(
      hubPill?.icon, "clock.arrow.circlepath",
      "the Brain pill must not wear Rewind's section glyph")
    // Chat is a peer pill, not a brand mark: the eight-dot mark belongs to the query bar, where it
    // animates while Omi is answering. The pill wears a chat glyph because the page IS the chat.
    XCTAssertEqual(ShellDestination.home.navItem, .dashboard)
    XCTAssertEqual(ShellDestination.home.reach, .topBar)
    XCTAssertEqual(
      TopNavigationRoutes.primaryItems.first?.icon, "bubble.left.and.text.bubble.right",
      "Chat must not spend the Omi mark on a static nav glyph")

  }

  /// **The page that had no door.** `PermissionsPage` renders correctly and always did — its only
  /// writer was the sidebar the glass shell stopped rendering, so the app reached a state where it
  /// told the user to fix permissions on a page nothing led to.
  ///
  /// Its door is a row in the Settings list, which the bar's gear opens. Three things have to hold
  /// together for that to be a door at all, so all three are asserted here: the row is in the list,
  /// the row mounts the **whole** page rather than a summary of it (INV-NAV-1 in the other
  /// direction), and the gear that opens Settings is still on the bar.
  func testTheStrandedUtilityPagesAreReachedThroughTheSettingsList() {
    for destination in [ShellDestination.permissions] {
      XCTAssertEqual(destination.reach, .settingsSidebar)
      guard let section = destination.settingsSection else {
        return XCTFail("\(destination.title) names no Settings row")
      }
      XCTAssertTrue(
        SettingsSidebarRoutes.visibleSections.contains(section),
        "\(destination.title) has a section but the Settings list does not show it")
      XCTAssertEqual(
        section.presentedPage, destination,
        "the \(section.rawValue) row must mount the page itself, not a reduced copy of it")
    }

    XCTAssertEqual(
      TopNavigationRoutes.persistentItems.map(\.index), [SidebarNavItem.settings.rawValue],
      "the gear is the only way into Settings, and the stranded page now lives behind it")
    XCTAssertTrue(
      TopNavigationRoutes.persistentItems.contains { $0.tooltip.lowercased().contains("permission") },
      "the gear has promised permissions all along — now it has to be telling the truth")
  }

  /// The trailing cluster is measured by `testTheFlatDestinationRowFitsTheNarrowestWindow…` as a
  /// constant, so a second persistent control would shrink the pill row without that test noticing.
  /// Tie the constant to the real list.
  func testTheSettingsControlWidthStillMatchesTheNumberOfPersistentControls() {
    XCTAssertEqual(
      TopNavigationLayoutMetrics.settingsControlWidth,
      CGFloat(TopNavigationRoutes.persistentItems.count) * 32,
      """
      the pinned trailing width no longer matches the controls actually rendered, so the narrowest\
      -window layout test is measuring a row the bar does not build
      """
    )
  }

  func testReferAFriendRemainsAvailableAfterAIAndAutomationInSettings() {
    guard
      let advanced = SettingsSidebarRoutes.visibleSections.firstIndex(of: .advanced),
      let referral = SettingsSidebarRoutes.visibleSections.firstIndex(of: .referral)
    else {
      return XCTFail("AI & Automation and Refer a Friend must both be visible Settings rows")
    }

    XCTAssertEqual(referral, advanced + 1)
  }

  func testOperationalStatusFollowsUpdateStatusWithoutPromotionalChrome() {
    let recorder = TopNavigationLayoutRecorder()
    let host = NSHostingView(
      rootView: TopNavigationTrailingControlsLayout(
        updateStatus: {
          TopNavigationLayoutProbe(recorder: recorder, slot: .updateStatus) {
            Color.clear.frame(width: 100, height: 32)
          }
        },
        statusControls: {
          HStack(spacing: 2) {
            TopNavigationLayoutProbe(recorder: recorder, slot: .microphone) {
              Color.clear.frame(width: 32, height: 32)
            }
            Color.clear.frame(width: 32, height: 32)
          }
        }
      )
    )
    host.frame = NSRect(x: 0, y: 0, width: 280, height: 32)
    host.layoutSubtreeIfNeeded()

    guard
      let updateStatus = recorder.frame(of: .updateStatus),
      let microphone = recorder.frame(of: .microphone)
    else {
      return XCTFail("expected every trailing control to be laid out")
    }

    XCTAssertEqual(microphone.minX, updateStatus.maxX + OmiSpacing.sm, accuracy: 0.5)
  }

  /// A destination whose `reach` points at a page the bar does not have a pill for is exactly the
  /// stranding INV-NAV-1 forbids, so the checker has to *see* it rather than pass vacuously.
  func testTheReachabilityCheckerCatchesADestinationWhosePillWasRemoved() {
    let barWithoutLibrary = TopNavigationRoutes.primaryItems.filter {
      $0.index != SidebarNavItem.conversations.rawValue
    }
    XCTAssertEqual(
      Set(ShellDestination.unreachable(fromBarItems: barWithoutLibrary)),
      [.conversations, .memories, .brainMap, .rewind, .activity],
      "without the Brain pill the section's views have no way in")
  }

  /// **The bridge's destination vocabulary, now that a test can reach it.** This mapping was a
  /// `private func` inside `DesktopHomeView`, so the names `omi-ctl navigate` accepts were asserted
  /// nowhere. `apps` and `integrations` both landing on the catalog matters most here: `Apps` is the
  /// only door to connectors and exports, and the bridge is how an agent reaches it without a cursor.
  func testTheBridgeResolvesEveryDestinationNameItAdvertises() {
    XCTAssertEqual(SidebarNavItem.automationDestination(named: "apps"), .apps)
    XCTAssertEqual(SidebarNavItem.automationDestination(named: "integrations"), .apps)
    XCTAssertEqual(SidebarNavItem.automationDestination(named: "rewind"), .rewind)
    XCTAssertEqual(SidebarNavItem.automationDestination(named: "tasks"), .tasks)
    XCTAssertEqual(SidebarNavItem.automationDestination(named: "conversations"), .conversations)

    // Home is the chat, so all three names resolve to it rather than to a destination that is gone.
    for name in ["dashboard", "home", "chat"] {
      XCTAssertEqual(SidebarNavItem.automationDestination(named: name), .dashboard, name)
    }

    // Case and separator folding is part of the contract callers rely on.
    XCTAssertEqual(SidebarNavItem.automationDestination(named: "Brain-Map"), nil)
    XCTAssertEqual(SidebarNavItem.automationDestination(named: "APPS"), .apps)
    XCTAssertNil(SidebarNavItem.automationDestination(named: "nowhere"))
  }

  /// **Apps is the only door to connectors and exports, so it has to be in the model that guards
  /// doors.** Home used to offer a second one — the ask bar's `Connect` tray, whose `More` opened the
  /// same `AppsPage` as a bounded card — and it disappeared with the hub when Home became the query
  /// surface. That cost nothing, because this pill was already here. But `Apps` was outside
  /// `ShellDestination` at the time, so `unreachable()` could not have told anyone either way, and
  /// deleting the pill would have stranded the catalog in silence. Both halves are asserted: it
  /// routes to the established page, and removing the pill is now a failure.
  func testAppsIsModelledSoItsPillCannotBeDeletedInSilence() {
    XCTAssertEqual(ShellDestination.apps.reach, .topBar)
    XCTAssertEqual(
      ShellDestination.apps.navItem, .apps,
      "Apps must route to the established catalog page, never a shell-local copy of it")
    XCTAssertNil(ShellDestination.apps.memoryDestination)
    XCTAssertNil(ShellDestination.apps.settingsSection)

    let barWithoutApps = TopNavigationRoutes.primaryItems.filter {
      $0.index != SidebarNavItem.apps.rawValue
    }
    XCTAssertEqual(
      ShellDestination.unreachable(fromBarItems: barWithoutApps), [.apps],
      "Apps lost its pill and nothing noticed — connectors and exports have no other door")
  }

  /// The same negative proof for the Settings list, because that is how `PermissionsPage` got
  /// stranded in the first place: the surface that wrote to it stopped rendering and nothing said
  /// so. Both ways of losing the door have to be visible to the checker — the row disappearing, and
  /// the gear that opens the list disappearing.
  func testTheReachabilityCheckerCatchesAPageWhoseSettingsDoorWasRemoved() {
    let listWithoutPermissions = SettingsSidebarRoutes.visibleSections.filter { $0 != .permissions }
    XCTAssertEqual(
      ShellDestination.unreachable(settingsSidebarSections: listWithoutPermissions), [.permissions],
      "Permissions lost its Settings row and nothing noticed")

    XCTAssertEqual(
      Set(ShellDestination.unreachable(persistentItems: [])),
      [.permissions],
      "without the gear there is no way into Settings, so the page behind it is stranded")
  }

  func testTheActivityPillReadsAsCurrentOnEveryHubPage() {
    for destination in ShellDestination.allCases
    where destination.reach == .activityChipRow || destination == .activity {
      XCTAssertTrue(
        ShellDestination.isHubPage(selectedIndex: destination.navItem.rawValue),
        "\(destination.title) must light the Brain pill")
    }
    XCTAssertFalse(ShellDestination.isHubPage(selectedIndex: SidebarNavItem.dashboard.rawValue))
    XCTAssertFalse(ShellDestination.isHubPage(selectedIndex: SidebarNavItem.apps.rawValue))
  }

  /// The badge used to be one number on the hub's pill — then labelled `Library` — covering
  /// conversations, memories *and* tasks, because Tasks lived inside the menu. Tasks has its own
  /// pill now, so a task counted on the hub's pill would point at the wrong page.
  func testNewItemCountsAreCarriedByThePillThatOwnsThem() {
    let badges = TopNavigationDestinationBadges(library: 4, tasks: 7)
    XCTAssertEqual(badges.count(forNavItemIndex: SidebarNavItem.conversations.rawValue), 4)
    XCTAssertEqual(badges.count(forNavItemIndex: SidebarNavItem.tasks.rawValue), 7)
    XCTAssertEqual(badges.count(forNavItemIndex: SidebarNavItem.apps.rawValue), 0)
    XCTAssertEqual(badges.count(forNavItemIndex: SidebarNavItem.rewind.rawValue), 0)
    XCTAssertEqual(badges.count(forNavItemIndex: SidebarNavItem.dashboard.rawValue), 0)
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
    // **Fitting only means something if what fitted is still a tab bar of every named segment.**
    // `ViewThatFits` is satisfied by anything narrow enough, so a control that had quietly stopped
    // drawing a segment would pass the check above and prove nothing. Deleting a segment makes this
    // test *easier*, which is exactly when a guard is worth having: two destinations were removed
    // from this row (`Insights` here, `Chat` earlier) and the assertion did not notice either. A
    // width floor did not notice either — three real segments are wider than four minimum ones —
    // so this counts what was rendered.
    assertEveryDestinationIsRendered(in: host, rowWidth: navigation.width)
    XCTAssertLessThanOrEqual(navigation.width, lane - inset * 2)
  }

  /// The rendered segment count, from the renderer that is actually on screen. Against the macOS 26
  /// SDK on macOS 26 the row is `EqualWidthSegments`, whose width is exactly `count × widest
  /// segment` plus the track inset, so a segment measured on its own gives the width four of them
  /// must add up to — a row missing one is a whole segment short. Everywhere else the row is the
  /// system segmented control, which says how many segments it has.
  private func assertEveryDestinationIsRendered(in host: NSView, rowWidth: CGFloat) {
    let items = TopNavigationRoutes.primaryItems
    #if compiler(>=6.2)
      if #available(macOS 26.0, *) {
        let badges = TopNavigationDestinationBadges(library: 99, tasks: 99)
        let widest =
          items.map { item in
            NSHostingView(
              rootView: TopNavigationGlassSegmentLabel(item: item, badges: badges, isSelected: false)
            ).fittingSize.width
          }.max() ?? 0
        XCTAssertGreaterThan(widest, TopNavigationSegmentMetrics.minimumSegmentWidth)
        XCTAssertEqual(
          rowWidth, widest * CGFloat(items.count) + TopNavigationGlassSegmentMetrics.trackInset * 2,
          accuracy: 1,
          "the row is not `\(items.count)` equal segments wide, so a destination is not being drawn")
        return
      }
    #endif
    let controls = segmentedControls(in: host)
    XCTAssertEqual(controls.count, 1, "the fallback row must be one system segmented control")
    XCTAssertEqual(
      controls.first?.segmentCount, items.count,
      "the system segmented control draws fewer segments than `TopNavigationRoutes.primaryItems`")
  }

  private func segmentedControls(in view: NSView) -> [NSSegmentedControl] {
    var found: [NSSegmentedControl] = []
    if let control = view as? NSSegmentedControl { found.append(control) }
    for subview in view.subviews { found += segmentedControls(in: subview) }
    return found
  }

  /// The native tab bar shows one selected segment or none. Any Brain page lights the `Memories`
  /// tab; a page with no tab of its own (Settings, Permissions) selects nothing rather than lying.
  func testTheNativeTabBarSelectsTheTabThatOwnsTheCurrentPage() {
    XCTAssertEqual(
      TopNavigationSegmentSelection.selectedTag(forSelectedIndex: SidebarNavItem.dashboard.rawValue),
      SidebarNavItem.dashboard.rawValue)
    XCTAssertEqual(
      TopNavigationSegmentSelection.selectedTag(forSelectedIndex: SidebarNavItem.tasks.rawValue),
      SidebarNavItem.tasks.rawValue)
    XCTAssertEqual(
      TopNavigationSegmentSelection.selectedTag(forSelectedIndex: SidebarNavItem.apps.rawValue),
      SidebarNavItem.apps.rawValue)
    for destination in ShellDestination.allCases where destination.memoryDestination != nil {
      XCTAssertEqual(
        TopNavigationSegmentSelection.selectedTag(forSelectedIndex: destination.navItem.rawValue),
        SidebarNavItem.conversations.rawValue,
        "\(destination.title) must light the Memories tab")
    }
    XCTAssertNil(
      TopNavigationSegmentSelection.selectedTag(forSelectedIndex: SidebarNavItem.settings.rawValue))
    XCTAssertNil(
      TopNavigationSegmentSelection.selectedTag(forSelectedIndex: SidebarNavItem.permissions.rawValue))
  }

  /// Pressing a tab navigates to it; re-pressing the current one, or the control writing back `nil`,
  /// does not restart the page. The hub tab counts as current on every Brain page.
  func testPressingANativeTabNavigatesOnlyWhenItChangesThePage() {
    var pressed: [Int] = []
    let record: (Int) -> Void = { pressed.append($0) }
    TopNavigationSegmentSelection.press(
      tag: SidebarNavItem.tasks.rawValue, selectedIndex: SidebarNavItem.dashboard.rawValue,
      onSelect: record)
    TopNavigationSegmentSelection.press(
      tag: SidebarNavItem.tasks.rawValue, selectedIndex: SidebarNavItem.tasks.rawValue,
      onSelect: record)
    TopNavigationSegmentSelection.press(
      tag: nil, selectedIndex: SidebarNavItem.tasks.rawValue, onSelect: record)
    TopNavigationSegmentSelection.press(
      tag: SidebarNavItem.conversations.rawValue, selectedIndex: SidebarNavItem.conversations.rawValue,
      onSelect: record)
    TopNavigationSegmentSelection.press(
      tag: SidebarNavItem.dashboard.rawValue, selectedIndex: SidebarNavItem.settings.rawValue,
      onSelect: record)
    XCTAssertEqual(pressed, [SidebarNavItem.tasks.rawValue, SidebarNavItem.dashboard.rawValue])
  }

  /// A native segment is text only, so the count the pills wore as a badge joins the title — and
  /// only when there is something to count.
  func testTheNewItemCountJoinsTheSegmentTitleOnlyWhenNonZero() {
    let badges = TopNavigationDestinationBadges(library: 4, tasks: 7)
    let titles = TopNavigationRoutes.primaryItems.map {
      TopNavigationSegmentSelection.title(for: $0, badges: badges)
    }
    XCTAssertEqual(titles, ["Chat", "Memories +4", "Tasks +7", "Apps"])
    let quiet = TopNavigationRoutes.primaryItems.map {
      TopNavigationSegmentSelection.title(for: $0, badges: TopNavigationDestinationBadges())
    }
    XCTAssertEqual(quiet, ["Chat", "Memories", "Tasks", "Apps"])

    // VoiceOver hears the count too: the tooltip sentence, then `N new`, and nothing extra at zero.
    let spoken = TopNavigationRoutes.primaryItems.map {
      TopNavigationSegmentSelection.accessibilityLabel(for: $0, badges: badges)
    }
    XCTAssertEqual(
      spoken,
      [
        "Chat — talk to Omi about everything you've seen and heard",
        "Memories — everything Omi captured, newest first, 4 new",
        "Tasks — everything Omi heard you commit to, 7 new",
        "Apps — connectors, imports and exports",
      ])
    let spokenQuiet = TopNavigationRoutes.primaryItems.map {
      TopNavigationSegmentSelection.accessibilityLabel(for: $0, badges: TopNavigationDestinationBadges())
    }
    XCTAssertEqual(spokenQuiet, TopNavigationRoutes.primaryItems.map(\.tooltip))
  }

  /// The glass lens follows the pointer but never leaves the track: its centre is clamped to the
  /// first and last segment centres, and a release picks the segment under the pointer, with the
  /// track's edges rounding into the end segments rather than into nothing.
  func testTheGlassLensClampsToTheTrackAndReleasesOnTheSegmentUnderThePointer() {
    let geometry = TopNavigationGlassSegmentGeometry(segmentWidth: 80, count: 4, inset: 3)
    XCTAssertEqual(geometry.lensCenterX(forPosition: 0), 43)
    XCTAssertEqual(geometry.lensCenterX(forPosition: 3), 283)
    XCTAssertEqual(geometry.lensCenterX(forPointerX: -50), 43)
    XCTAssertEqual(geometry.lensCenterX(forPointerX: 150), 150)
    XCTAssertEqual(geometry.lensCenterX(forPointerX: 900), 283)
    XCTAssertEqual(geometry.position(forPointerX: -50), 0)
    XCTAssertEqual(geometry.position(forPointerX: 3), 0)
    XCTAssertEqual(geometry.position(forPointerX: 82), 0)
    XCTAssertEqual(geometry.position(forPointerX: 83), 1)
    XCTAssertEqual(geometry.position(forPointerX: 250), 3)
    XCTAssertEqual(geometry.position(forPointerX: 900), 3)
    // Before the first layout pass the width is unknown; the lens parks at the inset and a release
    // means the first segment rather than a trap on divide-by-zero.
    let unmeasured = TopNavigationGlassSegmentGeometry(segmentWidth: 0, count: 4, inset: 3)
    XCTAssertEqual(unmeasured.lensCenterX(forPointerX: 120), 3)
    XCTAssertEqual(unmeasured.position(forPointerX: 120), 0)
  }

  // The glass renderer only exists when compiled against the macOS 26 SDK (see
  // `TopNavigationDestinationRow.body`); against an older SDK the row is the system control.
  #if compiler(>=6.2)
    /// **A drag on the tabs moves the lens, never the window.** The bar is a `WindowDragGesture` handle
    /// that recognises simultaneously with anything SwiftUI inside it, which is how the first glass row
    /// walked the whole window sideways when you dragged the selection. The press is AppKit-owned now:
    /// the view under the pointer is an `NSView` that refuses `mouseDownCanMoveWindow` and consumes the
    /// mouse sequence, so neither AppKit's background move nor SwiftUI's gesture ever sees it.
    ///
    /// This hosts the real row *inside* the real drag handle in a real window and checks two things:
    /// the view hit-tested under a tab is that AppKit owner and refuses `mouseDownCanMoveWindow` —
    /// which is the whole mechanism, since AppKit's background move asks exactly that of the hit
    /// view — and a press, travel and release sent to it land the selection on the tab under the
    /// pointer. The events go straight to the hit view (an off-screen window drops `sendEvent`), so the
    /// window's own frame is not something this harness can observe moving; the refusal is the guard.
    @available(macOS 26.0, *)
    func testDraggingTheSelectionAcrossTheTabsSelectsTheReleasedTabThroughAViewThatRefusesWindowMoves()
      throws
    {
      var selected: [Int] = []
      let row = TopNavigationDestinationRow(
        selectedIndex: SidebarNavItem.dashboard.rawValue,
        badges: TopNavigationDestinationBadges(),
        onSelect: { selected.append($0) }
      )
      let host = NSHostingView(rootView: row.padding(20).shellWindowDragHandle())
      let size = host.fittingSize
      let window = NSWindow(
        contentRect: NSRect(x: 400, y: 300, width: size.width, height: size.height),
        styleMask: [.borderless], backing: .buffered, defer: false)
      window.contentView = host
      host.frame = NSRect(origin: .zero, size: size)
      host.layoutSubtreeIfNeeded()

      // Four equal segments inside the row's 20 pt padding: press on the second, release on the fourth.
      let items = TopNavigationRoutes.primaryItems
      let segmentWidth = (size.width - 40) / CGFloat(items.count)
      let y = size.height / 2
      func x(_ position: Int) -> CGFloat { 20 + segmentWidth * (CGFloat(position) + 0.5) }
      let owner = try XCTUnwrap(host.hitTest(NSPoint(x: x(1), y: y)), "nothing under the tab")
      XCTAssertFalse(
        owner.mouseDownCanMoveWindow,
        "the view under a tab must refuse to move the window, or a drag on the tabs drags the shell")
      XCTAssertFalse(owner is NSHostingView<AnyView>, "the hosting view must not be the press owner")

      func event(_ type: NSEvent.EventType, at point: NSPoint) throws -> NSEvent {
        try XCTUnwrap(
          NSEvent.mouseEvent(
            with: type, location: point, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
            windowNumber: window.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1))
      }
      owner.mouseDown(with: try event(.leftMouseDown, at: NSPoint(x: x(1), y: y)))
      for step in 1...6 {
        let t = CGFloat(step) / 6
        owner.mouseDragged(with: try event(.leftMouseDragged, at: NSPoint(x: x(1) + (x(3) - x(1)) * t, y: y)))
      }
      owner.mouseUp(with: try event(.leftMouseUp, at: NSPoint(x: x(3), y: y)))

      XCTAssertEqual(selected, [items[3].index], "the release must select the tab under the pointer")
    }
  #endif

  func testNavigationLaneMatchesFullChatWidthAndPageInsets() {
    // The 900 pt readable cap belongs to content inside the lane. The glass fills the window
    // horizontally — including a hypothetical 1400 pt host.
    XCTAssertEqual(
      TopNavigationLayoutMetrics.contentLaneWidth(for: ChatComposerLayout.contentLaneMaxWidth),
      ChatComposerLayout.contentLaneMaxWidth)
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 1_400), 1_400)
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 800), 800)
    XCTAssertEqual(TopNavigationLayoutMetrics.contentLaneWidth(for: 40), 40)
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
  case updateStatus
  case microphone
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
