import XCTest

@testable import Omi_Computer

/// Behavioral contract for the macOS integration-connect telemetry that closes
/// the connect-funnel observability gap. Mirrors the
/// `MemoryAssistantTelemetryTests` allowlist pattern: every test asserts the
/// closed schema and that no content/credential can reach PostHog — not just
/// literal event strings. The capture seam lives on `AnalyticsManager`'s
/// main-actor boundary, so behavioral cases observe the real event and exact
/// payload without a mutable unsafe global and without PostHog network
/// (`PostHogManager.track` early-returns when the SDK is uninitialized).
@MainActor
final class IntegrationConnectTelemetryTests: XCTestCase {
  private typealias CapturedEvent = (name: String, properties: [String: Any])
  private var captured: [CapturedEvent] = []

  override func setUp() async throws {
    captured = []
    AnalyticsManager.shared.setIntegrationConnectTelemetryCaptureForTests { [weak self] name, properties in
      self?.captured.append((name, properties))
    }
  }

  override func tearDown() async throws {
    AnalyticsManager.shared.setIntegrationConnectTelemetryCaptureForTests(nil)
    captured = []
  }

  // MARK: - Closed schema

  func testAttemptedPayloadHasKeysetExactlyAllowList() {
    let payload = IntegrationConnectTelemetry.attemptedPayload(
      integrationName: "Google Calendar", connectorID: "calendar",
      surface: .apps, stage: "import")
    XCTAssertEqual(
      Set(payload.keys),
      ["integration_name", "connector_id", "surface", "stage"])
    XCTAssertEqual(payload["integration_name"] as? String, "Google Calendar")
    XCTAssertEqual(payload["surface"] as? String, "apps")
  }

  func testSucceededPayloadHasKeysetExactlyAllowListWithAndWithoutBuckets() {
    let withBuckets = IntegrationConnectTelemetry.succeededPayload(
      integrationName: "Gmail", connectorID: "email", surface: .apps, stage: "import",
      durationMs: 4_000, sourceCount: 42, memoryCount: 7, wasFirstSync: true)
    XCTAssertEqual(
      Set(withBuckets.keys),
      [
        "integration_name", "connector_id", "surface", "stage", "duration_bucket",
        "source_count_bucket", "memory_count_bucket", "was_first_sync",
      ])
    XCTAssertEqual(withBuckets["duration_bucket"] as? String, "3_10s")
    XCTAssertEqual(withBuckets["source_count_bucket"] as? String, "11_50")
    XCTAssertEqual(withBuckets["was_first_sync"] as? Bool, true)

    let withoutBuckets = IntegrationConnectTelemetry.succeededPayload(
      integrationName: "Gmail", connectorID: "email", surface: .onboarding, stage: "verify")
    XCTAssertEqual(
      Set(withoutBuckets.keys),
      ["integration_name", "connector_id", "surface", "stage", "was_first_sync"])
    XCTAssertNil(withoutBuckets["duration_bucket"])
  }

  func testFailedPayloadHasKeysetExactlyAllowListAndCarriesReconnectRequired() {
    let payload = IntegrationConnectTelemetry.failedPayload(
      integrationName: "Google Calendar", connectorID: "calendar", surface: .apps, stage: "import",
      errorClass: .notSignedIn, durationMs: 500)
    XCTAssertEqual(
      Set(payload.keys),
      [
        "integration_name", "connector_id", "surface", "stage", "error_class",
        "reconnect_required", "was_first_sync", "duration_bucket",
      ])
    XCTAssertEqual(payload["error_class"] as? String, "not_signed_in")
    XCTAssertEqual(payload["reconnect_required"] as? Bool, true)
  }

  // MARK: - Privacy: no content/credential can leak

  func testPayloadsCannotLeakSensitiveDataEvenWithAdversarialInputs() {
    // An adversarial caller cannot thread content through the bounded builders:
    // only declared keys survive the allow-list filter, and the only string
    // inputs are bounded identifiers.
    let payload = IntegrationConnectTelemetry.failedPayload(
      integrationName: "Gmail", connectorID: "email", surface: .apps, stage: "import",
      errorClass: .network)
    let serialized = String(describing: payload)
    let forbidden = [
      "token", "cookie", "account_id", "password", "secret", "url", "query",
      "path", "profile", "error_message", "localized_description", "duration_ms",
      "summary", "snippet", "subject", "from", "attendee",
    ]
    for term in forbidden {
      XCTAssertFalse(
        serialized.lowercased().contains(term),
        "payload leaked forbidden term '\(term)': \(serialized)")
    }
    XCTAssertFalse(Set(payload.keys).contains("error"))
  }

  func testContextDimsAreNotInPayload() {
    // platform/app_version/app_build/update_channel ride PostHog
    // super-properties; they must NOT be re-added per-event.
    let attempted = IntegrationConnectTelemetry.attemptedPayload(
      integrationName: "X", connectorID: "x", surface: .apps, stage: "import")
    let failed = IntegrationConnectTelemetry.failedPayload(
      integrationName: "X", connectorID: "x", surface: .apps, stage: "import",
      errorClass: .unknown)
    for payload in [attempted, failed] {
      let contextKeys: Set<String> = [
        "platform", "app_version", "app_build", "update_channel",
      ]
      XCTAssertTrue(Set(payload.keys).isDisjoint(with: contextKeys))
    }
  }

  // MARK: - Closed-set predicates

  func testDurationBucketClampsAndProducesClosedRanges() {
    XCTAssertEqual(IntegrationConnectTelemetry.durationBucket(-500), "0_1s")
    XCTAssertEqual(IntegrationConnectTelemetry.durationBucket(0), "0_1s")
    XCTAssertEqual(IntegrationConnectTelemetry.durationBucket(999), "0_1s")
    XCTAssertEqual(IntegrationConnectTelemetry.durationBucket(1_000), "1_3s")
    XCTAssertEqual(IntegrationConnectTelemetry.durationBucket(2_999), "1_3s")
    XCTAssertEqual(IntegrationConnectTelemetry.durationBucket(3_000), "3_10s")
    XCTAssertEqual(IntegrationConnectTelemetry.durationBucket(10_000), "10_30s")
    XCTAssertEqual(IntegrationConnectTelemetry.durationBucket(29_999), "10_30s")
    XCTAssertEqual(IntegrationConnectTelemetry.durationBucket(30_000), "30_60s")
    XCTAssertEqual(IntegrationConnectTelemetry.durationBucket(59_999), "30_60s")
    XCTAssertEqual(IntegrationConnectTelemetry.durationBucket(60_000), "60s_plus")
  }

  func testCountBucketClampsAndProducesClosedRanges() {
    XCTAssertEqual(IntegrationConnectTelemetry.countBucket(-3), "0")
    XCTAssertEqual(IntegrationConnectTelemetry.countBucket(0), "0")
    XCTAssertEqual(IntegrationConnectTelemetry.countBucket(1), "1_10")
    XCTAssertEqual(IntegrationConnectTelemetry.countBucket(10), "1_10")
    XCTAssertEqual(IntegrationConnectTelemetry.countBucket(11), "11_50")
    XCTAssertEqual(IntegrationConnectTelemetry.countBucket(200), "51_200")
    XCTAssertEqual(IntegrationConnectTelemetry.countBucket(201), "201_500")
    XCTAssertEqual(IntegrationConnectTelemetry.countBucket(500), "201_500")
    XCTAssertEqual(IntegrationConnectTelemetry.countBucket(501), "500_plus")
  }

  func testFailureRequiresReconnectIsTrueOnlyForReauthClasses() {
    let reconnect: Set<IntegrationConnectTelemetry.ErrorClass> = [
      .notSignedIn, .sessionExpired, .noBrowser, .decryptFailed, .authentication,
    ]
    for errorClass in IntegrationConnectTelemetry.ErrorClass.allCases {
      let expected = reconnect.contains(errorClass)
      XCTAssertEqual(
        IntegrationConnectTelemetry.failureRequiresReconnect(errorClass), expected,
        "\(errorClass.rawValue) reconnect classification mismatch")
    }
  }

  func testConnectorNativeFailureEnumsMapIntoClosedErrorClass() {
    // The connector-native taxonomies are the precise source; they must map
    // 1:1 into the closed macOS ErrorClass vocabulary.
    XCTAssertEqual(IntegrationConnectTelemetry.ErrorClass(GmailFailureClass.notSignedIn), .notSignedIn)
    XCTAssertEqual(IntegrationConnectTelemetry.ErrorClass(GmailFailureClass.sessionExpired), .sessionExpired)
    XCTAssertEqual(IntegrationConnectTelemetry.ErrorClass(CalendarFailureClass.configuration), .configuration)
    XCTAssertEqual(IntegrationConnectTelemetry.ErrorClass(CalendarFailureClass.network), .network)
  }

  /// `nudge` joined the set when proactive integration nudges shipped: a
  /// nudge-sourced connect must be separable from an Apps-tab connect, or the
  /// nudge's conversion cannot be measured against the tab it competes with.
  /// The guard is unchanged in kind — the set is still closed and exact.
  func testSurfaceEnumIsClosedSet() {
    XCTAssertEqual(
      Set(IntegrationConnectTelemetry.Surface.allCases.map(\.rawValue)),
      ["apps", "onboarding", "nudge"])
  }

  func testNoContentFailureClassIsNotReconnectRequired() {
    // A memory-log parse that produced nothing durable is NOT a connect
    // failure: it must carry the distinct `no_content` class and never read as
    // reconnect-required, so analysts can exclude it from the failure rate.
    XCTAssertFalse(IntegrationConnectTelemetry.failureRequiresReconnect(.noContent))
    let payload = IntegrationConnectTelemetry.failedPayload(
      integrationName: "ChatGPT", connectorID: "chatgpt", surface: .apps, stage: "import",
      errorClass: .noContent)
    XCTAssertEqual(payload["error_class"] as? String, "no_content")
    XCTAssertEqual(payload["reconnect_required"] as? Bool, false)
  }

  func testMemoryLogNoDurableMemoriesCarriesNoContentClass() {
    // Drives the real production mapping: a memory-log import that parsed but
    // found nothing durable surfaces UI guidance as a failure but threads the
    // bounded `no_content` class (not the generic `unknown` fallback the runner
    // would otherwise derive from the message). Combined with
    // testRunnerEmitsFailedWithThreadedNativeFailureClass this proves the
    // end-to-end Failed/no_content/no-reconnect telemetry for memory-logs.
    let outcome = ConnectorImportOperations.memoryLogOutcome(.noDurableMemories, source: .chatgpt)
    guard case .failure(_, let failureClass) = outcome else {
      return XCTFail("expected failure for no-durable-memories, got \(outcome)")
    }
    XCTAssertEqual(failureClass, .noContent)
  }
  func testProductionConnectorIDsMapToCleanBoundedNames() {
    // The privacy boundary for `integration_name` VALUES is call-site
    // discipline: production connectorIDs come from a closed set and map to a
    // closed set of display names. No id may map to a value carrying a
    // sensitive token.
    let productionIDs = [
      "calendar", "email", "gmail", "apple-notes", "applenotes",
      "local-files", "files", "x", "chatgpt", "claude",
    ]
    let forbidden = ["token", "cookie", "account", "secret", "password", "url", "path"]
    for id in productionIDs {
      let name = IntegrationConnectTelemetry.integrationName(forConnectorID: id)
      for term in forbidden {
        XCTAssertFalse(
          name.lowercased().contains(term),
          "integration name for '\(id)' carries forbidden term '\(term)': \(name)")
      }
    }
  }

  // MARK: - Behavioral: the real ConnectorImportRunner boundary

  func testRunnerEmitsAttemptedThenSucceededThroughTheFacade() async {
    let runner = ConnectorImportRunner()
    let task = runner.start(
      connectorID: "calendar",
      progressTitle: "Importing",
      progressDetail: "Calendar"
    ) { _ in
      .success(
        message: "done",
        metrics: ConnectorImportRunner.RunMetrics(
          sourceCount: 120, memoryCount: 9, wasFirstSync: true))
    }

    await task?.value

    XCTAssertEqual(captured.count, 2)
    XCTAssertEqual(captured[0].name, "Integration Connect Attempted")
    XCTAssertEqual(captured[0].properties["integration_name"] as? String, "Google Calendar")
    XCTAssertEqual(captured[0].properties["surface"] as? String, "apps")
    XCTAssertEqual(captured[0].properties["stage"] as? String, "import")

    XCTAssertEqual(captured[1].name, "Integration Connect Succeeded")
    XCTAssertEqual(captured[1].properties["integration_name"] as? String, "Google Calendar")
    XCTAssertEqual(captured[1].properties["source_count_bucket"] as? String, "51_200")
    XCTAssertEqual(captured[1].properties["memory_count_bucket"] as? String, "1_10")
    XCTAssertEqual(captured[1].properties["was_first_sync"] as? Bool, true)
    XCTAssertNotNil(captured[1].properties["duration_bucket"])
  }

  func testRunnerEmitsFailedWithThreadedNativeFailureClass() async {
    let runner = ConnectorImportRunner()
    let task = runner.start(
      connectorID: "email",
      progressTitle: "Importing",
      progressDetail: "Gmail"
    ) { _ in
      .failure(
        message: "Sign into Gmail in your browser.",
        metrics: ConnectorImportRunner.RunMetrics(
          failureClass: .notSignedIn, wasFirstSync: true))
    }

    await task?.value

    XCTAssertEqual(captured.count, 2)
    XCTAssertEqual(captured[1].name, "Integration Connect Failed")
    XCTAssertEqual(captured[1].properties["error_class"] as? String, "not_signed_in")
    XCTAssertEqual(captured[1].properties["reconnect_required"] as? Bool, true)
    XCTAssertEqual(captured[1].properties["was_first_sync"] as? Bool, true)
    // The user-facing message must NOT appear in the payload.
    XCTAssertFalse(
      String(describing: captured[1].properties).contains("Sign into Gmail"))
  }

  func testRunnerFallsBackToDiagnosticErrorClassWhenNoNativeClass() async {
    let runner = ConnectorImportRunner()
    let task = runner.start(
      connectorID: "x",
      progressTitle: "Connecting",
      progressDetail: "X"
    ) { _ in
      // No native failure class threaded (e.g. X/local-files/memory-log): the
      // runner must derive a bounded class from the message via the shared
      // sanitizer rather than emitting raw text.
      .failure(message: "The operation timed out.", metrics: ConnectorImportRunner.RunMetrics())
    }

    await task?.value

    XCTAssertEqual(captured[1].name, "Integration Connect Failed")
    XCTAssertEqual(captured[1].properties["error_class"] as? String, "timeout")
    XCTAssertEqual(captured[1].properties["reconnect_required"] as? Bool, false)
  }

  func testDeduplicatedStartEmitsAtMostOneAttempted() async {
    let runner = ConnectorImportRunner()
    let release = Gate()
    let first = runner.start(
      connectorID: "calendar",
      progressTitle: "Importing",
      progressDetail: "Calendar"
    ) { _ in
      await release.wait()
      return .success(message: "done")
    }
    // A second start while the first is in flight is ignored — it must NOT
    // emit a second Attempted (no inflated funnel numerator).
    let second = runner.start(
      connectorID: "calendar",
      progressTitle: "Importing",
      progressDetail: "Calendar"
    ) { _ in .success(message: "second") }

    XCTAssertNil(second)
    await release.signal()
    await first?.value

    let attempted = captured.filter { $0.name == "Integration Connect Attempted" }
    XCTAssertEqual(attempted.count, 1)
  }

  // MARK: - Behavioral: onboarding uses the shared import terminal

  func testOnboardingImportRetainsItsSurfaceAtAttemptAndSuccess() async {
    let runner = ConnectorImportRunner()
    let task = runner.start(
      connectorID: "calendar",
      progressTitle: "Connecting",
      progressDetail: "Calendar",
      surface: .onboarding
    ) { _ in
      .success(message: "done")
    }

    await task?.value

    XCTAssertEqual(captured.map(\.name), ["Integration Connect Attempted", "Integration Connect Succeeded"])
    XCTAssertEqual(captured[0].properties["surface"] as? String, "onboarding")
    XCTAssertEqual(captured[0].properties["stage"] as? String, "import")
    XCTAssertEqual(captured[1].properties["surface"] as? String, "onboarding")
    XCTAssertEqual(captured[1].properties["stage"] as? String, "import")
  }

  func testOnboardingImportFailureRetainsReconnectClassification() async {
    let runner = ConnectorImportRunner()
    let task = runner.start(
      connectorID: "email",
      progressTitle: "Connecting",
      progressDetail: "Gmail",
      surface: .onboarding
    ) { _ in
      .failure(
        message: "Sign in",
        metrics: ConnectorImportRunner.RunMetrics(failureClass: .notSignedIn)
      )
    }

    await task?.value

    XCTAssertEqual(captured[1].name, "Integration Connect Failed")
    XCTAssertEqual(captured[1].properties["surface"] as? String, "onboarding")
    XCTAssertEqual(captured[1].properties["error_class"] as? String, "not_signed_in")
    XCTAssertEqual(captured[1].properties["reconnect_required"] as? Bool, true)
  }
}

/// Minimal async gate for deterministic in-flight dedup tests — mirrors the
/// `Gate` actor in `ConnectorImportRunnerTests`. No sleeps, no wall-clock.
private actor Gate {
  private var isOpen = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func wait() async {
    if isOpen { return }
    await withCheckedContinuation { continuation in
      waiters.append(continuation)
    }
  }

  func signal() {
    isOpen = true
    let toResume = waiters
    waiters.removeAll()
    for continuation in toResume {
      continuation.resume()
    }
  }
}
