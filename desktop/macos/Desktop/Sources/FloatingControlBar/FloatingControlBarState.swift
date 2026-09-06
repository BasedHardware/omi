import Combine
import SwiftUI
import VoiceTurnDomain

/// Message-id pair for one archived floating-bar exchange.
/// Content always resolves from `ChatProvider.messages` — these are viewport anchors only.
struct FloatingChatExchangePair: Equatable {
  var questionMessageId: String?
  var answerMessageId: String?
}

/// Session cursor over the shared chat timeline. Chrome + anchors live here;
/// transcript text lives in `ChatProvider.messages`.
struct FloatingChatViewport: Equatable {
  var activeClientTurnId: String?
  var questionMessageId: String?
  var answerMessageId: String?
  var archivedExchanges: [FloatingChatExchangePair] = []

  var hasAnchors: Bool {
    activeClientTurnId != nil
      || questionMessageId != nil
      || answerMessageId != nil
      || !archivedExchanges.isEmpty
  }

  mutating func archiveCurrentExchange() {
    guard answerMessageId != nil || questionMessageId != nil else { return }
    archivedExchanges.append(
      FloatingChatExchangePair(
        questionMessageId: questionMessageId,
        answerMessageId: answerMessageId
      )
    )
    questionMessageId = nil
    answerMessageId = nil
    activeClientTurnId = nil
  }

  mutating func clear() {
    activeClientTurnId = nil
    questionMessageId = nil
    answerMessageId = nil
    archivedExchanges = []
  }
}

/// Thin view-model derived from provider messages for `AIResponseView`.
/// Not stored as source of truth on floating-bar state.
struct FloatingChatExchange: Identifiable {
  let id: String
  let question: String?
  let questionMessageId: String?
  let aiMessage: ChatMessage

  init(
    id: String? = nil,
    question: String?,
    questionMessageId: String?,
    aiMessage: ChatMessage
  ) {
    self.id = id ?? aiMessage.id
    self.question = question
    self.questionMessageId = questionMessageId
    self.aiMessage = aiMessage
  }
}

enum FloatingConversationSurface: Equatable {
  case closed
  case mainInput
  case mainResponse
  case agent(UUID)

  var isOpen: Bool {
    switch self {
    case .closed: return false
    case .mainInput, .mainResponse, .agent: return true
    }
  }

  var isResponseLike: Bool {
    switch self {
    case .mainResponse, .agent: return true
    case .closed, .mainInput: return false
    }
  }

  var agentID: UUID? {
    guard case .agent(let id) = self else { return nil }
    return id
  }

  var measurementKey: String {
    switch self {
    case .closed: return "closed"
    case .mainInput: return "mainInput"
    case .mainResponse: return "mainResponse"
    case .agent(let id): return "agent:\(id.uuidString)"
    }
  }
}

/// Closing a visible surface is usually a user cancellation. A voice handoff is
/// different: it only collapses the typed surface before routing the already
/// admitted voice turn, so it must leave that turn's physical drivers and
/// reducer-owned lifecycle intact.
enum FloatingConversationCloseIntent: Equatable {
  case userDismissal
  case voiceHandoff

  var cancelsInFlightWork: Bool {
    switch self {
    case .userDismissal: return true
    case .voiceHandoff: return false
    }
  }
}

/// Hover is an idle-only notch presentation. Voice owns the same top-anchored
/// surface while recording, thinking, waiting, or speaking, so the two must
/// never animate their geometry or affordances at the same time.
enum NotchHoverSurfacePolicy {
  static func allowsMenu(
    showingAIConversation: Bool,
    isVoicePresentationActive: Bool,
    isShowingNotification: Bool
  ) -> Bool {
    !showingAIConversation && !isVoicePresentationActive && !isShowingNotification
  }

  static func usesAnimatedHoverSurface(
    usesNotchIsland: Bool,
    showingAIConversation: Bool,
    isVoicePresentationActive: Bool,
    isShowingNotification: Bool
  ) -> Bool {
    usesNotchIsland
      && !showingAIConversation
      && !isVoicePresentationActive
      && !isShowingNotification
  }
}

/// The compact idle notch has an explicit route to the main chat. Its expanded hover
/// surface shows actionable subagents when there are any, and always shows the shortcut
/// legend and capture controls — so hovering the notch is never a no-op.
///
/// The surface was previously agent-only because the rows it carried were duplicate entry
/// points into chat and settings (`FC-split-mutation-authority`). The legend is a
/// read-only reference and the capture toggles route through the single
/// `SystemCaptureControls` owner, so neither reintroduces a second authority.
enum NotchAgentMenuPresentation {
  static func shouldPresent(agentCount: Int) -> Bool {
    true
  }

  /// Whether the agent row list itself has anything to draw.
  static func hasAgentRows(agentCount: Int) -> Bool {
    agentCount > 0
  }
}

/// Hidden provenance carried with a floating-bar notification so follow-up
/// questions can explain where the notification came from without guessing.
struct FloatingBarNotificationContext: Equatable {
  let sourceTitle: String
  let assistantId: String
  let sourceApp: String?
  let windowTitle: String?
  let contextSummary: String?
  let currentActivity: String?
  let reasoning: String?
  let detail: String?
  /// Durable lookup key into `proactive_deliveries`. Unlike the legacy card
  /// context, this survives the old 60-second follow-up window.
  let provenanceRef: String?

  init(
    sourceTitle: String,
    assistantId: String,
    sourceApp: String? = nil,
    windowTitle: String? = nil,
    contextSummary: String? = nil,
    currentActivity: String? = nil,
    reasoning: String? = nil,
    detail: String? = nil,
    provenanceRef: String? = nil
  ) {
    self.sourceTitle = sourceTitle
    self.assistantId = assistantId
    self.sourceApp = sourceApp
    self.windowTitle = windowTitle
    self.contextSummary = contextSummary
    self.currentActivity = currentActivity
    self.reasoning = reasoning
    self.detail = detail
    self.provenanceRef = provenanceRef
  }
}

/// Pure decision for how a persistent card interacts with the notification
/// queue: a newcomer displaces it (the persistent card returns right after)
/// rather than queueing behind a card that has no timeout — otherwise one
/// un-acted persistent card would starve every later proactive notification.
enum FloatingBarNotificationQueuePolicy {
  static func shouldDisplacePersistentCard(
    currentIsPersistent: Bool,
    showingAIConversation: Bool
  ) -> Bool {
    currentIsPersistent && !showingAIConversation
  }

  /// A displaced persistent card rejoins at the TAIL: every notification that
  /// queued while it was visible presents first, and the card — which never
  /// times out — returns once the queue drains, so it can neither be lost nor
  /// starve anything behind it.
  static func requeueIndex(queueCount: Int) -> Int {
    queueCount
  }
}

enum FloatingBarNotificationAction: Equatable {
  case openWhatMattersNow(recommendationID: String)
  /// Offer to connect an integration the user has open but has not set up.
  /// Carries the catalog's telemetry id (`import:email`, `export:notion`, …),
  /// which is unique across both halves of the catalog — the bare connector id
  /// is not, because ChatGPT and Claude exist on both sides. `triggerID` names
  /// what was recognized, so a conversion can be attributed to the native-app
  /// or browser-site trigger that produced the card rather than merged.
  case connectIntegration(telemetryID: String, triggerID: String)
  /// Post-meeting summary share card: carries what the card's buttons need —
  /// the conversation to share and the calendar-detected recipients a
  /// one-click "Send to …" email would go to (empty = no send button).
  case meetingSummaryShare(conversationID: String, recipients: [ConversationShareRecipient])
  /// Open the main chat with `prompt` already in the composer, focused and
  /// **not sent**. Raised by the first-real-app card, whose whole purpose is to
  /// turn a dead-end notch card into the user's first question — they still
  /// press return, so the question stays theirs.
  case askOmiPrefilled(prompt: String)
  /// Place-bound reminder: Done marks it complete, Remind me tomorrow snoozes
  /// until the next calendar day. Bound to the frontmost app/document, not a time.
  case contextReminder(reminderID: String)
}

/// A custom in-app notification rendered directly below the floating bar.
struct FloatingBarNotification: Identifiable, Equatable {
  let id = UUID()
  /// Immutable owner provenance captured before the workflow that produced
  /// this notification crossed an async boundary.
  let ownerID: String
  let title: String
  let message: String
  let assistantId: String
  let kind: ProactiveNotificationKind
  let context: FloatingBarNotificationContext?
  let action: FloatingBarNotificationAction?
  /// Explicit feedback controls for a planned JIT trigger. This is opaque
  /// provenance only; action labels are rendered by the card.
  let jitFeedbackContext: JITTriggerFeedbackContext?
  /// Ambient JIT feedback is delivery-scoped and has no standing trigger.
  let jitAmbientFeedbackContext: JITAmbientFeedbackContext?
  /// Optional opaque proactive-suggestion join keys. No card content or screen
  /// provenance enters notification analytics through this field.
  let suggestionTelemetryIdentity: SuggestionAssistantTelemetry.NotificationIdentity?
  /// Optional opaque Advice delivery key. It is consumed only at the actual
  /// floating-bar presentation boundary and carries no advice or screen content.
  let insightDeliveryID: UUID?
  /// Screenshot JPEG data from the moment the notification was generated (not shown in UI)
  let screenshotData: Data?
  /// A persistent card never times out: it stays presented until the user
  /// acts on it or dismisses it. Reserved for cards whose whole point is an
  /// explicit decision (e.g. the meeting summary share card).
  let isPersistent: Bool

  init(
    ownerID: String,
    title: String,
    message: String,
    assistantId: String,
    kind: ProactiveNotificationKind,
    context: FloatingBarNotificationContext? = nil,
    action: FloatingBarNotificationAction? = nil,
    jitFeedbackContext: JITTriggerFeedbackContext? = nil,
    jitAmbientFeedbackContext: JITAmbientFeedbackContext? = nil,
    suggestionTelemetryIdentity: SuggestionAssistantTelemetry.NotificationIdentity? = nil,
    insightDeliveryID: UUID? = nil,
    screenshotData: Data? = nil,
    isPersistent: Bool = false
  ) {
    self.ownerID = ownerID
    self.title = title
    self.message = message
    self.assistantId = assistantId
    // Required, never derived here. Deriving it from `assistantId` meant every
    // producer that forgot to say what its card was silently became `.general`
    // and journaled a bare `notification:<uuid>` row badged "Notification".
    self.kind = kind
    self.context = context
    self.action = action
    self.jitFeedbackContext = jitFeedbackContext
    self.jitAmbientFeedbackContext = jitAmbientFeedbackContext
    self.suggestionTelemetryIdentity = suggestionTelemetryIdentity
    self.insightDeliveryID = insightDeliveryID
    self.screenshotData = screenshotData
    self.isPersistent = isPersistent
  }

  /// Identity every shown card can write. SuggestionAssistant supplies a real
  /// pair; context-director and other cards synthesize from delivery id / card id
  /// so the ledger is not gated on suggestion-only telemetry.
  var feedbackIdentity: SuggestionAssistantTelemetry.NotificationIdentity {
    if let suggestionTelemetryIdentity { return suggestionTelemetryIdentity }
    let evaluationID =
      insightDeliveryID
      ?? UUID(uuidString: context?.provenanceRef ?? "")
      ?? id
    return SuggestionAssistantTelemetry.NotificationIdentity(
      evaluationID: evaluationID, suggestionID: id)
  }

  static func == (lhs: FloatingBarNotification, rhs: FloatingBarNotification) -> Bool {
    lhs.id == rhs.id
  }
}

/// Observable object holding the state for the floating control bar.
@MainActor
class FloatingControlBarState: NSObject, ObservableObject {
  static let visibleConversationReuseInterval: TimeInterval = 10 * 60

  @Published var isRecording: Bool = false
  @Published var duration: Int = 0
  @Published var isInitialising: Bool = false
  @Published var isDragging: Bool = false
  @Published var isHoveringBar: Bool = false
  @Published var requiresHoverReset: Bool = false
  @Published var currentNotification: FloatingBarNotification? = nil
  /// Visible while PTT is live inside the 60s card-context window.
  @Published var interjectReplyingToTitle: String? = nil
  /// Same hover signal the Interject dismiss timer pauses on. Notch hover
  /// never sets `isHoveringBar`; insight teasers key off this instead.
  @Published var interjectBarHovering: Bool = false

  /// Onboarding-only: pulse a glowing border on the bar so first-run users
  /// notice it. Cleared automatically once they start typing.
  @Published var onboardingBarGlow: Bool = false

  // AI conversation chrome (not transcript content)
  @Published var showingAIConversation: Bool = false
  @Published var showingAIResponse: Bool = false
  @Published var isAILoading: Bool = true
  @Published var aiInputText: String = "" {
    didSet {
      guard !isRestoringAIDraft else { return }
      aiDraftRevision &+= 1
      ChatDraftStore.shared.setText(aiInputText, for: activeAIDraftKey)
    }
  }
  /// Optimistic pending user text shown before/while the provider turn resolves.
  @Published var displayedQuery: String = ""
  @Published var inputViewHeight: CGFloat = 120
  @Published var responseContentHeight: CGFloat = 0
  @Published private(set) var responseContentHeights: [String: CGFloat] = [:]
  /// Viewport cursor over `ChatProvider.messages` — ids only, never a durable transcript copy.
  @Published var chatViewport = FloatingChatViewport()
  /// Bumped when provider message content streams in-place so SwiftUI re-reads derived accessors.
  @Published private(set) var answerStreamToken: String = ""
  /// Local-only answer for ephemeral presentation (usage limit, busy, legacy updateAIResponse)
  /// that is not (yet) on the shared provider timeline.
  @Published private(set) var localAnswerOverride: ChatMessage? = nil
  @Published var lastConversationActivityAt: Date? = nil
  @Published var activeAgentChatPillID: UUID? = nil
  @Published var conversationSurface: FloatingConversationSurface = .closed
  private var activeAIDraftKey = ChatDraftKey.floatingMain
  private var isRestoringAIDraft = false
  private var aiDraftRevision: UInt64 = 0
  private var submittedAIDraft: (key: ChatDraftKey, text: String, revision: UInt64)?

  override init() {
    super.init()
    isRestoringAIDraft = true
    aiInputText = ChatDraftStore.shared.text(for: activeAIDraftKey)
    isRestoringAIDraft = false
  }

  /// The sole bridge from reducer state into floating-bar voice presentation.
  /// Keeping the presenter nested lets `applyVoiceProjection` remain private,
  /// so no capture, window, onboarding, or automation caller can mutate the
  /// rendered voice state independently.
  @MainActor
  final class PTTBarPresenter {
    private weak var barState: FloatingControlBarState?
    private let resizeForPTT: @MainActor (Bool) -> Void

    init(
      barState: FloatingControlBarState,
      resizeForPTT: @escaping @MainActor (Bool) -> Void
    ) {
      self.barState = barState
      self.resizeForPTT = resizeForPTT
    }

    func apply(_ projection: VoiceTurnUIProjection) {
      guard let barState else { return }
      let wasExpandedForVoice = barState.isVoiceListening
      barState.applyVoiceProjection(projection)
      let shouldExpandForVoice = barState.isVoiceListening

      // Clear idle hover before the PTT resize so its animated surface cannot
      // compete with the reducer-owned voice presentation.
      barState.dismissNotchHoverForVoicePresentation()

      // Onboarding uses this same renderer. Its PTT demo must receive the
      // same surface transition as a completed user's first voice turn.
      if shouldExpandForVoice != wasExpandedForVoice,
        !barState.showingAIConversation
      {
        resizeForPTT(shouldExpandForVoice)
      }
    }
  }

  /// Onboarding demos reuse the real floating window but must not overwrite the
  /// user's normal notch draft. Switching scopes restores each independently.
  func switchAIDraft(to key: ChatDraftKey) {
    guard key != activeAIDraftKey else { return }
    activeAIDraftKey = key
    aiDraftRevision &+= 1
    isRestoringAIDraft = true
    aiInputText = ChatDraftStore.shared.text(for: key)
    isRestoringAIDraft = false
  }

  func markAIDraftSubmitted(_ text: String) {
    submittedAIDraft = (activeAIDraftKey, text, aiDraftRevision)
  }

  func clearSubmittedAIDraftIfUnchanged(_ text: String) {
    guard let submittedAIDraft,
      submittedAIDraft.key == activeAIDraftKey,
      submittedAIDraft.text == text,
      submittedAIDraft.revision == aiDraftRevision,
      aiInputText == text
    else { return }
    self.submittedAIDraft = nil
    aiInputText = ""
  }

  /// Subagent switcher visibility state, shared by both display modes.
  /// On notched displays the menu opens on hover over the notch; on
  /// non-notched displays it opens pinned via an explicit click on the
  /// pill's agents affordance. Mirrored from the SwiftUI view so the
  /// window can account for an expanded switcher when resizing.
  @Published var agentSwitcherPinned: Bool = false
  @Published var agentSwitcherHovering: Bool = false
  var isAgentSwitcherExpanded: Bool { agentSwitcherPinned || agentSwitcherHovering }
  @Published private(set) var notchHoverMenuOpen: Bool = false
  var canShowNotchHoverMenu: Bool {
    NotchHoverSurfacePolicy.allowsMenu(
      showingAIConversation: showingAIConversation,
      isVoicePresentationActive: isVoicePresentationActive,
      isShowingNotification: isShowingNotification
    )
  }
  var isNotchHoverMenuVisible: Bool {
    canShowNotchHoverMenu && notchHoverMenuOpen
  }

  func setNotchHoverMenuOpen(_ open: Bool) {
    notchHoverMenuOpen = open
    isHoveringBar = open
    agentSwitcherHovering = open
    if !open {
      agentSwitcherPinned = false
    }
  }

  /// Voice presentation owns the notch from recording through response playback.
  /// Retaining hover state across that handoff leaves a stale morph underneath it.
  func dismissNotchHoverForVoicePresentation() {
    guard isVoicePresentationActive, notchHoverMenuOpen else { return }
    setNotchHoverMenuOpen(false)
  }

  /// Convenience for call sites that previously used a stored question id.
  var currentQuestionMessageId: String? {
    get { chatViewport.questionMessageId }
    set {
      var viewport = chatViewport
      viewport.questionMessageId = newValue
      chatViewport = viewport
    }
  }

  // Push-to-talk presentation is one atomic reducer projection. Individual
  // fields are read-only derivations so observers cannot see or create a
  // partially applied voice state.
  @Published private(set) var voiceProjection = VoiceTurnUIProjection.idle
  var isVoiceListening: Bool {
    voiceProjection.isListening || !voiceProjection.hint.isEmpty
  }
  var isVoiceLocked: Bool { voiceProjection.isLocked }
  var voiceTranscript: String { voiceProjection.transcript }
  /// Transient inline status shown only for actionable PTT failures.
  var pttHintText: String { VoiceTurnUICopy.statusBannerText(for: voiceProjection) }
  var isVoiceResponseActive: Bool { voiceProjection.isResponseActive }
  var isVoiceResponseWaiting: Bool { voiceProjection.isResponseWaiting }
  /// The current hold has been recognised as a dictation.
  var isVoiceDictating: Bool { voiceProjection.isDictating }
  /// True while a committed Push-to-Talk query is being processed and no
  /// response output (voice glow or conversation surface) has surfaced yet.
  /// Drives the notch/pill "thinking" animation.
  var isThinking: Bool { voiceProjection.isThinking }
  var isVoiceResponseGlowActive: Bool {
    isVoiceResponseActive || isVoiceResponseWaiting
  }
  /// Any reducer-owned voice phase that reserves the notch surface.
  var isVoicePresentationActive: Bool {
    isVoiceListening || isThinking || isVoiceResponseGlowActive || !pttHintText.isEmpty
  }
  /// True only when the notch-mode setting is enabled and the current display
  /// exposes a real camera housing safe area. External displays keep old pill UI.
  @Published var usesNotchIsland: Bool = false
  @Published var notchRevealProgress: CGFloat = 1

  private func applyVoiceProjection(_ projection: VoiceTurnUIProjection) {
    voiceProjection = projection
  }

  /// Whether the current query originated from voice (PTT). Used to decide
  /// whether voice responses should play for this particular query.
  @Published var currentQueryFromVoice: Bool = false

  // Model selection
  @Published var selectedModel: String = ModelQoS.Claude.defaultSelection

  /// Available models for the floating bar picker (driven by QoS tier)
  static var availableModels: [(id: String, label: String)] { ModelQoS.Claude.availableModels }

  var isShowingNotification: Bool {
    currentNotification != nil
  }

  var hasMainConversation: Bool {
    chatViewport.hasAnchors || localAnswerOverride != nil || !displayedQuery.isEmpty
  }

  var hasVisibleConversation: Bool {
    conversationSurface.isOpen || activeAgentChatPillID != nil || hasMainConversation
  }

  var canRestoreVisibleConversation: Bool {
    guard hasVisibleConversation, let lastConversationActivityAt else { return false }
    return Date().timeIntervalSince(lastConversationActivityAt) <= Self.visibleConversationReuseInterval
  }

  /// True when a restored viewport should re-subscribe to provider streaming
  /// for the active turn (mid-stream close → reopen within the reuse window).
  static func shouldReobserveStreamingTurn(
    activeClientTurnId: String?,
    answerMessage: ChatMessage?
  ) -> Bool {
    guard let turnId = activeClientTurnId?.trimmingCharacters(in: .whitespacesAndNewlines),
      !turnId.isEmpty,
      let answerMessage,
      answerMessage.isStreaming,
      answerMessage.clientTurnId == turnId
    else { return false }
    return true
  }

  /// Resolve the current answer from the shared provider timeline (or local override).
  /// Provider-bound answers always win over `localAnswerOverride` so the shared
  /// timeline remains source of truth once an answer id is anchored.
  func currentAIMessage(from provider: ChatProvider?) -> ChatMessage? {
    if let answerId = chatViewport.answerMessageId,
      let provider,
      let message = AgentLifecycleDisplayProjection.projectedMessage(
        id: answerId,
        in: provider.messages
      )
    {
      return message
    }
    if let localAnswerOverride { return localAnswerOverride }
    guard let provider else { return nil }
    if let turnId = chatViewport.activeClientTurnId,
      let message = provider.messages.last(where: {
        $0.clientTurnId == turnId && $0.sender == .ai
      })
    {
      return AgentLifecycleDisplayProjection.projectedMessage(
        id: message.id,
        in: provider.messages
      )
    }
    return nil
  }

  func aiResponseText(from provider: ChatProvider?) -> String {
    currentAIMessage(from: provider)?.text ?? ""
  }

  /// True when a message has user-visible answer payload (plain text, structured
  /// blocks, or resources). Block-only / resource-only answers are not empty.
  static func messageHasAnswerContent(_ message: ChatMessage) -> Bool {
    !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      || !message.contentBlocks.isEmpty
      || !message.resources.isEmpty
  }

  /// Provider-bound answer with visible content (text, contentBlocks, or resources).
  func hasProviderBackedAnswerContent(from provider: ChatProvider?) -> Bool {
    guard let answerId = chatViewport.answerMessageId,
      let message = provider?.messages.first(where: { $0.id == answerId })
    else { return false }
    return Self.messageHasAnswerContent(message)
  }

  /// Post-send empty-response path: only fail when there is no provider-backed
  /// answer and no visible content. Never treat a bound provider answer as a
  /// failure (calling `setLocalAnswerOverride` would clear the answer id).
  func shouldPresentEmptyResponseFailure(from provider: ChatProvider?) -> Bool {
    if let answerId = chatViewport.answerMessageId,
      provider?.messages.contains(where: { $0.id == answerId }) == true
    {
      return false
    }
    guard let message = currentAIMessage(from: provider) else { return true }
    return !Self.messageHasAnswerContent(message)
  }

  /// Resources visible in the floating/notch viewport — only those owned by
  /// viewport-anchored message ids (INV-6: no orphan historical artifacts).
  func viewportDisplayResources(from provider: ChatProvider?) -> [ChatResource] {
    guard let provider else { return [] }
    var ids = Set<String>()
    if let answerId = chatViewport.answerMessageId { ids.insert(answerId) }
    if let questionId = chatViewport.questionMessageId { ids.insert(questionId) }
    for pair in chatViewport.archivedExchanges {
      if let questionId = pair.questionMessageId { ids.insert(questionId) }
      if let answerId = pair.answerMessageId { ids.insert(answerId) }
    }
    // A terminal-only agent completion can be folded into the producing row by
    // the shared display projection. Resolve the viewport anchors through that
    // projection before collecting resources so the notch follows the same row
    // and artifact cards as the main transcript.
    let viewportMessages = ids.compactMap {
      AgentLifecycleDisplayProjection.projectedMessage(id: $0, in: provider.messages)
    }
    return ChatContinuityInvariants.resourcesBelongingToMessages(
      messages: viewportMessages,
      messageIds: Set(viewportMessages.map(\.id))
    )
  }

  /// Build archived exchanges as a thin view-model from ids + provider messages.
  func derivedChatHistory(from provider: ChatProvider?) -> [FloatingChatExchange] {
    guard let provider else { return [] }
    return chatViewport.archivedExchanges.compactMap { pair in
      guard let answerId = pair.answerMessageId,
        let aiMessage = AgentLifecycleDisplayProjection.projectedMessage(
          id: answerId,
          in: provider.messages
        )
      else { return nil }
      let question: String?
      if let questionId = pair.questionMessageId,
        let questionMessage = provider.messages.first(where: { $0.id == questionId })
      {
        question = questionMessage.text
      } else {
        question = nil
      }
      return FloatingChatExchange(
        id: answerId,
        question: question,
        questionMessageId: pair.questionMessageId,
        aiMessage: aiMessage
      )
    }
  }

  /// Synced message ids for share/rate, in chat order.
  func syncedShareMessageIds(from provider: ChatProvider?) -> [String] {
    guard let provider else { return [] }
    var messageIds: [String] = []
    for pair in chatViewport.archivedExchanges {
      if let questionId = pair.questionMessageId,
        provider.messages.contains(where: { $0.id == questionId && $0.isSynced })
      {
        messageIds.append(questionId)
      }
      if let answerId = pair.answerMessageId,
        provider.messages.contains(where: { $0.id == answerId && $0.isSynced })
      {
        messageIds.append(answerId)
      }
    }
    if let questionId = chatViewport.questionMessageId,
      provider.messages.contains(where: { $0.id == questionId && $0.isSynced })
    {
      messageIds.append(questionId)
    }
    if let answerId = chatViewport.answerMessageId,
      provider.messages.contains(where: { $0.id == answerId && $0.isSynced })
    {
      messageIds.append(answerId)
    }
    return messageIds.reduce(into: [String]()) { ids, messageId in
      if !ids.contains(messageId) {
        ids.append(messageId)
      }
    }
  }

  func beginTurn(clientTurnId: String) {
    localAnswerOverride = nil
    var viewport = chatViewport
    viewport.activeClientTurnId = clientTurnId
    viewport.questionMessageId = nil
    viewport.answerMessageId = nil
    chatViewport = viewport
    answerStreamToken = ""
  }

  /// Clear the current answer/question cursor without archiving or wiping prior exchanges.
  func clearCurrentAnswerAnchors() {
    localAnswerOverride = nil
    var viewport = chatViewport
    viewport.activeClientTurnId = nil
    viewport.questionMessageId = nil
    viewport.answerMessageId = nil
    chatViewport = viewport
    answerStreamToken = ""
  }

  func bindAnswerMessage(_ message: ChatMessage) {
    localAnswerOverride = nil
    var viewport = chatViewport
    viewport.answerMessageId = message.id
    if let turnId = message.clientTurnId {
      viewport.activeClientTurnId = turnId
    }
    chatViewport = viewport
    answerStreamToken = [
      message.id,
      message.text,
      String(message.isStreaming),
      String(message.contentBlocks.count),
      message.contentBlocks.map(\.blockIdentity).joined(separator: ","),
    ].joined(separator: "\u{1F}")
  }

  func bindQuestionMessageId(_ messageId: String?) {
    var viewport = chatViewport
    viewport.questionMessageId = messageId
    chatViewport = viewport
  }

  /// Ephemeral UI-only answer (usage limit, busy, synthetic errors with no
  /// provider message). Not for provider-backed answers — those must
  /// `bindAnswerMessage` instead. Setting a non-nil override drops the answer
  /// id so the ephemeral message is visible; if an answer id is later bound
  /// while an override remains, `currentAIMessage` prefers the provider.
  func setLocalAnswerOverride(_ message: ChatMessage?) {
    if message != nil, chatViewport.answerMessageId != nil {
      var viewport = chatViewport
      viewport.answerMessageId = nil
      chatViewport = viewport
    }
    localAnswerOverride = message
    if let message {
      answerStreamToken = "local:\(message.id):\(message.text)"
    }
  }

  func appendLocalAnswerText(_ text: String) {
    var message = localAnswerOverride ?? ChatMessage(text: "", sender: .ai)
    message.text += text
    setLocalAnswerOverride(message)
  }

  func replaceLocalAnswerText(_ text: String) {
    var message = localAnswerOverride ?? ChatMessage(text: "", sender: .ai)
    message.text = text
    setLocalAnswerOverride(message)
  }

  /// Archive the current exchange as message-id anchors (not ChatMessage copies).
  func archiveCurrentExchange(using provider: ChatProvider?) {
    if chatViewport.answerMessageId == nil,
      let message = currentAIMessage(from: provider),
      Self.messageHasAnswerContent(message)
    {
      bindAnswerMessage(message)
    }
    guard chatViewport.answerMessageId != nil || chatViewport.questionMessageId != nil else {
      return
    }
    if let answerId = chatViewport.answerMessageId,
      let provider,
      let message = provider.messages.first(where: { $0.id == answerId }),
      !Self.messageHasAnswerContent(message)
    {
      return
    }
    if localAnswerOverride != nil, chatViewport.answerMessageId == nil {
      // Ephemeral local answers with no provider id are not durable.
      localAnswerOverride = nil
      return
    }
    var viewport = chatViewport
    viewport.archiveCurrentExchange()
    chatViewport = viewport
    localAnswerOverride = nil
    answerStreamToken = ""
  }

  func clearViewport() {
    chatViewport = FloatingChatViewport()
    localAnswerOverride = nil
    answerStreamToken = ""
    displayedQuery = ""
  }

  func markConversationActivity(at date: Date = Date()) {
    lastConversationActivityAt = date
  }

  func present(_ surface: FloatingConversationSurface) {
    conversationSurface = surface
    activeAgentChatPillID = surface.agentID
    showingAIConversation = surface.isOpen
    showingAIResponse = surface.isResponseLike
    markConversationActivity()
  }

  func leaveAgentSurface() {
    activeAgentChatPillID = nil
    let nextSurface: FloatingConversationSurface = hasMainConversation ? .mainResponse : .mainInput
    present(nextSurface)
  }

  func hideConversationSurface() {
    // Cancel in-flight work before resetting process flags so UI state and
    // active response/follow-up workflows stay in sync. Without this, a
    // streaming response or PTT follow-up keeps running after its UI flags
    // are cleared, and late-arriving chunks update a surface nobody sees.
    // (Cubic P2 — presentation/process desync.)
    FloatingControlBarManager.shared.cancelChat()
    // cancelListening() is already guarded by state != .idle.
    PushToTalkManager.shared.cancelListening()
    activeAgentChatPillID = nil
    conversationSurface = .closed
    showingAIConversation = false
    showingAIResponse = false
    isAILoading = false
    markConversationActivity()
  }

  func reportContentHeight(_ height: CGFloat, for surface: FloatingConversationSurface) {
    guard height > 0, conversationSurface == surface else { return }
    let measuredHeight = (height * 2).rounded(.up) / 2
    let key = surface.measurementKey
    if let previousHeight = responseContentHeights[key],
      abs(previousHeight - measuredHeight) < 0.5
    {
      return
    }
    responseContentHeights[key] = measuredHeight
    if surface == .mainResponse {
      responseContentHeight = measuredHeight
    }
  }

  func measuredContentHeight(for surface: FloatingConversationSurface) -> CGFloat? {
    responseContentHeights[surface.measurementKey]
  }

  func resetMeasuredContentHeight(for surface: FloatingConversationSurface) {
    responseContentHeights.removeValue(forKey: surface.measurementKey)
    if surface == .mainResponse {
      responseContentHeight = 0
    }
  }

  func clearVisibleConversation(cancelInFlightWork: Bool = true) {
    // When cancelInFlightWork is true (default), cancel in-flight chat
    // streaming and PTT capture before resetting UI flags. This is needed
    // from close/restore/notification paths where stale streams and mic
    // capture should be stopped. (Cubic P2.)
    //
    // Callers that only need a UI reset (e.g. openAIInputWithQuery, which
    // already cancelled its own subscriptions and is about to route a new
    // typed query) pass cancelInFlightWork: false to avoid killing a
    // provider session that the new query depends on. (Cubic P2 — semantic
    // mismatch between method name and hard-cancellation side effects.)
    if cancelInFlightWork {
      FloatingControlBarManager.shared.cancelChat()
      PushToTalkManager.shared.cancelListening()
    }
    activeAgentChatPillID = nil
    conversationSurface = .closed
    responseContentHeights = [:]
    responseContentHeight = 0
    aiInputText = ""
    clearViewport()
    showingAIConversation = false
    showingAIResponse = false
    isAILoading = false
    currentQueryFromVoice = false
    lastConversationActivityAt = nil
  }

}

extension ChatContentBlock {
  fileprivate var blockIdentity: String {
    switch self {
    case .text(let id, _): return "t:\(id)"
    case .toolCall(let id, let name, let status, _, _, _): return "c:\(id):\(name):\(status)"
    case .thinking(let id, _): return "h:\(id)"
    case .discoveryCard(let id, _, _, _): return "d:\(id)"
    case .questionCard(let id, _, _, _, _, _, _): return "q:\(id)"
    case .taskCard(let id, _): return "t:\(id)"
    case .goalLink(let id, _, _): return "g:\(id)"
    case .captureLink(let id, _, _, _): return "c:\(id)"
    case .conversationLink(let id, _, _, _): return "v:\(id)"
    case .memoryLink(let id, _, _): return "m:\(id)"
    case .memoryReviewCard(let id, _, _, let items): return "mr:\(id):\(items.count)"
    case .citation(let id, let reference): return "r:\(id):\(reference.ordinal)"
    case .followUp(let id, let text): return "f:\(id):\(text.count)"
    case .agentSpawn(let id, let pillId, _, _, _, _, _): return "s:\(id):\(pillId?.uuidString ?? "")"
    case .agentCompletion(let id, let pillId, _, _, _, _, _, _): return "a:\(id):\(pillId?.uuidString ?? "")"
    }
  }
}
