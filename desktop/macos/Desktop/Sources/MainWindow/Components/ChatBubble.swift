import AppKit
import OmiTheme
import SwiftUI

// MARK: - Chat Bubble

struct ChatBubble: View {
  let message: ChatMessage
  let app: OmiApp?
  let showsOmiMark: Bool
  let onRate: (Int?) -> Void
  var onCitationTap: ((Citation) -> Void)? = nil
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
  /// Controllable seam for the metadata band's reveal state. Hover is not
  /// drivable from a test process (it is never the active application), and the
  /// invariant worth pinning — a revealed band adds no layout height — is only
  /// observable with the band actually revealed. Nil everywhere in production.
  var metadataRevealOverrideForTesting: Bool? = nil

  @State private var isRowHovering = false
  /// The band draws outside the row's bounds, so it needs its own hover to stay
  /// up while the pointer is on the controls.
  @State private var isMetadataBandHovering = false
  @State private var isExpanded = false
  @State private var showCopied = false
  @State private var showRatingFeedback = false
  @State private var showInfoPopover = false
  @State private var lastSubmittedRating: Int?
  // Shared across every metadata control: true while any of them holds
  // keyboard focus, so Tab / Full Keyboard Access never lands on an
  // invisible button.
  @FocusState private var isMetadataControlFocused: Bool

  init(
    message: ChatMessage, app: OmiApp?, showsOmiMark: Bool, onRate: @escaping (Int?) -> Void,
    onCitationTap: ((Citation) -> Void)? = nil, isDuplicate: Bool = false,
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
      text: message.text,
      isStreaming: message.isStreaming,
      isExpanded: isExpanded
    )
  }

  /// The text to display (truncated or full) — keeps the start of the message visible
  private var displayText: String {
    ChatBubbleTruncation.displayText(
      message.text,
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
    .onHover { isRowHovering = $0 }
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
        groupView(group)
      }
      if message.isStreaming, app != nil {
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
if message.sender == .ai, shouldTruncate {
            // Keep the expansion affordance on the same baseline as the
            // visible truncation ellipsis. The text gets the remaining width,
            // so the control cannot fall onto a detached row.
            HStack(alignment: .lastTextBaseline, spacing: OmiSpacing.xs) {
              messageTextBubble(displayText)
                .frame(maxWidth: .infinity, alignment: .leading)
                .layoutPriority(0)
              showMoreButton
            }
            .frame(
              maxWidth: .infinity,
              alignment: .leading
            )
          } else if message.isStreaming {
            StreamingAssistantText(displayText, isStreaming: true, sender: message.sender)
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.sm)
              .background(
                message.sender == .user
                  ? OmiColors.userBubble : OmiColors.backgroundTertiary.opacity(0.42)
              )
          } else {
                  ? OmiColors.userBubble : OmiColors.backgroundTertiary.opacity(0.42)
              )
          } else {
            messageTextBubble(displayText)
          }
        }

        if backgroundAgentSummary == nil, message.text.count > Self.truncationThreshold {
          if isExpanded {
            Button(action: { isExpanded.toggle() }) {
              // Pairs with `showMoreButton`; left `.white`, it vanished on the light panel.
              Text("Show less")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.accent)
            }
            .buttonStyle(.plain)
          } else if message.sender == .user, shouldTruncate {
            // Keep the pre-existing user-bubble layout. Only assistant replies
            // need the inline treatment; moving this control beside a user
            // bubble would pull its trailing edge left by the button width.
            showMoreButton
          }
        }

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

    if message.sender == .ai && !message.isStreaming && message.isSynced {
      messageMetadataRow(includeRatingButtons: true, includeCopyButton: true)
    } else if message.sender == .ai && !message.isStreaming && !message.copyableText.isEmpty {
      messageMetadataRow(includeRatingButtons: false, includeCopyButton: true)
    } else if message.sender == .ai && !message.isStreaming {
      messageMetadataRow(includeRatingButtons: false, includeCopyButton: false)
    }
    // **A user turn gets no metadata band.** Its timestamp-only row cost every
    // question a reserved band for a fact the reply underneath already stamps.
  }

  private var presentation: ChatRowPresentation { ChatRowPresentation.of(message) }

  @ViewBuilder
  private func messageTextBubble(_ text: String) -> some View {
    if presentation == .proactivePush {
      ChatProactivePushRow(text: text)
    } else {
      OmiMarkdown(text: text, sender: message.sender)
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
return AnyView(StreamingAssistantText(text, isStreaming: message.isStreaming))
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

  @ViewBuilder
  private func messageMetadataRow(includeRatingButtons: Bool, includeCopyButton: Bool) -> some View {
    let isVisible =
      metadataRevealOverrideForTesting
      ?? ChatBubbleMetadataReveal.isVisible(
        hovering: isRowHovering || isMetadataBandHovering,
        controlFocused: isMetadataControlFocused,
        transientFeedback: showRatingFeedback || showCopied || showInfoPopover
      )
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
    // The zero-height frame proposes zero height; take the band's own instead of
    // letting the proposal squash it.
    .fixedSize(horizontal: false, vertical: true)
    // Hover has to survive the pointer reaching the controls. The band draws
    // outside the row's bounds, so the row's own `onHover` reports a leave the
    // moment the pointer moves down onto the buttons. Inside `allowsHitTesting`,
    // so a hidden band cannot reveal itself — this only keeps a revealed one up.
    .contentShape(Rectangle())
    .onHover { isMetadataBandHovering = $0 }
    // **Costs nothing at rest, and nothing when revealed either.** It was already
    // invisible at rest, but an `opacity(0)` row still reserves its height, and
    // ~20 pt on every assistant turn was most of the dead space between two
    // one-line messages. So the band is *always* zero-height in layout and draws
    // out of that frame into the 16 pt gap the transcript keeps after an
    // assistant row (`ChatTranscriptLayout.regularRowSpacing`).
    //
    // Sizing it on reveal instead made document height a function of where the
    // pointer was: a hovered row was ~16 pt taller, so every row below it shifted
    // down — under the cursor, mid-scroll, since scrolling happens with the
    // pointer over the transcript. Painting outside the frame was always the
    // intent; only the layout height was wrong.
    .frame(height: 0, alignment: .top)
    // Outside the zero-height frame, or the stack's 4 pt outlives the row it spaced.
    .padding(.top, -OmiSpacing.xxs)
    .opacity(isVisible ? 1 : 0)
    .allowsHitTesting(isVisible)
    .omiAnimation(.easeInOut(duration: 0.15), value: isRowHovering)
    .omiAnimation(.easeInOut(duration: 0.15), value: isMetadataBandHovering)
    .omiAnimation(.easeInOut(duration: 0.15), value: isMetadataControlFocused)
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
    }
    .buttonStyle(.plain)
    .focused($isMetadataControlFocused)
    .help("Copy message")
  }

  /// Response Context popover — same developer info the floating bar shows
  /// (model, screenshot, prompt context counts, tools). Only fresh responses
  /// carry metadata; it is in-memory only and not persisted across restarts.
  @ViewBuilder
  private var infoButton: some View {
    Button(action: { showInfoPopover.toggle() }) {
      Image(systemName: "info.circle")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(showInfoPopover ? Ink.primary : Ink.secondary)
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
    // Streaming messages always re-render so SwiftUI sees live updates
    guard !lhs.message.isStreaming && !rhs.message.isStreaming else { return false }
    // Completed messages are equal when visible content hasn't changed
    return lhs.message.id == rhs.message.id
      && lhs.message.text == rhs.message.text
      && lhs.message.rating == rhs.message.rating
      && lhs.app?.id == rhs.app?.id
      && lhs.showsOmiMark == rhs.showsOmiMark
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
  case questionCard(id: String, questionID: String, text: String, options: [[String: Any]], selectedOptionID: String?)
  case taskCard(id: String, taskID: String)
  case goalLink(id: String, goalID: String, summary: String)
  case captureLink(id: String, conversationID: String, momentTimestampMs: Int?, summary: String)
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
    case .toolCalls(let id, _): return id
    case .thinking(let id, _): return id
    case .discoveryCard(let id, _, _, _): return id
    case .questionCard(let id, _, _, _, _): return id
    case .taskCard(let id, _): return id
    case .goalLink(let id, _, _): return id
    case .captureLink(let id, _, _, _): return id
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
      case .memoryLink(let id, let memoryID, let summary):
        flushToolCalls()
        guard richBlockRenderingEnabled else { continue }
        groups.append(.memoryLink(id: id, memoryID: memoryID, summary: summary))
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
    return group(blocks, richBlockRenderingEnabled: richBlockRenderingEnabled).compactMap { group in
      switch group {
      case .text(_, let text):
        return text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : group
      case .discoveryCard, .questionCard, .taskCard, .goalLink, .captureLink, .memoryLink, .agentSpawn,
        .agentCompletion:
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

/// Keeps streamed tool groups compact until the reader explicitly asks for the details.
enum ToolCallsGroupExpansionPolicy {
  static func initiallyExpanded() -> Bool {
    false
  }
}

/// Renders a group of consecutive tool calls as a single summary line with
/// optional expanded per-step details.
struct ToolCallsGroup: View {
  let calls: [ChatContentBlock]
  var compact: Bool = false
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
    onCancel: (() -> Void)? = nil,
    onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil,
    onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil
  ) {
    self.calls = calls
    self.compact = compact
    self.onCancel = onCancel
    self.onOpenAgent = onOpenAgent
    self.onOpenAgentRef = onOpenAgentRef
    self._isExpanded = State(initialValue: ToolCallsGroupExpansionPolicy.initiallyExpanded())
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
    AgentTimelineOpenFeedback.shouldShowLinkOut(
      hasResolvableAgent: spawnedAgentOpenRef != nil,
      hasOpenAction: onOpenAgentRef != nil || onOpenAgent != nil,
      showUnavailable: showUnavailable
    )
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
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.bottom, compact ? OmiSpacing.xs : OmiSpacing.sm)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .fixedSize(horizontal: false, vertical: true)
    .glassCard(cornerRadius: compact ? 14 : 16)
  }

  private var header: some View {
    StableChatCardHeader(
      isExpanded: isExpanded,
      showsDisclosure: true,
      horizontalPadding: OmiSpacing.sm,
      verticalPadding: compact ? 0 : OmiSpacing.xs,
      minimumHeight: compact ? 34 : nil,
      onToggle: {
        OmiMotion.withGated(.easeInOut(duration: 0.2)) {
          isExpanded.toggle()
        }
      },
      onOpen: canOpenSpawnedAgent
        ? {
          openSpawnedAgent { succeeded in
            if AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: succeeded) {
              showUnavailable = true
            }
          }
        } : nil
    ) {
      statusIcon(for: aggregateStatus, size: 12)
    } content: {
      HStack(spacing: compact ? 7 : 6) {
        Text(currentToolName)
          .scaledFont(size: OmiType.caption, weight: compact ? .semibold : .regular)
          .foregroundColor(Ink.secondary)
          .lineLimit(1)

        if let summary = currentToolSummary, !summary.isEmpty {
          Text(summary)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
            .lineLimit(1)
            .truncationMode(.middle)
        }

        if calls.count > 1 {
          Text(compact ? "· \(calls.count) steps" : "·")
            .scaledFont(size: compact ? 11 : 12)
            .foregroundColor(Ink.secondary)
            .lineLimit(1)
          if !compact {
            Text("\(calls.count) steps")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }
        }
      }
    }
  }

  private var expandedToolCalls: some View {
    VStack(alignment: .leading, spacing: 0) {
      Divider()
        .padding(.horizontal, OmiSpacing.sm)

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
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
      .padding(.horizontal, OmiSpacing.xs)
      .padding(.vertical, OmiSpacing.xs)
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
      // Compact header row
      StableChatCardHeader(
        isExpanded: isExpanded,
        showsDisclosure: hasExpandableContent,
        horizontalPadding: OmiSpacing.sm,
        verticalPadding: OmiSpacing.xs,
        onToggle: hasExpandableContent
          ? {
            if hasExpandableContent {
              OmiMotion.withGated(.easeInOut(duration: 0.2)) {
                isExpanded.toggle()
              }
            }
          } : nil,
        onOpen: canOpenSpawnedAgent
          ? {
            openSpawnedAgent { succeeded in
              if AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: succeeded) {
                showUnavailable = true
              }
            }
          } : nil
      ) {
        // Status indicator — uses the shared statusIcon helper so
        // .slow / .stalled / .failed render the same way here as in
        // the group header.
        statusIcon(for: status, size: 12)
      } content: {
        HStack(spacing: OmiSpacing.xs) {
          // Tool name
          Text(ChatContentBlock.displayName(for: name))
            .scaledFont(size: OmiType.caption, design: .monospaced)
            .foregroundColor(Ink.secondary)

          // Inline argument summary
          if let summary = input?.summary {
            Text("·")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)

            Text(summary)
              .scaledFont(size: OmiType.caption, design: .monospaced)
              .foregroundColor(Ink.secondary)
              .lineLimit(1)
              .truncationMode(.middle)
          }
        }
      }

      // Expanded content
      if isExpanded || showUnavailable {
        Divider()
          .padding(.horizontal, OmiSpacing.sm)

        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          // Input details
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

          // Output
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
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.sm)
      }
    }
    .glassCard(cornerRadius: 16)
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

// MARK: - Tool Call Status Icon (shared by ToolCallsGroup + ToolCallCard)

/// Single source of truth for how each `ToolCallStatus` value renders
/// as a small inline icon. Used in both the group header and individual
/// tool rows so the visual language is consistent.
@MainActor @ViewBuilder
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
      .tint(PageGlass.warning)
  case .stalled:
    Image(systemName: "exclamationmark.triangle.fill")
      .scaledFont(size: size)
      .foregroundColor(PageGlass.warning)
  case .completed:
    Image(systemName: "checkmark.circle.fill")
      .scaledFont(size: size)
      .foregroundColor(Ink.listeningGreen)
  case .failed:
    Image(systemName: "xmark.circle.fill")
      .scaledFont(size: size)
      .foregroundColor(Ink.errorRed)
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
