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
  /// Re-sends the question that failed, through the host's one send — never a second send path. The
  /// host holds that question, because the composer is emptied by the send that failed.
  let onRetry: () -> Void

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
        // **Not zero.** The assistant's identity mark is drawn in an overlay offset
        // `ChatOmiMarkPlacement.markGutter` to the left of the message column, so a transcript with
        // no leading inset draws it outside the panel and clips it away — leaving omi's replies as
        // bare text with no anchor while the user's keep their capsule. Asking for exactly the
        // gutter the mark needs is what makes the two sides read as a conversation.
        horizontalContentPadding: ChatOmiMarkPlacement.markGutter,
        // **The compact window, which is the one written for this panel.**
        // `ChatMessagesView` keeps its rows eagerly mounted on purpose — a lazy
        // stack re-estimates off-screen rich-Markdown heights and hands AppKit
        // the wrong anchor mid-gesture — so how many rows are mounted is the
        // whole cost. It picks the compact window automatically only for a
        // caller that passes a chat-first block context, and this surface has
        // none, so Home was silently mounting the 500-row default into a panel
        // 460 pt tall: 910 ms and 607 native views for 400 messages, against
        // 114 ms and 84 for the same transcript compact. `Show older messages`
        // is already the way back to the rest of it.
        transcriptWindowPolicy: .compactHome,
        verticalContentPadding: OmiSpacing.sm,
        // **The one thing an empty transcript here is ever allowed to say.** The post-onboarding
        // opener is composed by the provider the moment onboarding finishes — a greeting by name
        // and tappable starters — and its only renderer was the deleted chat page and the legacy
        // hub. Landing on a search surface that has never heard of you is not the first thing the
        // app should do after asking you who you are. Everything else stays `EmptyView`: an empty
        // answer thread is a mode you entered by asking, so it is about to have a question in it.
        welcomeContent: {
          if let opener = chatProvider.onboardingOpener {
            OnboardingOpenerView(opener: opener, chatProvider: chatProvider)
          }
        }
      )
      .frame(maxWidth: .infinity, minHeight: 240, maxHeight: 460)

      // **A turn that failed must say so here.** The transcript renders nothing for a turn that
      // never produced a message, so without this the panel swaps to the answer mode, shows the
      // question, and then sits silent forever — which is indistinguishable from a slow answer. It
      // is the shared `ChatErrorCard` and the shared recovery, not a second error vocabulary.
      // **Both error shapes, because the provider has two and only one of them was covered.**
      // A `BridgeError` that maps to a card lands on `currentError`; everything else lands on the
      // legacy `errorMessage` with `currentError` nil — and *that* is the branch a crashed agent
      // runtime actually takes. Handling only the card left the exact failure this build produces
      // rendering as an empty panel, which is why the first version of this fix did not fix it.
      if let error = chatProvider.currentError {
        ChatErrorCard(
          state: error,
          onRecover: { Task { await chatProvider.recoverFromError() } },
          onDismiss: { chatProvider.dismissCurrentError() }
        )
        .accessibilityIdentifier("query-shell-answer-error")
      } else if let raw = chatProvider.errorMessage, !raw.isEmpty {
        QueryAnswerFailureNotice(
          raw: raw,
          onRetry: onRetry,
          onDismiss: { chatProvider.errorMessage = nil }
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

/// A turn that failed without a structured card.
///
/// The raw string is run through the shared `AgentErrorClassifier` rather than shown as-is: the
/// provider's `errorMessage` is a `localizedDescription`, so untranslated it reads
/// "pi-mono process exited (code 1)" — which is true, and tells the person holding the keyboard
/// nothing about whether to wait, retry, or give up. The classifier already owns that mapping and
/// already knows which failures are worth retrying.
private struct QueryAnswerFailureNotice: View {
  let raw: String
  let onRetry: () -> Void
  let onDismiss: () -> Void

  private var classified: ClassifiedAgentError { AgentErrorClassifier.classify(raw) }

  var body: some View {
    HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
      Image(systemName: "exclamationmark.circle")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundStyle(Ink.errorRed)
      Text(classified.userMessage)
        .scaledFont(size: OmiType.caption, weight: .regular)
        .foregroundStyle(Ink.primary)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
      if classified.retryable {
        Button("Try again", action: onRetry)
          .buttonStyle(.plain)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(Ink.accent)
      }
      Button {
        onDismiss()
      } label: {
        Image(systemName: "xmark")
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .foregroundStyle(Ink.secondary)
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Dismiss")
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .glassCard(cornerRadius: PageGlass.rowRadius)
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
