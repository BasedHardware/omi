import AppKit
import OmiTheme
import SwiftUI

/// A token that callers pass when the local user sends a message.
/// This allows ChatMessagesView to distinguish genuine user sends from
/// messages arriving via polling, sync, or other sources — without
/// inferring solely from messages.count changes.
struct LocalSendToken: Equatable {
  /// Monotonic counter that increments on every local send.
  /// ChatMessagesView tracks the last seen value and reacts to increments.
  let generation: Int
}

/// Pure duplicate-detection for the chat transcript. Extracted so it is unit
/// testable and so the fingerprint can't silently collide distinct messages.
enum ChatMessageDeduplicator {
  /// IDs of long messages that are exact duplicates of an earlier message in
  /// the same list. The fingerprint is sender + the FULL body: an earlier
  /// implementation keyed only on the first 200 characters, so two genuinely
  /// distinct long messages that shared an opening (same preamble, different
  /// answer) collided and the later one was hidden. Only true whole-message
  /// duplicates (sync/poll replay) should collapse.
  static func duplicateIDs(in messages: [ChatMessage]) -> Set<String> {
    var seen: [String: String] = [:]  // sender+full-text fingerprint → first message ID
    var dupes = Set<String>()
    for msg in messages {
      guard msg.text.count > 200 else { continue }  // only dedup long messages
      let fingerprint = "\(msg.sender)\u{1}\(msg.text)"
      if seen[fingerprint] != nil {
        dupes.insert(msg.id)
      } else {
        seen[fingerprint] = msg.id
      }
    }
    return dupes
  }
}

/// **When duplicate detection has to run again.**
///
/// It is a full pass over every long message in the mounted window — 4.2 ms at
/// the 500-row cap, measured — and the transcript used to re-derive it on every
/// body evaluation, which during a streamed answer is once per 35 ms flush. A
/// streamed tail cannot create a duplicate *pair* among the rows above it, so
/// the derivation belongs to the transcript's **shape** rather than its content:
/// which rows are present, how many are mounted, whose conversation it is, and
/// the moment a turn settles and its text stops being rewritten.
struct ChatTranscriptDuplicateKey: Equatable {
  let messageCount: Int
  let newestMessageID: String?
  let presentation: ChatTranscriptWindow.Presentation
  let conversationIdentity: String
  /// A settled turn may have had its text replaced wholesale by journal replay
  /// without the count moving, so the settle itself is part of the shape.
  let isSettled: Bool

  init(
    messages: [ChatMessage],
    presentation: ChatTranscriptWindow.Presentation,
    conversationIdentity: String,
    isSending: Bool
  ) {
    messageCount = messages.count
    newestMessageID = messages.last?.id
    self.presentation = presentation
    self.conversationIdentity = conversationIdentity
    isSettled = !isSending
  }
}

/// Stable conversation identity sentinels for surfaces without a persisted session.
enum ChatConversationIdentity {
  static let mainChatDefault = "main-chat-default"
}

/// Pure decision for the conversation-switch scroll-state reset. Callers pass
/// the stable conversation/session identity; message IDs are not identities
/// because prepending history changes the first message in the same chat.
enum ChatConversationSwitch {
  /// - Parameters:
  ///   - tracked: the conversation id currently being tracked.
  ///   - newId: the incoming stable conversation/session identity.
  /// - Returns: the id to track next, and whether to reset session state.
  ///   A nil incoming id keeps tracking the previous conversation (so the
  ///   reset fires when the real conversation arrives) and never resets;
  ///   a real incoming id resets only when a previous conversation existed
  ///   (never on the initial population).
  static func transition(current tracked: String?, incoming newId: String?)
    -> (newTracked: String?, shouldReset: Bool)
  {
    guard let newId, newId != tracked else { return (tracked, false) }
    return (newId, tracked != nil)
  }
}

/// Lifecycle state for the one-shot launch placement. A pending placement may
/// be retried if SwiftUI removes the chat surface during Home's launch
/// transition; explicit reader input permanently wins for this view lifetime.
enum ChatInitialRestoreState: Equatable {
  case waiting
  case pending
  case completed
  case userInterrupted

  var canStart: Bool {
    self == .waiting
  }

  static func afterDisappear(_ state: Self) -> Self {
    state == .pending ? .waiting : state
  }

  /// Every new transcript presentation begins at the live edge. A previously
  /// completed placement belongs to the old mounted scroll view, not the new
  /// one SwiftUI creates after a Home transition or route change.
  static func atPresentationStart(previous _: Self) -> Self { .waiting }

  static func afterUserInteraction(_ state: Self) -> Self {
    switch state {
    case .waiting, .pending:
      return .userInterrupted
    case .completed, .userInterrupted:
      return state
    }
  }
}

/// **The rhythm of the transcript**, which is what makes a column of short
/// messages read as a conversation instead of as scattered text.
///
/// One rule: things that belong together sit closer than things that do not. A
/// reply belongs to the question above it, so that gap is the small one; the next
/// question starts a new exchange, so that gap is the large one. Before this the
/// stack used a single 16 pt gap everywhere, which said nothing about what went
/// with what — and because each row also carried a permanently reserved metadata
/// band and a container's padding without a container, consecutive one-line
/// messages ended up roughly 140 pt apart.
enum ChatTranscriptLayout {
  /// The stack's own spacing, and the largest gap in the ladder: the boundary
  /// between one exchange and the next. Every other gap is this plus a negative
  /// `topAdjustment`, so the stack has one spacing and the exceptions are named.
  static let regularRowSpacing: CGFloat = OmiSpacing.lg
  static let consecutiveUserRowSpacing: CGFloat = OmiSpacing.sm
  /// A reply and the question that caused it are one exchange, not two events.
  /// `md` rather than `sm`: the user bubble's own bottom padding already hugs
  /// the text, so `sm` left the next assistant line sitting on the bubble.
  static let replySpacing: CGFloat = OmiSpacing.md

  /// The gap *before* `current`, given the row above it.
  ///
  /// An assistant row above always takes the full gap: it closes an exchange, and
  /// it is also the row whose hover-revealed metadata band draws into the space
  /// below it, so that space has to exist.
  static func spacing(from previous: ChatMessage, to current: ChatMessage) -> CGFloat {
    guard previous.sender == .user else { return regularRowSpacing }
    return current.sender == .user ? consecutiveUserRowSpacing : replySpacing
  }

  static func topAdjustment(at index: Int, in messages: [ChatMessage]) -> CGFloat {
    guard index > 0, messages.indices.contains(index) else { return 0 }
    return spacing(from: messages[index - 1], to: messages[index]) - regularRowSpacing
  }
}

/// **Where the jump-to-latest control sits: in the transcript's own trailing gutter, never on a
/// message.**
///
/// It floats over a live transcript, so "in the corner" is not a placement. A 36 pt disc inset 16 pt
/// reached 52 pt in from the scroll view's trailing edge while the message column stops at the
/// transcript's trailing inset — 32 on the ask panel — so the control sat *on* the trailing edge of
/// every user bubble it passed, which is the one place a right-aligned transcript guarantees there is
/// something to cover.
///
/// The transcript already keeps a clear gutter on that side (it is the trailing half of the same
/// symmetric inset whose leading half holds the assistant's mark). So the control is fitted to that
/// gutter rather than dropped on top of it: as large as the gutter allows, pushed to the outside of
/// it, and clamped so it stays a real click target on hosts whose gutter is too small to hold one.
enum ChatScrollJumpPlacement {
  /// The disc at full size, which is what the ask panel's gutter can hold.
  static let maximumDiameter: CGFloat = 32
  /// Below this it stops being a target worth aiming at, so a narrower gutter is overlapped rather
  /// than obeyed — the honest trade, and the reason `clearsMessageColumn` exists to say which case a
  /// host is in.
  static let minimumDiameter: CGFloat = 24

  static func diameter(trailingContentInset: CGFloat) -> CGFloat {
    min(maximumDiameter, max(minimumDiameter, trailingContentInset))
  }

  /// How far the disc sits from the scroll view's trailing edge: whatever the gutter has left after
  /// the disc, up to one small gap. Zero when the gutter is the disc, which is the ask panel.
  static func trailingInset(trailingContentInset: CGFloat) -> CGFloat {
    let leftover = trailingContentInset - diameter(trailingContentInset: trailingContentInset)
    return max(0, min(OmiSpacing.sm, leftover))
  }

  /// Whether the disc lands entirely outside the message column.
  static func clearsMessageColumn(trailingContentInset: CGFloat) -> Bool {
    diameter(trailingContentInset: trailingContentInset)
      + trailingInset(trailingContentInset: trailingContentInset) <= trailingContentInset
  }
}

/// The desktop transcript is deliberately a recent-window view. Older turns
/// stay in the canonical journal, but rendering an unbounded timeline makes
/// ordinary chat sessions progressively more expensive to scroll and update.
enum ChatTranscriptWindow {
  static let maximumVisibleMessageCount = 500
  static let compactHomeInitialMessageCount = 50

  enum Presentation: Equatable {
    case initial
    case expanded
  }

  /// Controls how many locally available rows are mounted before the reader
  /// explicitly asks for older context. The expanded limit stays bounded so
  /// the eager stack retains stable rich-Markdown geometry.
  struct Policy: Equatable {
    let initialMessageCount: Int
    let maximumMessageCount: Int

    init(
      initialMessageCount: Int,
      maximumMessageCount: Int = ChatTranscriptWindow.maximumVisibleMessageCount
    ) {
      let boundedMaximum = min(
        max(1, maximumMessageCount),
        ChatTranscriptWindow.maximumVisibleMessageCount
      )
      self.maximumMessageCount = boundedMaximum
      self.initialMessageCount = min(max(1, initialMessageCount), boundedMaximum)
    }

    static let standard = Self(initialMessageCount: ChatTranscriptWindow.maximumVisibleMessageCount)
    static let compactHome = Self(initialMessageCount: ChatTranscriptWindow.compactHomeInitialMessageCount)
  }

  enum EarlierAction: Equatable {
    case none
    case revealLocallyLoadedRows
    case loadMoreRows
    case revealLocallyLoadedRowsAndLoadMore
  }

  static func recentMessages(in messages: [ChatMessage]) -> [ChatMessage] {
    visibleMessages(in: messages, policy: .standard, presentation: .expanded)
  }

  static func visibleMessages(
    in messages: [ChatMessage],
    policy: Policy,
    presentation: Presentation
  ) -> [ChatMessage] {
    let limit = presentation == .initial ? policy.initialMessageCount : policy.maximumMessageCount
    return Array(messages.suffix(limit))
  }

  static func prependAnchorID(
    in messages: [ChatMessage],
    policy: Policy,
    presentation: Presentation
  ) -> String? {
    visibleMessages(in: messages, policy: policy, presentation: presentation).first?.id
  }

  /// Duplicate detection only needs to inspect rows this surface can render.
  /// Keeping the windowing at this boundary gives streaming body evaluations a
  /// deterministic O(visible-window) work budget even when the journal grows.
  static func visibleDuplicateIDs(in messages: [ChatMessage]) -> Set<String> {
    duplicateIDs(inVisibleWindow: recentMessages(in: messages))
  }

  /// Deduplicates a window that the caller has already bounded. Keeping this
  /// overload separate avoids copying the suffix twice when the transcript
  /// body shares one visible snapshot with the lifecycle projection.
  static func duplicateIDs(inVisibleWindow messages: [ChatMessage]) -> Set<String> {
    ChatMessageDeduplicator.duplicateIDs(in: messages)
  }

  static func allowsLoadingEarlier(for messages: [ChatMessage]) -> Bool {
    allowsLoadingEarlier(for: messages, policy: .standard)
  }

  static func allowsLoadingEarlier(for messages: [ChatMessage], policy: Policy) -> Bool {
    messages.count < policy.maximumMessageCount
  }

  static func canRevealLocallyLoadedRows(
    in messages: [ChatMessage],
    policy: Policy,
    presentation: Presentation
  ) -> Bool {
    presentation == .initial
      && policy.initialMessageCount < policy.maximumMessageCount
      && messages.count > policy.initialMessageCount
  }

  static func earlierAction(
    for messages: [ChatMessage],
    policy: Policy,
    presentation: Presentation,
    hasMoreMessages: Bool
  ) -> EarlierAction {
    let canReveal = canRevealLocallyLoadedRows(
      in: messages,
      policy: policy,
      presentation: presentation
    )
    let canLoadMore = hasMoreMessages && allowsLoadingEarlier(for: messages, policy: policy)

    switch (canReveal, canLoadMore) {
    case (false, false):
      return .none
    case (true, false):
      return .revealLocallyLoadedRows
    case (false, true):
      return .loadMoreRows
    case (true, true):
      return .revealLocallyLoadedRowsAndLoadMore
    }
  }
}

/// Reusable chat messages scroll view extracted from ChatPage.
/// Used by both ChatPage (main chat) and TaskChatPanel (task sidebar chat).
struct ChatMessagesView<WelcomeContent: View>: View {
  let messages: [ChatMessage]
  let conversationIdentity: String
  let isSending: Bool
  let hasMoreMessages: Bool
  let isLoadingMoreMessages: Bool
  let isLoadingInitial: Bool
  let app: OmiApp?
  let onLoadMore: () async -> Void
  let onRate: (String, Int?) -> Void
  var onCitationTap: ((Citation) -> Void)? = nil
  var onOpenInlineCitation: ((ChatCitationReference) -> Void)? = nil
  var sessionsLoadError: String? = nil
  var onRetry: (() -> Void)? = nil
  /// Token that increments each time the local user sends a message.
  /// ChatMessagesView uses this to follow the latest message immediately
  /// after the local user row is inserted.
  /// Pass nil when the caller cannot distinguish local sends (e.g. TaskChatPanel
  /// with its own send path).
  var localSendToken: LocalSendToken? = nil
  /// Fired when the user taps Cancel on a stalled-tool banner.
  /// Threaded down to `ToolCallsGroup`. Optional so existing callers
  /// don't need updating; ChatPage passes `chatProvider.stopAgent`.
  var onCancelTurn: (() -> Void)? = nil
  /// Opens a spawned background-agent pill from a `spawn_agent` tool row.
  /// Optional so task/sidebar chat callers that do not expose floating pills
  /// keep the existing non-clickable tool-card behavior.
  /// Completion reports whether the agent was resolved and presented.
  var onOpenAgent: ((UUID, @escaping (Bool) -> Void) -> Void)? = nil
  /// Opens via structured agent identity (session/run/pill) when available.
  var onOpenAgentRef: ((AgentTimelineRef, @escaping (Bool) -> Void) -> Void)? = nil
  /// Horizontal inset of the message column. Home passes 0 so bubbles align
  /// exactly with the ask bar's edges; other surfaces keep the default gutter.
  var horizontalContentPadding: CGFloat = ChatComposerLayout.transcriptEdgeInset
  /// Explicitly enables chat-first controls only in the Chat-first shell's main
  /// Chat route. Nil keeps shared transcript projections safe elsewhere.
  var chatFirstRichBlockContext: ChatFirstRichBlockContext? = nil
  /// Optional transcript-window override for callers with a smaller initial
  /// mount budget. When omitted, the existing 500-row default is preserved;
  /// the existing Home-only rich-block capability selects the compact Home
  /// policy automatically.
  var transcriptWindowPolicy: ChatTranscriptWindow.Policy? = nil
  /// Vertical transcript inset. Home uses a tighter value because its page
  /// shell already provides the breathing room beneath the floating top bar.
  var verticalContentPadding: CGFloat = OmiSpacing.xl
  /// Extra trailing inset only. Home passes a small value so the macOS overlay
  /// scrollbar doesn't clip right-aligned user pills when horizontalContentPadding
  /// is 0; the left edge stays aligned with the ask bar. Default 0.
  var trailingContentPadding: CGFloat = 0
  /// Where the prompt rail's right edge should land. Zero keeps it flush with
  /// Home's ask bar; pass a page margin only when the host's composer is inset.
  var timelineTrailingInset: CGFloat = 0
  /// Narrow sidebars (task chat) keep the rail off so it cannot sit on the text.
  var enablesPromptTimeline: Bool = true
  @ViewBuilder var welcomeContent: () -> WelcomeContent

  // MARK: - Scroll State

  /// Source of truth for scroll intent. Geometry/layout changes alone must NOT
  /// switch this to `.freeScrolling` — only physical user input (wheel/trackpad,
  /// mouse, or keyboard scroll-navigation).
  @State private var scrollMode: ChatScrollMode = .followingBottom
  /// Throttle token for scrollToBottom — prevents the streaming + scroll
  /// detection feedback loop from saturating the main thread.
  @State private var scrollThrottleWorkItem: DispatchWorkItem?
  /// When the transcript last re-reached the live edge, and whether one run is
  /// already queued for the current window. See `ChatScrollFollowThrottle`.
  @State private var lastFollowScrollTime: TimeInterval?
  @State private var hasQueuedFollowScroll = false
  /// True when the user is actively scrolling via scroll wheel/trackpad.
  /// Set immediately by the scroll wheel monitor to win the race against
  /// throttled programmatic scrolls during streaming.
  @State private var userIsScrolling = false
  @State private var userScrollEndWorkItem: DispatchWorkItem?
  /// Tracks work items for delayed initial bottom scrolls so they can be
  /// canceled on user scroll or disappear.
  @State private var initialScrollWorkItems: [DispatchWorkItem] = []
  // MARK: - Local Send Anchoring

  /// Last observed local send token generation. When it increments, we know
  /// a local user send just happened and can anchor the viewport.
  @State private var lastSeenSendGeneration: Int = 0

  // MARK: - Saved Restore

  /// Launch placement is bottom-first, unless the reader explicitly scrolls
  /// before it settles. A pending placement is retried after a transient view
  /// disappearance; completed/user-interrupted state preserves scroll position.
  @State private var initialRestoreState: ChatInitialRestoreState = .waiting

  // MARK: - Prepend Preservation (Load Earlier Messages)

  /// The ID of the first visible message before a "Load earlier" operation.
  /// After load completes, we scroll to reposition this message at the top
  /// of the viewport, preserving the user's reading position.
  @State private var prependAnchorId: String?
  /// Document height and clip origin captured with the anchor, so restore can
  /// compensate for rows inserted above rather than jumping to offset zero.
  @State private var prependSnapshot: ChatTranscriptPrependPreservation.Snapshot?
  /// True from the load-earlier click until restore settles. The control sits
  /// inside the transcript, so the content-size change looks like the same
  /// press moved the viewport — that must not cancel the restore.
  @State private var isPreservingPrepend = false

  /// Measured transcript geometry for the prompt timeline. This view
  /// deliberately does not observe the object; only the overlay subscribes, so
  /// scrolling does not re-evaluate every message row.
  @State private var transcriptGeometry = ChatTranscriptGeometry()

  // MARK: - Activity Below Indicator

  /// True when new content arrived while the user is scrolled away, so the
  /// jump-to-bottom affordance should be shown.
  @State private var hasActivityBelow = false

  // MARK: - Conversation Identity

  /// The first message ID of the conversation this view is currently tracking.
  /// Used to detect conversation switches so session-scoped @State can be reset.
  @State private var trackedConversationId: String?

  /// Starts compact on Home, and expands only after the reader asks for older
  /// locally-loaded rows. Standard callers start at the existing 500-row cap.
  @State private var transcriptWindowPresentation: ChatTranscriptWindow.Presentation = .initial

  // MARK: - Duplicate Rows

  /// Derived when the transcript's shape changes, not when its tail is rewritten.
  /// See `ChatTranscriptDuplicateKey`.
  @State private var duplicateMessageIDs: Set<String> = []
  var body: some View {
    ScrollViewReader { proxy in
      // Rail first, jump-to-latest on top of it. The rail is a full-height
      // trailing strip; stacking the disc underneath it ate the click.
      ZStack {
        scrollContent(proxy: proxy)
      }
      .overlay(alignment: .trailing) {
        if enablesPromptTimeline {
          ChatPromptTimelineOverlay(
            geometry: transcriptGeometry,
            trailingInset: timelineTrailingInset,
            onSelect: { markID in
              jumpToPrompt(markID, proxy: proxy)
            }
          )
        }
      }
      .overlay(alignment: .bottomTrailing) {
        scrollToBottomButton(proxy: proxy)
      }
      .onGeometryChange(for: CGSize.self) {
        $0.size
      } action: { size in
        transcriptGeometry.setViewport(size, columnWidth: size.width)
      }
    }
  }

  /// Never less than the mark's gutter, whatever the host asked for.
  private var leadingContentPadding: CGFloat {
    max(horizontalContentPadding, ChatOmiMarkPlacement.markGutter)
  }

  /// The clear strip between the message column and the scroll view's trailing edge. The
  /// jump-to-latest control is placed inside it — see `ChatScrollJumpPlacement`.
  private var trailingContentInset: CGFloat {
    horizontalContentPadding + trailingContentPadding
  }

  private var effectiveTranscriptWindowPolicy: ChatTranscriptWindow.Policy {
    transcriptWindowPolicy
      ?? (chatFirstRichBlockContext == nil ? .standard : .compactHome)
  }

  /// A direct timeline choice leaves live-follow mode and places the selected
  /// prompt at the top of the viewport.
  private func jumpToPrompt(_ markID: String, proxy: ScrollViewProxy) {
    cancelPendingScrollsForUserInteraction()
    userIsScrolling = false
    scrollMode = .freeScrolling
    hasActivityBelow = false
    OmiMotion.withGated(ChatPromptTimelineMetrics.jumpAnimation) {
      proxy.scrollTo(markID, anchor: .top)
    }
  }

  private func capturePrependAnchor() {
    if prependAnchorId == nil {
      prependAnchorId = ChatTranscriptWindow.prependAnchorID(
        in: messages,
        policy: effectiveTranscriptWindowPolicy,
        presentation: transcriptWindowPresentation
      )
    }
    if prependSnapshot == nil {
      prependSnapshot = transcriptGeometry.prependSnapshot()
    }
    isPreservingPrepend = true
  }

  private var visibleTranscriptMessages: [ChatMessage] {
    ChatTranscriptWindow.visibleMessages(
      in: messages,
      policy: effectiveTranscriptWindowPolicy,
      presentation: transcriptWindowPresentation
    )
  }

  private var duplicateKey: ChatTranscriptDuplicateKey {
    ChatTranscriptDuplicateKey(
      messages: messages,
      presentation: transcriptWindowPresentation,
      conversationIdentity: conversationIdentity,
      isSending: isSending
    )
  }

  private func refreshDuplicateMessageIDs() {
    let refreshed = ChatTranscriptWindow.duplicateIDs(inVisibleWindow: visibleTranscriptMessages)
    if refreshed != duplicateMessageIDs { duplicateMessageIDs = refreshed }
  }

  @ViewBuilder
  private func scrollContent(proxy: ScrollViewProxy) -> some View {
    ScrollView {
      // Keep transcript rows eagerly measured. LazyVStack estimates the heights
      // of off-screen rich Markdown rows; as those rows materialize during a
      // fast gesture, its document height can change by tens of thousands of
      // points and AppKit preserves the wrong visual anchor. The transcript is
      // already capped by ChatTranscriptWindow, so stable geometry is the more
      // important optimization here.
      VStack(spacing: OmiSpacing.lg) {
        loadMoreButton
        messageContent
      }
      // **The transcript owns the assistant mark's gutter, not its host.** The
      // mark is drawn in an overlay offset one gutter to the left of the message
      // column, so a host that insets by less draws it outside itself and the
      // assistant's only identity cue silently vanishes — which is exactly what
      // Home's chat did while passing 0. Asking every caller to know the number
      // made that a bug each of them could reintroduce; clamping here makes it
      // impossible.
      .padding(.leading, leadingContentPadding)
      .padding(.trailing, trailingContentInset)
      .padding(.vertical, verticalContentPadding)
      .frame(maxWidth: .infinity)
      .coordinateSpace(name: ChatTranscriptSpace.content)
      // Do not enable text selection on the whole stack. SelectionOverlay on every
      // chrome Text (agent card headers, tool summaries, timestamps) can peg the
      // main thread in GraphHost layout. Message bodies opt in via OmiMarkdown.
      .background(scrollDetectors)

      // Keep the live-edge anchor outside the message stack so it remains a
      // stable, dedicated target for ScrollViewReader.
      if !messages.isEmpty {
        Color.clear
          .frame(height: 1)
          .id("bottom-anchor")
      }
    }
    // Keep the native indicator policy static. Mutating NSScrollView's scroller
    // visibility from a transcript overlay changes the transcript width, which
    // changes wrapping and geometry, which can re-enter SwiftUI's AttributeGraph
    // layout pass indefinitely on long histories.
    // `.never`, not `.hidden`. Both are static policies, so the reason this
    // stays out of the runtime is unchanged — but `.hidden` only asks, and AppKit
    // still drew the overlay scroller during and after a scroll, on top of the
    // panel's rounded leading/trailing edge. `.never` overrides the scrollable
    // component instead of requesting.
    .scrollIndicators(.never)
    // MARK: - Re-derive duplicate rows when the transcript's shape changes
    .onChange(of: duplicateKey) { _, _ in refreshDuplicateMessageIDs() }
    // MARK: - React to message count changes
    .onChange(of: messages.count) { oldCount, newCount in
      transcriptGeometry.setMessages(visibleTranscriptMessages)
      handleMessagesCountChange(oldCount: oldCount, newCount: newCount, proxy: proxy)
    }
    // Refresh reply previews only once a streamed answer settles. Rebuilding
    // sources for every token would re-walk the entire transcript.
    .onChange(of: messages.last?.isStreaming) { wasStreaming, isStreaming in
      guard wasStreaming == true, isStreaming != true else { return }
      transcriptGeometry.setMessages(visibleTranscriptMessages)
    }
    // A journal restore may be populated by background events while the
    // loader is still collecting its canonical snapshot. Reveal it only after
    // loading completes, then make one initial placement at the live edge.
    .onChange(of: isLoadingInitial) { wasLoading, isLoading in
      guard wasLoading, !isLoading, !messages.isEmpty else { return }
      handleInitialRestore(proxy: proxy)
    }
    // MARK: - React to streaming text changes
    .onChange(of: messages.last?.text) { _, _ in
      handleLiveContentChange(proxy: proxy)
    }
    // MARK: - React to content block changes (tool calls, etc.)
    .onChange(of: messages.last?.contentBlocks.count) { _, _ in
      handleLiveContentChange(proxy: proxy)
    }
    // MARK: - React to local send token (turn anchoring)
    .onChange(of: localSendToken?.generation) { oldGen, newGen in
      guard let newGen = newGen else { return }
      if newGen > lastSeenSendGeneration {
        lastSeenSendGeneration = newGen
        handleLocalSend(proxy: proxy)
      }
    }
    // MARK: - React to isSending (send started)
    .onChange(of: isSending) { oldValue, newValue in
      if newValue && !oldValue && localSendToken == nil {
        // A send is deliberate, so it may reclaim the live edge — but not out
        // from under a reader whose gesture is still in flight. Clearing the
        // latch unconditionally let a send this reader did not make (poll,
        // sync, another surface) teleport them to the bottom mid-scroll.
        guard !userIsScrolling else {
          hasActivityBelow = true
          return
        }
        cancelPendingScrollsForUserInteraction()
        scrollMode = .followingBottom
        hasActivityBelow = false
        scrollToBottom(proxy: proxy)
      }
    }
    // MARK: - React to isLoadingMoreMessages (prepend preservation)
    .onChange(of: isLoadingMoreMessages) { _, isLoading in
      if isLoading {
        capturePrependAnchor()
      } else {
        restorePrependAnchor(proxy: proxy)
      }
    }
    // Expanding a compact mount adds rows above the reader's current context.
    // Reuse the same anchor preservation as server-backed prepends — but not
    // while a server load is still in flight, or the expand would clear the
    // original anchor and recapture the newly revealed oldest row.
    .onChange(of: transcriptWindowPresentation) { _, presentation in
      transcriptGeometry.setMessages(visibleTranscriptMessages)
      guard presentation == .expanded, !isLoadingMoreMessages else { return }
      restorePrependAnchor(proxy: proxy)
    }
    // MARK: - Reset session state on conversation switch
    .onChange(of: conversationIdentity) { _, newId in
      // When the stable conversation identity changes, reset all
      // session-scoped @State so stale tracking doesn't leak across.
      // The decision is delegated to a pure helper so the switch-through-
      // empty transition (A -> nil -> B) is unit-testable and no longer
      // skips the reset for B.
      let transition = ChatConversationSwitch.transition(
        current: trackedConversationId, incoming: newId)
      trackedConversationId = transition.newTracked
      if transition.shouldReset {
        cancelAllPendingScrolls()
        initialRestoreState = .waiting
        lastSeenSendGeneration = localSendToken?.generation ?? 0
        prependAnchorId = nil
        hasActivityBelow = false
        scrollMode = .followingBottom
        userIsScrolling = false
        transcriptGeometry.reset()
        transcriptWindowPresentation = .initial
        prependAnchorId = nil
        prependSnapshot = nil
        isPreservingPrepend = false
        transcriptGeometry.setMessages(visibleTranscriptMessages)
        if !isLoadingInitial, !messages.isEmpty {
          handleInitialRestore(proxy: proxy)
        }
      }
    }
    .onAppear {
      // Product invariant: a presented chat starts at its newest message.
      // Never reuse a completed placement from a prior scroll-view instance;
      // that instance may have been dismissed while the reader was at top.
      cancelAllPendingScrolls()
      initialRestoreState = ChatInitialRestoreState.atPresentationStart(previous: initialRestoreState)
      scrollMode = .followingBottom
      userIsScrolling = false
      hasActivityBelow = false
      trackedConversationId = conversationIdentity
      refreshDuplicateMessageIDs()
      transcriptGeometry.reset()
      transcriptGeometry.setMessages(visibleTranscriptMessages)
      if !isLoadingInitial, !messages.isEmpty {
        handleInitialRestore(proxy: proxy)
      }
    }
    .onDisappear {
      initialRestoreState = ChatInitialRestoreState.afterDisappear(initialRestoreState)
      transcriptWindowPresentation = .initial
      cancelAllPendingScrolls()
    }
  }

  // MARK: - Message Count Change Handler

  /// Central handler for messages.count changes. Handles:
  /// - Initial restore (scroll to latest message on first load)
  /// - New messages arriving while following
  /// - New messages arriving while scrolled away (activity indicator)
  /// - Prepend detection (load earlier)
  private func handleMessagesCountChange(oldCount: Int, newCount: Int, proxy: ScrollViewProxy) {
    // Saved journal rows are not live arrivals. The loading-complete observer
    // above performs their one final placement after the snapshot is visible.
    guard !isLoadingInitial else { return }

    if newCount > oldCount {
      // --- Initial restore: messages went from 0→N ---
      if oldCount == 0 && newCount > 0 {
        handleInitialRestore(proxy: proxy)
        return
      }

      // --- Prepend: new older messages inserted ---
      if prependAnchorId != nil || isPreservingPrepend {
        return
      }

      // --- New live messages arriving ---
      if scrollMode == .followingBottom {
        scrollToBottom(proxy: proxy)
      } else {
        // freeScrolling — new content arrived below
        hasActivityBelow = true
      }
    }
  }

  private func handleLiveContentChange(proxy: ScrollViewProxy) {
    guard !isLoadingInitial else { return }

    switch scrollMode {
    case .followingBottom:
      throttledScrollToBottom(proxy: proxy)
    case .freeScrolling:
      hasActivityBelow = true
    }
  }

  // MARK: - Initial Restore

  /// On the first load of a saved conversation, follow the latest message.
  /// Chat surfaces should open at the live edge; if the reader wants older
  /// context, explicit scroll input switches the mode to free-scrolling.
  private func handleInitialRestore(proxy: ScrollViewProxy) {
    guard initialRestoreState.canStart else { return }

    scrollMode = .followingBottom
    hasActivityBelow = false
    initialRestoreState = .pending

    // The anchor already exists by the time this handler runs in the common
    // case. Try immediately, then retain the settling passes below for rich
    // Markdown that expands across later layout turns.
    scrollToBottom(proxy: proxy)

    let delays = ChatScrollLiveEdge.initialRestoreSettlingDelays
    guard !delays.isEmpty else {
      initialRestoreState = .completed
      return
    }
    for (index, delay) in delays.enumerated() {
      scheduleInitialScroll(
        proxy: proxy,
        delay: delay,
        completesInitialRestore: index == delays.index(before: delays.endIndex)
      )
    }
  }

  // MARK: - Local Send / Turn Anchoring

  /// Called when the local send token increments. Follow the latest message
  /// so the newly inserted user row and streamed assistant response stay in
  /// view unless the user explicitly scrolls away.
  private func handleLocalSend(proxy: ScrollViewProxy) {
    guard !messages.isEmpty else { return }
    // The reader typed and hit send, so following is what they asked for —
    // unless a gesture is genuinely in flight, in which case their hand is
    // still on the trackpad and the viewport is still theirs.
    guard !userIsScrolling else {
      hasActivityBelow = true
      return
    }

    cancelPendingScrollsForUserInteraction()
    scrollMode = .followingBottom
    hasActivityBelow = false
    scrollToBottom(proxy: proxy)
    scheduleInitialScroll(proxy: proxy, delay: 0.1)
  }

  // MARK: - Prepend Preservation

  /// After "Load earlier messages" completes, restore the viewport so the
  /// rows the reader was looking at stay put. Skipped only if they physically
  /// scrolled away *after* the restore window — not for the click that started
  /// the load, which lives inside the transcript and looks like a drag.
  private func restorePrependAnchor(proxy: ScrollViewProxy) {
    let anchorId = prependAnchorId
    let snapshot = prependSnapshot
    prependAnchorId = nil
    prependSnapshot = nil

    guard
      !ChatTranscriptPrependPreservation.shouldAbortRestoreBecauseUserIsScrolling(
        userIsScrolling: userIsScrolling,
        isPreservingPrepend: isPreservingPrepend
      )
    else {
      isPreservingPrepend = false
      return
    }

    let delays = Array(ChatScrollLiveEdge.initialRestoreSettlingDelays.prefix(3))
    let once = RestoreOnce()
    for (index, delay) in delays.enumerated() {
      let isLast = index == delays.index(before: delays.endIndex)
      let work = DispatchWorkItem { [self] in
        if !once.applied,
          let snapshot,
          let scrollView = transcriptGeometry.scrollView,
          ChatTranscriptPrependPreservation.apply(to: scrollView, snapshot: snapshot)
        {
          once.applied = true
        } else if isLast, !once.applied, let anchorId,
          messages.contains(where: { $0.id == anchorId })
        {
          proxy.scrollTo(anchorId, anchor: .top)
        }
        if isLast { isPreservingPrepend = false }
      }
      initialScrollWorkItems.append(work)
      DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
    }
    if delays.isEmpty { isPreservingPrepend = false }
  }

  // MARK: - Scheduled Scrolls

  /// Schedules a delayed bottom scroll that is mode-aware and cancelable.
  private func scheduleInitialScroll(
    proxy: ScrollViewProxy,
    delay: TimeInterval,
    completesInitialRestore: Bool = false
  ) {
    var workItem: DispatchWorkItem?
    workItem = DispatchWorkItem { [self] in
      // Only fire if still following — user may have scrolled during settling
      if scrollMode == .followingBottom {
        scrollToBottom(proxy: proxy)
        if completesInitialRestore, initialRestoreState == .pending {
          initialRestoreState = .completed
        }
      }
      if let workItem {
        initialScrollWorkItems.removeAll { $0 === workItem }
      }
    }
    if let workItem {
      initialScrollWorkItems.append(workItem)
      DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: workItem)
    }
  }

  /// Cancels all pending scheduled scrolls (throttle, initial, user-scroll-end).
  private func cancelAllPendingScrolls() {
    scrollThrottleWorkItem?.cancel()
    scrollThrottleWorkItem = nil
    // The queued run is gone, so the throttle must stop reporting one as
    // pending — otherwise every later request answers `.alreadyScheduled` and
    // the transcript never follows again for this view's lifetime. Written only
    // when it changes: this runs on every scroll event, and an unconditional
    // `@State` write there is a body invalidation per event.
    if hasQueuedFollowScroll { hasQueuedFollowScroll = false }
    userScrollEndWorkItem?.cancel()
    userScrollEndWorkItem = nil
    for item in initialScrollWorkItems {
      item.cancel()
    }
    initialScrollWorkItems.removeAll()
    if ChatTranscriptPrependPreservation.shouldReleasePreserveLatchAfterCancellingRestore(
      isPreservingPrepend: isPreservingPrepend,
      prependAnchorId: prependAnchorId
    ) {
      isPreservingPrepend = false
    }
  }

  /// Explicit reader input cancels launch placement and makes the current
  /// viewport authoritative until the conversation changes.
  private func cancelPendingScrollsForUserInteraction() {
    initialRestoreState = ChatInitialRestoreState.afterUserInteraction(initialRestoreState)
    cancelAllPendingScrolls()
  }

  // MARK: - Subviews

  @ViewBuilder
  private var loadMoreButton: some View {
    let action = ChatTranscriptWindow.earlierAction(
      for: messages,
      policy: effectiveTranscriptWindowPolicy,
      presentation: transcriptWindowPresentation,
      hasMoreMessages: hasMoreMessages
    )
    if action != .none {
      Button {
        capturePrependAnchor()
        if action == .revealLocallyLoadedRows || action == .revealLocallyLoadedRowsAndLoadMore {
          transcriptWindowPresentation = .expanded
        }
        if action == .loadMoreRows || action == .revealLocallyLoadedRowsAndLoadMore {
          Task {
            await onLoadMore()
          }
        }
      } label: {
        if isLoadingMoreMessages {
          ProgressView()
            .scaleEffect(0.8)
        } else {
          Text(action == .loadMoreRows ? "Load earlier messages" : "Show older messages")
            .font(.caption)
            .foregroundColor(.secondary)
        }
      }
      .buttonStyle(.plain)
      .frame(maxWidth: .infinity)
      .padding(.vertical, OmiSpacing.sm)
    }
  }

  @ViewBuilder
  private var messageContent: some View {
    if isLoadingInitial && sessionsLoadError == nil {
      VStack(spacing: OmiSpacing.md) {
        ProgressView()
          .scaleEffect(0.8)
        Text("Loading...")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
      }
      .frame(maxWidth: .infinity)
      .padding(.vertical, 80)
    } else if let error = sessionsLoadError, messages.isEmpty {
      errorContent(error: error)
    } else if messages.isEmpty {
      welcomeContent()
    } else {
      // Streamed tokens re-evaluate this body. Take one bounded snapshot so each
      // token avoids another suffix copy and never scans history that cannot be
      // rendered. Duplicate detection is deliberately *not* here — it is derived
      // from the transcript's shape (`ChatTranscriptDuplicateKey`) rather than
      // re-run on every rewrite of the streaming tail.
      let visibleMessages = visibleTranscriptMessages
      let displayMessages = AgentLifecycleDisplayProjection.project(visibleMessages)
      let finalAssistantMessageID = ChatOmiMarkPlacement.finalAssistantMessageID(in: displayMessages)
      ForEach(Array(displayMessages.enumerated()), id: \.element.id) { index, message in
        ChatBubble(
          message: message,
          app: app,
          showsOmiMark: message.id == finalAssistantMessageID,
          onRate: { rating in
            onRate(message.id, rating)
          },
          onCitationTap: { citation in
            onCitationTap?(citation)
          },
          onOpenInlineCitation: onOpenInlineCitation,
          isDuplicate: duplicateMessageIDs.contains(message.id),
          onCancelTurn: onCancelTurn,
          onOpenAgent: onOpenAgent,
          onOpenAgentRef: onOpenAgentRef,
          chatFirstRichBlockContext: chatFirstRichBlockContext
        )
        .padding(.top, ChatTranscriptLayout.topAdjustment(at: index, in: displayMessages))
        .id(message.id)
        .onGeometryChange(for: CGFloat.self) {
          $0.frame(in: .named(ChatTranscriptSpace.content)).minY
        } action: { minY in
          guard message.sender == .user else { return }
          transcriptGeometry.setRowOffset(minY, for: message.id)
        }
      }
    }
  }

  @ViewBuilder
  private func errorContent(error: String) -> some View {
    VStack(spacing: OmiSpacing.lg) {
      Image(systemName: "exclamationmark.triangle")
        .scaledFont(size: OmiType.hero)
        .foregroundColor(Ink.errorRed)

      Text("Failed to load chats")
        .scaledFont(size: OmiType.subheading, weight: .medium)
        .foregroundColor(Ink.primary)

      Text(error)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .multilineTextAlignment(.center)

      if let onRetry {
        Button(action: onRetry) {
          Text("Try Again")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.sm)
            .glassCard(cornerRadius: PageGlass.chipRadius)
        }
        .buttonStyle(.plain)
      }
    }
    .frame(maxWidth: .infinity)
    .padding(OmiSpacing.section)
    .padding(.vertical, 48)
  }

  // The detector's .background lands its NSView inside NSScrollView.documentView.
  // Keep this instrumentation observational: changing the enclosing scroll view's
  // chrome here feeds geometry back into the transcript layout and can starve the
  // main thread.
  private var scrollDetectors: some View {
    ZStack {
      ScrollPositionDetector { position in
        transcriptGeometry.setContent(
          height: position.documentHeight,
          scrollTop: position.scrollTop
        )
      } onScrollViewResolved: { scrollView in
        transcriptGeometry.scrollView = scrollView
      }
      UserScrollDetector {
        scrollMode = .freeScrolling
        userIsScrolling = true
        hasActivityBelow = false
        transcriptGeometry.setFollowingLiveEdge(false)
        transcriptGeometry.releaseSelection()
        cancelPendingScrollsForUserInteraction()
        let endWork = DispatchWorkItem {
          userIsScrolling = false
        }
        userScrollEndWorkItem = endWork
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3, execute: endWork)
      } onScrollSettledAtBottom: {
        // The detector reports a settle only once the input that produced it
        // genuinely finished: AppKit's `didEndLiveScroll` for wheel/trackpad
        // (momentum included), or the bounded timer for keyboard and scrollbar
        // input. Both are stronger evidence than the wall-clock
        // `userIsScrolling` latch, which exists only to stop programmatic
        // scrolls fighting a gesture still in flight. Consulting the latch here
        // made this resume unreachable: `didEndLiveScroll` delivers on the very
        // next main-thread turn, ~0.3s before the latch clears, so a reader who
        // returned to the live edge could never resume live following.
        userScrollEndWorkItem?.cancel()
        userScrollEndWorkItem = nil
        userIsScrolling = false
        guard
          ChatScrollLiveEdge.canResumeFollowing(
            source: .settledUserScroll,
            isAtBottom: true,
            userIsScrolling: userIsScrolling
          ), scrollMode == .freeScrolling
        else { return }
        cancelAllPendingScrolls()
        scrollMode = .followingBottom
        hasActivityBelow = false
        transcriptGeometry.setFollowingLiveEdge(true)
      }
    }
  }

  @ViewBuilder
  private func scrollToBottomButton(proxy: ScrollViewProxy) -> some View {
    // Show when free-scrolled AND there are messages, AND either there's
    // activity below or we're in a non-following mode.
    if scrollMode == .freeScrolling && !messages.isEmpty {
      let diameter = ChatScrollJumpPlacement.diameter(trailingContentInset: trailingContentInset)
      Button {
        cancelPendingScrollsForUserInteraction()
        userIsScrolling = false
        scrollMode = .followingBottom
        hasActivityBelow = false
        scrollToBottom(proxy: proxy)
        scheduleInitialScroll(proxy: proxy, delay: ChatScrollLiveEdge.explicitJumpSettlingDelay)
      } label: {
        ZStack(alignment: .center) {
          Color.clear
            .frame(width: diameter, height: diameter)
            // A free-floating object over the transcript, so it is real glass
            // with its own ambient shadow rather than a wash on the panel.
            .glassFloatingBar(cornerRadius: diameter / 2)
          Image(systemName: "arrow.down")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.primary)
        }
        // Activity pulse: subtle white glow when new content arrived below
        .overlay(
          Circle()
            .stroke(Ink.secondary.opacity(hasActivityBelow ? 0.6 : 0), lineWidth: 1.5)
        )
        .opacity(hasActivityBelow ? 1.0 : 0.85)
        .scaleEffect(hasActivityBelow ? 1.08 : 1.0)
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Jump to latest message")
      .padding(.bottom, OmiSpacing.lg)
      .padding(
        .trailing,
        ChatScrollJumpPlacement.trailingInset(trailingContentInset: trailingContentInset)
      )
      .transition(.scale.combined(with: .opacity))
      .omiAnimation(.easeInOut(duration: 0.2), value: scrollMode)
      .omiAnimation(.easeInOut(duration: 0.3), value: hasActivityBelow)
    }
  }

  private func scrollToBottom(proxy: ScrollViewProxy) {
    guard scrollMode == .followingBottom else { return }
    // Don't fight the user — skip if they're actively wheel/trackpad scrolling
    guard !userIsScrolling else { return }
    guard !messages.isEmpty else { return }
    transcriptGeometry.setFollowingLiveEdge(true)
    proxy.scrollTo("bottom-anchor", anchor: .bottom)
  }

  /// Rate-limited version of scrollToBottom: at most one follow per
  /// `ChatScrollFollowThrottle.interval`, and **at least** one per window for as
  /// long as content keeps arriving. Cancelling and rescheduling on every change
  /// instead — which is what this used to do — meant a stream flushing faster
  /// than the window never scrolled once.
  private func throttledScrollToBottom(proxy: ScrollViewProxy) {
    guard !userIsScrolling else { return }
    let now = ProcessInfo.processInfo.systemUptime
    switch ChatScrollFollowThrottle.decide(
      now: now, lastRun: lastFollowScrollTime, hasQueuedRun: hasQueuedFollowScroll)
    {
    case .alreadyScheduled:
      return
    case .now:
      lastFollowScrollTime = now
      scrollToBottom(proxy: proxy)
    case .schedule(let delay):
      hasQueuedFollowScroll = true
      let workItem = DispatchWorkItem { [self] in
        hasQueuedFollowScroll = false
        lastFollowScrollTime = ProcessInfo.processInfo.systemUptime
        scrollToBottom(proxy: proxy)
      }
      scrollThrottleWorkItem = workItem
      DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: workItem)
    }
  }
}

/// One-shot latch for delayed prepend restores. A local `Bool` cannot be mutated
/// from the escaping work items that retry across layout turns.
private final class RestoreOnce: @unchecked Sendable {
  var applied = false
}
