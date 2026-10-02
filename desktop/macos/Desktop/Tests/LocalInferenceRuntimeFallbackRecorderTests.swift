import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: resetForTests is a DEBUG-only diagnostic seam.
  final class LocalInferenceRuntimeFallbackRecorderTests: XCTestCase {
    override func setUp() {
      super.setUp()
      DesktopDiagnosticsManager.shared.resetForTests()
    }

    override func tearDown() {
      DesktopDiagnosticsManager.shared.resetForTests()
      super.tearDown()
    }

    // red-proof: pass arbitrary from/to strings directly to recordFallback
    func testRecorderEmitsOneBoundedSharedEventPerFallback() throws {
      let recorder = DesktopLocalInferenceFallbackRecorder()
      let cases: [(String, String, String, DesktopFallbackOutcome)] = [
        ("afm", "deterministic_minimum", "config_incomplete", .exhausted),
        ("local-server", "local-server", "engine_failed", .recovered),
        ("none", "deterministic_minimum", "dispatch_disabled", .exhausted),
        ("private transcript", "private prompt", "free-form error", .degraded),
      ]
      for (from, to, reason, outcome) in cases {
        recorder.recordLocalInferenceFallback(from: from, to: to, reason: reason, outcome: outcome)
      }
      let snapshots = DesktopDiagnosticsManager.shared.currentSnapshotsForSentry()
      XCTAssertEqual(snapshots.count, cases.count, "one shared health event per fallback")
      for (index, snapshot) in snapshots.enumerated() {
        let expected = cases[index]
        XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered")
        XCTAssertEqual(snapshot["area"] as? String, "local_llm")
        XCTAssertEqual(snapshot["from"] as? String, index == 3 ? "other" : expected.0)
        XCTAssertEqual(snapshot["to"] as? String, index == 3 ? "other" : expected.1)
        XCTAssertEqual(snapshot["reason"] as? String, index == 3 ? "other" : expected.2)
        XCTAssertEqual(snapshot["outcome"] as? String, expected.3.rawValue)
        XCTAssertNil(snapshot["prompt"])
        XCTAssertNil(snapshot["transcript"])
      }
    }
  }
#endif
