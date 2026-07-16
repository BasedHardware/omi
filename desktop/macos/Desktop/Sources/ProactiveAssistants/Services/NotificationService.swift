import AppKit
import Foundation
import UserNotifications

/// Sound options for notifications
enum NotificationSound {
  case `default`
  case focusLost
  case focusRegained
  case none

  var unSound: UNNotificationSound? {
    switch self {
    case .default:
      return .default
    case .focusLost, .focusRegained:
      // Custom sounds are played manually via NSSound (see playCustomSound)
      // because UNNotificationSound(named:) can't find SPM-bundled resources.
      return nil
    case .none:
      return nil
    }
  }

  /// Play the custom sound manually from the SPM resource bundle.
  func playCustomSound() {
    let filename: String
    switch self {
    case .focusLost:
      filename = "focus-lost"
    case .focusRegained:
      filename = "focus-regained"
    default:
      return
    }

    guard let url = Bundle.resourceBundle.url(forResource: filename, withExtension: "aiff") else {
      log("NotificationSound: Could not find \(filename).aiff in bundle")
      return
    }

    guard let sound = NSSound(contentsOf: url, byReference: true) else {
      log("NotificationSound: Could not load sound from \(url)")
      return
    }

    sound.play()
  }
}

@MainActor
class NotificationService: NSObject, UNUserNotificationCenterDelegate {
  static let shared = NotificationService(registerWithSystemNotificationCenter: true)

  /// Category ID for notifications that track dismissal
  private static let trackableCategoryId = "omi.trackable"

  /// Category ID for screen capture reset notifications with action button
  private static let screenCaptureResetCategoryId = "omi.screen_capture_reset"

  /// Action ID for the "Reset Now" button
  private static let resetNowActionId = "RESET_SCREEN_CAPTURE_NOW"

  /// Title that identifies screen capture reset notifications
  static let screenCaptureResetTitle = "Screen Recording Needs Reset"

  /// UserDefaults key that records whether the screen capture reset notification
  /// has already been shown in the current broken-capture episode. Cleared by
  /// `AppState.checkScreenRecordingPermission()` as soon as capture recovers,
  /// so a new breakage re-notifies exactly once.
  static let screenCaptureResetShownKey = "screenCaptureResetNotificationShown"

  /// UserDefaults key mirroring the user's `notification_frequency` setting from the backend.
  /// 0=Off (default), 1=Minimal, 2=Low, 3=Balanced, 4=High, 5=Maximum.
  /// The Settings page writes this on load and on slider change; `sendNotification`
  /// reads it synchronously to throttle proactive notifications.
  static let frequencyDefaultsKey = "notification_frequency"

  /// One-time migration flag: when set, the notifications-off-by-default migration
  /// has already run for this install, so we never re-disable a user who opted back in.
  static let offByDefaultMigrationKey = "notificationsOffByDefaultMigrationDone"

  /// UserDefaults key mirroring the master `notifications_enabled` toggle from the backend.
  /// The Settings page writes it on load and on toggle change; `sendNotification` reads it
  /// synchronously so proactive notifications are suppressed the moment the user turns the
  /// master Notifications switch off — without waiting for a backend round-trip. Defaults to
  /// `true` when the key is absent (first run before the Settings page hydrates).
  static let masterEnabledDefaultsKey = "notifications_enabled"

  /// Default level used when the key has never been written (e.g. first run before
  /// the Settings page has hydrated from the backend). Mirrors the backend default.
  /// Proactive notifications are OFF by default — users opt in via the Settings slider.
  private static let defaultFrequencyLevel = 0

  private struct NotificationMetadata {
    let title: String
    let assistantId: String
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  }

  /// Interaction provenance is bound to the exact authorization generation
  /// that delivered the banner, not only to a reusable user ID.
  private var notificationMetadata: [String: NotificationMetadata] = [:]

  /// Insertion order of `notificationMetadata` keys, used to evict the oldest entries.
  /// Metadata is only removed on user interaction (`didReceive`); a functional banner
  /// the user never touches (ages out / is cleared without a dismiss action) would
  /// otherwise leak its entry for the life of the process. Bounded FIFO eviction caps
  /// the growth.
  private var notificationMetadataOrder: [String] = []
  private static let maxNotificationMetadata = 200

  /// Evict oldest ids from `order`/`store` until `order.count <= max`.
  /// `nonisolated static` + generic so the FIFO eviction policy is synchronously
  /// unit-testable without hopping the main actor.
  nonisolated static func evictOldestMetadata<V>(order: inout [String], store: inout [String: V], max: Int) {
    guard order.count > max else { return }
    let removeCount = order.count - max
    for id in order.prefix(removeCount) { store.removeValue(forKey: id) }
    order.removeFirst(removeCount)
  }

  /// Last time we triggered a notification repair (debounce to avoid hammering lsregister)
  private var lastRepairAttempt: Date?

  /// Last proactive-notification timestamp per assistantId. Used by the frequency
  /// throttle so one chatty assistant cannot starve another.
  private var lastNotificationAt: [String: Date] = [:]

  /// Last proactive-notification timestamp across all assistants. Used by the
  /// frequency throttle as a global rate limit.
  private var lastNotificationAtGlobal: Date?
  private var throttleOwnerSnapshot: RuntimeOwnerAuthorizationSnapshot?
  private var ownerChangeObserver: NSObjectProtocol?

  /// The system notification center raises an Objective-C exception when
  /// constructed from SwiftPM's command-line test host. Owner-bound policy
  /// tests inject `false`; production always uses the shared `true` instance.
  init(registerWithSystemNotificationCenter: Bool) {
    super.init()
    if registerWithSystemNotificationCenter {
      // Set ourselves as the delegate to show notifications even when app is in foreground
      UNUserNotificationCenter.current().delegate = self
      // Set up notification categories for tracking
      setupNotificationCategories()
    }
    ownerChangeObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated {
        self?.resetOwnerScopedState()
      }
    }
    if registerWithSystemNotificationCenter {
      // Track that delegate is ready
      AnalyticsManager.shared.notificationDelegateReady()
      log("NotificationService: Delegate initialized and ready")
    }
  }

  private func resetOwnerScopedState() {
    notificationMetadata.removeAll()
    notificationMetadataOrder.removeAll()
    lastNotificationAt.removeAll()
    lastNotificationAtGlobal = nil
    throttleOwnerSnapshot = nil
  }

  /// Set up notification categories to enable dismiss tracking
  private func setupNotificationCategories() {
    // Create a category that tracks custom dismiss action
    // This allows us to know when a user explicitly dismisses a notification
    let trackableCategory = UNNotificationCategory(
      identifier: Self.trackableCategoryId,
      actions: [],
      intentIdentifiers: [],
      options: [.customDismissAction]  // This enables didReceive callback on dismiss
    )

    // Create "Reset Now" action for screen capture reset notifications
    let resetNowAction = UNNotificationAction(
      identifier: Self.resetNowActionId,
      title: "Reset Now",
      options: [.foreground]  // Bring app to foreground when tapped
    )

    // Create category for screen capture reset with the action button
    let screenCaptureResetCategory = UNNotificationCategory(
      identifier: Self.screenCaptureResetCategoryId,
      actions: [resetNowAction],
      intentIdentifiers: [],
      options: [.customDismissAction]
    )

    UNUserNotificationCenter.current().setNotificationCategories([trackableCategory, screenCaptureResetCategory])
  }

  // MARK: - UNUserNotificationCenterDelegate

  // This allows notifications to be displayed even when the app is in the foreground
  nonisolated func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    willPresent notification: UNNotification,
    withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
  ) {
    let notificationId = notification.request.identifier
    let title = notification.request.content.title
    // Resolve owner provenance before presenting an already-scheduled banner;
    // an OS callback may arrive after the originating session signed out.
    Task { @MainActor in
      guard let metadata = self.notificationMetadata[notificationId],
        RuntimeOwnerIdentity.isAuthorizationCurrent(metadata.authorizationSnapshot)
      else {
        self.notificationMetadata.removeValue(forKey: notificationId)
        self.notificationMetadataOrder.removeAll { $0 == notificationId }
        completionHandler([])
        return
      }
      AnalyticsManager.shared.notificationWillPresent(notificationId: notificationId, title: title)
      // Show banner and badge; only include .sound if the notification has a sound attached.
      var options: UNNotificationPresentationOptions = [.banner, .badge]
      if notification.request.content.sound != nil {
        options.insert(.sound)
      }
      completionHandler(options)
    }
  }

  // Handle notification interactions (click or dismiss)
  nonisolated func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    didReceive response: UNNotificationResponse,
    withCompletionHandler completionHandler: @escaping () -> Void
  ) {
    let notificationId = response.notification.request.identifier

    Task { @MainActor in
      // Retrieve stored metadata
      let metadata = self.notificationMetadata[notificationId]
      guard let metadata,
        RuntimeOwnerIdentity.isAuthorizationCurrent(metadata.authorizationSnapshot)
      else {
        self.notificationMetadata.removeValue(forKey: notificationId)
        self.notificationMetadataOrder.removeAll { $0 == notificationId }
        return
      }
      let title = metadata.title
      let assistantId = metadata.assistantId

      switch response.actionIdentifier {
      case UNNotificationDefaultActionIdentifier:
        // User clicked/tapped the notification
        print("[\(assistantId)] Notification clicked: \(title)")
        AnalyticsManager.shared.notificationClicked(
          notificationId: notificationId,
          title: title,
          assistantId: assistantId,
          surface: "system_notification"
        )

        // If this is a screen capture reset notification, trigger the reset
        if title == Self.screenCaptureResetTitle {
          self.handleScreenCaptureResetAction(source: "notification_click")
        }

      case UNNotificationDismissActionIdentifier:
        // User explicitly dismissed the notification (X button, swipe, or Clear)
        print("[\(assistantId)] Notification dismissed: \(title)")
        AnalyticsManager.shared.notificationDismissed(
          notificationId: notificationId,
          title: title,
          assistantId: assistantId,
          surface: "system_notification"
        )

      case Self.resetNowActionId:
        // User clicked the "Reset Now" action button
        print("[\(assistantId)] Reset Now action clicked: \(title)")
        AnalyticsManager.shared.notificationClicked(
          notificationId: notificationId,
          title: title,
          assistantId: assistantId,
          surface: "system_notification"
        )
        self.handleScreenCaptureResetAction(source: "notification_action_button")

      default:
        // Custom action (if we add action buttons in the future)
        print("[\(assistantId)] Notification action: \(response.actionIdentifier)")
      }

      // Clean up metadata
      self.notificationMetadata.removeValue(forKey: notificationId)
      self.notificationMetadataOrder.removeAll { $0 == notificationId }
    }

    completionHandler()
  }

  /// Handle screen capture reset action from notification click or action button
  private func handleScreenCaptureResetAction(source: String) {
    log("Screen capture reset triggered from \(source)")
    AnalyticsManager.shared.screenCaptureResetClicked(source: source)
    ScreenCaptureService.resetScreenCapturePermissionAndRestart()
  }

  /// Send a notification via the floating bar, and optionally as a native macOS system banner.
  ///
  /// `deliverSystemBanner` defaults to `false` because proactive AI notifications are
  /// floating-bar only — users who disabled the floating bar reported clicking the
  /// top-right system banner and getting no conversation context, which was confusing.
  /// Functional notifications (Crisp support replies, screen-recording permission
  /// prompts with a repair action) must pass `deliverSystemBanner: true` so they
  /// still surface as a system banner — they either have no floating-bar equivalent
  /// or must reach the user even when the floating bar is hidden/snoozed.
  func sendNotification(
    ownerID: String,
    title: String,
    message: String,
    assistantId: String = "default",
    sound: NotificationSound = .default,
    context: FloatingBarNotificationContext? = nil,
    action: FloatingBarNotificationAction? = nil,
    screenshotData: Data? = nil,
    deliverSystemBanner: Bool = false,
    respectFrequency: Bool = true,
    authorizationSnapshot suppliedAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) {
    guard !ownerID.isEmpty,
      let authorizationSnapshot = suppliedAuthorizationSnapshot
        ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID),
      authorizationSnapshot.ownerID == ownerID,
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    else {
      log("NotificationService: rejecting notification from stale runtime owner")
      return
    }
    prepareOwnerScopedState(for: authorizationSnapshot)
    // Rate-limit the screen-capture reset notification to one per broken-capture
    // episode. The recovery loop in ProactiveAssistantsPlugin.attemptAutoReset
    // re-fires this on every session (soft-recovery + app restart), which buried
    // users in duplicate banners when a stale TCC csreq from an auto-update made
    // the capture path unrecoverable without a manual toggle in System Settings.
    // NOTE: only READ the "already shown" flag here. The flag is SET at actual
    // delivery time (just before showNotification below), NOT here — setting it
    // before the snooze/enabled/frequency gates meant that if any gate suppressed
    // this delivery (e.g. the user is snoozed when capture breaks), the flag was
    // still persisted, and since it is only cleared on capture RECOVERY — which
    // never happens while capture stays broken — every later retry hit this early
    // return and the "screen recording needs reset" notice was never delivered.
    if title == Self.screenCaptureResetTitle
      && UserDefaults.standard.bool(forKey: Self.screenCaptureResetShownKey)
    {
      log("NotificationService: suppressing duplicate screen capture reset notification")
      return
    }

    // Honor the floating-bar snooze for both the in-bar preview and the native
    // macOS banner — the user opted into "no notifications for 2h".
    if FloatingControlBarManager.shared.isSnoozed {
      log("NotificationService: suppressing notification because floating bar is snoozed")
      return
    }

    // Proactive notifications honor the master Notifications toggle. When the user
    // turns Notifications off in Settings, suppress the floating-bar popup and the
    // native banner entirely (#6778). Functional notifications (Crisp support replies,
    // screen-recording permission prompts, onboarding test) pass `respectFrequency: false`
    // to bypass this, matching the frequency gate below.
    if respectFrequency && !Self.areNotificationsEnabled() {
      log("NotificationService: suppressing \(assistantId) notification because notifications are disabled")
      return
    }

    // Proactive notifications honor the user's frequency setting. Functional
    // notifications (Crisp support replies, screen-recording permission prompts,
    // onboarding test) pass `respectFrequency: false` to bypass the gate.
    if respectFrequency
      && !shouldAllowProactiveNotification(
        assistantId: assistantId,
        authorizationSnapshot: authorizationSnapshot
      )
    {
      log("NotificationService: throttled \(assistantId) notification (frequency=\(Self.currentFrequencyLevel()))")
      return
    }

    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      log("NotificationService: owner changed before notification presentation")
      return
    }

    // Mark the screen-capture reset notice as shown only now that it has passed
    // every suppression gate and is actually being delivered — so a snoozed (or
    // otherwise gated) attempt does not permanently suppress it for the episode.
    if title == Self.screenCaptureResetTitle {
      UserDefaults.standard.set(true, forKey: Self.screenCaptureResetShownKey)
    }

    FloatingControlBarManager.shared.showNotification(
      ownerID: ownerID,
      title: title,
      message: message,
      assistantId: assistantId,
      sound: sound,
      context: context,
      action: action,
      screenshotData: screenshotData
    )

    // Default path: floating-bar only. Functional callers opt-in via
    // `deliverSystemBanner: true` (see the parameter doc above).
    guard deliverSystemBanner else { return }

    UNUserNotificationCenter.current().getNotificationSettings { [weak self] settings in
      Task { @MainActor in
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
          log("NotificationService: dropping stale-owner system notification")
          return
        }
        guard settings.authorizationStatus == .authorized else {
          log("Notification skipped (auth=\(settings.authorizationStatus.rawValue)): \(title)")

          // If auth reverted to notDetermined (not explicitly denied), trigger repair.
          // Debounce: at most once per 10 minutes to avoid hammering lsregister.
          if settings.authorizationStatus == .notDetermined {
            let now = Date()
            if self?.lastRepairAttempt == nil || now.timeIntervalSince(self?.lastRepairAttempt ?? .distantPast) > 600 {
              self?.lastRepairAttempt = now
              log("Notification auth is notDetermined at send time — triggering repair")
              AnalyticsManager.shared.notificationRepairTriggered(
                reason: "send_time_not_determined",
                previousStatus: "unknown",
                currentStatus: "notDetermined"
              )
              ProactiveAssistantsPlugin.repairNotificationRegistration()
            }
          }

          return
        }

        self?.deliverNotification(
          title: title,
          message: message,
          assistantId: assistantId,
          sound: sound,
          authorizationSnapshot: authorizationSnapshot
        )
      }
    }
  }

  /// The only delivery path for contextual task interruptions. Unlike the
  /// generic functional-notification API, this path exposes no bypass flag.
  @discardableResult
  func sendContextualTaskInterruption(
    _ candidate: TaskInterruptionCandidate,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    now: Date = Date(),
    calendar: Calendar = .current,
    ledgerPersistence: (any TaskInterruptionLedgerPersisting)? = nil
  ) -> TaskInterruptionGateTrace {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      return Self.staleOwnerGateTrace(candidate: candidate, now: now)
    }
    let ownerID = authorizationSnapshot.ownerID
    prepareOwnerScopedState(for: authorizationSnapshot)
    let configuration = ProactiveTaskInterruptionSettings.load()
    let environment = TaskInterruptionEnvironment(
      cohort: ProactiveTaskCohort.current,
      masterNotificationsEnabled: Self.areNotificationsEnabled(),
      frequencyEnabled: Self.currentFrequencyLevel() > 0,
      ambientFrequencyEligible: isProactiveNotificationEligible(
        assistantId: "task",
        now: now,
        authorizationSnapshot: authorizationSnapshot
      ),
      taskNotificationsEnabled: TaskAssistantSettings.shared.notificationsEnabled,
      focusSuppressed: FocusStorage.shared.currentStatus == .focused
        || ProactiveTaskInterruptionSettings.isFocusSuppressed,
      snoozed: FloatingControlBarManager.shared.isSnoozed,
      now: now,
      calendar: calendar
    )
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      return Self.staleOwnerGateTrace(candidate: candidate, now: now)
    }
    let proactiveTaskGate = ProactiveTaskInterruptionGate(
      persistence: ledgerPersistence ?? TaskInterruptionLedgerDefaults(ownerID: ownerID)
    )
    let trace = proactiveTaskGate.evaluate(
      candidate: candidate,
      configuration: configuration,
      environment: environment
    )
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      return Self.staleOwnerGateTrace(candidate: candidate, now: now)
    }
    AnalyticsManager.shared.proactiveTaskGateEvaluated(trace)
    guard trace.reason == .allowed else {
      log(
        "TaskInterruptionGate: suppressed recommendation=\(candidate.recommendationID) "
          + "reason=\(trace.reason.rawValue) cohort=\(trace.cohort.rawValue)"
      )
      return trace
    }

    let context = FloatingBarNotificationContext(
      sourceTitle: candidate.headline,
      assistantId: "task",
      sourceApp: nil,
      windowTitle: nil,
      contextSummary: candidate.whyNow,
      currentActivity: nil,
      reasoning: candidate.whyNow,
      detail: "recommendation_id=\(candidate.recommendationID)"
    )
    sendNotification(
      ownerID: ownerID,
      title: candidate.headline,
      message: "\(candidate.whyNow) · \(candidate.recommendedAction)",
      assistantId: "task",
      context: context,
      action: .openWhatMattersNow(recommendationID: candidate.recommendationID),
      authorizationSnapshot: authorizationSnapshot
    )
    return trace
  }

  private static func staleOwnerGateTrace(
    candidate: TaskInterruptionCandidate,
    now: Date
  ) -> TaskInterruptionGateTrace {
    TaskInterruptionGateTrace(
      candidate: candidate,
      environment: TaskInterruptionEnvironment(
        cohort: ProactiveTaskCohort.current,
        masterNotificationsEnabled: false,
        frequencyEnabled: false,
        ambientFrequencyEligible: false,
        taskNotificationsEnabled: false,
        focusSuppressed: false,
        snoozed: false,
        now: now,
        calendar: .current
      ),
      reason: .staleOwner
    )
  }

  private func deliverNotification(
    title: String,
    message: String,
    assistantId: String,
    sound: NotificationSound,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    let content = UNMutableNotificationContent()
    content.title = title
    content.body = message
    content.sound = sound.unSound

    // Use screen capture reset category for reset notifications (adds "Reset Now" button)
    if title == Self.screenCaptureResetTitle {
      content.categoryIdentifier = Self.screenCaptureResetCategoryId
    } else {
      content.categoryIdentifier = Self.trackableCategoryId  // Enable dismiss tracking
    }

    let notificationId = UUID().uuidString
    let request = UNNotificationRequest(
      identifier: notificationId,
      content: content,
      trigger: nil  // Deliver immediately
    )

    // Store metadata for later retrieval in delegate callbacks, capping growth so
    // never-interacted banners cannot leak entries unboundedly.
    storeNotificationMetadata(
      id: notificationId,
      title: title,
      assistantId: assistantId,
      authorizationSnapshot: authorizationSnapshot
    )

    // Play custom sound manually (SPM resources aren't found by UNNotificationSound)
    sound.playCustomSound()

    print("[\(assistantId)] Sending notification: \(title) - \(message)")
    UNUserNotificationCenter.current().add(request) { [weak self] error in
      if let error = error {
        print("Notification error: \(error)")
        logError("Notification error", error: error)
        // Clean up metadata on error
        Task { @MainActor in
          self?.notificationMetadata.removeValue(forKey: notificationId)
          self?.notificationMetadataOrder.removeAll { $0 == notificationId }
        }
      } else {
        print("Notification sent successfully")
        // Track notification sent
        Task { @MainActor in
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
          AnalyticsManager.shared.notificationSent(
            notificationId: notificationId,
            title: title,
            assistantId: assistantId,
            surface: "system_notification"
          )
        }
      }
    }
  }

  // MARK: - Frequency throttle

  /// One-time migration to make proactive notifications OFF by default for ALL users.
  /// Runs once per install (guarded by `offByDefaultMigrationKey`): sets the local
  /// frequency to Off and persists it to the backend so the choice sticks across
  /// devices and is reflected in Settings. Because it is guarded by the flag, a user
  /// who later turns notifications back on is never re-disabled on subsequent launches.
  /// Call early at launch, before any proactive assistant can fire.
  static func migrateToOffByDefaultIfNeeded() {
    guard !UserDefaults.standard.bool(forKey: Self.offByDefaultMigrationKey) else { return }
    UserDefaults.standard.set(0, forKey: Self.frequencyDefaultsKey)
    UserDefaults.standard.set(true, forKey: Self.offByDefaultMigrationKey)
    log("NotificationService: applied notifications-off-by-default migration (frequency=0)")
    guard AuthService.shared.isSignedIn else { return }
    Task {
      do {
        _ = try await APIClient.shared.updateNotificationSettings(enabled: nil, frequency: 0)
      } catch {
        logError(
          "NotificationService: off-by-default migration backend push failed", error: error)
      }
    }
  }

  /// Whether the master Notifications toggle is on. Reads the mirrored UserDefaults key,
  /// defaulting to `true` when absent so notifications are not accidentally suppressed
  /// before the Settings page has hydrated from the backend.
  static func areNotificationsEnabled() -> Bool {
    guard UserDefaults.standard.object(forKey: Self.masterEnabledDefaultsKey) != nil else {
      return true
    }
    return UserDefaults.standard.bool(forKey: Self.masterEnabledDefaultsKey)
  }

  /// Current frequency level from UserDefaults, clamped to [0, 5]. Falls back to
  /// `defaultFrequencyLevel` when the key is absent (first run before sync).
  static func currentFrequencyLevel() -> Int {
    guard UserDefaults.standard.object(forKey: Self.frequencyDefaultsKey) != nil else {
      return Self.defaultFrequencyLevel
    }
    let raw = UserDefaults.standard.integer(forKey: Self.frequencyDefaultsKey)
    return max(0, min(5, raw))
  }

  /// Minimum interval between proactive notifications for a given level.
  /// `nil` means no throttle (Maximum); `.infinity` means drop everything (Off).
  private static func minInterval(forLevel level: Int) -> TimeInterval? {
    switch level {
    case 0: return .infinity  // Off
    case 1: return 60 * 60  // Minimal:  1 per hour
    case 2: return 30 * 60  // Low:      1 per 30 min
    case 3: return 10 * 60  // Balanced: 1 per 10 min
    case 4: return 3 * 60  // High:     1 per 3 min
    default: return nil  // Maximum:  no throttle
    }
  }

  /// Decide whether a proactive notification from `assistantId` should be delivered.
  /// Records the timestamp when allowed so subsequent calls within the window are
  /// suppressed. Per-assistant + global limits combine so a chatty assistant cannot
  /// starve another.
  private func prepareOwnerScopedState(
    for authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) {
    if let throttleOwnerSnapshot,
      RuntimeOwnerIdentity.isAuthorizationCurrent(throttleOwnerSnapshot),
      throttleOwnerSnapshot == authorizationSnapshot
    {
      return
    }
    lastNotificationAt.removeAll()
    lastNotificationAtGlobal = nil
    throttleOwnerSnapshot = authorizationSnapshot
  }

  private func shouldAllowProactiveNotification(
    assistantId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    now: Date = Date()
  ) -> Bool {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return false }
    prepareOwnerScopedState(for: authorizationSnapshot)
    guard
      isProactiveNotificationEligible(
        assistantId: assistantId,
        now: now,
        authorizationSnapshot: authorizationSnapshot
      )
    else { return false }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return false }
    lastNotificationAt[assistantId] = now
    lastNotificationAtGlobal = now
    return true
  }

  private func storeNotificationMetadata(
    id: String,
    title: String,
    assistantId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    notificationMetadata[id] = NotificationMetadata(
      title: title,
      assistantId: assistantId,
      authorizationSnapshot: authorizationSnapshot
    )
    notificationMetadataOrder.append(id)
    Self.evictOldestMetadata(
      order: &notificationMetadataOrder,
      store: &notificationMetadata,
      max: Self.maxNotificationMetadata
    )
  }

  func recordNotificationMetadataForTesting(
    id: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) {
    storeNotificationMetadata(
      id: id,
      title: "test",
      assistantId: "test",
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func hasCurrentNotificationMetadataForTesting(id: String) -> Bool {
    guard let metadata = notificationMetadata[id],
      RuntimeOwnerIdentity.isAuthorizationCurrent(metadata.authorizationSnapshot)
    else {
      notificationMetadata.removeValue(forKey: id)
      notificationMetadataOrder.removeAll { $0 == id }
      return false
    }
    return true
  }

  func allowProactiveNotificationForTesting(
    assistantId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    now: Date
  ) -> Bool {
    shouldAllowProactiveNotification(
      assistantId: assistantId,
      authorizationSnapshot: authorizationSnapshot,
      now: now
    )
  }

  private func isProactiveNotificationEligible(
    assistantId: String,
    now: Date,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) -> Bool {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return false }
    prepareOwnerScopedState(for: authorizationSnapshot)
    let level = Self.currentFrequencyLevel()
    guard let interval = Self.minInterval(forLevel: level) else {
      return true  // Maximum
    }
    if interval == .infinity {
      return false  // Off
    }
    if let last = lastNotificationAtGlobal, now.timeIntervalSince(last) < interval {
      return false
    }
    if let last = lastNotificationAt[assistantId], now.timeIntervalSince(last) < interval {
      return false
    }
    return true
  }
}
// Updated Gemini API key in Codemagic secret — triggering release
