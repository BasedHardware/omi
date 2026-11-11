import Combine
import OmiTheme
import SwiftUI

/// The same Activity rows are used by the product and headless render evidence.
/// Owns failure navigation and retry feedback without introducing another chat.
struct FailedConversationsActivitySection: View {
  let conversations: [ServerConversation]
  var showHeader = true
  let onOpen: (ServerConversation) -> Void
  let retry: (ServerConversation) async throws -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      if !conversations.isEmpty {
        if showHeader { Text("Needs attention").font(.headline).foregroundStyle(Ink.primary) }
        ForEach(conversations) { conversation in
          FailureActivityRow(
            conversation: conversation, onOpen: { onOpen(conversation) },
            retry: {
              try await retry(conversation)
            })
        }
      }
    }
    .accessibilityIdentifier("activity-failed-conversations")
  }
}

@MainActor
final class FailureActivityRetryController: ObservableObject {
  @Published private(set) var busy = false
  @Published private(set) var failed = false
  private let retry: () async throws -> Void

  init(retry: @escaping () async throws -> Void) { self.retry = retry }

  func run() async {
    guard !busy else { return }
    busy = true
    failed = false
    defer { busy = false }
    do { try await retry() } catch { failed = true }
  }
}

private struct FailureActivityRow: View {
  let conversation: ServerConversation
  let onOpen: () -> Void
  @StateObject private var retryState: FailureActivityRetryController

  init(conversation: ServerConversation, onOpen: @escaping () -> Void, retry: @escaping () async throws -> Void) {
    self.conversation = conversation
    self.onOpen = onOpen
    _retryState = StateObject(wrappedValue: FailureActivityRetryController(retry: retry))
  }

  var body: some View {
    HStack(spacing: 12) {
      Image(systemName: "exclamationmark.triangle").foregroundStyle(Ink.secondary)
      Button(action: onOpen) {
        VStack(alignment: .leading, spacing: 4) {
          Text(
            (conversation.isLocked || conversation.structured.title.isEmpty)
              ? "Processing failed" : conversation.structured.title
          )
          .font(.body).foregroundStyle(Ink.primary)
          Text("Processing failed · \(OmiDateFormat.timestamp(conversation.startedAt ?? conversation.createdAt))")
            .font(.caption).foregroundStyle(Ink.secondary)
          if retryState.failed { Text("Couldn't retry. Try again.").font(.caption).foregroundStyle(Ink.primary) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }
      .buttonStyle(.plain)
      Button(retryState.busy ? "Retrying…" : "Try Again") {
        Task { await retryState.run() }
      }
      .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
      .disabled(retryState.busy)
      .accessibilityIdentifier("activity-retry-\(conversation.id)")
    }
    .padding(14)
    .accessibilityIdentifier("activity-failed-\(conversation.id)")
  }
}

struct HomeFailuresMovedState: View {
  let openActivity: () -> Void

  var body: some View {
    VStack(spacing: 12) {
      Text("No conversations here").font(.headline).foregroundStyle(Ink.primary)
      Button("Activity", action: openActivity).buttonStyle(OmiButtonStyle(.secondary))
    }
    .frame(maxWidth: .infinity, minHeight: 180)
    .accessibilityIdentifier("home-failures-moved")
  }
}
