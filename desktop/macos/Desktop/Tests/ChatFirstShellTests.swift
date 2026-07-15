import XCTest

@testable import Omi_Computer

@MainActor
final class ChatFirstShellTests: XCTestCase {
  private func enabledControl(generation: Int = 7) -> OmiAPI.TaskWorkflowControl {
    OmiAPI.TaskWorkflowControl(
      accountGeneration: generation,
      chatFirstUi: true,
      workflowMode: .read
    )
  }

  func testSuccessfulSampleSelectsChatFirstAndCannotLiveSwap() throws {
    var sample = ChatFirstShellCapabilitySample()
    sample.resolve(
      control: enabledControl(),
      requestedOwnerID: "owner-a",
      ownerIsStillCurrent: true
    )

    XCTAssertEqual(sample.variant.projection?.controlGeneration, 7)
    XCTAssertEqual(sample.variant.stableName, "chat_first")

    sample.resolve(
      control: OmiAPI.TaskWorkflowControl(accountGeneration: 8, chatFirstUi: false, workflowMode: .off),
      requestedOwnerID: "owner-a",
      ownerIsStillCurrent: true
    )
    XCTAssertEqual(sample.variant.projection?.controlGeneration, 7)
  }

  func testMissingStaleAndOwnerChangedSamplesFailClosed() {
    var missing = ChatFirstShellCapabilitySample()
    missing.resolve(control: nil, requestedOwnerID: "owner-a", ownerIsStillCurrent: true)
    XCTAssertEqual(missing.variant.stableName, "legacy")

    var stale = ChatFirstShellCapabilitySample()
    stale.resolve(control: enabledControl(), requestedOwnerID: "owner-a", ownerIsStillCurrent: false)
    XCTAssertEqual(stale.variant.stableName, "legacy")

    var ownerChanged = ChatFirstShellCapabilitySample()
    ownerChanged.resolve(control: enabledControl(), requestedOwnerID: "owner-a", ownerIsStillCurrent: true)
    ownerChanged.ownerDidChange(to: "owner-b")
    XCTAssertEqual(ownerChanged.variant.stableName, "legacy")
  }

  func testNavigationPersistsOnlyRouteAndCollapseAndRetainsFocusUntilAcknowledged() {
    let suiteName = "ChatFirstShellTests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(defaults: defaults)
    XCTAssertEqual(navigation.route, .chat)
    XCTAssertNil(navigation.pendingFocus)

    let focus = ChatFirstPendingFocus.capture(id: "capture-1", momentTs: 42)
    navigation.open(focus: focus)
    navigation.toggleSidebar()
    XCTAssertEqual(navigation.route, .conversations)
    XCTAssertEqual(navigation.pendingFocus, focus)
    XCTAssertFalse(navigation.acknowledgeFocus(.task(id: "task-1")))
    XCTAssertEqual(navigation.pendingFocus, focus)
    XCTAssertTrue(navigation.acknowledgeFocus(focus))
    XCTAssertNil(navigation.pendingFocus)
    XCTAssertEqual(navigation.lastAcknowledgedFocusKind, "capture")

    let restored = ChatFirstShellNavigation(defaults: defaults)
    XCTAssertEqual(restored.route, .conversations)
    XCTAssertTrue(restored.isSidebarCollapsed)
    XCTAssertNil(restored.pendingFocus)
  }

  func testDirectAndLegacyNavigationClearFocusAndMapToTypedRoutes() {
    let suiteName = "ChatFirstShellTests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(defaults: defaults)
    navigation.open(focus: .goal(id: "goal-1"))
    navigation.selectPrimary(.tasks)
    XCTAssertEqual(navigation.route, .tasks)
    XCTAssertNil(navigation.pendingFocus)

    navigation.open(focus: .memory(id: "memory-1"))
    navigation.selectLegacyDestination(.settings)
    XCTAssertEqual(navigation.route, .more(.settings))
    XCTAssertNil(navigation.pendingFocus)

    navigation.selectLegacyDestination(.chat)
    XCTAssertEqual(navigation.route, .chat)
  }

  func testPrimaryAutomationRouteIncludesGoalsWithoutRepurposingLegacyPages() {
    XCTAssertEqual(ChatFirstRoute.primaryAutomationDestination(named: "goals"), .goals)
    XCTAssertEqual(ChatFirstRoute.primaryAutomationDestination(named: "GOALS"), .goals)
    XCTAssertNil(ChatFirstRoute.primaryAutomationDestination(named: "dashboard"))
    XCTAssertNil(ChatFirstRoute.primaryAutomationDestination(named: "settings"))
  }

  func testProjectionGatePassesOnlyEnabledMainChatForSampledOwner() throws {
    var gate = ChatFirstMainChatProjectionGate()
    XCTAssertFalse(gate.isConfigured(for: "owner-a"))
    let enabled = try XCTUnwrap(ChatFirstCapabilityProjection(control: enabledControl(generation: 11)))
    XCTAssertTrue(gate.configure(sample: enabled, ownerID: "owner-a"))
    XCTAssertTrue(gate.isConfigured(for: "owner-a"))

    let main = AgentSurfaceReference.mainChat(chatId: nil)
    XCTAssertEqual(gate.capability(for: main, ownerID: "owner-a"), enabled)
    XCTAssertNil(gate.capability(for: .floatingChat(), ownerID: "owner-a"))
    XCTAssertNil(gate.capability(for: main, ownerID: "owner-b"))

    gate.markResolved(surface: main, ownerID: "owner-a")
    XCTAssertFalse(gate.configure(sample: nil, ownerID: "owner-a"))
    XCTAssertEqual(gate.capability(for: main, ownerID: "owner-a"), enabled)
  }

  func testProjectionGateKeepsCapabilityOffForFalseSample() {
    var gate = ChatFirstMainChatProjectionGate()
    XCTAssertTrue(gate.configure(sample: nil, ownerID: "owner-a"))
    XCTAssertNil(gate.capability(for: .mainChat(chatId: nil), ownerID: "owner-a"))
  }
}
