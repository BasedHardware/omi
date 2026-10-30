import Foundation

/// Explicit authority source; hermetic clients inject their own session authority.
struct EmbeddingOwnerAuthority: Sendable {
  let capture: @Sendable () -> RuntimeOwnerAuthorizationSnapshot?
  let isCurrent: @Sendable (RuntimeOwnerAuthorizationSnapshot) -> Bool
  static let runtime = Self(
    capture: { RuntimeOwnerIdentity.captureAuthorizationSnapshot() },
    isCurrent: { RuntimeOwnerIdentity.isAuthorizationCurrent($0) })
}

/// Spend authority is fresh, session-bound server state, never the UI's persisted plan hint.
/// Peeks never await networking. Misses coalesce into one bounded background refresh.
final class ScreenCloudEntitlementService: @unchecked Sendable {
  static let shared = ScreenCloudEntitlementService()
  private let lock = NSLock()
  private let authority: EmbeddingOwnerAuthority
  private let now: @Sendable () -> Date
  private let fetch: @Sendable (RuntimeOwnerAuthorizationSnapshot) async throws -> UserSubscriptionResponse
  private let ttl: TimeInterval
  private var owner: RuntimeOwnerAuthorizationSnapshot?
  private var cached: (RuntimeOwnerAuthorizationSnapshot, UserSubscriptionResponse, Date)?
  private var inflight: (UUID, RuntimeOwnerAuthorizationSnapshot)?
  private var retryAfter = Date.distantPast
  private var observers: [NSObjectProtocol] = []

  init(
    authority: EmbeddingOwnerAuthority = .runtime, ttl: TimeInterval = 300,
    observeAuthChanges: Bool = true, now: @escaping @Sendable () -> Date = Date.init,
    fetch: @escaping @Sendable (RuntimeOwnerAuthorizationSnapshot) async throws -> UserSubscriptionResponse = {
      try await APIClient.shared.getUserSubscription(authorizationSnapshot: $0)
    }
  ) {
    self.authority = authority
    self.ttl = ttl
    self.now = now
    self.fetch = fetch
    if observeAuthChanges {
      for name in [Notification.Name.userDidSignOut, .runtimeOwnerDidChange] {
        observers.append(
          NotificationCenter.default.addObserver(forName: name, object: nil, queue: nil) { [weak self] _ in
            self?.invalidate()
          })
      }
    }
  }

  deinit { observers.forEach(NotificationCenter.default.removeObserver) }

  func invalidate() {
    lock.withLock {
      owner = nil
      cached = nil
      inflight = nil
      retryAfter = .distantPast
    }
  }

  /// Also fed by launch/sign-in/checkout's existing plan fetch, without a second request.
  func accept(_ response: UserSubscriptionResponse, authorization: RuntimeOwnerAuthorizationSnapshot) {
    guard authority.isCurrent(authorization) else { return }
    lock.withLock {
      guard authority.isCurrent(authorization) else { return }
      owner = authorization
      cached = (authorization, response, now().addingTimeInterval(ttl))
      inflight = nil  // supersedes any older response, including a pre-downgrade refresh
      retryAfter = .distantPast
    }
  }

  func peek(authorization supplied: RuntimeOwnerAuthorizationSnapshot? = nil) -> UserSubscriptionResponse? {
    guard let authorization = supplied ?? authority.capture(), authority.isCurrent(authorization) else { return nil }
    let decision: (UserSubscriptionResponse?, UUID?) = lock.withLock {
      if let cached, cached.0 == authorization, cached.2 > now() { return (cached.1, nil) }
      if owner != authorization {
        owner = authorization
        cached = nil
        inflight = nil
        retryAfter = .distantPast
      }
      if let inflight, inflight.1 == authorization { return (nil, nil) }
      guard now() >= retryAfter else { return (nil, nil) }
      let id = UUID()
      inflight = (id, authorization)
      retryAfter = now().addingTimeInterval(30)
      return (nil, id)
    }
    if let id = decision.1 {
      Task(priority: .utility) { [self] in
        let response = try? await LocalEmbeddingCallBound.run(.seconds(15)) { [fetch] in
          try await fetch(authorization)
        }
        lock.withLock {
          guard inflight?.0 == id else { return }
          inflight = nil
          if let response, authority.isCurrent(authorization) {
            cached = (authorization, response, now().addingTimeInterval(ttl))
          }
        }
      }
    }
    guard authority.isCurrent(authorization) else { return nil }
    return decision.0
  }

  func allowsCloud(_ authorization: RuntimeOwnerAuthorizationSnapshot) -> Bool {
    let response = peek(authorization: authorization)
    return ScreenEmbeddingPolicy(
      plan: response?.subscription.plan, status: response?.subscription.status,
      localRoute: .none, killSwitches: .enabled,
      desktopGrandfatherUntil: response?.desktopGrandfatherUntil.map(Double.init), now: now()
    ).shouldEmbedWithGemini
  }
}
