import Foundation

struct FirstRunObservedContext: Codable, Equatable, Sendable {
  let appName: String
  let bundleID: String
  let normalizedTitle: String
  let bucketID: String?

  var reminderKey: ContextReminderKey {
    ContextReminderKey(bundleID: bundleID, normalizedTitle: normalizedTitle, bucketID: bucketID)
  }

  var isBrowser: Bool {
    WorkHistoryHandleExtractor.isBrowser(appName: appName, bundleID: bundleID)
  }

  var distractionSite: String? {
    guard isBrowser else { return nil }
    let title = normalizedTitle.lowercased()
    for pattern in Self.distractionPatterns where title.contains(pattern.match) {
      return pattern.label
    }
    return nil
  }

  var isEligibleProject: Bool {
    let title = normalizedTitle.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !title.isEmpty, !title.hasPrefix("Omi Welcome"), distractionSite == nil else { return false }
    let bundle = bundleID.lowercased()
    let isOmi =
      bundle == "com.omi.computer-macos"
      || bundle == "com.omi.computer-macos.beta"
      || bundle == "com.omi.desktop-dev"
      || bundle.hasPrefix("com.omi.omi-")
    return !isOmi
  }

  private static let distractionPatterns: [(match: String, label: String)] = [
    ("reddit", "Reddit"),
    ("twitter", "Twitter"),
    ("x.com", "X"),
    ("facebook", "Facebook"),
    ("instagram", "Instagram"),
    ("youtube", "YouTube"),
    ("tiktok", "TikTok"),
    ("hacker news", "Hacker News"),
    ("news", "news"),
  ]
}

extension Notification.Name {
  static let firstRunContextChanged = Notification.Name("omi.firstRun.contextChanged")
  static let firstRunVoiceTurnCompleted = Notification.Name("omi.firstRun.voiceTurnCompleted")
  static let firstRunNotificationDismissed = Notification.Name("omi.firstRun.notificationDismissed")
}

@MainActor
final class FirstRunContextObserver {
  static let shared = FirstRunContextObserver()

  private var observations: [NSObjectProtocol] = []
  private var started = false

  private init() {}

  static func post(
    appName: String,
    bundleID: String?,
    windowTitle: String?,
    bucketID: String?
  ) {
    guard let bundleID,
      let normalizedTitle = ContextDetection.normalizeWindowTitle(windowTitle),
      !normalizedTitle.isEmpty
    else { return }
    var userInfo: [String: Any] = [
      "app_name": appName,
      "bundle_id": bundleID,
      "normalized_title": normalizedTitle,
    ]
    if let bucketID { userInfo["bucket_id"] = bucketID }
    NotificationCenter.default.post(
      name: .firstRunContextChanged,
      object: nil,
      userInfo: userInfo)
  }

  static func postCompletedVoiceTurn(_ transcript: String) {
    let text = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
    NotificationCenter.default.post(
      name: .firstRunVoiceTurnCompleted,
      object: nil,
      userInfo: ["transcript": text])
  }

  func start() {
    guard !started else { return }
    started = true

    observations.append(
      NotificationCenter.default.addObserver(
        forName: .firstRunContextChanged, object: nil, queue: .main
      ) { notification in
        let appName = notification.userInfo?["app_name"] as? String
        let bundleID = notification.userInfo?["bundle_id"] as? String
        let normalizedTitle = notification.userInfo?["normalized_title"] as? String
        let bucketID = notification.userInfo?["bucket_id"] as? String
        Task { @MainActor in
          guard let appName, let bundleID, let normalizedTitle else { return }
          let context = FirstRunObservedContext(
            appName: appName,
            bundleID: bundleID,
            normalizedTitle: normalizedTitle,
            bucketID: bucketID)
          FirstRunCoordinator.shared.observeContext(context)
          await Self.deliverGeneralReminders(for: context)
        }
      })
    observations.append(
      NotificationCenter.default.addObserver(
        forName: .firstRunVoiceTurnCompleted, object: nil, queue: .main
      ) { notification in
        let transcript = notification.userInfo?["transcript"] as? String
        Task { @MainActor in
          guard let transcript else { return }
          let repliedToCard = FloatingControlBarManager.shared.recentNotchCardVoiceContext() != nil
          DesktopUsageDailyReporter.shared.recordCompletedPTTTurn(repliedToCard: repliedToCard)
          FirstRunCoordinator.shared.observeVoiceTurn(transcript)
        }
      })
    observations.append(
      NotificationCenter.default.addObserver(
        forName: Notification.Name("omi.floatingBar.cardAction"), object: nil, queue: .main
      ) { notification in
        let action = notification.userInfo?["action"] as? String ?? ""
        let id = notification.userInfo?["id"] as? String
        Task { @MainActor in
          DesktopUsageDailyReporter.shared.recordProactiveCardActed()
          FirstRunCoordinator.shared.handleCardAction(action, id: id)
        }
      })
    observations.append(
      NotificationCenter.default.addObserver(
        forName: .firstRunNotificationDismissed, object: nil, queue: .main
      ) { notification in
        let assistantID = notification.userInfo?["assistant_id"] as? String
        Task { @MainActor in
          guard assistantID == "first_run_guide" else { return }
          FirstRunCoordinator.shared.dismissByUser()
        }
      })
  }

  private static func deliverGeneralReminders(for context: FirstRunObservedContext) async {
    do {
      let reminders = try await ContextReminderStore.shared.dueReminders(for: context)
      for reminder in reminders where !FirstRunCoordinator.shared.ownsReminderDelivery(reminder.id) {
        _ = ContextReminderStore.shared.deliver(reminder)
      }
    } catch {
      logError("FirstRunContextObserver: failed to evaluate context reminders", error: error)
    }
  }
}
