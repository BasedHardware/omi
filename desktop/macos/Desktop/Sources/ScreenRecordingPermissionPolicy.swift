enum ScreenRecordingPermissionPolicy {
  /// The UI permission badge mirrors macOS TCC, not capture-engine diagnostics.
  static func uiPermissionGranted(tccGranted: Bool) -> Bool {
    tccGranted
  }

  /// Capture-engine failures must never turn the permission row red. A denied
  /// TCC preflight already makes the permission state missing on its own.
  static func shouldMarkCaptureKitBroken(tccGranted: Bool) -> Bool {
    false
  }

  /// A screen-recording grant only takes effect at process launch (the window
  /// server evaluates it once per connection). Granted now but not at launch
  /// means capture stays dead until the app relaunches — that is the only
  /// case where offering "Reopen Omi" is correct. In particular, an app that
  /// already relaunched after the grant must never be asked to reopen again.
  static func needsRelaunchToApply(grantedNow: Bool, grantedAtLaunch: Bool) -> Bool {
    grantedNow && !grantedAtLaunch
  }

  /// ScreenCaptureKit talks to the window-server connection opened at launch.
  /// A TCC grant that landed after that connection was created is visible to
  /// `CGPreflightScreenCaptureAccess` and dead to SCK; calling
  /// `SCShareableContent` / `SCScreenshotManager` in that window aborts instead
  /// of throwing. Only invoke SCK when this process launched with the grant.
  static func shouldInvokeScreenCaptureKit(grantedAtLaunch: Bool) -> Bool {
    grantedAtLaunch
  }

  /// Whether a capture failure may terminate and relaunch the app to repair itself.
  ///
  /// Capture recovery restarts the process. That is a reasonable last resort for a granted
  /// install whose TCC state went stale, and it is wrong in the two cases below, where a
  /// failure is the expected state rather than a broken one:
  ///
  /// - **The grant is not live in this process.** ScreenCaptureKit is bound to the
  ///   window-server connection opened at launch, so capture cannot work until the next
  ///   launch no matter how many times we restart. The onboarding "Reopen Omi" prompt is the
  ///   one place that relaunch belongs.
  /// - **Onboarding is not finished.** A new Mac has not granted anything yet, so capture
  ///   fails by definition. Restarting there quits the app out from under someone who is
  ///   partway through a permission page — and because the "already recovered once" flag is
  ///   per process, the fresh process repeats it. David's first-run session took three of
  ///   these in 45 seconds (0.12.187, macOS 15.1).
  static func mayRestartToRecoverCapture(grantedAtLaunch: Bool, onboardingComplete: Bool) -> Bool {
    grantedAtLaunch && onboardingComplete
  }
}

/// Policy for a capture attempt that ScreenCaptureKit rejected with "user declined
/// TCCs" — macOS re-confirming consent for app-built content filters
/// (`SCContentFilter(desktopIndependentWindow:)`), with the underlying grant intact.
///
/// The contract this encodes: a declined consent is TERMINAL for automatic capture.
/// Every retried capture opens a fresh session, and macOS re-arms the consent dialog
/// per session — the 3 s tick plus the 5 s recovery poll turned one due re-confirmation
/// into three dialogs in ten minutes on a live machine. So outside the known special
/// system modes, the only correct moves are: stop capturing, tell the user once, and
/// resume only on a human-scale signal (notification click, Settings toggle, app
/// re-activation).
enum ScreenCaptureConsentPolicy {
  enum DeclinedCaptureAction: Equatable {
    /// Exposé / Mission Control / Notification Center produce the same "declined TCCs"
    /// error transiently while they own the screen. That is not a consent event; keep
    /// the normal timer armed and wait for the mode to end.
    case waitForSpecialModeToEnd
    /// The consent dialog is (or was) genuinely on screen. Stop monitoring — no timer
    /// retry of any cadence — and surface at most one repair notification per session
    /// (re-activation restarts monitoring anyway, and a banner per attempt is spam).
    case stopAndNotify(shouldNotify: Bool)
  }

  static func actionForDeclinedCapture(
    isInSpecialSystemMode: Bool,
    hasNotifiedThisSession: Bool
  ) -> DeclinedCaptureAction {
    if isInSpecialSystemMode {
      return .waitForSpecialModeToEnd
    }
    return .stopAndNotify(shouldNotify: !hasNotifiedThisSession)
  }
}
