import AppKit
import Foundation
@preconcurrency import UserNotifications

/// Sendable wrapper for a `UNUserNotificationCenter` completion handler so the
/// non-Sendable closure can be captured across an isolation hop (e.g. into a
/// `@MainActor` `Task`) without a data-race diagnostic.
private struct UNCompletionHandlerBox: @unchecked Sendable {
  let value: (UNNotificationPresentationOptions) -> Void
  init(_ value: @escaping (UNNotificationPresentationOptions) -> Void) { self.value = value }
}

/// Sound options for notifications
enum NotificationSound {
  case `default`
  case none

  var unSound: UNNotificationSound? {
    switch self {
    case .default:
      return .default
    case .none:
      return nil
    }
  }

}

/// Named delivery intent for notifications that must not become Chat rows.
/// The default preserves the existing floating-bar presentation and journaling
/// path; system-banner-only callers still pass every owner, toggle, and
/// frequency gate in `NotificationService` before reaching UserNotifications.
enum NotificationDeliveryMode: Equatable {
  case standard
  case systemBannerOnly

  var presentsInFloatingBar: Bool { self == .standard }
  var requiresSystemBanner: Bool { self == .systemBannerOnly }
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
  /// `NotificationSettingsSyncCoordinator` writes this on hydrate and on slider change;
  /// `sendNotification` reads it synchronously to throttle proactive notifications.
  nonisolated static let frequencyDefaultsKey = "notification_frequency"
  static let settingsPendingSyncDefaultsKey = "notification_settings_pending_sync"
  static let settingsSyncRevisionDefaultsKey = "notification_settings_sync_revision"

  /// One-time migration flag: when set, the balanced-by-default re-enable migration
  /// has already run for this install, so we never re-enable a user who turns
  /// notifications off after the migration.
  nonisolated static let balancedByDefaultMigrationKey = "notificationsBalancedByDefaultMigrationDone"

  /// Frequency level the re-enable migration applies (3 = Balanced).
  nonisolated static let balancedFrequencyLevel = 3

  /// UserDefaults key mirroring the master `notifications_enabled` toggle from the backend.
  /// `NotificationSettingsSyncCoordinator` writes it on hydrate and on toggle change;
  /// `sendNotification` reads it synchronously so proactive notifications are suppressed
  /// the moment the user turns the master Notifications switch off — without waiting for
  /// a backend round-trip. Defaults to `true` when the key is absent (first run before
  /// the coordinator hydrates).
  static let masterEnabledDefaultsKey = "notifications_enabled"

  /// Default level used when the key has never been written (e.g. first run before
  /// the Settings page has hydrated from the backend). Mirrors the backend default.
  /// Kept at 0 (fail-closed) only for the window before `migrateToBalancedDefaultIfNeeded`
  /// writes the key at launch; the effective default is Balanced via that migration.
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
    let completion = UNCompletionHandlerBox(completionHandler)
    Task { @MainActor in
      guard let metadata = self.notificationMetadata[notificationId],
        RuntimeOwnerIdentity.isAuthorizationCurrent(metadata.authorizationSnapshot)
      else {
        self.notificationMetadata.removeValue(forKey: notificationId)
        self.notificationMetadataOrder.removeAll { $0 == notificationId }
        completion.value([])
        return
      }
      AnalyticsManager.shared.notificationWillPresent(notificationId: notificationId, title: title)
      // Show banner and badge; only include .sound if the notification has a sound attached.
      var options: UNNotificationPresentationOptions = [.banner, .badge]
      if notification.request.content.sound != nil {
        options.insert(.sound)
      }
      completion.value(options)
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

        switch Self.openAction(assistantId: assistantId, title: title) {
        case .resetScreenCapture:
          self.handleScreenCaptureResetAction(source: "notification_click")
        case .openMainChat:
          // The same reveal-and-land-on-chat path the floating bar's
          // "Continue in Omi" affordance uses; the chat transcript there
          // carries the meeting-notes card with the conversation link.
          AppDelegate.summonWindowTarget()?.openMainAppChat()
        case .none:
          break
        }

      case UNNotificationDismissActionIdentifier:
        // User explicitly dismissed the notification (X button, swipe, or Clear)
        print("[\(assistantId)] Notification dismissed: \(title)")
        AnalyticsManager.shared.notificationDismissed(
          notificationId: notificationId,
          title: title,
          assistantId: assistantId,
          surface: "system_notification",
          dismissalKind: .user
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

  /// What tapping a delivered banner does, beyond recording that it was tapped.
  ///
  /// Tapping a notification is a request to *see the thing it is about*. A banner whose tap only
  /// fires analytics is worse than no banner: it interrupts, then refuses. This names the cases
  /// where the app owes the user a destination.
  enum OpenAction: Equatable {
    /// Nothing to open — the notification's content was the whole message.
    case none
    /// The screen-recording repair, which is an action rather than a page.
    case resetScreenCapture
    /// The main-window chat surface, where the meeting-notes card (with its
    /// conversation link) was materialized.
    case openMainChat
  }

  /// Resolve the tap destination from the notification's provenance.
  ///
  /// The screen-capture case matches on title because that is how its own delivery gates
  /// (`screenCaptureResetShownKey`) already identify it — changing that identity is a separate
  /// change with its own suppression-state migration.
  static func openAction(assistantId: String, title: String) -> OpenAction {
    if title == screenCaptureResetTitle { return .resetScreenCapture }
    if assistantId == MeetingActionItemBannerPolicy.assistantID { return .openMainChat }
    return .none
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
  /// floating-bar cards by default — a bare top-right system banner with no conversation
  /// context was previously reported as confusing. Functional notifications (screen-recording
  /// permission prompts with a repair action) must pass `deliverSystemBanner: true` so they
  /// still surface as a system banner — they either have no floating-bar equivalent
  /// or must reach the user even when the floating bar is hidden/snoozed.
  ///
  /// Only the Notifications master toggle (and frequency gate) decide whether a
  /// notification is owed. Disabling the Ask Omi bar (`askOmiBarEnabled`) hides the
  /// persistent bar UI only: delivery still uses the existing temp-show path, which
  /// pops the card and re-hides afterwards. `FloatingBarNotificationPreviewPolicy`
  /// forces a system banner once the user has explicitly muted in-bar previews
  /// (`ShortcutSettings.floatingBarNotificationPreviewsEnabled == false`) while the
  /// Floating Bar is still enabled, so that opt-out is never fully silenced (#6765).
  /// Previews muted *and* the bar disabled still temp-shows the card rather than
  /// going silent or falling back to a contentless banner. That temp-show is a
  /// proactive-notification surface only: a caller passing `deliverSystemBanner: true`
  /// while the bar is disabled keeps its banner instead, because a card on a bar the
  /// user turned off auto-dismisses in seconds and cannot carry a functional notice
  /// (the screen-recording repair prompt is delivered once per broken-capture episode).
  /// `insightDeliveryID`, when present, is an opaque Advice correlation key. It records only
  /// bounded delivery outcomes and never carries notification text or window context.
  func sendNotification(
    ownerID: String,
    title: String,
    message: String,
    assistantId: String = "default",
    sound: NotificationSound = .default,
    context: FloatingBarNotificationContext? = nil,
    action: FloatingBarNotificationAction? = nil,
    suggestionTelemetryIdentity: SuggestionAssistantTelemetry.NotificationIdentity? = nil,
    insightDeliveryID: UUID? = nil,
    screenshotData: Data? = nil,
    deliverSystemBanner: Bool = false,
    deliveryMode: NotificationDeliveryMode = .standard,
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
      recordInsightDeliveryOutcome(
        insightDeliveryID,
        outcome: .suppressed,
        reason: .staleOwner
      )
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
    // this delivery (e.g. notifications are disabled when capture breaks), the flag was
    // still persisted, and since it is only cleared on capture RECOVERY — which
    // never happens while capture stays broken — every later retry hit this early
    // return and the "screen recording needs reset" notice was never delivered.
    if title == Self.screenCaptureResetTitle
      && UserDefaults.standard.bool(forKey: Self.screenCaptureResetShownKey)
    {
      log("NotificationService: suppressing duplicate screen capture reset notification")
      return
    }

    // Hiding the floating bar ("Hide for 2 hours") and disabling it are both statements
    // about the BAR, not about notifications: an hour of a movie with the bar hidden or
    // off must still nudge. Delivery goes through the existing temp-show path, which pops
    // the card and re-hides the bar afterwards. It deliberately does not gate here.

    // Proactive notifications honor the master Notifications toggle. When the user
    // turns Notifications off in Settings, suppress the floating-bar popup and the
    // native banner entirely (#6778). Functional notifications (Crisp support replies,
    // screen-recording permission prompts, onboarding test) pass `respectFrequency: false`
    // to bypass this, matching the frequency gate below.
    if respectFrequency && !Self.areNotificationsEnabled() {
      log("NotificationService: suppressing \(assistantId) notification because notifications are disabled")
      recordInsightDeliveryOutcome(
        insightDeliveryID,
        outcome: .suppressed,
        reason: .masterNotificationsDisabled
      )
      return
    }

    // Proactive notifications honor the user's frequency setting. Functional
    // notifications (Crisp support replies, screen-recording permission prompts,
    // onboarding test) pass `respectFrequency: false` to bypass the gate.
    if respectFrequency
      && !isProactiveNotificationEligible(
        assistantId: assistantId,
        now: Date(),
        authorizationSnapshot: authorizationSnapshot
      )
    {
      log("NotificationService: throttled \(assistantId) notification (frequency=\(Self.currentFrequencyLevel()))")
      recordInsightDeliveryOutcome(
        insightDeliveryID,
        outcome: .suppressed,
        reason: Self.currentFrequencyLevel() == 0 ? .frequencyOff : .frequencyThrottled
      )
      return
    }

    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      log("NotificationService: owner changed before notification presentation")
      recordInsightDeliveryOutcome(
        insightDeliveryID,
        outcome: .suppressed,
        reason: .staleOwner
      )
      return
    }

    // `respectFrequency` is the existing proactive/functional split: assistants leave it
    // true; functional notices (onboarding test, screen-repair prompts) pass false and
    // must never be spoken.
    let speech = NotificationSpeechOnDelivery(message: message, isProactive: respectFrequency)
    let recordPresentation = { [weak self] in
      speech.notificationWasPresented()
      if respectFrequency {
        self?.recordProactiveNotificationPresented(
          assistantId: assistantId,
          authorizationSnapshot: authorizationSnapshot)
      }
      if title == Self.screenCaptureResetTitle {
        UserDefaults.standard.set(true, forKey: Self.screenCaptureResetShownKey)
      }
    }

    let previewsEnabled = ShortcutSettings.shared.floatingBarNotificationPreviewsEnabled
    let floatingBarEnabled = FloatingControlBarManager.shared.isEnabled
    let floatingBarPreviewEnabled =
      deliveryMode.presentsInFloatingBar
      && FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
        previewsEnabled: previewsEnabled, floatingBarEnabled: floatingBarEnabled,
        deliverSystemBanner: deliverSystemBanner
      )

    var floatingBarMayDeliver = false
    var floatingBarQueued = false
    if floatingBarPreviewEnabled {
      let presentation = FloatingControlBarManager.shared.showNotification(
        ownerID: ownerID,
        title: title,
        message: message,
        assistantId: assistantId,
        sound: sound,
        context: context,
        action: action,
        suggestionTelemetryIdentity: suggestionTelemetryIdentity,
        insightDeliveryID: insightDeliveryID,
        screenshotData: screenshotData,
        onPresented: recordPresentation
      )
      switch presentation {
      case .presented:
        floatingBarMayDeliver = true
      case .queued:
        // Queue admission is not user-visible delivery. Leave the identity unresolved so a
        // later presentation boundary (or a system-banner fallback) can emit the terminal event.
        floatingBarQueued = true
      case .suppressed:
        // Unreachable today (a hidden or disabled bar presents via temp-show instead of
        // suppressing), kept for the shared result type; label with the surface, not a
        // retired reason.
        recordInsightDeliveryOutcome(insightDeliveryID, outcome: .suppressed, reason: .floatingBarUnavailable)
        return
      case .rejectedOwnerChange:
        recordInsightDeliveryOutcome(
          insightDeliveryID,
          outcome: .suppressed,
          reason: .staleOwner
        )
        return
      case .windowUnavailable:
        break
      }
    }

    // Default path: floating-bar card (including temp-show when the bar is disabled).
    // Functional callers opt-in via `deliverSystemBanner: true` (see the parameter
    // doc above). When the user explicitly muted in-bar previews (bar still enabled),
    // fall back to the system banner so the notification is never fully silenced.
    let shouldDeliverSystemBanner =
      deliveryMode.requiresSystemBanner
      || FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBannerAfterFloatingBar(
        previewsEnabled: previewsEnabled, floatingBarEnabled: floatingBarEnabled,
        deliverSystemBanner: deliverSystemBanner,
        floatingBarAccepted: floatingBarMayDeliver || floatingBarQueued
      )
    guard shouldDeliverSystemBanner else {
      if !floatingBarMayDeliver && !floatingBarQueued {
        // Genuine no-surface failure (window creation / presentation never started).
        // Bar-disabled is no longer a suppression reason; that path temp-shows.
        recordInsightDeliveryOutcome(
          insightDeliveryID,
          outcome: .failed,
          reason: .noDeliverySurface
        )
      }
      return
    }

    // Freeze the presentation decision before crossing the UserNotifications callback boundary;
    // @Sendable MainActor closures must not capture mutable local state.
    let floatingBarDelivered = floatingBarMayDeliver
    let floatingBarHasQueued = floatingBarQueued
    UserNotificationCallbackBridge.authorizationStatus { [weak self] authorizationStatus in
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
        log("NotificationService: dropping stale-owner system notification")
        self?.recordInsightDeliveryOutcome(
          insightDeliveryID,
          outcome: .suppressed,
          reason: .staleOwner
        )
        return
      }
      guard authorizationStatus == .authorized else {
        log("Notification skipped (auth=\(authorizationStatus.rawValue)): \(title)")

        if !floatingBarDelivered && !floatingBarHasQueued {
          self?.recordInsightDeliveryOutcome(
            insightDeliveryID,
            outcome: .suppressed,
            reason: .systemAuthorizationDenied
          )
        }

        // Sending an assistant notification is not consent to change TCC or
        // LaunchServices state. A user can repair notification access from
        // Settings; background delivery simply remains unavailable.
        return
      }

      self?.deliverNotification(
        title: title,
        message: message,
        assistantId: assistantId,
        sound: sound,
        authorizationSnapshot: authorizationSnapshot,
        insightDeliveryID: floatingBarDelivered ? nil : insightDeliveryID,
        insightFailureDeliveryID: (floatingBarDelivered || floatingBarHasQueued) ? nil : insightDeliveryID,
        onPresented: recordPresentation
      )
    }
  }

  /// Presentation seam for the flag-on context director. Budget/dedup live in the
  /// durable ledger; this method still re-checks floating-preview policy so a muted
  /// in-bar preview (bar still enabled) falls back to a system banner, and a
  /// disabled bar still temp-shows the card, instead of burning quota invisibly.
  @discardableResult
  func contextDirectorPresentationPreflight(ownerID: String) async -> OwnerBoundNotificationPresentationResult {
    guard !ownerID.isEmpty,
      let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID),
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    else { return .rejectedOwnerChange }
    guard contextDirectorMayPresent(authorizationSnapshot: authorizationSnapshot, now: Date()) else {
      return .suppressed
    }

    let previewsEnabled = ShortcutSettings.shared.floatingBarNotificationPreviewsEnabled
    let floatingBarEnabled = FloatingControlBarManager.shared.isEnabled
    if FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
      previewsEnabled: previewsEnabled,
      floatingBarEnabled: floatingBarEnabled,
      deliverSystemBanner: false)
    {
      return FloatingControlBarManager.shared.contextNotificationPreflight(
        ownerID: ownerID,
        authorizationSnapshot: authorizationSnapshot)
    }
    guard
      FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
        previewsEnabled: previewsEnabled,
        floatingBarEnabled: floatingBarEnabled,
        deliverSystemBanner: false)
    else { return .suppressed }

    let settings = await withCheckedContinuation { continuation in
      UserNotificationCallbackBridge.notificationSettings { settings in
        continuation.resume(returning: settings)
      }
    }
    guard
      NotificationPermissionPolicy.hasVisibleAlertSurface(
        status: settings.authorizationStatus,
        alertStyle: settings.alertStyle)
    else { return .suppressed }
    return .queued
  }

  @discardableResult
  func presentContextDirectorNotification(
    ownerID: String,
    title: String,
    message: String,
    decisionType: String,
    context: FloatingBarNotificationContext,
    onPresented: (() -> Void)? = nil,
    onDropped: (() -> Void)? = nil
  ) -> OwnerBoundNotificationPresentationResult {
    guard !ownerID.isEmpty,
      let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID),
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
    else {
      onDropped?()
      return .rejectedOwnerChange
    }
    guard contextDirectorMayPresent(authorizationSnapshot: authorizationSnapshot, now: Date()) else {
      onDropped?()
      return .suppressed
    }

    let previewsEnabled = ShortcutSettings.shared.floatingBarNotificationPreviewsEnabled
    let floatingBarEnabled = FloatingControlBarManager.shared.isEnabled
    let showInBar = FloatingBarNotificationPreviewPolicy.shouldShowInBarPreview(
      previewsEnabled: previewsEnabled, floatingBarEnabled: floatingBarEnabled,
      deliverSystemBanner: false)
    let deliverSystemBanner = FloatingBarNotificationPreviewPolicy.shouldDeliverSystemBanner(
      previewsEnabled: previewsEnabled, floatingBarEnabled: floatingBarEnabled, deliverSystemBanner: false)

    let speech = NotificationSpeechOnDelivery(message: message, isProactive: true)
    let recordPresented = { [weak self] in
      speech.notificationWasPresented()
      self?.recordProactiveNotificationPresented(
        assistantId: "context-director",
        authorizationSnapshot: authorizationSnapshot)
      onPresented?()
    }

    if showInBar {
      return FloatingControlBarManager.shared.showNotification(
        ownerID: ownerID,
        title: title,
        message: message,
        assistantId: "context-director",
        sound: .default,
        kind: ProactiveNotificationKind.from(decisionType: decisionType),
        context: context,
        authorizationSnapshot: authorizationSnapshot,
        onPresented: recordPresented,
        onDropped: onDropped)
    }

    guard deliverSystemBanner else {
      onDropped?()
      return .suppressed
    }

    UserNotificationCallbackBridge.notificationSettings { [weak self] settings in
      guard let self,
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
        self.contextDirectorMayPresent(authorizationSnapshot: authorizationSnapshot, now: Date()),
        NotificationPermissionPolicy.hasVisibleAlertSurface(
          status: settings.authorizationStatus,
          alertStyle: settings.alertStyle)
      else {
        onDropped?()
        return
      }
      self.deliverNotification(
        title: title,
        message: message,
        assistantId: "context-director",
        sound: .default,
        authorizationSnapshot: authorizationSnapshot,
        onPresented: recordPresented,
        onDropped: onDropped
      )
    }
    return .queued
  }

  private func contextDirectorMayPresent(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    now: Date
  ) -> Bool {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return false }
    let level = Self.currentFrequencyLevel()
    let gate = ContextDeliveryGateInput(
      masterEnabled: Self.areNotificationsEnabled(),
      frequencyLevel: level,
      paywalled: AppState.isPaywalledEffective,
      cooldownSeconds: ContextDeliveryBudget.cooldownSeconds(frequencyLevel: level)
    )
    guard ContextDeliveryBudget.freeGate(input: gate) == .allowed else { return false }
    return isProactiveNotificationEligible(
      assistantId: "context-director",
      now: now,
      authorizationSnapshot: authorizationSnapshot)
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
      focusSuppressed: ProactiveTaskInterruptionSettings.isFocusSuppressed,
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
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    insightDeliveryID: UUID? = nil,
    insightFailureDeliveryID: UUID? = nil,
    onPresented: (() -> Void)? = nil,
    onDropped: (() -> Void)? = nil
  ) {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      recordInsightDeliveryOutcome(insightFailureDeliveryID, outcome: .suppressed, reason: .staleOwner)
      onDropped?()
      return
    }
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

    print("[\(assistantId)] Sending notification: \(title) - \(message)")
    UserNotificationCallbackBridge.add(request) { [weak self] result in
      if let errorDescription = result.errorDescription {
        print("Notification error: \(errorDescription)")
        log("Notification error: \(errorDescription)")
        // Clean up metadata on error
        self?.notificationMetadata.removeValue(forKey: notificationId)
        self?.notificationMetadataOrder.removeAll { $0 == notificationId }
        self?.recordInsightDeliveryOutcome(
          insightFailureDeliveryID,
          outcome: .failed,
          reason: .systemDeliveryFailed
        )
        onDropped?()
      } else {
        print("Notification sent successfully")
        // Track notification sent
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
          self?.recordInsightDeliveryOutcome(insightDeliveryID, outcome: .suppressed, reason: .staleOwner)
          onDropped?()
          return
        }
        self?.recordInsightDeliveryOutcome(
          insightDeliveryID,
          outcome: .delivered,
          reason: .systemBannerDelivered,
          surface: .systemNotification
        )
        AnalyticsManager.shared.notificationSent(
          notificationId: notificationId,
          title: title,
          assistantId: assistantId,
          surface: "system_notification"
        )
        onPresented?()
      }
    }
  }

  private func recordInsightDeliveryOutcome(
    _ deliveryID: UUID?,
    outcome: InsightAssistantTelemetry.Outcome,
    reason: InsightAssistantTelemetry.Reason,
    surface: InsightAssistantTelemetry.Surface? = nil
  ) {
    guard let deliveryID else { return }
    AnalyticsManager.shared.insightAssistantDeliveryOutcome(
      outcome,
      reason: reason,
      deliveryID: deliveryID,
      surface: surface
    )
  }

  // MARK: - Frequency throttle

  /// One-time migration to re-enable proactive notifications at Balanced for users the
  /// notifications-off-by-default migration (`48239de8`) turned off. A user at Off — or a
  /// fresh install with no stored level — moves to Balanced; a user who opted in to any
  /// other level keeps it. Per-assistant toggles are not touched, so only the categories
  /// that default on (Live Suggestions, Insight) fire; Task and Memory stay opt-in.
  /// Because it is guarded by `balancedByDefaultMigrationKey`, a user who turns
  /// notifications off after the migration is never re-enabled on subsequent launches.
  /// Call early at launch, before any proactive assistant can fire.
  static func migrateToBalancedDefaultIfNeeded() {
    guard let target = applyBalancedDefaultMigration(defaults: .standard) else { return }
    log("NotificationService: applied balanced-by-default migration (frequency=\(target))")
    // Route the backend push through the pending-sync journal and the durable
    // coordinator: a failed push is retried with bounded backoff until the server
    // confirms, instead of waiting for a Settings load, and a slow launch push can
    // never land after — and overwrite — a frequency change the user makes right
    // after startup.
    let revision = beginNotificationSettingsSync()
    NotificationSettingsSyncCoordinator.shared.enqueue(
      enabled: nil, frequency: target, revision: revision)
  }

  /// Local half of the balanced-by-default migration, split from the backend push so the
  /// decision is synchronously unit-testable. Returns the level to push to the backend,
  /// or nil when nothing changed (already migrated, or the user opted in to another level).
  @discardableResult
  nonisolated static func applyBalancedDefaultMigration(defaults: UserDefaults) -> Int? {
    guard !defaults.bool(forKey: Self.balancedByDefaultMigrationKey) else { return nil }
    defaults.set(true, forKey: Self.balancedByDefaultMigrationKey)
    // The raw stored value, not `currentFrequencyLevel()`: an absent key (fresh install)
    // must migrate so the level is written locally AND to the backend — otherwise the
    // backend's off default would hydrate 0 over the in-memory fallback later.
    if defaults.object(forKey: Self.frequencyDefaultsKey) != nil,
      defaults.integer(forKey: Self.frequencyDefaultsKey) != 0
    {
      return nil
    }
    defaults.set(Self.balancedFrequencyLevel, forKey: Self.frequencyDefaultsKey)
    return Self.balancedFrequencyLevel
  }

  /// Whether the master Notifications toggle is on. Reads the mirrored UserDefaults key,
  /// defaulting to `true` when absent so notifications are not accidentally suppressed
  /// before the coordinator has hydrated from the backend. The delivery gate never
  /// consults the network.
  static func areNotificationsEnabled(defaults: UserDefaults = .standard) -> Bool {
    guard defaults.object(forKey: Self.masterEnabledDefaultsKey) != nil else {
      return true
    }
    return defaults.bool(forKey: Self.masterEnabledDefaultsKey)
  }

  /// Current frequency level from UserDefaults, clamped to [0, 5]. Falls back to
  /// `defaultFrequencyLevel` when the key is absent (first run before sync).
  static func currentFrequencyLevel(defaults: UserDefaults = .standard) -> Int {
    guard defaults.object(forKey: Self.frequencyDefaultsKey) != nil else {
      return Self.defaultFrequencyLevel
    }
    let raw = defaults.integer(forKey: Self.frequencyDefaultsKey)
    return max(0, min(5, raw))
  }

  @discardableResult
  static func beginNotificationSettingsSync(defaults: UserDefaults = .standard) -> Int {
    let revision = defaults.integer(forKey: settingsSyncRevisionDefaultsKey) &+ 1
    defaults.set(revision, forKey: settingsSyncRevisionDefaultsKey)
    defaults.set(true, forKey: settingsPendingSyncDefaultsKey)
    return revision
  }

  static func completeNotificationSettingsSync(
    revision: Int,
    defaults: UserDefaults = .standard
  ) {
    guard defaults.integer(forKey: settingsSyncRevisionDefaultsKey) == revision else { return }
    defaults.set(false, forKey: settingsPendingSyncDefaultsKey)
  }

  static func hasPendingNotificationSettingsSync(defaults: UserDefaults = .standard) -> Bool {
    defaults.bool(forKey: settingsPendingSyncDefaultsKey)
  }

  static func shouldPreserveLocalNotificationSettings(
    revisionAtLoadStart: Int,
    currentRevision: Int,
    pendingAtLoadStart: Bool,
    pendingNow: Bool
  ) -> Bool {
    pendingAtLoadStart || pendingNow || currentRevision != revisionAtLoadStart
  }

  /// Minimum interval between proactive notifications for a given level.
  /// `nil` means no throttle (Maximum); `.infinity` means drop everything (Off).
  private static func minInterval(forLevel level: Int) -> TimeInterval? {
    switch level {
    case 0: return .infinity  // Off
    case 1...4: return ContextDeliveryBudget.cooldownSeconds(frequencyLevel: level)
    default: return nil  // Maximum:  no throttle
    }
  }

  /// Prepare the owner-scoped throttle ledger. Eligibility checks are read-only;
  /// timestamps advance only at a visible presentation boundary.
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

  private func recordProactiveNotificationPresented(
    assistantId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    now: Date = Date()
  ) {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    prepareOwnerScopedState(for: authorizationSnapshot)
    lastNotificationAt[assistantId] = now
    lastNotificationAtGlobal = now
  }

  func lastProactivePresentationAtForCurrentOwner() -> Date? {
    guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(),
      RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot)
    else { return nil }
    prepareOwnerScopedState(for: snapshot)
    return lastNotificationAtGlobal
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
    guard
      isProactiveNotificationEligible(
        assistantId: assistantId,
        now: now,
        authorizationSnapshot: authorizationSnapshot)
    else { return false }
    recordProactiveNotificationPresented(
      assistantId: assistantId,
      authorizationSnapshot: authorizationSnapshot,
      now: now
    )
    return true
  }

  func proactiveNotificationEligibleForTesting(
    assistantId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    now: Date
  ) -> Bool {
    isProactiveNotificationEligible(
      assistantId: assistantId,
      now: now,
      authorizationSnapshot: authorizationSnapshot)
  }

  func recordProactiveNotificationPresentedForTesting(
    assistantId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    now: Date
  ) {
    recordProactiveNotificationPresented(
      assistantId: assistantId,
      authorizationSnapshot: authorizationSnapshot,
      now: now)
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
