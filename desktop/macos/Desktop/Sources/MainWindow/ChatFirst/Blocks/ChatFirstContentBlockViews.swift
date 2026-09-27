import AppKit
import OmiTheme
import SwiftUI

// MARK: - Question card

/// Choices are controls only while the kernel-backed parent is the completed
/// tail of Main Chat. The runtime remains authoritative at selection time;
/// this view's gate simply avoids presenting obsolete choices as actionable.
/// Whether a question card's options are pressable, dimmed, or gone.
///
/// Three different situations used to collapse into one boolean, and the losing
/// two both rendered as "no options at all": a question already answered (right),
/// a question whose turn is no longer the tail (right), and a question on an
/// account whose capability has not resolved (wrong — that reader saw a question
/// with no visible answers and no explanation).
enum ChatFirstQuestionCardOptionsPolicy: Equatable {
  case hidden
  case enabled
  case disabled

  static func presentation(
    isActionable: Bool,
    isCapabilityAvailable: Bool,
    hasSelection: Bool,
    hasOptions: Bool
  ) -> Self {
    guard hasOptions, !hasSelection else { return .hidden }
    if isActionable { return .enabled }
    // Capability-off is the only reason to show unpressable options: the
    // question is live, we simply cannot answer it yet.
    return isCapabilityAvailable ? .hidden : .disabled
  }

  var isVisible: Bool { self != .hidden }
  var isPressable: Bool { self == .enabled }
}

struct QuestionCardView: View {
  private struct Option: Identifiable {
    let id: String
    let label: String
    let isDeferral: Bool

    init?(_ dictionary: [String: Any]) {
      guard let id = dictionary["optionId"] as? String,
        !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
        let label = dictionary["label"] as? String,
        !label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      else { return nil }
      self.id = id
      self.label = label
      self.isDeferral = dictionary["defer"] as? Bool ?? false
    }
  }

  let questionID: String
  let text: String
  let options: [[String: Any]]
  let selectedOptionID: String?
  let isActionable: Bool
  /// False while the server-owned capability has not resolved, or for an account
  /// it does not cover. The options still render — a question with its answers
  /// hidden reads as a question nobody asked — but they cannot be pressed.
  let isCapabilityAvailable: Bool
  let onSelect: (String, Bool) -> Void

  private var validOptions: [Option] { options.compactMap(Option.init) }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Label("Question", systemImage: "questionmark.circle")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundStyle(Ink.secondary)

      Text(text)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

      // A completed question remains useful transcript context, but its
      // suggestions disappear as soon as an answer exists or another bubble
      // has taken the tail. We never leave stale chips that look tappable.
      //
      // Capability-off is the one case that shows the chips *without* making
      // them pressable: the question is real and its answers are the only thing
      // that explains it, so they are dimmed rather than deleted.
      let optionsPresentation = ChatFirstQuestionCardOptionsPolicy.presentation(
        isActionable: isActionable,
        isCapabilityAvailable: isCapabilityAvailable,
        hasSelection: selectedOptionID != nil,
        hasOptions: !validOptions.isEmpty
      )
      if optionsPresentation.isVisible {
        FlowLayout(spacing: OmiSpacing.sm) {
          ForEach(validOptions) { option in
            Button {
              onSelect(option.id, option.isDeferral)
            } label: {
              Text(option.label)
                .scaledFont(size: OmiType.caption, weight: .medium)
                .foregroundStyle(Ink.secondary)
                .padding(.horizontal, OmiSpacing.md)
                .padding(.vertical, OmiSpacing.sm)
                .glassChip()
            }
            .buttonStyle(.plain)
            .disabled(!optionsPresentation.isPressable)
            .opacity(optionsPresentation.isPressable ? 1 : 0.45)
            .accessibilityLabel("Send suggestion: \(option.label)")
            .accessibilityIdentifier("chat-first-question-\(questionID)-option-\(option.id)")
          }
        }

        if !optionsPresentation.isPressable {
          Text("Answering is unavailable right now")
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
            .accessibilityIdentifier("chat-first-question-\(questionID)-unavailable")
        }
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Ink.rowFill)
    .clipShape(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous))
    .overlay(
      RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous)
        .stroke(Ink.glassEdge, lineWidth: 1)
    )
    .accessibilityElement(children: .contain)
    .accessibilityIdentifier("chat-first-question-\(questionID)")
    .onAppear {
      AnalyticsManager.shared.chatFirst(
        .richBlock(kind: .questionCard, outcome: .rendered, action: .none)
      )
      AnalyticsManager.shared.chatFirst(.question(lifecycle: .shown))
    }
    .onChange(of: isActionable) { wasActionable, nowActionable in
      guard wasActionable, !nowActionable, selectedOptionID == nil else { return }
      AnalyticsManager.shared.chatFirst(.question(lifecycle: .retiredUnseen))
    }
  }
}

// MARK: - Task card

struct TaskCardView: View {
  let taskID: String
  @ObservedObject private var tasksStore: TasksStore
  let navigation: ChatFirstShellNavigation

  @State private var isToggling = false
  @State private var showCompletionAcknowledgement = false
  @State private var hydrationFinished = false
  @State private var retainedCompletedTask: TaskActionItem?
  /// The completion the reader performed on this card, kept whatever the store
  /// says afterwards. See `ChatFirstTaskCardPresentation.displayTask`.
  @State private var locallyCompletedTask: TaskActionItem?

  init(taskID: String, tasksStore: TasksStore, navigation: ChatFirstShellNavigation) {
    self.taskID = taskID
    _tasksStore = ObservedObject(wrappedValue: tasksStore)
    self.navigation = navigation
  }

  private var liveTask: TaskActionItem? {
    tasksStore.tasks.first { $0.id == taskID && !$0.isRetired }
  }

  private var isExplicitlyRetired: Bool {
    (tasksStore.tasks + tasksStore.deletedTasks).contains { $0.id == taskID && $0.isRetired }
  }

  /// The store's row for this card, retired or not.
  ///
  /// `liveTask` is a presentation filter, so it answers nil for a retired row —
  /// which made it the wrong thing to reconcile a toggle against. Completing a
  /// task whose local row carried a stale tombstone read back as "the mutation
  /// did not land", and the card retired itself over the reader's own tick.
  private var storeRecord: TaskActionItem? {
    tasksStore.tasks.first { $0.id == taskID }
  }

  private var task: TaskActionItem? {
    ChatFirstTaskCardPresentation.displayTask(
      liveTask: liveTask,
      retainedCompletedTask: retainedCompletedTask?.id == taskID ? retainedCompletedTask : nil,
      locallyCompletedTask: locallyCompletedTask?.id == taskID ? locallyCompletedTask : nil
    )
  }

  private var hydrationKey: String {
    "\(taskID):\(liveTask == nil)"
  }

  // The body's branches are extracted so release optimization can type-check
  // each in reasonable time; the whole expression as one literal timed out the
  // compiler ("unable to type-check this expression in reasonable time").
  var body: some View {
    Group {
      if let task {
        renderedCard(task)
      } else if hydrationFinished {
        unavailableBlock
      } else {
        ChatFirstLoadingBlockView(entityName: "Task")
      }
    }
    .accessibilityIdentifier("chat-first-task-\(taskID)")
    .onChange(of: liveTask) { _, updatedTask in
      retainCompletedTaskIfNeeded(updatedTask)
    }
    .onChange(of: isExplicitlyRetired) { _, retired in
      if retired {
        retainedCompletedTask = nil
      }
    }
    .task(id: hydrationKey) {
      guard liveTask == nil else {
        hydrationFinished = true
        return
      }
      if retainedCompletedTask == nil {
        hydrationFinished = false
      }
      let resolvedTask = await tasksStore.resolveCanonicalTask(id: taskID)
      switch ChatFirstTaskCardHydration.resolution(
        isCancelled: Task.isCancelled, hasLiveTask: liveTask != nil)
      {
      case .abandon:
        return
      case .settle:
        // The toggle won the race and put the task back in the store. That is
        // a better answer than this hydration's, so take it.
        retainCompletedTaskIfNeeded(liveTask)
        hydrationFinished = true
      case .adopt:
        if resolvedTask == nil {
          log("TaskCardView: \(taskID) hydrated to nothing — the store cannot vouch for this task")
        }
        // A store that cannot vouch for the row is not the same as a row the
        // user retired, and only the second is grounds for taking a card away.
        // `.onChange(of: isExplicitlyRetired)` is the one clearer.
        retainCompletedTaskIfNeeded(resolvedTask)
        hydrationFinished = true
      }
    }
  }

  private func renderedCard(_ task: TaskActionItem) -> some View {
    card(task)
      .onAppear {
        retainCompletedTaskIfNeeded(liveTask)
        AnalyticsManager.shared.chatFirst(
          .richBlock(kind: .taskCard, outcome: .rendered, action: .none)
        )
      }
  }

  private var unavailableBlock: some View {
    ChatFirstUnavailableBlockView(entityName: "Task")
      .onAppear {
        log(unavailableDescription)
        AnalyticsManager.shared.chatFirst(
          .richBlock(kind: .taskCard, outcome: .stalePlaceholder, action: .none)
        )
      }
  }

  private var unavailableDescription: String {
    "TaskCardView: \(taskID) unavailable"
      + " store=\(tasksStore.tasks.count)"
      + " incomplete=\(tasksStore.incompleteTasks.count)"
      + " completed=\(tasksStore.completedTasks.count)"
      + " deleted=\(tasksStore.deletedTasks.count)"
      + " present=\(tasksStore.tasks.contains { $0.id == taskID })"
      + " retiredHere=\(isExplicitlyRetired)"
      + " retained=\(retainedCompletedTask?.id ?? "none")"
  }

  @ViewBuilder
  private func card(_ task: TaskActionItem) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(spacing: OmiSpacing.xs) {
        Label("Task", systemImage: "checklist")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(Ink.secondary)
      }

      HStack(alignment: .center, spacing: OmiSpacing.md) {
        Button {
          toggle(task)
        } label: {
          ZStack {
            Image(systemName: task.completed ? "checkmark.circle.fill" : "circle")
              .scaledFont(size: OmiType.subheading, weight: .medium)
              .foregroundStyle(task.completed ? Ink.listeningGreen : Ink.secondary)

            if showCompletionAcknowledgement {
              Image(systemName: "checkmark")
                .scaledFont(size: OmiType.caption, weight: .bold)
                .foregroundStyle(Ink.listeningGreen)
                .transition(.scale.combined(with: .opacity))
            }
          }
          .frame(width: 24, height: 24)
        }
        .buttonStyle(.plain)
        .disabled(isToggling)
        .accessibilityLabel(
          task.completed ? "Mark \(task.description) incomplete" : "Mark \(task.description) complete"
        )
        .accessibilityIdentifier("chat-first-task-\(taskID)-toggle")

        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          Text(task.description)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundStyle(task.completed ? Ink.secondary : Ink.primary)
            .strikethrough(task.completed, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)

          HStack(spacing: OmiSpacing.xs) {
            if let goalID = task.goalId, !goalID.isEmpty {
              ChatFirstDestinationBadge(
                title: "Goal",
                systemImage: "target",
                accessibilityID: "chat-first-task-\(taskID)-goal-\(goalID)"
              ) {
                navigation.open(focus: .goal(id: goalID))
              }
            }
            if let conversationID = ChatFirstCaptureLinkPolicy.captureID(for: task) {
              ChatFirstDestinationBadge(
                title: "Capture",
                systemImage: "waveform",
                accessibilityID: "chat-first-task-\(taskID)-capture-\(conversationID)"
              ) {
                navigation.open(focus: .capture(id: conversationID, momentTs: nil))
              }
            }
          }
        }
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Ink.rowFill)
    .clipShape(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous))
    .overlay(
      RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous)
        .stroke(Ink.glassEdge, lineWidth: 1)
    )
  }

  private func retainCompletedTaskIfNeeded(_ task: TaskActionItem?) {
    guard let task else { return }
    retainedCompletedTask = task.completed && !task.isRetired ? task : nil
  }

  private func toggle(_ task: TaskActionItem) {
    guard !isToggling else { return }
    let intendedCompletion = !task.completed
    isToggling = true
    AnalyticsManager.shared.chatFirst(
      .richBlock(kind: .taskCard, outcome: .acted, action: .toggle)
    )
    AnalyticsManager.shared.chatFirst(
      .taskMutation(lifecycle: .attempt, mutation: .completion)
    )

    Task { @MainActor in
      await tasksStore.toggleTask(task)
      isToggling = false

      let reconciledTask = self.storeRecord
      // The reader ticked this card and the store took the mutation. That is
      // the answer the card shows from here on: a retirement discovered
      // afterwards — a stale local tombstone, a lane that cannot vouch for the
      // row — is not grounds for erasing a completion they performed.
      if intendedCompletion {
        locallyCompletedTask = reconciledTask?.completed == true ? reconciledTask : nil
      } else {
        locallyCompletedTask = nil
      }
      AnalyticsManager.shared.chatFirst(
        .taskMutation(
          lifecycle: reconciledTask?.completed == intendedCompletion ? .success : .rollback,
          mutation: .completion
        )
      )
      if reconciledTask?.completed != intendedCompletion {
        AnalyticsManager.shared.chatFirst(
          .richBlock(kind: .taskCard, outcome: .rejected, action: .toggle)
        )
      }

      // `TasksStore` owns local-first mutation and rollback. Acknowledgement
      // is derived only from its reconciled record, never from the tap.
      guard
        ChatFirstTaskCardReconciliation.shouldShowCompletionAcknowledgement(
          intendedCompletion: intendedCompletion,
          reconciledTask: reconciledTask
        )
      else { return }
      OmiMotion.withGated(.spring(response: 0.26, dampingFraction: 0.72)) {
        showCompletionAcknowledgement = true
      }
      Task { @MainActor in
        try? await Task.sleep(nanoseconds: 550_000_000)
        guard !Task.isCancelled else { return }
        OmiMotion.withGated(.easeOut(duration: 0.16)) {
          showCompletionAcknowledgement = false
        }
      }
    }
  }
}

/// What a finished hydration is allowed to write back to the card.
///
/// `.task(id:)` cancels the in-flight hydration when its key changes, but Swift
/// cancellation is cooperative: the body keeps running and its `await` still
/// returns. A hydration that started while the card had no task can therefore
/// land *after* the reader has ticked that task, carrying an answer from before
/// the tick — and `resolveCanonicalTask` answers nil for any row it cannot
/// vouch for, including one whose owner lease turned over mid-flight. Applying
/// that late nil cleared the retained task and marked hydration finished, which
/// is exactly the pair that renders "Task is no longer available" under a task
/// the reader had just completed.
///
/// Observed directly: a card visibly showing its task logged
/// `hydrated resolved=nil` from a hydration still in flight behind it.
enum ChatFirstTaskCardHydration {
  enum Resolution: Equatable {
    /// Nothing newer arrived; the answer is the card's state.
    case adopt
    /// The card already has a live task, so there is nothing to adopt — but
    /// this hydration is genuinely over.
    case settle
    /// A successor hydration owns the card's state. Write nothing at all:
    /// even `hydrationFinished` would flash the unavailable placeholder in
    /// the gap before the successor answers.
    case abandon
  }

  static func resolution(isCancelled: Bool, hasLiveTask: Bool) -> Resolution {
    if isCancelled { return .abandon }
    return hasLiveTask ? .settle : .adopt
  }
}

enum ChatFirstTaskCardPresentation {
  /// `locallyCompletedTask` is the completion the reader performed on this card
  /// and it outranks everything, retirement included.
  ///
  /// Every other input is a projection of store state, and store state can say
  /// a task is gone for reasons that have nothing to do with the reader: the
  /// Removed lane used to tombstone live rows locally, so ticking one of them
  /// swapped their own completed card for "Task is no longer available". A
  /// gesture the app accepted is not something a later read gets to deny — the
  /// card keeps showing the tick until the reader themselves unticks it.
  static func displayTask(
    liveTask: TaskActionItem?,
    retainedCompletedTask: TaskActionItem?,
    locallyCompletedTask: TaskActionItem? = nil
  ) -> TaskActionItem? {
    if let locallyCompletedTask, locallyCompletedTask.completed {
      return locallyCompletedTask
    }
    if let liveTask {
      return liveTask.isRetired ? nil : liveTask
    }
    guard let retainedCompletedTask,
      retainedCompletedTask.completed,
      !retainedCompletedTask.isRetired
    else { return nil }
    return retainedCompletedTask
  }
}

/// Keeps the card's acknowledgement tied to the owner-safe store's reconciled
/// record. A failed remote mutation leaves the original task in the store, so
/// the view never converts a tap into a false success signal.
enum ChatFirstTaskCardReconciliation {
  static func shouldShowCompletionAcknowledgement(
    intendedCompletion: Bool,
    reconciledTask: TaskActionItem?
  ) -> Bool {
    intendedCompletion && reconciledTask?.completed == true
  }
}

// MARK: - Goal and capture links

struct GoalLinkView: View {
  let goalID: String
  let summary: String
  let navigation: ChatFirstShellNavigation
  @ObservedObject var goalsStore: CanonicalGoalsStore

  @State private var isOpening = false
  @State private var isUnavailable = false

  var body: some View {
    Group {
      if isUnavailable {
        ChatFirstUnavailableBlockView(entityName: "Goal")
      } else {
        ChatFirstLinkBlockView(
          eyebrow: "Goal",
          systemImage: "target",
          summary: summary,
          actionTitle: "Open in Goals",
          isOpening: isOpening,
          accessibilityID: "chat-first-goal-\(goalID)-open"
        ) {
          openGoal()
        }
      }
    }
    .onAppear {
      AnalyticsManager.shared.chatFirst(
        .richBlock(kind: .goalLink, outcome: .rendered, action: .none)
      )
    }
  }

  private func openGoal() {
    guard !isOpening else { return }
    isOpening = true
    let resolutionGeneration = navigation.beginGoalLinkResolution()
    Task { @MainActor in
      defer { isOpening = false }
      // Validate through the root-owned canonical projection. The actual
      // destination remains a typed shell focus, never a display-string URL.
      let detail = await goalsStore.loadDetail(goalID: goalID)
      guard navigation.isCurrentGoalLinkResolution(resolutionGeneration) else { return }
      guard detail != nil else {
        isUnavailable = true
        AnalyticsManager.shared.chatFirst(
          .richBlock(kind: .goalLink, outcome: .stalePlaceholder, action: .open)
        )
        return
      }
      AnalyticsManager.shared.chatFirst(
        .richBlock(kind: .goalLink, outcome: .acted, action: .open)
      )
      _ = navigation.completeGoalLinkResolution(goalID: goalID, generation: resolutionGeneration)
    }
  }
}

struct CaptureLinkView: View {
  let conversationID: String
  let momentTimestampMs: Int?
  let summary: String
  let navigation: ChatFirstShellNavigation

  @State private var isOpening = false
  @State private var isUnavailable = false

  var body: some View {
    Group {
      if isUnavailable {
        ChatFirstUnavailableBlockView(entityName: "Conversation")
      } else {
        ChatFirstLinkBlockView(
          eyebrow: "Conversation",
          systemImage: "waveform",
          summary: summary,
          actionTitle: "Open conversation",
          isOpening: isOpening,
          accessibilityID: "chat-first-capture-\(conversationID)-open"
        ) {
          openCapture()
        }
      }
    }
    .onAppear {
      AnalyticsManager.shared.chatFirst(
        .richBlock(kind: .captureLink, outcome: .rendered, action: .none)
      )
    }
  }

  private func openCapture() {
    guard !isOpening else { return }
    isOpening = true
    Task { @MainActor in
      defer { isOpening = false }
      do {
        _ = try await APIClient.shared.getOmiCapture(id: conversationID)
        let moment = momentTimestampMs.map { TimeInterval($0) / 1_000 }
        AnalyticsManager.shared.chatFirst(
          .richBlock(kind: .captureLink, outcome: .acted, action: .open)
        )
        navigation.open(focus: .capture(id: conversationID, momentTs: moment))
      } catch {
        isUnavailable = true
        AnalyticsManager.shared.chatFirst(
          .richBlock(kind: .captureLink, outcome: .stalePlaceholder, action: .open)
        )
      }
    }
  }
}

struct ConversationLinkView: View {
  let conversationID: String
  let summary: String
  let recommendedActionItems: [ConversationLinkActionItem]
  let navigation: ChatFirstShellNavigation

  @State private var isOpening = false
  @State private var isUnavailable = false
  @State private var isCopyingLink = false
  @State private var shareLinkFeedback: ConversationShareLinkFeedback?
  @State private var shareLinkFeedbackGeneration = 0
  @State private var shareRecipients: [ConversationShareRecipient] = []
  @State private var isSendingSummary = false
  @State private var summarySendStatus: (message: String, success: Bool)?

  private var sendSummaryTitle: String? {
    guard let first = shareRecipients.first else { return nil }
    let extra = shareRecipients.count - 1
    return extra > 0 ? "Send to \(first.shortLabel) +\(extra)" : "Send to \(first.shortLabel)"
  }

  private var statusLine: (message: String, systemImage: String, color: Color)? {
    if let summarySendStatus {
      return (
        summarySendStatus.message,
        summarySendStatus.success ? "checkmark" : "exclamationmark.triangle",
        summarySendStatus.success ? Ink.listeningGreen : Ink.errorRed
      )
    }
    if let shareLinkFeedback {
      return (
        shareLinkFeedback.message,
        shareLinkFeedback.systemImage,
        shareLinkFeedback == .copied ? Ink.listeningGreen : Ink.errorRed
      )
    }
    return nil
  }

  var body: some View {
    Group {
      if isUnavailable {
        ChatFirstUnavailableBlockView(entityName: "Conversation")
      } else {
        ChatFirstLinkBlockView(
          eyebrow: "Meeting notes ready",
          systemImage: "text.document",
          summary: summary,
          actionTitle: "Open conversation",
          isOpening: isOpening,
          accessibilityID: "chat-first-conversation-\(conversationID)-open",
          action: { openConversation() },
          recommendedActionItems: recommendedActionItems,
          recommendedActionItemAction: { item in
            guard let taskID = item.taskID else { return }
            navigation.open(focus: .task(id: taskID))
          },
          secondaryActionTitle: "Copy share link",
          secondaryActionSystemImage: "link",
          isSecondaryBusy: isCopyingLink,
          secondaryAccessibilityID: "chat-first-conversation-\(conversationID)-copy-link",
          secondaryHelp: "Copy share link — anyone with the link can view",
          secondaryAction: { copyShareLink() },
          tertiaryActionTitle: sendSummaryTitle,
          tertiaryActionSystemImage: "paperplane",
          isTertiaryBusy: isSendingSummary,
          tertiaryAccessibilityID: "chat-first-conversation-\(conversationID)-send-summary",
          tertiaryHelp: shareRecipients.first.map { "Email the summary to \($0.email)" },
          tertiaryAction: { sendSummary() },
          statusMessage: statusLine?.message,
          statusSystemImage: statusLine?.systemImage,
          statusColor: statusLine?.color ?? Ink.secondary
        )
      }
    }
    .onAppear {
      AnalyticsManager.shared.chatFirst(
        .richBlock(kind: .conversationLink, outcome: .rendered, action: .none)
      )
    }
    .task {
      // Calendar-detected participants make the one-click "Send to …" chip
      // appear; no detection (or a fetch failure) just means no chip.
      shareRecipients =
        (try? await APIClient.shared.getConversationShareRecipients(id: conversationID)) ?? []
    }
  }

  /// One-click email of the summary to the calendar-detected participants.
  /// The backend validates recipients and flips visibility to shared, so this
  /// discloses the audience in the confirmation just like copying the link.
  private func sendSummary() {
    guard !isSendingSummary, !shareRecipients.isEmpty else { return }
    isSendingSummary = true
    Task { @MainActor in
      defer { isSendingSummary = false }
      do {
        let sent = try await APIClient.shared.sendConversationSummaryEmail(
          id: conversationID,
          recipientEmails: shareRecipients.map(\.email)
        )
        summarySendStatus = (
          "Summary sent to \(sent.joined(separator: ", ")) — anyone with the link can view", true
        )
      } catch {
        summarySendStatus = ("Couldn't send the summary — try again", false)
      }
    }
  }

  /// Copies a public share link for the conversation. Minting the link flips
  /// the conversation's visibility to shared, so the confirmation discloses
  /// the audience. A failure here never touches `isUnavailable` — copy
  /// problems must not block "Open conversation".
  private func copyShareLink() {
    guard !isCopyingLink else { return }
    isCopyingLink = true
    Task { @MainActor in
      defer { isCopyingLink = false }
      let feedback = await ConversationShareLinkAction.run(
        mintLink: { try await APIClient.shared.getConversationShareLink(id: conversationID) },
        copyToPasteboard: { link in
          NSPasteboard.general.clearContents()
          return NSPasteboard.general.setString(link, forType: .string)
        }
      )
      AnalyticsManager.shared.chatFirst(
        .richBlock(
          kind: .conversationLink,
          outcome: feedback == .copied ? .acted : .rejected,
          action: .copyLink
        )
      )
      shareLinkFeedback = feedback
      shareLinkFeedbackGeneration += 1
      let generation = shareLinkFeedbackGeneration
      DispatchQueue.main.asyncAfter(deadline: .now() + ConversationShareLinkFeedback.displaySeconds) {
        guard shareLinkFeedbackGeneration == generation else { return }
        shareLinkFeedback = nil
      }
    }
  }

  private func openConversation() {
    guard !isOpening else { return }
    isOpening = true
    let resolutionGeneration = navigation.beginConversationLinkResolution()
    Task { @MainActor in
      defer { isOpening = false }
      do {
        let conversation = try await APIClient.shared.getConversation(id: conversationID)
        guard
          let conversation = ChatFirstConversationLinkPolicy.validatedConversation(
            conversation,
            requestedID: conversationID
          )
        else {
          throw URLError(.cannotParseResponse)
        }
        guard
          navigation.completeConversationLinkResolution(
            conversation: conversation,
            generation: resolutionGeneration)
        else { return }
        AnalyticsManager.shared.chatFirst(
          .richBlock(kind: .conversationLink, outcome: .acted, action: .open)
        )
      } catch {
        isUnavailable = true
        AnalyticsManager.shared.chatFirst(
          .richBlock(kind: .conversationLink, outcome: .stalePlaceholder, action: .open)
        )
      }
    }
  }
}

/// The detail fetch is authoritative for a conversation link. Keep a small
/// pure policy around the ID check so malformed or mismatched responses take
/// the same unavailable path as a failed request instead of opening a nearby
/// paginated row.
enum ChatFirstConversationLinkPolicy {
  static func validatedConversation(
    _ conversation: ServerConversation?,
    requestedID: String
  ) -> ServerConversation? {
    guard let conversation, conversation.id == requestedID else { return nil }
    return conversation
  }
}

/// Where a chat citation for a conversation opens, decided from the record the
/// server returns for the cited ID.
enum ChatFirstConversationCitationRoute: Equatable {
  /// An Omi-device capture. The capture focus routes through the capture
  /// archive, which carries the transcript moment into playback.
  case captureFocus(momentTs: TimeInterval?)
  /// Any other recorded conversation — a desktop or phone session the agent
  /// retrieved. Opens as the exact fetched record, which the paginated
  /// Conversations list may not currently contain.
  case exactRecord
}

extension ChatFirstConversationLinkPolicy {
  /// Chat citations name whatever conversation the agent retrieved, but the
  /// capture focus resolves only through the archive's strictly source-scoped
  /// fetch — routing a non-capture citation there landed the reader on the
  /// Conversations list with nothing opened. Let the fetched record's own
  /// provenance pick the route instead of the citation's kind alone.
  static func citationRoute(
    forFetched conversation: ServerConversation?,
    requestedID: String,
    momentTimestampMs: Int?
  ) -> ChatFirstConversationCitationRoute? {
    guard let conversation = validatedConversation(conversation, requestedID: requestedID) else {
      return nil
    }
    if conversation.isOmiCaptureArchiveRecord {
      return .captureFocus(momentTs: momentTimestampMs.map { TimeInterval($0) / 1_000 })
    }
    return .exactRecord
  }
}

struct MemoryLinkView: View {
  let memoryID: String
  let summary: String
  let navigation: ChatFirstShellNavigation

  var body: some View {
    ChatFirstLinkBlockView(
      eyebrow: "Memory",
      systemImage: "brain.head.profile",
      summary: summary,
      actionTitle: "Open in Memories",
      isOpening: false,
      accessibilityID: "chat-first-memory-\(memoryID)-open"
    ) {
      AnalyticsManager.shared.chatFirst(
        .richBlock(kind: .memoryLink, outcome: .acted, action: .open)
      )
      navigation.open(focus: .memory(id: memoryID))
    }
    .onAppear {
      AnalyticsManager.shared.chatFirst(
        .richBlock(kind: .memoryLink, outcome: .rendered, action: .none)
      )
    }
  }
}

// MARK: - Memory review card

/// The `memoryReviewCard` block, rendered as the same rows the daily summary card uses.
///
/// One row view, two arrival paths. The desktop's live path is the summary record — this app has
/// no `day_summary` chat row today — but the block is the contract both shells share, and giving it
/// a second row implementation is how the two surfaces would drift into disagreeing about what a
/// verdict means.
struct MemoryReviewCardView: View {
  let summaryID: String
  let date: String
  let items: [MemoryReviewItem]

  var body: some View {
    MemoryReviewSection(items: items, source: .chatBlock)
      .id("memory-review-block-\(summaryID)-\(date)")
  }
}

private struct ChatFirstLinkBlockView: View {
  let eyebrow: String
  let systemImage: String
  let summary: String
  let actionTitle: String
  let isOpening: Bool
  let accessibilityID: String
  let action: () -> Void
  var recommendedActionItems: [ConversationLinkActionItem] = []
  var recommendedActionItemAction: ((ConversationLinkActionItem) -> Void)? = nil
  // Optional secondary chip rendered beside the primary destination chip
  // (e.g. "Copy share link" beside "Open conversation"). The transient
  // status renders on its own caption line under the chips so a long
  // confirmation never stretches or clips the chip row.
  var secondaryActionTitle: String? = nil
  var secondaryActionSystemImage: String = "link"
  var isSecondaryBusy: Bool = false
  var secondaryAccessibilityID: String = ""
  var secondaryHelp: String? = nil
  var secondaryAction: (() -> Void)? = nil
  // Optional tertiary chip (e.g. "Send to Sarah" beside "Copy share link"),
  // same chrome and busy semantics as the secondary chip.
  var tertiaryActionTitle: String? = nil
  var tertiaryActionSystemImage: String = "paperplane"
  var isTertiaryBusy: Bool = false
  var tertiaryAccessibilityID: String = ""
  var tertiaryHelp: String? = nil
  var tertiaryAction: (() -> Void)? = nil
  var statusMessage: String? = nil
  var statusSystemImage: String? = nil
  var statusColor: Color = Ink.secondary

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Label(eyebrow, systemImage: systemImage)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundStyle(Ink.secondary)

      Text(summary)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

      if !recommendedActionItems.isEmpty {
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          Text("Recommended next steps")
            .scaledFont(size: OmiType.micro, weight: .semibold)
            .foregroundStyle(Ink.secondary)

          ForEach(recommendedActionItems.indices, id: \.self) { index in
            recommendedActionItemRow(recommendedActionItems[index])
          }
        }
      }

      HStack(spacing: OmiSpacing.sm) {
        Button(action: action) {
          HStack(spacing: OmiSpacing.xs) {
            if isOpening {
              ProgressView()
                .controlSize(.small)
            }
            Text(actionTitle)
            Image(systemName: "arrow.up.right")
          }
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(Ink.primary)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xs)
          .glassChip()
        }
        .buttonStyle(.plain)
        .disabled(isOpening)
        .accessibilityLabel(actionTitle)
        .accessibilityIdentifier(accessibilityID)

        if let secondaryActionTitle, let secondaryAction {
          Button(action: secondaryAction) {
            HStack(spacing: OmiSpacing.xs) {
              if isSecondaryBusy {
                ProgressView()
                  .controlSize(.small)
              }
              Text(secondaryActionTitle)
              Image(systemName: secondaryActionSystemImage)
            }
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundStyle(Ink.primary)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xs)
            .glassChip()
          }
          .buttonStyle(.plain)
          .disabled(isSecondaryBusy)
          .help(secondaryHelp ?? secondaryActionTitle)
          .accessibilityLabel(secondaryHelp ?? secondaryActionTitle)
          .accessibilityIdentifier(secondaryAccessibilityID)
        }

        if let tertiaryActionTitle, let tertiaryAction {
          Button(action: tertiaryAction) {
            HStack(spacing: OmiSpacing.xs) {
              if isTertiaryBusy {
                ProgressView()
                  .controlSize(.small)
              }
              Text(tertiaryActionTitle)
              Image(systemName: tertiaryActionSystemImage)
            }
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundStyle(Ink.primary)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xs)
            .glassChip()
          }
          .buttonStyle(.plain)
          .disabled(isTertiaryBusy)
          .help(tertiaryHelp ?? tertiaryActionTitle)
          .accessibilityLabel(tertiaryHelp ?? tertiaryActionTitle)
          .accessibilityIdentifier(tertiaryAccessibilityID)
        }
      }

      if let statusMessage {
        Label(statusMessage, systemImage: statusSystemImage ?? "checkmark")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundStyle(statusColor)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Ink.rowFill)
    .clipShape(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous))
    .overlay(
      RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous)
        .stroke(Ink.glassEdge, lineWidth: 1)
    )
  }

  @ViewBuilder
  private func recommendedActionItemRow(_ item: ConversationLinkActionItem) -> some View {
    if item.taskID != nil, let recommendedActionItemAction {
      Button {
        recommendedActionItemAction(item)
      } label: {
        recommendedActionItemLabel(item, showsOpenIndicator: true)
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Open task: \(item.description)")
    } else {
      recommendedActionItemLabel(item, showsOpenIndicator: false)
    }
  }

  private func recommendedActionItemLabel(
    _ item: ConversationLinkActionItem,
    showsOpenIndicator: Bool
  ) -> some View {
    HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.xs) {
      Image(systemName: "circle")
        .scaledFont(size: OmiType.micro, weight: .medium)
        .foregroundStyle(Ink.secondary)
      Text(item.description)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundStyle(Ink.primary)
        .fixedSize(horizontal: false, vertical: true)
      if showsOpenIndicator {
        Image(systemName: "chevron.right")
          .scaledFont(size: OmiType.micro, weight: .semibold)
          .foregroundStyle(Ink.secondary)
      }
    }
  }
}

/// A compact typed destination control shared by rich Chat cards and the
/// universal Tasks page. Its closure is intentionally the only navigation
/// surface: callers supply typed shell focus rather than model text or URLs.
struct ChatFirstDestinationBadge: View {
  let title: String
  let systemImage: String
  let accessibilityID: String
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Label(title, systemImage: systemImage)
        .scaledFont(size: OmiType.micro, weight: .medium)
        .foregroundStyle(Ink.secondary)
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.xxs)
        .glassChip()
    }
    .buttonStyle(.plain)
    .accessibilityLabel("Open \(title)")
    .accessibilityIdentifier(accessibilityID)
  }
}

struct ChatFirstUnavailableBlockView: View {
  let entityName: String

  var body: some View {
    Label("\(entityName) is no longer available", systemImage: "exclamationmark.circle")
      .scaledFont(size: OmiType.caption, weight: .medium)
      .foregroundStyle(Ink.secondary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(Ink.rowFill)
      .clipShape(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous))
      .overlay(
        RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous)
          .stroke(Ink.glassEdge, lineWidth: 1)
      )
      .accessibilityLabel("\(entityName) is no longer available")
      .accessibilityIdentifier("chat-first-\(entityName.lowercased())-unavailable")
  }
}

private struct ChatFirstLoadingBlockView: View {
  let entityName: String

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      ProgressView()
        .controlSize(.small)
      Text("Loading \(entityName.lowercased())")
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundStyle(Ink.secondary)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(Ink.rowFill)
    .clipShape(RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous))
    .overlay(
      RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous)
        .stroke(Ink.glassEdge, lineWidth: 1)
    )
    .accessibilityLabel("Loading \(entityName.lowercased())")
    .accessibilityIdentifier("chat-first-\(entityName.lowercased())-loading")
  }
}
