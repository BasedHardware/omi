@preconcurrency import AVFoundation
import Combine
import SwiftUI
@preconcurrency import UserNotifications

@MainActor
extension AppState {
  /// Reasons that belong to the free-plan / trial paywall family this file
  /// guards. Deliberately narrow (an allowlist, not everything): `"realtime"`
  /// (`RealtimeHubController+SessionDelegate`) reports a real-time
  /// transcription PROVIDER quota exhaustion (Deepgram/Soniox), a distinct
  /// axis from the AI chat provider. It must keep surfacing even when Local
  /// chat is active but no self-hosted backend is configured for voice, so it
  /// is intentionally excluded here. A future reason not in this set fails
  /// closed (still shown) rather than silently swallowed.
  private static let freePlanPaywallReasons: Set<String> = [
    "trial_expired", "transcription", "ptt", "chat", "screen_capture",
  ]

  /// Reason-aware Local-provider exemption, shared by the central
  /// `triggerUsageLimitPopup` choke point and every leaf gate that needs the
  /// same answer for the same reason. Free-tier quota exists to meter Omi's
  /// cloud model usage; a reason names WHICH feature is asking, so each one
  /// gets exactly the exemption its own model/network path earns:
  ///
  /// - `"chat"`/`"ptt"`: the completion itself always runs against the
  ///   user's own server under Local (`AIProvider.currentProviderMode`
  ///   never routes text to Omi regardless of the cloud-assist setting), so
  ///   the free-tier question quota does not apply: `isLocalProviderActive`
  ///   alone is enough.
  /// - `"screen_capture"`: matches `isScreenCaptureExemptFromPaywall`'s
  ///   Local-specific clause exactly, so this backstop can never disagree
  ///   with the leaf gate it backstops (see `isScreenCaptureExemptFromPaywall`'s
  ///   doc comment for why cloud-assist re-introduces metering here).
  /// - `"transcription"`: voice never runs through the local text model
  ///   alone, only a configured self-hosted backend takes it off Omi's
  ///   Deepgram proxy, so this needs `isLocalProviderWithSelfHostedBackend`.
  /// - anything else (including `"trial_expired"`, `"realtime"`): no Local
  ///   exemption. `"trial_expired"` no longer has a Local-specific poster:
  ///   both `SystemCaptureControls` gates now post their own narrower reason,
  ///   so a caller that still posts it is asking about genuine Omi-account
  ///   trial state, which Local does not change.
  nonisolated static func isUsageLimitExemptLocally(reason: String) -> Bool {
    switch reason {
    case "chat", "ptt":
      return AIProvider.isLocalProviderActive
    case "screen_capture":
      return AIProvider.isLocalProviderFailingClosed
    case "transcription":
      return AIProvider.isLocalProviderWithSelfHostedBackend
    default:
      return false
    }
  }

  func triggerUsageLimitPopup(reason: String) {
    // Debug escape hatch for self-test runs that don't want the overage modal in the way.
    if ProcessInfo.processInfo.environment["OMI_SKIP_USAGE_POPUP"] == "1" { return }
    // Single choke point for every `.showUsageLimitPopup` poster (direct calls
    // and the notification both land here; see DesktopHomeView's listener).
    // Every known leaf already checks its own exemption before posting, but a
    // future caller that forgets to, or a stale cached flag that slips one
    // through, still lands here, so re-check once, centrally, rather than
    // trusting every call site forever. BYOK is already covered per-leaf via
    // `isPaywalled`/`isPaywalledEffective`; the Local-provider check is the
    // one this file exists to add.
    if Self.freePlanPaywallReasons.contains(reason),
      APIKeyService.isByokActive || AppState.isUsageLimitExemptLocally(reason: reason)
    {
      log("AppState: usage-limit popup (reason=\(reason)) suppressed: BYOK or Local-provider exemption for this reason")
      return
    }
    // A modal the user did not ask for, arriving over what they were doing: the same "something
    // just opened" cue the what's-new card gets.
    OmiUISound.play(.reveal)
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
    !APIKeyService.isByokActive && UserDefaults.standard.bool(forKey: .desktopIsPaywalled)
  }

  /// True when transcription specifically is exempt from the paywall: either
  /// the general BYOK exemption above, or because the local provider is
  /// active with a self-hosted backend configured (Settings' "Local Backend
  /// URL", see `AIProvider.isLocalProviderWithSelfHostedBackend`), which
  /// routes voice transcription away from Omi's Deepgram proxy entirely.
  /// Distinct from `isScreenCaptureExemptFromPaywall`: transcription needs the
  /// extra backend-URL check because the Local provider alone only covers
  /// text and (via the vision subagent) screenshots, not the separate voice
  /// pipeline.
  nonisolated static var isTranscriptionExemptFromPaywall: Bool {
    if !isPaywalledEffective { return true }
    return AIProvider.isLocalProviderWithSelfHostedBackend
  }

  /// True when screen capture / screenshot interpretation is exempt from the
  /// paywall: either the general BYOK exemption above, or because the Local
  /// provider is active AND the user has not opted cloud-assisted features
  /// on. Unlike `isTranscriptionExemptFromPaywall`, this needs no
  /// self-hosted-backend check: screen capture's own cloud dependency was
  /// Omi's Gemini proxy for interpreting the image, and the vision-subagent
  /// delegation (see `ChatProvider.visionSubagentInstruction`) already routes
  /// that through the local provider's own model/subagent instead. Screen
  /// capture itself (the macOS frame grab) never leaves the device under any
  /// provider, but the proactive assistants and live notes that consume it
  /// (task/memory/insight/suggestion extraction) go back to Omi's Gemini
  /// proxy the moment the user opts cloud-assist on, so this is metered again
  /// exactly like a cloud user once `AIProvider.localCloudAssistEnabled` is
  /// true.
  nonisolated static var isScreenCaptureExemptFromPaywall: Bool {
    if !isPaywalledEffective { return true }
    return AIProvider.isLocalProviderFailingClosed
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
      let features = [
        "unlimited_listening", "unlimited_transcription", "unlimited_memories", "unlimited_insights",
        "30_chat_questions_per_month",
      ]
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
    if isSystemAudioSupported, audioRecordingMode != .off, shouldCaptureSystemAudio,
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

  /// Check if notification permission was explicitly denied.
  ///
  /// Reads the actual TCC answer (`notificationAuthorizationStatus`, cached from
  /// `checkNotificationPermission()`) rather than inferring denial from "not yet
  /// granted". `notDetermined` is not denied: it means the user was never asked,
  /// and macOS typically will not even list an app under System Settings ->
  /// Notifications until it has called `requestAuthorization` once — so routing
  /// a never-asked user to "open System Settings" was a dead end. See
  /// `NotificationPermissionPolicy.enableAction(for:)`, the single source of
  /// truth this must never disagree with.
  func isNotificationPermissionDenied() -> Bool {
    hasCompletedOnboarding && notificationAuthorizationStatus == .denied
  }

  /// Open notification preferences in System Settings (directly to Omi's settings)
  func openNotificationPreferences() {
    let bundleId = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.notifications?id=\(bundleId)")
    {
      log("Opening notification settings for bundle \(bundleId)")
      NSWorkspace.shared.open(url)
    }
  }

  /// True if any required permissions are missing
  var hasMissingPermissions: Bool {
    !missingPermissions.isEmpty
  }

  // Transcription services
}
