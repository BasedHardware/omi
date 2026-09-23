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
final class SubscriptionEntitlementService: @unchecked Sendable {
  static let shared = SubscriptionEntitlementService()

  static let defaultTTL: TimeInterval = 5 * 60

  private let lock = NSLock()
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
          self?.invalidate()
        })
      observers.append(
        center.addObserver(forName: .runtimeOwnerDidChange, object: nil, queue: nil) { [weak self] _ in
          self?.invalidate()
        })
    }
  }

  deinit {
    for observer in observers {
      NotificationCenter.default.removeObserver(observer)
    }
  }

  private func withLock<T>(_ body: () -> T) -> T {
    lock.lock()
    defer { lock.unlock() }
    return body()
  }

  func invalidate() {
    withLock {
      cached = nil
      inflight?.cancel()
      inflight = nil
    }
  }

  var cachedSnapshot: UserSubscriptionResponse? {
    withLock { cached?.response }
  }

  /// Sync peek for call sites that cannot await (recording start). Empty or
  /// expired cache is unknown plan and fails open.
  func cachedDecisionForManagedProactivity() -> SubscriptionEntitlementDecision {
    let info = cachedSnapshot?.subscription
    return SubscriptionEntitlement.decision(
      plan: info?.plan,
      features: info?.features ?? [],
      isByokActive: isByokActive())
  }

  func decisionForManagedProactivity() async -> SubscriptionEntitlementDecision {
    let info = await snapshot()?.subscription
    return SubscriptionEntitlement.decision(
      plan: info?.plan,
      features: info?.features ?? [],
      isByokActive: isByokActive())
  }

  func snapshot() async -> UserSubscriptionResponse? {
    if let response = withLock({
      guard let cached, cached.expiresAt > now() else { return nil as UserSubscriptionResponse? }
      return cached.response
    }) {
      return response
    }
    if let inflight = withLock({ inflight }) {
      return await inflight.value
    }
    let task = Task { await self.refresh() }
    withLock { inflight = task }
    return await task.value
  }

  private func refresh() async -> UserSubscriptionResponse? {
    let response: UserSubscriptionResponse?
    do {
      response = try await fetchSubscription()
    } catch {
      response = nil
    }
    withLock {
      inflight = nil
      if let response {
        cached = (response, now().addingTimeInterval(ttl))
      }
    }
    return response
  }
}

/// Test seam so Gemini / lane clients can pin a decision without touching
/// `SubscriptionEntitlementService.shared`.
enum ManagedProactivityDecisionSource {
  private static let lock = NSLock()
  nonisolated(unsafe) private static var override: (@Sendable () async -> SubscriptionEntitlementDecision)?

  private static func withLock<T>(_ body: () -> T) -> T {
    lock.lock()
    defer { lock.unlock() }
    return body()
  }

  static func current() async -> SubscriptionEntitlementDecision {
    let pinned = withLock { override }
    if let pinned {
      return await pinned()
    }
    return await SubscriptionEntitlementService.shared.decisionForManagedProactivity()
  }

  static func setOverride(_ resolve: (@Sendable () async -> SubscriptionEntitlementDecision)?) {
    withLock { override = resolve }
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

  /// Exact typed code at a known JSON field. Prose that happens to mention
  /// `plan_gated` must not classify. Hub mint uses this; the legacy
  /// `isPlanGated(status:data:)` scanner still serves Gemini/lane clients.
  static func isTypedPlanGatedCode(_ value: String?) -> Bool {
    guard let value else { return false }
    return value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "plan_gated"
  }

  static func isPlanGated(status: Int, payload: APIErrorPayload?) -> Bool {
    guard status == 402, let payload else { return false }
    return isTypedPlanGatedCode(payload.error)
      || isTypedPlanGatedCode(payload.code)
      || isTypedPlanGatedCode(payload.detail)
  }

  /// Exact `error` / `code` / `detail.error` (or a string `detail`) on a 402.
  /// Does not scan the raw body for substring containment.
  static func isPlanGatedTypedJSON(status: Int, data: Data) -> Bool {
    guard status == 402 else { return false }
    guard let object = try? JSONSerialization.jsonObject(with: data) else { return false }
    if isTypedPlanGatedCode(errorField(object)) || isTypedPlanGatedCode(codeField(object)) {
      return true
    }
    guard let root = object as? [String: Any], let detail = root["detail"] else { return false }
    if isTypedPlanGatedCode(errorField(detail)) || isTypedPlanGatedCode(codeField(detail)) {
      return true
    }
    return isTypedPlanGatedCode(detail as? String)
  }

  static func isPlanGatedMint(_ error: RealtimeTokenMintError) -> Bool {
    isPlanGatedTypedJSON(status: error.statusCode, data: error.responseBody)
      || isPlanGated(status: error.statusCode, payload: error.payload)
  }

  /// Typed 402 `plan_gated` from the managed proxy, or a client that already
  /// classified it. Distinct from chat-quota / trial-expired 402.
  static func isPlanGatedWarmFailure(_ error: Error) -> Bool {
    if case GeminiClient.GeminiClientError.planGated = error {
      return true
    }
    if case ProactiveLaneClientError.planGated = error {
      return true
    }
    if let mint = error as? RealtimeTokenMintError {
      return isPlanGatedMint(mint)
    }
    return false
  }

  private static func errorField(_ object: Any) -> String? {
    (object as? [String: Any])?["error"] as? String
  }

  private static func codeField(_ object: Any) -> String? {
    (object as? [String: Any])?["code"] as? String
  }
}

/// Bounded server-denial latch for managed proactivity.
///
/// Cached unknown plans fail open to `.allowManagedProactivity`, so an upgrade
/// that never changes the decision would otherwise retry forever after a typed
/// 402 `plan_gated`. Clear when the decision becomes allow, or after
/// `defaultLifetime` (one probe per window). LiveNotes (`shouldSkipManagedAINotes`
/// on `fix/desktop-livenotes-respects-plan-gate`) and the realtime hub both use
/// this so the two call sites cannot drift.
struct ManagedPlanGateLatch: Equatable, Sendable {
  static let defaultLifetime: TimeInterval = 10 * 60

  private(set) var ownerID: String?
  private(set) var lastDecision: SubscriptionEntitlementDecision?
  private(set) var serverDenied = false
  private(set) var deniedAt: Date?

  /// Returns whether automatic managed work should skip. User-initiated PTT is
  /// a separate admission decision and must not consult this for a key press.
  /// An owner change always resets: both users can fail-open to `.allow`, so
  /// comparing only the enum would carry A's 402 latch onto B.
  mutating func shouldSkipAutomaticManagedWork(
    decision: SubscriptionEntitlementDecision,
    now: Date,
    ownerID: String? = nil,
    lifetime: TimeInterval = Self.defaultLifetime
  ) -> Bool {
    if self.ownerID != ownerID {
      reset()
      self.ownerID = ownerID
    }
    if lastDecision != decision {
      let previous = lastDecision
      lastDecision = decision
      // Only an observed `.planGated` → `.allow` transition drops a 402 latch.
      // `nil` → allow is the first observation of a fail-open cache, which is
      // exactly when a typed 402 must stick until owner change or expiry.
      if previous == .planGated, decision == .allowManagedProactivity {
        clearServerDenial()
      }
    }
    if serverDenied, let deniedAt, now.timeIntervalSince(deniedAt) >= lifetime {
      clearServerDenial()
    }
    return decision == .planGated || serverDenied
  }

  mutating func latchServerDenial(at now: Date, ownerID: String? = nil) {
    if self.ownerID != ownerID {
      lastDecision = nil
    }
    self.ownerID = ownerID
    serverDenied = true
    deniedAt = now
  }

  mutating func clearServerDenial() {
    serverDenied = false
    deniedAt = nil
  }

  mutating func reset() {
    lastDecision = nil
    ownerID = nil
    clearServerDenial()
  }
}

enum RealtimeHubUsageLimitPresentation {
  /// Mid-session provider quota 1008 is a usage-limit close. Gemini idle 1008
  /// (`expectedIdleTeardown`) is not.
  static func shouldPresent(category: RealtimeHubCloseCategory?, failoverStarted: Bool) -> Bool {
    category == .providerQuotaExceeded && !failoverStarted
  }
}
