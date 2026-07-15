import Combine
import Foundation

/// Pure debounce policy so foreground handling remains deterministic and cheap
/// to test without a running app or backend.
enum ChatFirstPromptMaterializationPolicy {
  static let minimumInterval: TimeInterval = 60

  static func shouldStart(
    transcriptFirstPageLoaded: Bool,
    isRunning: Bool,
    lastAttemptAt: Date?,
    now: Date
  ) -> Bool {
    guard transcriptFirstPageLoaded, !isRunning else { return false }
    guard let lastAttemptAt else { return true }
    return now.timeIntervalSince(lastAttemptAt) >= minimumInterval
  }
}

/// Root-owned, silent-until-open coordinator for server-owned prompt intents.
/// It owns timing only: content, due decisions, receipt identity, and journal
/// state remain on the backend/kernel respectively.
@MainActor
final class ChatFirstPromptMaterializationCoordinator: ObservableObject {
  private weak var chatProvider: ChatProvider?
  private var didLoadTranscriptFirstPage = false
  private var lastAttemptAt: Date?
  private var requestTask: Task<Void, Never>?
  private var requestGeneration = 0
  private let now: () -> Date

  init(now: @escaping () -> Date = Date.init) {
    self.now = now
  }

  func activate(using chatProvider: ChatProvider) {
    self.chatProvider = chatProvider
  }

  /// Called from the one rich main-chat page after its first transcript page is
  /// available. A shell with another route never creates a proactive turn.
  func chatTranscriptFirstPageDidLoad() {
    didLoadTranscriptFirstPage = true
    requestMaterialization(windowForeground: true)
  }

  /// Leaving the rich Chat route must immediately make this coordinator inert.
  /// In particular, a later app-foreground notification cannot materialize an
  /// intent into a transcript the user is not presently viewing.
  func chatTranscriptDidDisappear() {
    didLoadTranscriptFirstPage = false
    requestGeneration &+= 1
    requestTask?.cancel()
    requestTask = nil
  }

  /// `ChatFirstShell` alone forwards app foreground events. This is never
  /// registered by the legacy shell, floating/notch UI, or a background task.
  func mainWindowDidBecomeForeground() {
    requestMaterialization(windowForeground: true)
  }

  private func requestMaterialization(windowForeground: Bool) {
    guard ChatFirstPromptMaterializationPolicy.shouldStart(
      transcriptFirstPageLoaded: didLoadTranscriptFirstPage,
      isRunning: requestTask != nil,
      lastAttemptAt: lastAttemptAt,
      now: now()
    ), let chatProvider, chatProvider.chatFirstMaterializationContext() != nil
    else { return }

    lastAttemptAt = now()
    requestGeneration &+= 1
    let generation = requestGeneration
    requestTask = Task { [weak self, weak chatProvider] in
      guard let self, let chatProvider else { return }
      await self.materialize(using: chatProvider, windowForeground: windowForeground, generation: generation)
      if self.requestGeneration == generation {
        self.requestTask = nil
      }
    }
  }

  private func materialize(
    using chatProvider: ChatProvider,
    windowForeground: Bool,
    generation: Int
  ) async {
    guard isCurrentMaterialization(generation) else { return }
    guard let context = chatProvider.chatFirstMaterializationContext() else { return }
    do {
      let pendingReceipts = try await chatProvider.pendingChatFirstMaterializationReceipts()
      guard isCurrentMaterialization(generation) else { return }
      // The endpoint atomically accepts prior receipts before returning ready
      // intents. Only after a success response do we remove their local copies.
      let response = try await APIClient.shared.materializeChatFirstPrompts(
        ownerID: context.ownerID,
        controlGeneration: context.controlGeneration,
        windowForeground: windowForeground,
        receipts: pendingReceipts
      )
      guard isCurrentMaterialization(generation) else { return }
      if !pendingReceipts.isEmpty {
        _ = try await chatProvider.acknowledgeChatFirstMaterializationReceipts(pendingReceipts)
        guard isCurrentMaterialization(generation) else { return }
      }

      guard isCurrentMaterialization(generation),
        response.intents.allSatisfy({ $0.accountGeneration == context.controlGeneration })
      else { return }
      // Preserve the server's `(created_at, intent_id)` order in one kernel
      // transaction. The kernel stops after a question or any blocked tail;
      // Swift never reorders, caches, or locally schedules these intents.
      _ = try await chatProvider.materializeChatFirstIntents(response.intents)
    } catch {
      // Failure is intentionally quiet and retryable on the next debounced
      // foreground/open. Do not create a notification, badge, or Chat row.
      log("Chat-first prompt materialization deferred")
    }
  }

  private func isCurrentMaterialization(_ generation: Int) -> Bool {
    didLoadTranscriptFirstPage && requestGeneration == generation && !Task.isCancelled
  }
}
