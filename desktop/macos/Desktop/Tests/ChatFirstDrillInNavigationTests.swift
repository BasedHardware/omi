import XCTest

@testable import Omi_Computer

/// Goals and a Rewind drill-in are pages you are sent to, not pills you pick: each remembers where
/// the reader came from, Back and Esc return there, and the top bar does not claim Chat for them.
@MainActor
final class ChatFirstDrillInNavigationTests: XCTestCase {
  private func makeNavigation() throws -> (ChatFirstShellNavigation, () -> Void) {
    let suiteName = "ChatFirstDrillInNavigationTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    let navigation = ChatFirstShellNavigation(defaults: defaults, analytics: { _ in })
    return (navigation, { defaults.removePersistentDomain(forName: suiteName) })
  }

  func testGoalsBackAndEscapeReturnToThePageThatOpenedIt() throws {
    let (navigation, cleanup) = try makeNavigation()
    defer { cleanup() }

    navigation.selectPrimary(.tasks)
    navigation.open(focus: .goal(id: "goal-1"))
    XCTAssertEqual(navigation.route, .goals)
    XCTAssertEqual(navigation.goalsOrigin, .tasks)

    navigation.closeGoals()
    XCTAssertEqual(navigation.route, .tasks)
    XCTAssertNil(navigation.goalsOrigin)

    navigation.selectPrimary(.memories)
    navigation.selectPrimary(.goals)
    XCTAssertTrue(navigation.handleEscapeNavigation())
    XCTAssertEqual(navigation.route, .memories, "Esc on Goals is its Back, not a jump to Chat")
  }

  func testGoalsWithNoRecordedOriginReturnsToChat() throws {
    let (navigation, cleanup) = try makeNavigation()
    defer { cleanup() }

    navigation.selectMore(.settings)
    navigation.selectPrimary(.goals)
    XCTAssertNil(navigation.goalsOrigin)
    navigation.closeGoals()
    XCTAssertEqual(navigation.route, .chat)
  }

  func testGoalsOriginSurvivesADetourThroughARecap() throws {
    let (navigation, cleanup) = try makeNavigation()
    defer { cleanup() }

    navigation.selectPrimary(.tasks)
    navigation.selectPrimary(.goals)
    navigation.openDailyRecap(DailyRecapRouteRef(recordID: "ds_1", date: "2026-09-03"))
    navigation.closeDailyRecap()
    XCTAssertEqual(navigation.route, .goals)
    XCTAssertEqual(navigation.goalsOrigin, .tasks)
  }

  func testTopBarClaimsNoPillForGoalsAndTheOriginsPillForARecap() {
    XCTAssertEqual(ChatFirstModernNavigationPolicy.topBarIndex(for: .goals), ChatFirstModernNavigationPolicy.noPill)
    XCTAssertNotEqual(
      ChatFirstModernNavigationPolicy.topBarIndex(for: .goals), SidebarNavItem.dashboard.rawValue)
    let recap = ChatFirstRoute.dailyRecap(DailyRecapRouteRef(recordID: "ds_1", date: "2026-09-03"))
    XCTAssertEqual(
      ChatFirstModernNavigationPolicy.topBarIndex(for: recap, dailyRecapOrigin: .memories),
      SidebarNavItem.conversations.rawValue)
    XCTAssertEqual(
      ChatFirstModernNavigationPolicy.topBarIndex(for: recap, dailyRecapOrigin: .goals),
      ChatFirstModernNavigationPolicy.noPill)
  }

  func testTaskEvidenceOpensRewindAsADrillInBackToTasks() throws {
    let (navigation, cleanup) = try makeNavigation()
    defer { cleanup() }

    navigation.selectPrimary(.tasks)
    XCTAssertNil(navigation.rewindDrillInOrigin)
    navigation.selectMore(.rewind)
    XCTAssertEqual(navigation.rewindDrillInOrigin, .tasks)

    XCTAssertTrue(navigation.handleEscapeNavigation())
    XCTAssertEqual(navigation.route, .tasks)

    // Choosing a Brain section from the drill-in is a new place, not a detour: the way back goes.
    navigation.selectMore(.rewind)
    navigation.selectPrimary(.memories)
    XCTAssertNil(navigation.rewindDrillInOrigin)
  }
}

/// ⌘F reaches the search field of the page on screen, in the window it was pressed in.
@MainActor
final class FindCommandRouterTests: XCTestCase {
  func testPolicyAcceptsOnlyPlainCommandF() {
    XCTAssertTrue(FindCommandPolicy.isFindCommand(charactersIgnoringModifiers: "f", modifierFlags: .command))
    XCTAssertTrue(FindCommandPolicy.isFindCommand(charactersIgnoringModifiers: "F", modifierFlags: .command))
    XCTAssertFalse(FindCommandPolicy.isFindCommand(charactersIgnoringModifiers: "f", modifierFlags: []))
    XCTAssertFalse(
      FindCommandPolicy.isFindCommand(charactersIgnoringModifiers: "f", modifierFlags: [.command, .shift]))
    XCTAssertFalse(
      FindCommandPolicy.isFindCommand(charactersIgnoringModifiers: "f", modifierFlags: [.command, .option]))
    XCTAssertFalse(FindCommandPolicy.isFindCommand(charactersIgnoringModifiers: "n", modifierFlags: .command))
  }

  func testNothingRegisteredLetsTheKeyPass() {
    let router = FindCommandRouter()
    XCTAssertFalse(router.dispatchFind(in: nil))
  }

  func testDetailFindBeatsThePageSearch() {
    let router = FindCommandRouter()
    var claimed: [String] = []
    router.register(window: nil, priority: .detail) { claimed.append("transcript") }
    router.register(window: nil, priority: .page) { claimed.append("page") }

    XCTAssertTrue(router.dispatchFind(in: nil))
    XCTAssertEqual(claimed, ["transcript"])
  }

  func testMostRecentlyMountedPageFieldWinsAndUnregisteredOnesNeverAnswer() {
    let router = FindCommandRouter()
    var claimed: [String] = []
    router.register(window: nil) { claimed.append("old") }
    let newer = router.register(window: nil) { claimed.append("new") }

    router.dispatchFind(in: nil)
    router.unregister(newer)
    router.dispatchFind(in: nil)

    XCTAssertEqual(claimed, ["new", "old"])
  }

  func testAHiddenFieldIsSkipped() {
    let router = FindCommandRouter()
    var claimed: [String] = []
    router.register(window: nil) { claimed.append("visible") }
    router.register(window: nil, isAvailable: { false }) { claimed.append("hidden") }

    router.dispatchFind(in: nil)
    XCTAssertEqual(claimed, ["visible"])
  }

  func testAFieldInAnotherWindowDoesNotAnswer() {
    let router = FindCommandRouter()
    let window = NSWindow(
      contentRect: .zero, styleMask: [.titled], backing: .buffered, defer: true)
    var claimed = false
    router.register(window: window) { claimed = true }

    XCTAssertFalse(router.dispatchFind(in: nil))
    XCTAssertFalse(claimed)
    XCTAssertTrue(router.dispatchFind(in: window))
    XCTAssertTrue(claimed)
  }
}
