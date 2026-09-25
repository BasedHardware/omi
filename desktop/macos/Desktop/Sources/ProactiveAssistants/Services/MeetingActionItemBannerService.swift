import Foundation

/// User toggle for the post-meeting summary share notification (Settings →
/// Notifications). Defaults to on; `NotificationService.categoryToggleAllows`
/// is the single delivery boundary that consults it.
@MainActor
enum MeetingSummaryNotificationSettings {
  static var isEnabled: Bool {
    get {
      if let stored =
        UserDefaults.standard.object(forKey: DefaultsKey.meetingSummaryNotificationsEnabled.rawValue) as? Bool
      {
        return stored
      }
      // First read inherits the Task toggle: meeting-notes banners were gated
      // by Task Notifications before this became its own category, so a user
      // who turned those off must not start receiving meeting cards because
      // of the split.
      return TaskAssistantSettings.shared.notificationsEnabled
    }
    set {
      UserDefaults.standard.set(newValue, forKey: DefaultsKey.meetingSummaryNotificationsEnabled.rawValue)
    }
  }
}

/// Pure decision logic for the meeting action-item completion banner, kept
/// static and value-typed so filtering, formatting, and dedup are unit-testable
/// without a backend or notification center.
enum MeetingActionItemBannerPolicy {
  static let bannerTitle = "Meeting notes ready"
  static let assistantID = "meeting-notes"
  static let maxBodyLength = 120

  /// The `capture_owner` value that marks an extracted item as the user's own
  /// commitment (as opposed to someone else's follow-up captured in passing).
  static let userCaptureOwner = "user"

  /// Items worth recommending when a meeting's notes finish processing: the
  /// user's own, still-open commitments. Legacy items without a capture owner
  /// are excluded rather than guessed at.
  static func recommendedItems(from items: [ActionItem]) -> [ActionItem] {
    items.filter { $0.captureOwner == userCaptureOwner && !$0.completed && !$0.deleted }
  }

  /// Banner body: conversation title plus the first recommended item, with an
  /// "and N more" tail when more exist. Returns nil for zero items — the
  /// caller must then change nothing about today's behavior. Truncation always
  /// preserves the tail so the item count survives a long title/description.
  static func bannerBody(
    conversationTitle: String,
    recommendedItems: [ActionItem],
    maxLength: Int = maxBodyLength
  ) -> String? {
    guard let first = recommendedItems.first else { return nil }
    let additionalCount = recommendedItems.count - 1
    let suffix = additionalCount > 0 ? " and \(additionalCount) more" : ""
    let base = "\(conversationTitle): \(first.description)"
    if base.count + suffix.count <= maxLength {
      return base + suffix
    }
    let budget = max(1, maxLength - suffix.count - 1)
    return String(base.prefix(budget)) + "…" + suffix
  }
}

/// Posts a system banner recommending a completed meeting's open action items,
/// deep-linking back into the chat surface that carries the meeting-notes card.
///
/// Strictly additive to the existing completion flow: it only observes the
/// already-coalesced `.desktopMeetingConversationDidComplete` signal, never
/// blocks or reorders the Chat materialization path, and any fetch/decode
/// failure or zero-item result degrades silently to today's behavior.
@MainActor
final class MeetingActionItemBannerService {
  static let shared = MeetingActionItemBannerService()

  typealias ConversationFetcher = @Sendable (_ conversationID: String) async throws -> ServerConversation
  typealias RecipientsFetcher = @Sendable (_ conversationID: String) async throws -> [ConversationShareRecipient]
  typealias BannerPresenter =
    @MainActor (
      _ title: String, _ body: String, _ conversationID: String, _ recipients: [ConversationShareRecipient]
    ) -> Void

  private let fetchConversation: ConversationFetcher
  private let fetchShareRecipients: RecipientsFetcher
  private let presentBanner: BannerPresenter

  /// Conversations already handled this process, in insertion order. The
  /// finalization service can legitimately re-signal one conversation (e.g. a
  /// deferred projection poll racing a crash-recovery retry), so the banner
  /// dedupes by conversation ID before any async work starts.
  private var handledConversationIDs: Set<String> = []
  private var handledConversationIDOrder: [String] = []
  private static let maxHandledConversationIDs = 512

  private var completionObserver: NSObjectProtocol?

  /// Tracks in-flight fetches so tests can await quiescence. Entries remove
  /// themselves on completion, so production never accumulates finished tasks.
  private var inflightTasks: [UUID: Task<Void, Never>] = [:]

  init(
    fetchConversation: ConversationFetcher? = nil,
    fetchShareRecipients: RecipientsFetcher? = nil,
    presentBanner: BannerPresenter? = nil
  ) {
    self.fetchConversation =
      fetchConversation ?? { conversationID in
        try await APIClient.shared.getConversation(id: conversationID)
      }
    self.fetchShareRecipients =
      fetchShareRecipients ?? { conversationID in
        try await APIClient.shared.getConversationShareRecipients(id: conversationID)
      }
    self.presentBanner =
      presentBanner ?? { title, body, conversationID, recipients in
        // Same owner-provenance and delivery gates as the other proactive
        // banners: master Notifications toggle, the meeting-summary toggle,
        // frequency throttle, and the floating-bar preview policy all remain
        // authoritative inside `sendNotification`. The card presents in the
        // notch as a persistent share card (Copy link / Send to … / close);
        // it never journals a Chat row — the durable Chat surface is the
        // conversation-link card the backend materializes.
        guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return }
        NotificationService.shared.sendNotification(
          ownerID: snapshot.ownerID,
          title: title,
          message: body,
          assistantId: MeetingActionItemBannerPolicy.assistantID,
          action: .meetingSummaryShare(conversationID: conversationID, recipients: recipients),
          isPersistent: true,
          authorizationSnapshot: snapshot
        )
      }
  }

  /// Install the completion observer. Idempotent; called once at launch so the
  /// banner works regardless of which window (if any) is open.
  func activate() {
    guard completionObserver == nil else { return }
    completionObserver = NotificationCenter.default.addObserver(
      forName: .desktopMeetingConversationDidComplete,
      object: nil,
      queue: .main
    ) { notification in
      guard let completion = notification.object as? MeetingCompletionNotification else { return }
      MainActor.assumeIsolated {
        MeetingActionItemBannerService.shared.handleMeetingCompletion(completion)
      }
    }
  }

  func handleMeetingCompletion(_ completion: MeetingCompletionNotification) {
    for conversationID in completion.conversationIDs {
      guard markHandled(conversationID) else { continue }
      let taskID = UUID()
      inflightTasks[taskID] = Task { [weak self] in
        await self?.recommendActionItems(conversationID: conversationID)
        self?.inflightTasks.removeValue(forKey: taskID)
      }
    }
  }

  /// Await all fetches started so far. Test seam; production never blocks on it.
  func waitForPendingRecommendations() async {
    while let task = inflightTasks.values.first {
      await task.value
    }
  }

  /// Returns false when the conversation was already handled. Marking happens
  /// before the fetch starts, so a duplicate completion signal for the same
  /// conversation can never race its way into a second banner.
  private func markHandled(_ conversationID: String) -> Bool {
    guard handledConversationIDs.insert(conversationID).inserted else { return false }
    handledConversationIDOrder.append(conversationID)
    if handledConversationIDOrder.count > Self.maxHandledConversationIDs {
      let removeCount = handledConversationIDOrder.count - Self.maxHandledConversationIDs
      for id in handledConversationIDOrder.prefix(removeCount) {
        handledConversationIDs.remove(id)
      }
      handledConversationIDOrder.removeFirst(removeCount)
    }
    return true
  }

  private func recommendActionItems(conversationID: String) async {
    do {
      let conversation = try await fetchConversation(conversationID)
      let items = MeetingActionItemBannerPolicy.recommendedItems(
        from: conversation.structured.actionItems)
      // The share card exists even with zero recommended items — its point is
      // Copy/Send, not the item list — so fall back to the conversation title.
      let body =
        MeetingActionItemBannerPolicy.bannerBody(
          conversationTitle: conversation.title,
          recommendedItems: items
        ) ?? conversation.title
      // Recipient detection failing (or finding no one) degrades to the same
      // card without a Send button, never to a missing card.
      let recipients = (try? await fetchShareRecipients(conversationID)) ?? []
      presentBanner(MeetingActionItemBannerPolicy.bannerTitle, body, conversationID, recipients)
    } catch {
      // Silent by design: the meeting-notes card in Chat is the durable
      // surface; the banner is an opportunistic recommendation on top.
      log("MeetingActionItemBanner: skipped for \(conversationID) (fetch failed)")
    }
  }
}
