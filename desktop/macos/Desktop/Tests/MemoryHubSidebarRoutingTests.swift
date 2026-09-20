import XCTest

@testable import Omi_Computer

final class MemoryHubSidebarRoutingTests: XCTestCase {
  /// The Activity spine — Home's former landing surface — is a hub destination, the page the bar's
  /// pill opens, and the chip that leads the row that reaches the rest.
  func testActivityIsAHubDestinationAndLeadsTheChipRow() {
    XCTAssertEqual(ActivityDestinationChip.allCases.first?.hubDestination, .activity)
    XCTAssertEqual(
      Set(ActivityDestinationChip.reachableHubDestinations), Set(MemoryHubDestination.allCases),
      "every destination is reachable from Activity's chip row")
    XCTAssertEqual(MemoryHubDestination.destination(for: .conversations), .conversations)
  }

  func testConversationsSidebarSelectionUpdatesRailAndDestination() {
    var selectedIndex = SidebarNavItem.dashboard.rawValue
    var memoryDestinationRawValue = MemoryHubDestination.memories.rawValue

    MemoryHubDestination.apply(
      .conversations,
      to: &selectedIndex,
      hub: &memoryDestinationRawValue
    )

    XCTAssertEqual(selectedIndex, SidebarNavItem.conversations.rawValue)
    XCTAssertEqual(memoryDestinationRawValue, MemoryHubDestination.conversations.rawValue)
  }

  func testOtherSidebarSelectionsPreserveMemoryDestination() {
    var selectedIndex = SidebarNavItem.dashboard.rawValue
    var memoryDestinationRawValue = MemoryHubDestination.conversations.rawValue

    MemoryHubDestination.apply(
      .tasks,
      to: &selectedIndex,
      hub: &memoryDestinationRawValue
    )

    XCTAssertEqual(selectedIndex, SidebarNavItem.tasks.rawValue)
    XCTAssertEqual(memoryDestinationRawValue, MemoryHubDestination.conversations.rawValue)
  }

  /// The menu/keyboard route (`⌘2`, posted as `.navigateToSidebarItem`) resolves the hub view
  /// through this, not through `apply` — it has no `inout` pair to hand over.
  ///
  /// Regression: the handler used to set only the rail index, so a menu item **labelled
  /// "Conversations"** opened the hub on whichever view was last persisted. The hub's stored default
  /// is `.memories` (`MemoryHubDestination.allCases` starts there), so out of the box `⌘2` opened
  /// Memories. Naming a destination and landing on a different one is the failure this asserts is
  /// gone.
  func testAMenuCallerNamingConversationsResolvesConversationsNotTheRememberedView() {
    XCTAssertEqual(MemoryHubDestination.destination(for: .conversations), .conversations)
  }

  /// The other half of the same contract: a caller that names a page outside the hub must not
  /// disturb the hub's remembered view on its way past.
  func testAMenuCallerNamingAPageOutsideTheHubResolvesNoHubView() {
    XCTAssertNil(MemoryHubDestination.destination(for: .tasks))
    XCTAssertNil(MemoryHubDestination.destination(for: .settings))
  }

  func testEveryLegacyMemoryAliasResolvesTheCanonicalHubDestination() {
    XCTAssertEqual(MemoryHubDestination.destination(for: .conversations), .conversations)
    XCTAssertEqual(MemoryHubDestination.destination(for: .memories), .memories)
    XCTAssertEqual(MemoryHubDestination.destination(for: .rewind), .rewind)
  }

  /// `bridge.navigate conversations` used to select only the memories *route*,
  /// so the hub stayed on its remembered view (default Memories). Automation
  /// resolves the hub through `destination(forAutomationTarget:)` inside
  /// `navigateToLegacyDestination(_:automationTarget:)` — the same helper this
  /// test calls — before selecting the chat-first route.
  func testAutomationNameConversationsSelectsConversationsHubNotRememberedMemories() {
    XCTAssertEqual(
      MemoryHubDestination.destination(forAutomationTarget: "conversations"), .conversations)
    XCTAssertEqual(
      MemoryHubDestination.destination(forAutomationTarget: "Conversations"), .conversations)
    XCTAssertEqual(
      MemoryHubDestination.destination(forAutomationTarget: "CONVERSATIONS"),
      .conversations)
    XCTAssertEqual(MemoryHubDestination.destination(forAutomationTarget: "memories"), .memories)
    XCTAssertEqual(MemoryHubDestination.destination(forAutomationTarget: "rewind"), .rewind)
  }

  /// Targets outside the hub must leave the remembered view untouched on their way past.
  func testAnAutomationCallerNamingAPageOutsideTheHubResolvesNoHubView() {
    XCTAssertNil(MemoryHubDestination.destination(forAutomationTarget: "tasks"))
    XCTAssertNil(MemoryHubDestination.destination(forAutomationTarget: "chat"))
    XCTAssertNil(MemoryHubDestination.destination(forAutomationTarget: "dashboard"))
    XCTAssertNil(MemoryHubDestination.destination(forAutomationTarget: "settings"))
    XCTAssertNil(MemoryHubDestination.destination(forAutomationTarget: "help"))
    XCTAssertNil(MemoryHubDestination.destination(forAutomationTarget: "not-a-target"))
  }

  /// `navigate permissions` must acknowledge `more.permissions`, not `more.settings`.
  /// Mapping the name into `SidebarNavItem.permissions` sends automation through the
  /// legacy adapter (`selectMore(.settings)`), which breaks `waitForNavigationTarget`.
  func testAutomationPermissionsNameMapsToVisibleMorePermissionsRoute() {
    XCTAssertNil(SidebarNavItem.automationDestination(named: "permissions"))
    XCTAssertNil(SidebarNavItem.automationDestination(named: "PERMISSIONS"))
    XCTAssertEqual(
      ChatFirstRoute.automationVisibilityDestination(named: "permissions"),
      .more(.permissions))
  }
}
