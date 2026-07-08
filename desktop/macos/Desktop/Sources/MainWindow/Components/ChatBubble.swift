import AppKit
import MarkdownUI
import SwiftUI
import OmiTheme

// MARK: - Chat Bubble

struct ChatBubble: View {
  let message: ChatMessage
  let app: OmiApp?
  let onRate: (Int?) -> Void
  var onCitationTap: ((Citation) -> Void)? = nil
  var isDuplicate: Bool = false
  /// Optional cancel action for stalled tool-call banners, threaded
  /// down to `ToolCallsGroup`. Optional so existing callers compile
  /// without wiring cancellation.
  var onCancelTurn: (() -> Void)? = nil
  var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil
  var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil

  @State private var isTimestampHovering = false
  @State private var isExpanded = false
  @State private var showCopied = false
  @State private var showRatingFeedback = false
  @State private var showInfoPopover = false
  @State private var lastSubmittedRating: Int?

  init(
    message: ChatMessage, app: OmiApp?, onRate: @escaping (Int?) -> Void,
    onCitationTap: ((Citation) -> Void)? = nil, isDuplicate: Bool = false,
    onCancelTurn: (() -> Void)? = nil,
    onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil,
    onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil
  ) {
    self.message = message
    self.app = app
    self.onRate = onRate
    self.onCitationTap = onCitationTap
    self.isDuplicate = isDuplicate
    self.onCancelTurn = onCancelTurn
    self.onOpenAgent = onOpenAgent
    self.onOpenAgentRef = onOpenAgentRef
    _lastSubmittedRating = State(initialValue: message.rating)
  }

  /// Messages longer than this are truncated with a "Show more" button
  private static let truncationThreshold = 500

  /// Whether this message should be truncated
  private var shouldTruncate: Bool {
    !message.isStreaming && message.text.count > Self.truncationThreshold && !isExpanded
  }

  /// The text to display (truncated or full) — keeps the start of the message visible
  private var displayText: String {
    if shouldTruncate {
      return String(message.text.prefix(Self.truncationThreshold)).trimmingCharacters(
        in: .whitespacesAndNewlines
      ) + "…"
    }
    return message.text
  }

  private var backgroundAgentSummary: BackgroundAgentSummary? {
    guard message.sender == .ai, message.contentBlocks.isEmpty else { return nil }
    return BackgroundAgentSummary.parse(message.text)
  }

  private func openAgent(ref: AgentTimelineRef, completion: @escaping (Bool) -> Void) {
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

  var body: some View {
    let groupedBlocks = ContentBlockGroup.visibleChatGroups(
      message.contentBlocks,
      isStreaming: message.isStreaming
    )

    HStack(alignment: .top, spacing: 12) {
      if message.sender == .ai {
        // App avatar
        if let app = app {
          AsyncImage(url: URL(string: app.image)) { phase in
            switch phase {
            case .success(let image):
              image
                .resizable()
                .aspectRatio(contentMode: .fill)
            default:
              Circle()
                .fill(OmiColors.backgroundTertiary)
            }
          }
          .frame(width: 32, height: 32)
          .clipShape(Circle())
        } else {
          if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
            let logoImage = NSImage(contentsOf: logoURL)
          {
            Image(nsImage: logoImage)
              .resizable()
              .scaledToFit()
              .frame(width: 20, height: 20)
              .frame(width: 32, height: 32)
              .background(OmiColors.backgroundTertiary)
              .clipShape(Circle())
          }
        }
      }

      VStack(alignment: message.sender == .user ? .trailing : .leading, spacing: 4) {
        if message.isStreaming && message.text.isEmpty && message.contentBlocks.isEmpty {
          // Show typing indicator for empty streaming message
          TypingIndicator()
        } else if message.sender == .ai && !message.contentBlocks.isEmpty {
          // Render structured content blocks, grouping consecutive tool calls
          ForEach(groupedBlocks) { group in
            switch group {
            case .text(_, let text):
              if !text.isEmpty {
                SelectableMarkdown(text: text, sender: .ai)
                  .padding(.horizontal, 14)
                  .padding(.vertical, 10)
                  .background(OmiColors.backgroundTertiary.opacity(0.92))
                  .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                  .padding(.top, 2)
              }
            case .toolCalls(_, let calls):
              ToolCallsGroup(
                calls: calls,
                onCancel: onCancelTurn,
                onOpenAgent: onOpenAgent,
                onOpenAgentRef: onOpenAgentRef
              )
            case .thinking(_, let text):
              ThinkingBlock(text: text)
            case .discoveryCard(_, let title, let summary, let fullText):
              DiscoveryCard(title: title, summary: summary, fullText: fullText)
            case .agentSpawn(_, let pillId, let sessionId, let runId, let title, let objective):
              AgentSpawnCard(
                title: title,
                objective: objective,
                ref: AgentTimelineRef(pillId: pillId, sessionId: sessionId, runId: runId),
                onOpen: openAgent(ref:completion:)
              )
            case .agentCompletion(
              _, let pillId, let sessionId, let runId, let title, let promptSnippet, let output, let status
            ):
              AgentCompletionCard(
                title: title,
                promptSnippet: promptSnippet,
                output: output,
                status: status,
                ref: AgentTimelineRef(pillId: pillId, sessionId: sessionId, runId: runId),
                onOpen: openAgent(ref:completion:)
              )
            }
          }
          // Show typing indicator at end if still streaming
          // (skip only when last group is tool calls with an in-flight tool — it already has a spinner)
          if message.isStreaming {
            if case .toolCalls(_, let calls) = groupedBlocks.last,
              calls.contains(where: { block in
                if case .toolCall(_, _, let status, _, _, _) = block { return status.isInFlight }
                return false
              })
            {
              // Tool group has a running tool — its card already shows a spinner
            } else {
              TypingIndicator()
            }
          }
          if !message.displayResources.isEmpty {
            ChatResourceStrip(resources: message.displayResources, density: .full, alignment: .leading)
          }
        } else if isDuplicate && !isExpanded {
          // Collapsed duplicate message
          Button(action: { isExpanded = true }) {
            HStack(spacing: 6) {
              Image(systemName: "doc.on.doc")
                .scaledFont(size: 11)
              Text("Duplicate message")
                .scaledFont(size: 12)
              Image(systemName: "chevron.down")
                .scaledFont(size: 9)
            }
            .foregroundColor(OmiColors.textTertiary)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(OmiColors.backgroundTertiary.opacity(0.72))
            .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
          }
          .buttonStyle(.plain)
        } else {
          // User messages or AI messages without content blocks (loaded from Firestore)
          VStack(alignment: message.sender == .user ? .trailing : .leading, spacing: 6) {
            // User attachments read as "here's what I'm sending" and belong
            // above the text; AI-generated artifacts are the result of the
            // reply and always sit below it.
            let resourceStrip = message.displayResources.isEmpty
              ? nil
              : ChatResourceStrip(
                resources: message.displayResources,
                density: .full,
                alignment: message.sender == .user ? .trailing : .leading
              )

            if message.sender == .user, let resourceStrip {
              resourceStrip
            }

            if let backgroundAgentSummary {
              BackgroundAgentSummaryCard(summary: backgroundAgentSummary, onOpenAgent: onOpenAgent)
            } else if !message.text.isEmpty {
              SelectableMarkdown(text: displayText, sender: message.sender)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                  message.sender == .user
                    ? OmiColors.userBubble : OmiColors.backgroundTertiary.opacity(0.95)
                )
                .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                .padding(.top, 2)
            }

            // Show more / Show less toggle for long messages
            if message.text.count > Self.truncationThreshold {
              Button(action: { isExpanded.toggle() }) {
                Text(isExpanded ? "Show less" : "Show more")
                  .scaledFont(size: 11)
                  .foregroundColor(.white)
              }
              .buttonStyle(.plain)
            }

            if message.sender != .user, let resourceStrip {
              resourceStrip
            }
          }
        }

        // Citation cards for AI messages with citations
        if message.sender == .ai && !message.citations.isEmpty && !message.isStreaming {
          CitationCardsView(citations: message.citations) { citation in
            onCitationTap?(citation)
          }
          .frame(maxWidth: 280)
        }

        // Rating buttons, copy button, and message metadata
        if message.sender == .ai && !message.isStreaming && message.isSynced {
          messageMetadataRow(includeRatingButtons: true, includeCopyButton: true)
        } else if message.sender == .ai && !message.isStreaming && !message.copyableText.isEmpty {
          messageMetadataRow(includeRatingButtons: false, includeCopyButton: true)
        } else if !message.isStreaming || !message.text.isEmpty {
          messageMetadataRow(includeRatingButtons: false, includeCopyButton: false)
        }
      }

      if message.sender == .user {
        // User avatar
        Image(systemName: "person.fill")
          .scaledFont(size: 14)
          .foregroundColor(OmiColors.textSecondary)
          .frame(width: 32, height: 32)
          .background(OmiColors.backgroundTertiary)
          .clipShape(Circle())
      }
    }
    .frame(maxWidth: .infinity, alignment: message.sender == .user ? .trailing : .leading)
    .contentShape(Rectangle())
  }

  @ViewBuilder
  private func messageMetadataRow(includeRatingButtons: Bool, includeCopyButton: Bool) -> some View {
    HStack(spacing: 8) {
      if includeRatingButtons {
        ratingButtons
      }

      if includeCopyButton {
        copyButton
      }

      if includeCopyButton, message.metadata != nil {
        infoButton
      }

      Text(message.createdAt, format: .dateTime.hour().minute())
        .scaledFont(size: 10, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)
        .onHover { isTimestampHovering = $0 }

      if isTimestampHovering {
        Text(message.createdAt, format: .dateTime.month(.abbreviated).day())
          .scaledFont(size: 10, weight: .medium)
          .foregroundColor(OmiColors.textSecondary)
          .transition(.opacity)
      }
    }
    .animation(.easeInOut(duration: 0.12), value: isTimestampHovering)
  }

  @ViewBuilder
  private var ratingButtons: some View {
    HStack(spacing: 4) {
      // Thumbs up
      Button(action: {
        let newRating = message.rating == 1 ? nil : 1
        guard newRating != lastSubmittedRating else { return }
        lastSubmittedRating = newRating
        onRate(newRating)
        if newRating != nil { showRatingFeedbackBriefly() }
      }) {
        Image(systemName: message.rating == 1 ? "hand.thumbsup.fill" : "hand.thumbsup")
          .scaledFont(size: 11)
          .foregroundColor(message.rating == 1 ? OmiColors.purplePrimary : OmiColors.textTertiary)
      }
      .buttonStyle(.plain)
      .help("Helpful response")

      // Thumbs down
      Button(action: {
        let newRating = message.rating == -1 ? nil : -1
        guard newRating != lastSubmittedRating else { return }
        lastSubmittedRating = newRating
        onRate(newRating)
        if newRating != nil { showRatingFeedbackBriefly() }
      }) {
        Image(systemName: message.rating == -1 ? "hand.thumbsdown.fill" : "hand.thumbsdown")
          .scaledFont(size: 11)
          .foregroundColor(message.rating == -1 ? .red : OmiColors.textTertiary)
      }
      .buttonStyle(.plain)
      .help("Not helpful")

      if showRatingFeedback {
        Text("Thank you!")
          .scaledFont(size: 10)
          .foregroundColor(OmiColors.textTertiary)
          .transition(.opacity)
      }
    }
    .animation(.easeInOut(duration: 0.2), value: showRatingFeedback)
  }

  private func showRatingFeedbackBriefly() {
    showRatingFeedback = true
    DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
      showRatingFeedback = false
    }
  }

  @ViewBuilder
  private var copyButton: some View {
    Button(action: {
      NSPasteboard.general.clearContents()
      NSPasteboard.general.setString(message.copyableText, forType: .string)
      showCopied = true
      DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
        showCopied = false
      }
    }) {
      Image(systemName: showCopied ? "checkmark" : "doc.on.doc")
        .scaledFont(size: 11)
        .foregroundColor(showCopied ? .green : OmiColors.textTertiary)
    }
    .buttonStyle(.plain)
    .help("Copy message")
  }

  /// Response Context popover — same developer info the floating bar shows
  /// (model, screenshot, prompt context counts, tools). Only fresh responses
  /// carry metadata; it is in-memory only and not persisted across restarts.
  @ViewBuilder
  private var infoButton: some View {
    Button(action: { showInfoPopover.toggle() }) {
      Image(systemName: "info.circle")
        .scaledFont(size: 11)
        .foregroundColor(showInfoPopover ? OmiColors.textPrimary : OmiColors.textTertiary)
    }
    .buttonStyle(.plain)
    .help("View response context")
    .popover(isPresented: $showInfoPopover, arrowEdge: .bottom) {
      if let metadata = message.metadata {
        MessageMetadataPopover(metadata: metadata)
      }
    }
  }
}

struct BackgroundAgentSummary: Equatable {
  let agentID: UUID?
  let prompt: String
  let output: String

  static func parse(_ text: String) -> BackgroundAgentSummary? {
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.hasPrefix("[Background agent") else { return nil }
    guard let close = trimmed.firstIndex(of: "]") else { return nil }

    let headerStart = trimmed.index(trimmed.startIndex, offsetBy: 1)
    let header = String(trimmed[headerStart..<close])
    guard header.hasPrefix("Background agent") else { return nil }

    var remainder = String(header.dropFirst("Background agent".count))
      .trimmingCharacters(in: .whitespacesAndNewlines)
    var agentID: UUID?

    if remainder.hasPrefix("id=") {
      remainder.removeFirst(3)
      let idEnd = remainder.firstIndex { $0 == " " || $0 == "—" } ?? remainder.endIndex
      let idText = String(remainder[..<idEnd]).trimmingCharacters(in: .whitespacesAndNewlines)
      agentID = UUID(uuidString: idText)
      remainder = String(remainder[idEnd...]).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    if remainder.hasPrefix("—") {
      remainder.removeFirst()
      remainder = remainder.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    let outputStart = trimmed.index(after: close)
    let output = String(trimmed[outputStart...]).trimmingCharacters(in: .whitespacesAndNewlines)
    guard !output.isEmpty else { return nil }

    return BackgroundAgentSummary(
      agentID: agentID,
      prompt: remainder.isEmpty ? "Background agent" : remainder,
      output: output
    )
  }
}

private struct BackgroundAgentSummaryCard: View {
  let summary: BackgroundAgentSummary
  var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil

  @State private var isExpanded = false
  @State private var showUnavailable = false

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Button(action: {
        if let agentID = summary.agentID, let onOpenAgent {
          onOpenAgent(agentID) { succeeded in
            if AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: succeeded) {
              showUnavailable = true
            }
          }
        } else {
          withAnimation(.easeInOut(duration: 0.18)) {
            isExpanded.toggle()
          }
        }
      }) {
        HStack(spacing: 8) {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: 12)
            .foregroundColor(.green)
          Text("Background agent")
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
          Text(summary.output)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
            .truncationMode(.tail)
          Spacer(minLength: 4)
          Image(systemName: summary.agentID != nil && onOpenAgent != nil ? "arrow.up.forward.app" : (isExpanded ? "chevron.up" : "chevron.down"))
            .scaledFont(size: 9)
            .foregroundColor(OmiColors.textTertiary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .frame(maxWidth: .infinity, alignment: .leading)
      }
      .buttonStyle(.plain)

      if isExpanded || summary.agentID == nil || showUnavailable {
        Divider()
          .padding(.horizontal, 10)
        VStack(alignment: .leading, spacing: 8) {
          Text(summary.prompt)
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(3)
          Text(summary.output)
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textPrimary)
            .fixedSize(horizontal: false, vertical: true)
          if showUnavailable {
            Text("Agent unavailable — it may have been dismissed.")
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .omiControlSurface(fill: OmiColors.backgroundTertiary.opacity(0.88), radius: 16)
  }
}

private struct AgentSpawnCard: View {
  let title: String
  let objective: String
  let ref: AgentTimelineRef
  var onOpen: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil

  @State private var showUnavailable = false

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Button(action: {
        if ref.hasIdentity, let onOpen {
          onOpen(ref) { succeeded in
            if AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: succeeded) {
              showUnavailable = true
            }
          }
        }
      }) {
        HStack(spacing: 8) {
          Image(systemName: "arrow.triangle.branch")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textSecondary)
          Text(title.isEmpty ? "Background agent" : title)
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
          Text(objective)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
            .truncationMode(.tail)
          Spacer(minLength: 4)
          if ref.hasIdentity {
            Image(systemName: "arrow.up.forward.app")
              .scaledFont(size: 9)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .frame(maxWidth: .infinity, alignment: .leading)
      }
      .buttonStyle(.plain)

      if showUnavailable {
        Divider()
          .padding(.horizontal, 10)
        Text("Agent unavailable — it may have been dismissed.")
          .scaledFont(size: 11)
          .foregroundColor(OmiColors.textTertiary)
          .padding(.horizontal, 12)
          .padding(.vertical, 10)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .omiControlSurface(fill: OmiColors.backgroundTertiary.opacity(0.88), radius: 16)
  }
}

private struct AgentCompletionCard: View {
  let title: String
  let promptSnippet: String
  let output: String
  let status: String
  let ref: AgentTimelineRef
  var onOpen: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil

  @State private var isExpanded = false
  @State private var showUnavailable = false

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      Button(action: {
        if ref.hasIdentity, let onOpen {
          onOpen(ref) { succeeded in
            if AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: succeeded) {
              showUnavailable = true
            }
          }
        } else {
          withAnimation(.easeInOut(duration: 0.18)) {
            isExpanded.toggle()
          }
        }
      }) {
        HStack(spacing: 8) {
          Image(systemName: statusIconName)
            .scaledFont(size: 12)
            .foregroundColor(statusColor)
          Text(title.isEmpty ? "Background agent" : title)
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(OmiColors.textSecondary)
          Text(output)
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
            .truncationMode(.tail)
          Spacer(minLength: 4)
          Image(systemName: ref.hasIdentity && onOpen != nil ? "arrow.up.forward.app" : (isExpanded ? "chevron.up" : "chevron.down"))
            .scaledFont(size: 9)
            .foregroundColor(OmiColors.textTertiary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .frame(maxWidth: .infinity, alignment: .leading)
      }
      .buttonStyle(.plain)

      if isExpanded || !ref.hasIdentity || showUnavailable {
        Divider()
          .padding(.horizontal, 10)
        VStack(alignment: .leading, spacing: 8) {
          if !promptSnippet.isEmpty {
            Text(promptSnippet)
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(3)
          }
          Text(output)
            .scaledFont(size: 13)
            .foregroundColor(OmiColors.textPrimary)
            .fixedSize(horizontal: false, vertical: true)
          if showUnavailable {
            Text("Agent unavailable — it may have been dismissed.")
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .omiControlSurface(fill: OmiColors.backgroundTertiary.opacity(0.88), radius: 16)
  }

  private var statusIconName: String {
    switch status.lowercased() {
    case "failed", "cancelled", "stopped", "timed_out", "orphaned":
      return "xmark.circle.fill"
    default:
      return "checkmark.circle.fill"
    }
  }

  private var statusColor: Color {
    switch status.lowercased() {
    case "failed", "cancelled", "stopped", "timed_out", "orphaned":
      return .red
    default:
      return .green
    }
  }
}

extension ChatBubble: Equatable {
  static func == (lhs: ChatBubble, rhs: ChatBubble) -> Bool {
    // Streaming messages always re-render so SwiftUI sees live updates
    guard !lhs.message.isStreaming && !rhs.message.isStreaming else { return false }
    // Completed messages are equal when visible content hasn't changed
    return lhs.message.id == rhs.message.id
      && lhs.message.text == rhs.message.text
      && lhs.message.rating == rhs.message.rating
      && lhs.app?.id == rhs.app?.id
      && lhs.isDuplicate == rhs.isDuplicate
  }
}

// MARK: - Content Block Grouping

/// Groups consecutive tool call blocks into a single collapsible group
enum ContentBlockGroup: Identifiable {
  case text(id: String, text: String)
  case toolCalls(id: String, calls: [ChatContentBlock])
  case thinking(id: String, text: String)
  case discoveryCard(id: String, title: String, summary: String, fullText: String)
  case agentSpawn(
    id: String,
    pillId: UUID?,
    sessionId: String,
    runId: String,
    title: String,
    objective: String
  )
  case agentCompletion(
    id: String,
    pillId: UUID?,
    sessionId: String?,
    runId: String?,
    title: String,
    promptSnippet: String,
    output: String,
    status: String
  )

  var id: String {
    switch self {
    case .text(let id, _): return id
    case .toolCalls(let id, _): return id
    case .thinking(let id, _): return id
    case .discoveryCard(let id, _, _, _): return id
    case .agentSpawn(let id, _, _, _, _, _): return id
    case .agentCompletion(let id, _, _, _, _, _, _, _): return id
    }
  }

  /// Groups consecutive `.toolCall` blocks together; passes other blocks through
  static func group(_ blocks: [ChatContentBlock]) -> [ContentBlockGroup] {
    var groups: [ContentBlockGroup] = []
    var pendingToolCalls: [ChatContentBlock] = []

    func flushToolCalls() {
      guard let first = pendingToolCalls.first else { return }
      let groupId = "toolgroup_\(first.id)"
      groups.append(.toolCalls(id: groupId, calls: pendingToolCalls))
      pendingToolCalls = []
    }

    for block in blocks {
      switch block {
      case .text(let id, let text):
        flushToolCalls()
        groups.append(.text(id: id, text: text))
      case .toolCall:
        pendingToolCalls.append(block)
      case .thinking(let id, let text):
        flushToolCalls()
        groups.append(.thinking(id: id, text: text))
      case .discoveryCard(let id, let title, let summary, let fullText):
        flushToolCalls()
        groups.append(.discoveryCard(id: id, title: title, summary: summary, fullText: fullText))
      case .agentSpawn(let id, let pillId, let sessionId, let runId, let title, let objective):
        flushToolCalls()
        groups.append(
          .agentSpawn(
            id: id,
            pillId: pillId,
            sessionId: sessionId,
            runId: runId,
            title: title,
            objective: objective
          )
        )
      case .agentCompletion(
        let id, let pillId, let sessionId, let runId, let title, let promptSnippet, let output, let status
      ):
        flushToolCalls()
        groups.append(
          .agentCompletion(
            id: id,
            pillId: pillId,
            sessionId: sessionId,
            runId: runId,
            title: title,
            promptSnippet: promptSnippet,
            output: output,
            status: status
          )
        )
      }
    }
    flushToolCalls()
    return groups
  }

  /// Main chat renders the agent's final answer and sub-agent entrypoints, not
  /// the implementation log of every completed tool. While a response is live,
  /// in-flight tools remain visible as progress feedback; after completion,
  /// only spawned-agent links survive.
  static func visibleChatGroups(_ blocks: [ChatContentBlock], isStreaming: Bool) -> [ContentBlockGroup] {
    group(blocks).compactMap { group in
      switch group {
      case .text, .discoveryCard, .agentSpawn, .agentCompletion:
        return group
      case .thinking:
        return isStreaming ? group : nil
      case .toolCalls(let id, let calls):
        let spawnedAgentCalls = calls.filter { $0.spawnedAgentID != nil }
        if !spawnedAgentCalls.isEmpty {
          return .toolCalls(id: id, calls: spawnedAgentCalls)
        }
        guard isStreaming else { return nil }
        let inFlightCalls = calls.filter { block in
          if case .toolCall(_, _, let status, _, _, _) = block {
            return status.isInFlight
          }
          return false
        }
        return inFlightCalls.isEmpty ? nil : .toolCalls(id: id, calls: inFlightCalls)
      }
    }
  }
}

// MARK: - Tool Calls Group

/// Renders a group of consecutive tool calls as a single summary line with
/// optional expanded per-step details.
struct ToolCallsGroup: View {
  let calls: [ChatContentBlock]
  var compact: Bool = false
  var expandRunning: Bool = true
  /// `ChatProvider` wires this to `agentBridge.interrupt()` via the
  /// parent message view. If no action is available, the banner is hidden
  /// so the UI never presents a no-op Cancel button.
  var onCancel: (() -> Void)? = nil
  var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil
  var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil

  @State private var isExpanded: Bool
  @State private var showUnavailable = false

  init(
    calls: [ChatContentBlock],
    compact: Bool = false,
    expandRunning: Bool = true,
    onCancel: (() -> Void)? = nil,
    onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil,
    onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil
  ) {
    self.calls = calls
    self.compact = compact
    self.expandRunning = expandRunning
    self.onCancel = onCancel
    self.onOpenAgent = onOpenAgent
    self.onOpenAgentRef = onOpenAgentRef
    self._isExpanded = State(initialValue: expandRunning && Self.hasRunningTool(in: calls))
  }

  /// Whether any tool in the group is still running.
  private var hasRunningTool: Bool {
    Self.hasRunningTool(in: calls)
  }

  /// True iff at least one tool in the group is `.stalled` and is not a
  /// tool we expect to run long (shell, file writes, web fetches, agents).
  /// Drives the message-level "taking longer than usual" banner, which we
  /// suppress for long-by-design work so it doesn't cry wolf.
  private var hasStalledTool: Bool {
    calls.contains { block in
      if case .toolCall(_, let name, .stalled, _, _, _) = block {
        return !ChatContentBlock.isSlowExpectedTool(name)
      }
      return false
    }
  }

  /// Most attention-worthy status across the group. Drives the header
  /// icon. Priority: stalled > failed > slow > running > completed.
  private var aggregateStatus: ToolCallStatus {
    var hasStalled = false
    var hasFailed = false
    var hasSlow = false
    var hasRunning = false
    for block in calls {
      if case .toolCall(_, let name, let status, _, _, _) = block {
        switch status {
        case .stalled:
          // Long-by-design tools surface as "slow" (spinner), never the
          // alarming stalled triangle.
          if ChatContentBlock.isSlowExpectedTool(name) { hasSlow = true } else { hasStalled = true }
        case .failed: hasFailed = true
        case .slow: hasSlow = true
        case .running: hasRunning = true
        case .completed: break
        }
      }
    }
    if hasStalled { return .stalled }
    if hasFailed { return .failed }
    if hasSlow { return .slow }
    if hasRunning { return .running }
    return .completed
  }

  /// Display name of the currently in-flight tool (last in-flight one), or last tool if all done.
  private var currentToolName: String {
    if let lastRunning = calls.last(where: { block in
      if case .toolCall(_, _, let status, _, _, _) = block { return status.isInFlight }
      return false
    }) {
      if case .toolCall(_, let name, _, _, _, _) = lastRunning {
        return ChatContentBlock.displayName(for: name)
      }
    }
    if case .toolCall(_, let name, _, _, _, _) = calls.last {
      return ChatContentBlock.displayName(for: name)
    }
    return "Working"
  }

  private var currentToolSummary: String? {
    if let lastRunning = calls.last(where: { block in
      if case .toolCall(_, _, let status, _, _, _) = block { return status.isInFlight }
      return false
    }), case .toolCall(_, let name, _, _, let input, _) = lastRunning {
      return input?.summary ?? Self.summaryEmbeddedInToolName(name)
    }
    if case .toolCall(_, let name, _, _, let input, _) = calls.last {
      return input?.summary ?? Self.summaryEmbeddedInToolName(name)
    }
    return nil
  }

  private var spawnedAgentOpenRef: AgentTimelineRef? {
    calls.compactMap(\.agentOpenRef).last
  }

  private var canOpenSpawnedAgent: Bool {
    spawnedAgentOpenRef != nil && (onOpenAgentRef != nil || onOpenAgent != nil)
  }

  private func openSpawnedAgent(completion: @escaping (Bool) -> Void) {
    guard let ref = spawnedAgentOpenRef else {
      completion(false)
      return
    }
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

  var body: some View {
    VStack(alignment: .leading, spacing: compact ? 0 : 6) {
      if hasStalledTool, let onCancel {
        ToolCallStalledBanner(onCancel: onCancel)
      }

      header

      if isExpanded {
        expandedToolCalls
      }

      if showUnavailable {
        Text("Agent unavailable — it may have been dismissed.")
          .scaledFont(size: 11)
          .foregroundColor(OmiColors.textTertiary)
          .padding(.horizontal, 10)
          .padding(.bottom, compact ? 6 : 8)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .omiControlSurface(fill: OmiColors.backgroundTertiary.opacity(0.82), radius: compact ? 14 : 16)
    .onChange(of: hasRunningTool) { _, isRunning in
      guard expandRunning, isRunning else { return }
      withAnimation(.easeInOut(duration: 0.18)) {
        isExpanded = true
      }
    }
  }

  private var header: some View {
    Button(action: {
      if canOpenSpawnedAgent {
        openSpawnedAgent { succeeded in
          if AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: succeeded) {
            showUnavailable = true
          }
        }
        return
      }
      withAnimation(.easeInOut(duration: 0.2)) {
        isExpanded.toggle()
      }
    }) {
      HStack(spacing: compact ? 7 : 6) {
        statusIcon(for: aggregateStatus, size: 12)

        Text(currentToolName)
          .scaledFont(size: 12, weight: compact ? .semibold : .regular)
          .foregroundColor(OmiColors.textSecondary)
          .lineLimit(1)

        if let summary = currentToolSummary, !summary.isEmpty {
          Text(summary)
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
            .truncationMode(.middle)
        }

        if calls.count > 1 {
          Text(compact ? "· \(calls.count) steps" : "·")
            .scaledFont(size: compact ? 11 : 12)
            .foregroundColor(OmiColors.textTertiary)
            .lineLimit(1)
          if !compact {
            Text("\(calls.count) steps")
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
          }
        }

        Spacer(minLength: compact ? 0 : 4)

        Image(systemName: canOpenSpawnedAgent ? "arrow.up.forward.app" : (isExpanded ? "chevron.up" : "chevron.down"))
          .scaledFont(size: 9)
          .foregroundColor(OmiColors.textTertiary)
      }
      .padding(.horizontal, 10)
      .padding(.vertical, compact ? 0 : 6)
      .frame(height: compact ? 34 : nil)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .buttonStyle(.plain)
  }

  private var expandedToolCalls: some View {
    VStack(alignment: .leading, spacing: 0) {
      Divider()
        .padding(.horizontal, 8)

      VStack(alignment: .leading, spacing: 4) {
        ForEach(calls) { block in
          if case .toolCall(_, let name, let status, _, let input, let output) = block {
            ToolCallCard(
              name: name,
              status: status,
              input: input,
              output: output,
              agentOpenRef: block.agentOpenRef,
              onOpenAgent: onOpenAgent,
              onOpenAgentRef: onOpenAgentRef
            )
          }
        }
      }
      .padding(.horizontal, 6)
      .padding(.vertical, 6)
    }
  }

  private static func hasRunningTool(in calls: [ChatContentBlock]) -> Bool {
    calls.contains { block in
      if case .toolCall(_, _, let status, _, _, _) = block { return status.isInFlight }
      return false
    }
  }

  private static func summaryEmbeddedInToolName(_ name: String) -> String? {
    guard let separator = name.firstIndex(of: ":") else { return nil }
    let summary = name[name.index(after: separator)...]
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return summary.isEmpty ? nil : summary
  }
}

// MARK: - Tool Call Card

struct ToolCallCard: View {
  let name: String
  let status: ToolCallStatus
  let input: ToolCallInput?
  let output: String?
  var agentOpenRef: AgentTimelineRef? = nil
  var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil
  var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil

  @State private var isExpanded = false
  @State private var showUnavailable = false

  private var hasExpandableContent: Bool {
    input?.details != nil || output != nil
  }

  private var canOpenSpawnedAgent: Bool {
    agentOpenRef != nil && (onOpenAgentRef != nil || onOpenAgent != nil)
  }

  private func openSpawnedAgent(completion: @escaping (Bool) -> Void) {
    guard let ref = agentOpenRef else {
      completion(false)
      return
    }
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

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Compact header row
      Button(action: {
        if canOpenSpawnedAgent {
          openSpawnedAgent { succeeded in
            if AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: succeeded) {
              showUnavailable = true
            }
          }
          return
        }
        if hasExpandableContent {
          withAnimation(.easeInOut(duration: 0.2)) {
            isExpanded.toggle()
          }
        }
      }) {
        HStack(spacing: 6) {
          // Status indicator — uses the shared statusIcon helper so
          // .slow / .stalled / .failed render the same way here as in
          // the group header.
          statusIcon(for: status, size: 12)

          // Tool name
          Text(ChatContentBlock.displayName(for: name))
            .scaledFont(size: 12, design: .monospaced)
            .foregroundColor(OmiColors.textSecondary)

          // Inline argument summary
          if let summary = input?.summary {
            Text("·")
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textTertiary)

            Text(summary)
              .scaledFont(size: 11, design: .monospaced)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(1)
              .truncationMode(.middle)
          }

          Spacer(minLength: 4)

          // Expand chevron
          if canOpenSpawnedAgent {
            Image(systemName: "arrow.up.forward.app")
              .scaledFont(size: 9)
              .foregroundColor(OmiColors.textTertiary)
          } else if hasExpandableContent {
            Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
              .scaledFont(size: 9)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
      }
      .buttonStyle(.plain)

      // Expanded content
      if isExpanded || showUnavailable {
        Divider()
          .padding(.horizontal, 8)

        VStack(alignment: .leading, spacing: 8) {
          // Input details
          if let details = input?.details {
            VStack(alignment: .leading, spacing: 2) {
              Text("Input")
                .scaledFont(size: 10, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)

              Text(details)
                .scaledFont(size: 11, design: .monospaced)
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(10)
            }
          }

          // Output
          if let output = output, !output.isEmpty {
            VStack(alignment: .leading, spacing: 2) {
              Text("Output")
                .scaledFont(size: 10, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)

              Text(output)
                .scaledFont(size: 11, design: .monospaced)
                .foregroundColor(OmiColors.textSecondary)
                .lineLimit(15)
            }
          }

          if showUnavailable {
            Text("Agent unavailable — it may have been dismissed.")
              .scaledFont(size: 11)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
      }
    }
    .omiControlSurface(fill: OmiColors.backgroundTertiary.opacity(0.8), radius: 16)
  }
}

extension ChatContentBlock {
  var agentOpenRef: AgentTimelineRef? {
    if let ref = agentTimelineRef, ref.hasIdentity {
      return ref
    }
    let ref = AgentTimelineRef(
      pillId: spawnedAgentID,
      sessionId: spawnedAgentSessionID,
      runId: spawnedAgentRunID
    )
    return ref.hasIdentity ? ref : nil
  }

  var spawnedAgentID: UUID? {
    if case .agentSpawn(_, let pillId, _, _, _, _) = self {
      return pillId
    }
    if case .agentCompletion(_, let pillId, _, _, _, _, _, _) = self {
      return pillId
    }
    guard case .toolCall(_, let name, let status, _, _, let output) = self,
      Self.cleanToolName(name) == "spawn_agent",
      !status.isInFlight,
      let output
    else { return nil }

    return Self.labeledValue(in: output, keys: ["id"]).flatMap(UUID.init(uuidString:))
  }

  var spawnedAgentSessionID: String? {
    if case .agentSpawn(_, _, let sessionId, _, _, _) = self {
      return sessionId
    }
    if case .agentCompletion(_, _, let sessionId, _, _, _, _, _) = self {
      return sessionId
    }
    guard case .toolCall(_, let name, let status, _, _, let output) = self,
      Self.cleanToolName(name) == "spawn_agent",
      !status.isInFlight,
      let output
    else { return nil }
    return Self.labeledValue(in: output, keys: ["sessionid", "session_id"])
  }

  var spawnedAgentRunID: String? {
    if case .agentSpawn(_, _, _, let runId, _, _) = self {
      return runId
    }
    if case .agentCompletion(_, _, _, let runId, _, _, _, _) = self {
      return runId
    }
    guard case .toolCall(_, let name, let status, _, _, let output) = self,
      Self.cleanToolName(name) == "spawn_agent",
      !status.isInFlight,
      let output
    else { return nil }
    return Self.labeledValue(in: output, keys: ["runid", "run_id"])
  }

  private static func labeledValue(in output: String, keys: [String]) -> String? {
    let keySet = Set(keys.map { $0.lowercased() })
    for line in output.components(separatedBy: .newlines) {
      let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
      guard let colon = trimmed.firstIndex(of: ":") else { continue }
      let label = String(trimmed[..<colon]).trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
      guard keySet.contains(label) else { continue }
      let value = String(trimmed[trimmed.index(after: colon)...])
        .trimmingCharacters(in: .whitespacesAndNewlines)
      if !value.isEmpty { return value }
    }
    return nil
  }

  private static func cleanToolName(_ name: String) -> String {
    guard name.hasPrefix("mcp__") else { return name }
    return String(name.split(separator: "__").last ?? Substring(name))
  }
}

// MARK: - Tool Call Status Icon (shared by ToolCallsGroup + ToolCallCard)

/// Single source of truth for how each `ToolCallStatus` value renders
/// as a small inline icon. Used in both the group header and individual
/// tool rows so the visual language is consistent.
@ViewBuilder
private func statusIcon(for status: ToolCallStatus, size: CGFloat) -> some View {
  switch status {
  case .running:
    ProgressView()
      .controlSize(.mini)
      .frame(width: size, height: size)
  case .slow:
    ProgressView()
      .controlSize(.mini)
      .frame(width: size, height: size)
      .tint(.orange)
  case .stalled:
    Image(systemName: "exclamationmark.triangle.fill")
      .scaledFont(size: size)
      .foregroundColor(.orange)
  case .completed:
    Image(systemName: "checkmark.circle.fill")
      .scaledFont(size: size)
      .foregroundColor(.green)
  case .failed:
    Image(systemName: "xmark.circle.fill")
      .scaledFont(size: size)
      .foregroundColor(.red)
  }
}

// MARK: - Tool Call Stalled Banner

/// Message-level banner that appears above a tool group when any of
/// its tools is `.stalled`. Tapping Cancel triggers the `onCancel`
/// closure passed in by `ToolCallsGroup`, which is wired to
/// `AgentBridge.interrupt()`.
struct ToolCallStalledBanner: View {
  let onCancel: () -> Void

  var body: some View {
    HStack(spacing: 8) {
      Image(systemName: "exclamationmark.triangle.fill")
        .scaledFont(size: 12)
        .foregroundColor(.orange)

      Text("This is taking longer than usual.")
        .scaledFont(size: 12)
        .foregroundColor(OmiColors.textSecondary)

      Spacer(minLength: 4)

      Button(action: onCancel) {
        Text("Cancel")
          .scaledFont(size: 11, weight: .medium)
          .foregroundColor(.white)
          .padding(.horizontal, 10)
          .padding(.vertical, 4)
          .background(Color.red.opacity(0.85))
          .clipShape(RoundedRectangle(cornerRadius: 6))
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, 12)
    .padding(.vertical, 8)
    .background(Color.orange.opacity(0.1))
    .overlay(
      RoundedRectangle(cornerRadius: 12)
        .strokeBorder(Color.orange.opacity(0.4), lineWidth: 1)
    )
    .clipShape(RoundedRectangle(cornerRadius: 12))
  }
}

// MARK: - Thinking Block

struct ThinkingBlock: View {
  let text: String

  @State private var isExpanded = false

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Header
      Button(action: {
        withAnimation(.easeInOut(duration: 0.2)) {
          isExpanded.toggle()
        }
      }) {
        HStack(spacing: 6) {
          Image(systemName: "brain")
            .scaledFont(size: 11)
            .foregroundColor(OmiColors.textTertiary)

          Text("Thinking")
            .scaledFont(size: 12, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
            .italic()

          Spacer(minLength: 4)

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: 9)
            .foregroundColor(OmiColors.textTertiary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
      }
      .buttonStyle(.plain)

      // Expanded thinking content
      if isExpanded {
        Divider()
          .padding(.horizontal, 8)

        Text(text)
          .scaledFont(size: 12)
          .foregroundColor(OmiColors.textTertiary)
          .italic()
          .padding(.horizontal, 10)
          .padding(.vertical, 8)
          .lineLimit(30)
      }
    }
    .omiControlSurface(fill: OmiColors.backgroundTertiary.opacity(0.72), radius: 16)
  }
}

// MARK: - Discovery Card

/// Collapsible card that shows a brief summary with expandable full profile text
struct DiscoveryCard: View {
  let title: String
  let summary: String
  let fullText: String

  @State private var isExpanded = false

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Header — always visible
      Button(action: {
        withAnimation(.easeInOut(duration: 0.2)) {
          isExpanded.toggle()
        }
      }) {
        HStack(spacing: 8) {
          Image(systemName: "doc.text.magnifyingglass")
            .scaledFont(size: 12)
            .foregroundColor(OmiColors.purplePrimary)

          VStack(alignment: .leading, spacing: 2) {
            Text(title)
              .scaledFont(size: 13, weight: .semibold)
              .foregroundColor(OmiColors.textPrimary)

            Text(summary)
              .scaledFont(size: 12)
              .foregroundColor(OmiColors.textSecondary)
              .lineLimit(2)
          }

          Spacer(minLength: 4)

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: 10)
            .foregroundColor(OmiColors.textTertiary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
      }
      .buttonStyle(.plain)

      // Expanded content
      if isExpanded {
        Divider()
          .padding(.horizontal, 10)

        ScrollView {
          SelectableMarkdown(text: fullText, sender: .ai)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
        }
        .frame(maxHeight: 300)
      }
    }
    .omiPanel(
      fill: OmiColors.backgroundSecondary, radius: 18, stroke: OmiColors.border.opacity(0.18),
      shadowOpacity: 0.08, shadowRadius: 10, shadowY: 6)
  }
}

// MARK: - Markdown Themes

extension Theme {
  static func userMessage(scale: CGFloat = 1.0) -> Theme {
    Theme()
      .text {
        ForegroundColor(.white)
        FontSize(round(14 * scale))
      }
      .code {
        FontFamilyVariant(.monospaced)
        FontSize(round(13 * scale))
        ForegroundColor(.white.opacity(0.9))
        BackgroundColor(.white.opacity(0.15))
      }
      .strong {
        FontWeight(.semibold)
      }
      .link {
        ForegroundColor(.white.opacity(0.9))
        UnderlineStyle(.single)
      }
      .table { configuration in
        ScrollView(.horizontal, showsIndicators: false) {
          configuration.label
            .fixedSize(horizontal: true, vertical: true)
            .markdownTableBorderStyle(.init(color: .white.opacity(0.18)))
            .markdownTableBackgroundStyle(.alternatingRows(.white.opacity(0.06), .white.opacity(0.03)))
        }
        .markdownMargin(top: 0, bottom: 10)
      }
      .tableCell { configuration in
        configuration.label
          .markdownTextStyle {
            if configuration.row == 0 {
              FontWeight(.semibold)
            }
          }
          .padding(.vertical, 5)
          .padding(.horizontal, 9)
      }
  }

  static func aiMessage(scale: CGFloat = 1.0) -> Theme {
    Theme()
      .text {
        ForegroundColor(OmiColors.textPrimary)
        FontSize(round(14 * scale))
      }
      .code {
        FontFamilyVariant(.monospaced)
        FontSize(round(13 * scale))
        ForegroundColor(OmiColors.textPrimary)
        BackgroundColor(OmiColors.backgroundTertiary)
      }
      .codeBlock { configuration in
        ScrollView(.horizontal, showsIndicators: false) {
          configuration.label
            .markdownTextStyle {
              FontFamilyVariant(.monospaced)
              FontSize(round(13 * scale))
              ForegroundColor(OmiColors.textPrimary)
            }
        }
        .padding(12)
        .background(OmiColors.backgroundTertiary)
        .cornerRadius(8)
      }
      .strong {
        FontWeight(.semibold)
      }
      .link {
        ForegroundColor(OmiColors.purplePrimary)
      }
      .table { configuration in
        ScrollView(.horizontal, showsIndicators: false) {
          configuration.label
            .fixedSize(horizontal: true, vertical: true)
            .markdownTableBorderStyle(.init(color: Color.white.opacity(0.14)))
            .markdownTableBackgroundStyle(
              .alternatingRows(OmiColors.backgroundTertiary.opacity(0.92), Color.white.opacity(0.035))
            )
        }
        .markdownMargin(top: 0, bottom: 10)
      }
      .tableCell { configuration in
        configuration.label
          .markdownTextStyle {
            if configuration.row == 0 {
              FontWeight(.semibold)
            }
          }
          .padding(.vertical, 5)
          .padding(.horizontal, 9)
      }
  }
}

struct ScaledMarkdownTheme: ViewModifier {
  @Environment(\.fontScale) private var fontScale
  let sender: ChatSender

  func body(content: Content) -> some View {
    content.markdownTheme(
      sender == .user ? .userMessage(scale: fontScale) : .aiMessage(scale: fontScale))
  }
}

extension View {
  func scaledMarkdownTheme(_ sender: ChatSender) -> some View {
    modifier(ScaledMarkdownTheme(sender: sender))
  }
}
