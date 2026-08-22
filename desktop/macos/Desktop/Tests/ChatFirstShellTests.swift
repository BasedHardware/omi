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

  private func conversation(id: String) -> ServerConversation {
    ServerConversation(
      id: id,
      createdAt: Date(timeIntervalSince1970: 1_000),
      updatedAt: Date(timeIntervalSince1970: 1_001),
      startedAt: Date(timeIntervalSince1970: 1_000),
      finishedAt: Date(timeIntervalSince1970: 1_060),
      structured: Structured(
        title: "Meeting notes",
        overview: "Overview",
        emoji: "",
        category: "other",
        actionItems: [],
        events: []
      ),
      transcriptSegments: [],
      transcriptSegmentsIncluded: false,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: "en",
      status: .completed,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: false,
      folderId: nil,
      inputDeviceName: nil,
      deferred: false
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

  func testLegacyWorkflowMetadataCannotSuppressDerivedChatFirstCapability() throws {
    let control = OmiAPI.TaskWorkflowControl(
      accountGeneration: 9,
      chatFirstUi: true,
      workflowMode: .off
    )

    let projection = try XCTUnwrap(ChatFirstCapabilityProjection(control: control))

    XCTAssertTrue(projection.chatFirstUi)
    XCTAssertEqual(projection.controlGeneration, 9)
  }

  func testOnlyLegacyShellUsesThePostOnboardingFloatingPopup() {
    var enabled = ChatFirstShellCapabilitySample()
    enabled.resolve(
      control: enabledControl(),
      requestedOwnerID: "owner-a",
      ownerIsStillCurrent: true
    )

    XCTAssertFalse(
      DesktopShellPresentationPolicy.usesLegacyPostOnboardingPopup(false, enabled.variant),
      "chat-first starter prompts belong to the main chat")
    XCTAssertTrue(
      DesktopShellPresentationPolicy.usesLegacyPostOnboardingPopup(false, .legacy),
      "the server-selected legacy shell retains its floating prompt")
    XCTAssertTrue(
      DesktopShellPresentationPolicy.usesLegacyPostOnboardingPopup(true, enabled.variant),
      "the explicit legacy preference remains authoritative")
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

  func testNavigationPersistsOnlyRouteAndCollapseAndRetainsFocusUntilAcknowledged() throws {
    let suiteName = "ChatFirstShellTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(defaults: defaults)
    XCTAssertEqual(navigation.route, .chat)
    XCTAssertNil(navigation.pendingFocus)

    let focus = ChatFirstPendingFocus.capture(id: "capture-1", momentTs: 42)
    navigation.open(focus: focus)
    navigation.toggleSidebar()
    XCTAssertEqual(navigation.route, .conversations)
    XCTAssertEqual(navigation.pendingFocus, focus)
    XCTAssertEqual(navigation.focusedEntityID, "capture-1")
    XCTAssertFalse(navigation.isFocusedEntityAcknowledged)
    XCTAssertFalse(navigation.acknowledgeFocus(.task(id: "task-1")))
    XCTAssertEqual(navigation.pendingFocus, focus)
    XCTAssertTrue(navigation.acknowledgeFocus(focus))
    XCTAssertNil(navigation.pendingFocus)
    XCTAssertEqual(navigation.lastAcknowledgedFocusKind, "capture")
    XCTAssertEqual(navigation.focusedEntityID, "capture-1")
    XCTAssertTrue(navigation.isFocusedEntityAcknowledged)

    let restored = ChatFirstShellNavigation(defaults: defaults)
    XCTAssertEqual(restored.route, .conversations)
    XCTAssertTrue(restored.isSidebarCollapsed)
    XCTAssertNil(restored.pendingFocus)
    XCTAssertNil(restored.focusedEntityID)
    XCTAssertFalse(restored.isFocusedEntityAcknowledged)
  }

  func testConversationDeepLinkCarriesFetchedRecordOutsidePaginatedList() throws {
    let suiteName = "ChatFirstShellTests.conversation-deeplink.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(defaults: defaults)
    let fetched = conversation(id: "older-meeting-42")
    navigation.open(conversation: fetched)

    XCTAssertEqual(navigation.route, .conversations)
    XCTAssertEqual(navigation.pendingConversation, fetched)
    XCTAssertNil(navigation.pendingFocus)
  }

  func testBackNavigationReturnsToChatFromPrimaryAndSettingsRoutes() throws {
    let suiteName = "ChatFirstShellTests.escape-navigation.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(defaults: defaults)
    for route: ChatFirstRoute in [.tasks, .more(.settings)] {
      switch route {
      case .more(let page): navigation.selectMore(page)
      default: navigation.selectPrimary(route)
      }

      XCTAssertTrue(navigation.handleEscapeNavigation(), route.stableName)
      XCTAssertEqual(navigation.route, .chat, route.stableName)
    }
    XCTAssertFalse(navigation.handleEscapeNavigation())
    XCTAssertEqual(navigation.route, .chat)
  }

  func testSettingsRouteMountsSectionNavigationAndContentInTheSameDestination() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/ChatFirst/ChatFirstShell.swift")
    // omi-test-quality: source-inspection -- static contract: SwiftUI settings composition wiring
    let source = try String(contentsOf: sourceURL, encoding: .utf8)
    let moreDestination = try XCTUnwrap(
      source.components(separatedBy: "private func moreDestination").last
    )
    let settingsTail = try XCTUnwrap(
      moreDestination.components(separatedBy: "case .settings:").dropFirst().first
    )
    let settingsDestination = try XCTUnwrap(
      settingsTail.components(separatedBy: "/// Existing Dashboard").first
    )

    XCTAssertTrue(settingsDestination.contains("SettingsSidebar("))
    XCTAssertTrue(settingsDestination.contains("SettingsPage("))
    XCTAssertTrue(settingsDestination.contains("navigation.handleEscapeNavigation()"))
  }

  func testMemoryFocusRequiresTheRequestedMemoryToBeVisibleBeforeAcknowledgement() {
    let focus = ChatFirstPendingFocus.memory(id: "memory-1")

    XCTAssertEqual(
      ChatFirstMemoryFocusPolicy.focusToAcknowledge(pendingFocus: focus, visibleMemoryID: "memory-1"),
      focus
    )
    XCTAssertNil(ChatFirstMemoryFocusPolicy.focusToAcknowledge(pendingFocus: focus, visibleMemoryID: "memory-2"))
  }

  func testRouteIsNotVisibleUntilTheMountedDestinationAcknowledgesIt() throws {
    let suiteName = "ChatFirstShellTests.visible-route.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(defaults: defaults)
    XCTAssertNil(navigation.visibleRoute)

    navigation.selectPrimary(.goals)
    XCTAssertEqual(navigation.route, .goals)
    XCTAssertNil(navigation.visibleRoute)

    navigation.markRouteVisible(.tasks)
    XCTAssertNil(navigation.visibleRoute)
    navigation.markRouteVisible(.goals)
    XCTAssertEqual(navigation.visibleRoute, .goals)

    navigation.open(focus: .task(id: "task-1"))
    XCTAssertEqual(navigation.route, .tasks)
    XCTAssertNil(navigation.visibleRoute)
  }

  func testReselectingMountedRouteKeepsItsVisibilityAcknowledgement() throws {
    let suiteName = "ChatFirstShellTests.reselect-visible.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let navigation = ChatFirstShellNavigation(defaults: defaults)

    navigation.markRouteVisible(.chat)
    navigation.selectPrimary(.chat)
    XCTAssertEqual(navigation.visibleRoute, .chat)

    navigation.selectMore(.settings)
    navigation.markRouteVisible(.more(.settings))
    navigation.selectMore(.settings)
    XCTAssertEqual(navigation.visibleRoute, .more(.settings))
  }

  func testReselectingMountedRouteInvalidatesGoalLinkResolution() throws {
    let suiteName = "ChatFirstShellTests.reselect-goal-link.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let navigation = ChatFirstShellNavigation(defaults: defaults)

    navigation.markRouteVisible(.chat)
    let resolution = navigation.beginGoalLinkResolution()
    navigation.selectPrimary(.chat)

    XCTAssertFalse(navigation.completeGoalLinkResolution(goalID: "goal-old", generation: resolution))
    XCTAssertEqual(navigation.route, .chat)
    XCTAssertNil(navigation.pendingFocus)
  }

  func testDirectAndLegacyNavigationClearFocusAndMapToTypedRoutes() throws {
    let suiteName = "ChatFirstShellTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(defaults: defaults)
    navigation.open(focus: .goal(id: "goal-1"))
    navigation.selectPrimary(.tasks)
    XCTAssertEqual(navigation.route, .tasks)
    XCTAssertNil(navigation.pendingFocus)
    XCTAssertNil(navigation.focusedEntityID)
    XCTAssertFalse(navigation.isFocusedEntityAcknowledged)

    navigation.open(focus: .memory(id: "memory-1"))
    navigation.selectLegacyDestination(.settings)
    XCTAssertEqual(navigation.route, .more(.settings))
    XCTAssertNil(navigation.pendingFocus)

    // `.chat` was removed from `SidebarNavItem` when the standalone chat page was deleted (Home is
    // the only chat). Legacy dashboard callbacks now re-enter that canonical Chat route rather than
    // selecting a second dashboard presentation.
    navigation.selectLegacyDestination(.dashboard)
    XCTAssertEqual(navigation.route, .chat)
  }

  func testNavigationUsesTypedOriginsWithoutEntityIdentifiersInAnalytics() throws {
    let suiteName = "ChatFirstShellTests.analytics.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    var events: [ChatFirstAnalyticsEvent] = []
    let navigation = ChatFirstShellNavigation(defaults: defaults) { event in
      events.append(event)
    }

    navigation.selectPrimary(.tasks)
    navigation.open(focus: .goal(id: "private-goal-id"))
    navigation.selectMore(.settings)

    XCTAssertEqual(
      events,
      [
        .routeEntered(route: .tasks, origin: .sidebar),
        .routeEntered(route: .goals, origin: .chatDeeplink),
        .routeEntered(route: .more, origin: .more),
      ]
    )
    XCTAssertFalse(
      events.map(\.analyticsPayload).flatMap { $0.properties.values }.contains("private-goal-id")
    )
  }

  func testExternalMainChatRequestUsesTheChatDeeplinkOrigin() throws {
    let suiteName = "ChatFirstShellTests.external-main-chat.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    var events: [ChatFirstAnalyticsEvent] = []
    let navigation = ChatFirstShellNavigation(defaults: defaults) { event in
      events.append(event)
    }

    navigation.selectPrimary(.tasks)
    events.removeAll()
    navigation.selectPrimary(.chat, origin: .chatDeeplink)

    XCTAssertEqual(navigation.route, .chat)
    XCTAssertEqual(events, [.routeEntered(route: .chat, origin: .chatDeeplink)])
  }

  func testLaunchAnalyticsRouteReflectsTheRestoredNavigationRoute() throws {
    let suiteName = "ChatFirstShellTests.launch-route.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let navigation = ChatFirstShellNavigation(defaults: defaults)

    navigation.selectPrimary(.tasks)
    let restored = ChatFirstShellNavigation(defaults: defaults)

    XCTAssertEqual(restored.route, .tasks)
    XCTAssertEqual(restored.route.analyticsRoute, .tasks)
  }

  func testNewerGoalLinkResolutionPreventsAStaleCompletionFromNavigating() throws {
    let suiteName = "ChatFirstShellTests.goal-link-resolution.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    var events: [ChatFirstAnalyticsEvent] = []
    let navigation = ChatFirstShellNavigation(defaults: defaults) { event in
      events.append(event)
    }

    let staleResolution = navigation.beginGoalLinkResolution()
    let currentResolution = navigation.beginGoalLinkResolution()

    XCTAssertFalse(navigation.completeGoalLinkResolution(goalID: "goal-old", generation: staleResolution))
    XCTAssertEqual(navigation.route, .chat)
    XCTAssertTrue(navigation.completeGoalLinkResolution(goalID: "goal-new", generation: currentResolution))
    XCTAssertEqual(navigation.route, .goals)
    XCTAssertEqual(navigation.pendingFocus, .goal(id: "goal-new"))
    XCTAssertEqual(events, [.routeEntered(route: .goals, origin: .chatDeeplink)])
  }

  func testNewerConversationLinkResolutionPreventsAStaleCompletionFromNavigating() throws {
    let suiteName = "ChatFirstShellTests.conversation-link-resolution.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let navigation = ChatFirstShellNavigation(defaults: defaults)

    let staleResolution = navigation.beginConversationLinkResolution()
    let currentResolution = navigation.beginConversationLinkResolution()

    XCTAssertFalse(
      navigation.completeConversationLinkResolution(
        conversation: conversation(id: "meeting-old"),
        generation: staleResolution))
    XCTAssertEqual(navigation.route, .chat)
    XCTAssertNil(navigation.pendingConversation)
    XCTAssertTrue(
      navigation.completeConversationLinkResolution(
        conversation: conversation(id: "meeting-new"),
        generation: currentResolution))
    XCTAssertEqual(navigation.route, .conversations)
    XCTAssertEqual(navigation.pendingConversation?.id, "meeting-new")
  }

  func testDirectNavigationInvalidatesAnInFlightConversationLinkResolution() throws {
    let suiteName = "ChatFirstShellTests.conversation-link-direct-navigation.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let navigation = ChatFirstShellNavigation(defaults: defaults)

    let resolution = navigation.beginConversationLinkResolution()
    navigation.selectPrimary(.tasks)

    XCTAssertFalse(
      navigation.completeConversationLinkResolution(
        conversation: conversation(id: "meeting-old"),
        generation: resolution))
    XCTAssertEqual(navigation.route, .tasks)
    XCTAssertNil(navigation.pendingConversation)
  }

  func testDirectNavigationInvalidatesAnInFlightGoalLinkResolution() throws {
    let suiteName = "ChatFirstShellTests.goal-link-direct-navigation.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let navigation = ChatFirstShellNavigation(defaults: defaults)

    let resolution = navigation.beginGoalLinkResolution()
    navigation.selectPrimary(.tasks)

    XCTAssertFalse(navigation.completeGoalLinkResolution(goalID: "goal-old", generation: resolution))
    XCTAssertEqual(navigation.route, .tasks)
    XCTAssertNil(navigation.pendingFocus)
  }

  func testRelatedGoalFocusCanLandInTasksAndAcknowledgesAfterTasksVisibility() throws {
    let suiteName = "ChatFirstShellTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(defaults: defaults)
    let focus = ChatFirstPendingFocus.goal(id: "goal-1")
    navigation.open(focus: focus, destination: .tasks)

    XCTAssertEqual(navigation.route, .tasks)
    XCTAssertEqual(navigation.pendingFocus, focus)
    XCTAssertEqual(navigation.pendingFocusDestination, .tasks)
    XCTAssertTrue(navigation.acknowledgeFocus(focus))
    XCTAssertNil(navigation.pendingFocus)
  }

  func testPrimaryAutomationRouteIncludesGoalsWithoutRepurposingLegacyPages() {
    XCTAssertEqual(ChatFirstRoute.primaryAutomationDestination(named: "goals"), .goals)
    XCTAssertEqual(ChatFirstRoute.primaryAutomationDestination(named: "GOALS"), .goals)
    XCTAssertNil(ChatFirstRoute.primaryAutomationDestination(named: "dashboard"))
    XCTAssertNil(ChatFirstRoute.primaryAutomationDestination(named: "settings"))
  }

  func testAutomationNavigationVisibilityAcceptsTheMountedShellForSharedNames() {
    XCTAssertEqual(ChatFirstRoute.automationVisibilityDestination(named: "settings"), .more(.settings))
    XCTAssertEqual(ChatFirstRoute.automationVisibilityDestination(named: "home"), .chat)
    XCTAssertEqual(ChatFirstRoute.automationVisibilityDestination(named: "dashboard"), .chat)

    XCTAssertTrue(
      DesktopAutomationNavigationVisibilityPolicy.isTargetVisible(
        shellVariant: "chat_first",
        selectedTab: nil,
        visibleChatFirstRoute: "tasks",
        expectedChatFirstRoute: "tasks",
        expectedLegacyTitle: "Tasks"
      )
    )
    XCTAssertTrue(
      DesktopAutomationNavigationVisibilityPolicy.isTargetVisible(
        shellVariant: "legacy",
        selectedTab: "Tasks",
        visibleChatFirstRoute: nil,
        expectedChatFirstRoute: "tasks",
        expectedLegacyTitle: "Tasks"
      )
    )
    XCTAssertFalse(
      DesktopAutomationNavigationVisibilityPolicy.isTargetVisible(
        shellVariant: "loading",
        selectedTab: "Tasks",
        visibleChatFirstRoute: nil,
        expectedChatFirstRoute: "tasks",
        expectedLegacyTitle: "Tasks"
      )
    )
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

  func testModernShellUsesTopBarHomeForChatAndMapsPrimaryDestinations() {
    XCTAssertEqual(
      ChatFirstModernNavigationPolicy.topBarIndex(for: .chat),
      SidebarNavItem.dashboard.rawValue
    )
    XCTAssertEqual(
      ChatFirstModernNavigationPolicy.topBarIndex(for: .conversations),
      SidebarNavItem.conversations.rawValue
    )
    XCTAssertEqual(
      ChatFirstModernNavigationPolicy.topBarIndex(for: .tasks),
      SidebarNavItem.tasks.rawValue
    )
    XCTAssertEqual(
      ChatFirstModernNavigationPolicy.route(forTopBarIndex: SidebarNavItem.dashboard.rawValue),
      .chat
    )
    XCTAssertEqual(
      ChatFirstModernNavigationPolicy.route(forTopBarIndex: SidebarNavItem.apps.rawValue),
      .more(.apps)
    )
  }

  func testExplicitLegacyDesignIsTheOnlyPathThatMountsTheSidebarShell() throws {
    var sample = ChatFirstShellCapabilitySample()
    sample.resolve(
      control: enabledControl(),
      requestedOwnerID: "owner-a",
      ownerIsStillCurrent: true
    )

    XCTAssertTrue(
      DesktopShellPresentationPolicy.usesChatFirst(false, sample.variant)
    )
    XCTAssertFalse(
      DesktopShellPresentationPolicy.usesChatFirst(true, sample.variant)
    )
    XCTAssertFalse(
      DesktopShellPresentationPolicy.usesChatFirst(false, .legacy)
    )
  }

  /// **The legacy shell has no Home stage, and must not claim one.** Its Home is the query surface;
  /// the only branch there that still mounts `DashboardPage` needs `useLegacyHomeDesign`, which
  /// renders `legacyHome`. So no value of any input can make the legacy shell report a stage mode.
  ///
  /// The bug this replaces reported `hub` for exactly this shell, forever, because the guard was
  /// written when the non-legacy legacy-shell Home *was* `DashboardPage`. It never read as broken:
  /// `hub` is a legitimate mode, so `/state` looked healthy while describing a surface that was not
  /// mounted, and a flow waiting for `chat` waited for a transition nothing could produce.
  func testTheLegacyShellReportsNoHomeStageModeWhateverItWasLastTold() {
    for route in [ChatFirstRoute.chat, .more(.dashboard), .tasks] {
      XCTAssertNil(
        HomeStageAutomationPolicy.reportedHomeMode(
          usesChatFirstShell: false,
          chatFirstRoute: route,
          lastPublishedMode: "hub"),
        "the legacy shell renders no stage, so it may not report one even with a route in hand")
    }
    XCTAssertNil(
      HomeStageAutomationPolicy.reportedHomeMode(
        usesChatFirstShell: false,
        chatFirstRoute: nil,
        lastPublishedMode: "connect"))
  }

  /// On the shell that *does* mount `DashboardPage`, the field carries what that page published —
  /// unchanged, and `nil` until it has published anything. The shell is a courier here, not a source:
  /// substituting a default is what turned a missing reading into a false one.
  func testTheChatFirstShellCarriesTheStageOwnersValueWithoutInventingOne() {
    for mode in ["hub", "chat", "connect"] {
      XCTAssertEqual(
        HomeStageAutomationPolicy.reportedHomeMode(
          usesChatFirstShell: true,
          chatFirstRoute: .chat,
          lastPublishedMode: mode),
        mode)
    }
    XCTAssertNil(
      HomeStageAutomationPolicy.reportedHomeMode(
        usesChatFirstShell: true,
        chatFirstRoute: .chat,
        lastPublishedMode: nil),
      "before DashboardPage reports, the honest answer is 'not known', not 'hub'")
  }

  func testChatFirstGlassBoundaryWrapsOnlyRoutesWithoutTheirOwnPanels() {
    let wrapped: [ChatFirstRoute] = [
      .conversations, .tasks, .goals, .memories,
      .more(.apps), .more(.permissions), .more(.settings),
    ]
    let selfContained: [ChatFirstRoute] = [.chat, .more(.dashboard), .more(.rewind)]

    for route in wrapped {
      XCTAssertTrue(ChatFirstPageGlassLanePolicy.shouldWrap(route), route.stableName)
      XCTAssertNotEqual(
        ChatFirstPageGlassLanePolicy.pageGlassLaneIndex(for: route),
        SidebarNavItem.dashboard.rawValue,
        route.stableName)
      XCTAssertNotEqual(
        ChatFirstPageGlassLanePolicy.pageGlassLaneIndex(for: route),
        SidebarNavItem.rewind.rawValue,
        route.stableName)
    }
    for route in selfContained {
      XCTAssertFalse(ChatFirstPageGlassLanePolicy.shouldWrap(route), route.stableName)
    }

    // The memory route mounts the hub, whose Activity page carries Home's own two panels. Wrapping
    // that one puts glass inside glass and doubles the scrim.
    XCTAssertFalse(
      ChatFirstPageGlassLanePolicy.shouldWrap(
        .memories, memoryDestinationRawValue: MemoryHubDestination.activity.rawValue))
    for destination in MemoryHubDestination.allCases where destination != .activity {
      XCTAssertTrue(
        ChatFirstPageGlassLanePolicy.shouldWrap(
          .memories, memoryDestinationRawValue: destination.rawValue),
        destination.title)
    }
  }

  /// Only the two routes that mount `DashboardPage` have a stage. Navigating away publishes `nil`
  /// rather than leaving the last mode standing, which is how the field stops describing a page that
  /// is no longer on screen.
  func testOnlyTheRoutesThatMountDashboardPageReportAStage() {
    XCTAssertTrue(HomeStageAutomationPolicy.mountsHomeStage(.chat))
    XCTAssertTrue(HomeStageAutomationPolicy.mountsHomeStage(.more(.dashboard)))

    for route: ChatFirstRoute in [
      .conversations, .tasks, .goals, .memories,
      .more(.apps), .more(.rewind), .more(.settings), .more(.permissions),
    ] {
      XCTAssertFalse(
        HomeStageAutomationPolicy.mountsHomeStage(route),
        "\(route.stableName) does not render the stage")
      XCTAssertNil(
        HomeStageAutomationPolicy.reportedHomeMode(
          usesChatFirstShell: true,
          chatFirstRoute: route,
          lastPublishedMode: "connect"),
        "\(route.stableName) must not keep reporting the mode the stage had before we left it")
    }
  }
}
