import XCTest

@testable import Omi_Computer

final class MemoryHubSidebarRoutingTests: XCTestCase {
  func testConversationsSidebarSelectionUpdatesRailAndDestination() {
    var selectedIndex = SidebarNavItem.dashboard.rawValue
    var memoryDestinationRawValue = MemoryHubDestination.memories.rawValue

    MemoryHubDestination.applySidebarSelection(
      .conversations,
      selectedIndex: &selectedIndex,
      memoryDestinationRawValue: &memoryDestinationRawValue
    )

    XCTAssertEqual(selectedIndex, SidebarNavItem.conversations.rawValue)
    XCTAssertEqual(memoryDestinationRawValue, MemoryHubDestination.conversations.rawValue)
  }

  func testOtherSidebarSelectionsPreserveMemoryDestination() {
    var selectedIndex = SidebarNavItem.dashboard.rawValue
    var memoryDestinationRawValue = MemoryHubDestination.conversations.rawValue

    MemoryHubDestination.applySidebarSelection(
      .tasks,
      selectedIndex: &selectedIndex,
      memoryDestinationRawValue: &memoryDestinationRawValue
    )

    XCTAssertEqual(selectedIndex, SidebarNavItem.tasks.rawValue)
    XCTAssertEqual(memoryDestinationRawValue, MemoryHubDestination.conversations.rawValue)
  }

  func testLegacyHomeDesignKeepsConversationsAsAStandalonePage() {
    XCTAssertEqual(
      MemoryHubDestination.presentation(
        for: .conversations,
        useLegacyHomeDesign: true
      ),
      .standaloneConversations
    )
  }

  func testModernHomeDesignUsesTheMemoryHubForTheSharedRailIndex() {
    XCTAssertEqual(
      MemoryHubDestination.presentation(
        for: .conversations,
        useLegacyHomeDesign: false
      ),
      .memoryHub
    )
  }
}
