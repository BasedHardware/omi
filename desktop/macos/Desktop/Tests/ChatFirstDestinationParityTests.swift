import XCTest

@testable import Omi_Computer

final class ChatFirstDestinationParityTests: XCTestCase {
  func testBrainMapSelectionSurvivesTheMemoryRouteTransition() {
    XCTAssertEqual(
      ChatFirstMemoryRoutePolicy.destination(afterSelecting: .memories, current: .brainMap),
      .brainMap
    )
    XCTAssertEqual(
      ChatFirstMemoryRoutePolicy.destination(afterSelecting: .memories, current: .conversations),
      .memories
    )
    XCTAssertEqual(
      ChatFirstMemoryRoutePolicy.destination(afterSelecting: .conversations, current: .brainMap),
      .conversations
    )
    XCTAssertNil(
      ChatFirstMemoryRoutePolicy.destination(afterSelecting: .tasks, current: .brainMap)
    )
  }

  /// **The regression this policy actually shipped.** The memory route used to preserve `.brainMap`
  /// by name, so `.activity` — added later as a fourth hub view sharing that route — was rewritten
  /// to `.memories` by the route sync that runs right after the click. Pressing Activity landed on
  /// Memories, from the pill and from Activity's own chip row alike. Every view whose route is the
  /// memory route must survive it, not just the two that were there when the policy was written.
  func testActivitySelectionSurvivesTheMemoryRouteTransition() {
    XCTAssertEqual(
      ChatFirstMemoryRoutePolicy.destination(afterSelecting: .memories, current: .activity),
      .activity,
      "the memory route rewrote Activity back to Memories, swallowing the click")

    for destination in MemoryHubDestination.allCases
    where MemoryHubSelectionPolicy.chatFirstRoute(for: destination) == .memories {
      XCTAssertEqual(
        ChatFirstMemoryRoutePolicy.destination(afterSelecting: .memories, current: destination),
        destination,
        "\(destination.title) does not survive its own route")
    }
  }

  /// Selecting a hub view in the chat-first shell has to move its typed route as well as the
  /// persisted destination. Conversations has its own route (it carries capture-archive focus);
  /// Memories and Brain Map are both the Memory route, which is where `MemoryHubPage` is mounted.
  ///
  /// Without this, picking Brain Map from the Conversations route left the shell on a host that has
  /// no Brain Map in it — the state that made the map unreachable once the menu was gone.
  func testChatFirstAppliesAHubSelectionToItsOwnRoute() {
    XCTAssertEqual(MemoryHubSelectionPolicy.chatFirstRoute(for: .conversations), .conversations)
    XCTAssertEqual(MemoryHubSelectionPolicy.chatFirstRoute(for: .memories), .memories)
    XCTAssertEqual(MemoryHubSelectionPolicy.chatFirstRoute(for: .brainMap), .memories)
    XCTAssertEqual(MemoryHubSelectionPolicy.chatFirstRoute(for: .activity), .memories)
  }

  /// **The chip row is the door, so its contents are a contract.**
  ///
  /// The hub's switcher was deleted and this row replaced it. `ShellDestination.Reach.activityChipRow`
  /// claims the row reaches Conversations, Memories and Brain Map; that claim is only true while the
  /// row actually offers every hub page. Tasks and Rewind were removed from the row deliberately —
  /// each already has its own pill in the bar directly above it — and neither is a hub page, so
  /// neither may come back here without the reachability model being revisited. That every chip
  /// opens *some* hub page is held by the type — `hubDestination` is not optional — rather than by
  /// an assertion here.
  func testTheActivityChipRowOffersEveryHubPageAndNothingElse() {
    XCTAssertEqual(
      ActivityDestinationChip.allCases.map(\.title),
      ["Brain", "Conversations", "Memories", "Brain Map"])

    XCTAssertEqual(
      Set(ActivityDestinationChip.reachableHubDestinations), Set(MemoryHubDestination.allCases),
      "a hub page the chip row does not offer has no door")
  }

  /// The row's word for itself has to follow what the row does. Home's chips narrow results in
  /// place and are a filter; Activity's open pages and are a view.
  func testThePanelHeaderNamesWhatTheChipRowActuallyDoes() {
    XCTAssertEqual(QueryPanelChipBehavior.filterKinds.disclosureLabel, "Filter")
    XCTAssertEqual(
      QueryPanelChipBehavior.openDestinations(selected: .activity, open: { _ in }).disclosureLabel,
      "View")
  }

  /// Every flat pill the bar now shows must resolve to a chat-first route, both ways. `Focus` did
  /// not: `route(forTopBarIndex:)` returned nil for it, so while Focus lived in the retired menu the
  /// press was silently swallowed in this shell.
  func testEveryTopBarPillResolvesToAChatFirstRouteAndBack() {
    for item in TopNavigationRoutes.primaryItems {
      guard let route = ChatFirstModernNavigationPolicy.route(forTopBarIndex: item.index) else {
        return XCTFail("\(item.title) presses nothing in the chat-first shell")
      }
      XCTAssertEqual(
        ChatFirstModernNavigationPolicy.topBarIndex(for: route), item.index,
        "\(item.title) does not light its own pill once selected")
    }
  }
}
