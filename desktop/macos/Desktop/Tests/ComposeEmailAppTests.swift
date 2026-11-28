import XCTest

@testable import Omi_Computer

/// The email draft opens in whatever app handles `mailto:` links, so results
/// must name that app rather than assume Mail.
@MainActor
final class ComposeEmailAppTests: ComposeProposalTestCase {
  private let mail = ComposeEmailApp(name: "Mail", bundleID: "com.apple.mail", isBrowser: false)
  private let outlook = ComposeEmailApp(name: "Microsoft Outlook", bundleID: "com.microsoft.Outlook", isBrowser: false)
  private let chrome = ComposeEmailApp(name: "Google Chrome", bundleID: "com.google.Chrome", isBrowser: true)

  private func result(_ outcome: ComposeProposalOutcome, _ app: ComposeEmailApp?) throws -> [String: Any] {
    try decode(ChatToolExecutor.composeOutcomeJSON(outcome, proposal: emailProposal(), emailApp: app))
  }

  func testAMailAppHandoffNamesThatApp() throws {
    for app in [mail, outlook] {
      let payload = try result(.handedOff, app)

      XCTAssertEqual(payload["status"] as? String, "handed_to_email_app")
      XCTAssertEqual(payload["app"] as? String, app.name)
      XCTAssertEqual(payload["app_is_browser"] as? Bool, false)
      XCTAssertTrue(
        (payload["message"] as? String)?.contains("the default email app (\(app.name))") == true, app.name)
    }
    let outlookMessage = try result(.handedOff, outlook)["message"] as? String
    XCTAssertFalse(outlookMessage?.contains("open in Mail") == true, "never assume Mail")
  }

  func testABrowserHandlerSaysWebMailAndThatOmiCannotSee() throws {
    let payload = try result(.handedOff, chrome)
    let message = try XCTUnwrap(payload["message"] as? String)

    XCTAssertEqual(payload["app"] as? String, "Google Chrome")
    XCTAssertEqual(payload["app_is_browser"] as? Bool, true)
    XCTAssertTrue(message.contains("Google Chrome"))
    XCTAssertTrue(message.contains("web mail site"))
    XCTAssertTrue(message.contains("can't see whether it was sent"))
    XCTAssertFalse(message.contains("Mail for"), "a browser handler is not Mail")
  }

  func testOpenFailedAndUnavailableNameTheApp() throws {
    XCTAssertTrue((try result(.open, chrome)["message"] as? String)?.contains("Google Chrome") == true)
    XCTAssertTrue((try result(.failed(code: 3), outlook)["error"] as? String)?.hasPrefix("Microsoft Outlook") == true)
    XCTAssertTrue((try result(.unavailable, outlook)["error"] as? String)?.contains("Microsoft Outlook") == true)
  }

  func testAnUnknownHandlerIsCalledTheDefaultEmailApp() throws {
    let payload = try result(.handedOff, nil)

    XCTAssertNil(payload["app"])
    XCTAssertTrue((payload["message"] as? String)?.contains("the default email app") == true)
    XCTAssertFalse((payload["message"] as? String)?.contains("Mail for") == true)
  }

  func testMessagesResultsNameMessages() throws {
    let message = ComposeProposal(channel: .message, recipients: ["+15550100100"], subject: nil, body: "Hi")
    let payload = try decode(ChatToolExecutor.composeOutcomeJSON(.handedOff, proposal: message, emailApp: chrome))

    XCTAssertEqual(payload["app"] as? String, "Messages")
    XCTAssertNil(payload["app_is_browser"])
  }

  func testAMessagesHandoffSaysThePersonSendsAndOmiCannotSee() throws {
    let message = ComposeProposal(channel: .message, recipients: ["+15550100100"], subject: nil, body: "Hi")
    let payload = try decode(ChatToolExecutor.composeOutcomeJSON(.handedOff, proposal: message))
    let text = try XCTUnwrap(payload["message"] as? String)

    XCTAssertEqual(payload["status"] as? String, "handed_to_messages")
    XCTAssertTrue(text.contains("press Send in Messages"))
    XCTAssertTrue(text.contains("cannot see whether they send or discard it"))
    XCTAssertFalse(text.contains("sheet"), "current macOS hands off to Messages; no sheet is claimed")
  }

  func testADuplicateDraftPointsAtTheAppAndForbidsResending() throws {
    let payload = try result(.duplicateDraft, chrome)
    let error = try XCTUnwrap(payload["error"] as? String)

    XCTAssertEqual(payload["reason"] as? String, "draft_already_open")
    XCTAssertEqual(payload["status"] as? String, "not_opened")
    XCTAssertTrue(error.contains("press Send in Google Chrome"))
    XCTAssertTrue(error.contains("do not use send_message or create_desktop_dispatch"))
  }

  func testHandlerClassification() {
    XCTAssertFalse(
      ComposeEmailApp(name: "Mail", bundleID: "com.apple.mail", webLinkHandlerBundleID: "com.apple.Safari").isBrowser)
    XCTAssertTrue(
      ComposeEmailApp(name: "Google Chrome", bundleID: "com.google.Chrome", webLinkHandlerBundleID: nil).isBrowser)
    XCTAssertTrue(
      ComposeEmailApp(name: "Arc", bundleID: "company.thebrowser.Browser", webLinkHandlerBundleID: "com.apple.Safari")
        .isBrowser)
    XCTAssertTrue(
      ComposeEmailApp(name: "Orion", bundleID: "com.kagi.kagimacOS", webLinkHandlerBundleID: "com.kagi.kagimacOS")
        .isBrowser, "the app that opens web links is a browser")
    XCTAssertFalse(
      ComposeEmailApp(
        name: "Microsoft Outlook", bundleID: "com.microsoft.Outlook", webLinkHandlerBundleID: "com.google.Chrome"
      )
      .isBrowser)
  }

  func testTheExecutorNamesTheResolvedHandler() async throws {
    let surface = FakeComposeSurface()
    surface.immediateEvent = .shared
    let call = ToolCall(
      name: "propose_email", arguments: ["to": ["sam@example.com"], "subject": "Deck", "text": "Here is the deck."],
      thoughtSignature: nil)
    let chrome = chrome

    let result = await ChatToolExecutor.executeComposeProposal(
      call, userText: "email sam@example.com the deck", runID: "run-1", expectedOwnerID: nil,
      coordinator: makeCoordinator(surface, sleep: neverElapses), grounding: makeGrounding(), transcript: [],
      emailApp: { chrome })

    let payload = try decode(result)
    XCTAssertEqual(payload["status"] as? String, "handed_to_email_app")
    XCTAssertEqual(payload["app"] as? String, "Google Chrome")
  }
}
