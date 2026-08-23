import Foundation

/// Notification-facing automation actions, grouped out of the main registry file.
extension DesktopAutomationActionRegistry {
  func registerNotificationActions() {
    register(
      name: "settings_notifications_snapshot",
      summary: "Return notification settings and local permission state"
    ) { _ in
      async let settingsTask = APIClient.shared.getNotificationSettings()
      let settings = try await settingsTask
      let appState = await MainActor.run { AppState.current }
      let hasPermission = appState?.hasNotificationPermission ?? false
      let bannersDisabled = appState?.isNotificationBannerDisabled ?? false
      return [
        "schema": "enabled,frequency,frequency_label,has_permission,banners_disabled",
        "enabled": settings.enabled ? "true" : "false",
        "frequency": "\(settings.frequency)",
        "frequency_label": settings.frequencyDescription,
        "has_permission": hasPermission ? "true" : "false",
        "banners_disabled": bannersDisabled ? "true" : "false",
      ]
    }

    register(
      name: "set_notification_settings",
      summary: "Update notification settings via the real API",
      params: ["enabled", "frequency"]
    ) { params in
      let enabled = params["enabled"].map { boolParam($0, default: true) }
      let frequency = params["frequency"].flatMap { Int($0) }
      let response = try await APIClient.shared.updateNotificationSettings(
        enabled: enabled,
        frequency: frequency
      )
      UserDefaults.standard.set(
        response.enabled,
        forKey: NotificationService.masterEnabledDefaultsKey)
      UserDefaults.standard.set(
        response.frequency,
        forKey: NotificationService.frequencyDefaultsKey)
      return [
        "saved": "true",
        "enabled": response.enabled ? "true" : "false",
        "frequency": "\(response.frequency)",
      ]
    }

    // The distributed com.omi.test.notification channel is machine-global: every
    // running Omi bundle — the user's production install included — receives it,
    // delivers it, and journals it into the real account's chat (#11943). This is
    // the bundle-scoped alternative: it reaches only the bundle whose port and
    // token the caller holds, through the same production sendNotification path.
    register(
      name: "send_test_notification",
      summary: "Deliver a proactive test notification through the real sendNotification path (this bundle only)",
      params: ["title", "message", "assistant_id"]
    ) { params in
      let title = params["title"] ?? "Insight"
      let message = params["message"] ?? "Test notification from Omi"
      let assistantId = params["assistant_id"] ?? "insight"
      let posted = await MainActor.run { () -> Bool in
        guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return false }
        NotificationService.shared.sendNotification(
          ownerID: ownerID,
          title: title,
          message: message,
          assistantId: assistantId
        )
        return true
      }
      return ["posted": posted ? "true" : "false"]
    }
  }
}
