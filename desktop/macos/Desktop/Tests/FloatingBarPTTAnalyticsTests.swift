import XCTest

@testable import Omi_Computer

private final class Box<T>: @unchecked Sendable {
  var value: T
  init(_ value: T) { self.value = value }
}

/// Contract tests for the `floating_bar_ptt_ended` terminal classification
/// (`turn_kind`): dictation vs question vs unknown. The capture seam lives on
/// `AnalyticsManager`'s main-actor boundary so tests observe the real event
/// name and payload without initializing PostHog.
@MainActor
final class FloatingBarPTTAnalyticsTests: XCTestCase {
  private let capturedBox = Box<[(String, [String: Any])]>([])

  private func startCapturing() {
    let box = capturedBox
    box.value = []
    AnalyticsManager.shared.setFloatingBarPTTTelemetryCaptureForTests { event, properties in
      box.value.append((event, properties))
    }
    addTeardownBlock {
      await MainActor.run {
        AnalyticsManager.shared.setFloatingBarPTTTelemetryCaptureForTests(nil)
      }
    }
  }

  // MARK: - turn_kind closed set

  func testEndedPayloadCarriesEveryTurnKindRawValue() {
    startCapturing()

    for (kind, raw) in [
      (PTTAttemptLifecycleRecorder.TurnKind.dictation, "dictation"),
      (.question, "question"),
      (.unknown, "unknown"),
    ] {
      AnalyticsManager.shared.floatingBarPTTEnded(
        mode: "hold", committed: false, transcriptLength: nil, turnKind: kind)
      XCTAssertEqual(capturedBox.value.last?.1["turn_kind"] as? String, raw)
    }
    let kinds = capturedBox.value.map { $0.1["turn_kind"] as? String }
    XCTAssertEqual(kinds, ["dictation", "question", "unknown"])
    for captured in capturedBox.value {
      XCTAssertEqual(captured.0, "floating_bar_ptt_ended")
      XCTAssertEqual(captured.1["mode"] as? String, "hold")
      XCTAssertEqual(captured.1["had_transcript"] as? Bool, false)
    }
  }

  func testTurnKindDefaultsToUnknownWhenSiteCannotKnowIntent() {
    startCapturing()

    AnalyticsManager.shared.floatingBarPTTEnded(mode: "hold", committed: false, transcriptLength: nil)

    XCTAssertEqual(capturedBox.value.single?.1["turn_kind"] as? String, "unknown")
  }

  func testExistingWirePropertiesAreUnchanged() {
    startCapturing()

    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: "toggle", committed: true, transcriptLength: 42, turnKind: .question)

    let props = capturedBox.value.single?.1
    XCTAssertEqual(props?["mode"] as? String, "toggle")
    XCTAssertEqual(props?["had_transcript"] as? Bool, true)
    XCTAssertEqual(props?["transcript_length"] as? Int, 42)
  }

  // MARK: - optional bounded extras

  func testAudioSecondsCollapseIntoClosedBuckets() {
    startCapturing()

    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: "hold", committed: true, transcriptLength: nil, turnKind: .question, audioSeconds: 19.5)
    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: "hold", committed: true, transcriptLength: nil, turnKind: .question, audioSeconds: 61)
    // A site that genuinely does not know the length omits the property.
    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: "hold", committed: true, transcriptLength: nil, turnKind: .question)

    let buckets = capturedBox.value.map { $0.1["audio_seconds_bucket"] as? String }
    XCTAssertEqual(buckets, ["lt_20", "ge_60", nil])
  }

  func testDictationTranscriberRidesOnlyDictationTerminals() {
    startCapturing()

    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: "hold", committed: true, transcriptLength: 3, turnKind: .dictation,
      dictationTranscriber: "backend_batch_stt")
    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: "hold", committed: true, transcriptLength: nil, turnKind: .question)

    XCTAssertEqual(capturedBox.value[0].1["dictation_transcriber"] as? String, "backend_batch_stt")
    XCTAssertNil(capturedBox.value[1].1["dictation_transcriber"])
  }

  // MARK: - privacy boundary

  /// PostHog receives bounded dimensions only: the payload's key set is closed
  /// and contains no transcript, prompt, or free-text key.
  func testPayloadKeysStayBoundedAndContentFree() {
    startCapturing()

    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: "hold", committed: true, transcriptLength: 12, turnKind: .dictation,
      audioSeconds: 3, dictationTranscriber: "on_device_asr")
    AnalyticsManager.shared.floatingBarPTTEnded(
      mode: "hold", committed: false, transcriptLength: nil, turnKind: .unknown)

    let allowed: Set<String> = [
      "mode", "had_transcript", "transcript_length", "turn_kind", "audio_seconds_bucket",
      "dictation_transcriber",
    ]
    for (_, props) in capturedBox.value {
      assertKeysWithin(Set(props.keys), allowed)
    }
    // No key may carry content, even by another name.
    let contentBearing: Set<String> = [
      "transcript", "transcript_text", "text", "prompt", "message", "query", "response",
    ]
    for (_, props) in capturedBox.value {
      XCTAssertTrue(Set(props.keys).isDisjoint(with: contentBearing))
    }
  }

  // MARK: - call-site wiring (source inspection)

  /// Every terminal in `PushToTalkManager` must classify its `turn_kind`
  /// explicitly — the payload contract above is worthless if a site forgets
  /// the argument and silently reports `unknown`.
  func testEveryPTTTerminalCallSiteClassifiesTurnKindExplicitly() throws {
    // omi-test-quality: source-inspection -- static contract: every floatingBarPTTEnded and pttLifecycle.terminate call site in PushToTalkManager passes an explicit turnKind; driving the full CoreAudio/key-event stack behaviorally is not possible in a unit test, and the payload contract is covered behaviorally above.
    let source = try pushToTalkManagerSource()

    for (_, call) in balancedCalls(of: "floatingBarPTTEnded(", in: source)
      + balancedCalls(of: "pttLifecycle.terminate(", in: source)
    {
      XCTAssertTrue(
        call.contains("turnKind:"), "terminal call site must pass turnKind:\n\(call.prefix(200))")
    }

    // The dictation close funnels through finishVoiceTypingTurn; every product
    // event inside it is a dictation terminal.
    let body = try functionBody(named: "finishVoiceTypingTurn", in: source)
    for (lineNumber, call) in balancedCalls(of: "floatingBarPTTEnded(", in: body) {
      XCTAssertTrue(
        call.contains("turnKind: .dictation"),
        "dictation close must classify as .dictation (body line \(lineNumber))")
    }
  }

  /// The lifecycle terminate inside the dictation close is the one place a
  /// `voice_typing` snapshot is emitted — it must be `dictation`, not the
  /// `unknown` default.
  func testVoiceTypingLifecycleTerminateIsDictation() throws {
    // omi-test-quality: source-inspection -- static contract: terminateVoiceTypingLifecycle is the single voice_typing lifecycle emit and must pass .dictation; the recorder field itself is covered behaviorally in PTTAttemptLifecycleRecorderTests.
    let source = try pushToTalkManagerSource()
    let body = try functionBody(named: "terminateVoiceTypingLifecycle", in: source)
    XCTAssertTrue(body.contains("turnKind: .dictation"))
  }

  // MARK: - helpers
  private func pushToTalkManagerSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/PushToTalkManager.swift")
    // omi-test-quality: source-inspection -- static contract: reads PushToTalkManager.swift for the annotated turn_kind call-site tripwires above; payload behavior is covered behaviorally in this file.
    return try String(contentsOf: url, encoding: .utf8)
  }

  /// Extracts a `func <name>(...) { ... }` body by brace matching.
  private func functionBody(named name: String, in source: String) throws -> String {
    let signature = try XCTUnwrap(
      source.range(of: "func \(name)("), "function \(name) not found")
    let opening = try XCTUnwrap(source[signature.lowerBound...].firstIndex(of: "{"))
    var depth = 1
    var index = source.index(after: opening)
    while index < source.endIndex, depth > 0 {
      if source[index] == "{" { depth += 1 }
      if source[index] == "}" { depth -= 1 }
      index = source.index(after: index)
    }
    return String(source[opening..<index])
  }

  /// Returns `(lineNumber, fullBalancedCall)` for every occurrence of `needle`
  /// in `source`, where the call text spans from the needle through its
  /// matching close parenthesis.
  private func balancedCalls(of needle: String, in source: String) -> [(Int, String)] {
    var calls: [(Int, String)] = []
    var searchRange = source.startIndex..<source.endIndex
    while let found = source.range(of: needle, range: searchRange) {
      var depth = 1
      var index = found.upperBound
      while index < source.endIndex, depth > 0 {
        if source[index] == "(" { depth += 1 }
        if source[index] == ")" { depth -= 1 }
        index = source.index(after: index)
      }
      calls.append(
        (
          source[..<(found.lowerBound)].components(separatedBy: "\n").count,
          String(source[found.lowerBound..<index])
        ))
      searchRange = index..<source.endIndex
    }
    return calls
  }
}

extension Array {
  fileprivate var single: Element? { count == 1 ? first : nil }
}

private func assertKeysWithin(
  _ keys: Set<String>, _ allowed: Set<String>, file: StaticString = #filePath, line: UInt = #line
) {
  XCTAssertTrue(
    keys.subtracting(allowed).isEmpty, "unexpected payload keys: \(keys.subtracting(allowed))",
    file: file, line: line)
}
