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
  func testListeningModeTitlePreservesOakleyMetaName() {
    let appState = AppState()
    appState.isTranscribing = true
    appState.recordingInputDeviceName = "Oakley Meta Vanguard"

    XCTAssertEqual(
      CaptureListeningLogic.listeningModeTitle(appState: appState, raw: "always"),
      "Oakley Meta Vanguard")
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

  func testAppsPageOwnsItsCatalogAndDetailPresentations() throws {
    let appsPageSource = try appsSource()

    XCTAssertFalse(appsPageSource.contains("enum AppsCatalogInitialSection"))
    XCTAssertFalse(appsPageSource.contains("var initialSection:"))
    XCTAssertFalse(appsPageSource.contains("var onSelectApp: ((OmiApp) -> Void)?"))
    XCTAssertFalse(appsPageSource.contains("var onSelectConnector: ((ImportConnector) -> Void)?"))
    XCTAssertFalse(appsPageSource.contains("var onSelectDestination: ((MemoryExportDestination) -> Void)?"))
    XCTAssertTrue(appsPageSource.contains("ImportsSection("))
    XCTAssertTrue(appsPageSource.contains("ExportsSection("))
    XCTAssertTrue(appsPageSource.contains("private func selectApp(_ app: OmiApp)"))
    XCTAssertTrue(appsPageSource.contains("private func selectConnector(_ connector: ImportConnector)"))
    XCTAssertTrue(appsPageSource.contains("private func selectDestination(_ destination: MemoryExportDestination)"))
    XCTAssertTrue(appsPageSource.contains("selectedApp = app"))
    XCTAssertTrue(appsPageSource.contains("selectedConnector = connector"))
    XCTAssertTrue(appsPageSource.contains("selectedExportDestination = destination"))
    XCTAssertTrue(appsPageSource.contains("if appProvider.apps.isEmpty && !appProvider.isLoading"))
    // Responsive layout was extracted into AppsHeaderRow (AppsPageHeaderControls.swift);
    // AppsPage now delegates to it instead of inlining ViewThatFits.
    let headerSource = try source(named: "AppsPageHeaderControls.swift")
    XCTAssertTrue(headerSource.contains("struct AppsHeaderRow"))
    XCTAssertTrue(headerSource.contains("let search: Search"))
    XCTAssertTrue(headerSource.contains("let filters: Filters"))
    XCTAssertFalse(appsPageSource.contains("struct AppsCatalogContent: View"))
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
