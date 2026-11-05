import XCTest

@testable import Omi_Computer

@MainActor final class CloudConnectorFormEndpointPinTests: XCTestCase {
  private let production = CloudConnectorFormAutomation.OmiConnectorEndpoints(
    serverURL: "https://api.omi.me/v1/mcp",
    authorizeURL: "https://api.omi.me/authorize",
    tokenURL: "https://api.omi.me/token")

  /// Runs the tool with a spy in place of the UI steps and reports what the spy saw.
  private func run(
    _ args: [String: Any],
    endpoints: CloudConnectorFormAutomation.OmiConnectorEndpoints? = nil
  ) async -> (result: String, uiRequests: [CloudConnectorFormAutomation.PreparedFill]) {
    var seen: [CloudConnectorFormAutomation.PreparedFill] = []
    let result = await CloudConnectorFormAutomation.fill(
      args,
      expectedOwnerID: nil,
      endpoints: endpoints ?? production,
      uiSteps: { request, _ in
        seen.append(request)
        return "ui-ran"
      })
    return (result, seen)
  }

  private func value(
    _ label: String, in request: CloudConnectorFormAutomation.PreparedFill
  ) -> String? {
    request.values.first(where: { $0.label == label })?.value
  }

  func testNonOmiServerURLIsRefusedBeforeAnyUIStep() async {
    let refused = [
      "https://evil.com/v1/mcp",
      "http://api.omi.me/v1/mcp",
      "https://omi.me.evil.com/v1/mcp",
      "https://api.omi.me.evil.com/v1/mcp",
      "https://evil.com/omi.me",
      "https://evil.com/api.omi.me/v1/mcp",
      "https://api.omi.me/v1/mcp/extra",
      "https://api.omi.me/v1/mcp/",
      "https://api.omi.me/v1/mcp/sse",
      "https://api.omi.me/v1",
      "https://api.omi.me/v1/mcp?next=https://evil.com",
      "https://api.omi.me/v1/mcp#fragment",
      "https://user@api.omi.me/v1/mcp",
      "https://api.omi.me:8443/v1/mcp",
      "https://api.omi.me./v1/mcp",
      "api.omi.me/v1/mcp",
      "ftp://api.omi.me/v1/mcp",
      "not a url",
    ]
    for provider in ["claude", "chatgpt"] {
      for serverURL in refused {
        let outcome = await run(["provider": provider, "server_url": serverURL, "submit": true])
        XCTAssertTrue(
          outcome.result.hasPrefix("Error: server_url_not_omi:"),
          "\(provider) \(serverURL): \(outcome.result)")
        XCTAssertTrue(outcome.result.contains("Nothing was typed."), serverURL)
        XCTAssertEqual(outcome.uiRequests, [], "\(provider) \(serverURL) reached the UI steps")
      }
    }
  }

  func testOmiServerURLIsAcceptedAndThePinnedSpellingIsTyped() async {
    for serverURL in [
      "https://api.omi.me/v1/mcp",
      "  https://api.omi.me/v1/mcp\n",
      "HTTPS://API.OMI.ME/v1/mcp",
      "https://api.omi.me:443/v1/mcp",
    ] {
      let outcome = await run(["provider": "claude", "server_url": serverURL, "submit": true])
      XCTAssertEqual(outcome.result, "ui-ran", serverURL)
      XCTAssertEqual(outcome.uiRequests.count, 1, serverURL)
      if let request = outcome.uiRequests.first {
        XCTAssertEqual(value("Remote MCP server URL", in: request), production.serverURL)
      }
    }
  }

  func testThisBuildsOwnEndpointsAreAccepted() async {
    let current = CloudConnectorFormAutomation.OmiConnectorEndpoints.current
    XCTAssertEqual(current.serverURL, MemoryExportDestination.mcpServerURL)
    XCTAssertEqual(current.authorizeURL, MemoryExportDestination.mcpAuthorizeURL)
    XCTAssertEqual(current.tokenURL, MemoryExportDestination.mcpTokenURL)

    // The same arguments the ChatGPT setup prompt passes.
    let outcome = await run(
      [
        "provider": "chatgpt",
        "name": "Omi Memory",
        "server_url": MemoryExportDestination.mcpServerURL,
        "authentication": "OAuth",
        "token_auth_method": "none",
        "auth_url": MemoryExportDestination.mcpAuthorizeURL,
        "token_url": MemoryExportDestination.mcpTokenURL,
        "submit": true,
      ],
      endpoints: current)
    XCTAssertEqual(outcome.result, "ui-ran")
    XCTAssertEqual(outcome.uiRequests.count, 1)
  }

  func testNonOmiOAuthURLsAreRefusedBeforeAnyUIStep() async {
    let cases: [(key: String, url: String, code: String)] = [
      ("auth_url", "https://evil.com/authorize", "auth_url_not_omi"),
      ("auth_url", "http://api.omi.me/authorize", "auth_url_not_omi"),
      ("auth_url", "https://api.omi.me.evil.com/authorize", "auth_url_not_omi"),
      ("auth_url", "https://api.omi.me/authorize/extra", "auth_url_not_omi"),
      ("auth_url", "https://api.omi.me/token", "auth_url_not_omi"),
      ("token_url", "https://evil.com/token", "token_url_not_omi"),
      ("token_url", "https://evil.com/api.omi.me/token", "token_url_not_omi"),
      ("token_url", "https://api.omi.me/token?x=1", "token_url_not_omi"),
      ("token_url", "https://api.omi.me/authorize", "token_url_not_omi"),
    ]
    for testCase in cases {
      let outcome = await run([
        "provider": "chatgpt",
        "server_url": production.serverURL,
        testCase.key: testCase.url,
        "submit": true,
      ])
      XCTAssertTrue(
        outcome.result.hasPrefix("Error: \(testCase.code):"), "\(testCase.url): \(outcome.result)")
      XCTAssertEqual(outcome.uiRequests, [], "\(testCase.url) reached the UI steps")
    }
  }

  func testOmiOAuthURLsAreAcceptedAndPinned() async {
    let outcome = await run([
      "provider": "chatgpt",
      "server_url": production.serverURL,
      "auth_url": "https://API.omi.me/authorize",
      "token_url": production.tokenURL,
    ])
    XCTAssertEqual(outcome.result, "ui-ran")
    guard let request = outcome.uiRequests.first else { return XCTFail("UI steps did not run") }
    XCTAssertEqual(value("Auth URL", in: request), production.authorizeURL)
    XCTAssertEqual(value("Token URL", in: request), production.tokenURL)
    XCTAssertFalse(request.submit)
  }

  func testAnEndpointThatIsNotHTTPSAcceptsNothing() async {
    let localHTTP = CloudConnectorFormAutomation.OmiConnectorEndpoints(
      serverURL: "http://localhost:8000/v1/mcp",
      authorizeURL: "http://localhost:8000/authorize",
      tokenURL: "http://localhost:8000/token")
    let outcome = await run(
      ["provider": "claude", "server_url": localHTTP.serverURL], endpoints: localHTTP)
    XCTAssertTrue(outcome.result.hasPrefix("Error: server_url_not_omi:"), outcome.result)
    XCTAssertEqual(outcome.uiRequests, [])
  }

  func testEarlierArgumentErrorsAreUnchanged() async {
    let badProvider = await run(["provider": "gemini", "server_url": production.serverURL])
    XCTAssertEqual(badProvider.result, "Error: provider must be 'claude' or 'chatgpt'.")
    XCTAssertEqual(badProvider.uiRequests, [])

    let missingURL = await run(["provider": "claude", "server_url": "  "])
    XCTAssertEqual(missingURL.result, "Error: server_url is required.")
    XCTAssertEqual(missingURL.uiRequests, [])
  }

  func testClaudeRequestIsUnchangedForTheOmiURL() async {
    let outcome = await run([
      "provider": "claude",
      "name": "Omi Memory",
      "server_url": production.serverURL,
      "oauth_client_id": "omi-claude-prod",
      "submit": true,
    ])
    XCTAssertEqual(outcome.result, "ui-ran")
    guard let request = outcome.uiRequests.first else { return XCTFail("UI steps did not run") }
    XCTAssertEqual(request.provider, "claude")
    XCTAssertTrue(request.submit)
    XCTAssertEqual(
      request.values.map(\.label), ["Name", "Remote MCP server URL", "OAuth Client ID"])
    XCTAssertEqual(
      request.values.map(\.value), ["Omi Memory", production.serverURL, "omi-claude-prod"])
  }

  func testChatGPTPageRequiresChatGPTConnectorSettingsURL() {
    let accepted = [
      "AXTextField chatgpt.com/#settings/Connectors Address and search bar",
      "AXTextField https://chatgpt.com/#settings/Connectors/Advanced",
      "AXStaticText chatgpt.com/#settings/Apps",
    ]
    for text in accepted {
      XCTAssertTrue(CloudConnectorFormAutomation.showsChatGPTConnectorSettingsURL(text), text)
    }

    let refused = [
      // Not ChatGPT at all.
      "AXTextField example.com/connectors New connector MCP Server URL",
      "AXTextField claude.ai/customize/connectors?modal=add-custom-connector",
      // Look-alike hosts and paths that only mention chatgpt.com.
      "AXTextField chatgpt.com.evil.com/#settings/Connectors",
      "AXTextField evil.com/chatgpt.com/#settings/Connectors",
      "AXTextField https://evil.com/?u=chatgpt.com/#settings/Connectors",
      "AXTextField notchatgpt.com/#settings/Connectors",
      "AXTextField http://chatgpt.com/#settings/Connectors",
      // ChatGPT, but not its connector settings.
      "AXTextField chatgpt.com/ New chat",
      "AXTextField chatgpt.com/c/123 MCP Server URL",
      "AXTextField chatgpt.com/#settings/General",
      // No URL, only a window title.
      "AXWindow ChatGPT New App MCP Server URL",
    ]
    for text in refused {
      XCTAssertFalse(CloudConnectorFormAutomation.showsChatGPTConnectorSettingsURL(text), text)
    }
  }

  func testChatGPTFormRequiresAServerURLField() {
    XCTAssertTrue(
      CloudConnectorFormAutomation.looksLikeChatGPTConnectorForm(
        "AXGroup New App AXStaticText Name AXTextField MCP Server URL AXButton Create"))
    XCTAssertFalse(
      CloudConnectorFormAutomation.looksLikeChatGPTConnectorForm(
        "AXGroup Settings AXStaticText Connectors AXButton Create app"))
  }

  func testChatGPTSubmitPressesOnlyTheFormsOwnAddOrCreateButton() {
    XCTAssertEqual(
      CloudConnectorFormAutomation.chatGPTSubmitButtonIndex(labels: ["Close", "Cancel", "Create"]),
      2)
    XCTAssertEqual(
      CloudConnectorFormAutomation.chatGPTSubmitButtonIndex(labels: ["Back", " Create app "]), 1)
    XCTAssertEqual(
      CloudConnectorFormAutomation.chatGPTSubmitButtonIndex(labels: ["Cancel", "Add"]), 1)

    // Loose words that only contain add/create/connect/save never count.
    XCTAssertNil(
      CloudConnectorFormAutomation.chatGPTSubmitButtonIndex(
        labels: ["Add files", "Connect Google Drive", "Save memory", "Created by you", "Address"]))
    XCTAssertNil(
      CloudConnectorFormAutomation.chatGPTSubmitButtonIndex(labels: ["Connect", "Save"]))
    // Two candidates means the form's own button is not identified.
    XCTAssertNil(
      CloudConnectorFormAutomation.chatGPTSubmitButtonIndex(labels: ["Create", "Add"]))
    XCTAssertNil(CloudConnectorFormAutomation.chatGPTSubmitButtonIndex(labels: []))
  }
}
