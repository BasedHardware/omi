import XCTest

@testable import Omi_Computer

/// What the voice session is told about the panel before the user's words arrive.
///
/// Measured live: on a turn where it called no tool, the model said "I've updated that
/// note for you, making it shorter and more casual" with an empty screen and nothing
/// behind the claim. Tool results only teach it about the panel after it acts; this is
/// what it knows before.
@MainActor
final class PanelStateContextTests: XCTestCase {
  override func setUp() async throws {
    await MainActor.run {
      _ = PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
      PanelSession.forgetClosedHistory()
    }
  }

  override func tearDown() async throws {
    await MainActor.run {
      _ = PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
      PanelSession.forgetClosedHistory()
    }
  }

  private func present(_ value: String, masked: Bool = false) {
    PanelSession.present(
      title: "Note", subtitle: "Copy it",
      fields: [CloudConnectorCopyField(id: "body", label: "", value: value, masksValue: masked)],
      grain: .app, origin: .requested)
  }

  /// An empty screen is stated, not omitted. Silence is what let the model believe a
  /// panel it put up three turns ago was still there.
  func testAnEmptyScreenIsStatedExplicitly() {
    let state = RealtimeHubPanelStateContext.state()
    XCTAssertTrue(state.contains("Nothing is on the user's screen"))
    XCTAssertTrue(state.contains("update_panel"))
    // Measured: "is anything on my screen right now" was answered by CALLING
    // reopen_panel, which puts a panel up rather than reporting there is none.
    XCTAssertTrue(state.contains("do not try reopen_panel to find out"))
  }

  func testALivePanelIsReportedWithItsText() {
    present("Thanks for everything!")
    let state = RealtimeHubPanelStateContext.state()
    XCTAssertTrue(state.contains("Thanks for everything!"))
    XCTAssertTrue(state.contains("never say you changed it without calling that tool"))
    // Measured: "what is on the panel right now" was answered by CALLING close_panel,
    // which took the panel away instead of describing it. Reading is not a tool.
    XCTAssertTrue(state.contains("with no tool call"))
    XCTAssertTrue(state.contains("never for looking"))
  }

  /// The same guarantee as every other path out of PanelSession: a masked value is a
  /// secret and must not reach the speech provider.
  func testSecretsAreNotInjected() {
    PanelSession.present(
      title: "Connect", subtitle: "Copy each",
      fields: [
        CloudConnectorCopyField(id: "url", label: "URL", value: "https://x", masksValue: false),
        CloudConnectorCopyField(id: "key", label: "Key", value: "sk-live-secret", masksValue: true),
      ],
      grain: .app, origin: .requested)
    XCTAssertFalse(RealtimeHubPanelStateContext.state().contains("sk-live-secret"))
  }

  // MARK: - Cost

  /// A turn boundary fires constantly. Re-sending an unchanged panel is prompt cost for
  /// no information.
  func testAnUnchangedPanelIsNotResent() {
    present("First.")
    let first = RealtimeHubPanelStateContext.line(lastSent: nil)
    XCTAssertNotNil(first)
    XCTAssertNil(RealtimeHubPanelStateContext.line(lastSent: first))
  }

  func testAChangedPanelIsResent() {
    present("First.")
    let first = RealtimeHubPanelStateContext.line(lastSent: nil)
    PanelSession.revise(
      title: nil, fields: VoicePanel.copyFields(from: [VoicePanelItem(label: "", text: "Second.")]))
    let second = RealtimeHubPanelStateContext.line(lastSent: first)
    XCTAssertEqual(second?.contains("Second."), true)
  }

  /// Closing is a change the model has to hear about, or it keeps offering to edit a
  /// panel that is gone.
  func testClosingThePanelIsAnnounced() {
    present("First.")
    let live = RealtimeHubPanelStateContext.line(lastSent: nil)
    _ = PanelSession.dismiss()
    let closed = RealtimeHubPanelStateContext.line(lastSent: live)
    XCTAssertEqual(closed?.contains("Nothing is on the user's screen"), true)
  }
}

/// A panel with no copyable text yet is still a panel. Reporting "nothing is on screen"
/// for an unanswered offer or a card mid-fill is the same lie this seam exists to stop:
/// the model would offer to put up what the user is already looking at.
@MainActor
final class PanelPresenceTests: XCTestCase {
  override func setUp() async throws {
    await MainActor.run {
      _ = PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
      PanelSession.forgetClosedHistory()
    }
  }

  override func tearDown() async throws {
    await MainActor.run {
      _ = PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
      PanelSession.forgetClosedHistory()
    }
  }

  func testNothingOnScreenIsNone() {
    XCTAssertEqual(PanelSession.presence(), .none)
  }

  func testCopyablePanelReportsItsText() {
    PanelSession.present(
      title: "Note", subtitle: "Copy it",
      fields: [CloudConnectorCopyField(id: "b", label: "", value: "Hello", masksValue: false)],
      grain: .app, origin: .requested)
    XCTAssertEqual(PanelSession.presence(), .copy("Hello"))
  }

  func testAnUnansweredOfferIsAnOfferNotNothing() {
    PanelSession.present(
      title: "Fill this form?", subtitle: "5 fields", fields: [], grain: .context,
      origin: .ambient,
      ask: CopyCardAsk(placeholder: "Add context…", confirmLabel: "Fill it", onConfirm: { _ in }))
    XCTAssertEqual(PanelSession.presence(), .offer(title: "Fill this form?"))
    let state = RealtimeHubPanelStateContext.state()
    XCTAssertTrue(state.contains("waiting for them to accept"))
    XCTAssertFalse(state.contains("Nothing is on the user's screen"))
  }

  func testACardStillFillingInIsWorkingNotNothing() {
    PanelSession.present(
      title: "Safari form", subtitle: "Reading your memories…",
      fields: [
        CloudConnectorCopyField(
          id: "n", label: "Name", value: "", masksValue: false, isPending: true)
      ],
      grain: .context, origin: .requested)
    XCTAssertEqual(PanelSession.presence(), .working(title: "Safari form"))
    let state = RealtimeHubPanelStateContext.state()
    XCTAssertTrue(state.contains("still filling in"))
    XCTAssertTrue(state.contains("Do not describe its contents"))
  }

  func testTheDraftCardIsReportedWithItsText() {
    PanelSession.presentCompose(
      fingerprint: "c1", appDisplayName: "Telegram", targetWindowFrame: nil,
      restore: MessageDraft(subject: nil, body: "See you Monday"), origin: .requested,
      onGenerate: { _, _ in .success(MessageDraft(subject: nil, body: "x")) }, onDecline: {})
    XCTAssertEqual(PanelSession.presence(), .draft("See you Monday"))
    let state = RealtimeHubPanelStateContext.state()
    XCTAssertTrue(state.contains("See you Monday"))
    XCTAssertTrue(state.contains("its own box"))
  }

  func testADraftCardStillWritingSaysSo() {
    PanelSession.presentCompose(
      fingerprint: "c1", appDisplayName: "Telegram", targetWindowFrame: nil, restore: nil,
      origin: .requested,
      onGenerate: { _, _ in .success(MessageDraft(subject: nil, body: "x")) }, onDecline: {})
    XCTAssertEqual(PanelSession.presence(), .draft(nil))
    XCTAssertTrue(RealtimeHubPanelStateContext.state().contains("still writing"))
  }
}
