//
//  QueryAnswerThread.swift — what the results panel becomes when you press ⌘⏎.
//
//  **Asking is a mode of the query, not a destination.** The window does not navigate, the query bar
//  does not move, the panel keeps its frame and its corner — only the body inside it swaps. That is
//  the whole reason the answer lives inside the results panel rather than on a page of its own: the
//  thing you asked about is the thing you were just looking at, and taking the list away to show the
//  answer would break that.
//
//  It renders `ChatProvider.messages` through the shared `ChatMessagesView`. There is **one**
//  `ChatProvider`, one transcript and no new turn handler here (INV-6): this view sends nothing and
//  owns nothing — `QueryShellHome` sends through the same `sendMessage` the composer uses, and this
//  file only draws the result.
//
//  Citation chips are built from the answer's own `captureLink` / `memoryLink` content blocks, which
//  is the live provenance the backend actually emits. `ChatMessage.citations` is *not* used: nothing
//  in the app ever constructs one, so a chip strip built on it would be permanently empty.
//
//  Brand: `Ink` semantics only (INV-UI-1).
//

import OmiTheme
import SwiftUI

struct QueryAnswerThread: View {
  @ObservedObject var chatProvider: ChatProvider
  let onOpenConversation: (String) -> Void
  let onOpenMemories: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      ChatMessagesView(
        messages: chatProvider.messages,
        conversationIdentity: chatProvider.currentSessionId
          ?? ChatConversationIdentity.mainChatDefault,
        isSending: chatProvider.isSending,
        hasMoreMessages: chatProvider.hasMoreMessages,
        isLoadingMoreMessages: chatProvider.isLoadingMoreMessages,
        isLoadingInitial: chatProvider.isLoading && !chatProvider.isClearing,
        app: nil,
        onLoadMore: { await chatProvider.loadMoreMessages() },
        onRate: { messageId, rating in
          Task { await chatProvider.rateMessage(messageId, rating: rating) }
        },
        sessionsLoadError: chatProvider.sessionsLoadError.map {
          UserFacingErrorPresentation.message(from: $0, while: .chatSessions)
        },
        onRetry: { Task { await chatProvider.retryLoad() } },
        localSendToken: chatProvider.localSendToken,
        onCancelTurn: { chatProvider.stopAgent(owner: .mainChat) },
        horizontalContentPadding: 0,
        verticalContentPadding: OmiSpacing.sm,
        welcomeContent: { EmptyView() }
      )
      .frame(maxWidth: .infinity, minHeight: 240, maxHeight: 460)

      // **A turn that failed must say so here.** The transcript renders nothing for a turn that
      // never produced a message, so without this the panel swaps to the answer mode, shows the
      // question, and then sits silent forever — which is indistinguishable from a slow answer. It
      // is the shared `ChatErrorCard` and the shared recovery, not a second error vocabulary.
      if let error = chatProvider.currentError {
        ChatErrorCard(
          state: error,
          onRecover: { Task { await chatProvider.recoverFromError() } },
          onDismiss: { chatProvider.dismissCurrentError() }
        )
        .accessibilityIdentifier("query-shell-answer-error")
      }

      if !sources.isEmpty {
        QueryCitationStrip(
          sources: sources,
          onOpenConversation: onOpenConversation,
          onOpenMemories: onOpenMemories)
      }
    }
    .accessibilityIdentifier("query-shell-answer")
  }

  /// Where the newest answer came from. Only the latest assistant turn, because a strip that
  /// accumulates every source in the session stops being a citation and becomes a bibliography.
  private var sources: [QueryAnswerSource] {
    guard let latest = chatProvider.messages.last(where: { $0.sender == .ai }) else { return [] }
    return QueryAnswerSource.from(blocks: latest.contentBlocks)
  }
}

/// One place the answer came from.
struct QueryAnswerSource: Identifiable, Equatable {
  enum Origin: Equatable {
    case conversation(id: String)
    case memory
  }

  let id: String
  let origin: Origin
  let summary: String

  var glyph: String {
    switch origin {
    case .conversation: return "text.bubble"
    case .memory: return "brain.head.profile"
    }
  }

  /// Reads the two link blocks the backend emits for provenance and ignores everything else a turn
  /// carries — tool calls, thinking, task cards are not sources.
  static func from(blocks: [ChatContentBlock]) -> [QueryAnswerSource] {
    blocks.compactMap { block in
      switch block {
      case .captureLink(let id, let conversationId, _, let summary):
        return QueryAnswerSource(
          id: id, origin: .conversation(id: conversationId),
          summary: summary.isEmpty ? "Conversation" : summary)
      case .memoryLink(let id, _, let summary):
        return QueryAnswerSource(
          id: id, origin: .memory, summary: summary.isEmpty ? "Memory" : summary)
      default:
        return nil
      }
    }
  }
}

private struct QueryCitationStrip: View {
  let sources: [QueryAnswerSource]
  let onOpenConversation: (String) -> Void
  let onOpenMemories: () -> Void

  var body: some View {
    ScrollView(.horizontal, showsIndicators: false) {
      HStack(spacing: 6) {
        ForEach(sources) { source in
          QueryCitationChip(source: source) {
            switch source.origin {
            case .conversation(let id): onOpenConversation(id)
            case .memory: onOpenMemories()
            }
          }
        }
      }
      .padding(.bottom, 2)
    }
    .accessibilityIdentifier("query-shell-citations")
  }
}

private struct QueryCitationChip: View {
  let source: QueryAnswerSource
  let action: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: action) {
      HStack(spacing: 6) {
        Image(systemName: source.glyph)
          .scaledFont(size: OmiType.micro, weight: .semibold)
        Text(source.summary)
          .scaledFont(size: OmiType.caption, weight: .regular)
          .lineLimit(1)
      }
      .foregroundStyle(GlassShell.controlLabel(isProminent: isHovering))
      .padding(.horizontal, 10)
      .frame(height: QueryShellLayout.chipHeight)
      .glassChip(isActive: false)
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .help("Open the source this came from")
  }
}
