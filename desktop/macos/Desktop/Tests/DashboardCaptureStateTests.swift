import XCTest

@testable import Omi_Computer

final class DashboardCaptureStateTests: XCTestCase {
  @MainActor
  func testLiveCapturingIsFalseWhileAwaitingAMeeting() {
    let appState = AppState()
    appState.isTranscribing = true
    appState.isAwaitingMeeting = true
    XCTAssertFalse(
      appState.isLiveCapturing,
      "Only Meetings with no call pauses the mic; Live UI must not treat the armed session as capture.")

    appState.isAwaitingMeeting = false
    XCTAssertTrue(appState.isLiveCapturing)

    appState.isTranscribing = false
    XCTAssertFalse(appState.isLiveCapturing)
  }

  @MainActor
  func testListeningStatusIsInactiveWhileAwaitingAMeeting() {
    let appState = AppState()
    appState.isTranscribing = true
    appState.isAwaitingMeeting = true
    XCTAssertEqual(CaptureListeningLogic.listeningStatus(appState: appState), .inactive)

    appState.isAwaitingMeeting = false
    XCTAssertEqual(CaptureListeningLogic.listeningStatus(appState: appState), .active)
  }

  @MainActor
  func testHomeListeningHelpDoesNotClaimOffWhileAwaitingAMeeting() {
    let help = HomeListeningStatusButton.helpText(
      status: .inactive, modeTitle: "Only Meetings", isAwaitingMeeting: true)
    XCTAssertTrue(help.contains("waiting for a call"))
    XCTAssertTrue(help.contains("Only Meetings"))
    XCTAssertTrue(help.contains("Click to turn off"))
    XCTAssertFalse(help.contains("Off"))
    XCTAssertEqual(
      HomeListeningStatusButton.helpText(
        status: .inactive, modeTitle: "Always On", isAwaitingMeeting: false),
      "Listening: Off, Always On")
  }

  @MainActor
  func testListeningModeTitlePreservesOakleyMetaName() {
    let appState = AppState()
    appState.isTranscribing = true
    appState.recordingInputDeviceName = "Oakley Meta Vanguard"

    XCTAssertEqual(
      CaptureListeningLogic.listeningModeTitle(appState: appState, raw: "always"),
      "Oakley Meta Vanguard")
  }

  func testDashboardCaptureStatusUsesLiveMonitoringState() throws {
    let source = try dashboardSource()
    let logic = try captureLogicSource()

    // The header derives capture status from the shared CaptureListeningLogic…
    XCTAssertTrue(
      source.contains(
        "CaptureListeningLogic.captureStatus(appState: appState, isCaptureMonitoring: isCaptureMonitoring)"),
      "DashboardPage should derive capture status from the shared CaptureListeningLogic"
    )
    // …which lights up from the LIVE monitor, never stale persisted intent.
    XCTAssertTrue(
      logic.contains("return isCaptureLive(isCaptureMonitoring: isCaptureMonitoring) ? .active : .inactive"),
      "Capture status should light up when monitoring is live, even if persisted intent is stale"
    )
    XCTAssertTrue(
      logic.contains("isCaptureMonitoring || ProactiveAssistantsPlugin.shared.isMonitoring"),
      "Live capture state must reflect the running monitor"
    )
    XCTAssertFalse(
      logic.contains("if screenAnalysisEnabled && isCaptureMonitoring {\n            return .active\n        }"),
      "Capture status must not require persisted intent to match the live monitor"
    )
  }

  func testDashboardCaptureToggleDerivesFromLiveState() throws {
    let source = try dashboardSource()
    let logic = try captureLogicSource()

    XCTAssertTrue(
      source.contains("CaptureListeningLogic.toggleCapture("),
      "DashboardPage's capture toggle should route through the shared CaptureListeningLogic"
    )
    XCTAssertTrue(
      logic.contains(
        "syncCaptureState(screenAnalysisEnabled: screenAnalysisEnabled, isCaptureMonitoring: isCaptureMonitoring)"),
      "Capture toggles should reconcile the live monitor before deciding whether the click starts or stops capture"
    )
    XCTAssertTrue(
      logic.contains("let enabled = !isCaptureLive(isCaptureMonitoring: isCaptureMonitoring.wrappedValue)"),
      "Capture toggles should derive the next state from the live monitor"
    )
    XCTAssertFalse(
      logic.contains("let enabled = !screenAnalysisEnabled"),
      "Capture toggles should not derive from stale persisted intent"
    )
  }

  func testListeningPillReflectsTheUnifiedAudioRecordingMode() throws {
    let source = try dashboardSource()
    let logic = try captureLogicSource()

    XCTAssertTrue(source.contains("@AppStorage(AssistantSettings.audioRecordingModeDefaultsKey)"))
    XCTAssertTrue(source.contains("private var listeningModeTitle: String"))
    XCTAssertTrue(logic.contains("return appState.isAwaitingMeeting ? \"Only Meetings\" : \"In Meeting\""))
    XCTAssertTrue(source.contains("HomeListeningStatusButton("))
    XCTAssertFalse(source.contains("modeAction: toggleListeningMode"))
    XCTAssertFalse(logic.contains("toggleListeningMode"))
    XCTAssertTrue(source.contains(".frame(height: 34)"))
    XCTAssertFalse(source.contains("Circle()\n                    .fill(status.indicator)"))
    XCTAssertFalse(source.contains("OmiColors.purplePrimary"))
  }

  func testListeningStatusIsSharedAndLiveTranscriptExpandReplacesThePage() throws {
    let dashboard = try dashboardSource()
    let logic = try captureLogicSource()
    let conversations = try source(named: "ConversationsPage.swift")
    let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let shellURL =
      testsURL
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/QueryShell/ShellStatusIcons.swift")
    // omi-test-quality: source-inspection -- static contract: which predicate the Live card and listening dot name is not observable from a running view without a window server
    let shell = try String(contentsOf: shellURL, encoding: .utf8)

    XCTAssertTrue(logic.contains("return appState.isLiveCapturing ? .active : .inactive"))
    XCTAssertTrue(dashboard.contains("CaptureListeningLogic.listeningStatus(appState: appState)"))
    XCTAssertTrue(dashboard.contains("isAwaitingMeeting: appState.isAwaitingMeeting"))
    XCTAssertTrue(shell.contains("CaptureListeningLogic.listeningStatus(appState: appState)"))
    XCTAssertTrue(conversations.contains("if appState.isLiveCapturing {"))
    XCTAssertTrue(conversations.contains("if isLiveTranscriptExpanded && appState.isLiveCapturing"))
    XCTAssertFalse(
      conversations.contains(".overlay {\n      if isLiveTranscriptExpanded"),
      "Expanding the live transcript must replace the Conversations page body, not overlay it.")
  }

  func testRedesignedHomeUsesResponsiveStageSizing() throws {
    let source = try dashboardSource()

    XCTAssertTrue(source.contains("private static let homeStageMaxWidth: CGFloat = 1360"))
    XCTAssertTrue(source.contains("private static let homeAskBarMinWidth: CGFloat = 560"))
    XCTAssertTrue(source.contains("private static let homeStagePanelMaxWidth: CGFloat = 1280"))
    XCTAssertTrue(source.contains("private func homeStageSideInset(for stageWidth: CGFloat) -> CGFloat"))
    XCTAssertTrue(source.contains("private func homeHubAskBarWidth(for stageWidth: CGFloat, draft: String) -> CGFloat"))
    XCTAssertTrue(
      source.contains("(text as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: 15)]).width"))
    XCTAssertTrue(source.contains("private func homeHubStage(stageWidth: CGFloat) -> some View"))
    XCTAssertTrue(source.contains("private var homeHubHeadline: some View"))
    XCTAssertFalse(source.contains(".frame(width: 304)"))
    XCTAssertFalse(source.contains(".frame(maxWidth: Self.homeAskBarMaxWidth)"))
    XCTAssertFalse(source.contains(".frame(maxWidth: Self.homeStagePanelMaxWidth)"))
  }

  func testHomeAskBarRefocusesAfterOpeningChatStage() throws {
    let source = try dashboardSource()
    let openChat = try methodBody(named: "openHomeChat", in: source)

    XCTAssertTrue(source.contains("private func openHomeChat(focusInput: Bool = true)"))
    XCTAssertTrue(source.contains("focusHomeAskFieldAfterStageTransition()"))
    XCTAssertTrue(source.contains("await Task.yield()"))
    XCTAssertTrue(source.contains("homeAskFieldFocused = true"))
    XCTAssertTrue(source.contains("openHomeChat(focusInput: false)"))
    // omi-test-quality: source-inspection -- static contract: the SwiftUI focus
    // state and navigation method are private view wiring, so the hotkey's
    // already-visible-chat path cannot be driven from the test host.
    XCTAssertTrue(
      openChat.contains("if homeMode != .chat {"),
      "Opening an already-visible chat must still continue to the input-focus request")
    XCTAssertFalse(
      openChat.contains("guard homeMode != .chat else { return }"),
      "An early return drops the hotkey's input focus when chat is already visible")
  }

  func testSecondaryHomePagesReturnHomeOnEscape() {
    for item in [SidebarNavItem.conversations, .memories, .tasks, .rewind] {
      XCTAssertTrue(
        DesktopHomeEscapeNavigation.shouldNavigateHome(
          selectedIndex: item.rawValue,
          usesLegacyHomeDesign: false
        ))
    }
    // `.chat` was removed from `SidebarNavItem` when the standalone chat page was deleted. Escape on
    // Home itself still must not navigate home, so the case moves to the destination Home now is.
    XCTAssertFalse(
      DesktopHomeEscapeNavigation.shouldNavigateHome(
        selectedIndex: SidebarNavItem.dashboard.rawValue,
        usesLegacyHomeDesign: false
      ))
    XCTAssertFalse(
      DesktopHomeEscapeNavigation.shouldNavigateHome(
        selectedIndex: SidebarNavItem.tasks.rawValue,
        usesLegacyHomeDesign: true
      ))
  }

  func testHomeConnectorButtonsOpenSheetsDirectly() throws {
    let source = try dashboardSource()
    let importMethod = try methodBody(named: "openImportConnector", in: source)
    let exportMethod = try methodBody(named: "openExportDestination", in: source)

    XCTAssertTrue(source.contains("@State private var selectedImportConnector: ImportConnector?"))
    XCTAssertTrue(source.contains("@State private var selectedExportDestination: MemoryExportDestination?"))
    XCTAssertFalse(source.contains(".dismissableSheet(item: $selectedImportConnector)"))
    XCTAssertFalse(source.contains(".dismissableSheet(item: $selectedExportDestination)"))
    XCTAssertTrue(importMethod.contains("presentImportConnector(connector)"))
    XCTAssertTrue(exportMethod.contains("presentExportDestination(destination)"))
    XCTAssertFalse(importMethod.contains("navigate(to: .apps)"))
    XCTAssertFalse(exportMethod.contains("navigate(to: .apps)"))
  }

  func testHomeMoreUsesAppsPopup() throws {
    let source = try dashboardSource()
    let normalizedSource = normalizedWhitespace(source)
    let popupMethod = try methodBody(named: "openAppsPopup", in: source)
    let appSelectionMethod = try methodBody(named: "openAppFromAppsPopup", in: source)
    let importSelectionMethod = try methodBody(named: "openImportConnectorFromAppsPopup", in: source)
    let exportSelectionMethod = try methodBody(named: "openExportDestinationFromAppsPopup", in: source)

    XCTAssertTrue(source.contains("@State private var isShowingAppsPopup = false"))
    XCTAssertTrue(source.contains("@State private var selectedCatalogApp: OmiApp?"))
    XCTAssertTrue(source.contains("@State private var appsPopupInitialSection: AppsCatalogInitialSection = .imports"))
    XCTAssertTrue(source.contains("@State private var appsPopupPresentationID = UUID()"))
    XCTAssertTrue(source.contains("private func appsPopupOverlay("))
    XCTAssertTrue(normalizedSource.contains("AppsPage( appProvider: appProvider, appState: appState,"))
    XCTAssertTrue(source.contains("initialSection: appsPopupInitialSection"))
    XCTAssertTrue(normalizedSource.contains("onSelectApp: { app in openAppFromAppsPopup(app) }"))
    XCTAssertTrue(
      normalizedSource.contains("onSelectConnector: { connector in openImportConnectorFromAppsPopup(connector) }"))
    XCTAssertTrue(
      normalizedSource.contains(
        "onSelectDestination: { destination in openExportDestinationFromAppsPopup(destination) }"))
    XCTAssertTrue(source.contains(".id(appsPopupPresentationID)"))
    XCTAssertTrue(normalizedSource.contains("onDismiss: { dismissAppsPopup()"))
    XCTAssertTrue(source.contains(".frame(width: popupSize.width, height: popupSize.height)"))
    XCTAssertTrue(
      source.contains(".clipShape(RoundedRectangle(cornerRadius: Self.appsPopupCornerRadius, style: .continuous))"))
    // omi-test-quality: source-inspection -- static contract: whether Home hands its dim a dismiss
    // action. `isShowingAppsPopup` is private `@State` on a view that needs five live providers to
    // mount, so the popup cannot be raised and clicked from the test host. That a click on the dim
    // then runs this action — anywhere on the host, including the undimmed band beside the paint —
    // is exercised for real in `ShellModalScrimDismissTests`; this is only the wiring that reaches
    // it. It reads Home's own file because Home is what must do the wiring.
    XCTAssertTrue(
      normalizedSource.contains("ShellModalScrim(onTap: dismissAppsPopup)"),
      "The dim behind the apps popup must carry Home's dismiss action, or clicking outside the "
        + "popup stops closing it")
    XCTAssertTrue(
      normalizedSource.contains("OverlayModalEscapeCatcher { dismissAppsPopup()"))
    XCTAssertTrue(
      source.contains(
        "HomeAIChoiceButton(title: \"More\", systemImage: \"plus\") {\n        openAppsPopup(initialSection: .imports)"
      ))
    XCTAssertTrue(
      source.contains(
        "HomeAIChoiceButton(title: \"More\", systemImage: \"plus\") {\n        openAppsPopup(initialSection: .exports)"
      ))
    XCTAssertFalse(source.contains("@State private var dashboardContentSize"))
    XCTAssertFalse(source.contains(".dismissableSheet(isPresented: $isShowingAppsPopup)"))
    XCTAssertFalse(source.contains("HomeMoreConnectorsSheet"))
    XCTAssertFalse(source.contains("openAppsPage()"))
    XCTAssertTrue(
      popupMethod.contains("appProvider.clearFilters()"),
      "Opening the Home popup must clear stale marketplace filters or they replace the Imports/Exports sections"
    )
    XCTAssertTrue(popupMethod.contains("appsPopupInitialSection = initialSection"))
    XCTAssertTrue(popupMethod.contains("appsPopupPresentationID = UUID()"))
    XCTAssertTrue(popupMethod.contains("appsPopupAcceptsInput = true"))
    XCTAssertTrue(popupMethod.contains("isShowingAppsPopup = true"))
    XCTAssertFalse(popupMethod.contains("navigate(to: .apps)"))
    XCTAssertTrue(appSelectionMethod.contains("dismissAppsPopup()"))
    XCTAssertTrue(appSelectionMethod.contains("presentCatalogApp(app)"))
    XCTAssertTrue(importSelectionMethod.contains("dismissAppsPopup()"))
    XCTAssertTrue(importSelectionMethod.contains("presentImportConnector(connector)"))
    XCTAssertTrue(exportSelectionMethod.contains("dismissAppsPopup()"))
    XCTAssertTrue(exportSelectionMethod.contains("presentExportDestination(destination)"))
  }

  func testHomeConnectSheetsUseHomeScopedPresentation() throws {
    let source = try dashboardSource()
    let normalizedSource = normalizedWhitespace(source)

    XCTAssertTrue(source.contains("private var homeConnectSheetIsPresented: Bool"))
    XCTAssertTrue(source.contains("private var legacySelectedCatalogApp: Binding<OmiApp?>"))
    XCTAssertTrue(source.contains("private var legacySelectedImportConnector: Binding<ImportConnector?>"))
    XCTAssertTrue(source.contains("private var legacySelectedExportDestination: Binding<MemoryExportDestination?>"))
    XCTAssertTrue(source.contains("homeConnectSheetOverlay(\n          contentWidth: proxy.size.width"))
    XCTAssertTrue(
      source.contains("let sheetSize = homeConnectSheetSize(panelWidth: panelWidth, panelHeight: panelHeight)"))
    XCTAssertTrue(source.contains(".position(x: contentWidth / 2, y: panelTop + panelHeight / 2)"))
    // omi-test-quality: source-inspection -- static contract: same wiring as the apps popup above,
    // for the sheet stacked on top of it, and unreachable for the same reason —
    // `selectedImportConnector` and its siblings are private `@State`. The click that runs it is
    // behavioural in `ShellModalScrimDismissTests`.
    XCTAssertTrue(
      normalizedSource.contains("ShellModalScrim(onTap: dismissHomeConnectSheet)"),
      "The dim behind the Home connect sheet must carry its dismiss action, or clicking outside the "
        + "sheet stops closing it")
    XCTAssertFalse(source.contains("homeConnectSheetHasKeyboardFocus"))
    XCTAssertTrue(source.contains("private func dismissHomeConnectSheet()"))
  }

  func testHomeOverlaysStopHitTestingWhenDismissStarts() throws {
    let source = try dashboardSource()
    let popupDismissMethod = try methodBody(named: "dismissAppsPopup", in: source)
    let connectDismissMethod = try methodBody(named: "dismissHomeConnectSheet", in: source)

    XCTAssertTrue(source.contains("@State private var appsPopupAcceptsInput = false"))
    XCTAssertTrue(source.contains("@State private var homeConnectSheetAcceptsInput = false"))
    XCTAssertTrue(source.contains(".allowsHitTesting(appsPopupAcceptsInput && !homeConnectSheetIsPresented)"))
    XCTAssertTrue(source.contains("if appsPopupAcceptsInput && !homeConnectSheetIsPresented"))
    XCTAssertTrue(source.contains(".allowsHitTesting(homeConnectSheetAcceptsInput)"))
    XCTAssertTrue(source.contains("if homeConnectSheetAcceptsInput"))
    XCTAssertTrue(popupDismissMethod.contains("appsPopupAcceptsInput = false"))
    XCTAssertTrue(popupDismissMethod.contains("isShowingAppsPopup = false"))
    XCTAssertTrue(connectDismissMethod.contains("homeConnectSheetAcceptsInput = false"))
    XCTAssertTrue(connectDismissMethod.contains("selectedImportConnector = nil"))
    XCTAssertTrue(connectDismissMethod.contains("selectedExportDestination = nil"))
  }

  func testConnectorRowsUseStatusConnectionForConnectedState() throws {
    let destinationSheet = try source(named: "MemoryExportDestinationSheet.swift")
    let groupedSheet = try source(named: "AgentConnectPickerSheet.swift")
    let rowHelper = try computedPropertyBody(named: "showsConnectedState", in: destinationSheet)
    let singleSheetHelper = try computedPropertyBody(named: "isConnected", in: destinationSheet)
    let optionHelper = try computedPropertyBody(named: "isConnected", in: groupedSheet)

    XCTAssertTrue(rowHelper.contains("status.hasConnection"))
    XCTAssertTrue(rowHelper.contains("destination.supportsMCP || destination.supportsAgentSetup"))
    XCTAssertTrue(singleSheetHelper.contains("destination.hasLocallyVerifiableLiveSetup"))
    XCTAssertTrue(singleSheetHelper.contains("statuses[destination]?.hasConnection == true"))
    XCTAssertTrue(optionHelper.contains("statuses[destination]?.hasConnection == true"))
    XCTAssertTrue(optionHelper.contains("destination.hasLocallyVerifiableLiveSetup"))
  }

  func testGroupedConnectorSetupUsesUserSafeFailureCopy() throws {
    let source = try source(named: "AgentConnectPickerSheet.swift")

    XCTAssertTrue(source.contains("resultMessage = .failure(setupFailureMessage(for: error))"))
    XCTAssertFalse(source.contains("resultMessage = .failure(error.localizedDescription)"))
  }

  func testAppsPageSupportsPopupDismissalAndFocusedSections() throws {
    let source = try appsSource()

    XCTAssertTrue(source.contains("enum AppsCatalogInitialSection"))
    XCTAssertTrue(source.contains("var initialSection: AppsCatalogInitialSection = .imports"))
    XCTAssertTrue(source.contains("var onDismiss: (() -> Void)? = nil"))
    XCTAssertTrue(source.contains("var onSelectApp: ((OmiApp) -> Void)? = nil"))
    XCTAssertTrue(source.contains("var onSelectConnector: ((ImportConnector) -> Void)? = nil"))
    XCTAssertTrue(source.contains("var onSelectDestination: ((MemoryExportDestination) -> Void)? = nil"))
    XCTAssertTrue(source.contains("private var dismissControl: some View"))
    XCTAssertTrue(source.contains("DismissButton(action: onDismiss)"))
    XCTAssertTrue(
      source.contains(
        "case .imports:\n                ImportsSection(statusStore: connectorStatusStore)"))
    XCTAssertTrue(
      source.contains("case .exports:\n                ExportsSection(statuses: exportStatuses)"))
    XCTAssertTrue(source.contains("private func selectApp(_ app: OmiApp)"))
    XCTAssertTrue(source.contains("private func selectConnector(_ connector: ImportConnector)"))
    XCTAssertTrue(source.contains("private func selectDestination(_ destination: MemoryExportDestination)"))
    XCTAssertTrue(source.contains("onSelectApp(app)"))
    XCTAssertTrue(source.contains("selectedApp = app"))
    XCTAssertTrue(source.contains("onSelectConnector(connector)"))
    XCTAssertTrue(source.contains("selectedConnector = connector"))
    XCTAssertTrue(source.contains("onSelectDestination(destination)"))
    XCTAssertTrue(source.contains("selectedExportDestination = destination"))
    XCTAssertTrue(source.contains("if appProvider.apps.isEmpty && !appProvider.isLoading"))
    // Responsive layout was extracted into AppsHeaderRow (AppsPageHeaderControls.swift);
    // AppsPage now delegates to it instead of inlining ViewThatFits.
    XCTAssertTrue(source.contains("AppsHeaderRow("))
    XCTAssertTrue(source.contains("private var searchField: some View"))
    XCTAssertTrue(source.contains("private var filterControls: some View"))
    XCTAssertFalse(source.contains("struct AppsCatalogContent: View"))
  }

  func testConnectorSetupSurfacesDoNotUsePurpleAccents() throws {
    let memoryExportSheet = try source(named: "MemoryExportDestinationSheet.swift")
    let apps = try appsSource()

    let disallowedColors = [
      "OmiColors.purplePrimary",
      "OmiColors.purpleSecondary",
      "OmiColors.purpleAccent",
      "OmiColors.purpleLight",
      "OmiColors.userBubble",
      "OmiColors.purpleGradient",
    ]
    for color in disallowedColors {
      XCTAssertFalse(memoryExportSheet.contains(color))
      XCTAssertFalse(apps.contains(color))
    }
  }

  func testHomeOverlaysBehaveLikeModals() throws {
    let dashboard = try dashboardSource()
    let apps = try appsSource()
    // The `dismissableSheet` modifiers are the shared presentation primitive
    // both Home overlays and the pages mount; they live beside the pages that
    // use them rather than inside any one of them.
    let dismissableSheet = try source(named: "DismissableSheet.swift")
    let escapeKeyHandler = try escapeKeyHandlerSource()
    let normalizedDashboard = normalizedWhitespace(dashboard)

    // Esc must dismiss the topmost overlay. Custom ZStack overlays are not
    // NSWindow sheets, so Esc comes from the shared catcher's window-scoped
    // key monitor — onExitCommand never fires (the overlays are never
    // focused) and hidden cancel-shortcut buttons get culled from dispatch.
    XCTAssertTrue(escapeKeyHandler.contains("struct OverlayModalEscapeCatcher: View"))
    XCTAssertTrue(escapeKeyHandler.contains("struct EscapeKeyHandler: NSViewRepresentable"))
    XCTAssertTrue(escapeKeyHandler.contains("NSEvent.addLocalMonitorForEvents(matching: .keyDown)"))
    XCTAssertTrue(escapeKeyHandler.contains("registration.window === window"))
    XCTAssertTrue(
      dashboard.contains("if appsPopupAcceptsInput && !homeConnectSheetIsPresented"),
      "The apps popup owns Esc only while the connect sheet is not presented"
    )
    XCTAssertTrue(normalizedDashboard.contains("OverlayModalEscapeCatcher { dismissAppsPopup()"))
    XCTAssertTrue(
      normalizedDashboard.contains("OverlayModalEscapeCatcher { dismissHomeConnectSheet()"))
    XCTAssertFalse(
      dashboard.contains(".onExitCommand"),
      "Home overlays must not rely on onExitCommand — it requires focus the overlays never receive"
    )
    XCTAssertTrue(
      dismissableSheet.contains(
        "OverlayModalEscapeCatcher {\n              log(\"DISMISSABLE_SHEET: Escape pressed"))

    // While an overlay is up, the content underneath must be hidden from
    // VoiceOver / Full Keyboard Access and the panel marked as modal.
    XCTAssertTrue(dashboard.contains("private var isHomeModalPresented: Bool"))
    XCTAssertTrue(dashboard.contains(".accessibilityHidden(isHomeModalPresented)"))
    XCTAssertTrue(dashboard.contains(".accessibilityAddTraits(.isModal)"))
    XCTAssertTrue(dismissableSheet.contains(".accessibilityHidden(isPresented)"))
    XCTAssertTrue(dismissableSheet.contains(".accessibilityHidden(item != nil)"))
    XCTAssertTrue(dismissableSheet.contains(".accessibilityAddTraits(.isModal)"))

    // The close control must be a real, labeled button — not a tap gesture.
    XCTAssertTrue(apps.contains("var accessibilityLabel: String = \"Close\""))
    XCTAssertTrue(apps.contains(".accessibilityLabel(accessibilityLabel)"))
  }

  private func dashboardSource() throws -> String {
    let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let dashboardURL =
      testsURL
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/DashboardPage.swift")
    return try String(contentsOf: dashboardURL, encoding: .utf8)
  }

  private func captureLogicSource() throws -> String {
    let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let logicURL =
      testsURL
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/CaptureListeningLogic.swift")
    // omi-test-quality: source-inspection -- static contract: DashboardPage must delegate capture status and toggle to the shared CaptureListeningLogic source
    return try String(contentsOf: logicURL, encoding: .utf8)
  }

  private func desktopHomeSource() throws -> String {
    let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let desktopHomeURL =
      testsURL
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/DesktopHomeView.swift")
    return try String(contentsOf: desktopHomeURL, encoding: .utf8)
  }

  private func appsSource() throws -> String {
    try source(named: "AppsPage.swift")
  }

  private func escapeKeyHandlerSource() throws -> String {
    let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let handlerURL =
      testsURL
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/EscapeKeyHandler.swift")
    // omi-test-quality: source-inspection -- static contract: Esc stays window-scoped, never .onExitCommand
    return try String(contentsOf: handlerURL, encoding: .utf8)
  }

  private func source(named fileName: String) throws -> String {
    let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let sourceURL =
      testsURL
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/\(fileName)")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func methodBody(named name: String, in source: String) throws -> String {
    guard let declaration = source.range(of: "private func \(name)(") else {
      throw NSError(domain: "DashboardCaptureStateTests", code: 1)
    }
    guard let openingBrace = source[declaration.upperBound...].firstIndex(of: "{") else {
      throw NSError(domain: "DashboardCaptureStateTests", code: 2)
    }

    var depth = 0
    var cursor = openingBrace
    while cursor < source.endIndex {
      switch source[cursor] {
      case "{": depth += 1
      case "}":
        depth -= 1
        if depth == 0 {
          return String(source[source.index(after: openingBrace)..<cursor])
        }
      default: break
      }
      cursor = source.index(after: cursor)
    }
    throw NSError(domain: "DashboardCaptureStateTests", code: 3)
  }

  private func computedPropertyBody(named name: String, in source: String) throws -> String {
    let pattern = #"private var \#(name): [^{]+\{([\s\S]*?)\n\s+\}"#
    let regex = try NSRegularExpression(pattern: pattern)
    let range = NSRange(source.startIndex..<source.endIndex, in: source)
    let match = try XCTUnwrap(regex.firstMatch(in: source, range: range))
    let bodyRange = try XCTUnwrap(Range(match.range(at: 1), in: source))
    return String(source[bodyRange])
  }

  private func normalizedWhitespace(_ source: String) -> String {
    source.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
  }
}
