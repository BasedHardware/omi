import Foundation
import XCTest

@testable import Omi_Computer

#if canImport(FoundationModels)
  import FoundationModels
#endif

/// Measures the **shipping** free-tier path — AFM through the production
/// summarizer — against `LocalSummaryEvalCorpus`.
///
/// ## Why this exists
///
/// Until now AFM had never been run against any corpus. The small-model
/// evaluation produced a floor with no ceiling: if AFM scores similarly, the
/// limit is the harness, the prompts, or the task shape rather than parameter
/// count, and that is a far more consequential finding — AFM is the path we are
/// about to turn on for beta. All four defects fixed in the summarizer were
/// found in this path and were never measured in it.
///
/// Live, slow, and machine-dependent, so it skips unless asked:
///
/// ```
/// OMI_AFM_EVAL=1 xcrun swift test --package-path desktop/macos/Desktop \
///   --filter AFMSummaryEvalTests
/// ```
final class AFMSummaryEvalTests: XCTestCase {
  override func setUp() {
    super.setUp()
    executionTimeAllowance = 3600
  }

  private func skipUnlessRequested() throws {
    try XCTSkipUnless(
      ProcessInfo.processInfo.environment["OMI_AFM_EVAL"] == "1",
      "set OMI_AFM_EVAL=1 to run the live AFM evaluation"
    )
  }

  private func skipUnlessAFMAvailable() throws {
    #if canImport(FoundationModels)
      guard #available(macOS 26.0, *) else { throw XCTSkip("FoundationModels needs macOS 26+") }
      guard case .available = SystemLanguageModel.default.availability else {
        throw XCTSkip("Apple Intelligence is not available on this Mac")
      }
    #else
      throw XCTSkip("FoundationModels is not present in this toolchain")
    #endif
  }

  func testCorpusThroughProductionSummarizerOnAFM() async throws {
    try skipUnlessRequested()
    try skipUnlessAFMAvailable()

    let runtime = LocalInferenceRuntime.makeDefault(killSwitches: .enabled)
    XCTAssertEqual(
      runtime.defaultEngineID, .afm,
      "a Mac that can run AFM must select it without a force overlay; measuring anything else here is measuring the wrong engine"
    )
    let window = try XCTUnwrap(runtime.selectedContextWindowTokens())
    print("AFM_EVAL_WINDOW selected=\(window)")

    var schemaOK = 0
    var contentless = 0
    var actionsFound = 0
    var actionsLabelled = 0
    var actionsProduced = 0
    var actionsSupported = 0
    var actionsVerbatim = 0
    var hallucinated = 0
    var factsKept = 0
    var factsLabelled = 0
    var latencies: [String: Int] = [:]
    var chunkCounts: [String: Int] = [:]

    for scenario in LocalSummaryEvalCorpus.scenarios {
      let segments = scenario.segments()
      let chunks = ConversationChunkSummarizer.chunk(segments, windowTokens: window)
      chunkCounts[scenario.id] = chunks.count

      let summarizer = ConversationChunkSummarizer(
        runtime: runtime,
        store: MemoryLocalProjectionStore(),
        now: { Date(timeIntervalSince1970: 1_758_000_000) },
        sourceLabel: "Recording",
        timeZone: TimeZone(identifier: "UTC") ?? .current
      )

      let started = ContinuousClock.now
      let stored = try await summarizer.summarize(
        sessionId: Int64(abs(scenario.id.hashValue % 100_000)),
        segments: segments,
        startedAt: Date(timeIntervalSince1970: 1_758_000_000)
      )
      latencies[scenario.id] = max(0, Int(started.duration(to: .now) / .milliseconds(1)))

      // Read-only side channel for hand-auditing precision; scoring is unchanged.
      if let dump = ProcessInfo.processInfo.environment["OMI_AFM_EVAL_DUMP_DIR"] {
        let directory = URL(fileURLWithPath: dump)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try stored.json.write(to: directory.appendingPathComponent("\(scenario.id).json"))
      }

      let projection = try ClientProcessingContract.decode(stored.json)
      let structure = projection.structure
      let isDeterministic = projection.provenance.runtime == ClientProcessingContract.deterministicRuntime
      if !isDeterministic { schemaOK += 1 }

      // The generated DTO makes every optional-with-default field optional, so
      // unwrap once here rather than sprinkling `?? ` through the scoring below.
      let overview = structure.overview ?? ""
      let sections = structure.sections ?? []
      let body =
        ([overview] + sections.map { "\($0.heading) \($0.bodyMarkdown)" })
        .joined(separator: "\n")
      let bodyIsEmpty = body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      if isDeterministic || bodyIsEmpty { contentless += 1 }

      let producedActions = (projection.actionItems ?? []).map(\.description_)
      actionsProduced += producedActions.count

      actionsLabelled += scenario.labelledActionItems.count
      for label in scenario.labelledActionItems {
        // An action may be surfaced as an action item OR stated in the body; a
        // reader who sees the commitment written down has it either way.
        let inActions = producedActions.contains { LocalSummaryEvalCorpus.matches(label: label, produced: $0) }
        let inBody = LocalSummaryEvalCorpus.matches(label: label, produced: body)
        if inActions || inBody { actionsFound += 1 }
      }

      let transcript = scenario.turns.map(\.text).joined(separator: " ")
      var caseVerbatim = 0
      for produced in producedActions {
        if LocalSummaryEvalCorpus.containment(label: produced, produced: transcript) >= 0.5 {
          actionsSupported += 1
        }
        if LocalSummaryEvalCorpus.isVerbatimCopy(produced, of: scenario.turns) {
          actionsVerbatim += 1
          caseVerbatim += 1
        }
      }

      factsLabelled += scenario.mustKeepFacts.count
      for fact in scenario.mustKeepFacts
      where LocalSummaryEvalCorpus.matches(label: fact, produced: body) {
        factsKept += 1
      }

      for banned in scenario.hallucinatedIfPresent {
        let claimed =
          LocalSummaryEvalCorpus.claims(banned, in: body)
          || producedActions.contains { LocalSummaryEvalCorpus.matches(label: banned, produced: $0) }
        if claimed { hallucinated += 1 }
      }

      print(
        """
        AFM_EVAL_CASE id=\(scenario.id) class=\(scenario.lengthClass.rawValue) \
        tokens=\(scenario.estimatedTokens) chunks=\(chunks.count) \
        ms=\(latencies[scenario.id] ?? -1) runtime=\(projection.provenance.runtime) \
        model=\(projection.provenance.modelId) sections=\(sections.count) \
        actions=\(producedActions.count) overview_len=\(overview.count) \
        verbatim=\(caseVerbatim)/\(producedActions.count)
        TITLE: \(structure.title)
        OVERVIEW: \(overview)
        """
      )
    }

    let n = LocalSummaryEvalCorpus.scenarios.count
    let chunked = chunkCounts.values.filter { $0 > 1 }.count
    let mean = latencies.values.isEmpty ? 0 : latencies.values.reduce(0, +) / latencies.count
    print(
      """
      AFM_EVAL_SUMMARY n=\(n) chunked=\(chunked) schema_ok=\(schemaOK)/\(n) \
      contentless=\(contentless)/\(n) fact_retention=\(factsKept)/\(factsLabelled) \
      action_recall=\(actionsFound)/\(actionsLabelled) \
      action_support=\(actionsSupported)/\(actionsProduced) \
      hallucinated=\(hallucinated) mean_ms=\(mean) \
      verbatim=\(actionsVerbatim)/\(actionsProduced)
      """
    )

    // The corpus guarantees both long scenarios exceed the AFM window, so a run
    // where nothing chunked measured the wrong thing entirely.
    XCTAssertGreaterThanOrEqual(chunked, 2, "the reduce pass did not run; this measured single-pass only")
  }
}
