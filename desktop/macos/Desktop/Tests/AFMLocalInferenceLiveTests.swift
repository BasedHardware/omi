import Foundation
import XCTest

@testable import Omi_Computer

#if canImport(FoundationModels)
  import FoundationModels
#endif

/// On-device Apple Foundation Models proof. CI has no Apple Intelligence and a
/// full run is minutes, so this suite skips unless `OMI_AFM_LIVE=1`.
///
/// Run:
/// `OMI_AFM_LIVE=1 xcrun swift test --package-path desktop/macos/Desktop --filter AFMLocalInferenceLiveTests`
final class AFMLocalInferenceLiveTests: XCTestCase {
  static let liveEnvironmentKey = "OMI_AFM_LIVE"

  override func setUp() {
    super.setUp()
    executionTimeAllowance = 900
  }

  func testLiveStructuredGeneration() async throws {
    try skipUnlessLiveRequested()
    try XCTSkipUnless(isLiveAFMAvailable(), "Apple Foundation Models is not available on this Mac")
    let adapter = AFMLocalInferenceAdapter()
    let summary: LiveProbeSummary = try await adapter.generateStructured(
      prompt: "Return JSON with title set to the two-word phrase On Device. Do not invent extra fields.",
      schema: LiveProbeSchema.title
    )
    print("AFM_LIVE_STRUCTURED: title=\(summary.title)")
    XCTAssertFalse(summary.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
  }

  func testLiveConversationChunkSummarizerProducesStoredProjection() async throws {
    try skipUnlessLiveRequested()
    try XCTSkipUnless(isLiveAFMAvailable(), "Apple Foundation Models is not available on this Mac")
    let runtime = LocalInferenceRuntime.makeDefault(killSwitches: .enabled)
    XCTAssertEqual(runtime.defaultEngineID, .afm, "a Mac that can run AFM must select it without a force overlay")
    let window = try XCTUnwrap(runtime.selectedContextWindowTokens())
    #if canImport(FoundationModels)
      guard #available(macOS 26.0, *) else {
        throw XCTSkip("FoundationModels needs macOS 26+")
      }
      XCTAssertEqual(
        window,
        AFMLocalInferenceAdapter.acceptedContextWindowTokens(SystemLanguageModel.default.contextSize),
        "production AFM window must be SystemLanguageModel.default.contextSize after bounds"
      )
      print(
        "AFM_LIVE_WINDOW: selected=\(window) systemLanguageModel.contextSize=\(SystemLanguageModel.default.contextSize)"
      )
    #else
      print("AFM_LIVE_WINDOW: selected=\(window)")
    #endif

    let node = try AFMJSONSchemaBridge.parse(LocalSummaryDraft.jsonSchema)
    print("AFM_LIVE_SCHEMA_REQUIRED: \(requiredPropertyNames(node).joined(separator: ","))")

    let segments = [
      TranscriptHash.Segment(speaker: "SPEAKER_00", text: "We decided to ship the on-device summarizer today."),
      TranscriptHash.Segment(speaker: "SPEAKER_01", text: "I will write the adapter tests this afternoon."),
    ]
    let transcript = ConversationChunkSummarizer.plainTranscript(segments)
    let prompt = ConversationChunkSummarizer.finalPrompt(transcript)
    let chunks = ConversationChunkSummarizer.chunk(segments, windowTokens: window)
    print(
      "AFM_LIVE_PROMPT: chars=\(prompt.count) estimatedTokens=\(ConversationChunkSummarizer.estimatedTokens(prompt)) chunks=\(chunks.count)"
    )

    let adapter = AFMLocalInferenceAdapter()
    let draft: LocalSummaryDraft = try await adapter.generateStructured(
      prompt: prompt,
      schema: LocalSummaryDraft.jsonSchema
    )
    print(
      "AFM_LIVE_DRAFT: title=\(draft.title) overview_len=\(draft.overview.count) sections=\(draft.sections.count) action_items=\(draft.actionItems.count) events=\(draft.events.count)"
    )
    print("AFM_LIVE_DRAFT_OVERVIEW: \(draft.overview)")
    print(
      "AFM_LIVE_DRAFT_SECTIONS: \(draft.sections.map { "\($0.heading)|\($0.bodyMarkdown.count)" }.joined(separator: "; "))"
    )

    let store = MemoryLocalProjectionStore()
    let summarizer = ConversationChunkSummarizer(
      runtime: runtime,
      store: store,
      now: { Date(timeIntervalSince1970: 1_704_140_040) },
      deviceClass: "macos",
      sourceLabel: "Recording",
      timeZone: TimeZone.gmt
    )
    let stored = try await summarizer.summarize(
      sessionId: 42,
      segments: segments,
      startedAt: Date(timeIntervalSince1970: 1_704_140_040)
    )
    let payload = try ClientProcessingContract.decode(stored.json)
    let json = String(decoding: stored.json, as: UTF8.self)
    print("AFM_LIVE_PROJECTION_JSON: \(json)")
    print(
      "AFM_LIVE_PROJECTION: title=\(payload.structure.title) runtime=\(payload.provenance.runtime) model=\(payload.provenance.modelId) overview=\(payload.structure.overview ?? "") sections=\(payload.structure.sections?.count ?? 0) action_items=\(payload.actionItems?.count ?? 0)"
    )
    XCTAssertEqual(payload.schemaVersion, ClientProcessingContract.schemaVersion)
    XCTAssertEqual(payload.transcriptSha256, TranscriptHash.sha256(segments: segments))
    XCTAssertFalse(payload.structure.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
    XCTAssertEqual(payload.provenance.runtime, ClientProcessingContract.localRuntime)
    XCTAssertEqual(payload.provenance.modelId, LocalInferenceEngineID.afm.rawValue)
  }

  private func skipUnlessLiveRequested() throws {
    try XCTSkipUnless(
      ProcessInfo.processInfo.environment[Self.liveEnvironmentKey] == "1",
      "set OMI_AFM_LIVE=1 to run on-device AFM live tests"
    )
  }

  private func isLiveAFMAvailable() -> Bool {
    AFMSystemAvailabilityChecker().resolve() == .available
  }

  private func requiredPropertyNames(_ node: AFMJSONSchemaNode) -> [String] {
    guard case .object(_, let properties, _) = node else { return [] }
    return properties.filter { !$0.isOptional }.map(\.name)
  }
}

private struct LiveProbeSummary: Codable, Sendable, Equatable {
  var title: String
}

private enum LiveProbeSchema {
  static let title = LocalInferenceJSONSchema(
    name: "probe",
    json: Data(#"{"type":"object","properties":{"title":{"type":"string"}},"required":["title"]}"#.utf8)
  )
}
