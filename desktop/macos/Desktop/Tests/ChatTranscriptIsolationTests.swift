import XCTest

@testable import Omi_Computer

/// CHAT-06: floating-bar and main-chat share one ChatProvider by design (turn
/// interruption needs a single streaming pipeline), but their TRANSCRIPTS must
/// not co-mingle. Turns are stamped with a `ChatTurnOwner` at append and every
/// surface (main render, main snapshot, floating snapshot) filters through
/// `ChatTurnOwner.transcriptMessages`.
final class ChatTranscriptIsolationTests: XCTestCase {

  private func msg(_ text: String, sender: ChatSender, owner: ChatTurnOwner?) -> ChatMessage {
    ChatMessage(text: text, sender: sender, turnOwner: owner)
  }

  func testMainSurfaceExcludesFloatingTurns() {
    let mixed = [
      msg("m1", sender: .user, owner: .mainChat),
      msg("f1", sender: .user, owner: .floatingDefault),
      msg("f1r", sender: .ai, owner: .floatingDefault),
      msg("m1r", sender: .ai, owner: .mainChat),
      msg("v1", sender: .user, owner: .floatingVoice),
    ]
    let main = ChatTurnOwner.transcriptMessages(mixed, floatingSurface: false)
    XCTAssertEqual(main.map(\.text), ["m1", "m1r"])
  }

  func testFloatingSurfaceExcludesMainTurns() {
    let mixed = [
      msg("m1", sender: .user, owner: .mainChat),
      msg("f1", sender: .user, owner: .floatingDefault),
      msg("v1", sender: .user, owner: .floatingVoice),
      msg("m2", sender: .user, owner: .mainChat),
    ]
    let floating = ChatTurnOwner.transcriptMessages(mixed, floatingSurface: true)
    XCTAssertEqual(floating.map(\.text), ["f1", "v1"])
  }

  func testNilOwnerIsLegacyHistoryAndBelongsToMain() {
    // Restored/backend-loaded rows carry no owner — they must keep appearing in
    // the main transcript (pre-fix behavior) and never in the floating one.
    let mixed = [
      msg("legacy", sender: .ai, owner: nil),
      msg("f1", sender: .user, owner: .floatingDefault),
    ]
    XCTAssertEqual(ChatTurnOwner.transcriptMessages(mixed, floatingSurface: false).map(\.text), ["legacy"])
    XCTAssertEqual(ChatTurnOwner.transcriptMessages(mixed, floatingSurface: true).map(\.text), ["f1"])
  }

  func testOrderPreservedWithinSurface() {
    let mixed = (0..<10).map { i in
      msg("t\(i)", sender: .user, owner: i % 2 == 0 ? .mainChat : .floatingDefault)
    }
    let main = ChatTurnOwner.transcriptMessages(mixed, floatingSurface: false).map(\.text)
    XCTAssertEqual(main, ["t0", "t2", "t4", "t6", "t8"])
  }

  func testOwnerFloatingClassification() {
    XCTAssertFalse(ChatTurnOwner.mainChat.isFloating)
    XCTAssertTrue(ChatTurnOwner.floatingDefault.isFloating)
    XCTAssertTrue(ChatTurnOwner.floatingVoice.isFloating)
    // taskChat/agentPill are NOT floating-bar surfaces — they must keep
    // rendering with the main transcript if they ever share this provider.
    XCTAssertFalse(ChatTurnOwner.taskChat("t1").isFloating)
    XCTAssertFalse(ChatTurnOwner.agentPill(UUID()).isFloating)
  }

  func testClearingMainRetainsFloatingTurns() {
    // clearChat semantics: wiping the MAIN transcript keeps floating turns
    // (same array, different surface).
    let mixed = [
      msg("m1", sender: .user, owner: .mainChat),
      msg("f1", sender: .user, owner: .floatingDefault),
      msg("legacy", sender: .ai, owner: nil),
    ]
    let retained = ChatTurnOwner.transcriptMessages(mixed, floatingSurface: true)
    XCTAssertEqual(retained.map(\.text), ["f1"])
  }

  func testSendPathsStampTurnOwner() throws {
    // Source invariant: the four live-turn ChatMessage constructions in the
    // send paths carry a turnOwner stamp, and the floating snapshot no longer
    // delegates to the unfiltered main snapshot.
    let root = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let provider = try String(
      contentsOf: root.appendingPathComponent("Sources/Providers/ChatProvider.swift"),
      encoding: .utf8)
    // Wiring invariants (kept identifier-loose: pre-existing context structs
    // also pass turnOwner, so we assert the *filtered surfaces*, and that the
    // live ChatMessage constructions stamp an owner at all).
    XCTAssertGreaterThanOrEqual(
      provider.components(separatedBy: "turnOwner: turnOwner").count - 1, 2,
      "sendMessage must stamp its user and ai messages (follow-ups ride the same path post-#9231)")
    XCTAssertTrue(
      provider.contains("automationChatSnapshot(limit: limit, floatingSurface:"),
      "snapshots must run through the surface-filtered core")
    let chatPage = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Pages/ChatPage.swift"),
      encoding: .utf8)
    XCTAssertTrue(
      chatPage.contains("ChatTurnOwner.transcriptMessages(chatProvider.messages, floatingSurface: false)"),
      "main chat must derive its transcript through the surface filter")
    XCTAssertTrue(
      chatPage.contains("messages: mainTranscript,"),
      "main chat must render the filtered transcript, not the raw shared array")
    let dashboard = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Pages/DashboardPage.swift"),
      encoding: .utf8)
    XCTAssertEqual(
      dashboard.components(
        separatedBy: "messages: ChatTurnOwner.transcriptMessages(chatProvider.messages, floatingSurface: false)"
      ).count - 1, 2,
      "both dashboard home-chat surfaces (legacyHome + homeChatPanel) must render filtered")
    XCTAssertFalse(
      dashboard.contains("messages: chatProvider.messages,"),
      "no dashboard chat surface may render the raw shared array")
    let floating = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarWindow.swift"),
      encoding: .utf8)
    XCTAssertTrue(floating.contains("automationFloatingChatSnapshot(limit:"))
    XCTAssertFalse(
      floating.contains("return provider.automationMainChatSnapshot"),
      "floating snapshot must not delegate to the unfiltered main snapshot")
  }
}
