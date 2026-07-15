import Foundation

/// Closed, content-free analytics schema for the cohort-only Chat-first
/// experience. The associated values are all finite enums or bounded numeric
/// buckets: callers cannot put titles, entity IDs, question answers, URLs,
/// prompts, transcripts, or raw errors into a payload.
enum ChatFirstAnalyticsEvent: Equatable, Sendable {
  enum Route: String, CaseIterable, Sendable {
    case chat
    case conversations
    case tasks
    case goals
    case memories
    case more
  }

  enum RouteOrigin: String, CaseIterable, Sendable {
    case shellLaunch = "shell_launch"
    case sidebar
    case chatDeeplink = "chat_deeplink"
    case more
  }

  enum RichBlockKind: String, CaseIterable, Sendable {
    case taskCard = "task_card"
    case goalLink = "goal_link"
    case captureLink = "capture_link"
    case questionCard = "question_card"
  }

  enum RichBlockOutcome: String, CaseIterable, Sendable {
    case rendered
    case acted
    case stalePlaceholder = "stale_placeholder"
    case rejected
  }

  enum RichBlockAction: String, CaseIterable, Sendable {
    case none
    case open
    case toggle
    case select
  }

  enum QuestionLifecycle: String, CaseIterable, Sendable {
    case shown
    case answered
    case retiredUnseen = "retired_unseen"
    case deferred
  }

  enum TaskMutationLifecycle: String, CaseIterable, Sendable {
    case attempt
    case success
    case rollback
  }

  enum TaskMutation: String, CaseIterable, Sendable {
    case create
    case completion
    case rename
    case schedule
  }

  enum CapabilityOutcome: String, CaseIterable, Sendable {
    case enabled
    case disabled
    case unavailable
    case projectionRejected = "projection_rejected"
  }

  enum CapabilityGenerationBucket: String, CaseIterable, Sendable {
    case none
    case zeroToNine = "0_9"
    case tenToNinetyNine = "10_99"
    case hundredPlus = "100_plus"

    static func bucket(for generation: Int?) -> Self {
      guard let generation, generation >= 0 else { return .none }
      switch generation {
      case 0...9: return .zeroToNine
      case 10...99: return .tenToNinetyNine
      default: return .hundredPlus
      }
    }
  }

  enum CapabilityErrorClass: String, CaseIterable, Sendable {
    case none
    case unavailable
    case ownerChanged = "owner_changed"
    case invalidControl = "invalid_control"
    case projectionRejected = "projection_rejected"
  }

  case routeEntered(route: Route, origin: RouteOrigin)
  case richBlock(kind: RichBlockKind, outcome: RichBlockOutcome, action: RichBlockAction)
  case question(lifecycle: QuestionLifecycle)
  case taskMutation(lifecycle: TaskMutationLifecycle, mutation: TaskMutation)
  case capabilityResolution(
    outcome: CapabilityOutcome,
    generationBucket: CapabilityGenerationBucket,
    errorClass: CapabilityErrorClass
  )
}

/// The only map accepted by `AnalyticsManager` for Chat-first events. String
/// keys are private to this mapper and values come exclusively from the enums
/// above, so a UI cannot accidentally widen the event contract with free text.
struct ChatFirstAnalyticsPayload {
  let eventName: String
  let properties: [String: String]
}

extension ChatFirstAnalyticsEvent {
  var analyticsPayload: ChatFirstAnalyticsPayload {
    switch self {
    case .routeEntered(let route, let origin):
      return ChatFirstAnalyticsPayload(
        eventName: "chat_first_route_entered",
        properties: [
          "route": route.rawValue,
          "origin": origin.rawValue,
          "telemetry_schema_version": "1",
        ]
      )
    case .richBlock(let kind, let outcome, let action):
      return ChatFirstAnalyticsPayload(
        eventName: "chat_first_rich_block",
        properties: [
          "kind": kind.rawValue,
          "outcome": outcome.rawValue,
          "action": action.rawValue,
          "telemetry_schema_version": "1",
        ]
      )
    case .question(let lifecycle):
      return ChatFirstAnalyticsPayload(
        eventName: "chat_first_question",
        properties: [
          "lifecycle": lifecycle.rawValue,
          "telemetry_schema_version": "1",
        ]
      )
    case .taskMutation(let lifecycle, let mutation):
      return ChatFirstAnalyticsPayload(
        eventName: "chat_first_task_mutation",
        properties: [
          "lifecycle": lifecycle.rawValue,
          "mutation": mutation.rawValue,
          "telemetry_schema_version": "1",
        ]
      )
    case .capabilityResolution(let outcome, let generationBucket, let errorClass):
      return ChatFirstAnalyticsPayload(
        eventName: "chat_first_capability_resolution",
        properties: [
          "outcome": outcome.rawValue,
          "generation_bucket": generationBucket.rawValue,
          "error_class": errorClass.rawValue,
          "telemetry_schema_version": "1",
        ]
      )
    }
  }
}

/// Converts the existing owner-safe task result into the only terminal shape
/// Chat-first may record. It deliberately collapses transport and owner detail.
enum ChatFirstTaskMutationTelemetry {
  static func terminalLifecycle(
    for outcome: TasksStore.TaskUpdateOutcome
  ) -> ChatFirstAnalyticsEvent.TaskMutationLifecycle {
    switch outcome {
    case .updated:
      return .success
    case .preservedLocalAfterRemoteFailure,
      .rolledBackAfterRemoteFailure,
      .rollbackFailed,
      .localWriteFailed,
      .ownerChanged:
      return .rollback
    }
  }
}
