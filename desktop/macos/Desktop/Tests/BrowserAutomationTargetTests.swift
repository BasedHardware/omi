import XCTest

@testable import Omi_Computer

final class BrowserAutomationTargetTests: XCTestCase {
  func testDetectsExtensionInConfiguredProfileRoot() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-browser-target-\(UUID().uuidString)")
    defer { try? FileManager.default.removeItem(at: root) }

    let target = BrowserAutomationTarget(
      name: "Test Chromium",
      bundleIdentifier: "test.chromium",
      appPath: "/Applications/Test Chromium.app",
      profileDirectoryRelativePath: "Profiles/TestChromium",
      installURL: nil,
      supportsChromeWebStore: true
    )
    let extensionDirectory = root
      .appendingPathComponent("Profiles/TestChromium/Default/Extensions/\(BrowserAutomationTarget.extensionId)")
    try FileManager.default.createDirectory(
      at: extensionDirectory, withIntermediateDirectories: true)

    XCTAssertTrue(
      BrowserAutomationTargetResolver.isExtensionInstalled(
        in: target,
        homeDirectory: root
      )
    )
  }

  func testDestinationModesSeparateCloudBrowserAndLocalSetup() {
    XCTAssertEqual(MemoryExportDestination.chatgpt.mcpExecuteKind, .browserAutonomous)
    XCTAssertEqual(MemoryExportDestination.claude.mcpExecuteKind, .browserAutonomous)
    XCTAssertEqual(MemoryExportDestination.codex.mcpExecuteKind, .localAutonomous)
    XCTAssertEqual(MemoryExportDestination.claudeCode.mcpExecuteKind, .localAutonomous)
    XCTAssertEqual(MemoryExportDestination.gemini.mcpExecuteKind, .assisted)
  }

  func testChatGPTAtlasIsSupportedBrowserTarget() throws {
    let atlas = try XCTUnwrap(
      BrowserAutomationTargetResolver.knownTargets.first { $0.bundleIdentifier == "com.openai.atlas" }
    )

    XCTAssertEqual(atlas.name, "ChatGPT Atlas")
    XCTAssertEqual(atlas.appPath, "/Applications/ChatGPT Atlas.app")
    XCTAssertEqual(
      atlas.profileDirectoryRelativePath,
      "Library/Application Support/com.openai.atlas/browser-data/host"
    )
    XCTAssertEqual(atlas.extensionInstallURL()?.absoluteString, BrowserAutomationTarget.chromeWebStoreURL)
    XCTAssertEqual(atlas.extensionSetupURL()?.absoluteString, BrowserAutomationTarget.chromeWebStoreURL)
    XCTAssertNotEqual(atlas.extensionSetupURL()?.scheme, "chrome-extension")
  }

  func testCommonChromiumBrowserVariantsAreSupported() throws {
    let expected: [String: (name: String, profileRoot: String)] = [
      "com.google.Chrome.beta": (
        "Google Chrome Beta", "Library/Application Support/Google/Chrome Beta"),
      "com.google.Chrome.canary": (
        "Google Chrome Canary", "Library/Application Support/Google/Chrome Canary"),
      "com.brave.Browser.beta": (
        "Brave Browser Beta", "Library/Application Support/BraveSoftware/Brave-Browser-Beta"),
      "com.brave.Browser.nightly": (
        "Brave Browser Nightly", "Library/Application Support/BraveSoftware/Brave-Browser-Nightly"),
      "com.microsoft.edgemac.Beta": (
        "Microsoft Edge Beta", "Library/Application Support/Microsoft Edge Beta"),
      "com.microsoft.edgemac.Dev": (
        "Microsoft Edge Dev", "Library/Application Support/Microsoft Edge Dev"),
      "com.microsoft.edgemac.Canary": (
        "Microsoft Edge Canary", "Library/Application Support/Microsoft Edge Canary"),
      "com.operasoftware.Opera": (
        "Opera", "Library/Application Support/com.operasoftware.Opera"),
      "com.operasoftware.OperaGX": (
        "Opera GX", "Library/Application Support/com.operasoftware.OperaGX"),
    ]

    for (bundleIdentifier, values) in expected {
      let target = try XCTUnwrap(
        BrowserAutomationTargetResolver.knownTargets.first {
          $0.bundleIdentifier == bundleIdentifier
        },
        "Missing \(bundleIdentifier)"
      )

      XCTAssertEqual(target.name, values.name)
      XCTAssertEqual(target.profileDirectoryRelativePath, values.profileRoot)
      XCTAssertEqual(target.extensionInstallURL()?.absoluteString, BrowserAutomationTarget.chromeWebStoreURL)
    }
  }

  func testOldAutoSelectedBrowserDoesNotOverrideDefaultBrowser() {
    let defaults = UserDefaults.standard
    defaults.set("com.google.Chrome", forKey: "playwrightBrowserBundleIdentifier")
    defaults.removeObject(forKey: "playwrightBrowserBundleIdentifierUserSelected")
    defer {
      defaults.removeObject(forKey: "playwrightBrowserBundleIdentifier")
      defaults.removeObject(forKey: "playwrightBrowserBundleIdentifierUserSelected")
    }

    XCTAssertNil(BrowserAutomationTargetStore.selectedBundleIdentifier)
  }

  func testClaudeCloudSetupUsesCustomizeConnectorModalURL() throws {
    let setup = try XCTUnwrap(MemoryExportDestination.claude.mcpSetup(key: "test-key"))

    XCTAssertEqual(
      setup.openURL?.absoluteString,
      "https://claude.ai/customize/connectors?modal=add-custom-connector"
    )
    XCTAssertEqual(setup.openTitle, "Add Claude Connector")
    XCTAssertTrue(setup.steps.first?.contains("Customize") == true)
  }

  func testGuidedBrowserTaskIncludesExactChatGPTOAuthValues() {
    let task = MemoryExportDestination.chatgpt.guidedBrowserSetupTask(
      key: "test-key",
      browserName: "Brave Browser"
    )

    XCTAssertNotNil(task)
    XCTAssertTrue(task?.body.contains("Use macOS UI automation first") == true)
    XCTAssertTrue(task?.body.contains("FIRST ACTION: call the `fill_cloud_connector_form` tool") == true)
    XCTAssertTrue(task?.body.contains("\"provider\":\"chatgpt\"") == true)
    XCTAssertTrue(task?.body.contains("\"submit\":true") == true)
    XCTAssertTrue(task?.body.contains("do not require the user to install a browser extension") == true)
    XCTAssertTrue(task?.body.contains("Setup values JSON:") == true)
    XCTAssertTrue(task?.body.contains("Automation ladder:") == true)
    XCTAssertTrue(task?.body.contains("execute javascript") == true)
    XCTAssertTrue(task?.body.contains("Do not install browser extensions") == true)
    XCTAssertTrue(task?.body.contains("Brave Browser") == true)
    XCTAssertTrue(task?.body.contains("OAuth Client ID: omi") == true)
    XCTAssertTrue(task?.body.contains("OAuth Client Secret: test-key") == true)
    XCTAssertTrue(task?.body.contains(MemoryExportDestination.mcpServerURL) == true)
  }

  func testGuidedClaudeTaskStartsWithNativeFormFiller() {
    let task = MemoryExportDestination.claude.guidedBrowserSetupTask(
      key: "test-key",
      browserName: "ChatGPT Atlas"
    )

    XCTAssertNotNil(task)
    XCTAssertTrue(task?.body.contains("FIRST ACTION: call the `fill_cloud_connector_form` tool") == true)
    XCTAssertTrue(task?.body.contains("\"provider\":\"claude\"") == true)
    XCTAssertTrue(task?.body.contains("\"oauth_client_secret\":\"test-key\"") == true)
    XCTAssertTrue(task?.body.contains("\"submit\":true") == true)
    XCTAssertTrue(task?.body.contains("Only fall back to bash") == true)
    XCTAssertTrue(task?.body.contains("https://claude.ai/customize/connectors?modal=add-custom-connector") == true)
  }

  func testCloudSetupDoesNotReusePersistedPlaywrightBrowserSelection() throws {
    let repoRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let executor = repoRoot
      .appendingPathComponent("Sources/MemoryExportExecutor.swift")
    let source = try String(contentsOf: executor)

    XCTAssertFalse(
      source.contains("BrowserAutomationTargetStore.selectedBundleIdentifier"),
      "Cloud connector setup should use the macOS default browser, not the persisted Playwright/extension browser preference."
    )
  }

  @MainActor
  func testClaudeNativeSetupWaitsForAccessibilityApprovalInsteadOfAgentFallback() {
    XCTAssertTrue(
      MemoryExportExecutor.cloudFormFillRequiresAccessibilityApproval(
        "Error: Accessibility permission is not available to Omi, so the native connector form filler cannot inspect browser fields."
      )
    )
    XCTAssertFalse(
      MemoryExportExecutor.cloudFormFillRequiresAccessibilityApproval(
        "Error: Could not find a visible claude custom connector form."
      )
    )
    XCTAssertTrue(
      MemoryExportExecutor.cloudFormFillRequiresScreenRecordingApproval(
        "Error: Screen Recording permission is not available to Omi, so the native connector form filler cannot OCR the hidden Claude Connect button."
      )
    )
    XCTAssertFalse(
      MemoryExportExecutor.cloudFormFillRequiresScreenRecordingApproval(
        "Error: Claude connector is added, but the Connect button is not exposed to Accessibility."
      )
    )
  }

  func testClaudeConnectorPageStateClassification() {
    XCTAssertEqual(
      CloudConnectorFormAutomation.classifyClaudeConnectorPageText(
        "AXText claude.ai/customize/connectors?modal=add-custom-connector Add custom connector Remote MCP server URL"
      ),
      .addCustomConnectorModal
    )

    XCTAssertEqual(
      CloudConnectorFormAutomation.classifyClaudeConnectorPageText(
        "AXText claude.ai/customize/connectors Omi CUSTOM You are not connected to Omi yet. Connect"
      ),
      .connectorDetailNotConnected
    )

    XCTAssertEqual(
      CloudConnectorFormAutomation.classifyClaudeConnectorPageText(
        "AXText claude.ai/customize/connectors Omi CUSTOM You are connected to Omi"
      ),
      .connectorDetailConnected
    )

    XCTAssertEqual(
      CloudConnectorFormAutomation.classifyClaudeConnectorPageText(
        "AXText https://example.com/connectors Add custom connector"
      ),
      .other
    )

    XCTAssertEqual(
      CloudConnectorFormAutomation.classifyClaudeConnectorPageText(
        "AXText claude.ai/customize/connectors?modal=add-custom-connector"
      ),
      .other
    )

    XCTAssertEqual(
      CloudConnectorFormAutomation.classifyClaudeConnectorPageText(
        "AXText claude.ai/customize/connectors Add custom connector"
      ),
      .other
    )

    XCTAssertEqual(
      CloudConnectorFormAutomation.classifyClaudeConnectorPageText(
        "AXText claude.ai/customize/connectors Slack You are not connected to Omi yet. Connect"
      ),
      .other
    )
  }

  func testClaudeConnectorStateMachineRefusesUnexpectedStates() {
    XCTAssertEqual(
      CloudConnectorFormAutomation.claudeConnectorAction(
        for: .addCustomConnectorModal,
        submit: true
      ),
      .fillAddModal
    )
    XCTAssertEqual(
      CloudConnectorFormAutomation.claudeConnectorAction(
        for: .connectorDetailNotConnected,
        submit: true
      ),
      .pressConnect
    )
    XCTAssertEqual(
      CloudConnectorFormAutomation.claudeConnectorAction(
        for: .connectorDetailNotConnected,
        submit: false
      ),
      .refuse
    )
    XCTAssertEqual(
      CloudConnectorFormAutomation.claudeConnectorAction(
        for: .connectorDetailConnected,
        submit: true
      ),
      .alreadyConnected
    )
    XCTAssertEqual(
      CloudConnectorFormAutomation.claudeConnectorAction(
        for: .other,
        submit: true
      ),
      .refuse
    )
  }

  func testClaudeConnectOCRCandidateRequiresExactUniqueRightPaneConnect() {
    let imageSize = CGSize(width: 1600, height: 1000)
    let windowFrame = CGRect(x: 100, y: 100, width: 1600, height: 1000)
    let candidate = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Connect",
      confidence: 0.92,
      imageRect: CGRect(x: 970, y: 710, width: 120, height: 46)
    )

    XCTAssertEqual(
      CloudConnectorFormAutomation.findClaudeConnectOCRCandidate(
        [candidate],
        imageSize: imageSize,
        windowFrame: windowFrame
      ),
      candidate
    )
  }

  func testClaudeConnectOCRCandidateRejectsUnsafeMatches() {
    let imageSize = CGSize(width: 1600, height: 1000)
    let windowFrame = CGRect(x: 100, y: 100, width: 1600, height: 1000)
    let good = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Connect",
      confidence: 0.92,
      imageRect: CGRect(x: 970, y: 710, width: 120, height: 46)
    )
    let sidebar = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Connect",
      confidence: 0.92,
      imageRect: CGRect(x: 360, y: 190, width: 120, height: 46)
    )
    let toolbar = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Connect",
      confidence: 0.92,
      imageRect: CGRect(x: 970, y: 24, width: 120, height: 38)
    )
    let lowConfidence = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Connect",
      confidence: 0.4,
      imageRect: CGRect(x: 970, y: 710, width: 120, height: 46)
    )
    let substring = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Connected",
      confidence: 0.92,
      imageRect: CGRect(x: 970, y: 710, width: 120, height: 46)
    )

    XCTAssertNil(
      CloudConnectorFormAutomation.findClaudeConnectOCRCandidate(
        [sidebar],
        imageSize: imageSize,
        windowFrame: windowFrame
      )
    )
    XCTAssertNil(
      CloudConnectorFormAutomation.findClaudeConnectOCRCandidate(
        [toolbar],
        imageSize: imageSize,
        windowFrame: windowFrame
      )
    )
    XCTAssertNil(
      CloudConnectorFormAutomation.findClaudeConnectOCRCandidate(
        [lowConfidence],
        imageSize: imageSize,
        windowFrame: windowFrame
      )
    )
    XCTAssertNil(
      CloudConnectorFormAutomation.findClaudeConnectOCRCandidate(
        [substring],
        imageSize: imageSize,
        windowFrame: windowFrame
      )
    )
    XCTAssertNil(
      CloudConnectorFormAutomation.findClaudeConnectOCRCandidate(
        [good, good],
        imageSize: imageSize,
        windowFrame: windowFrame
      )
    )
  }
}
