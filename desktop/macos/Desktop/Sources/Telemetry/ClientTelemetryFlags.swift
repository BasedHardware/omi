import Foundation

/// Transport shadow and PostHog retirement switches for the frozen client collector.
///
/// Both default off. A missing PostHog value stays off. Retirement cannot suppress
/// `desktop_health_event`, screen-task terminals, or Device Disconnected; those stay
/// until Lane 4 voice-panel and fallback-triage parity plus a live canary receipt.
enum ClientTelemetryFlags {
  static let transportShadowFlagName = "client_telemetry_transport_shadow"
  static let postHogRetirementFlagName = "client_telemetry_posthog_retirement"

  private static let lock = NSLock()
  nonisolated(unsafe) private static var shadowOverride: Bool?
  nonisolated(unsafe) private static var retirementOverride: Bool?
  nonisolated(unsafe) private static var channelOverride: String?
  nonisolated(unsafe) private static var cachedShadowEnabled = false
  nonisolated(unsafe) private static var cachedRetirementEnabled = false
  nonisolated(unsafe) private static var didInstallRefresh = false

  static var transportShadowEnabled: Bool {
    lock.lock()
    defer { lock.unlock() }
    if let shadowOverride { return shadowOverride }
    return cachedShadowEnabled
  }

  static var postHogRetirementEnabled: Bool {
    lock.lock()
    defer { lock.unlock() }
    if let retirementOverride { return retirementOverride }
    return cachedRetirementEnabled
  }

  /// Infrastructure PostHog events stay. This lane does not treat the retirement
  /// flag as permission to stop them.
  static var retiresInfrastructurePostHog: Bool { false }

  static func resolvedChannel() -> String? {
    lock.lock()
    let override = channelOverride
    lock.unlock()
    if let override { return override }
    return ClientTelemetryChannel.releaseChannel()
  }

  @MainActor
  static func installProductionRefresh() {
    lock.lock()
    let already = didInstallRefresh
    didInstallRefresh = true
    lock.unlock()
    guard !already else { return }
    NotificationCenter.default.addObserver(
      forName: PostHogManager.featureFlagsDidLoad,
      object: nil,
      queue: .main
    ) { _ in
      Task { @MainActor in
        refreshCacheFromPostHog()
      }
    }
    Task { @MainActor in
      refreshCacheFromPostHog()
    }
  }

  @MainActor
  static func refreshCacheFromPostHog() {
    let shadow = interpret(PostHogManager.shared.getFeatureFlag(transportShadowFlagName))
    let retirement = interpret(PostHogManager.shared.getFeatureFlag(postHogRetirementFlagName))
    lock.lock()
    cachedShadowEnabled = shadow
    cachedRetirementEnabled = retirement
    lock.unlock()
  }

  static func setTransportShadowForTests(_ enabled: Bool?) {
    lock.lock()
    shadowOverride = enabled
    lock.unlock()
  }

  static func setPostHogRetirementForTests(_ enabled: Bool?) {
    lock.lock()
    retirementOverride = enabled
    lock.unlock()
  }

  static func setChannelForTests(_ channel: String?) {
    lock.lock()
    channelOverride = channel
    lock.unlock()
  }

  static func resetForTests() {
    lock.lock()
    shadowOverride = nil
    retirementOverride = nil
    channelOverride = nil
    cachedShadowEnabled = false
    cachedRetirementEnabled = false
    lock.unlock()
    ClientTelemetryIdentity.resetForTests()
    ClientTelemetryShadow.resetForTests()
  }

  private static func interpret(_ value: Any?) -> Bool {
    if let enabled = value as? Bool { return enabled }
    if let number = value as? NSNumber { return number.boolValue }
    if let text = value as? String { return text == "true" }
    return false
  }
}

enum ClientTelemetryChannel {
  /// Release identity only. Dev and named bundles do not invent a channel.
  static func releaseChannel(
    bundleIdentifier: String = AppBuild.bundleIdentifier,
    isBeta: Bool = AppBuild.isBetaProductionBundle
  ) -> String? {
    if isBeta { return "beta" }
    if bundleIdentifier == AppBuild.productionBundleIdentifier { return "production" }
    return nil
  }
}

enum ClientTelemetryIdentity {
  private static let lock = NSLock()
  nonisolated(unsafe) private static var ownerOverride: (() -> String?)?

  static func currentOwnerID() -> String? {
    lock.lock()
    let override = ownerOverride
    lock.unlock()
    if let override { return override() }
    return RuntimeOwnerIdentity.currentOwnerId()
  }

  static func setOwnerForTests(_ ownerID: @escaping () -> String?) {
    lock.lock()
    ownerOverride = ownerID
    lock.unlock()
  }

  static func resetForTests() {
    lock.lock()
    ownerOverride = nil
    lock.unlock()
  }
}
