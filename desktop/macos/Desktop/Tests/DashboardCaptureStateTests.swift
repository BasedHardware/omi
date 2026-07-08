import XCTest

final class DashboardCaptureStateTests: XCTestCase {
    func testDashboardCaptureStatusUsesLiveMonitoringState() throws {
        let source = try dashboardSource()

        XCTAssertTrue(
            source.contains("private var isCaptureLive: Bool"),
            "DashboardPage should centralize live capture state so the header reflects the running monitor"
        )
        XCTAssertTrue(
            source.contains("if isCaptureLive {\n            return .active\n        }"),
            "Capture status should light up when monitoring is live, even if persisted intent is stale"
        )
        XCTAssertFalse(
            source.contains("if screenAnalysisEnabled && isCaptureMonitoring {\n            return .active\n        }"),
            "Capture status must not require persisted intent to match the live monitor"
        )
    }

    func testDashboardCaptureToggleDerivesFromLiveState() throws {
        let source = try dashboardSource()

        XCTAssertTrue(
            source.contains("syncCaptureState()\n        let enabled = !isCaptureLive"),
            "Capture toggles should reconcile the live monitor before deciding whether the click starts or stops capture"
        )
        XCTAssertFalse(
            source.contains("let enabled = !screenAnalysisEnabled"),
            "Capture toggles should not derive from stale persisted intent"
        )
    }

    func testListeningPillShowsAndTogglesCaptureMode() throws {
        let source = try dashboardSource()

        XCTAssertTrue(source.contains("@AppStorage(\"systemAudioCaptureMode\")"))
        XCTAssertTrue(source.contains("private var listeningModeTitle: String"))
        XCTAssertTrue(source.contains("return appState.isAwaitingMeeting ? \"Meetings only\" : \"In meeting\""))
        XCTAssertTrue(source.contains("HomeListeningStatusButton("))
        XCTAssertTrue(source.contains("modeAction: toggleListeningMode"))
        XCTAssertTrue(source.contains("AssistantSettings.shared.systemAudioCaptureMode = nextMode"))
        XCTAssertTrue(source.contains("Image(systemName: isMeetingsOnly ? \"person.2.fill\" : \"person.fill\")"))
        XCTAssertTrue(source.contains("private var modeIconColor: Color"))
        XCTAssertTrue(source.contains(".frame(height: 34)"))
        XCTAssertFalse(source.contains("Image(systemName: isMeetingsOnly ? \"person.2.fill\" : \"infinity\")"))
        XCTAssertFalse(source.contains("Circle()\n                    .fill(status.indicator)"))
        XCTAssertFalse(source.contains("OmiColors.purplePrimary"))
    }

    func testRedesignedHomeUsesResponsiveStageSizing() throws {
        let source = try dashboardSource()

        XCTAssertTrue(source.contains("private static let homeStageMaxWidth: CGFloat = 1360"))
        XCTAssertTrue(source.contains("private static let homeAskBarMinWidth: CGFloat = 560"))
        XCTAssertTrue(source.contains("private static let homeStagePanelMaxWidth: CGFloat = 1280"))
        XCTAssertTrue(source.contains("private func homeStageSideInset(for stageWidth: CGFloat) -> CGFloat"))
        XCTAssertTrue(source.contains("private func homeAskBarWidth(for stageWidth: CGFloat) -> CGFloat"))
        XCTAssertTrue(source.contains("(text as NSString).size(withAttributes: attributes).width"))
        XCTAssertTrue(source.contains("private func homeHubStage(askBarWidth: CGFloat, stageHeight: CGFloat) -> some View"))
        XCTAssertTrue(source.contains("private var homeHubWordmark: some View"))
        XCTAssertTrue(source.contains("private struct HomeStatRibbon: View"))
        XCTAssertTrue(source.contains(".frame(height: 76)"))
        XCTAssertFalse(source.contains(".frame(width: 304)"))
        XCTAssertFalse(source.contains(".frame(maxWidth: Self.homeAskBarMaxWidth)"))
        XCTAssertFalse(source.contains(".frame(maxWidth: Self.homeStagePanelMaxWidth)"))
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
        XCTAssertFalse(importMethod.contains("desktopAutomationOpenImportRequested"))
        XCTAssertFalse(exportMethod.contains("desktopAutomationOpenExportRequested"))
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
        XCTAssertTrue(normalizedSource.contains("onSelectConnector: { connector in openImportConnectorFromAppsPopup(connector) }"))
        XCTAssertTrue(normalizedSource.contains("onSelectDestination: { destination in openExportDestinationFromAppsPopup(destination) }"))
        XCTAssertTrue(source.contains(".id(appsPopupPresentationID)"))
        XCTAssertTrue(normalizedSource.contains("onDismiss: { dismissAppsPopup()"))
        XCTAssertTrue(source.contains(".frame(width: popupSize.width, height: popupSize.height)"))
        XCTAssertTrue(source.contains(".clipShape(RoundedRectangle(cornerRadius: Self.appsPopupCornerRadius, style: .continuous))"))
        XCTAssertTrue(normalizedSource.contains(".onTapGesture { dismissAppsPopup()"))
        XCTAssertTrue(
            normalizedSource.contains("OverlayModalEscapeCatcher { dismissAppsPopup()"))
        XCTAssertTrue(source.contains("HomeAIChoiceButton(title: \"More\", systemImage: \"plus\") {\n                openAppsPopup(initialSection: .imports)"))
        XCTAssertTrue(source.contains("HomeAIChoiceButton(title: \"More\", systemImage: \"plus\") {\n                openAppsPopup(initialSection: .exports)"))
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
        XCTAssertTrue(source.contains("homeConnectSheetOverlay(\n                    contentWidth: proxy.size.width"))
        XCTAssertTrue(source.contains("let sheetSize = homeConnectSheetSize(panelWidth: panelWidth, panelHeight: panelHeight)"))
        XCTAssertTrue(source.contains(".position(x: contentWidth / 2, y: panelTop + panelHeight / 2)"))
        XCTAssertTrue(normalizedSource.contains(".onTapGesture { dismissHomeConnectSheet()"))
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

    func testHomeStatusRefreshUsesSharedActivationThrottle() throws {
        let source = try dashboardSource()
        let normalizedSource = normalizedWhitespace(source)
        let method = try methodBody(named: "refreshHomeStatusData", in: source)

        XCTAssertTrue(source.contains("@State private var lastHomeStatusRefreshAt = Date.distantPast"))
        XCTAssertTrue(normalizedSource.contains("syncCaptureState() reportHomeAutomationMode() Task { await refreshHomeStatusData(force: true) }"))
        XCTAssertTrue(
            normalizedSource.contains(
                "viewModel.refreshGoals() appState.checkAllPermissions() syncCaptureState() Task { await refreshHomeStatusData(force: false) }"
            )
        )
        XCTAssertTrue(method.contains("PollingConfig.shouldAllowActivationRefresh"))
        XCTAssertTrue(method.contains("lastRefresh: lastHomeStatusRefreshAt"))
        XCTAssertTrue(method.contains("lastHomeStatusRefreshAt = now"))
        XCTAssertTrue(method.contains("async let importConnectorStatuses: Void = importConnectorStatusStore.refresh()"))
        XCTAssertTrue(method.contains("async let screenshots: Void = loadScreenshotCount()"))
        XCTAssertTrue(method.contains("async let knowledgeCounts: Void = loadKnowledgeCounts()"))
        XCTAssertTrue(method.contains("async let exportStatuses: Void = loadMemoryExportStatuses()"))
        XCTAssertFalse(source.contains("memoryExportStatusActiveRefreshThrottle"))
        XCTAssertFalse(source.contains("lastMemoryExportStatusRefreshAt"))
        XCTAssertFalse(source.contains("loadMemoryExportStatuses(force:"))
    }

    func testMemoryExportStatusesRefreshInsideHomeStatusGate() throws {
        let source = try dashboardSource()
        let method = try methodBody(named: "loadMemoryExportStatuses", in: source)

        XCTAssertTrue(method.contains("let statuses = await MemoryExportService.shared.allStatuses()"))
        XCTAssertTrue(method.contains("memoryExportStatuses = statuses"))
        XCTAssertFalse(method.contains("PollingConfig.shouldAllowActivationRefresh"))
        XCTAssertFalse(method.contains("lastHomeStatusRefreshAt"))
        XCTAssertFalse(method.contains("memoryExportStatusActiveRefreshThrottle"))
    }

    func testOmiDeviceHistorySkipsNetworkAfterStickyFlag() throws {
        let source = try dashboardSource()
        let method = try methodBody(named: "loadKnowledgeCounts", in: source)
        let helper = try methodBody(named: "loadOmiDeviceHistory", in: source)

        XCTAssertTrue(method.contains("let shouldLoadDeviceHistory = await MainActor.run { !accountHasOmiDeviceConversations }"))
        XCTAssertTrue(method.contains("async let deviceHistory = shouldLoadDeviceHistory ? loadOmiDeviceHistory() : nil"))
        XCTAssertTrue(helper.contains("APIClient.shared.hasOmiDeviceConversations()"))
        XCTAssertTrue(method.contains("UserDefaults.standard.set(true, forKey: Self.omiDeviceHistoryDefaultsKey)"))
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
        XCTAssertTrue(source.contains("case .imports:\n                                ImportsSection(statusStore: connectorStatusStore)"))
        XCTAssertTrue(source.contains("case .exports:\n                                ExportsSection(statuses: exportStatuses)"))
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
        XCTAssertTrue(source.contains("ViewThatFits(in: .horizontal)"))
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
        let normalizedDashboard = normalizedWhitespace(dashboard)

        // Esc must dismiss the topmost overlay. Custom ZStack overlays are not
        // NSWindow sheets, so Esc comes from the shared catcher's window-scoped
        // key monitor — onExitCommand never fires (the overlays are never
        // focused) and hidden cancel-shortcut buttons get culled from dispatch.
        XCTAssertTrue(apps.contains("struct OverlayModalEscapeCatcher: NSViewRepresentable"))
        XCTAssertTrue(apps.contains("NSEvent.addLocalMonitorForEvents(matching: .keyDown)"))
        XCTAssertTrue(apps.contains("event.window === window"))
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
        XCTAssertTrue(apps.contains("OverlayModalEscapeCatcher {\n                            log(\"DISMISSABLE_SHEET: Escape pressed"))

        // While an overlay is up, the content underneath must be hidden from
        // VoiceOver / Full Keyboard Access and the panel marked as modal.
        XCTAssertTrue(dashboard.contains("private var isHomeModalPresented: Bool"))
        XCTAssertTrue(dashboard.contains(".accessibilityHidden(isHomeModalPresented)"))
        XCTAssertTrue(dashboard.contains(".accessibilityAddTraits(.isModal)"))
        XCTAssertTrue(apps.contains(".accessibilityHidden(isPresented)"))
        XCTAssertTrue(apps.contains(".accessibilityHidden(item != nil)"))
        XCTAssertTrue(apps.contains(".accessibilityAddTraits(.isModal)"))

        // The close control must be a real, labeled button — not a tap gesture.
        XCTAssertTrue(apps.contains("var accessibilityLabel: String = \"Close\""))
        XCTAssertTrue(apps.contains(".accessibilityLabel(accessibilityLabel)"))
    }

    private func dashboardSource() throws -> String {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let dashboardURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/MainWindow/Pages/DashboardPage.swift")
        return try String(contentsOf: dashboardURL, encoding: .utf8)
    }

    private func appsSource() throws -> String {
        try source(named: "AppsPage.swift")
    }

    private func source(named fileName: String) throws -> String {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sourceURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/MainWindow/Pages/\(fileName)")
        return try String(contentsOf: sourceURL, encoding: .utf8)
    }

    private func methodBody(named name: String, in source: String) throws -> String {
        let pattern = #"private func \#(name)\([^\)]*\)[^{]*\{([\s\S]*?)\n    \}"#
        let regex = try NSRegularExpression(pattern: pattern)
        let range = NSRange(source.startIndex..<source.endIndex, in: source)
        let match = try XCTUnwrap(regex.firstMatch(in: source, range: range))
        let bodyRange = try XCTUnwrap(Range(match.range(at: 1), in: source))
        return String(source[bodyRange])
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
