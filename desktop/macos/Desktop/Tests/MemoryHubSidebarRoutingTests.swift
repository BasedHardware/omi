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
}
