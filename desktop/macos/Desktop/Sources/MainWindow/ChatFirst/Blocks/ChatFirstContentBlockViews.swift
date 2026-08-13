import OmiTheme
import SwiftUI

// MARK: - Question card

/// Choices are controls only while the kernel-backed parent is the completed
/// tail of Main Chat. The runtime remains authoritative at selection time;
/// this view's gate simply avoids presenting obsolete choices as actionable.
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
      if isActionable, selectedOptionID == nil, !validOptions.isEmpty {
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
            .accessibilityLabel("Send suggestion: \(option.label)")
            .accessibilityIdentifier("chat-first-question-\(questionID)-option-\(option.id)")
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

  private var task: TaskActionItem? {
    ChatFirstTaskCardPresentation.displayTask(
      liveTask: liveTask,
      retainedCompletedTask: retainedCompletedTask?.id == taskID ? retainedCompletedTask : nil
    )
  }

  private var hydrationKey: String {
    "\(taskID):\(liveTask == nil)"
  }

  var body: some View {
    Group {
      if let task {
        card(task)
          .onAppear {
            retainCompletedTaskIfNeeded(liveTask)
            AnalyticsManager.shared.chatFirst(
              .richBlock(kind: .taskCard, outcome: .rendered, action: .none)
            )
          }
      } else if hydrationFinished {
        ChatFirstUnavailableBlockView(entityName: "Task")
          .onAppear {
            AnalyticsManager.shared.chatFirst(
              .richBlock(kind: .taskCard, outcome: .stalePlaceholder, action: .none)
            )
          }
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
      retainCompletedTaskIfNeeded(resolvedTask)
      if resolvedTask == nil {
        retainedCompletedTask = nil
      }
      hydrationFinished = true
    }
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

      let reconciledTask = self.task
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

enum ChatFirstTaskCardPresentation {
  static func displayTask(
    liveTask: TaskActionItem?,
    retainedCompletedTask: TaskActionItem?
  ) -> TaskActionItem? {
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

private struct ChatFirstLinkBlockView: View {
  let eyebrow: String
  let systemImage: String
  let summary: String
  let actionTitle: String
  let isOpening: Bool
  let accessibilityID: String
  let action: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      Label(eyebrow, systemImage: systemImage)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundStyle(Ink.secondary)

      Text(summary)
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundStyle(Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

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
