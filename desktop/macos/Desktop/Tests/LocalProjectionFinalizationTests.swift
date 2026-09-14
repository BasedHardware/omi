import Foundation
import XCTest

@testable import Omi_Computer

#if DEBUG
  final class LocalProjectionFinalizationTests: XCTestCase {
    func testFlagDefaultsOff() throws {
      let defaults = try XCTUnwrap(UserDefaults(suiteName: UUID().uuidString))
      let enabled = FreeTierLocalProcessingFlag.isEnabled(environment: [:], defaults: defaults)
      XCTAssertFalse(enabled)
    }

    func testFlagAcceptsEnvOneAndTrue() throws {
      let defaults = try XCTUnwrap(UserDefaults(suiteName: UUID().uuidString))
      XCTAssertTrue(
        FreeTierLocalProcessingFlag.isEnabled(
          environment: [FreeTierLocalProcessingFlag.environmentKey: "1"],
          defaults: defaults
        ))
      XCTAssertTrue(
        FreeTierLocalProcessingFlag.isEnabled(
          environment: [FreeTierLocalProcessingFlag.environmentKey: "true"],
          defaults: defaults
        ))
    }

    func testFlagAcceptsUserDefaults() throws {
      let defaults = try XCTUnwrap(UserDefaults(suiteName: UUID().uuidString))
      defaults.set(true, forKey: FreeTierLocalProcessingFlag.defaultsKey)
      let enabled = FreeTierLocalProcessingFlag.isEnabled(environment: [:], defaults: defaults)
      XCTAssertTrue(enabled)
    }

    func testDecisionSkipsWhenFlagOffOrNotBasic() {
      XCTAssertEqual(
        LocalProjectionFinalization.decision(
          flagEnabled: false,
          entitlement: .planGated,
          thermalState: .nominal
        ),
        .skip
      )
      XCTAssertEqual(
        LocalProjectionFinalization.decision(
          flagEnabled: true,
          entitlement: .allowManagedProactivity,
          thermalState: .nominal
        ),
        .skip
      )
    }

    func testDecisionGeneratesForIdentifiedBasic() {
      let decision = LocalProjectionFinalization.decision(
        flagEnabled: true,
        entitlement: .planGated,
        thermalState: .nominal
      )
      XCTAssertEqual(decision, .generate)
    }

    func testDecisionDefersGenerationAtSeriousThermal() {
      let serious = LocalProjectionFinalization.decision(
        flagEnabled: true,
        entitlement: .planGated,
        thermalState: .serious
      )
      let critical = LocalProjectionFinalization.decision(
        flagEnabled: true,
        entitlement: .planGated,
        thermalState: .critical
      )
      XCTAssertEqual(serious, .storedOnly)
      XCTAssertEqual(critical, .storedOnly)
    }

    func testProjectionGenerateUsesSummarizer() async throws {
      let summarizer = FixtureSummarizer(stored: try Self.fixture(runtime: "local"))
      let attached = await LocalProjectionFinalization.projection(
        decision: .generate,
        sessionId: 7,
        segments: [TranscriptHash.Segment(text: "hello")],
        startedAt: Date(timeIntervalSince1970: 1_704_140_040),
        summarizer: summarizer
      )
      let summarizeCalls = summarizer.summarizeCalls
      let peekCalls = summarizer.peekCalls
      let payload = try ClientProcessingContract.decode(try XCTUnwrap(attached))
      XCTAssertEqual(summarizeCalls, 1)
      XCTAssertEqual(peekCalls, 0)
      XCTAssertEqual(payload.provenance.runtime, "local")
    }

    func testProjectionStoredOnlySkipsGenerationWithoutABlob() async throws {
      let summarizer = FixtureSummarizer(stored: nil)
      let attached = await LocalProjectionFinalization.projection(
        decision: .storedOnly,
        sessionId: 7,
        segments: [TranscriptHash.Segment(text: "hello")],
        startedAt: Date(timeIntervalSince1970: 1_704_140_040),
        summarizer: summarizer
      )
      let summarizeCalls = summarizer.summarizeCalls
      let peekCalls = summarizer.peekCalls
      XCTAssertNil(attached)
      XCTAssertEqual(summarizeCalls, 0)
      XCTAssertEqual(peekCalls, 1)
    }

    func testProjectionStoredOnlySendsMatchingBlob() async throws {
      let stored = try Self.fixture(runtime: "local")
      let summarizer = FixtureSummarizer(stored: stored)
      let attached = await LocalProjectionFinalization.projection(
        decision: .storedOnly,
        sessionId: 7,
        segments: [TranscriptHash.Segment(text: "hello")],
        startedAt: Date(timeIntervalSince1970: 1_704_140_040),
        summarizer: summarizer
      )
      let summarizeCalls = summarizer.summarizeCalls
      let payload = try ClientProcessingContract.decode(try XCTUnwrap(attached))
      XCTAssertEqual(summarizeCalls, 0)
      XCTAssertEqual(payload.provenance.runtime, "local")
      XCTAssertEqual(payload.transcriptSha256, stored.transcriptSha256)
    }

    func testProjectionFailsClosedWhenSummarizerThrows() async {
      let attached = await LocalProjectionFinalization.projection(
        decision: .generate,
        sessionId: 7,
        segments: [TranscriptHash.Segment(text: "hello")],
        startedAt: Date(timeIntervalSince1970: 1_704_140_040),
        summarizer: ThrowingSummarizer()
      )
      XCTAssertNil(attached)
    }

    private static func fixture(runtime: String) throws -> StoredClientProjection {
      let segments = [TranscriptHash.Segment(text: "hello")]
      let projection = ClientProcessingContract.assemble(
        draft: LocalSummaryDraft(title: "Local title", overview: "Local overview."),
        transcriptSha256: TranscriptHash.sha256(segments: segments),
        provenance: OmiAPI.ProjectionProvenance(
          deviceClass: "macos",
          generatedAt: "2024-01-01T20:14:00Z",
          modelId: "local-server",
          runtime: runtime
        ),
        fallbackTitle: "Recording"
      )
      return try ClientProcessingContract.stored(projection)
    }
  }

  private final class FixtureSummarizer: ConversationSummarizing, @unchecked Sendable {
    private let lock = NSLock()
    private let stored: StoredClientProjection?
    private var _summarizeCalls = 0
    private var _peekCalls = 0

    var summarizeCalls: Int {
      lock.lock()
      defer { lock.unlock() }
      return _summarizeCalls
    }

    var peekCalls: Int {
      lock.lock()
      defer { lock.unlock() }
      return _peekCalls
    }

    init(stored: StoredClientProjection?) {
      self.stored = stored
    }

    func summarize(
      sessionId _: Int64,
      segments _: [TranscriptHash.Segment],
      startedAt _: Date
    ) async throws -> StoredClientProjection {
      lock.withLock { _summarizeCalls += 1 }
      guard let stored else {
        throw TranscriptionStorageError.sessionNotFound
      }
      return stored
    }

    func peekStored(sessionId _: Int64) async throws -> StoredClientProjection? {
      lock.withLock { _peekCalls += 1 }
      return stored
    }
  }

  private struct ThrowingSummarizer: ConversationSummarizing {
    func summarize(
      sessionId _: Int64,
      segments _: [TranscriptHash.Segment],
      startedAt _: Date
    ) async throws -> StoredClientProjection {
      throw TranscriptionStorageError.sessionNotFound
    }

    func peekStored(sessionId _: Int64) async throws -> StoredClientProjection? {
      throw TranscriptionStorageError.sessionNotFound
    }
  }
#endif
