import Foundation

/// Client UX decision for paid-or-BYOK managed proactivity.
///
/// Unknown / unavailable plan fails open so the server remains the invariant.
/// Identified `basic` without BYOK is the only locally gated case.
enum SubscriptionEntitlementDecision: Equatable, Sendable {
  case allowManagedProactivity
  case planGated
}

enum SubscriptionEntitlement {
  static let byokFeature = "byok"

  /// Plan authority is `GET /v1/users/me/subscription`, not `TierManager` and
  /// not the trial-paywall UserDefaults gate. `SubscriptionPlanType.hasPaidCapability`
  /// treats `.unknown` as unpaid; this decision deliberately does not.
  static func decision(
    plan: SubscriptionPlanType?,
    features: [String],
    isByokActive: Bool
  ) -> SubscriptionEntitlementDecision {
    if isByokActive || hasByokFeature(features) {
      return .allowManagedProactivity
    }
    guard let plan else {
      return .allowManagedProactivity
    }
    switch plan {
    case .basic:
      return .planGated
    case .unknown, .plus, .unlimited, .unlimitedV2, .architect, .pro, .operator:
      return .allowManagedProactivity
    }
  }

  static func hasByokFeature(_ features: [String]) -> Bool {
    features.contains { $0.caseInsensitiveCompare(byokFeature) == .orderedSame }
  }
}

/// Cached snapshot of `/v1/users/me/subscription` for S13 / S11.
///
/// Refresh on TTL and on auth/owner change. Fetch failure is unknown plan
/// (allow; server decides). BYOK is re-read on every decision so a key change
/// does not wait for the subscription TTL.
actor SubscriptionEntitlementService {
  static let shared = SubscriptionEntitlementService()

  static let defaultTTL: TimeInterval = 5 * 60

  private var cached: (response: UserSubscriptionResponse, expiresAt: Date)?
  private var inflight: Task<UserSubscriptionResponse?, Never>?
  private var observers: [NSObjectProtocol] = []

  var ttl: TimeInterval
  var now: @Sendable () -> Date
  var fetchSubscription: @Sendable () async throws -> UserSubscriptionResponse
  var isByokActive: @Sendable () -> Bool

  init(
    ttl: TimeInterval = SubscriptionEntitlementService.defaultTTL,
    observeAuthChanges: Bool = true,
    now: @escaping @Sendable () -> Date = { Date() },
    fetchSubscription: @escaping @Sendable () async throws -> UserSubscriptionResponse = {
      try await APIClient.shared.getUserSubscription()
    },
    isByokActive: @escaping @Sendable () -> Bool = { APIKeyService.isByokActive }
  ) {
    self.ttl = ttl
    self.now = now
    self.fetchSubscription = fetchSubscription
    self.isByokActive = isByokActive
    if observeAuthChanges {
      let center = NotificationCenter.default
      observers.append(
        center.addObserver(forName: .userDidSignOut, object: nil, queue: nil) { [weak self] _ in
          guard let self else { return }
          Task { await self.invalidate() }
        })
      observers.append(
        center.addObserver(forName: .runtimeOwnerDidChange, object: nil, queue: nil) { [weak self] _ in
          guard let self else { return }
          Task { await self.invalidate() }
        })
    }
  }

  deinit {
    for observer in observers {
      NotificationCenter.default.removeObserver(observer)
    }
  }

  func invalidate() {
    cached = nil
    inflight?.cancel()
    inflight = nil
  }

  func cachedSnapshot() -> UserSubscriptionResponse? {
    cached?.response
  }

  func decisionForManagedProactivity() async -> SubscriptionEntitlementDecision {
    let info = await snapshot()?.subscription
    return SubscriptionEntitlement.decision(
      plan: info?.plan,
      features: info?.features ?? [],
      isByokActive: isByokActive())
  }

  func snapshot() async -> UserSubscriptionResponse? {
    if let cached, cached.expiresAt > now() {
      return cached.response
    }
    if let inflight {
      return await inflight.value
    }
    let task = Task { await self.refresh() }
    inflight = task
    return await task.value
  }

  private func refresh() async -> UserSubscriptionResponse? {
    let response: UserSubscriptionResponse?
    do {
      response = try await fetchSubscription()
    } catch {
      response = nil
    }
    inflight = nil
    if let response {
      cached = (response, now().addingTimeInterval(ttl))
    }
    return response
  }
}

/// Test seam so Gemini / lane clients can pin a decision without touching
/// `SubscriptionEntitlementService.shared`.
actor ManagedProactivityDecisionSource {
  static let shared = ManagedProactivityDecisionSource()

  private var override: (@Sendable () async -> SubscriptionEntitlementDecision)?

  func current() async -> SubscriptionEntitlementDecision {
    if let override {
      return await override()
    }
    return await SubscriptionEntitlementService.shared.decisionForManagedProactivity()
  }

  func setOverride(_ resolve: (@Sendable () async -> SubscriptionEntitlementDecision)?) {
    override = resolve
  }
}

enum ManagedPlanGateHTTP {
  static func isPlanGated(status: Int, data: Data) -> Bool {
    guard status == 402 else { return false }
    if let object = try? JSONSerialization.jsonObject(with: data) {
      if errorField(object) == "plan_gated" {
        return true
      }
      if let root = object as? [String: Any], let detail = root["detail"] {
        if errorField(detail) == "plan_gated" {
          return true
        }
        if let detailString = detail as? String,
          detailString.lowercased().contains("plan_gated")
        {
          return true
        }
      }
    }
    let body = String(data: data.prefix(512), encoding: .utf8)?.lowercased() ?? ""
    return body.contains("plan_gated")
  }

  private static func errorField(_ object: Any) -> String? {
    (object as? [String: Any])?["error"] as? String
  }
}

enum RealtimeHubUsageLimitPresentation {
  /// Mid-session provider quota 1008 is a usage-limit close. Gemini idle 1008
  /// (`expectedIdleTeardown`) is not.
  static func shouldPresent(category: RealtimeHubCloseCategory?, failoverStarted: Bool) -> Bool {
    category == .providerQuotaExceeded && !failoverStarted
  }
}
