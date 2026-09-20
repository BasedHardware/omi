import Foundation
import XCTest

@testable import Omi_Computer

/// Measures the **local-server** path — a developer-run `llama-server` through
/// the production summarizer — against `LocalSummaryEvalCorpus`.
///
/// Sibling of `AFMSummaryEvalTests`, deliberately not a parameterization of it.
/// That test asserts a Mac that can run AFM selects AFM with no force overlay,
/// which protects a real invariant; forcing the engine there would either trip
/// the assertion or tempt someone into weakening it. Here the runtime is built
/// with the local-server engine as its only engine, so nothing about AFM
/// availability on the measuring machine can change what is being measured.
///
/// Scoring is copied from the AFM test line for line so the two summary lines
/// are directly comparable. If one changes, change both.
///
/// Live, slow, and needs a server, so it skips unless asked:
///
/// ```
/// OMI_LOCAL_SERVER_EVAL=1 \
/// OMI_LOCAL_INFERENCE_URL=http://127.0.0.1:8099/v1 \
/// OMI_LOCAL_INFERENCE_CONTEXT_TOKENS=32768 \
/// OMI_LOCAL_INFERENCE_TIMEOUT_SECONDS=1800 \
/// OMI_LOCAL_INFERENCE_TRACE=1 \
/// xcrun swift test --package-path desktop/macos/Desktop \
///   --filter LocalServerSummaryEvalTests
/// ```
///
/// `OMI_LOCAL_SERVER_EVAL_DUMP_DIR`, when set, receives one JSON projection per
/// scenario so precision can be read by a person rather than inferred from a
/// containment ratio.
final class LocalServerSummaryEvalTests: XCTestCase {
  override func setUp() {
    super.setUp()
    executionTimeAllowance = 7200
  }

  private struct PrintingFallbackRecorder: LocalInferenceFallbackRecording {
    func recordLocalInferenceFallback(
      from: String,
      to: String,
      reason: String,
      outcome: DesktopFallbackOutcome
    ) {
      // A fallback is an engine finding, not a quality finding. Surface it next
      // to the case it belongs to so the two are never conflated afterwards.
      print("LOCAL_SERVER_EVAL_FALLBACK from=\(from) to=\(to) reason=\(reason) outcome=\(outcome)")
    }
  }

  /// Writes every request body and response body to disk, then forwards.
  ///
  /// The adapter reduces a response to a decoded draft or an error case, which
  /// is right for the product and useless for diagnosis: a runaway generation, a
  /// truncated object and a 400 all arrive here as "deterministic minimum". The
  /// bytes on the wire are the only record of which one happened.
  private actor WireRecordingHTTPClient: LocalInferenceHTTPClient {
    private let directory: URL?
    private let forward = URLSessionLocalInferenceHTTPClient()
    private var sequence = 0
    private var label = "unlabelled"

    init(directory: URL?) { self.directory = directory }

    func setLabel(_ label: String) { self.label = label }

    func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
      sequence += 1
      let stem = String(format: "%03d-%@", sequence, label)
      if let directory, let body = request.httpBody {
        try? body.write(to: directory.appendingPathComponent("\(stem).request.json"))
      }
      let (data, response) = try await forward.send(request)
      if let directory {
        try? data.write(to: directory.appendingPathComponent("\(stem).response.json"))
      }
      return (data, response)
    }
  }

  func testCorpusThroughProductionSummarizerOnLocalServer() async throws {
    let environment = ProcessInfo.processInfo.environment
    try XCTSkipUnless(
      environment["OMI_LOCAL_SERVER_EVAL"] == "1",
      "set OMI_LOCAL_SERVER_EVAL=1 (and start llama-server) to run the live local-server evaluation"
    )

    let configuration = LocalServerInferenceConfiguration.fromKillSwitchSources()
    let wireDirectory = environment["OMI_LOCAL_SERVER_EVAL_DUMP_DIR"].map {
      URL(fileURLWithPath: $0).appendingPathComponent("wire")
    }
    if let wireDirectory {
      try FileManager.default.createDirectory(at: wireDirectory, withIntermediateDirectories: true)
    }
    let wire = WireRecordingHTTPClient(directory: wireDirectory)
    let runtime = LocalInferenceRuntime(
      engines: [LocalServerInferenceAdapter(configuration: configuration, httpClient: wire)],
      killSwitches: .enabled,
      fallback: PrintingFallbackRecorder(),
      defaultEngineID: .localServer
    )
    XCTAssertEqual(runtime.defaultEngineID, .localServer)
    let window = try XCTUnwrap(runtime.selectedContextWindowTokens())
    print(
      "LOCAL_SERVER_EVAL_WINDOW selected=\(window) url=\(configuration.baseURL.absoluteString) model=\(configuration.model) timeout_s=\(Int(configuration.timeout))"
    )

    let dumpDirectory = environment["OMI_LOCAL_SERVER_EVAL_DUMP_DIR"].map { URL(fileURLWithPath: $0) }
    if let dumpDirectory {
      try FileManager.default.createDirectory(at: dumpDirectory, withIntermediateDirectories: true)
    }

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

    // Diagnostic narrowing only. A summary line from a filtered run is not
    // comparable with the AFM baseline and says so in `n=`.
    let only = environment["OMI_LOCAL_SERVER_EVAL_ONLY"].map { Set($0.split(separator: ",").map(String.init)) }
    let scenarios = LocalSummaryEvalCorpus.scenarios.filter { only?.contains($0.id) ?? true }

    for scenario in scenarios {
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

      if let dumpDirectory, chunks.count <= 1 {
        // The exact one-shot prompt, so a failed call can be replayed against
        // the server with curl and its real output read, instead of theorized.
        let prompt = ConversationChunkSummarizer.finalPrompt(ConversationChunkSummarizer.plainTranscript(segments))
        try Data(prompt.utf8).write(to: dumpDirectory.appendingPathComponent("\(scenario.id).prompt.txt"))
      }

      await wire.setLabel(scenario.id)
      let started = ContinuousClock.now
      let stored = try await summarizer.summarize(
        sessionId: Int64(abs(scenario.id.hashValue % 100_000)),
        segments: segments,
        startedAt: Date(timeIntervalSince1970: 1_758_000_000)
      )
      latencies[scenario.id] = max(0, Int(started.duration(to: .now) / .milliseconds(1)))

      if let dumpDirectory {
        try stored.json.write(to: dumpDirectory.appendingPathComponent("\(scenario.id).json"))
      }

      let projection = try ClientProcessingContract.decode(stored.json)
      let structure = projection.structure
      let isDeterministic = projection.provenance.runtime == ClientProcessingContract.deterministicRuntime
      if !isDeterministic { schemaOK += 1 }

      let overview = structure.overview ?? ""
      let sections = structure.sections ?? []
      let body =
        ([overview] + sections.map { "\($0.heading) \($0.bodyMarkdown)" })
        .joined(separator: "\n")
      let bodyIsEmpty = body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      if isDeterministic || bodyIsEmpty { contentless += 1 }

      let producedActions = (projection.actionItems ?? []).map(\.description_)
      actionsProduced += producedActions.count

      var caseActionsFound = 0
      actionsLabelled += scenario.labelledActionItems.count
      for label in scenario.labelledActionItems {
        let inActions = producedActions.contains { LocalSummaryEvalCorpus.matches(label: label, produced: $0) }
        let inBody = LocalSummaryEvalCorpus.matches(label: label, produced: body)
        if inActions || inBody {
          actionsFound += 1
          caseActionsFound += 1
        } else {
          print("LOCAL_SERVER_EVAL_MISS id=\(scenario.id) kind=action label=\(label)")
        }
      }

      let transcript = scenario.turns.map(\.text).joined(separator: " ")
      var caseSupported = 0
      var caseVerbatim = 0
      for produced in producedActions {
        let support = LocalSummaryEvalCorpus.containment(label: produced, produced: transcript)
        if support >= 0.5 {
          actionsSupported += 1
          caseSupported += 1
        } else {
          print(
            "LOCAL_SERVER_EVAL_UNSUPPORTED id=\(scenario.id) containment=\(String(format: "%.2f", support)) action=\(produced)"
          )
        }
        if LocalSummaryEvalCorpus.isVerbatimCopy(produced, of: scenario.turns) {
          actionsVerbatim += 1
          caseVerbatim += 1
        }
      }

      var caseFactsKept = 0
      factsLabelled += scenario.mustKeepFacts.count
      for fact in scenario.mustKeepFacts {
        if LocalSummaryEvalCorpus.matches(label: fact, produced: body) {
          factsKept += 1
          caseFactsKept += 1
        } else {
          print("LOCAL_SERVER_EVAL_MISS id=\(scenario.id) kind=fact label=\(fact)")
        }
      }

      var caseHallucinated = 0
      for banned in scenario.hallucinatedIfPresent {
        let claimed =
          LocalSummaryEvalCorpus.claims(banned, in: body)
          || producedActions.contains { LocalSummaryEvalCorpus.matches(label: banned, produced: $0) }
        if claimed {
          hallucinated += 1
          caseHallucinated += 1
          print("LOCAL_SERVER_EVAL_HALLUCINATED id=\(scenario.id) claim=\(banned)")
        }
      }

      print(
        """
        LOCAL_SERVER_EVAL_CASE id=\(scenario.id) class=\(scenario.lengthClass.rawValue) \
        tokens=\(scenario.estimatedTokens) chunks=\(chunks.count) \
        path=\(chunks.count > 1 ? "chunked" : "one-shot") \
        ms=\(latencies[scenario.id] ?? -1) runtime=\(projection.provenance.runtime) \
        model=\(projection.provenance.modelId) sections=\(sections.count) \
        actions=\(producedActions.count) overview_len=\(overview.count) \
        facts=\(caseFactsKept)/\(scenario.mustKeepFacts.count) \
        action_recall=\(caseActionsFound)/\(scenario.labelledActionItems.count) \
        action_support=\(caseSupported)/\(producedActions.count) hallucinated=\(caseHallucinated) \
        verbatim=\(caseVerbatim)/\(producedActions.count)
        TITLE: \(structure.title)
        OVERVIEW: \(overview)
        """
      )
    }

    let n = scenarios.count
    let chunked = chunkCounts.values.filter { $0 > 1 }.count
    let mean = latencies.values.isEmpty ? 0 : latencies.values.reduce(0, +) / latencies.count
    print(
      """
      LOCAL_SERVER_EVAL_SUMMARY n=\(n) chunked=\(chunked) schema_ok=\(schemaOK)/\(n) \
      contentless=\(contentless)/\(n) fact_retention=\(factsKept)/\(factsLabelled) \
      action_recall=\(actionsFound)/\(actionsLabelled) \
      action_support=\(actionsSupported)/\(actionsProduced) \
      hallucinated=\(hallucinated) mean_ms=\(mean) \
      verbatim=\(actionsVerbatim)/\(actionsProduced)
      """
    )

    // No `chunked >= 2` assertion here, on purpose. The AFM test needs it because
    // an 8192 window that chunked nothing measured the wrong thing. This test is
    // run at more than one window, and "nothing chunked" at 32K is the hypothesis
    // rather than a harness fault. The summary line carries `chunked=` instead.
  }
}
