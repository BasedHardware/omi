import XCTest

@testable import Omi_Computer
@testable import VoiceTurnDomain

/// Hermetic projection tests: reducer state / terminal reason → user-facing string.
/// No sleeps, no UI harness.
final class VoiceTurnUIProjectionCopyTests: XCTestCase {
  func testStatusBannerShowsActionableFailureHint() {
    var projection = VoiceTurnUIProjection.idle
    projection.transcript = VoiceTurnUICopy.transcribingProgress
    projection.hint = "Couldn't get a voice reply — try again"
    XCTAssertEqual(
      VoiceTurnUICopy.statusBannerText(for: projection),
      "Couldn't get a voice reply — try again")
  }

  func testStatusBannerHidesTranscribingProgress() {
    var projection = VoiceTurnUIProjection.idle
    projection.transcript = VoiceTurnUICopy.transcribingProgress
    XCTAssertEqual(VoiceTurnUICopy.statusBannerText(for: projection), "")
  }

  func testStatusBannerIgnoresOrdinaryTranscriptText() {
    var projection = VoiceTurnUIProjection.idle
    projection.transcript = "hello there"
    XCTAssertEqual(VoiceTurnUICopy.statusBannerText(for: projection), "")
  }

  func testTerminalHintMappingByTypedReason() {
    XCTAssertEqual(
      VoiceTurnUICopy.terminalHint(for: .journalFailed),
      "Couldn't save that reply — try again")
    XCTAssertEqual(
      VoiceTurnUICopy.terminalHint(for: .providerFailed),
      "Couldn't get a voice reply — try again")
    XCTAssertEqual(
      VoiceTurnUICopy.terminalHint(for: .providerNoResponse),
      "Couldn't get a voice reply — try again")
    XCTAssertEqual(
      VoiceTurnUICopy.terminalHint(for: .deferredCommitTimeout),
      "Couldn't get a voice reply — try again")
    XCTAssertEqual(
      VoiceTurnUICopy.terminalHint(for: .bargeInReplacementTimeout),
      "Previous reply was interrupted — try again")
    XCTAssertEqual(
      VoiceTurnUICopy.terminalHint(for: .toolTimeout),
      "A tool took too long — try again")
    XCTAssertNil(VoiceTurnUICopy.terminalHint(for: .interruptedByBargeIn))
    XCTAssertNil(VoiceTurnUICopy.terminalHint(for: .hubWarmTimeout))
    XCTAssertNil(VoiceTurnUICopy.terminalHint(for: .success))
  }

  func testTerminateAppliesSplitFailureCopy() {
    let reducer = VoiceTurnReducer()
    let turnID = VoiceTurnID()
    var model = reducer.reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reducer.reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: nil))).model
    model = reducer.reduce(model, .finalize(turnID: turnID)).model

    let journal = reducer.reduce(
      model,
      .finish(turnID: turnID, reason: .journalFailed))
    XCTAssertEqual(
      journal.model.turn?.projection.hint,
      "Couldn't save that reply — try again")

    let provider = reducer.reduce(
      model,
      .finish(turnID: turnID, reason: .providerFailed))
    XCTAssertEqual(
      provider.model.turn?.projection.hint,
      "Couldn't get a voice reply — try again")

    let tool = reducer.reduce(
      model,
      .finish(turnID: turnID, reason: .toolTimeout))
    XCTAssertEqual(
      tool.model.turn?.projection.hint,
      "A tool took too long — try again")

    let bargeTimeout = reducer.reduce(
      model,
      .finish(turnID: turnID, reason: .bargeInReplacementTimeout))
    XCTAssertEqual(
      bargeTimeout.model.turn?.projection.hint,
      "Previous reply was interrupted — try again")
  }

  func testBargeInStartKeepsReplacementTurnTextFree() {
    let reducer = VoiceTurnReducer()
    let oldID = VoiceTurnID()
    let newID = VoiceTurnID()
    let model = reducer.reduce(.idle, .start(turnID: oldID, ownerID: nil, intent: .hold)).model
    let replaced = reducer.reduce(
      model,
      .start(turnID: newID, ownerID: nil, intent: .hold))

    XCTAssertEqual(replaced.model.turn?.id, newID)
    XCTAssertEqual(replaced.model.turn?.projection.hint, "")
    XCTAssertFalse(replaced.model.turn?.deadlines.contains(.hintVisibility) == true)
    XCTAssertEqual(replaced.model.lastTerminal?.reason, .interruptedByBargeIn)
  }

  func testAgentFailureSanitizesTransportGutsAndMapsSetupNeeded() {
    XCTAssertEqual(
      AgentFailureTranscriptFormatter.userFacingFailure(
        "URLSessionTask failed with error: The request timed out. (-1001) https://example.com/v1"),
      AgentFailureTranscriptFormatter.genericSpawnFailure)

    XCTAssertEqual(
      AgentFailureTranscriptFormatter.userFacingFailure(
        "openclaw adapter not found",
        directedProvider: .openclaw),
      AgentPillsManager.DirectedProvider.openclaw.setupNeededStatus)

    XCTAssertEqual(
      AgentFailureTranscriptFormatter.userFacingFailure(
        "OMI_HERMES_ADAPTER_COMMAND missing",
        directedProvider: .hermes),
      AgentPillsManager.DirectedProvider.hermes.setupNeededStatus)

    XCTAssertEqual(
      AgentFailureTranscriptFormatter.transcriptText(
        for: "URLSessionTask failed with error: timeout https://x"),
      "Failed: \(AgentFailureTranscriptFormatter.genericSpawnFailure)")
  }
}
