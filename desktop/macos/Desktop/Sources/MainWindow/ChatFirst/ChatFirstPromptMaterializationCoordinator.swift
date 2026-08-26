import Combine
import Foundation

/// Pure debounce policy so foreground handling remains deterministic and cheap
/// to test without a running app or backend.
enum ChatFirstPromptMaterializationPolicy {
  static let minimumInterval: TimeInterval = 60

  static func shouldStart(
    hasChatFirstMainChatContext: Bool,
    transcriptFirstPageLoaded: Bool,
    isRunning: Bool,
    lastAttemptAt: Date?,
    now: Date
  ) -> Bool {
    guard hasChatFirstMainChatContext, transcriptFirstPageLoaded, !isRunning else { return false }
    guard let lastAttemptAt else { return true }
    return now.timeIntervalSince(lastAttemptAt) >= minimumInterval
  }
}

/// Root-owned, silent-until-open coordinator for server-owned prompt intents.
/// It owns timing only: content, due decisions, receipt identity, and journal
/// state remain on the backend/kernel respectively.
@MainActor
final class ChatFirstPromptMaterializationCoordinator: ObservableObject {
  private var driver: (any ChatFirstPromptMaterializationDriving)?
  private var didLoadTranscriptFirstPage = false
  private var lastAttemptAt: Date?
  private var requestTask: Task<Void, Never>?
  private var pendingCompletionBypass = false
  private var pendingCompletionWindowForeground = false
  private var requestGeneration = 0
  private let now: () -> Date

  init(now: @escaping () -> Date = Date.init) {
    self.now = now
  }

  func activate(using chatProvider: ChatProvider) {
    driver = APIChatFirstPromptMaterializationDriver(chatProvider: chatProvider)
  }

  /// Test seam for the same narrow driver used in production. This does not
  /// accept a local capability or transcript writer, so it cannot bypass the
  /// provider/kernel authority boundary.
  func activate(driver: any ChatFirstPromptMaterializationDriving) {
    self.driver = driver
  }

  /// Called from the one rich main-chat page after its first transcript page is
  /// available. A shell with another route never creates a proactive turn.
  func chatTranscriptFirstPageDidLoad() {
    didLoadTranscriptFirstPage = true
    _ = requestMaterialization(windowForeground: true)
  }

  /// Leaving the rich Chat route must immediately make this coordinator inert.
  /// In particular, a later app-foreground notification cannot materialize an
  /// intent into a transcript the user is not presently viewing.
  func chatTranscriptDidDisappear() {
    didLoadTranscriptFirstPage = false
    requestGeneration &+= 1
    requestTask?.cancel()
    requestTask = nil
    pendingCompletionBypass = false
    pendingCompletionWindowForeground = false
  }

  /// `ChatFirstShell` alone forwards app foreground events. This is never
  /// registered by the legacy shell, floating/notch UI, or a background task.
  @discardableResult
  func mainWindowDidBecomeForeground() -> Bool {
    // A completion observed while the window was backgrounded must not spend
    // the debounce interval on a request the server is required to reject.
    // Consume the queued completion only when a real foreground opportunity is
    // available; if a request is already in flight, leave it queued so the
    // completion handler below can issue the one bypassing follow-up.
    if pendingCompletionBypass {
      pendingCompletionWindowForeground = true
      guard requestTask == nil else { return true }
      pendingCompletionBypass = false
      pendingCompletionWindowForeground = false
      return requestMaterialization(windowForeground: true, bypassMinimumInterval: true)
    }
    return requestMaterialization(windowForeground: true)
  }

  /// Conversation processing completed while rich Chat is already visible.
  /// This exact completion signal bypasses only the foreground debounce; all
  /// route, owner, first-page, and in-flight gates remain authoritative.
  @discardableResult
  func meetingConversationDidComplete(windowForeground: Bool) -> Bool {
    guard didLoadTranscriptFirstPage, driver?.materializationContext() != nil else { return false }
    if requestTask != nil {
      pendingCompletionBypass = true
      pendingCompletionWindowForeground = pendingCompletionWindowForeground || windowForeground
      return true
    }
    guard windowForeground else {
      // Keep the completion durable in this coordinator until the shell gets a
      // genuine foreground event. In particular, do not update lastAttemptAt
      // for the server's intentionally empty background response.
      pendingCompletionBypass = true
      pendingCompletionWindowForeground = false
      return true
    }
    return requestMaterialization(windowForeground: windowForeground, bypassMinimumInterval: true)
  }

  @discardableResult
  private func requestMaterialization(
    windowForeground: Bool,
    bypassMinimumInterval: Bool = false
  ) -> Bool {
    guard
      let driver,
      driver.materializationContext() != nil,
      didLoadTranscriptFirstPage,
      requestTask == nil,
      bypassMinimumInterval
        || ChatFirstPromptMaterializationPolicy.shouldStart(
          hasChatFirstMainChatContext: true,
          transcriptFirstPageLoaded: true,
          isRunning: false,
          lastAttemptAt: lastAttemptAt,
          now: now())
    else { return false }

    lastAttemptAt = now()
    requestGeneration &+= 1
    let generation = requestGeneration
    requestTask = Task { [weak self, driver] in
      guard let self else { return }
      await self.materialize(using: driver, windowForeground: windowForeground, generation: generation)
      if self.requestGeneration == generation {
        self.requestTask = nil
        if self.pendingCompletionBypass {
          let windowForeground = self.pendingCompletionWindowForeground
          if windowForeground {
            self.pendingCompletionBypass = false
            self.pendingCompletionWindowForeground = false
            _ = self.requestMaterialization(
              windowForeground: true,
              bypassMinimumInterval: true
            )
          }
        }
      }
    }
    return true
  }

  private func materialize(
    using driver: any ChatFirstPromptMaterializationDriving,
    windowForeground: Bool,
    generation: Int
  ) async {
    guard isCurrentMaterialization(generation) else { return }
    guard let context = driver.materializationContext() else { return }
    do {
      try await ChatFirstPromptMaterializationRunner.run(
        driver: driver,
        context: context,
        windowForeground: windowForeground,
        isCurrent: { [weak self] in
          self?.isCurrentMaterialization(generation) ?? false
        }
      )
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
