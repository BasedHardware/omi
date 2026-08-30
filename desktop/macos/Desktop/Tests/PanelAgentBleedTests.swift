import XCTest

@testable import Omi_Computer

/// A background run pulls every later request toward reporting on it. Measured live:
/// with a note on screen, "make that shorter and more casual" routed to
/// list_agent_sessions and the reply spoke about "that bio" a stale agent had been
/// spawned for. A prompt rule did not stop it, so the tool result does.
@MainActor
final class PanelAgentBleedTests: XCTestCase {
  /// PanelSession is process-wide state. Draining on the way IN as well as out makes
  /// these order-independent: a suite that leaves a record behind must not be able to
  /// fail a later one.
  override func setUp() async throws {
    try await super.setUp()
    await MainActor.run {
      _ = PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
    }
  }

  override func tearDown() async throws {
    await MainActor.run {
      _ = PanelSession.dismiss()
      _ = PanelSession.takeChatCards()
    }
    try await super.tearDown()
  }

  private func presentNote() {
    PanelSession.present(
      title: "Thank you note",
      subtitle: "Copy it",
      fields: [
        CloudConnectorCopyField(
          id: "body", label: "", value: "Dear Priya, thank you for the support.",
          masksValue: false, wraps: true)
      ],
      grain: .app, origin: .requested)
  }

  private typealias Delegate = RealtimeHubController

  /// These results are JSON. Appending prose to one made it unparseable, and
  /// RealtimeProviderToolResultPolicy.finalize replaced the ENTIRE result with "The tool
  /// returned an invalid response" — measured live, 986 raw bytes became 404. The note
  /// has to be a field, and the payload has to still parse.
  func testTheRedirectKeepsTheResultParseableJSON() {
    presentNote()
    let output = Delegate.panelAwareOutput(
      #"{"ok":true,"sessions":[{"id":"run-1","state":"completed"}]}"#,
      forTool: "list_agent_sessions")
    guard
      let parsed = (try? JSONSerialization.jsonObject(with: Data(output.utf8))) as? [String: Any]
    else { return XCTFail("finalize rejects anything it cannot parse") }
    XCTAssertEqual(parsed["ok"] as? Bool, true, "the real status survives")
    let note = parsed["panelOnScreen"] as? String
    XCTAssertEqual(note?.contains("Dear Priya"), true)
    XCTAssertEqual(note?.contains("update_panel"), true)
    XCTAssertEqual(note?.contains("do not report task status"), true)
  }

  /// A non-JSON status result is not going to be parsed downstream either, so prose is
  /// safe there.
  func testANonJSONStatusResultTakesTheNoteAsProse() {
    presentNote()
    let output = Delegate.panelAwareOutput("Run 1 finished.", forTool: "get_agent_run")
    XCTAssertTrue(output.hasPrefix("Run 1 finished."))
    XCTAssertTrue(output.contains("update_panel"))
  }

  /// No panel, nothing to redirect toward — a status question gets a status answer.
  func testStatusIsUntouchedWithNoPanelOnScreen() {
    let json = #"{"ok":true,"sessions":[]}"#
    XCTAssertEqual(Delegate.panelAwareOutput(json, forTool: "list_agent_sessions"), json)
  }

  /// Only the status tools are rewritten. Every other tool result passes through byte
  /// for byte, or a screenshot result would start carrying panel text.
  func testOtherToolResultsPassThroughUnchanged() {
    presentNote()
    XCTAssertEqual(Delegate.panelAwareOutput("Captured.", forTool: "screenshot"), "Captured.")
    XCTAssertEqual(Delegate.panelAwareOutput("Done.", forTool: "get_tasks"), "Done.")
  }

  /// Measured: "write a two paragraph product description for an espresso machine and
  /// put it on my screen" spawned a background agent and put nothing up. Writing at
  /// length reads as background work and the "on my screen" half is lost.
  func testSpawningAnAgentIsRemindedItCannotReachTheScreen() {
    let output = Delegate.panelAwareOutput("Started a background agent.", forTool: "spawn_agent")
    XCTAssertTrue(output.contains("CANNOT put anything on the user's screen"))
    XCTAssertTrue(output.contains("call show_panel in this same turn"))
    XCTAssertTrue(output.hasPrefix("Started a background agent."), "the real result survives")
  }

  /// The reminder rides on a spawn whether or not a panel happens to be up: the point is
  /// what the background run cannot do, not what is currently on screen.
  func testTheSpawnReminderDoesNotDependOnAPanelBeingUp() {
    XCTAssertTrue(
      Delegate.panelAwareOutput("Started.", forTool: "spawn_agent")
        .contains("CANNOT put anything on the user's screen"))
  }

  /// A spawn result is JSON in production, and a note appended as prose made it
  /// unparseable — finalize then replaced the entire result.
  func testTheSpawnReminderKeepsJSONParseable() {
    let output = Delegate.panelAwareOutput(
      #"{"ok":true,"runId":"r-1"}"#, forTool: "spawn_agent")
    guard
      let parsed = (try? JSONSerialization.jsonObject(with: Data(output.utf8))) as? [String: Any]
    else { return XCTFail("finalize rejects anything it cannot parse") }
    XCTAssertEqual(parsed["runId"] as? String, "r-1")
    XCTAssertEqual((parsed["panelReminder"] as? String)?.contains("show_panel"), true)
  }

  /// A masked secret must not reach the model through this path either.
  func testSecretsDoNotLeakThroughTheRedirect() {
    PanelSession.present(
      title: "Connect",
      subtitle: "Copy each",
      fields: [
        CloudConnectorCopyField(id: "url", label: "URL", value: "https://x", masksValue: false),
        CloudConnectorCopyField(id: "key", label: "Key", value: "sk-live-secret", masksValue: true),
      ],
      grain: .app, origin: .requested)
    let output = Delegate.panelAwareOutput(#"{"ok":true}"#, forTool: "list_agent_sessions")
    XCTAssertFalse(output.contains("sk-live-secret"))
    // Read the field rather than the raw string: JSON escapes the slashes in a URL.
    let parsed = (try? JSONSerialization.jsonObject(with: Data(output.utf8))) as? [String: Any]
    XCTAssertEqual((parsed?["panelOnScreen"] as? String)?.contains("https://x"), true)
  }
}

/// A spawn result is compacted down to its `providerResult` before it reaches the model
/// (`RealtimeProviderToolResultPolicy.prepare` — measured, 2144 raw bytes became 842).
/// A note added beside that object is silently thrown away, so it has to go inside it.
@MainActor
final class PanelSpawnNotePlacementTests: XCTestCase {
  func testTheNoteSurvivesTheSpawnCompaction() {
    let raw = #"{"ok":true,"providerResult":{"toolResultEnvelope":{"version":1},"runId":"r-1"},"extra":"dropped"}"#
    let output = RealtimeHubController.panelAwareOutput(raw, forTool: "spawn_agent")
    guard
      let parsed = (try? JSONSerialization.jsonObject(with: Data(output.utf8))) as? [String: Any],
      let providerResult = parsed["providerResult"] as? [String: Any]
    else { return XCTFail("the spawn payload must stay parseable") }
    XCTAssertEqual(
      (providerResult["panelReminder"] as? String)?.contains("show_panel"), true,
      "the note must ride inside providerResult, which is the only part that survives")
    XCTAssertEqual(providerResult["runId"] as? String, "r-1")
  }

  /// A result with no providerResult keeps the note at the top level.
  func testAPlainPayloadKeepsTheNoteAtTheTopLevel() {
    let output = RealtimeHubController.panelAwareOutput(
      #"{"ok":true,"runId":"r-2"}"#, forTool: "spawn_agent")
    let parsed = (try? JSONSerialization.jsonObject(with: Data(output.utf8))) as? [String: Any]
    XCTAssertEqual((parsed?["panelReminder"] as? String)?.contains("show_panel"), true)
  }
}
