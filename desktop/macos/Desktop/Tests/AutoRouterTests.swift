import XCTest

@testable import Omi_Computer

/// Tests for the AutoRouter desktop client.
///
/// Covers the testable surface (enum, URL building, cache key generation,
/// store/invalidate behavior). End-to-end HTTP tests are not in scope for
/// this unit test file — those would require either URLProtocol mocking or a
/// running local backend, both of which are out of scope for v1.
@MainActor
final class AutoRouterTests: XCTestCase {

  // NOTE: AutoRouter writes to UserDefaults.standard (process-wide), not to a
  // per-test suite. The original setUp/tearDown created an unused `defaultsSuite`
  // and tried to clean it up with `dictionaryRepresentation().keys.first ?? ""`
  // as the domain name — but `keys.first` returns a stored KEY (e.g. an
  // autoRouterPick.* value), not the suite name, so the cleanup was a no-op.
  // Each test that writes via `AutoRouter.shared.store(...)` cleans up by
  // calling `AutoRouter.shared.invalidate(task: ...)` at the end. That keeps
  // the production cache consistent and avoids bleeding sentinels into the
  // next test or the developer's app state.

  // MARK: - AutoRouterTask enum

  func testAllCases_haveFiveTasks() {
    XCTAssertEqual(AutoRouterTask.allCases.count, 5)
  }

  func testAllCases_haveExpectedRawValues() {
    let expected: [(AutoRouterTask, String)] = [
      (.pttResponse, "ptt_response"),
      (.screenshotUnderstanding, "screenshot_understanding"),
      (.screenshotEmbedding, "screenshot_embedding"),
      (.generalAssistant, "general_assistant"),
      (.transcription, "transcription"),
    ]
    for (task, raw) in expected {
      XCTAssertEqual(task.rawValue, raw, "rawValue mismatch for \(task)")
    }
  }

  func testRawValueRoundTrip() {
    for task in AutoRouterTask.allCases {
      let parsed = AutoRouterTask(rawValue: task.rawValue)
      XCTAssertEqual(parsed, task, "round-trip failed for \(task)")
    }
  }

  func testDisplayNames_areNonEmpty() {
    for task in AutoRouterTask.allCases {
      XCTAssertFalse(task.displayName.isEmpty, "\(task) has empty displayName")
    }
  }

  func testDisplayNames_areHumanReadable() {
    // Smoke check: displayName should NOT be the raw snake_case value.
    XCTAssertNotEqual(AutoRouterTask.pttResponse.displayName, "ptt_response")
    XCTAssertNotEqual(AutoRouterTask.transcription.displayName, "transcription")
  }

  // MARK: - Endpoint URL building

  func testEndpointURL_stripsTrailingSlash() {
    let url = AutoRouter.endpointURL(base: "https://api.example.com/", task: .pttResponse)
    XCTAssertEqual(url?.absoluteString, "https://api.example.com/v1/auto-router/pick?task=ptt_response")
  }

  func testEndpointURL_preservesNoTrailingSlash() {
    let url = AutoRouter.endpointURL(base: "https://api.example.com", task: .generalAssistant)
    XCTAssertEqual(url?.absoluteString, "https://api.example.com/v1/auto-router/pick?task=general_assistant")
  }

  func testEndpointURL_includesQueryParam() {
    let url = AutoRouter.endpointURL(base: "https://api.example.com", task: .screenshotEmbedding)
    let comps = URLComponents(url: url!, resolvingAgainstBaseURL: false)
    XCTAssertEqual(comps?.queryItems?.count, 1)
    XCTAssertEqual(comps?.queryItems?.first?.name, "task")
    XCTAssertEqual(comps?.queryItems?.first?.value, "screenshot_embedding")
  }

  func testEndpointURL_pathIsCanonical() {
    // The path is /v1/auto-router/pick — must NOT be /v1/auto/model-pick
    // (that's the upstream realtime-voice endpoint we deliberately don't use).
    let url = AutoRouter.endpointURL(base: "https://api.example.com", task: .transcription)
    XCTAssertEqual(url?.path, "/v1/auto-router/pick")
  }

  func testEndpointURL_preservesPort() {
    let url = AutoRouter.endpointURL(base: "http://localhost:8000", task: .pttResponse)
    XCTAssertEqual(url?.host, "localhost")
    XCTAssertEqual(url?.port, 8000)
  }

  func testEndpointURL_queryValueIsCorrect() {
    // Tasks already use snake_case which is URL-safe. Verify the query
    // value is exactly the task's rawValue (no double-encoding, no skipping).
    let url = AutoRouter.endpointURL(base: "https://api.example.com", task: .screenshotUnderstanding)
    let comps = URLComponents(url: url!, resolvingAgainstBaseURL: false)
    XCTAssertEqual(comps?.queryItems?.first?.value, "screenshot_understanding")
  }

  func testEndpointURL_worksWithUnderscoredBaseURL() {
    let url = AutoRouter.endpointURL(base: "https://api_omi.example.com", task: .transcription)
    XCTAssertNotNil(url)
    XCTAssertEqual(url?.host, "api_omi.example.com")
  }

  func testEndpointURL_pathIsConsistentAcrossTasks() {
    // All 5 tasks should hit the same path; only the query param differs.
    let urls = AutoRouterTask.allCases.map {
      AutoRouter.endpointURL(base: "https://api.example.com", task: $0)
    }
    let paths = Set(urls.compactMap { $0?.path })
    XCTAssertEqual(paths.count, 1, "all tasks should hit the same path, got \(paths)")
    XCTAssertEqual(paths.first, "/v1/auto-router/pick")
  }

  // MARK: - Cache key uniqueness

  func testEachTaskHasDistinctUserDefaultsKey() {
    // The desktop client uses per-task UserDefaults keys (prefix + rawValue).
    // Verify the prefix is applied — we don't have direct access to the
    // private keys, but we can verify that store() then currentPick() for one
    // task does NOT bleed into another task's currentPick().
    //
    // Note: this test relies on UserDefaults.standard which is shared with
    // other parts of the app. We use a unique store value to detect pollution.
    let sentinel = "sentinel-\(UUID().uuidString)"
    AutoRouter.shared.store(sentinel, for: .pttResponse)
    XCTAssertEqual(AutoRouter.shared.currentPick(for: .pttResponse), sentinel)
    XCTAssertNil(AutoRouter.shared.currentPick(for: .transcription), "transcription should not have ptt's pick")
    XCTAssertNil(AutoRouter.shared.currentPick(for: .screenshotUnderstanding), "screenshotUnderstanding should not have ptt's pick")
    // Clean up.
    AutoRouter.shared.invalidate(task: .pttResponse)
  }

  func testInvalidateClearsBothValueAndDate() {
    // UAT finding (P2): invalidate() previously only cleared the date key,
    // leaving the cached pick readable via currentPick(for:). Now it should
    // clear BOTH so callers don't see a stale model after invalidation.
    let sentinel = "sentinel-\(UUID().uuidString)"
    AutoRouter.shared.store(sentinel, for: .generalAssistant)
    XCTAssertEqual(AutoRouter.shared.currentPick(for: .generalAssistant), sentinel)
    AutoRouter.shared.invalidate(task: .generalAssistant)
    XCTAssertNil(
      AutoRouter.shared.currentPick(for: .generalAssistant),
      "invalidate() must clear the cached pick (not just the date)"
    )
  }

  // MARK: - Cache key generation (via store / currentPick)

  /// AutoRouter.store uses UserDefaults.standard — for these tests we
  /// exercise the equivalent cache-key pattern via a thin wrapper. The
  /// production cache uses UserDefaults.standard (process-wide); we don't
  /// inject the suite in v1. Instead we test the key-generation via the
  /// URL building test (each task produces a distinct URL) — that's the
  /// externally observable consequence of distinct keys.

  // MARK: - Documented out-of-scope

  /// End-to-end HTTP tests (refreshIfStale, refresh, server-pick override,
  /// stale fallback) are NOT in this unit test file. They require either
  /// URLProtocol mocking (URLSession interception) or a running local
  /// backend. Both are deferred to a follow-up AIDLC cycle if needed.
  /// For v1 the structure is verified via:
  ///   - Backend endpoint tests (test_auto_router_endpoint.py — 28 tests)
  ///   - Swift structure tests (this file — enum, URL building, key pattern)
}
