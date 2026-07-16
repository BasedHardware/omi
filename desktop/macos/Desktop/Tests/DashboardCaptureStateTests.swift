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

    func testHomeMatchesLockedDayZeroAndPopulatedMocks() throws {
        let source = try dashboardSource()

        XCTAssertTrue(source.contains("private var isDayZeroHome: Bool"))
        XCTAssertTrue(source.contains("homeConversationCount == 0"))
        XCTAssertTrue(source.contains("&& homeTaskCount == 0"))
        XCTAssertTrue(source.contains("&& homeMemoryCount == 0"))
        XCTAssertTrue(source.contains("&& homeScreenshotCount == 0"))
        XCTAssertTrue(source.contains("if !isDayZeroHome {\n                    homeStatRibbon"))
        XCTAssertTrue(source.contains("Turn your conversations and screen activity into answers, memories, and next steps."))
        XCTAssertTrue(source.contains("Ask a question out loud"))
        XCTAssertTrue(source.contains("See your first Memory — press ⌘O and try it now"))
        XCTAssertTrue(source.contains("Set your first goal to focus What Matters Now"))
        XCTAssertTrue(source.contains("let referenceWidth = isDayZeroHome ? Self.homeAskBarMinWidth : CGFloat(620)"))
        XCTAssertTrue(source.contains(".scaledFont(size: 64, weight: .bold)"))
    }

    func testHomeAskBarRefocusesAfterOpeningChatStage() throws {
        let source = try dashboardSource()

        XCTAssertTrue(source.contains("private func openHomeChat(focusInput: Bool = true)"))
        XCTAssertTrue(source.contains("focusHomeAskFieldAfterStageTransition()"))
        XCTAssertTrue(source.contains("await Task.yield()"))
        XCTAssertTrue(source.contains("homeAskFieldFocused = true"))
        XCTAssertTrue(source.contains("openHomeChat(focusInput: false)"))
    }

    func testSecondaryHomePagesReturnHomeOnEscape() throws {
        let source = try desktopHomeSource()

        XCTAssertTrue(source.contains(".onExitCommand {\n          navigateHomeOnEscapeIfNeeded()\n        }"))
        XCTAssertTrue(source.contains("[.conversations, .memories, .tasks, .rewind].contains(item)"))
        XCTAssertTrue(source.contains("selectedIndex = SidebarNavItem.dashboard.rawValue"))
        XCTAssertFalse(source.contains("[.conversations, .chat, .memories, .tasks, .rewind]"))
    }

    func testHomeConnectNavigatesToCanonicalAppsDestination() throws {
        let source = try dashboardSource()
        let openAppsMethod = try methodBody(named: "openCanonicalApps", in: source)

        XCTAssertTrue(source.contains("onConnect: openCanonicalApps"))
        XCTAssertTrue(openAppsMethod.contains("appProvider.clearFilters()"))
        XCTAssertTrue(openAppsMethod.contains("navigate(to: .apps)"))
        XCTAssertFalse(source.contains("case connect\n\n    var automationLabel"))
        XCTAssertFalse(source.contains("private func homeConnectPanel("))
        XCTAssertFalse(source.contains("private func appsPopupOverlay("))
        XCTAssertFalse(source.contains("private func homeConnectSheetOverlay("))
        XCTAssertFalse(source.contains("@State private var selectedImportConnector"))
        XCTAssertFalse(source.contains("@State private var selectedExportDestination"))
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

    private func dashboardSource() throws -> String {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let dashboardURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/MainWindow/Pages/DashboardPage.swift")
        return try String(contentsOf: dashboardURL, encoding: .utf8)
    }

    private func desktopHomeSource() throws -> String {
        let testsURL = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let desktopHomeURL = testsURL
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/MainWindow/DesktopHomeView.swift")
        return try String(contentsOf: desktopHomeURL, encoding: .utf8)
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

}
