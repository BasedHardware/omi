import AppKit
import OmiTheme
import SwiftUI

enum ChatBubbleMetadataControlMetrics {
  static let leadingInset = OmiSpacing.xxs
  static let topInset = leadingInset
  static let targetSize: CGFloat = 24
}

enum ChatBubbleMetadataHoverRegion {
  case row
  case controls
}

/// Hover ownership for the message and its metadata controls. AppKit can emit
/// the row exit before SwiftUI delivers the controls entry; the release token
/// bridges that event ordering without leaving the controls permanently shown.
struct ChatBubbleMetadataHoverState {
  private(set) var isRowHovering = false
  private(set) var isControlsHovering = false
  private(set) var holdsPointerTransition = false
  private var releaseGeneration = 0

  var keepsMetadataVisible: Bool {
    isRowHovering || isControlsHovering || holdsPointerTransition
  }

  mutating func update(_ region: ChatBubbleMetadataHoverRegion, hovering: Bool) -> Int? {
    switch region {
    case .row: isRowHovering = hovering
    case .controls: isControlsHovering = hovering
    }

    releaseGeneration += 1
    if hovering {
      holdsPointerTransition = true
      return nil
    }
    guard !isRowHovering, !isControlsHovering else { return nil }
    holdsPointerTransition = true
    return releaseGeneration
  }

  mutating func completeRelease(_ generation: Int) {
    guard generation == releaseGeneration, !isRowHovering, !isControlsHovering else { return }
    holdsPointerTransition = false
  }
}

// MARK: - Chat Bubble

struct ChatBubble: View {
  let message: ChatMessage
  let app: OmiApp?
  let showsOmiMark: Bool
  let onRate: (Int?) -> Void
  var onCitationTap: ((Citation) -> Void)? = nil
  var onOpenInlineCitation: ((ChatCitationReference) -> Void)? = nil
  var isDuplicate: Bool = false
  /// Optional cancel action for stalled tool-call banners, threaded
  /// down to `ToolCallsGroup`. Optional so existing callers compile
  /// without wiring cancellation.
  var onCancelTurn: (() -> Void)? = nil
  var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil
  var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil
  /// Nil for all existing Chat surfaces. Rich blocks are transcript data, but
  /// only the capability-gated main shell is allowed to turn them into controls.
  var chatFirstRichBlockContext: ChatFirstRichBlockContext? = nil
  var metadataRevealOverrideForTesting: Bool? = nil
  @State private var metadataHoverState = ChatBubbleMetadataHoverState()
  @State private var isExpanded = false
  @State private var showCopied = false
  @State private var showRatingFeedback = false
  @State private var showInfoPopover = false
  @State private var lastSubmittedRating: Int?
  @FocusState private var isMetadataControlFocused: Bool

  init(
    message: ChatMessage, app: OmiApp?, showsOmiMark: Bool, onRate: @escaping (Int?) -> Void,
    onCitationTap: ((Citation) -> Void)? = nil,
    onOpenInlineCitation: ((ChatCitationReference) -> Void)? = nil,
    isDuplicate: Bool = false,
    onCancelTurn: (() -> Void)? = nil,
    onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil,
    onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil,
    chatFirstRichBlockContext: ChatFirstRichBlockContext? = nil
  ) {
    self.message = message
    self.app = app
    self.showsOmiMark = showsOmiMark
    self.onRate = onRate
    self.onCitationTap = onCitationTap
    self.onOpenInlineCitation = onOpenInlineCitation
    self.isDuplicate = isDuplicate
    self.onCancelTurn = onCancelTurn
    self.onOpenAgent = onOpenAgent
    self.onOpenAgentRef = onOpenAgentRef
    self.chatFirstRichBlockContext = chatFirstRichBlockContext
    _lastSubmittedRating = State(initialValue: message.rating)
  }

  /// Messages longer than this are truncated with a "Show more" button
  private static let truncationThreshold = ChatBubbleTruncation.threshold

  /// Readable width shared by the bubble and its metadata row. Keeping this
  /// explicit lets the metadata row expand to the message column even when
  /// the Markdown body has only a few words.
  private static let messageColumnMaxWidth: CGFloat = 640

  /// Whether this message should be truncated
  private var shouldTruncate: Bool {
    ChatBubbleTruncation.shouldTruncate(
      text: bubbleText,
      isStreaming: message.isStreaming,
      isExpanded: isExpanded
    )
  }

  /// Visible answer body. Pre-tool model commentary is not the turn output.
  private var bubbleText: String {
    if message.sender == .ai, !message.contentBlocks.isEmpty {
      return message.visibleAnswerText
    }
    return message.text
  }

  /// The text to display (truncated or full) — keeps the start of the message visible
  private var displayText: String {
    ChatBubbleTruncation.displayText(
      bubbleText,
      isStreaming: message.isStreaming,
      isExpanded: isExpanded
    )
  }

  private var backgroundAgentSummary: BackgroundAgentSummary? {
    guard message.sender == .ai, message.contentBlocks.isEmpty else { return nil }
    return BackgroundAgentSummary.parse(message.text)
  }

  private var hasAgentOpenAction: Bool {
    onOpenAgentRef != nil || onOpenAgent != nil
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
    Group {
      if message.hidesEmptyStreamingPlaceholder,
        message.isStreaming,
        message.text.isEmpty,
        message.contentBlocks.isEmpty
      {
        EmptyView()
          .accessibilityHidden(true)
      } else {
        let groupedBlocks = ContentBlockGroup.visibleChatGroups(
          message.contentBlocks,
          isStreaming: message.isStreaming,
          richBlockRenderingEnabled: chatFirstRichBlockContext != nil
        )

        HStack(alignment: .top, spacing: OmiSpacing.md) {
          // Default omi replies render avatar-free for a quieter timeline; only
          // app personas keep their identity mark.
          if message.sender == .ai, let app = app {
            AsyncImage(url: URL(string: app.image)) { phase in
              switch phase {
              case .success(let image):
                image
                  .resizable()
                  .aspectRatio(contentMode: .fill)
              default:
                Circle()
                  .fill(Ink.rowFillHover)
              }
            }
            .frame(width: 32, height: 32)
            .clipShape(Circle())
          }

          // Bubbles hug their content up to a readable cap — omi replies sit
          // left, user messages sit right, neither spans the full column.
          VStack(alignment: message.sender == .user ? .trailing : .leading, spacing: OmiSpacing.xxs) {
            messageContentView(groupedBlocks)
          }
          // A max-width frame alone preserves the body's intrinsic width in
          // an unconstrained HStack. Expand first, then cap it, so metadata
          // has a stable trailing edge for short assistant replies too.
          .frame(
            maxWidth: message.sender == .ai ? .infinity : Self.messageColumnMaxWidth,
            alignment: message.sender == .user ? .trailing : .leading
          )
          .frame(
            maxWidth: Self.messageColumnMaxWidth,
            alignment: message.sender == .user ? .trailing : .leading
          )
        }
        // One hover region per row. The whole-row `onHover` below covers this
        // one, so a nested duplicate only ever reported a false "left the row".
        .frame(maxWidth: .infinity, alignment: message.sender == .user ? .trailing : .leading)
      }
    }
    .frame(
      maxWidth: .infinity,
      minHeight: ChatOmiMarkPlacement.rowHeight(
        showsMark: message.sender == .ai && app == nil && showsOmiMark),
      alignment: message.sender == .user ? .trailing : .leading
    )
    .overlay(alignment: .topLeading) {
      if message.sender == .ai, app == nil, showsOmiMark {
        ChatOmiMark(
          motion: ChatWorkingStatus.motion(for: message),
          size: ChatOmiMarkPlacement.markSize
        )
        // `.leading`, not the default centre: the layout box is wider than the
        // resting ring (the extra is travel for the streaming animation), so
        // centring bled the ring past the gutter, outside every other margin.
        .frame(
          width: ChatOmiMarkPlacement.markGutter,
          height: ChatOmiMarkPlacement.markSize,
          alignment: .leading
        )
        .offset(x: -ChatOmiMarkPlacement.markGutter)
      }
    }
    .contentShape(Rectangle())
    .onHover { updateMetadataHover(.row, hovering: $0) }
  }

  @ViewBuilder
  private func messageContentView(_ groupedBlocks: [ContentBlockGroup]) -> some View {
    if message.isStreaming && message.text.isEmpty && message.contentBlocks.isEmpty {
      // Omi's own reply shows the spinning Omi-mark avatar while thinking, so no
      // extra typing dots are needed; only app personas (no spinning mark) do.
      if app != nil {
        TypingIndicator()
      }
    } else if message.sender == .ai && !message.contentBlocks.isEmpty {
      ForEach(groupedBlocks) { group in
        if case .text = group {
          EmptyView()
        } else {
          groupView(group)
        }
      }
      if !message.visibleAnswerText.isEmpty {
        messageTextBubble(displayText)
        truncationControl
      }
      if message.isStreaming, app != nil {
        let hasInFlightTool = groupedBlocks.contains { group in
          guard case .toolCalls(_, let calls) = group else { return false }
          return calls.contains { block in
            if case .toolCall(_, _, let status, _, _, _) = block { return status.isInFlight }
            return false
          }
        }
        if !hasInFlightTool {
          TypingIndicator()
        }
      }
      if !message.displayResources.isEmpty {
        ChatResourceStrip(resources: message.displayResources, density: .full, alignment: .leading)
      }
    } else if isDuplicate && !isExpanded {
      Button(action: { isExpanded = true }) {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "doc.on.doc")
            .scaledFont(size: OmiType.caption)
          Text("Duplicate message")
            .scaledFont(size: OmiType.caption)
          Image(systemName: "chevron.down")
            .scaledFont(size: OmiType.micro)
        }
        .foregroundColor(Ink.secondary)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
        .background(Ink.rowFill)
        .clipShape(Capsule(style: .continuous))
      }
      .buttonStyle(.plain)
    } else {
      VStack(alignment: message.sender == .user ? .trailing : .leading, spacing: OmiSpacing.xs) {
        let resourceStrip =
          message.displayResources.isEmpty
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
          messageTextBubble(displayText)
        }

        truncationControl

        if message.sender != .user, let resourceStrip {
          resourceStrip
        }
      }
    }

    if message.sender == .ai && !message.citations.isEmpty && !message.isStreaming {
      CitationCardsView(citations: message.citations) { citation in
        onCitationTap?(citation)
      }
      .frame(maxWidth: 280)
    }

    // A failed turn now carries its own reason as the row's text (see
    // `ChatTurnFailureNotice`). The blanket "Couldn't save this reply" caption
    // both duplicated that reason in different words and named the wrong
    // cause — the turn failed, no save was attempted. Keep a stamp only for a
    // failed row that has nothing of its own to say.
    if message.sender == .ai && !message.isStreaming && message.journalStatus == .failed
      && message.text.isEmpty && message.contentBlocks.isEmpty
    {
      Text("This turn didn't finish")
        .scaledFont(size: OmiType.micro, weight: .medium)
        .foregroundColor(PageGlass.warning)
    }

    switch ChatBubbleMetadataBand.of(message) {
    case .hidden:
      EmptyView()
    case .timestampOnly:
      messageMetadataRow(includeRatingButtons: false, includeCopyButton: false)
    case .actions:
      messageMetadataRow(includeRatingButtons: true, includeCopyButton: true)
    }
    // **A user turn gets no metadata band.** Its timestamp-only row cost every
    // question a reserved band for a fact the reply underneath already stamps.
  }

  private var presentation: ChatRowPresentation { ChatRowPresentation.of(message) }

  @ViewBuilder
  private func messageTextBubble(_ text: String) -> some View {
    if presentation == .proactivePush, let card = SuggestedTaskChatCard.parse(text) {
      // A proposed task is actionable history, not a receipt: render the card
      // that lets the reader put it in their list (I1).
      ChatSuggestedTaskRow(card: card)
    } else if presentation == .proactivePush {
      ChatProactivePushRow(
        text: text,
        kind: ChatContinuityInvariants.proactiveNotificationKind(message) ?? .general)
    } else {
      OmiMarkdown(
        text: text,
        sender: message.sender,
        citations: citationReferencesForThisSurface,
        onOpenCitation: onOpenInlineCitation
      )
      .chatMessageBlock(filled: presentation.isFilled)
    }
  }

  private var showMoreButton: some View {
    Button(action: { isExpanded = true }) {
      Text("Show more")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.accent)
    }
    .buttonStyle(.plain)
    .accessibilityHint("Expand the full message")
  }

  @ViewBuilder
  private var truncationControl: some View {
    if backgroundAgentSummary == nil, bubbleText.count > Self.truncationThreshold {
      if isExpanded {
        Button(action: { isExpanded.toggle() }) {
          Text("Show less")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.accent)
        }
        .buttonStyle(.plain)
      } else if shouldTruncate {
        showMoreButton
      }
    }
  }

  private var agentOpenClosure: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? {
    guard hasAgentOpenAction else { return nil }
    return openAgent(ref:completion:)
  }

  private func groupView(_ group: ContentBlockGroup) -> AnyView {
    switch group {
    case .text(_, let text):
      if text.isEmpty {
        return AnyView(EmptyView())
      }
      // The glass is the ground for an assistant block — so no fill, and
      // therefore none of a container's padding either.
      return AnyView(
        OmiMarkdown(
          text: text,
          sender: .ai,
          citations: citationReferencesForThisSurface,
          onOpenCitation: onOpenInlineCitation
        )
        .chatMessageBlock(filled: false))
    case .commentary(_, let text):
      return AnyView(TurnCommentaryRow(text: text))
    case .toolCalls(_, let calls):
      return AnyView(
        ToolCallsGroup(
          calls: calls,
          compact: true,
          onCancel: onCancelTurn,
          onOpenAgent: onOpenAgent,
          onOpenAgentRef: onOpenAgentRef
        )
      )
    case .thinking:
      // Omi replies like a person texting — no exposed "Thinking" reasoning
      // disclosure. The streaming typing indicator (spinning mark) carries the
      // wait on its own.
      return AnyView(EmptyView())
    case .discoveryCard(_, let title, let summary, let fullText):
      return AnyView(DiscoveryCard(title: title, summary: summary, fullText: fullText))
    case .questionCard(_, let questionID, let text, let options, let selectedOptionID):
      guard let chatFirstRichBlockContext else { return AnyView(EmptyView()) }
      return AnyView(
        QuestionCardView(
          questionID: questionID,
          text: text,
          options: options,
          selectedOptionID: selectedOptionID,
          isActionable: chatFirstRichBlockContext.chatProvider.isQuestionCardActionable(
            messageID: message.id,
            questionID: questionID,
            selectedOptionID: selectedOptionID
          ),
          onSelect: { optionID, isDeferral in
            Task { @MainActor in
              AnalyticsManager.shared.chatFirst(
                .question(lifecycle: isDeferral ? .deferred : .answered)
              )
              AnalyticsManager.shared.chatFirst(
                .richBlock(kind: .questionCard, outcome: .acted, action: .select)
              )
              await chatFirstRichBlockContext.chatProvider.selectQuestionCardOption(
                questionID: questionID,
                optionID: optionID
              )
            }
          }
        )
      )
    case .taskCard(_, let taskID):
      guard let chatFirstRichBlockContext else { return AnyView(EmptyView()) }
      return AnyView(
        TaskCardView(
          taskID: taskID,
          tasksStore: chatFirstRichBlockContext.tasksStore,
          navigation: chatFirstRichBlockContext.navigation
        )
      )
    case .goalLink(_, let goalID, let summary):
      guard let chatFirstRichBlockContext else { return AnyView(EmptyView()) }
      return AnyView(
        GoalLinkView(
          goalID: goalID,
          summary: summary,
          navigation: chatFirstRichBlockContext.navigation,
          goalsStore: chatFirstRichBlockContext.canonicalGoalsStore
        )
      )
    case .captureLink(_, let conversationID, let momentTimestampMs, let summary):
      guard let chatFirstRichBlockContext else { return AnyView(EmptyView()) }
      return AnyView(
        CaptureLinkView(
          conversationID: conversationID,
          momentTimestampMs: momentTimestampMs,
          summary: summary,
          navigation: chatFirstRichBlockContext.navigation
        )
      )
    case .conversationLink(_, let conversationID, let summary, let recommendedActionItems):
      guard let chatFirstRichBlockContext else { return AnyView(EmptyView()) }
      return AnyView(
        ConversationLinkView(
          conversationID: conversationID,
          summary: summary,
          recommendedActionItems: recommendedActionItems,
          navigation: chatFirstRichBlockContext.navigation
        )
      )
    case .memoryLink(_, let memoryID, let summary):
      guard let chatFirstRichBlockContext else { return AnyView(EmptyView()) }
      return AnyView(
        MemoryLinkView(
          memoryID: memoryID,
          summary: summary,
          navigation: chatFirstRichBlockContext.navigation
        )
      )
    case .agentSpawn(
      _, let pillId, let sessionId, let runId, let title, let objective, let provider
    ):
      return AnyView(
        AgentSpawnCard(
          title: title,
          objective: objective,
          provider: provider,
          ref: AgentTimelineRef(pillId: pillId, sessionId: sessionId, runId: runId),
          onOpen: agentOpenClosure
        )
      )
    case .agentCompletion(
      _, let pillId, let sessionId, let runId, let title, let promptSnippet, let output, let status
    ):
      return AnyView(
        AgentCompletionCard(
          title: title,
          promptSnippet: promptSnippet,
          output: output,
          status: status,
          ref: AgentTimelineRef(pillId: pillId, sessionId: sessionId, runId: runId),
          onOpen: agentOpenClosure
        )
      )
    }
  }

  private var citationReferencesForThisSurface: [ChatCitationReference] {
    guard message.sender == .ai, !message.isStreaming, onOpenInlineCitation != nil else { return [] }
    return message.inlineCitationReferences
  }

  @ViewBuilder
  private func messageMetadataRow(includeRatingButtons: Bool, includeCopyButton: Bool) -> some View {
    let isVisible =
      metadataRevealOverrideForTesting
      ?? (metadataHoverState.keepsMetadataVisible || isMetadataControlFocused || showRatingFeedback
        || showCopied || showInfoPopover)
    // **One cluster under the message.** Controls far left and timestamp far right
    // of one line is how two halves of a row end up reading as page furniture.
    HStack(alignment: .center, spacing: OmiSpacing.sm) {
      if includeRatingButtons {
        ratingButtons
      }
      if includeCopyButton {
        copyButton
      }
      if includeCopyButton, message.metadata != nil {
        infoButton
      }
      ChatMessageTimestamp(date: message.createdAt)
      Spacer(minLength: 0)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    // Keep the strip inside the row's real layout bounds. Drawing it below a
    // zero-height frame left visible pixels with no AppKit hit-test region.
    .padding(.top, ChatBubbleMetadataControlMetrics.topInset)
    .padding(.leading, ChatBubbleMetadataControlMetrics.leadingInset)
    .contentShape(Rectangle())
    .onHover { updateMetadataHover(.controls, hovering: $0) }
    .opacity(isVisible ? 1 : 0)
    .allowsHitTesting(isVisible)
    .omiAnimation(.easeInOut(duration: 0.15), value: isVisible)
  }

  private func updateMetadataHover(_ region: ChatBubbleMetadataHoverRegion, hovering: Bool) {
    guard let release = metadataHoverState.update(region, hovering: hovering) else { return }
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
      metadataHoverState.completeRelease(release)
    }
  }

  @ViewBuilder
  private var ratingButtons: some View {
    HStack(spacing: OmiSpacing.xxs) {
      // Thumbs up
      Button(action: {
        let newRating = message.rating == 1 ? nil : 1
        guard newRating != lastSubmittedRating else { return }
        lastSubmittedRating = newRating
        onRate(newRating)
        if newRating != nil { showRatingFeedbackBriefly() }
      }) {
        Image(systemName: message.rating == 1 ? "hand.thumbsup.fill" : "hand.thumbsup")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(message.rating == 1 ? Ink.primary : Ink.secondary)
          .frame(
            width: ChatBubbleMetadataControlMetrics.targetSize,
            height: ChatBubbleMetadataControlMetrics.targetSize
          )
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .focused($isMetadataControlFocused)
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
          .scaledFont(size: OmiType.caption)
          .foregroundColor(message.rating == -1 ? Ink.errorRed : Ink.secondary)
          .frame(
            width: ChatBubbleMetadataControlMetrics.targetSize,
            height: ChatBubbleMetadataControlMetrics.targetSize
          )
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .focused($isMetadataControlFocused)
      .help("Not helpful")

      if showRatingFeedback {
        Text("Thank you")
          .scaledFont(size: OmiType.micro)
          .foregroundColor(Ink.secondary)
          .transition(.opacity)
      }
    }
    .omiAnimation(.easeInOut(duration: 0.2), value: showRatingFeedback)
    // Keep the dedupe shadow in sync with the live rating. Without this, an
    // external rating change (background sync/poll updates message.rating on a
    // stable .id(message.id) view) leaves lastSubmittedRating stale, so a later
    // un-rate tap computes newRating == nil == lastSubmittedRating and the guard
    // swallows it — the rating can never be cleared.
    .onChange(of: message.rating, initial: true) { _, newValue in
      lastSubmittedRating = newValue
    }
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
        .scaledFont(size: OmiType.caption)
        .foregroundColor(showCopied ? Ink.listeningGreen : Ink.secondary)
        .frame(
          width: ChatBubbleMetadataControlMetrics.targetSize,
          height: ChatBubbleMetadataControlMetrics.targetSize
        )
        .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .focused($isMetadataControlFocused)
    .help("Copy message")
  }

  /// Response Context popover — observed turn evidence (tools, screenshot,
  /// admitted kernel sources). Only fresh responses carry metadata; it is
  /// in-memory only and not persisted across restarts.
  @ViewBuilder
  private var infoButton: some View {
    Button(action: { showInfoPopover.toggle() }) {
      Image(systemName: "info.circle")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(showInfoPopover ? Ink.primary : Ink.secondary)
        .frame(
          width: ChatBubbleMetadataControlMetrics.targetSize,
          height: ChatBubbleMetadataControlMetrics.targetSize
        )
        .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .focused($isMetadataControlFocused)
    .help("View response context")
    .popover(isPresented: $showInfoPopover, arrowEdge: .bottom) {
      if let metadata = message.metadata {
        MessageMetadataPopover(metadata: metadata)
      }
    }
  }
}

/// Shared geometry for expandable timeline cards. Optional link-out actions
/// always retain their slot so status, text, and disclosure anchors never move
/// as agent availability changes.
private struct StableChatCardHeader<Identity: View, Content: View>: View {
  let isExpanded: Bool
  let showsDisclosure: Bool
  let horizontalPadding: CGFloat
  let verticalPadding: CGFloat
  let minimumHeight: CGFloat?
  let onToggle: (() -> Void)?
  let onOpen: (() -> Void)?
  let identity: Identity
  let content: Content

  init(
    isExpanded: Bool = false,
    showsDisclosure: Bool,
    horizontalPadding: CGFloat = OmiSpacing.md,
    verticalPadding: CGFloat = OmiSpacing.sm,
    minimumHeight: CGFloat? = nil,
    onToggle: (() -> Void)? = nil,
    onOpen: (() -> Void)? = nil,
    @ViewBuilder identity: @escaping () -> Identity,
    @ViewBuilder content: @escaping () -> Content
  ) {
    self.isExpanded = isExpanded
    self.showsDisclosure = showsDisclosure
    self.horizontalPadding = horizontalPadding
    self.verticalPadding = verticalPadding
    self.minimumHeight = minimumHeight
    self.onToggle = onToggle
    self.onOpen = onOpen
    self.identity = identity()
    self.content = content()
  }

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.xxs) {
      Button(action: { onToggle?() }) {
        HStack(alignment: .top, spacing: OmiSpacing.sm) {
          identity
            .frame(width: 18, height: 18, alignment: .center)
          content
            .frame(maxWidth: .infinity, alignment: .leading)
          Group {
            if showsDisclosure {
              Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                .scaledFont(size: OmiType.micro)
                .foregroundColor(Ink.secondary)
            } else {
              Color.clear
            }
          }
          .frame(width: 18, height: 18, alignment: .center)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .allowsHitTesting(onToggle != nil)

      Group {
        if let onOpen {
          Button(action: onOpen) {
            Image(systemName: "arrow.up.forward.app")
              .scaledFont(size: OmiType.micro)
              .foregroundColor(Ink.secondary)
              .frame(maxWidth: .infinity, maxHeight: .infinity)
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .help("Open agent")
        } else {
          Color.clear
        }
      }
      .frame(width: 28, height: 28)
    }
    .padding(.horizontal, horizontalPadding)
    .padding(.vertical, verticalPadding)
    .frame(minHeight: minimumHeight)
    .textSelection(.disabled)
  }
}

private struct BackgroundAgentSummaryCard: View {
  let summary: BackgroundAgentSummary
  var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil

  @State private var isExpanded = false
  @State private var showUnavailable = false

  private var shouldShowLinkOut: Bool {
    AgentTimelineOpenFeedback.shouldShowLinkOut(
      hasResolvableAgent: summary.agentID != nil,
      hasOpenAction: onOpenAgent != nil,
      showUnavailable: showUnavailable
    )
  }

  private var openAction: (() -> Void)? {
    shouldShowLinkOut ? { openAgent() } : nil
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      StableChatCardHeader(
        isExpanded: isExpanded,
        showsDisclosure: true,
        onToggle: toggleExpanded,
        onOpen: openAction
      ) {
        Image(systemName: "checkmark.circle.fill")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.listeningGreen)
      } content: {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text("Background agent")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundColor(Ink.primary)
            .lineLimit(2)
            .fixedSize(horizontal: false, vertical: true)
          if !isExpanded,
            !ChatContinuityInvariants.agentCardPreviewText(
              title: "Background agent",
              prompt: summary.prompt,
              output: summary.output
            ).isEmpty
          {
            Text(
              ChatContinuityInvariants.agentCardPreviewText(
                title: "Background agent",
                prompt: summary.prompt,
                output: summary.output
              )
            )
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .lineLimit(2)
            .truncationMode(.tail)
          }
        }
      }

      if isExpanded || showUnavailable {
        Divider()
          .padding(.horizontal, OmiSpacing.sm)
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          Text(summary.prompt)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .lineLimit(3)
            .textSelection(.disabled)
          OmiMarkdown(text: summary.output, sender: .ai)
          if showUnavailable {
            Text("Agent unavailable — it may have been dismissed.")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
              .textSelection(.disabled)
          }
        }
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .glassCard(cornerRadius: 16)
    .onChange(of: showUnavailable) { _, unavailable in
      guard unavailable else { return }
      OmiMotion.withGated(.easeInOut(duration: 0.18)) {
        isExpanded = true
      }
    }
  }

  private func toggleExpanded() {
    OmiMotion.withGated(.easeInOut(duration: 0.18)) {
      isExpanded.toggle()
    }
  }

  private func openAgent() {
    guard let agentID = summary.agentID, let onOpenAgent else { return }
    onOpenAgent(agentID) { succeeded in
      if AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: succeeded) {
        showUnavailable = true
      }
    }
  }
}

struct AgentSpawnCard: View {
  let title: String
  let objective: String
  let provider: AgentHarnessMode?
  let ref: AgentTimelineRef
  var onOpen: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil

  @State private var showUnavailable = false

  private var shouldShowLinkOut: Bool {
    AgentTimelineOpenFeedback.shouldShowLinkOut(
      hasResolvableAgent: ref.hasIdentity,
      hasOpenAction: onOpen != nil,
      showUnavailable: showUnavailable
    )
  }

  private var openAction: (() -> Void)? {
    shouldShowLinkOut ? { openAgent() } : nil
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      StableChatCardHeader(
        showsDisclosure: false,
        onOpen: openAction
      ) {
        Group {
          if provider.rendersProviderMark {
            AgentProviderLogoMark(
              provider: provider,
              statusColor: Ink.secondary,
              size: 14
            )
          } else {
            Image(systemName: "arrow.triangle.branch")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }
        }
      } content: {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(title.isEmpty ? "Background agent" : title)
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundColor(Ink.primary)
            .lineLimit(2)
            .fixedSize(horizontal: false, vertical: true)
          if !ChatContinuityInvariants.agentCardPreviewText(
            title: title,
            prompt: objective,
            output: ""
          ).isEmpty {
            Text(
              ChatContinuityInvariants.agentCardPreviewText(
                title: title,
                prompt: objective,
                output: ""
              )
            )
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .lineLimit(2)
            .truncationMode(.tail)
          }
        }
      }

      if showUnavailable {
        Divider()
          .padding(.horizontal, OmiSpacing.sm)
        Text("Agent unavailable — it may have been dismissed.")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, OmiSpacing.sm)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .glassCard(cornerRadius: 16)
  }

  private func openAgent() {
    guard shouldShowLinkOut, let onOpen else { return }
    onOpen(ref) { succeeded in
      if AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: succeeded) {
        showUnavailable = true
      }
    }
  }
}

struct AgentCompletionCard: View {
  let title: String
  let promptSnippet: String
  let output: String
  let status: String
  let ref: AgentTimelineRef
  var onOpen: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil

  @State private var isExpanded = false
  @State private var showUnavailable = false

  private var shouldShowLinkOut: Bool {
    AgentTimelineOpenFeedback.shouldShowLinkOut(
      hasResolvableAgent: ref.hasIdentity,
      hasOpenAction: onOpen != nil,
      showUnavailable: showUnavailable
    )
  }

  private var openAction: (() -> Void)? {
    shouldShowLinkOut ? { openAgent() } : nil
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      StableChatCardHeader(
        isExpanded: isExpanded,
        showsDisclosure: true,
        onToggle: toggleExpanded,
        onOpen: openAction
      ) {
        Image(systemName: statusIconName)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(statusColor)
      } content: {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(title.isEmpty ? "Background agent" : title)
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundColor(Ink.primary)
            .lineLimit(2)
            .fixedSize(horizontal: false, vertical: true)
          if !isExpanded,
            !ChatContinuityInvariants.agentCardPreviewText(
              title: title,
              prompt: promptSnippet,
              output: output
            ).isEmpty
          {
            Text(
              ChatContinuityInvariants.agentCardPreviewText(
                title: title,
                prompt: promptSnippet,
                output: output
              )
            )
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .lineLimit(2)
            .truncationMode(.tail)
          }
        }
      }

      if isExpanded || showUnavailable {
        Divider()
          .padding(.horizontal, OmiSpacing.sm)
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          if !promptSnippet.isEmpty {
            Text(promptSnippet)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
              .lineLimit(3)
              .textSelection(.disabled)
          }
          OmiMarkdown(text: output, sender: .ai)
          if showUnavailable {
            Text("Agent unavailable — it may have been dismissed.")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
              .textSelection(.disabled)
          }
        }
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .glassCard(cornerRadius: 16)
    .onChange(of: showUnavailable) { _, unavailable in
      guard unavailable else { return }
      OmiMotion.withGated(.easeInOut(duration: 0.18)) {
        isExpanded = true
      }
    }
  }

  private func toggleExpanded() {
    OmiMotion.withGated(.easeInOut(duration: 0.18)) {
      isExpanded.toggle()
    }
  }

  private func openAgent() {
    guard shouldShowLinkOut, let onOpen else { return }
    onOpen(ref) { succeeded in
      if AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: succeeded) {
        showUnavailable = true
      }
    }
  }

  private var statusIconName: String {
    switch status.lowercased() {
    case "failed", "cancelled", "canceled", "stopped", "timed_out", "timeout", "orphaned", "error":
      return "xmark.circle.fill"
    case "completed", "succeeded", "success", "done":
      return "checkmark.circle.fill"
    default:
      return "questionmark.circle.fill"
    }
  }

  private var statusColor: Color {
    switch status.lowercased() {
    case "failed", "cancelled", "canceled", "stopped", "timed_out", "timeout", "orphaned", "error":
      return Ink.errorRed
    case "completed", "succeeded", "success", "done":
      return Ink.listeningGreen
    default:
      return Ink.secondary
    }
  }
}

extension ChatBubble: @preconcurrency Equatable {
  static func == (lhs: ChatBubble, rhs: ChatBubble) -> Bool {
    ChatBubbleIdentity.equal(
      lhs.message,
      rhs.message,
      appIDs: (lhs.app?.id, rhs.app?.id),
      showsOmiMark: (lhs.showsOmiMark, rhs.showsOmiMark),
      isDuplicate: (lhs.isDuplicate, rhs.isDuplicate)
    )
  }
}

// MARK: - Content Block Grouping

/// Groups consecutive tool call blocks into a single collapsible group
enum ContentBlockGroup: Identifiable {
  case text(id: String, text: String)
  case commentary(id: String, text: String)
  case toolCalls(id: String, calls: [ChatContentBlock])
  case thinking(id: String, text: String)
  case discoveryCard(id: String, title: String, summary: String, fullText: String)
  case questionCard(id: String, questionID: String, text: String, options: [[String: Any]], selectedOptionID: String?)
  case taskCard(id: String, taskID: String)
  case goalLink(id: String, goalID: String, summary: String)
  case captureLink(id: String, conversationID: String, momentTimestampMs: Int?, summary: String)
  case conversationLink(
    id: String,
    conversationID: String,
    summary: String,
    recommendedActionItems: [ConversationLinkActionItem]
  )
  case memoryLink(id: String, memoryID: String, summary: String)
  case agentSpawn(
    id: String,
    pillId: UUID?,
    sessionId: String,
    runId: String,
    title: String,
    objective: String,
    provider: AgentHarnessMode?
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
    case .commentary(let id, _): return id
    case .toolCalls(let id, _): return id
    case .thinking(let id, _): return id
    case .discoveryCard(let id, _, _, _): return id
    case .questionCard(let id, _, _, _, _): return id
    case .taskCard(let id, _): return id
    case .goalLink(let id, _, _): return id
    case .captureLink(let id, _, _, _): return id
    case .conversationLink(let id, _, _, _): return id
    case .memoryLink(let id, _, _): return id
    case .agentSpawn(let id, _, _, _, _, _, _): return id
    case .agentCompletion(let id, _, _, _, _, _, _, _): return id
    }
  }

  /// Groups consecutive `.toolCall` blocks together; passes other blocks through
  static func group(
    _ blocks: [ChatContentBlock],
    richBlockRenderingEnabled: Bool = false
  ) -> [ContentBlockGroup] {
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
      case .questionCard(let id, let questionID, let text, _, _, let options, let selectedOptionID):
        flushToolCalls()
        guard richBlockRenderingEnabled else { continue }
        groups.append(
          .questionCard(
            id: id, questionID: questionID, text: text, options: options, selectedOptionID: selectedOptionID))
      case .taskCard(let id, let taskID):
        flushToolCalls()
        guard richBlockRenderingEnabled else { continue }
        groups.append(.taskCard(id: id, taskID: taskID))
      case .goalLink(let id, let goalID, let summary):
        flushToolCalls()
        guard richBlockRenderingEnabled else { continue }
        groups.append(.goalLink(id: id, goalID: goalID, summary: summary))
      case .captureLink(let id, let conversationID, let momentTimestampMs, let summary):
        flushToolCalls()
        guard richBlockRenderingEnabled else { continue }
        groups.append(
          .captureLink(
            id: id,
            conversationID: conversationID,
            momentTimestampMs: momentTimestampMs,
            summary: summary
          )
        )
      case .conversationLink(let id, let conversationID, let summary, let recommendedActionItems):
        flushToolCalls()
        guard richBlockRenderingEnabled else { continue }
        groups.append(
          .conversationLink(
            id: id,
            conversationID: conversationID,
            summary: summary,
            recommendedActionItems: recommendedActionItems))
      case .memoryLink(let id, let memoryID, let summary):
        flushToolCalls()
        guard richBlockRenderingEnabled else { continue }
        groups.append(.memoryLink(id: id, memoryID: memoryID, summary: summary))
      case .citation:
        // Answer-level provenance is rendered by OmiMarkdown at the inline marker.
        continue
      case .agentSpawn(
        let id, let pillId, let sessionId, let runId, let title, let objective, let provider
      ):
        flushToolCalls()
        groups.append(
          .agentSpawn(
            id: id,
            pillId: pillId,
            sessionId: sessionId,
            runId: runId,
            title: title,
            objective: objective,
            provider: provider
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

  /// Main chat keeps a durable tool trace, so streamed answers do not appear to lose completed work.
  /// A structured `.agentSpawn` replaces only its duplicate raw spawn call (INV-6 structured identity).
  static func visibleChatGroups(
    _ blocks: [ChatContentBlock],
    isStreaming: Bool,
    richBlockRenderingEnabled: Bool = false
  ) -> [ContentBlockGroup] {
    // The display projection turns a persisted spawn into its terminal card.
    // Both structured forms are therefore authoritative evidence that the
    // matching raw `spawn_agent` tool row is lifecycle plumbing, not a second
    // user-visible subagent.
    let structuredSpawnKeys = Set(
      blocks.compactMap { block -> String? in
        let pillId: UUID?
        let runId: String?
        switch block {
        case .agentSpawn(_, let blockPillId, _, let blockRunId, _, _, _):
          pillId = blockPillId
          runId = blockRunId
        case .agentCompletion(_, let blockPillId, _, let blockRunId, _, _, _, _):
          pillId = blockPillId
          runId = blockRunId
        default:
          return nil
        }
        if let pillId { return "pill:\(pillId.uuidString)" }
        let trimmedRun = runId?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmedRun.isEmpty ? nil : "run:\(trimmedRun)"
      }
    )
    let grouped = group(blocks, richBlockRenderingEnabled: richBlockRenderingEnabled)
    let lastToolIndex = grouped.lastIndex { group in
      if case .toolCalls = group { return true }
      return false
    }
    let hasTextAfterLastTool =
      lastToolIndex.map { toolIndex in
        grouped[(toolIndex + 1)...].contains { group in
          if case .text(_, let text) = group {
            return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          }
          return false
        }
      } ?? false

    return grouped.enumerated().compactMap { index, group in
      switch group {
      case .text(_, let text):
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return nil }
        if let lastToolIndex, index < lastToolIndex {
          if isStreaming {
            return .commentary(id: group.id, text: trimmed)
          }
          if hasTextAfterLastTool {
            return nil
          }
        }
        return group
      case .commentary:
        return isStreaming ? group : nil
      case .discoveryCard, .questionCard, .taskCard, .goalLink, .captureLink, .conversationLink, .memoryLink,
        .agentSpawn, .agentCompletion:
        return group
      case .thinking:
        return isStreaming ? group : nil
      case .toolCalls(let id, let calls):
        let spawnedAgentCalls = calls.filter { call in
          guard let pillId = call.spawnedAgentID else { return false }
          if structuredSpawnKeys.contains("pill:\(pillId.uuidString)") { return false }
          if let runId = call.spawnedAgentRunID,
            structuredSpawnKeys.contains("run:\(runId)")
          {
            return false
          }
          return true
        }
        // Keep the complete tool trace together. A raw spawn can briefly
        // precede its structured receipt; once that receipt arrives, hide only
        // the duplicate raw spawn and retain every other completed, failed, or
        // in-flight tool row as visible progress evidence.
        let unresolvedSpawnIDs = Set(spawnedAgentCalls.map(\.id))
        let visibleCalls = calls.filter { block in
          if unresolvedSpawnIDs.contains(block.id) { return true }
          if let ref = block.agentOpenRef {
            let hasStructuredSpawn =
              ref.pillId.map { structuredSpawnKeys.contains("pill:\($0.uuidString)") }
              ?? ref.runId.map { structuredSpawnKeys.contains("run:\($0)") }
              ?? false
            if hasStructuredSpawn { return false }
          }
          if case .toolCall = block { return true }
          return false
        }
        // Tool-call chips are live progress, not history: show them only while
        // the reply is streaming (tools actively being called) and drop them
        // once omi has finished replying, so the timeline reads like a clean
        // text conversation.
        if !isStreaming { return nil }
        return visibleCalls.isEmpty ? nil : .toolCalls(id: id, calls: visibleCalls)
      }
    }
  }
}

// MARK: - Tool Calls Group

struct ToolActivityTimelineItem: Identifiable {
  let id: String
  let block: ChatContentBlock
  let connectsToNext: Bool
}

enum ToolActivityTimelinePresentation {
  static func items(from blocks: [ChatContentBlock]) -> [ToolActivityTimelineItem] {
    let toolCalls = blocks.compactMap { block -> ChatContentBlock? in
      guard case .toolCall = block else { return nil }
      return block
    }
    var occurrenceByIdentity: [String: Int] = [:]
    return toolCalls.enumerated().map { position, block in
      let baseIdentity: String
      if case .toolCall(let id, let name, _, _, _, _) = block {
        baseIdentity = [id, name].joined(separator: ":")
      } else {
        baseIdentity = block.id
      }
      let occurrence = occurrenceByIdentity[baseIdentity, default: 0]
      occurrenceByIdentity[baseIdentity] = occurrence + 1
      return ToolActivityTimelineItem(
        id: "\(baseIdentity):\(occurrence)",
        block: block,
        connectsToNext: position < toolCalls.count - 1
      )
    }
  }

  static func animationToken(for items: [ToolActivityTimelineItem]) -> String {
    items.map { item in
      guard case .toolCall(_, _, let status, _, _, _) = item.block else { return item.id }
      return "\(item.id):\(status)"
    }.joined(separator: "|")
  }

  static func displayStatus(toolName: String, status: ToolCallStatus) -> ToolCallStatus {
    if status == .stalled, ChatContentBlock.isSlowExpectedTool(toolName) {
      return .slow
    }
    return status
  }

  static func accessibilityValue(for status: ToolCallStatus) -> String {
    switch status {
    case .running: return "Running"
    case .slow: return "Still working"
    case .stalled: return "Taking longer than usual"
    case .completed: return "Completed"
    case .failed: return "Failed"
    }
  }

  static func hasExpandableContent(input: ToolCallInput?, output: String?) -> Bool {
    let details = input?.details?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    let result = output?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return !details.isEmpty || !result.isEmpty
  }
}

/// Renders consecutive tool calls as one live activity rail. Each appended call
/// extends the rail instead of replacing the previous step with a summary.
struct ToolCallsGroup: View {
  let calls: [ChatContentBlock]
  var compact: Bool = false
  /// `ChatProvider` wires this to `agentBridge.interrupt()` via the
  /// parent message view. If no action is available, the banner is hidden
  /// so the UI never presents a no-op Cancel button.
  var onCancel: (() -> Void)? = nil
  var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil
  var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil

  init(
    calls: [ChatContentBlock],
    compact: Bool = false,
    onCancel: (() -> Void)? = nil,
    onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil,
    onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil
  ) {
    self.calls = calls
    self.compact = compact
    self.onCancel = onCancel
    self.onOpenAgent = onOpenAgent
    self.onOpenAgentRef = onOpenAgentRef
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

  private var timelineItems: [ToolActivityTimelineItem] {
    ToolActivityTimelinePresentation.items(from: calls)
  }

  var body: some View {
    VStack(alignment: .leading, spacing: compact ? OmiSpacing.xxs : OmiSpacing.xs) {
      if hasStalledTool, let onCancel {
        ToolCallStalledBanner(onCancel: onCancel)
      }

      VStack(alignment: .leading, spacing: 0) {
        ForEach(timelineItems) { item in
          if case .toolCall(_, let name, let status, _, let input, let output) = item.block {
            ToolCallCard(
              name: name,
              status: status,
              input: input,
              output: output,
              connectsToNext: item.connectsToNext,
              agentOpenRef: item.block.agentOpenRef,
              onOpenAgent: onOpenAgent,
              onOpenAgentRef: onOpenAgentRef
            )
            .transition(
              .asymmetric(
                insertion: .move(edge: .top).combined(with: .opacity),
                removal: .opacity
              )
            )
          }
        }
      }
      .omiAnimation(
        .spring(response: 0.36, dampingFraction: 0.86),
        value: ToolActivityTimelinePresentation.animationToken(for: timelineItems)
      )

    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .fixedSize(horizontal: false, vertical: true)
  }
}

/// Live-only model narration that preceded tools. Same rail as tool chips; dropped
/// when the turn settles so only the final answer remains.
struct TurnCommentaryRow: View {
  let text: String

  var body: some View {
    ToolCallActivityHeadline(name: "commentary", status: .completed) {
      Text(text)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
    .frame(maxWidth: .infinity, minHeight: ToolActivityTimelineLayout.rowMinHeight, alignment: .topLeading)
    .background(alignment: .topLeading) {
      GeometryReader { proxy in
        Rectangle()
          .fill(Ink.secondary.opacity(0.28))
          .frame(
            width: ToolActivityTimelineLayout.connectorWidth,
            height: max(0, proxy.size.height - ToolActivityTimelineLayout.connectorBottomTrim)
          )
          .offset(
            x: ToolActivityTimelineLayout.connectorOriginX,
            y: ToolActivityTimelineLayout.connectorTopInset
          )
      }
      .accessibilityHidden(true)
    }
    .accessibilityElement(children: .contain)
    .accessibilityLabel(text)
    .accessibilityIdentifier("query-shell-turn-commentary")
  }
}

// MARK: - Tool Call Card

struct ToolCallCard: View {
  let name: String
  let status: ToolCallStatus
  let input: ToolCallInput?
  let output: String?
  var connectsToNext = false
  var agentOpenRef: AgentTimelineRef? = nil
  var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil
  var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil

  @State private var isExpanded = false
  @State private var showUnavailable = false

  private var hasExpandableContent: Bool {
    ToolActivityTimelinePresentation.hasExpandableContent(input: input, output: output)
  }

  private var displayStatus: ToolCallStatus {
    ToolActivityTimelinePresentation.displayStatus(toolName: name, status: status)
  }

  private var accessibilityTitle: String {
    [ChatContentBlock.displayName(for: name), input?.summary]
      .compactMap { $0 }
      .filter { !$0.isEmpty }
      .joined(separator: ", ")
  }

  private var canOpenSpawnedAgent: Bool {
    AgentTimelineOpenFeedback.shouldShowLinkOut(
      hasResolvableAgent: agentOpenRef != nil,
      hasOpenAction: onOpenAgentRef != nil || onOpenAgent != nil,
      showUnavailable: showUnavailable
    )
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
      ToolCallActivityHeadline(name: name, status: displayStatus) {
        toolHeader
      }

      if isExpanded || showUnavailable {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          if let details = input?.details {
            VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
              Text("Input")
                .scaledFont(size: OmiType.micro, weight: .semibold)
                .foregroundColor(Ink.secondary)

              Text(details)
                .scaledFont(size: OmiType.caption, design: .monospaced)
                .foregroundColor(Ink.secondary)
                .lineLimit(10)
            }
          }

          if let output = output, !output.isEmpty {
            VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
              Text("Output")
                .scaledFont(size: OmiType.micro, weight: .semibold)
                .foregroundColor(Ink.secondary)

              Text(output)
                .scaledFont(size: OmiType.caption, design: .monospaced)
                .foregroundColor(Ink.secondary)
                .lineLimit(15)
            }
          }

          if showUnavailable {
            Text("Agent unavailable — it may have been dismissed.")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }
        }
        .padding(.vertical, OmiSpacing.xs)
        .padding(.leading, ToolActivityTimelineLayout.expandedContentLeadingInset)
        .padding(.trailing, OmiSpacing.sm)
      }
    }
    .frame(maxWidth: .infinity, minHeight: ToolActivityTimelineLayout.rowMinHeight, alignment: .topLeading)
    .background(alignment: .topLeading) {
      if connectsToNext {
        GeometryReader { proxy in
          Rectangle()
            .fill(Ink.secondary.opacity(0.28))
            .frame(
              width: ToolActivityTimelineLayout.connectorWidth,
              height: max(0, proxy.size.height - ToolActivityTimelineLayout.connectorBottomTrim)
            )
            .offset(
              x: ToolActivityTimelineLayout.connectorOriginX,
              y: ToolActivityTimelineLayout.connectorTopInset
            )
            .transition(.scale(scale: 0, anchor: .top).combined(with: .opacity))
        }
        .accessibilityHidden(true)
      }
    }
    .accessibilityElement(children: .contain)
  }

  @ViewBuilder
  private var toolHeader: some View {
    HStack(alignment: .center, spacing: OmiSpacing.xxs) {
      if hasExpandableContent {
        Button(action: {
          OmiMotion.withGated(.easeInOut(duration: 0.2)) {
            isExpanded.toggle()
          }
        }) {
          toolHeaderLabel(showsDisclosure: true)
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityHint(isExpanded ? "Collapse tool details" : "Expand tool details")
      } else {
        toolHeaderLabel(showsDisclosure: false)
          .frame(maxWidth: .infinity, alignment: .leading)
      }

      Group {
        if canOpenSpawnedAgent {
          Button(action: {
            openSpawnedAgent { succeeded in
              if AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: succeeded) {
                showUnavailable = true
              }
            }
          }) {
            Image(systemName: "arrow.up.forward.app")
              .scaledFont(size: OmiType.micro)
              .foregroundColor(Ink.secondary)
              .frame(maxWidth: .infinity, maxHeight: .infinity)
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .help("Open agent")
        } else if agentOpenRef != nil {
          Color.clear
        }
      }
      .frame(width: agentOpenRef == nil ? 0 : 28, height: 28)
    }
    .textSelection(.disabled)
  }

  private func toolHeaderLabel(showsDisclosure: Bool) -> some View {
    ToolCallHeaderLabel(
      title: ChatContentBlock.displayName(for: name),
      summary: input?.summary,
      showsDisclosure: showsDisclosure,
      isExpanded: isExpanded
    )
    .contentShape(Rectangle())
    .accessibilityElement(children: .ignore)
    .accessibilityLabel(accessibilityTitle)
    .accessibilityValue(ToolActivityTimelinePresentation.accessibilityValue(for: displayStatus))
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
    if case .agentSpawn(_, let pillId, _, _, _, _, _) = self {
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

    return Self.canonicalSpawnReceipt(in: output)?.pillId
      ?? Self.labeledValue(in: output, keys: ["id"]).flatMap(UUID.init(uuidString:))
  }

  var spawnedAgentSessionID: String? {
    if case .agentSpawn(_, _, let sessionId, _, _, _, _) = self {
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
    return Self.canonicalSpawnReceipt(in: output)?.sessionId
      ?? Self.labeledValue(in: output, keys: ["sessionid", "session_id"])
  }

  var spawnedAgentRunID: String? {
    if case .agentSpawn(_, _, _, let runId, _, _, _) = self {
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
    return Self.canonicalSpawnReceipt(in: output)?.runId
      ?? Self.labeledValue(in: output, keys: ["runid", "run_id"])
  }

  var spawnedAgentTitle: String? {
    guard case .toolCall(_, let name, let status, _, _, let output) = self,
      Self.cleanToolName(name) == "spawn_agent",
      !status.isInFlight,
      let output
    else { return nil }
    return Self.canonicalSpawnReceipt(in: output)?.title
      ?? Self.labeledValue(in: output, keys: ["title"])
  }

  var spawnedAgentProvider: String? {
    if case .agentSpawn(_, _, _, _, _, _, let provider) = self {
      return provider?.rawValue
    }
    guard case .toolCall(_, let name, let status, _, _, let output) = self,
      Self.cleanToolName(name) == "spawn_agent",
      !status.isInFlight,
      let output
    else { return nil }
    return Self.canonicalSpawnReceipt(in: output)?.provider
  }

  /// Parse a labeled `key: value` line from a spawn_agent tool block's output.
  static func labeledSpawnValue(in block: ChatContentBlock, keys: [String]) -> String? {
    guard case .toolCall(_, _, _, _, _, let output) = block, let output else { return nil }
    return labeledValue(in: output, keys: keys)
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

  /// Decode the one-line JSON emitted by the production Node `spawn_agent`
  /// control tool. The labeled-line parser below remains decode-only rollback
  /// compatibility for responses written by the previous desktop release.
  private static func canonicalSpawnReceipt(in output: String) -> (
    pillId: UUID?, sessionId: String?, runId: String?, title: String?, provider: String?
  )? {
    guard let data = output.data(using: .utf8),
      let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      root["ok"] as? Bool == true
    else { return nil }

    let firstAgent = (root["agents"] as? [[String: Any]])?.first
    let session =
      (firstAgent?["session"] as? [String: Any])
      ?? (root["session"] as? [String: Any])
    let run =
      (firstAgent?["run"] as? [String: Any])
      ?? (root["run"] as? [String: Any])
    let metadata = session?["metadata"] as? [String: Any]

    func string(_ value: Any?) -> String? {
      guard let raw = value as? String else { return nil }
      let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
      return trimmed.isEmpty ? nil : trimmed
    }

    let pillRaw =
      string(session?["externalRefId"])
      ?? string(metadata?["pillId"])
      ?? string(root["pillId"])
    let defaultAdapterId = string(session?["defaultAdapterId"])
    let authoritativeProvider =
      ["hermes", "openclaw"].contains(defaultAdapterId ?? "")
      ? defaultAdapterId
      : nil
    let legacyProvider = string(metadata?["provider"])
    let provider =
      authoritativeProvider
      ?? (["hermes", "openclaw"].contains(legacyProvider ?? "") ? legacyProvider : nil)
    return (
      pillId: pillRaw.flatMap(UUID.init(uuidString:)),
      sessionId: string(session?["sessionId"]),
      runId: string(run?["runId"]),
      title: string(session?["title"]),
      provider: provider
    )
  }

  private static func cleanToolName(_ name: String) -> String {
    guard name.hasPrefix("mcp__") else { return name }
    return String(name.split(separator: "__").last ?? Substring(name))
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
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "exclamationmark.triangle.fill")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(PageGlass.warning)

      Text("This is taking longer than usual.")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)

      Spacer(minLength: 4)

      Button(action: onCancel) {
        Text("Cancel")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.surface)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(Ink.errorRed)
          .clipShape(Capsule(style: .continuous))
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .background(Ink.rowFill)
    .overlay(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .strokeBorder(PageGlass.warning.opacity(0.4), lineWidth: 1)
    )
    .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))
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
        OmiMotion.withGated(.easeInOut(duration: 0.2)) {
          isExpanded.toggle()
        }
      }) {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "brain")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)

          Text("Thinking")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.secondary)
            .italic()

          Spacer(minLength: 4)

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.micro)
            .foregroundColor(Ink.secondary)
        }
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.xs)
      }
      .buttonStyle(.plain)

      // Expanded thinking content
      if isExpanded {
        Divider()
          .padding(.horizontal, OmiSpacing.sm)

        Text(text)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .italic()
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.sm)
          .lineLimit(30)
      }
    }
    .glassCard(cornerRadius: 16)
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
        OmiMotion.withGated(.easeInOut(duration: 0.2)) {
          isExpanded.toggle()
        }
      }) {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "doc.text.magnifyingglass")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.primary)

          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text(title)
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(Ink.primary)

            Text(summary)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
              .lineLimit(2)
          }

          Spacer(minLength: 4)

          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.micro)
            .foregroundColor(Ink.secondary)
        }
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
      }
      .buttonStyle(.plain)

      // Expanded content
      if isExpanded {
        Divider()
          .padding(.horizontal, OmiSpacing.sm)

        ScrollView {
          OmiMarkdown(text: fullText, sender: .ai)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
        }
        .frame(maxHeight: 300)
      }
    }
    .glassCard(cornerRadius: 18)
  }
}
