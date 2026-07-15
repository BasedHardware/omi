import AVFoundation
import Combine
import SwiftUI
import UserNotifications

@MainActor
extension AppState {
  func triggerUsageLimitPopup(reason: String) {
    // Debug escape hatch for self-test runs that don't want the overage modal in the way.
    if ProcessInfo.processInfo.environment["OMI_SKIP_USAGE_POPUP"] == "1" { return }
    usageLimitReason = reason
    showUsageLimitPopup = true
  }

  /// Returns true if the requested capture toggle should be blocked because
  /// the user is paywalled. Posts the existing usage-limit popup and returns
  /// true so the caller can early-return without enabling the feature.
  ///
  /// Use at the entry point of every toggle/start function that drives a
  /// $-cost path (transcription, screen analysis, proactive monitoring, etc).
  /// Single source of truth for "should the UI block $-cost features". A BYOK
  /// user (all four keys configured locally) is never paywalled, regardless of
  /// the persisted `desktop_isPaywalled` flag, which can lag behind BYOK
  /// activation. Use this anywhere that only has UserDefaults access.
  nonisolated static var isPaywalledEffective: Bool {
    !APIKeyService.isByokActive && UserDefaults.standard.bool(forKey: "desktop_isPaywalled")
  }

  /// Decision for the resume-on-paywall-clear hook in `fetchTrialMetadata()`.
  /// Pure so it is unit-testable: resume screen-analysis monitoring only when
  /// this fetch actually cleared the paywall (set → clear transition), the
  /// user still has screen analysis enabled, nothing is already running, and
  /// API keys are loaded (mirrors the launch gate; the key-load retry path
  /// covers the not-yet-loaded case).
  nonisolated static func shouldResumeMonitoringAfterPaywallClear(
    wasPaywalled: Bool,
    isPaywalledNow: Bool,
    screenAnalysisEnabled: Bool,
    isMonitoring: Bool,
    keysAvailable: Bool
  ) -> Bool {
    wasPaywalled && !isPaywalledNow && screenAnalysisEnabled && !isMonitoring && keysAvailable
  }

  @discardableResult
  func blockIfPaywalled(reason: String = "trial_expired") -> Bool {
    // BYOK users are never paywalled. If the user has all four BYOK keys
    // configured locally, every backend request carries them and the server
    // exempts the user — so the client must not block capture either, even if
    // a stale `isPaywalled` flag is still set (e.g. trial expired *before*
    // they added keys, and the backend heartbeat hasn't refreshed yet).
    if APIKeyService.isByokActive {
      if isPaywalled { isPaywalled = false }
      return false
    }
    guard isPaywalled else { return false }
    NotificationCenter.default.post(
      name: .showUsageLimitPopup,
      object: nil,
      userInfo: ["reason": reason]
    )
    return true
  }

  func fetchTrialMetadata() {
    #if DEBUG
    if let debugMode = UserDefaults.standard.string(forKey: "debug_trial_mode") {
      applyDebugTrialMode(debugMode)
      return
    }
    #endif

    Task { @MainActor in
      do {
        let metadata = try await APIClient.shared.getTrialMetadata()
        self.trialMetadata = metadata
        // Snapshot the paywall state observed AFTER the network await resolves
        // (intentionally not before): if two fetches are in flight, whichever
        // resolves first clears the flag, so the second sees false here and
        // the resume hook below fires exactly once instead of double-starting.
        let wasPaywalled = self.isPaywalled
        // Local BYOK always wins — never re-block a user who has all four keys
        // configured, regardless of what the (possibly heartbeat-lagged)
        // backend trial state says.
        if APIKeyService.isByokActive {
          if self.isPaywalled { self.isPaywalled = false }
        } else if metadata.trialExpired && !self.isPaywalled {
          self.isPaywalled = true
        } else if !metadata.trialExpired && self.isPaywalled {
          self.isPaywalled = false
        }
        // A mid-session `freemium_threshold_reached` event stops capture and
        // sets the sticky flag; nothing else observes the flag clearing, so
        // without this hook capture stays off after the paywall lifts until
        // the next incidental startMonitoring trigger (e.g. app
        // re-activation) — indefinitely for a user who leaves the window in
        // the background.
        if AppState.shouldResumeMonitoringAfterPaywallClear(
          wasPaywalled: wasPaywalled,
          isPaywalledNow: self.isPaywalled,
          screenAnalysisEnabled: AssistantSettings.shared.screenAnalysisEnabled,
          isMonitoring: ProactiveAssistantsPlugin.shared.isMonitoring,
          keysAvailable: APIKeyService.keysAvailable
        ) {
          log("AppState: paywall lifted — resuming screen analysis monitoring")
          ProactiveAssistantsPlugin.shared.startMonitoring { success, error in
            if !success, let error, !error.isEmpty {
              log("AppState: paywall-lifted monitoring restart failed: \(error)")
            }
          }
        }
      } catch {
        log("AppState: failed to fetch trial metadata: \(error.localizedDescription)")
      }
    }
  }

  #if DEBUG
  func applyDebugTrialMode(_ mode: String) {
    let now = Int(Date().timeIntervalSince1970)
    let features = ["unlimited_listening", "unlimited_transcription", "unlimited_memories", "unlimited_insights", "30_chat_questions_per_month"]
    let dur = 3 * 24 * 3600

    func mock(remaining: Int, expired: Bool) -> TrialMetadataResponse {
      TrialMetadataResponse(
        trialStartedAt: now - (dur - remaining), trialEndsAt: now + remaining,
        trialRemainingSeconds: remaining, trialExpired: expired,
        trialDurationSeconds: dur, trialFeatures: features, planAfterTrial: "Free"
      )
    }

    switch mode {
    case "active":
      self.trialMetadata = mock(remaining: 2 * 24 * 3600 + 3600, expired: false)
    case "warning":
      self.trialMetadata = mock(remaining: 12 * 3600, expired: false)
    case "expiring":
      self.trialMetadata = mock(remaining: 1800, expired: false)
    case "expired":
      self.trialMetadata = mock(remaining: 0, expired: true)
    case "realtime":
      let endKey = "debug_trial_end_time"
      let rtDur = 120
      var endTime = UserDefaults.standard.integer(forKey: endKey)
      if endTime == 0 {
        endTime = now + rtDur
        UserDefaults.standard.set(endTime, forKey: endKey)
      }
      let remaining = max(0, endTime - now)
      self.trialMetadata = TrialMetadataResponse(
        trialStartedAt: endTime - rtDur, trialEndsAt: endTime,
        trialRemainingSeconds: remaining, trialExpired: remaining == 0,
        trialDurationSeconds: rtDur, trialFeatures: features, planAfterTrial: "Free"
      )
      if remaining == 0 && !self.isPaywalled { self.isPaywalled = true }
    default:
      break
    }
  }
  #endif

  func startTrialMetadataRefresh() {
    trialRefreshTimer?.invalidate()
    fetchTrialMetadata()
    #if DEBUG
    let interval: TimeInterval = UserDefaults.standard.string(forKey: "debug_trial_mode") == "realtime" ? 10 : 60
    #else
    let interval: TimeInterval = 60
    #endif
    trialRefreshTimer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
      Task { @MainActor in
        self?.fetchTrialMetadata()
      }
    }
  }

  func stopTrialMetadataRefresh() {
    trialRefreshTimer?.invalidate()
    trialRefreshTimer = nil
    trialMetadata = nil
  }

  /// True if notifications are enabled but won't show visual banners
  var isNotificationBannerDisabled: Bool {
    hasNotificationPermission && notificationAlertStyle == .none
  }

  /// Returns list of missing permissions that are required for full functionality
  var missingPermissions: [String] {
    var missing: [String] = []
    if !hasMicrophonePermission { missing.append("Microphone") }
    if !hasScreenRecordingPermission || isScreenRecordingStale {
      missing.append("Screen Recording")
    }
    // System audio is optional/best-effort and its status idles at .unknown
    // (Core Audio taps have no preflight API — only a live capture proves the
    // grant). Counting .unknown as missing would permanently suppress the
    // "All permissions granted" banner for default users, so only a proven
    // denial counts.
    if isSystemAudioSupported, effectiveSystemAudioMode != .never,
      systemAudioPermissionStatus == .denied
    {
      missing.append("System Audio")
    }
    if !hasNotificationPermission {
      missing.append("Notifications")
    } else if isNotificationBannerDisabled {
      missing.append("Notification Banners")
    }
    if !hasAccessibilityPermission || isAccessibilityBroken { missing.append("Accessibility") }
    return missing
  }

  /// Check if notification permission was explicitly denied
  func isNotificationPermissionDenied() -> Bool {
    // We need to check synchronously, so use a semaphore pattern
    // This is cached from checkNotificationPermission() calls
    return hasCompletedOnboarding && !hasNotificationPermission
  }

  /// Open notification preferences in System Settings (directly to Omi's settings)
  func openNotificationPreferences() {
    let bundleId = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.notifications?id=\(bundleId)")
    {
      NSWorkspace.shared.open(url)
    }
  }

  /// True if any required permissions are missing
  var hasMissingPermissions: Bool {
    !missingPermissions.isEmpty
  }

  // Transcription services
}
