import Foundation

/// Immutable capture authority survives suppressed distribution, departure and rollback queues.
struct ScreenTaskFrameBinding: Sendable {
  let authorization: RuntimeOwnerAuthorizationSnapshot
  let exclusion: RewindCaptureExclusionSnapshot

  static func capture(app: String, title: String?) -> Self? {
    guard !ScreenTaskPrivacy.isPrivateWindow(app: app, title: title),
      let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(),
      let exclusion = RewindCaptureExclusionGeneration.snapshot(appName: app)
    else { return nil }
    return Self(authorization: authorization, exclusion: exclusion)
  }

  func isCurrent() -> Bool {
    RuntimeOwnerIdentity.isAuthorizationCurrent(authorization)
      && RewindCaptureExclusionGeneration.isCurrent(exclusion)
  }
}

enum ScreenTaskPrivacy {
  static func isPrivateWindow(app: String, title: String?) -> Bool {
    guard TaskAssistantSettings.isBrowser(app), let title else { return false }
    // The known browsers use these title markers. A missing marker cannot prove privacy.
    let markers = [
      "incognito", "private browsing", "inprivate", "private window", "private tab", "guest window", "(private)",
      "[private]", "- private", "— private",
      "navigation privée", "navegación privada", "privates fenster", "ẩn danh",
      "inkognito", "инкогнито", "privat vindu", "privat fönster", "janela privada", "finestra privata",
      "无痕", "無痕", "隐私浏览", "隱私瀏覽", "シークレット", "プライベート", "비공개", "시크릿",
    ]
    return markers.contains { title.localizedStandardContains($0) }
  }
}

/// Resolve fallback identity before capture, never label new pixels with the vanished window's authority.
struct ScreenTaskCaptureResolution {
  let app: String
  let title: String?
  let window: UInt32
  let binding: ScreenTaskFrameBinding?

  static func resolve(
    app: String?, title: String?, window: UInt32?,
    captureBinding: (String, String?) -> ScreenTaskFrameBinding? = {
      ScreenTaskFrameBinding.capture(app: $0, title: $1)
    }
  ) -> Self? {
    guard let app, let window, !ScreenTaskPrivacy.isPrivateWindow(app: app, title: title) else { return nil }
    return Self(app: app, title: title, window: window, binding: captureBinding(app, title))
  }
}

/// Admission expires even when a flag reload never completes. Uptime is monotonic.
final class ScreenTaskAdmissionAuthority: @unchecked Sendable {
  private let lock = NSLock()
  private var enabled = false
  private var generation: UInt64 = 0
  private var expires: TimeInterval = 0
  private let now: @Sendable () -> TimeInterval
  private var authorization: RuntimeOwnerAuthorizationSnapshot?
  private let ownerIsCurrent: @Sendable (RuntimeOwnerAuthorizationSnapshot) -> Bool

  init(
    now: @escaping @Sendable () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
    ownerIsCurrent: @escaping @Sendable (RuntimeOwnerAuthorizationSnapshot) -> Bool = {
      RuntimeOwnerIdentity.isAuthorizationCurrent($0)
    }
  ) {
    self.now = now
    self.ownerIsCurrent = ownerIsCurrent
  }

  func refresh(enabled: Bool, requestedAt: TimeInterval? = nil, authorization: RuntimeOwnerAuthorizationSnapshot? = nil)
  {
    lock.withLock {
      if self.enabled != enabled || now() >= expires || self.authorization != authorization { generation &+= 1 }
      self.authorization = authorization
      self.enabled = enabled
      expires = (requestedAt ?? now()) + 55
    }
  }

  func disable() {
    lock.withLock {
      if enabled { generation &+= 1 }
      enabled = false
      expires = 0
    }
  }

  func snapshot() -> UInt64? {
    let value = lock.withLock { (enabled && now() < expires ? generation : nil, authorization) }
    // Owner validation runs outside this lock to preserve commit-lease lock order.
    guard value.1.map(ownerIsCurrent) ?? true else { return nil }
    return value.0
  }
  func isCurrent(_ token: UInt64) -> Bool { snapshot() == token }
}

struct ScreenTaskLease: Sendable {
  let flag: UInt64
  let server: UInt64
  func isCurrent() -> Bool {
    ScreenTaskFeature.authority.isCurrent(flag) && ScreenTaskFeature.serverAuthority.isCurrent(server)
  }
}

enum ScreenTaskFreshFlagResponse {
  static func enabled(_ data: Data) throws -> Bool {
    guard let body = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      body["errorsWhileComputingFlags"] as? Bool != true,
      !(body["quotaLimited"] as? [String] ?? []).contains("feature_flags")
    else { throw ScreenTaskFailure.stopped }
    if let flags = body["featureFlags"] as? [String: Any] {
      return flags[ScreenTaskFeature.flagName] as? Bool ?? false
    }
    if let flags = body["flags"] as? [String: [String: Any]] {
      return flags[ScreenTaskFeature.flagName]?["enabled"] as? Bool ?? false
    }
    throw ScreenTaskFailure.invalidResponse
  }
}

@MainActor enum ScreenTaskFlagRefresh {
  private static var timer: Timer?
  private static var reloadInFlight = false
  static func start() {
    guard timer == nil else { return }
    reload()
    timer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { _ in
      Task { @MainActor in reload() }
    }
  }

  private static func reload() {
    PostHogManager.shared.reloadFeatureFlags()
    guard !reloadInFlight, PostHogManager.shared.isFeatureEnabled(ScreenTaskFeature.flagName),
      let owner = RuntimeOwnerIdentity.captureAuthorizationSnapshot()
    else { return }
    reloadInFlight = true
    let requestedAt = ProcessInfo.processInfo.systemUptime
    Task { @MainActor in
      defer { reloadInFlight = false }
      do {
        let flagEnabled = try await PostHogManager.shared.screenTaskFlagAdmission(authorization: owner)
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(owner) else { return }
        ScreenTaskFeature.authority.refresh(enabled: flagEnabled, requestedAt: requestedAt, authorization: owner)
        let serverEnabled = try await APIClient.shared.screenTaskAdmissionStatus(authorization: owner)
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(owner) else { return }
        ScreenTaskFeature.serverAuthority.refresh(
          enabled: serverEnabled, requestedAt: requestedAt, authorization: owner)
      } catch {
        // Failure cannot renew either cached lease. Already granted leases expire at request start +55s.
      }
    }
  }
}

/// Shared transport checks this at the actual dispatch, including auth retries.
/// Ordinary legacy work retains frame privacy/owner authority but does not need a feature lease.
enum ScreenTaskWorkAuthority {
  @TaskLocal static var validate: (@Sendable () throws -> Void)?
  static func require() throws {
    guard let validate else { return }
    try Task.checkCancellation()
    try validate()
  }
}

/// Never let an awaited helper's return value cross an original-owner mutation boundary.
enum ScreenTaskAuthorizedOperation {
  static func run<T>(
    authorization: LocalMutationAuthorization,
    isolation: isolated (any Actor)? = #isolation,
    operation: () async throws -> T
  ) async throws -> T {
    try authorization.require()
    let value = try await operation()
    try authorization.require()
    return value
  }
}
