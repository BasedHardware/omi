import AppKit
import SwiftUI
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

  func testSuccessfulSampleResolvesCapabilityAndCannotLiveSwap() throws {
    var sample = ChatFirstCapabilitySample()
    sample.resolve(
      control: enabledControl(),
      requestedOwnerID: "owner-a",
      ownerIsStillCurrent: true
    )

    XCTAssertEqual(sample.projection?.controlGeneration, 7)
    XCTAssertTrue(sample.isResolved)

    sample.resolve(
      control: OmiAPI.TaskWorkflowControl(accountGeneration: 8, chatFirstUi: false, workflowMode: .off),
      requestedOwnerID: "owner-a",
      ownerIsStillCurrent: true
    )
    XCTAssertEqual(sample.projection?.controlGeneration, 7)
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

  func testMissingStaleAndOwnerChangedSamplesFailClosedToCapabilityOff() {
    var missing = ChatFirstCapabilitySample()
    missing.resolve(control: nil, requestedOwnerID: "owner-a", ownerIsStillCurrent: true)
    XCTAssertNil(missing.projection)
    XCTAssertTrue(missing.isResolved, "a failed read still resolves — it must not re-request forever")

    var stale = ChatFirstCapabilitySample()
    stale.resolve(control: enabledControl(), requestedOwnerID: "owner-a", ownerIsStillCurrent: false)
    XCTAssertNil(stale.projection)

    var ownerChanged = ChatFirstCapabilitySample()
    ownerChanged.resolve(control: enabledControl(), requestedOwnerID: "owner-a", ownerIsStillCurrent: true)
    ownerChanged.ownerDidChange(to: "owner-b")
    XCTAssertNil(ownerChanged.projection)
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
    XCTAssertEqual(navigation.route, .memories)
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
    XCTAssertEqual(restored.route, .memories)
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

    XCTAssertEqual(navigation.route, .memories)
    XCTAssertEqual(navigation.pendingConversation, fetched)
    XCTAssertNil(navigation.pendingFocus)
  }

  func testActivityConversationDeepLinkStaysOnTheHubOwnedConversationsDestination() throws {
    let suiteName = "ChatFirstShellTests.activity-conversation-route.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(defaults: defaults)
    let fetched = conversation(id: "activity-meeting-42")
    navigation.open(conversation: fetched, destination: .memories)

    XCTAssertEqual(navigation.route, .memories)
    XCTAssertEqual(navigation.pendingConversation, fetched)
    XCTAssertNil(navigation.pendingFocus)
  }

  func testStagingConversationReferencePreservesDraftAndDoesNotSubmitATurn() throws {
    let suiteName = "ChatFirstShellTests.capture-reference.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(defaults: defaults)
    let provider = ChatProvider()
    provider.draftText = "Keep this draft"
    let messageCount = provider.messages.count

    navigation.stageCaptureReference(conversation(id: "capture-42"), using: provider)

    XCTAssertEqual(navigation.route, .chat)
    XCTAssertEqual(provider.draftText, "Keep this draft")
    XCTAssertEqual(provider.messages.count, messageCount)
    XCTAssertEqual(provider.pendingComposerReferences.map(\.sourceID), ["capture-42"])
  }

  func testRuntimeOwnerChangeClearsTransientConversationAndFocusRouting() throws {
    let suiteName = "ChatFirstShellTests.owner-change.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    let navigation = ChatFirstShellNavigation(defaults: defaults)
    navigation.open(conversation: conversation(id: "owner-a-conversation"))

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)

    XCTAssertNil(navigation.pendingConversation)

    navigation.open(focus: .capture(id: "owner-a-capture", momentTs: 12))
    let staleGeneration = navigation.beginConversationLinkResolution()

    NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)

    XCTAssertNil(navigation.pendingFocus)
    XCTAssertNil(navigation.focusedEntityID)
    XCTAssertFalse(navigation.isFocusedEntityAcknowledged)
    XCTAssertFalse(navigation.isCurrentConversationLinkResolution(staleGeneration))
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
    XCTAssertTrue(source.contains("private var settingsDestination: some View"))
    XCTAssertTrue(source.contains("SettingsSidebar("))
    XCTAssertTrue(source.contains("SettingsPage("))
    XCTAssertTrue(source.contains("case .permissions, .settings:"))
    XCTAssertTrue(source.contains("navigation.handleEscapeNavigation()"))
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
    XCTAssertEqual(navigation.route, .memories)
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
    XCTAssertEqual(ChatFirstRoute.primaryAutomationDestination(named: "conversations"), .memories)
    XCTAssertEqual(ChatFirstRoute.primaryAutomationDestination(named: "goals"), .goals)
    XCTAssertEqual(ChatFirstRoute.primaryAutomationDestination(named: "GOALS"), .goals)
    XCTAssertNil(ChatFirstRoute.primaryAutomationDestination(named: "dashboard"))
    XCTAssertNil(ChatFirstRoute.primaryAutomationDestination(named: "settings"))
  }

  func testAutomationNavigationVisibilityAcceptsTheMountedShellForSharedNames() {
    XCTAssertEqual(ChatFirstRoute.automationVisibilityDestination(named: "settings"), .more(.settings))
    XCTAssertEqual(ChatFirstRoute.automationVisibilityDestination(named: "home"), .chat)
    XCTAssertEqual(ChatFirstRoute.automationVisibilityDestination(named: "dashboard"), .chat)
    // `navigate help` resolved a title no shell mounted and then timed out.
    XCTAssertEqual(ChatFirstRoute.automationVisibilityDestination(named: "help"), .more(.settings))
    XCTAssertTrue(ChatFirstRoute.isHelpAutomationTarget("HELP"))
    XCTAssertFalse(ChatFirstRoute.isHelpAutomationTarget("settings"))

    XCTAssertTrue(
      DesktopAutomationNavigationVisibilityPolicy.isTargetVisible(
        shellVariant: DesktopAutomationSnapshot.singleShellVariant,
        visibleChatFirstRoute: "tasks",
        expectedChatFirstRoute: "tasks"
      )
    )
    XCTAssertFalse(
      DesktopAutomationNavigationVisibilityPolicy.isTargetVisible(
        shellVariant: DesktopAutomationSnapshot.singleShellVariant,
        visibleChatFirstRoute: "chat",
        expectedChatFirstRoute: "tasks"
      )
    )
    // No shell has reported state yet: a target cannot be "visible" on nothing.
    XCTAssertFalse(
      DesktopAutomationNavigationVisibilityPolicy.isTargetVisible(
        shellVariant: nil,
        visibleChatFirstRoute: "tasks",
        expectedChatFirstRoute: "tasks"
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

  func testChatFirstGlassBoundaryWrapsOnlyRoutesWithoutTheirOwnPanels() {
    let wrapped: [ChatFirstRoute] = [
      .goals,
      .more(.permissions), .more(.settings),
    ]
    let selfContained: [ChatFirstRoute] = [
      .chat, .conversations, .tasks, .memories, .more(.dashboard), .more(.rewind),
      .more(.apps),
    ]

    for route in wrapped {
      XCTAssertTrue(ChatFirstPageGlassLanePolicy.shouldWrap(route), route.stableName)
    }
    for route in selfContained {
      XCTAssertFalse(ChatFirstPageGlassLanePolicy.shouldWrap(route), route.stableName)
    }

    // Every hub page carries the shared search panel and a navigation-first content panel.
    for destination in MemoryHubDestination.allCases {
      XCTAssertFalse(
        ChatFirstPageGlassLanePolicy.shouldWrap(.memories),
        destination.title)
    }
  }

  /// Conversation links and the Memories tab mount the same hub-owned surface,
  /// so both aliases pass through the shell without a second glass lane.
  func testChatFirstConversationAliasesUseTheMemoryHubSurface() throws {
    let size = CGSize(width: 1_400, height: 800)

    let recorder = ChatFirstGlassFrameRecorder()
    let host = NSHostingView(
      rootView: ChatFirstPageGlassLane(route: .conversations) {
        ChatFirstGlassFrameProbe(recorder: recorder)
      }
      .frame(width: size.width, height: size.height)
    )
    host.frame = NSRect(origin: .zero, size: size)
    host.layoutSubtreeIfNeeded()

    let placed = try XCTUnwrap(recorder.frame)
    XCTAssertEqual(placed.width, size.width, accuracy: 0.5)
    XCTAssertEqual(placed.height, size.height, accuracy: 0.5)
  }

  func testChatFirstMemoryHubKeepsItsOwnPanels() throws {
    let size = CGSize(width: 1_400, height: 800)
    let recorder = ChatFirstGlassFrameRecorder()
    let host = NSHostingView(
      rootView: ChatFirstPageGlassLane(route: .memories) {
        ChatFirstGlassFrameProbe(recorder: recorder)
      }
      .frame(width: size.width, height: size.height)
    )
    host.frame = NSRect(origin: .zero, size: size)
    host.layoutSubtreeIfNeeded()

    let placed = try XCTUnwrap(recorder.frame)
    XCTAssertEqual(placed.width, size.width, accuracy: 0.5)
    XCTAssertEqual(placed.height, size.height, accuracy: 0.5)
  }

  func testEveryChatFirstRouteMountsTheGroundItsPolicyDeclares() throws {
    let size = CGSize(width: 1_400, height: 800)
    let cases: [(ChatFirstRoute, Bool)] = [
      (.chat, false),
      (.conversations, false),
      (.tasks, false),
      (.goals, true),
      (.memories, false),
      (.more(.dashboard), false),
      (.more(.rewind), false),
      (.more(.apps), false),
      (.more(.permissions), true),
      (.more(.settings), true),
    ]

    for (route, expectsSharedLane) in cases {
      let recorder = ChatFirstGlassFrameRecorder()
      let host = NSHostingView(
        rootView: ChatFirstPageGlassLane(route: route) {
          ChatFirstGlassFrameProbe(recorder: recorder)
        }
        .frame(width: size.width, height: size.height)
      )
      host.frame = NSRect(origin: .zero, size: size)
      host.layoutSubtreeIfNeeded()

      let placed = try XCTUnwrap(recorder.frame, route.stableName)
      let expectedHeight =
        expectsSharedLane
        ? size.height - PageGlassLaneLayout.topGap - PageGlassLaneLayout.bottomGap
        : size.height
      XCTAssertEqual(placed.height, expectedHeight, accuracy: 0.5, route.stableName)
      XCTAssertEqual(
        ChatFirstPageGlassLanePolicy.shouldWrap(route),
        expectsSharedLane,
        route.stableName)
    }
  }

}

private final class ChatFirstGlassFrameRecorder: @unchecked Sendable {
  private(set) var frame: CGRect?

  func record(_ frame: CGRect) {
    self.frame = frame
  }
}

private struct ChatFirstGlassFrameProbe: View {
  let recorder: ChatFirstGlassFrameRecorder

  var body: some View {
    ChatFirstGlassFrameProbeLayout(recorder: recorder) {
      Color.clear
    }
  }
}

private struct ChatFirstGlassFrameProbeLayout: Layout {
  let recorder: ChatFirstGlassFrameRecorder

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
    CGSize(width: proposal.width ?? 0, height: proposal.height ?? 0)
  }

  func placeSubviews(
    in bounds: CGRect,
    proposal: ProposedViewSize,
    subviews: Subviews,
    cache: inout ()
  ) {
    recorder.record(bounds)
    for subview in subviews {
      subview.place(at: bounds.origin, proposal: ProposedViewSize(bounds.size))
    }
  }
}
