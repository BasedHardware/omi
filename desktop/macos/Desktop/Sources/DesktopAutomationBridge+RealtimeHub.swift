import Foundation

/// Realtime-hub automation actions (non-production): drive the REAL provider
/// failover path and substitute the HID idle sample the presence-gated warm
/// loop reads — everything downstream of each seam is the production path.
extension DesktopAutomationActionRegistry {
  func registerRealtimeHubActions() {
    // Onboarding screen-demo step: open the three-doors page (same path as the
    // "Open the doors" button), so agents can exercise the demo without the cursor.
    register(
      name: "onboarding_open_doors",
      summary: "Onboarding screen-demo step: open the three-doors page (same path as the Open the doors button)"
    ) { _ in
      await MainActor.run {
        NotificationCenter.default.post(name: .onboardingOpenDoorsRequested, object: nil)
      }
      return ["status": "requested"]
    }

    // Drives the REAL provider failover the quota/auth close handlers call
    // (failoverToAlternateProvider), then re-warms, so the cross-provider path
    // can be exercised without waiting for the shared key to actually throttle.
    register(
      name: "realtime_failover",
      summary: "Fail the realtime hub over to the alternate provider via the production path (non-prod).",
      params: []
    ) { _ in
      guard AppBuild.isNonProduction else {
        return ["error": "realtime_failover is disabled on production bundles"]
      }
      let controller = RealtimeHubController.shared
      let from = controller.effectiveProvider.rawValue
      let started = controller.failoverToAlternateProvider(reason: "quota")
      controller.ensureWarm(userInitiated: true)
      return [
        "failover_started": started ? "true" : "false",
        "from": from,
        "to": controller.effectiveProvider.rawValue,
      ]
    }

    // Substitutes the HID idle sample the presence-gated warm loop reads, so
    // the away → defer → return → re-warm path can be exercised without a real
    // 10-minute walk-away. Everything downstream is the production path.
    register(
      name: "realtime_presence",
      summary: "Override the realtime hub's user-idle sample (non-prod): idle_seconds=<n> or reset.",
      params: ["idle_seconds"]
    ) { params in
      guard AppBuild.isNonProduction else {
        return ["error": "realtime_presence is disabled on production bundles"]
      }
      let controller = RealtimeHubController.shared
      if let raw = params["idle_seconds"], let idle = TimeInterval(raw) {
        controller.presenceIdleProvider = { idle }
      } else {
        controller.presenceIdleProvider = { UserInputPresence.secondsSinceLastInput() }
      }
      return [
        "idle_sample": controller.presenceIdleProvider().map { String($0) } ?? "nil",
        "warm_deferred": controller.warmDeferredForUserAway ? "true" : "false",
        "session_active": controller.session != nil ? "true" : "false",
      ]
    }

    registerResponseContextActions()
  }
}
