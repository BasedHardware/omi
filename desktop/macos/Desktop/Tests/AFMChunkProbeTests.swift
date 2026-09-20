import Foundation
import XCTest

@testable import Omi_Computer

#if canImport(FoundationModels)
  import FoundationModels
#endif

/// Per-stage timing and outcome for a chunked conversation on live AFM.
///
/// The end-to-end eval reports only "produced nothing" because
/// `LocalInferenceRuntime` fails closed with a low-cardinality reason. This runs
/// the production chunking and then each stage by hand, so a failure can be
/// attributed to a specific map chunk or to the reduce, with the prompt size and
/// wall time that produced it.
///
/// History: an earlier form of this probe established that AFM reports a window
/// of 8192 but stops answering well below it — failing at 7217 estimated tokens
/// (bytes/4) and answering at 5518 — which is why `estimatedTokens` is now bytes/3.
///
/// ```
/// OMI_AFM_EVAL=1 xcrun swift test --package-path desktop/macos/Desktop \
///   --filter AFMChunkProbeTests
/// ```
final class AFMChunkProbeTests: XCTestCase {
  override func setUp() {
    super.setUp()
    executionTimeAllowance = 3000
  }

  /// Recovers what `AFMLocalInferenceAdapter` throws away on macOS 27.
  ///
  /// `mapFrameworkError` returns `.engineFailed("session_failed")` for *every*
  /// error under `#available(macOS 27.0, *)`, because the pinned Xcode 26.6
  /// toolchain cannot name `LanguageModelError` and `#if compiler` is forbidden
  /// by `check-desktop-compiler-gates.py`. So on the OS beta users run, a context
  /// overflow, a guardrail refusal, a rate limit and a decode failure are
  /// indistinguishable.
  ///
  /// `NSError` bridging needs no framework type, so domain and code survive the
  /// pin and can say which one it actually was.
  private static func describe(_ error: Error) -> String {
    let ns = error as NSError
    var parts = ["domain=\(ns.domain)", "code=\(ns.code)", "desc=\(ns.localizedDescription)"]
    if let reason = ns.localizedFailureReason { parts.append("reason=\(reason)") }
    if let underlying = ns.userInfo[NSUnderlyingErrorKey] as? NSError {
      parts.append("underlying=\(underlying.domain)/\(underlying.code)/\(underlying.localizedDescription)")
    }
    parts.append("type=\(String(reflecting: type(of: error)))")
    return parts.joined(separator: " ")
  }

  private func skipUnlessLive() throws {
    try XCTSkipUnless(
      ProcessInfo.processInfo.environment["OMI_AFM_EVAL"] == "1",
      "set OMI_AFM_EVAL=1 to run"
    )
    #if canImport(FoundationModels)
      guard #available(macOS 26.0, *) else { throw XCTSkip("needs macOS 26+") }
      guard case .available = SystemLanguageModel.default.availability else {
        throw XCTSkip("Apple Intelligence unavailable")
      }
    #else
      throw XCTSkip("FoundationModels absent")
    #endif
  }

  func testPerStageOutcomeOnEveryLongScenario() async throws {
    try skipUnlessLive()
    let adapter = AFMLocalInferenceAdapter()
    let window = adapter.capabilities.contextWindowTokens

    for scenario in LocalSummaryEvalCorpus.scenarios where scenario.lengthClass == .long {
      let chunks = ConversationChunkSummarizer.chunk(scenario.segments(), windowTokens: window)
      print("PROBE scenario=\(scenario.id) tokens=\(scenario.estimatedTokens) chunks=\(chunks.count) window=\(window)")

      var drafts: [LocalSummaryDraft] = []
      var mapFailed = false
      for (index, chunk) in chunks.enumerated() {
        let prompt = ConversationChunkSummarizer.mapPrompt(
          ConversationChunkSummarizer.plainTranscript(chunk),
          index: index + 1,
          total: chunks.count
        )
        let estimated = ConversationChunkSummarizer.estimatedTokens(prompt)
        let started = ContinuousClock.now
        do {
          // Straight at the session, not through the adapter: `generateStructured`
          // has already flattened the framework error to `session_failed` by the
          // time it reaches a caller on macOS 27, which is the information we need.
          let node = try AFMJSONSchemaBridge.parse(LocalSummaryDraft.jsonSchema)
          let data = try await AFMSystemSession().generateJSON(prompt: prompt, node: node)
          let draft = try JSONDecoder().decode(LocalSummaryDraft.self, from: data)
          let ms = Int(started.duration(to: .now) / .milliseconds(1))
          drafts.append(draft)
          print(
            "PROBE \(scenario.id) map[\(index)] OK prompt=\(estimated) ms=\(ms) sections=\(draft.sections.count) actions=\(draft.actionItems.count)"
          )
        } catch {
          let ms = Int(started.duration(to: .now) / .milliseconds(1))
          print(
            "PROBE \(scenario.id) map[\(index)] FAIL prompt=\(estimated) ms=\(ms) error=\(error)"
          )
          print("PROBE   raw=\(Self.describe(error))")
          mapFailed = true
          break
        }
      }
      guard !mapFailed else { continue }

      let reducePrompt = ConversationChunkSummarizer.reducePrompt(drafts)
      let reduceEstimated = ConversationChunkSummarizer.estimatedTokens(reducePrompt)
      let started = ContinuousClock.now
      do {
        let node = try AFMJSONSchemaBridge.parse(LocalSummaryDraft.jsonSchema)
        let data = try await AFMSystemSession().generateJSON(prompt: reducePrompt, node: node)
        let merged = try JSONDecoder().decode(LocalSummaryDraft.self, from: data)
        let ms = Int(started.duration(to: .now) / .milliseconds(1))
        print(
          "PROBE \(scenario.id) reduce OK prompt=\(reduceEstimated) ms=\(ms) sections=\(merged.sections.count) actions=\(merged.actionItems.count)"
        )
      } catch {
        let ms = Int(started.duration(to: .now) / .milliseconds(1))
        print("PROBE \(scenario.id) reduce FAIL prompt=\(reduceEstimated) ms=\(ms) raw=\(Self.describe(error))")
      }
    }
  }
}
