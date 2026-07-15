import XCTest

@testable import Omi_Computer

final class ChatFirstAnalyticsTests: XCTestCase {
  func testEveryChatFirstEventMapsToAnExactBoundedSchema() {
    let cases: [(ChatFirstAnalyticsEvent, String, Set<String>)] = [
      (
        .routeEntered(route: .goals, origin: .chatDeeplink),
        "chat_first_route_entered",
        ["route", "origin", "telemetry_schema_version"]
      ),
      (
        .richBlock(kind: .goalLink, outcome: .acted, action: .open),
        "chat_first_rich_block",
        ["kind", "outcome", "action", "telemetry_schema_version"]
      ),
      (
        .question(lifecycle: .answered),
        "chat_first_question",
        ["lifecycle", "telemetry_schema_version"]
      ),
      (
        .taskMutation(lifecycle: .rollback, mutation: .schedule),
        "chat_first_task_mutation",
        ["lifecycle", "mutation", "telemetry_schema_version"]
      ),
      (
        .capabilityResolution(
          outcome: .unavailable,
          generationBucket: .none,
          errorClass: .unavailable
        ),
        "chat_first_capability_resolution",
        ["outcome", "generation_bucket", "error_class", "telemetry_schema_version"]
      ),
    ]

    for (event, eventName, keys) in cases {
      let payload = event.analyticsPayload
      XCTAssertEqual(payload.eventName, eventName)
      XCTAssertEqual(Set(payload.properties.keys), keys)
      XCTAssertEqual(payload.properties["telemetry_schema_version"], "1")
    }
  }

  func testMapperCannotAcceptUnknownDimensionsOrFreeFormText() {
    // These enums are the only public event dimensions. A raw title, entity
    // ID, question answer, transcript, URL, or exception cannot become a
    // `ChatFirstAnalyticsEvent` and unknown wire values are rejected.
    XCTAssertNil(ChatFirstAnalyticsEvent.Route(rawValue: "private task title"))
    XCTAssertNil(ChatFirstAnalyticsEvent.RichBlockKind(rawValue: "https://omi.me/private"))
    XCTAssertNil(ChatFirstAnalyticsEvent.QuestionLifecycle(rawValue: "answer text"))
    XCTAssertNil(ChatFirstAnalyticsEvent.TaskMutation(rawValue: "task-123"))
    XCTAssertNil(ChatFirstAnalyticsEvent.CapabilityErrorClass(rawValue: "network timeout details"))

    let payload = ChatFirstAnalyticsEvent.richBlock(
      kind: .questionCard,
      outcome: .rejected,
      action: .select
    ).analyticsPayload
    let prohibitedKeys = [
      "id", "title", "text", "prompt", "answer", "suggestion", "url", "exception", "transcript", "memory",
    ]
    XCTAssertTrue(Set(payload.properties.keys).isDisjoint(with: prohibitedKeys))
  }

  func testChatFirstInteractionSurfacesUseAnalyticsManagerAsTheirOnlyTelemetryPath() throws {
    // omi-test-quality: source-inspection -- static contract: direct telemetry
    // calls could bypass the closed mapper without a runtime-observable result.
    let desktopDirectory = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let sources = [
      "Sources/MainWindow/ChatFirst/Blocks/ChatFirstContentBlockViews.swift",
      "Sources/MainWindow/ChatFirst/ChatFirstRoute.swift",
      "Sources/MainWindow/ChatFirst/ChatFirstShell.swift",
      "Sources/MainWindow/ChatFirst/ChatFirstTasksPage.swift",
      "Sources/MainWindow/Components/ChatBubble.swift",
      "Sources/MainWindow/DesktopHomeView.swift",
    ]

    for path in sources {
      let source = try String(contentsOf: desktopDirectory.appendingPathComponent(path), encoding: .utf8)
      XCTAssertFalse(source.contains("PostHogManager.shared.track"), "\(path) bypasses AnalyticsManager")
      XCTAssertFalse(source.contains("PostHogManager.shared.capture"), "\(path) bypasses AnalyticsManager")
    }
  }

  func testCapabilityGenerationIsBucketedAndTaskResultHasNoTransportDimension() {
    XCTAssertEqual(ChatFirstAnalyticsEvent.CapabilityGenerationBucket.bucket(for: nil), .none)
    XCTAssertEqual(ChatFirstAnalyticsEvent.CapabilityGenerationBucket.bucket(for: 0), .zeroToNine)
    XCTAssertEqual(ChatFirstAnalyticsEvent.CapabilityGenerationBucket.bucket(for: 19), .tenToNinetyNine)
    XCTAssertEqual(ChatFirstAnalyticsEvent.CapabilityGenerationBucket.bucket(for: 100), .hundredPlus)

    XCTAssertEqual(
      ChatFirstTaskMutationTelemetry.terminalLifecycle(for: .updated),
      .success
    )
    XCTAssertEqual(
      ChatFirstTaskMutationTelemetry.terminalLifecycle(for: .rolledBackAfterRemoteFailure),
      .rollback
    )
    XCTAssertEqual(
      ChatFirstTaskMutationTelemetry.terminalLifecycle(for: .ownerChanged),
      .rollback
    )
  }

  func testNonProductionFixtureContractUsesOnlyDeterministicShapeFacts() {
    let interactive = ChatFirstAutomationFixture.contract(for: .interactiveQuestion)
    XCTAssertEqual(interactive.validRichBlockCount, 1)
    XCTAssertTrue(interactive.hasValidQuestion)
    XCTAssertTrue(interactive.hasPreparedAnswer)
    XCTAssertEqual(interactive.proactiveJudgeCalls, 0)
    XCTAssertEqual(interactive.materializationCount, 0)
    XCTAssertEqual(interactive.rawManifestProofMode, "external_raw_bytes_digest")
    XCTAssertEqual(interactive.shellVariant, "chatFirst")
    XCTAssertEqual(interactive.chatFirstToolCount, 2)

    let deferred = ChatFirstAutomationFixture.contract(for: .deferredQuestion)
    XCTAssertEqual(deferred.deferralSeconds, 86_400)
    XCTAssertEqual(deferred.fakeClockEpochSeconds, interactive.fakeClockEpochSeconds)

    let capture = ChatFirstAutomationFixture.contract(for: .mixedCapture)
    XCTAssertEqual(capture.captureSourceMode, "mixed")
    XCTAssertFalse(capture.hasPreparedAnswer)
    XCTAssertTrue(
      Set(capture.bridgeDetail.keys).isDisjoint(with: ["text", "answer", "title", "id", "transcript", "url", "error"])
    )

    for scenario in [ChatFirstAutomationFixture.Scenario.uiFlagOff, .outOfCohort] {
      let disabled = ChatFirstAutomationFixture.contract(for: scenario)
      XCTAssertEqual(disabled.shellVariant, "legacy")
      XCTAssertEqual(disabled.chatFirstToolCount, 0)
      XCTAssertEqual(disabled.validRichBlockCount, 0)
      XCTAssertEqual(disabled.materializationCount, 0)
      XCTAssertEqual(disabled.proactiveJudgeCalls, 0)
      XCTAssertEqual(disabled.proactiveEmissions, 0)
    }
  }

  @MainActor
  func testFixtureBridgeActionIsDiscoverableWithoutContentParameters() {
    let registry = DesktopAutomationActionRegistry.shared
    registry.registerBuiltins()
    let descriptor = registry.descriptors().first { $0.name == "chat_first_fixture_contract" }

    guard AppBuild.isNonProduction else {
      XCTAssertNil(descriptor)
      return
    }
    XCTAssertEqual(descriptor?.params, ["scenario"])
    XCTAssertEqual(descriptor?.category, "read")
    XCTAssertEqual(descriptor?.safety, "read_only")
    XCTAssertEqual(descriptor?.sideEffects, [])
  }
}
