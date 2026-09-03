import AppKit
import Foundation

/// Creates, matches, and delivers place-bound reminders through the same
/// `NotificationService` path every other proactive card uses.
///
/// Context switches are observed from `AssistantCoordinator.fireContextSwitchOnAllAssistants`
/// — the live frontmost-app/window detector — not from a second NSWorkspace observer.
@MainActor
final class ContextReminderCoordinator {
  static let shared = ContextReminderCoordinator()
  static let assistantID = "context_reminder"

  typealias Presenter = @MainActor (_ ownerID: String, _ reminder: ContextReminder) -> Bool
  typealias ContextProvider = @MainActor () async -> ContextReminderObservedContext?
  typealias ActionItemCreator =
    @MainActor (
      _ text: String, _ context: ContextReminderKey, _ ownerID: String,
      _ authorization: RuntimeOwnerAuthorizationSnapshot
    ) async -> String?
  typealias ActionItemCompleter =
    @MainActor (
      _ id: String, _ ownerID: String, _ authorization: RuntimeOwnerAuthorizationSnapshot
    ) async -> Void

  private let store: ContextReminderStore
  private let contextProvider: ContextProvider
  private let presenter: Presenter
  private let dismisser: @MainActor () -> Void
  private let now: () -> Date
  private let calendar: Calendar
  private let ownerIDProvider: () -> String?
  private let createActionItem: ActionItemCreator
  private let completeActionItem: ActionItemCompleter

  private var deliveredInCurrentContext: Set<String> = []
  private var lastObservedIdentity: String?
  private var ownerObserver: NSObjectProtocol?

  init(
    store: ContextReminderStore = .shared,
    contextProvider: @escaping ContextProvider = ContextReminderCoordinator.liveContextProvider,
    presenter: @escaping Presenter = ContextReminderCoordinator.notificationServicePresenter,
    dismisser: @escaping @MainActor () -> Void = ContextReminderCoordinator.floatingBarDismisser,
    now: @escaping () -> Date = Date.init,
    calendar: Calendar = .current,
    ownerIDProvider: @escaping () -> String? = { RuntimeOwnerIdentity.currentOwnerId() },
    createActionItem: @escaping ActionItemCreator = ContextReminderCoordinator.liveActionItemCreator,
    completeActionItem: @escaping ActionItemCompleter = ContextReminderCoordinator.liveActionItemCompleter
  ) {
    self.store = store
    self.contextProvider = contextProvider
    self.presenter = presenter
    self.dismisser = dismisser
    self.now = now
    self.calendar = calendar
    self.ownerIDProvider = ownerIDProvider
    self.createActionItem = createActionItem
    self.completeActionItem = completeActionItem
  }

  func start() {
    guard ownerObserver == nil else { return }
    ownerObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange, object: nil, queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated {
        self?.resetForOwnerChange()
      }
    }
  }

  /// Called from the existing context-switch path in `AssistantCoordinator`.
  func observeFrontmostChange(appName: String, windowTitle: String?) async {
    guard let context = await Self.observedContext(appName: appName, windowTitle: windowTitle) else { return }
    await observe(context)
  }

  func observe(_ context: ContextReminderObservedContext) async {
    let identity = "\(context.bundleID)|\(context.normalizedTitle)|\(context.bucketID ?? "")"
    if lastObservedIdentity != identity {
      lastObservedIdentity = identity
      deliveredInCurrentContext.removeAll()
    }
    do {
      let due = try await store.dueReminders(for: context, now: now())
      for reminder in due where !deliveredInCurrentContext.contains(reminder.id) {
        guard let ownerID = ownerIDProvider() else { return }
        if presenter(ownerID, reminder) {
          deliveredInCurrentContext.insert(reminder.id)
        }
      }
    } catch {
      logError("ContextReminderCoordinator: failed to evaluate reminders", error: error)
    }
  }

  func createFromCurrentContext(
    text: String,
    expectedOwnerID: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async -> String {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
      return "Error: text is required"
    }
    guard let ownerID = expectedOwnerID ?? ownerIDProvider(), !ownerID.isEmpty else {
      return "Error: sign in to set a place-based reminder."
    }
    let authorization =
      authorizationSnapshot
      ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    guard let authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      return "Error: sign in to set a place-based reminder."
    }
    guard let context = await contextProvider() else {
      return
        "I couldn't tell what you were looking at, so I didn't set a place-based reminder. Bring the document to the front and ask again."
    }
    guard !context.normalizedTitle.isEmpty, !context.bundleID.isEmpty, !context.isOmiBundle else {
      return
        "I need a real document or app in front — not Omi itself — to bind a reminder to this place."
    }
    do {
      let reminder = try await store.create(
        text: trimmed,
        for: context.reminderKey,
        now: now(),
        expectedOwnerID: ownerID,
        authorizationSnapshot: authorization)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
        return "Error: sign in to set a place-based reminder."
      }
      let actionItemID = await createActionItem(trimmed, context.reminderKey, ownerID, authorization)
      if let actionItemID {
        _ = try? await store.attachActionItem(id: reminder.id, actionItemID: actionItemID)
      }
      return "I'll remind you next time you're in \(context.normalizedTitle)."
    } catch {
      logError("ContextReminderCoordinator: failed to persist reminder", error: error)
      return "I couldn't save that reminder. Try again in a moment."
    }
  }

  func markDone(reminderID: String) {
    Task { await resolve(id: reminderID, snoozed: false) }
  }

  func snoozeUntilTomorrow(reminderID: String) {
    Task { await resolve(id: reminderID, snoozed: true) }
  }

  func resetForOwnerChange() {
    deliveredInCurrentContext.removeAll()
    lastObservedIdentity = nil
    dismisser()
  }

  func resolve(id: String, snoozed: Bool) async {
    do {
      let reminder: ContextReminder?
      if snoozed {
        let tomorrow =
          calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: now()))
          ?? now().addingTimeInterval(24 * 60 * 60)
        reminder = try await store.snooze(id: id, until: tomorrow)
      } else {
        reminder = try await store.markDone(id: id, at: now())
        if let actionItemID = reminder?.actionItemID,
          let ownerID = ownerIDProvider(),
          let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
        {
          await completeActionItem(actionItemID, ownerID, authorization)
        }
      }
      guard reminder != nil else { return }
      deliveredInCurrentContext.insert(id)
      dismisser()
    } catch {
      logError("ContextReminderCoordinator: failed to resolve reminder", error: error)
    }
  }

  static func observedContext(appName: String, windowTitle: String?) async -> ContextReminderObservedContext? {
    guard let normalizedTitle = ContextDetection.normalizeWindowTitle(windowTitle, appName: appName),
      !normalizedTitle.isEmpty
    else { return nil }
    let bundleID =
      NSWorkspace.shared.frontmostApplication.flatMap { application in
        application.localizedName == appName ? application.bundleIdentifier : nil
      } ?? ""
    guard !bundleID.isEmpty else { return nil }
    let bucketID = await ContextVisitCoordinator.shared.currentFence()?.bucketID
    return ContextReminderObservedContext(
      appName: appName,
      bundleID: bundleID,
      normalizedTitle: normalizedTitle,
      bucketID: bucketID)
  }

  static let liveContextProvider: ContextProvider = {
    let info = WindowMonitor.getActiveWindowInfoStatic()
    guard let appName = info.appName else { return nil }
    return await observedContext(appName: appName, windowTitle: info.windowTitle)
  }

  static let notificationServicePresenter: Presenter = { ownerID, reminder in
    guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: ownerID)
    else { return false }
    NotificationService.shared.sendNotification(
      ownerID: ownerID,
      title: reminder.contextKey.normalizedTitle,
      message: "You're back. You asked me to remind you: \(reminder.text)",
      assistantId: assistantID,
      action: .contextReminder(reminderID: reminder.id),
      respectFrequency: false,
      isPersistent: true,
      authorizationSnapshot: snapshot)
    return true
  }

  static let floatingBarDismisser: @MainActor () -> Void = {
    let manager = FloatingControlBarManager.shared
    guard manager.window?.state.currentNotification?.assistantId == assistantID else { return }
    manager.dismissCurrentNotification(kind: .user)
  }

  static let liveActionItemCreator: ActionItemCreator = { text, context, ownerID, authorization in
    do {
      let actionItem = try await APIClient.shared.createActionItem(
        description: "In \(context.normalizedTitle): \(text)",
        source: "context_reminder",
        expectedOwnerId: ownerID,
        authorizationSnapshot: authorization)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return nil }
      await TasksStore.shared.refreshDashboardTasksFromServer(
        expectedOwnerID: ownerID,
        authorizationSnapshot: authorization)
      return actionItem.id
    } catch {
      logError("ContextReminderCoordinator: action item create failed; reminder still saved", error: error)
      return nil
    }
  }

  static let liveActionItemCompleter: ActionItemCompleter = { id, ownerID, authorization in
    _ = try? await APIClient.shared.updateActionItem(
      id: id,
      completed: true,
      expectedOwnerId: ownerID,
      authorizationSnapshot: authorization)
    await TasksStore.shared.refreshDashboardTasksFromServer(
      expectedOwnerID: ownerID,
      authorizationSnapshot: authorization)
  }
}
