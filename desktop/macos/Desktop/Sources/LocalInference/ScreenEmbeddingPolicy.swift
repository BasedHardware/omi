import Foundation

/// The screen-vector spend boundary. A missing entitlement never authorizes Gemini.
struct ScreenEmbeddingPolicy: Sendable, Equatable {
  enum PlanClass: String, Sendable { case free, paid, unknown }
  enum SearchRoute: String, Sendable {
    case gemini, local
    case ftsOnly = "fts_only"
  }
  enum Reason: String, Sendable {
    case hardKill = "dispatch_disabled"
    case localAvailable = "local_available"
    case localUnavailable = "local_engine_unavailable"
    case localOptOut = "local_opt_out"
  }

  let planClass: PlanClass
  let shouldEmbedWithGemini: Bool
  let shouldIndexLocally: Bool
  let searchRoute: SearchRoute
  let reason: Reason

  init(
    plan: SubscriptionPlanType?, status: SubscriptionStatusType?,
    localRoute: LocalEmbeddingRuntime.Selection, killSwitches: LocalEmbeddingKillSwitches
  ) {
    switch plan {
    case nil, .unknown?: planClass = .unknown
    default: planClass = plan?.hasPaidCapability == true && status == .active ? .paid : .free
    }
    shouldEmbedWithGemini = killSwitches.isDisabled || planClass == .paid
    if killSwitches.isDisabled {
      shouldIndexLocally = false
      searchRoute = .gemini
      reason = .hardKill
    } else if killSwitches.isEnabled, case .engine = localRoute {
      shouldIndexLocally = true
      searchRoute = .local
      reason = .localAvailable
    } else {
      shouldIndexLocally = false
      searchRoute = planClass == .paid ? .gemini : .ftsOnly
      reason = killSwitches.isEnabled ? .localUnavailable : .localOptOut
    }
  }

  /// FloatingBarUsageLimiter persists paid identities only for active subscriptions;
  /// inactive subscriptions are persisted as basic, and sign-out removes the key.
  /// Read synchronously, without initializing the limiter or making a network request.
  static func cached(
    localRoute: LocalEmbeddingRuntime.Selection = .none,
    killSwitches: LocalEmbeddingKillSwitches? = nil,
    defaults: UserDefaults = .standard
  ) -> Self {
    let plan = defaults.string(forKey: .floatingBarCachedPlan).map { SubscriptionPlanType(rawValue: $0) }
    return Self(
      plan: plan, status: plan == nil ? nil : .active, localRoute: localRoute,
      killSwitches: killSwitches ?? .resolve(defaults: defaults))
  }

  /// One route counter through the existing local-inference fallback telemetry.
  /// The discriminator and dimensions are bounded; no frame or query content is accepted.
  func recordRoute() {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "local_embeddings", from: "gemini", to: searchRoute.rawValue,
      reason: reason == .hardKill ? "dispatch_disabled" : "policy",
      outcome: searchRoute == .ftsOnly ? .degraded : .recovered,
      extra: [
        "route_event": "screen_embedding_route", "plan_class": planClass.rawValue,
        "route": reason == .hardKill ? "disabled" : searchRoute.rawValue,
        "route_reason": reason.rawValue,
      ])
  }
}
