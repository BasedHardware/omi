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

}
