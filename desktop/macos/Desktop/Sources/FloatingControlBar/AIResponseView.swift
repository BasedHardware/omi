import OmiTheme
import SwiftUI

/// Streaming markdown response view for the floating control bar.
struct AIResponseView: View {
  @EnvironmentObject var state: FloatingControlBarState
  @Binding var isLoading: Bool
  let currentMessage: ChatMessage?
  @State private var isQuestionExpanded = false

  let userInput: String
  let chatHistory: [FloatingChatExchange]
  var canClearVisibleConversation: Bool = false
  var showsHeader: Bool = true

  var onClearVisibleConversation: (() -> Void)?
  var onEscape: (() -> Void)?
  /// Typing lives in the main app now — the bar only offers a jump there.
  var onOpenMainApp: (() -> Void)?
  var onRate: ((String, Int?) -> Void)?
  var onShareLink: (() async -> String?)?
  var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)?
  var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      if showsHeader {
        headerView
          .fixedSize(horizontal: false, vertical: true)
      }

      ChatScrollContainer(
        bottomAnchorId: "bottom",
        contentChangeToken: scrollContentToken,
        scrollPaddingTrailing: 26,
        onContentHeightChange: { height in
          state.reportContentHeight(height, for: .mainResponse)
        }
      ) {
        // Previous chat exchanges
        ForEach(chatHistory) { exchange in
          chatExchangeView(exchange)
        }

        if hasUserInput(userInput) {
          questionBar
        }

        // Current response
        currentContentView
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .overlay(alignment: .bottom) {
        ChatComposerFade()
      }

      if let shareFeedbackMessage, showShareFeedback {
        shareFeedbackBanner
          .transition(.move(edge: .bottom).combined(with: .opacity))
          .accessibilityLabel(shareFeedbackMessage)
      }

      if !isLoading {
        followUpInputView
      }
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.top, 0)
    .padding(.bottom, OmiSpacing.lg)
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .omiAnimation(.spring(response: 0.28, dampingFraction: 0.85), value: showShareFeedback)
    .onExitCommand {
      onEscape?()
    }
  }

  private var scrollContentToken: AnyHashable {
    AnyHashable(
      [
        String(chatHistory.count),
        chatHistory.last?.aiMessage.id ?? "",
        currentMessage?.id ?? "",
        currentMessage?.text ?? "",
        contentBlocksToken(currentMessage?.contentBlocks ?? []),
      ].joined(separator: "\u{1F}")
    )
  }

  private func contentBlocksToken(_ blocks: [ChatContentBlock]) -> String {
    blocks.map { block in
      switch block {
      case .text(let id, let text):
        return ["text", id, text].joined(separator: "\u{1E}")
      case .toolCall(let id, let name, let status, let toolUseId, let input, let output):
        return [
          "tool",
          id,
          name,
          String(describing: status),
          toolUseId ?? "",
          input?.summary ?? "",
          input?.details ?? "",
          output ?? "",
        ].joined(separator: "\u{1E}")
      case .thinking(let id, let text):
        return ["thinking", id, text].joined(separator: "\u{1E}")
      case .discoveryCard(let id, let title, let summary, let fullText):
        return ["discovery", id, title, summary, fullText].joined(separator: "\u{1E}")
      case .questionCard(let id, _, _, _, _, _, _):
        return ["chatFirstQuestion", id].joined(separator: "\u{1E}")
      case .taskCard(let id, _):
        return ["chatFirstTask", id].joined(separator: "\u{1E}")
      case .goalLink(let id, _, _):
        return ["chatFirstGoal", id].joined(separator: "\u{1E}")
      case .captureLink(let id, _, _, _):
        return ["chatFirstCapture", id].joined(separator: "\u{1E}")
      case .agentSpawn(
        let id, let pillId, let sessionId, let runId, let title, let objective, let provider
      ):
        return [
          "agentSpawn",
          id,
          pillId?.uuidString ?? "",
          sessionId,
          runId,
          title,
          objective,
          provider?.rawValue ?? "",
        ].joined(separator: "\u{1E}")
      case .agentCompletion(
        let id, let pillId, let sessionId, let runId, let title, let promptSnippet, let output, let status
      ):
        return [
          "agentCompletion",
          id,
          pillId?.uuidString ?? "",
          sessionId ?? "",
          runId ?? "",
          title,
          promptSnippet,
          output,
          status,
        ].joined(separator: "\u{1E}")
      }
    }.joined(separator: "\u{1D}")
  }

  private var headerView: some View {
    HStack(spacing: OmiSpacing.md) {
      if isLoading {
        ProgressView()
          .scaleEffect(0.6)
          .frame(width: 16, height: 16)
        Text("thinking")
          .scaledFont(size: OmiType.body)
          .foregroundColor(.secondary)
      } else {
        Text("omi says")
          .scaledFont(size: OmiType.body)
          .foregroundColor(.secondary)
      }

      Spacer()

      if canClearVisibleConversation {
        HStack(spacing: OmiSpacing.xxs) {
          Text("esc")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(.secondary)
            .frame(width: 30, height: 16)
            .background(Color.white.opacity(0.1))
            .cornerRadius(OmiChrome.stripRadius)
          Text("to clear")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(.secondary)
        }
      }
    }
  }

  // MARK: - Content Blocks Rendering

  /// Renders a ChatMessage's content blocks using the shared components from ChatPage.
  @ViewBuilder
  private func contentBlocksView(for message: ChatMessage) -> some View {
    if !message.contentBlocks.isEmpty {
      let grouped = groupedContentBlocks(for: message)
      ForEach(grouped) { group in
        switch group {
        case .text(_, let text):
          SelectableMarkdown(text: text, sender: .ai)
            .textSelection(.enabled)
            .environment(\.colorScheme, .dark)
            .frame(maxWidth: .infinity, alignment: .leading)
        case .toolCalls(_, let calls):
          ToolCallsGroup(
            calls: calls,
            compact: true,
            onOpenAgent: onOpenAgent,
            onOpenAgentRef: onOpenAgentRef
          )
          .frame(maxWidth: .infinity, alignment: .leading)
        case .thinking(_, let text):
          ThinkingBlock(text: text)
            .frame(maxWidth: .infinity, alignment: .leading)
        case .discoveryCard(_, let title, let summary, let fullText):
          DiscoveryCard(title: title, summary: summary, fullText: fullText)
            .frame(maxWidth: .infinity, alignment: .leading)
        // The floating/notch surface never opts into rich chat-first controls.
        // Keep journaled blocks inert if an older runtime projects them here.
        case .questionCard, .taskCard, .goalLink, .captureLink:
          EmptyView()
        case .agentSpawn(
          _, let pillId, let sessionId, let runId, let title, let objective, let provider
        ):
          AgentSpawnCard(
            title: title,
            objective: objective,
            provider: provider,
            ref: AgentTimelineRef(pillId: pillId, sessionId: sessionId, runId: runId),
            onOpen: openAgentRef
          )
          .frame(maxWidth: .infinity, alignment: .leading)
        case .agentCompletion(
          _, let pillId, let sessionId, let runId, let title, let promptSnippet, let output, let status
        ):
          // Keep the completion card + resources on the same message —
          // never EmptyView the card while leaving a standalone artifact strip.
          AgentCompletionCard(
            title: title,
            promptSnippet: promptSnippet,
            output: output,
            status: status,
            ref: AgentTimelineRef(pillId: pillId, sessionId: sessionId, runId: runId),
            onOpen: openAgentRef
          )
          .frame(maxWidth: .infinity, alignment: .leading)
        }
      }
    } else if !message.text.isEmpty {
      SelectableMarkdown(text: message.text, sender: .ai)
        .textSelection(.enabled)
        .environment(\.colorScheme, .dark)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
    if !message.displayResources.isEmpty {
      ChatResourceStrip(
        resources: message.displayResources,
        density: .compact,
        alignment: .leading
      )
      .environment(\.colorScheme, .dark)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  private func openAgentRef(_ ref: AgentTimelineRef, completion: @escaping (Bool) -> Void) {
    if let onOpenAgentRef {
      onOpenAgentRef(ref, completion)
      return
    }
    if let pillId = ref.pillId, let onOpenAgent {
      onOpenAgent(pillId, completion)
      return
    }
    completion(false)
  }

  private func groupedContentBlocks(for message: ChatMessage) -> [ContentBlockGroup] {
    let grouped = ContentBlockGroup.visibleChatGroups(
      message.contentBlocks,
      isStreaming: message.isStreaming
    )
    guard !message.isStreaming else { return grouped }

    return grouped
  }

  // MARK: - Per-Message Hover Action Overlay

  /// Wraps an AI message's content with a hover-triggered action bar.
  /// The `.id(message.id)` is load-bearing: without it SwiftUI can reuse an
  /// overlay view instance (and its Button action closures) across different
  /// messages in the same structural slot, which caused clicking Copy on an
  /// older message to read the current message's text.
  private func messageWithHoverActions(message: ChatMessage) -> some View {
    MessageHoverOverlay(
      message: message,
      onRate: { [id = message.id] rating in
        onRate?(id, rating)
      }
    ) {
      contentBlocksView(for: message)
    }
    .id(message.id)
  }

  // MARK: - Chat History

  private func chatExchangeView(_ exchange: FloatingChatExchange) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      if hasUserInput(exchange.question) {
        HStack(alignment: .top, spacing: OmiSpacing.sm) {
          Text(exchange.question ?? "")
            .scaledFont(size: OmiType.body)
            .foregroundColor(.white)
            .lineLimit(2)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
        .background(Color.white.opacity(0.1))
        .cornerRadius(OmiChrome.elementRadius)
      }

      // Response with hover actions
      messageWithHoverActions(message: exchange.aiMessage)
        .padding(.horizontal, OmiSpacing.xxs)
    }
  }

  // MARK: - Current Question & Response

  private var questionBar: some View {
    VStack(alignment: .leading, spacing: 0) {
      HStack(alignment: .top, spacing: OmiSpacing.sm) {
        Group {
          if isQuestionExpanded {
            ScrollView {
              Text(userInput)
                .scaledFont(size: OmiType.body)
                .foregroundColor(.white)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 120)
          } else {
            Text(userInput)
              .scaledFont(size: OmiType.body)
              .foregroundColor(.white)
              .lineLimit(1)
              .truncationMode(.head)
              .textSelection(.enabled)
              .frame(maxWidth: .infinity, alignment: .leading)
          }
        }

        if needsExpansion {
          Button(action: { isQuestionExpanded.toggle() }) {
            Image(systemName: isQuestionExpanded ? "chevron.up" : "chevron.down")
              .scaledFont(size: OmiType.micro)
              .foregroundColor(.secondary)
              .frame(width: 20, height: 20)
          }
          .buttonStyle(.plain)
        }
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(Color.white.opacity(0.1))
      .cornerRadius(OmiChrome.elementRadius)
      .contextMenu {
        Button("Copy") {
          NSPasteboard.general.clearContents()
          NSPasteboard.general.setString(userInput, forType: .string)
        }
      }
    }
  }

  private var needsExpansion: Bool {
    let font = NSFont.systemFont(ofSize: 13)
    let attributes = [NSAttributedString.Key.font: font]
    let size = (userInput as NSString).boundingRect(
      with: NSSize(width: 350, height: CGFloat.greatestFiniteMagnitude),
      options: .usesLineFragmentOrigin,
      attributes: attributes
    ).size
    return size.height > font.pointSize * 1.5
  }

  private func hasUserInput(_ text: String?) -> Bool {
    guard let text else { return false }
    return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
  }

  private var currentContentView: some View {
    Group {
      if let message = currentMessage {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          if message.isStreaming {
            // While streaming, show content without hover actions
            contentBlocksView(for: message)

            // Only show the typing dots when nothing has rendered yet.
            // A message can carry a delivered artifact card (resources)
            // with no text/blocks — that's already content, not "still
            // thinking", so the trailing "..." must not linger under it.
            if message.text.isEmpty && message.contentBlocks.isEmpty
              && message.displayResources.isEmpty
            {
              TypingIndicator()
            }
          } else {
            // After streaming completes, show with hover actions
            messageWithHoverActions(message: message)
          }
        }
        .padding(.horizontal, OmiSpacing.xxs)
        .padding(.bottom, OmiSpacing.xs)
        .contextMenu {
          Button("Copy") {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(message.text, forType: .string)
          }
          Button("Copy Question & Answer") {
            let combined = "Q: \(userInput)\n\nA: \(message.text)"
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(combined, forType: .string)
          }
        }
      } else if isLoading {
        TypingIndicator()
          .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
          .padding(.horizontal, OmiSpacing.xxs)
      }
    }
  }

  // MARK: - Follow-Up Input

  @State private var showShareFeedback = false
  @State private var shareFeedbackMessage: String?
  @State private var shareFeedbackHideWorkItem: DispatchWorkItem?
  @State private var isSharingLink = false

  private var followUpInputView: some View {
    VStack(spacing: 0) {
      HStack(spacing: OmiSpacing.xs) {
        Button(action: { shareLink() }) {
          Image(systemName: showShareFeedback ? "checkmark" : "arrowshape.turn.up.right")
            .scaledFont(size: OmiType.body)
            .foregroundColor(showShareFeedback ? .green : .secondary)
        }
        .buttonStyle(.plain)
        .help("Copy share link")
        .disabled(isSharingLink)

        Button(action: { onOpenMainApp?() }) {
          HStack(spacing: OmiSpacing.xs) {
            Text("Continue in Omi")
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(.white.opacity(0.85))
            Spacer(minLength: 0)
            Image(systemName: "arrow.up.forward.app")
              .scaledFont(size: OmiType.body)
              .foregroundColor(.secondary)
          }
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xs)
          .background(Color.white.opacity(0.10))
          .cornerRadius(OmiChrome.elementRadius)
          .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Open the Omi app to keep chatting")
      }
      .chatComposerShell(fill: OmiColors.backgroundSecondary.opacity(0.82))
    }
  }

  private var shareFeedbackBanner: some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "checkmark.circle.fill")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(.green)

      Text("Share link copied to your clipboard")
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(.white)

      Spacer(minLength: 0)
    }
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.sm)
    .background(Color.green.opacity(0.18))
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
        .strokeBorder(Color.green.opacity(0.35), lineWidth: 1)
    )
    .cornerRadius(OmiChrome.elementRadius)
  }

  private func shareLink() {
    guard !isSharingLink else { return }
    isSharingLink = true
    Task {
      if let url = await onShareLink?() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(url, forType: .string)
        AnalyticsManager.shared.shareAction(category: "floating_bar_share_link")
        showShareSuccessFeedback()
      }
      isSharingLink = false
    }
  }

  private func showShareSuccessFeedback() {
    shareFeedbackHideWorkItem?.cancel()
    shareFeedbackMessage = "Share link copied to your clipboard"
    OmiMotion.withGated {
      showShareFeedback = true
    }

    let workItem = DispatchWorkItem {
      OmiMotion.withGated {
        showShareFeedback = false
        shareFeedbackMessage = nil
      }
    }
    shareFeedbackHideWorkItem = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.8, execute: workItem)
  }

}

// MARK: - Message Hover Overlay

/// Overlay that shows action buttons (thumbs up/down, copy, info) on hover over an AI message
struct MessageHoverOverlay<Content: View>: View {
  let message: ChatMessage
  let onRate: (Int?) -> Void
  @ViewBuilder let content: () -> Content

  @State private var isHovered = false
  @State private var isBarHovered = false
  @State private var showCopied = false
  @State private var showInfoPopover = false
  @State private var hideWorkItem: DispatchWorkItem?
  @State private var showRatingFeedback = false
  @State private var lastSubmittedRating: Int?

  private var shouldShowBar: Bool {
    (isHovered || isBarHovered || showInfoPopover) && !message.isStreaming
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        content()
      }
      .frame(maxWidth: .infinity, alignment: .leading)

      if shouldShowBar {
        actionBar
          .transition(.opacity)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .contentShape(Rectangle())
    .onHover { hovering in
      if hovering {
        // Show immediately
        hideWorkItem?.cancel()
        hideWorkItem = nil
        OmiMotion.withGated(.easeInOut(duration: 0.15)) {
          isHovered = true
        }
      } else {
        // Delay hide by 1.5s so user can move cursor to the buttons
        let work = DispatchWorkItem {
          OmiMotion.withGated(.easeInOut(duration: 0.15)) {
            isHovered = false
          }
        }
        hideWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5, execute: work)
      }
    }
  }

  private var actionBar: some View {
    // Capture the message's value-type fields once per body evaluation so every
    // button action operates on the exact message the user sees — not whatever
    // `self.message` happens to point to when the click is dispatched.
    let messageText = message.text
    let currentRating = message.rating
    return HStack(alignment: .top, spacing: OmiSpacing.xs) {
      Spacer(minLength: 0)

      VStack(alignment: .trailing, spacing: OmiSpacing.hairline) {
        HStack(spacing: OmiSpacing.xs) {
          // Thumbs up
          Button(action: { [currentRating] in
            let newRating = currentRating == 1 ? nil : 1
            guard newRating != lastSubmittedRating else { return }
            lastSubmittedRating = newRating
            onRate(newRating)
            if newRating != nil { showRatingFeedbackBriefly() }
          }) {
            Image(systemName: currentRating == 1 ? "hand.thumbsup.fill" : "hand.thumbsup")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(currentRating == 1 ? .green : .secondary)
          }
          .buttonStyle(.plain)
          .help("Helpful response")

          // Thumbs down
          Button(action: { [currentRating] in
            let newRating = currentRating == -1 ? nil : -1
            guard newRating != lastSubmittedRating else { return }
            lastSubmittedRating = newRating
            onRate(newRating)
            if newRating != nil { showRatingFeedbackBriefly() }
          }) {
            Image(systemName: currentRating == -1 ? "hand.thumbsdown.fill" : "hand.thumbsdown")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(currentRating == -1 ? .red : .secondary)
          }
          .buttonStyle(.plain)
          .help("Not helpful")
          // Sync the dedupe shadow to the live rating. The overlay is keyed
          // `.id(message.id)` so it re-mounts with lastSubmittedRating == nil,
          // while a restored/history message already carries a rating — without
          // this, clicking to clear it computes newRating == nil ==
          // lastSubmittedRating and the guard swallows the tap (rating stuck).
          .onChange(of: message.rating, initial: true) { _, newValue in
            lastSubmittedRating = newValue
          }

          // Copy — captures `messageText` explicitly so we always copy the
          // message this button was drawn for, even if SwiftUI reuses the
          // overlay view across re-renders.
          Button(action: { [messageText] in copyText(messageText) }) {
            Image(systemName: showCopied ? "checkmark" : "doc.on.doc")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(showCopied ? .green : .secondary)
          }
          .buttonStyle(.plain)
          .help("Copy response")

          // Info (developer context)
          if message.metadata != nil {
            Button(action: { showInfoPopover.toggle() }) {
              Image(systemName: "info.circle")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(showInfoPopover ? .white : .secondary)
            }
            .buttonStyle(.plain)
            .help("View response context")
            .popover(isPresented: $showInfoPopover, arrowEdge: .bottom) {
              MessageMetadataPopover(metadata: message.metadata!)
            }
          }
        }

        if showRatingFeedback {
          Text("Thank you")
            .scaledFont(size: OmiType.micro)
            .foregroundColor(.secondary)
            .transition(.opacity)
        }
      }
    }
    .omiAnimation(.easeInOut(duration: 0.2), value: showRatingFeedback)
    .frame(maxWidth: .infinity, alignment: .trailing)
    .onHover { hovering in
      isBarHovered = hovering
      if hovering {
        // Cancel any pending hide
        hideWorkItem?.cancel()
        hideWorkItem = nil
      }
    }
  }

  private func showRatingFeedbackBriefly() {
    showRatingFeedback = true
    DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
      showRatingFeedback = false
    }
  }

  /// Copy the exact text passed in — *not* `self.message.text`.
  /// Callers must pass the captured text from the closure's capture list so
  /// clicking Copy on a historical message writes the correct content to the
  /// pasteboard even when SwiftUI has reused the overlay view across renders.
  private func copyText(_ text: String) {
    guard !text.isEmpty else { return }
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(text, forType: .string)
    AnalyticsManager.shared.shareAction(category: "floating_bar_response_copy")
    OmiMotion.withGated { showCopied = true }
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
      OmiMotion.withGated { showCopied = false }
    }
  }
}

// MARK: - Metadata Popover

/// Developer popover showing full context used to generate an AI response
struct MessageMetadataPopover: View {
  let metadata: MessageMetadata

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        // Header
        Text("Response Context")
          .font(.headline)
          .foregroundColor(.primary)

        // Key info
        if let model = metadata.model {
          metadataRow(label: "Model", value: model)
        }
        if metadata.hasScreenshot, let size = metadata.screenshotSizeBytes {
          let kb = size / 1024
          let base64Chars = (size * 4 + 2) / 3  // base64 expansion
          metadataRow(label: "Screenshot", value: "1 image (\(kb) KB, ~\(base64Chars / 1024) KB base64)")
        } else {
          metadataRow(label: "Screenshot", value: "None")
        }

        Divider()

        // Context fed into the prompt
        Text("Context in Prompt")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(.primary)
        metadataRow(label: "User memories/facts", value: "\(metadata.memoriesCount)")
        metadataRow(label: "Conversation history turns", value: "\(metadata.conversationTurns)")
        metadataRow(label: "Tasks", value: "\(metadata.tasksCount)")
        metadataRow(label: "Goals", value: "\(metadata.goalsCount)")
        metadataRow(label: "Available tools", value: "\(metadata.availableToolsCount)")

        // Tool calls
        if !metadata.toolNames.isEmpty {
          Divider()
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            Text("Tools used (\(metadata.toolNames.count))")
              .scaledFont(size: OmiType.caption, weight: .semibold)
              .foregroundColor(.primary)
            ForEach(metadata.toolNames, id: \.self) { tool in
              Text("  \(tool)")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(.secondary)
                .textSelection(.enabled)
            }
            if metadata.sqlQueryCount > 0 {
              metadataRow(
                label: "SQL queries",
                value: "\(metadata.sqlQueryCount) queries, \(metadata.sqlRowsReturned) rows returned"
              )
            }
          }
        }

        // Full system prompt — always expanded, scrollable
        if let prompt = metadata.systemPrompt, !prompt.isEmpty {
          Divider()
          VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
            HStack {
              Text("Full System Prompt")
                .scaledFont(size: OmiType.caption, weight: .semibold)
                .foregroundColor(.primary)
              Spacer()
              Text("\(prompt.count) chars")
                .scaledFont(size: OmiType.micro)
                .foregroundColor(.secondary)
              Button(action: {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(prompt, forType: .string)
              }) {
                Image(systemName: "doc.on.doc")
                  .scaledFont(size: OmiType.micro)
                  .foregroundColor(.secondary)
              }
              .buttonStyle(.plain)
              .help("Copy prompt")
            }
            Text(prompt)
              .scaledFont(size: OmiType.micro)
              .foregroundColor(.primary)
              .textSelection(.enabled)
              .frame(maxWidth: .infinity, alignment: .leading)
          }
        }
      }
      .padding()
      .frame(width: 450)
    }
    .frame(width: 450, height: 500)
  }

  private func metadataRow(label: String, value: String) -> some View {
    HStack {
      Text(label)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(.secondary)
      Spacer()
      Text(value)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(.primary)
        .textSelection(.enabled)
    }
  }
}

// MARK: - Model Menu Helper

class ModelMenuTarget: NSObject {
  nonisolated(unsafe) static let shared = ModelMenuTarget()
  var onSelect: ((String) -> Void)?

  @objc func selectModel(_ sender: NSMenuItem) {
    if let modelId = sender.representedObject as? String {
      onSelect?(modelId)
    }
  }
}
