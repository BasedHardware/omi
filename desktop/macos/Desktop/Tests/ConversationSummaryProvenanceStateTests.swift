import Foundation
import XCTest

@testable import Omi_Computer

/// The summary surface must never be silent and must never overclaim.
///
/// Before this policy existed, `ConversationSummarySelection` resolved `.empty`
/// and no view handled it — `ConversationSummaryBody` rendered `OmiMarkdown(text: "")`,
/// so a conversation with no summary showed a title and then nothing at all. And
/// `ServerConversation.localSummary` was read by no UI, so an on-device summary was
/// indistinguishable from a server one.
final class ConversationSummaryProvenanceStateTests: XCTestCase {
  private typealias State = ConversationSummaryProvenanceState

  // MARK: - Attribution

  func testALocalRuntimeWithABodyIsBadgedOnDevice() {
    XCTAssertEqual(
      State.attribution(localSummaryRuntime: "local", hasSummaryBody: true),
      .onDevice
    )
  }

  func testNoProjectionMeansTheServerWroteIt() {
    XCTAssertEqual(
      State.attribution(localSummaryRuntime: nil, hasSummaryBody: true),
      .server
    )
  }

  /// The deterministic minimum is mechanical string handling, not a model. Badging
  /// it as on-device intelligence would attribute work to an engine that never ran.
  func testTheDeterministicMinimumIsNotBadgedAsOnDevice() {
    XCTAssertEqual(
      State.attribution(localSummaryRuntime: "deterministic", hasSummaryBody: true),
      .server
    )
  }

  /// `runtime` is an open string on the wire, so an engine we have not shipped yet
  /// must still read as "a model ran here" rather than being dropped or crashing.
  func testAnUnrecognizedRuntimeIsStillOnDevice() {
    XCTAssertEqual(
      State.attribution(localSummaryRuntime: "some-future-engine", hasSummaryBody: true),
      .onDevice
    )
  }

  func testWhitespaceOnlyRuntimeIsNotAnEngine() {
    XCTAssertEqual(
      State.attribution(localSummaryRuntime: "   ", hasSummaryBody: true),
      .server
    )
  }

  /// Nothing to attribute. A badge over an empty body would say a summary was
  /// produced somewhere, which is the claim the empty state exists to deny.
  func testAnEmptyBodyIsNeverBadged() {
    XCTAssertNil(State.attribution(localSummaryRuntime: "local", hasSummaryBody: false))
    XCTAssertNil(State.attribution(localSummaryRuntime: nil, hasSummaryBody: false))
  }

  /// Badging every server summary would put a row on every conversation in the
  /// product to confirm what users already assume.
  func testOnlyTheOnDeviceClaimIsWorthShowing() {
    XCTAssertTrue(State.Attribution.onDevice.isWorthDisplaying)
    XCTAssertFalse(State.Attribution.server.isWorthDisplaying)
  }

  func testAttributionNamesThePlaceNotTheModel() {
    // `provenance.model_id` is "afm" — an internal id. A reader can act on where
    // it ran; an acronym tells them nothing.
    XCTAssertEqual(State.Attribution.onDevice.label, "Summarized on this Mac")
    XCTAssertEqual(State.Attribution.server.label, "Summarized by Omi")
    XCTAssertFalse(State.Attribution.onDevice.label.lowercased().contains("afm"))
  }

  // MARK: - Empty state

  func testProcessingWithALocalProjectionIsPendingOnDevice() {
    XCTAssertEqual(
      State.empty(deferred: false, localSummaryRuntime: "local", isProcessing: true),
      .pendingOnDevice
    )
  }

  func testProcessingWithoutAProjectionIsPendingServer() {
    XCTAssertEqual(
      State.empty(deferred: false, localSummaryRuntime: nil, isProcessing: true),
      .pendingServer
    )
  }

  /// A deferred conversation has a stored transcript and no summary yet. It is
  /// pending whatever a previous local attempt did, so `deferred` outranks runtime.
  func testDeferredOutranksAPriorLocalAttempt() {
    XCTAssertEqual(
      State.empty(deferred: true, localSummaryRuntime: "deterministic", isProcessing: false),
      .pendingServer
    )
  }

  /// The case this whole file is for: a Mac that could not run a local engine
  /// sends a `deterministic` projection, the server stores it, and the reader
  /// gets an empty body. That must read as a finished outcome, not a pending one.
  func testADeterministicProjectionReadsAsFinishedNotPending() {
    let state = State.empty(deferred: false, localSummaryRuntime: "deterministic", isProcessing: false)
    XCTAssertEqual(state, .localProducedNothing)
    XCTAssertFalse(
      state.message.lowercased().contains("being summarized"),
      "a terminal state must not imply a summary is still coming"
    )
    XCTAssertTrue(
      state.message.lowercased().contains("transcript"),
      "the reader still has a transcript and the message must say so"
    )
  }

  func testALocalRuntimeThatProducedNothingReadsTheSameWay() {
    // `carriesContent` should stop this reaching the server, but if it does the
    // reader's situation is identical: a transcript and no summary.
    XCTAssertEqual(
      State.empty(deferred: false, localSummaryRuntime: "local", isProcessing: false),
      .localProducedNothing
    )
  }

  func testNoLocalPathAndNoSummaryIsUnavailable() {
    XCTAssertEqual(
      State.empty(deferred: false, localSummaryRuntime: nil, isProcessing: false),
      .unavailable
    )
  }

  func testEveryEmptyStateSaysSomething() {
    let states: [State.Empty] = [.pendingOnDevice, .pendingServer, .localProducedNothing, .unavailable]
    for state in states {
      XCTAssertFalse(state.title.isEmpty, "\(state) has no title; the surface would be silent again")
      XCTAssertFalse(state.message.isEmpty, "\(state) has no message")
    }
  }

  /// The failure mode this replaces was a blank region. Any future state that
  /// forgets to explain itself should fail here rather than ship as blank space.
  func testNoEmptyStateBlamesTheUserOrTheirHardware() {
    let states: [State.Empty] = [.pendingOnDevice, .pendingServer, .localProducedNothing, .unavailable]
    let blame = ["unsupported", "too old", "not powerful", "incompatible", "sorry", "failed"]
    for state in states {
      let text = (state.title + " " + state.message).lowercased()
      for word in blame {
        XCTAssertFalse(
          text.contains(word),
          "\(state) says \"\(word)\"; the reader did nothing wrong and cannot act on it"
        )
      }
    }
  }
}
