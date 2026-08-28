import XCTest

@testable import Omi_Computer

/// The gate is the whole cost-and-annoyance contract: the card may only appear where a
/// message could actually be sent, into a box the user has not started writing in.
final class MessageComposeGateTests: XCTestCase {
  private func context(
    app: String = "Mail",
    title: String = "Re: Dinner",
    role: String = "AXTextArea",
    label: String = "Message body",
    value: String = "",
    secure: Bool = false,
    pageURL: String = ""
  ) -> MessageComposeContext {
    MessageComposeContext(
      appName: app, windowTitle: title, focusedRole: role,
      focusedLabel: label, focusedValue: value, isSecure: secure, pageURL: pageURL)
  }

  // MARK: Surface

  func testNativeMessagingAppsAreSurfaces() {
    for (app, name) in [
      ("Mail", "Mail"), ("Messages", "Messages"), ("WhatsApp", "WhatsApp"),
      ("Telegram", "Telegram"), ("Slack", "Slack"), ("Discord", "Discord"),
      ("Signal", "Signal"), ("Microsoft Outlook", "Outlook"),
    ] {
      XCTAssertEqual(
        MessageComposeGate.surface(appName: app, windowTitle: "anything"),
        .nativeApp(name), app)
    }
  }

  func testBrowserOnAMessagingSiteIsAWebSurface() {
    XCTAssertEqual(
      MessageComposeGate.surface(appName: "Google Chrome", windowTitle: "Inbox (3) - Gmail"),
      .webApp("Gmail"))
    XCTAssertEqual(
      MessageComposeGate.surface(appName: "Safari", windowTitle: "WhatsApp"),
      .webApp("WhatsApp"))
    XCTAssertEqual(
      MessageComposeGate.surface(appName: "Arc", windowTitle: "Telegram Web"),
      .webApp("Telegram"))
  }

  func testWebSurfaceIsRecognizedByURLWhenTheTitleIsTheChatName() {
    // Telegram Web renames the page to the open conversation; the URL still says
    // where the user is. Measured live in Safari on 2026-08-28.
    XCTAssertEqual(
      MessageComposeGate.surface(
        appName: "Safari", windowTitle: "David Zhang",
        pageURL: "https://web.telegram.org/a/#693180290"),
      .webApp("Telegram"))
    XCTAssertEqual(
      MessageComposeGate.surface(
        appName: "Google Chrome", windowTitle: "Inbox",
        pageURL: "https://mail.google.com/mail/u/0/#inbox"),
      .webApp("Gmail"))
  }

  func testOrdinaryURLIsNotASurface() {
    XCTAssertNil(
      MessageComposeGate.surface(
        appName: "Safari", windowTitle: "Front Page",
        pageURL: "https://news.ycombinator.com/"))
    // A messaging host must match the whole host, not a lookalike suffix.
    XCTAssertNil(
      MessageComposeGate.surface(
        appName: "Safari", windowTitle: "Front Page",
        pageURL: "https://evilweb.telegram.org/a/"))
  }

  func testBrowserOnAnOrdinarySiteIsNotASurface() {
    XCTAssertNil(
      MessageComposeGate.surface(appName: "Google Chrome", windowTitle: "Hacker News"))
  }

  func testOrdinaryAppsAreNotSurfaces() {
    XCTAssertNil(MessageComposeGate.surface(appName: "Xcode", windowTitle: "Package.swift"))
    XCTAssertNil(MessageComposeGate.surface(appName: "Notes", windowTitle: "Groceries"))
  }

  // MARK: Decisions

  func testEmptyComposeBoxInAMessagingAppIsEligible() {
    XCTAssertEqual(MessageComposeGate.decide(context()), .eligible)
  }

  func testSingleLineFieldCountsToo() {
    // Mail's "To:" line is an AXTextField, and focus there is still compose intent.
    XCTAssertEqual(
      MessageComposeGate.decide(context(role: "AXTextField", label: "To:")), .eligible)
  }

  func testNonMessagingAppIsRefused() {
    XCTAssertEqual(
      MessageComposeGate.decide(context(app: "Xcode")), .notMessaging)
  }

  func testFocusOutsideATextInputIsRefused() {
    XCTAssertEqual(
      MessageComposeGate.decide(context(role: "AXButton", label: "Send")), .noComposeFocus)
  }

  func testComposeAlreadyWrittenInIsLeftAlone() {
    XCTAssertEqual(
      MessageComposeGate.decide(context(value: "Hey, about tomorrow")), .composeNotEmpty)
  }

  func testWhitespaceStillCountsAsEmpty() {
    XCTAssertEqual(MessageComposeGate.decide(context(value: "  \n")), .eligible)
  }

  func testSearchFieldsAreNeverComposeBoxes() {
    XCTAssertEqual(
      MessageComposeGate.decide(context(role: "AXTextField", label: "Search conversations")),
      .searchField)
    XCTAssertEqual(
      MessageComposeGate.decide(context(role: "AXTextField", label: "Address and search bar")),
      .searchField)
  }

  func testSecureFieldsAreRefused() {
    XCTAssertEqual(
      MessageComposeGate.decide(context(role: "AXSecureTextField", label: "Password")),
      .secureField)
  }

  func testFingerprintIsTheAppAndWindow() {
    let snapshot = { (title: String) in
      MessageComposeSnapshot(
        context: self.context(title: title), surface: .nativeApp("Mail"),
        windowFrame: nil, windowID: nil)
    }
    XCTAssertEqual(snapshot("Re: Dinner").fingerprint, snapshot("Re: Dinner").fingerprint)
    XCTAssertNotEqual(snapshot("Re: Dinner").fingerprint, snapshot("Re: Rent").fingerprint)
  }
}

/// A Mail compose window is To, Cc, Subject — exactly form-shaped — so the messaging
/// surface check is what keeps two cards from racing for the same window.
final class MessageDraftFormAssistBoundaryTests: XCTestCase {
  func testMessagingWindowsBelongToMessageDraft() {
    XCTAssertNotNil(MessageComposeGate.surface(appName: "Mail", windowTitle: "New Message"))
    XCTAssertNotNil(
      MessageComposeGate.surface(appName: "Google Chrome", windowTitle: "Compose - Gmail"))
  }

  func testJobApplicationWindowsStayWithFormAssist() {
    XCTAssertNil(
      MessageComposeGate.surface(
        appName: "Google Chrome", windowTitle: "Software Engineer - Apply - Lever"))
  }
}

final class MessageDraftPolicyTests: XCTestCase {
  func testDraftIsTrimmedAndKept() {
    let draft = MessageDraftPolicy.accepted(subject: " Lunch \n", body: "  See you at noon.  ")
    XCTAssertEqual(draft, MessageDraft(subject: "Lunch", body: "See you at noon."))
  }

  func testChatDraftHasNoSubject() {
    XCTAssertEqual(
      MessageDraftPolicy.accepted(subject: "", body: "On my way."),
      MessageDraft(subject: nil, body: "On my way."))
    XCTAssertEqual(
      MessageDraftPolicy.accepted(subject: nil, body: "On my way.")?.subject, nil)
  }

  func testEmptyBodyIsRefused() {
    XCTAssertNil(MessageDraftPolicy.accepted(subject: "Hi", body: "   \n"))
  }

  func testRunawayDraftIsRefused() {
    let body = String(repeating: "a", count: MessageDraftAssistant.maxDraftLength + 1)
    XCTAssertNil(MessageDraftPolicy.accepted(subject: nil, body: body))
  }
}

final class MessageDraftPromptBuilderTests: XCTestCase {
  private var snapshot: MessageComposeSnapshot {
    MessageComposeSnapshot(
      context: MessageComposeContext(
        appName: "Mail", windowTitle: "Re: Contract", focusedRole: "AXTextArea",
        focusedLabel: "Message body", focusedValue: "", isSecure: false, pageURL: ""),
      surface: .nativeApp("Mail"), windowFrame: nil, windowID: nil)
  }

  func testInstructionAndDestinationReachTheModel() {
    let prompt = MessageDraftPromptBuilder.prompt(
      snapshot: snapshot, userContext: "tell them Friday works",
      refining: nil, memories: ["Works at Datasaur"], hasImage: true)
    XCTAssertTrue(prompt.contains("tell them Friday works"))
    XCTAssertTrue(prompt.contains("App: Mail"))
    XCTAssertTrue(prompt.contains("Re: Contract"))
    XCTAssertTrue(prompt.contains("Works at Datasaur"))
    XCTAssertTrue(prompt.contains("screenshot"))
  }

  func testUserIdentityReachesTheModel() {
    let prompt = MessageDraftPromptBuilder.prompt(
      snapshot: snapshot, userContext: "", refining: nil, memories: [], hasImage: false,
      userName: "Yash Katipally", userEmail: "yash@example.com")
    XCTAssertTrue(prompt.contains("WHO THE USER IS"))
    XCTAssertTrue(prompt.contains("Yash Katipally"))
    XCTAssertTrue(prompt.contains("yash@example.com"))
  }

  func testAnonymousUserGetsNoIdentitySection() {
    let prompt = MessageDraftPromptBuilder.prompt(
      snapshot: snapshot, userContext: "", refining: nil, memories: [], hasImage: false)
    XCTAssertFalse(prompt.contains("WHO THE USER IS"))
  }

  func testNoInstructionAsksForTheWaitingReply() {
    let prompt = MessageDraftPromptBuilder.prompt(
      snapshot: snapshot, userContext: "  ", refining: nil, memories: [], hasImage: false)
    XCTAssertTrue(prompt.contains("draft the reply the conversation on screen is waiting for"))
    XCTAssertFalse(prompt.contains("WHAT OMI KNOWS"))
  }

  func testRefiningCarriesThePreviousDraft() {
    let prompt = MessageDraftPromptBuilder.prompt(
      snapshot: snapshot, userContext: "shorter",
      refining: MessageDraft(subject: "Lunch", body: "Long draft text."),
      memories: [], hasImage: false)
    XCTAssertTrue(prompt.contains("THE DRAFT TO REVISE"))
    XCTAssertTrue(prompt.contains("Subject: Lunch"))
    XCTAssertTrue(prompt.contains("Long draft text."))
    XCTAssertTrue(prompt.contains("shorter"))
  }
}

final class MessageDraftCardMetricsTests: XCTestCase {
  func testPromptCardIsCompact() {
    let size = MessageDraftCardMetrics.size(state: .prompt, maxHeight: 500)
    XCTAssertEqual(size.width, MessageDraftCardMetrics.width)
    XCTAssertEqual(
      size.height,
      MessageDraftCardMetrics.headerHeight + MessageDraftCardMetrics.inputRowHeight
        + MessageDraftCardMetrics.verticalPadding)
  }

  func testDraftGrowsWithItsBodyAndSubject() {
    let short = MessageDraftCardMetrics.size(
      state: .draft(MessageDraft(subject: nil, body: "Sure.")), maxHeight: 500)
    let long = MessageDraftCardMetrics.size(
      state: .draft(MessageDraft(subject: nil, body: String(repeating: "word ", count: 120))),
      maxHeight: 500)
    let withSubject = MessageDraftCardMetrics.size(
      state: .draft(MessageDraft(subject: "Lunch", body: "Sure.")), maxHeight: 500)
    XCTAssertGreaterThan(long.height, short.height)
    XCTAssertEqual(
      withSubject.height, short.height + MessageDraftCardMetrics.subjectRowHeight)
  }

  func testDraftNeverOutgrowsTheCap() {
    let essay = String(repeating: "word ", count: 2_000)
    let size = MessageDraftCardMetrics.size(
      state: .draft(MessageDraft(subject: "S", body: essay)), maxHeight: 300)
    XCTAssertLessThanOrEqual(size.height, 300)
  }
}
