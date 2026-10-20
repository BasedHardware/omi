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
    localRoute: LocalEmbeddingRuntime.Selection, killSwitches: LocalEmbeddingKillSwitches,
    desktopGrandfatherUntil: TimeInterval? = nil, now: Date = Date()
  ) {
    switch plan {
    case nil, .unknown?: planClass = .unknown
    default: planClass = plan?.hasPaidCapability == true && status == .active ? .paid : .free
    }
    // TODO(#21488 follow-up): consume server cloud_screen_vectors when the
    // subscription wire exposes it. Plus screen context is Pro-only in ladder v1.
    // Neo retains vectors only through its server-reported grandfather deadline.
    // Mobile-only Unlimited-v2 and unknown plans do not grant screen vectors.
    switch plan {
    case .operator?, .pro?, .architect?:
      shouldEmbedWithGemini = status == .active
    case .unlimited?:
      shouldEmbedWithGemini = status == .active && (desktopGrandfatherUntil ?? 0) > now.timeIntervalSince1970
    default:
      shouldEmbedWithGemini = false
    }
    if killSwitches.isDisabled {
      shouldIndexLocally = false
      searchRoute = shouldEmbedWithGemini ? .gemini : .ftsOnly
      reason = .hardKill
    } else if killSwitches.isEnabled, case .engine = localRoute {
      shouldIndexLocally = true
      searchRoute = .local
      reason = .localAvailable
    } else {
      shouldIndexLocally = false
      searchRoute = shouldEmbedWithGemini ? .gemini : .ftsOnly
      reason = killSwitches.isEnabled ? .localUnavailable : .localOptOut
    }
  }

  /// A synchronous peek schedules bounded refresh on expiry; persisted UI plan hints cannot spend.
  static func cached(
    localRoute: LocalEmbeddingRuntime.Selection = .none,
    killSwitches: LocalEmbeddingKillSwitches? = nil,
    defaults: UserDefaults = .standard,
    entitlementService: ScreenCloudEntitlementService = .shared
  ) -> Self {
    let response = entitlementService.peek()
    return Self(
      plan: response?.subscription.plan, status: response?.subscription.status, localRoute: localRoute,
      killSwitches: killSwitches ?? .resolve(defaults: defaults),
      desktopGrandfatherUntil: response?.desktopGrandfatherUntil.map(Double.init))
  }

  /// One route counter through the existing local-inference fallback telemetry.
  /// The discriminator and dimensions are bounded; no frame or query content is accepted.
  /// Emission is process-bounded to decision changes only.
  func recordRoute() {
    guard ScreenEmbeddingRouteRecorder.shared.shouldRecord(self) else { return }
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

/// Process-held last decision. No periodic telemetry and no content-bearing fields.
final class ScreenEmbeddingRouteRecorder: @unchecked Sendable {
  static let shared = ScreenEmbeddingRouteRecorder()
  private let lock = NSLock()
  private var last: ScreenEmbeddingPolicy?

  func shouldRecord(_ policy: ScreenEmbeddingPolicy) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    guard last != policy else { return false }
    last = policy
    return true
  }
}
