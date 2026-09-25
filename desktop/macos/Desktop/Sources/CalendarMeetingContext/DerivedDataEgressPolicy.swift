import Foundation

/// The complete policy for data derived from local context/proactivity state.
///
/// This is deliberately default-deny: a new `DerivedDataClass` has no egress until
/// its declaration is changed here and a named route is registered below. Today the
/// sole exception is minimal meeting identity used by server-side summarization.
enum DerivedDataClass: String, CaseIterable, Sendable {
  case meetingIdentity = "meeting_identity"
  case contextBucketFacts = "context_bucket_facts"
  case contextBucketNarratives = "context_bucket_narratives"
  case contextBucketEntries = "context_bucket_entries"
  case proactiveNotificationDerivation = "proactive_notification_derivation"
}

enum DerivedDataEgressRoute: String, CaseIterable, Sendable {
  case calendarMeetings = "POST /v1/calendar/meetings"
}

struct DerivedDataEgressRequest: Equatable, Sendable {
  let dataClass: DerivedDataClass
  let route: DerivedDataEgressRoute
  let purpose: String
}

enum DerivedDataEgressDecision: Equatable, Sendable {
  case allow(purpose: String)
  case deny(reason: String)
}

enum DerivedDataEgressPolicyError: Error, Equatable {
  case denied(DerivedDataClass)
  case undeclaredRoute(DerivedDataClass, DerivedDataEgressRoute)
  case purposeMismatch(DerivedDataClass)
}

enum DerivedDataEgressPolicy {
  static let meetingIdentityPurpose = "server-side conversation summarization"

  /// Human-readable declarations. Missing entries are denied by `decision(for:)`.
  static let declarations: [DerivedDataClass: DerivedDataEgressDecision] = [
    .meetingIdentity: .allow(purpose: meetingIdentityPurpose),
    .contextBucketFacts: .deny(reason: "proactive-notification derivation stays on-device"),
    .contextBucketNarratives: .deny(reason: "proactive-notification derivation stays on-device"),
    .contextBucketEntries: .deny(reason: "proactive-notification derivation stays on-device"),
    .proactiveNotificationDerivation: .deny(reason: "proactive notifications are computed and consumed on-device"),
  ]

  /// Every production transport for derived data must be named here. CI asserts
  /// that no registered route belongs to a denied class.
  static let declaredRoutes: [DerivedDataEgressRequest] = [
    DerivedDataEgressRequest(
      dataClass: .meetingIdentity,
      route: .calendarMeetings,
      purpose: meetingIdentityPurpose)
  ]

  static func decision(for dataClass: DerivedDataClass) -> DerivedDataEgressDecision {
    declarations[dataClass] ?? .deny(reason: "no egress declaration")
  }

  static func authorize(_ request: DerivedDataEgressRequest) throws {
    guard case .allow(let declaredPurpose) = decision(for: request.dataClass) else {
      throw DerivedDataEgressPolicyError.denied(request.dataClass)
    }
    guard declaredRoutes.contains(request) else {
      throw DerivedDataEgressPolicyError.undeclaredRoute(request.dataClass, request.route)
    }
    guard request.purpose == declaredPurpose else {
      throw DerivedDataEgressPolicyError.purposeMismatch(request.dataClass)
    }
  }
}
