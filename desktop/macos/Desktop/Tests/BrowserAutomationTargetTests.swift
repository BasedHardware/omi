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
    let extensionDirectory =
      root
      .appendingPathComponent(
        "Profiles/TestChromium/Default/Extensions/\(BrowserAutomationTarget.extensionId)")
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
    // ChatGPT uses the approved directory listing. Claude remains assisted-first.
    XCTAssertEqual(MemoryExportDestination.chatgpt.mcpExecuteKind, .directoryApp)
    XCTAssertEqual(
      MemoryExportDestination.chatgpt.directoryInstallURL?.absoluteString,
      "https://chatgpt.com/plugins/plugin_asdk_app_6a1490df4c588191b9339ae21978c873?q=omi")
    XCTAssertEqual(MemoryExportDestination.claude.mcpExecuteKind, .assisted)
    XCTAssertNil(MemoryExportDestination.chatgpt.assistedOverlayHint)
    XCTAssertNotNil(MemoryExportDestination.claude.assistedOverlayHint)
    XCTAssertNil(MemoryExportDestination.gemini.assistedOverlayHint)
    XCTAssertEqual(MemoryExportDestination.claude.assistedSetupFields(key: "k")?.count, 4)
    // Preserve the developer-mode custom app fields as the advanced fallback.
    XCTAssertEqual(MemoryExportDestination.chatgpt.assistedSetupFields(key: "k")?.count, 8)
    // Prod ChatGPT client is public PKCE — the secret row must stay blank.
    XCTAssertEqual(
      MemoryExportDestination.chatgpt.assistedSetupFields(key: "k")?
        .first(where: { $0.label == "OAuth Client Secret" })?.value, "")
    XCTAssertEqual(
      MemoryExportDestination.chatgpt.assistedSetupFields(key: "k")?
        .first(where: { $0.label == "OAuth Client Secret" })?.masksValue, false)
    // Claude cloud uses a public OAuth client too — the secret row must stay blank.
    XCTAssertEqual(
      MemoryExportDestination.claude.assistedSetupFields(key: "secret-key")?
        .first(where: { $0.label == "OAuth Client ID" })?.value, "omi-claude-prod")
    XCTAssertEqual(
      MemoryExportDestination.claude.assistedSetupFields(key: "secret-key")?
        .first(where: { $0.label == "OAuth Client Secret" })?.value, "")
    XCTAssertEqual(
      MemoryExportDestination.claude.assistedSetupFields(key: "secret-key")?
        .first(where: { $0.label == "OAuth Client Secret" })?.masksValue, false)
    // Stable ids — never label-derived (duplicate labels would crash ForEach).
    let chatgptIDs = MemoryExportDestination.chatgpt.assistedSetupFields(key: "k")?.map(\.id) ?? []
    XCTAssertEqual(Set(chatgptIDs).count, chatgptIDs.count)
    XCTAssertNil(MemoryExportDestination.gemini.assistedSetupFields(key: "k"))
    XCTAssertEqual(MemoryExportDestination.codex.mcpExecuteKind, .localAutonomous)
    XCTAssertEqual(MemoryExportDestination.claudeCode.mcpExecuteKind, .localAutonomous)
    XCTAssertEqual(MemoryExportDestination.gemini.mcpExecuteKind, .assisted)
  }

  func testChatGPTAndCodexShareOnePickerChoice() {
    XCTAssertEqual(ConnectDestinationSheet.group(for: .chatgpt), [.chatgpt, .codex])
    XCTAssertEqual(ConnectDestinationSheet.group(for: .codex), [.chatgpt, .codex])
  }

  func testAgentSkillHandlesNullableHostedProfileAndRemoteTransport() {
    let skill = MemoryExportService.omiAgentSkillText
    XCTAssertTrue(skill.contains(MemoryExportDestination.mcpServerURL))
    XCTAssertTrue(skill.contains("profile: null"))
    XCTAssertTrue(skill.contains("mcp-remote"))
  }

  func testChatGPTAtlasIsSupportedBrowserTarget() throws {
    let atlas = try XCTUnwrap(
      BrowserAutomationTargetResolver.knownTargets.first {
        $0.bundleIdentifier == "com.openai.atlas"
      }
    )

    XCTAssertEqual(atlas.name, "ChatGPT Atlas")
    XCTAssertEqual(atlas.appPath, "/Applications/ChatGPT Atlas.app")
    XCTAssertEqual(
      atlas.profileDirectoryRelativePath,
      "Library/Application Support/com.openai.atlas/browser-data/host"
    )
    XCTAssertEqual(
      atlas.extensionInstallURL()?.absoluteString, BrowserAutomationTarget.chromeWebStoreURL)
    XCTAssertEqual(
      atlas.extensionSetupURL()?.absoluteString, BrowserAutomationTarget.chromeWebStoreURL)
    XCTAssertNotEqual(atlas.extensionSetupURL()?.scheme, "chrome-extension")
  }

  func testCommonChromiumBrowserVariantsAreSupported() throws {
    let expected: [String: (name: String, profileRoot: String)] = [
      "com.google.Chrome.beta": (
        "Google Chrome Beta", "Library/Application Support/Google/Chrome Beta"
      ),
      "com.google.Chrome.canary": (
        "Google Chrome Canary", "Library/Application Support/Google/Chrome Canary"
      ),
      "com.brave.Browser.beta": (
        "Brave Browser Beta", "Library/Application Support/BraveSoftware/Brave-Browser-Beta"
      ),
      "com.brave.Browser.nightly": (
        "Brave Browser Nightly", "Library/Application Support/BraveSoftware/Brave-Browser-Nightly"
      ),
      "com.microsoft.edgemac.Beta": (
        "Microsoft Edge Beta", "Library/Application Support/Microsoft Edge Beta"
      ),
      "com.microsoft.edgemac.Dev": (
        "Microsoft Edge Dev", "Library/Application Support/Microsoft Edge Dev"
      ),
      "com.microsoft.edgemac.Canary": (
        "Microsoft Edge Canary", "Library/Application Support/Microsoft Edge Canary"
      ),
      "com.operasoftware.Opera": (
        "Opera", "Library/Application Support/com.operasoftware.Opera"
      ),
      "com.operasoftware.OperaGX": (
        "Opera GX", "Library/Application Support/com.operasoftware.OperaGX"
      ),
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
      XCTAssertEqual(
        target.extensionInstallURL()?.absoluteString, BrowserAutomationTarget.chromeWebStoreURL)
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

  func testSelectingDifferentBrowserClearsPersistedExtensionToken() {
    let defaults = UserDefaults.standard
    defaults.set("com.google.Chrome", forKey: "playwrightBrowserBundleIdentifier")
    defaults.set(true, forKey: "playwrightBrowserBundleIdentifierUserSelected")
    defaults.set("old-token", forKey: "playwrightExtensionToken")
    defer {
      defaults.removeObject(forKey: "playwrightBrowserBundleIdentifier")
      defaults.removeObject(forKey: "playwrightBrowserBundleIdentifierUserSelected")
      defaults.removeObject(forKey: "playwrightExtensionToken")
    }

    let atlas = BrowserAutomationTarget(
      name: "ChatGPT Atlas",
      bundleIdentifier: "com.openai.atlas",
      appPath: "/Applications/ChatGPT Atlas.app",
      profileDirectoryRelativePath:
        "Library/Application Support/com.openai.atlas/browser-data/host",
      installURL: nil,
      supportsChromeWebStore: true
    )

    BrowserAutomationTargetStore.select(atlas)

    XCTAssertEqual(BrowserAutomationTargetStore.selectedBundleIdentifier, "com.openai.atlas")
    XCTAssertNil(defaults.string(forKey: "playwrightExtensionToken"))
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
    XCTAssertTrue(
      task?.body.contains("FIRST ACTION: call the `fill_cloud_connector_form` tool") == true)
    XCTAssertTrue(task?.body.contains("\"provider\":\"chatgpt\"") == true)
    XCTAssertTrue(task?.body.contains("\"submit\":true") == true)
    XCTAssertTrue(
      task?.body.contains("do not require the user to install a browser extension") == true)
    XCTAssertTrue(task?.body.contains("Setup values JSON:") == true)
    XCTAssertTrue(task?.body.contains("Automation ladder:") == true)
    XCTAssertTrue(task?.body.contains("execute javascript") == true)
    XCTAssertTrue(task?.body.contains("Do not install browser extensions") == true)
    XCTAssertTrue(task?.body.contains("Brave Browser") == true)
    // ChatGPT uses the registered public PKCE client — never the per-user key
    // as a client secret (the token endpoint rejects secrets for public clients).
    XCTAssertTrue(
      task?.body.contains("OAuth Client ID: \(MemoryExportDestination.chatgptOAuthClientID)")
        == true)
    XCTAssertTrue(task?.body.contains("Token auth method: none") == true)
    XCTAssertTrue(
      task?.body.contains("\"oauth_client_id\":\"\(MemoryExportDestination.chatgptOAuthClientID)\"")
        == true)
    XCTAssertTrue(task?.body.contains("\"token_auth_method\":\"none\"") == true)
    XCTAssertFalse(task?.body.contains("\"oauth_client_secret\"") == true)
    XCTAssertFalse(task?.body.contains("OAuth Client Secret: test-key") == true)
    XCTAssertTrue(task?.body.contains(MemoryExportDestination.mcpServerURL) == true)
  }

  func testGuidedClaudeTaskStartsWithNativeFormFiller() {
    let task = MemoryExportDestination.claude.guidedBrowserSetupTask(
      key: "test-key",
      browserName: "ChatGPT Atlas"
    )

    XCTAssertNotNil(task)
    XCTAssertTrue(
      task?.body.contains("FIRST ACTION: call the `fill_cloud_connector_form` tool") == true)
    XCTAssertTrue(task?.body.contains("\"provider\":\"claude\"") == true)
    XCTAssertTrue(task?.body.contains("\"oauth_client_id\":\"omi-claude-prod\"") == true)
    XCTAssertFalse(task?.body.contains("\"oauth_client_secret\"") == true)
    XCTAssertTrue(task?.body.contains("\"submit\":true") == true)
    XCTAssertTrue(task?.body.contains("Only fall back to bash") == true)
    XCTAssertTrue(
      task?.body.contains("https://claude.ai/customize/connectors?modal=add-custom-connector")
        == true)
  }

  func testAgentRuntimeOnlyEnablesPlaywrightWhenBridgeIsConfigured() {
    XCTAssertTrue(
      AgentRuntimeProcess.shouldEnablePlaywrightExtension(
        useExtension: true,
        token: "token",
        targetHasExtension: true
      )
    )
    XCTAssertFalse(
      AgentRuntimeProcess.shouldEnablePlaywrightExtension(
        useExtension: false,
        token: "token",
        targetHasExtension: true
      )
    )
    XCTAssertFalse(
      AgentRuntimeProcess.shouldEnablePlaywrightExtension(
        useExtension: true,
        token: "",
        targetHasExtension: true
      )
    )
    XCTAssertFalse(
      AgentRuntimeProcess.shouldEnablePlaywrightExtension(
        useExtension: true,
        token: "token",
        targetHasExtension: false
      )
    )
  }

  @MainActor
  func testClaudeNativeSetupWaitsForAccessibilityApprovalInsteadOfAgentFallback() {
    // Assisted-first Claude setup needs no Accessibility preflight; the check
    // only applies while a destination maps to .browserAutonomous.
    XCTAssertFalse(MemoryExportExecutor.requiresAccessibilityPreflight(.claude))
    XCTAssertFalse(MemoryExportExecutor.requiresAccessibilityPreflight(.chatgpt))
    XCTAssertFalse(MemoryExportExecutor.requiresAccessibilityPreflight(.codex))

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
    XCTAssertTrue(
      MemoryExportExecutor.cloudFormFillNeedsManualClaudeAdd(
        "Error: The Claude add connector button is not exposed to Accessibility. Refusing blind coordinate or keyboard clicks."
      )
    )
    XCTAssertFalse(
      MemoryExportExecutor.cloudFormFillNeedsManualClaudeAdd(
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
        "AXWindow Customize - Claude AXStaticText claude.ai/customize/connectors?modal=add-custom-connector"
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
        "AXText claude.ai/customize/connectors Omi \(MemoryExportDestination.mcpServerURL) You are connected to Omi"
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

  func testClaudeCloudSetupDoesNotFinishAfterOnlyAddingConnector() {
    let addResult = """
      Native connector form filler result:
      Provider: claude
      Browser/app: ChatGPT Atlas
      Filled: Name, Remote MCP server URL, OAuth Client ID, OAuth Client Secret
      Method: keyboard fallback
      Submitted with button: Add (OCR)
      """

    XCTAssertFalse(MemoryExportExecutor.cloudFormFillSucceeded(addResult))
    XCTAssertTrue(MemoryExportExecutor.cloudFormFillShouldRetry(addResult))

    let connectResult = """
      Native connector form filler result:
      Provider: claude
      Browser/app: ChatGPT Atlas
      Submitted with button: Connect (OCR)
      Connect pressed; waiting for Claude to finish or show OAuth consent.
      """

    XCTAssertTrue(MemoryExportExecutor.cloudFormFillSucceeded(connectResult))
    XCTAssertFalse(MemoryExportExecutor.cloudFormFillShouldRetry(connectResult))
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

  func testClaudeAddOCRCandidateRequiresExactUniqueLowerRightAdd() {
    let imageSize = CGSize(width: 1600, height: 1000)
    let windowFrame = CGRect(x: 100, y: 100, width: 1600, height: 1000)
    let candidate = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Add",
      confidence: 0.92,
      imageRect: CGRect(x: 1260, y: 230, width: 72, height: 42)
    )

    XCTAssertEqual(
      CloudConnectorFormAutomation.findClaudeAddOCRCandidate(
        [candidate],
        imageSize: imageSize,
        windowFrame: windowFrame
      ),
      candidate
    )
  }

  func testClaudeAddOCRCandidateRejectsUnsafeMatches() {
    let imageSize = CGSize(width: 1600, height: 1000)
    let windowFrame = CGRect(x: 100, y: 100, width: 1600, height: 1000)
    let good = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Add",
      confidence: 0.92,
      imageRect: CGRect(x: 1260, y: 230, width: 72, height: 42)
    )
    let cancel = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Cancel",
      confidence: 0.92,
      imageRect: CGRect(x: 1140, y: 230, width: 110, height: 42)
    )
    let sidebar = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Add",
      confidence: 0.92,
      imageRect: CGRect(x: 260, y: 170, width: 72, height: 42)
    )
    let topBar = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Add",
      confidence: 0.92,
      imageRect: CGRect(x: 1260, y: 35, width: 72, height: 42)
    )
    let lowConfidence = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Add",
      confidence: 0.4,
      imageRect: CGRect(x: 1260, y: 230, width: 72, height: 42)
    )
    let substring = CloudConnectorFormAutomation.OCRTextCandidate(
      text: "Added",
      confidence: 0.92,
      imageRect: CGRect(x: 1260, y: 230, width: 90, height: 42)
    )

    XCTAssertNil(
      CloudConnectorFormAutomation.findClaudeAddOCRCandidate(
        [cancel],
        imageSize: imageSize,
        windowFrame: windowFrame
      )
    )
    XCTAssertNil(
      CloudConnectorFormAutomation.findClaudeAddOCRCandidate(
        [sidebar],
        imageSize: imageSize,
        windowFrame: windowFrame
      )
    )
    XCTAssertNil(
      CloudConnectorFormAutomation.findClaudeAddOCRCandidate(
        [topBar],
        imageSize: imageSize,
        windowFrame: windowFrame
      )
    )
    XCTAssertNil(
      CloudConnectorFormAutomation.findClaudeAddOCRCandidate(
        [lowConfidence],
        imageSize: imageSize,
        windowFrame: windowFrame
      )
    )
    XCTAssertNil(
      CloudConnectorFormAutomation.findClaudeAddOCRCandidate(
        [substring],
        imageSize: imageSize,
        windowFrame: windowFrame
      )
    )
    XCTAssertNil(
      CloudConnectorFormAutomation.findClaudeAddOCRCandidate(
        [good, good],
        imageSize: imageSize,
        windowFrame: windowFrame
      )
    )
  }

  func testClaudeConnectGuidanceAnchorStaysInRightPane() {
    let windowFrame = CGRect(x: 80, y: 60, width: 1600, height: 1000)
    let anchor = CloudConnectorFormAutomation.claudeConnectGuidanceAnchor(in: windowFrame)

    XCTAssertGreaterThan(anchor.x, windowFrame.midX)
    XCTAssertLessThan(anchor.x, windowFrame.maxX)
    XCTAssertGreaterThan(anchor.y, windowFrame.minY + windowFrame.height * 0.2)
    XCTAssertLessThan(anchor.y, windowFrame.minY + windowFrame.height * 0.5)
  }

  func testClaudeAddGuidanceAnchorStaysNearBottomRightModalAction() {
    let windowFrame = CGRect(x: 80, y: 60, width: 1600, height: 1000)
    let anchor = CloudConnectorFormAutomation.claudeAddGuidanceAnchor(in: windowFrame)

    XCTAssertGreaterThan(anchor.x, windowFrame.minX + windowFrame.width * 0.55)
    XCTAssertLessThan(anchor.x, windowFrame.minX + windowFrame.width * 0.75)
    XCTAssertGreaterThan(anchor.y, windowFrame.minY + windowFrame.height * 0.16)
    XCTAssertLessThan(anchor.y, windowFrame.minY + windowFrame.height * 0.26)
  }

  @MainActor
  func testClaudeConnectGuidanceUsesExplicitTargetCandidateWhenAvailable() throws {
    let windowFrame = CGRect(x: 80, y: 60, width: 1600, height: 1000)
    let explicitFrame = CGRect(x: 1_100, y: 620, width: 120, height: 44)
    let candidates = CloudConnectorFormAutomation.claudeConnectGuidanceCandidates(
      windowFrame: windowFrame,
      explicitTargetFrames: [explicitFrame]
    )

    let result = try XCTUnwrap(
      CloudConnectorGuidanceOverlay.placementResult(
        windowFrame: windowFrame,
        candidates: candidates
      ))

    XCTAssertTrue(candidates[0].evidence.contains { $0.source == .accessibility })
    XCTAssertTrue(candidates[0].allowedUses.contains(.performClick))
    assertGuidancePlacement(result, pointsAt: explicitFrame, doesNotCover: explicitFrame)
  }

  @MainActor
  func testClaudeAddGuidanceUsesExplicitTargetCandidateWhenAvailable() throws {
    let windowFrame = CGRect(x: 80, y: 60, width: 1600, height: 1000)
    let explicitFrame = CGRect(x: 1_250, y: 855, width: 72, height: 42)
    let candidates = CloudConnectorFormAutomation.claudeAddGuidanceCandidates(
      windowFrame: windowFrame,
      explicitTargetFrames: [explicitFrame]
    )

    let result = try XCTUnwrap(
      CloudConnectorGuidanceOverlay.placementResult(
        windowFrame: windowFrame,
        candidates: candidates
      ))

    XCTAssertTrue(candidates[0].evidence.contains { $0.source == .accessibility })
    XCTAssertTrue(candidates[0].allowedUses.contains(.performClick))
    assertGuidancePlacement(result, pointsAt: explicitFrame, doesNotCover: explicitFrame)
  }

  @MainActor
  func testClaudeGuidancePrefersExplicitCandidateOverHigherConfidenceHeuristic() throws {
    let windowFrame = CGRect(x: 80, y: 60, width: 1600, height: 1000)
    let screen = SpatialOverlayScreen(id: "test", frame: windowFrame, visibleFrame: windowFrame)
    let explicitFrame = CGRect(x: 1_250, y: 230, width: 72, height: 42)
    let explicit = SpatialOverlayAnchorCandidate(
      id: "explicit-add",
      targetRect: explicitFrame,
      screen: screen,
      evidence: [
        SpatialOverlayTargetEvidence(source: .accessibility, confidence: 0.90, label: "Add")
      ],
      confidence: 0.90,
      allowedUses: [.displayGuidance, .performClick]
    )
    let heuristic = SpatialOverlayAnchorCandidate(
      id: "heuristic-add",
      targetRect: CGRect(
        x: explicitFrame.midX + 120, y: explicitFrame.midY + 80, width: 2, height: 2),
      screen: screen,
      evidence: [
        SpatialOverlayTargetEvidence(source: .layoutHeuristic, confidence: 0.99, label: "estimate")
      ],
      confidence: 0.99,
      allowedUses: [.displayGuidance]
    )

    let result = try XCTUnwrap(
      CloudConnectorGuidanceOverlay.placementResult(
        windowFrame: windowFrame,
        candidates: [heuristic, explicit]
      ))

    assertGuidancePlacement(result, pointsAt: explicitFrame, doesNotCover: explicitFrame)
  }

  @MainActor
  func testClaudeGuidanceIgnoresCandidatesNotAllowedForDisplay() throws {
    let windowFrame = CGRect(x: 80, y: 60, width: 1600, height: 1000)
    let screen = SpatialOverlayScreen(id: "test", frame: windowFrame, visibleFrame: windowFrame)
    let clickOnly = SpatialOverlayAnchorCandidate(
      id: "click-only",
      targetRect: CGRect(x: 1_250, y: 230, width: 72, height: 42),
      screen: screen,
      evidence: [
        SpatialOverlayTargetEvidence(source: .accessibility, confidence: 0.99, label: "Add")
      ],
      confidence: 0.99,
      allowedUses: [.performClick]
    )

    XCTAssertNil(
      CloudConnectorGuidanceOverlay.placementResult(
        windowFrame: windowFrame,
        candidates: [clickOnly]
      ))
  }

  @MainActor
  func testClaudeGuidanceHeuristicsAreFallbackOnly() throws {
    let windowFrame = CGRect(x: 80, y: 60, width: 1600, height: 1000)
    let connectCandidates = CloudConnectorFormAutomation.claudeConnectGuidanceCandidates(
      windowFrame: windowFrame,
      explicitTargetFrames: []
    )
    let addCandidates = CloudConnectorFormAutomation.claudeAddGuidanceCandidates(
      windowFrame: windowFrame,
      explicitTargetFrames: []
    )

    let connectResult = try XCTUnwrap(
      CloudConnectorGuidanceOverlay.placementResult(
        windowFrame: windowFrame,
        candidates: connectCandidates
      ))
    let addResult = try XCTUnwrap(
      CloudConnectorGuidanceOverlay.placementResult(
        windowFrame: windowFrame,
        candidates: addCandidates
      ))

    XCTAssertTrue(connectCandidates[0].evidence.contains { $0.source == .layoutHeuristic })
    XCTAssertTrue(addCandidates[0].evidence.contains { $0.source == .layoutHeuristic })
    XCTAssertFalse(connectCandidates[0].allowedUses.contains(.performClick))
    XCTAssertFalse(addCandidates[0].allowedUses.contains(.performClick))
    XCTAssertTrue(connectCandidates[0].id.contains("heuristic"))
    XCTAssertTrue(addCandidates[0].id.contains("heuristic"))
    XCTAssertEqual(connectResult.globalArrowTip.x, connectResult.targetPoint.x, accuracy: 3)
    XCTAssertEqual(addResult.globalArrowTip.x, addResult.targetPoint.x, accuracy: 3)
  }

  func testSpatialOverlayPlacementArrowTracksTargetAfterClamping() throws {
    let overlaySize = CGSize(width: 330, height: 118)
    let target = CGPoint(x: 1_240, y: 810)
    let screen = SpatialOverlayScreen(
      id: "test",
      frame: CGRect(x: 0, y: 0, width: 1_342, height: 1_000),
      visibleFrame: CGRect(x: 0, y: 0, width: 1_342, height: 1_000)
    )
    let candidate = SpatialOverlayAnchorCandidate(
      id: "target",
      targetRect: CGRect(x: target.x - 1, y: target.y - 1, width: 2, height: 2),
      screen: screen,
      confidence: 0.95,
      allowedUses: [.displayGuidance]
    )
    let result = try SpatialOverlayPlacementSolver.place(
      target: candidate,
      spec: SpatialOverlayPlacementSpec(
        overlaySize: overlaySize,
        preferredEdges: [.above, .below],
        canCoverTarget: true
      )
    ).get()

    XCTAssertEqual(result.globalArrowTip.x, target.x, accuracy: 3)
    XCTAssertEqual(result.globalArrowTip.y, target.y, accuracy: 3)
  }

  private func assertGuidancePlacement(
    _ result: SpatialOverlayPlacementResult,
    pointsAt target: CGRect,
    doesNotCover coveredTarget: CGRect,
    file: StaticString = #filePath,
    line: UInt = #line
  ) {
    let expandedTarget = target.insetBy(dx: -3, dy: -3)
    XCTAssertTrue(
      expandedTarget.contains(result.targetPoint),
      "Expected target point \(result.targetPoint) to land on \(target)",
      file: file,
      line: line
    )
    XCTAssertTrue(
      expandedTarget.contains(result.globalArrowTip),
      "Expected arrow tip \(result.globalArrowTip) to land on \(target)",
      file: file,
      line: line
    )
    XCTAssertFalse(
      result.panelFrame.intersects(coveredTarget),
      "Expected panel \(result.panelFrame) not to cover \(coveredTarget)",
      file: file,
      line: line
    )
  }

  func testSpatialOverlayPlacementFailsWhenArrowCannotReachTargetAfterClamp() {
    let screen = SpatialOverlayScreen(
      id: "test",
      frame: CGRect(x: 100, y: 0, width: 600, height: 500),
      visibleFrame: CGRect(x: 100, y: 0, width: 600, height: 500)
    )
    let candidate = SpatialOverlayAnchorCandidate(
      id: "left",
      targetRect: CGRect(x: 20, y: 140, width: 2, height: 2),
      screen: screen,
      confidence: 0.95,
      allowedUses: [.displayGuidance]
    )

    let result = SpatialOverlayPlacementSolver.place(
      target: candidate,
      spec: SpatialOverlayPlacementSpec(
        overlaySize: CGSize(width: 330, height: 118),
        preferredEdges: [.above]
      )
    )

    XCTAssertEqual(result.failure, .arrowCannotReachTargetAfterClamping)
  }
}

extension Result {
  fileprivate var failure: Failure? {
    if case .failure(let failure) = self {
      return failure
    }
    return nil
  }
}
