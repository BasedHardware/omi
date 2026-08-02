import AppKit
import OmiTheme
import SwiftUI

// MARK: - Task detail presentation contract

enum TaskDetailPanelAction: String, CaseIterable, Hashable {
  case toggleCompletion
  case edit
  case execute
  case openThread
  case decreaseIndent
  case increaseIndent
  case copyLink
  case delete
}

enum TaskDetailSourceRoute: Equatable {
  case conversation(id: String)
  case capture(id: String)
  case memory(id: String)
  case rewind
  case external(URL)
}

struct TaskDetailSourceLink: Identifiable, Equatable {
  let id: String
  let title: String
  let subtitle: String
  let systemImage: String
  let route: TaskDetailSourceRoute
}

struct TaskDetailField: Identifiable, Equatable {
  let label: String
  let value: String

  var id: String { "\(label):\(value)" }
}

struct TaskDetailPanelContent: Equatable {
  let taskID: String
  let description: String
  let status: String
  let whyOmiAddedThis: String
  let linkedSources: [TaskDetailSourceLink]
  let fields: [TaskDetailField]

  static func make(for task: TaskActionItem) -> Self {
    Self(
      taskID: task.id,
      description: task.description,
      status: task.completed ? "Completed" : "Active",
      whyOmiAddedThis: TaskDetailSourceLinkPolicy.whyOmiAddedThis(for: task),
      linkedSources: TaskDetailSourceLinkPolicy.links(for: task),
      fields: TaskDetailSourceLinkPolicy.detailFields(for: task)
    )
  }
}

/// The panel is a single-task presentation state, separate from the existing
/// keyboard and multi-select state owned by TasksViewModel.
struct TaskDetailPanelState: Equatable {
  private(set) var selectedTaskID: String?

  init(selectedTaskID: String? = nil) {
    self.selectedTaskID = selectedTaskID
  }

  var isPresented: Bool { selectedTaskID != nil }

  mutating func open(taskID: String) {
    selectedTaskID = taskID
  }

  mutating func close() {
    selectedTaskID = nil
  }
}

enum TaskDetailPanelPresentationPolicy {
  static func showsHoverActions(
    isRowHovering: Bool,
    isPriorityPickerPresented: Bool,
    isMultiSelectMode: Bool,
    isDeletedTask: Bool,
    isTextFieldFocused: Bool,
    isDetailPanelPresented: Bool
  ) -> Bool {
    guard !isDetailPanelPresented else { return false }
    return (isRowHovering || isPriorityPickerPresented)
      && !isMultiSelectMode
      && !isDeletedTask
      && !isTextFieldFocused
  }
}

enum TaskDetailPanelActionPolicy {
  static func availableActions(
    for task: TaskActionItem,
    indentLevel: Int,
    hasChat: Bool
  ) -> Set<TaskDetailPanelAction> {
    var actions: Set<TaskDetailPanelAction> = [
      .toggleCompletion, .edit, .copyLink, .delete,
    ]
    if !task.completed {
      actions.insert(.execute)
    }
    if hasChat {
      actions.insert(.openThread)
    }
    if indentLevel > 0 {
      actions.insert(.decreaseIndent)
    }
    if indentLevel < 3 {
      actions.insert(.increaseIndent)
    }
    return actions
  }
}

// MARK: - Source resolution and navigation

enum TaskDetailSourceLinkPolicy {
  static func links(for task: TaskActionItem) -> [TaskDetailSourceLink] {
    var links: [TaskDetailSourceLink] = []

    for evidence in task.provenance ?? [] {
      let evidenceID = normalized(evidence.id)
      guard !evidenceID.isEmpty else { continue }

      let route: TaskDetailSourceRoute?
      let title: String
      let subtitle: String
      let systemImage: String

      switch evidence.kind {
      case .conversation:
        let destinationID = normalizedOptional(task.conversationId) ?? evidenceID
        route = conversationRoute(task: task, id: destinationID)
        title = task.source == "transcription:omi" ? "Omi capture" : "Conversation"
        subtitle = destinationID
        systemImage = "bubble.left.and.bubble.right"
      case .chat_message:
        // A message ref is only navigable when the task's canonical
        // conversation id is present. Opening the message id as a conversation
        // would be a plausible-looking but invalid destination.
        guard let conversationID = normalizedOptional(task.conversationId) else { continue }
        route = conversationRoute(task: task, id: conversationID)
        title = task.source == "transcription:omi" ? "Omi capture" : "Conversation"
        subtitle = conversationID
        systemImage = "bubble.left.and.bubble.right"
      case .memory_item:
        route = .memory(id: evidenceID)
        title = "Memory"
        subtitle = evidenceID
        systemImage = "brain.head.profile"
      case .local_screen:
        // Rewind is the established desktop source surface. The current
        // Rewind page has no selection/deep-link contract for a frame id, so
        // do not pretend the opaque evidence id selects a particular frame.
        route = .rewind
        title = "Screen context"
        subtitle = "Open Rewind"
        systemImage = "rectangle.dashed.and.paperclip"
      case .external:
        guard let url = URL(string: evidenceID), url.scheme != nil else { continue }
        route = .external(url)
        title = "External source"
        subtitle = url.host ?? evidenceID
        systemImage = "arrow.up.right.square"
      case .workstream_event, .artifact, ._unknown:
        // These refs are useful to agents but have no user-facing desktop
        // route. Omit them rather than rendering a dead source button.
        continue
      }

      guard let route else { continue }
      let link = TaskDetailSourceLink(
        id: sourceIdentity(route),
        title: title,
        subtitle: subtitle,
        systemImage: systemImage,
        route: route
      )
      if !links.contains(where: { $0.id == link.id }) {
        links.append(link)
      }
    }

    // Older task responses can carry the canonical conversation id without a
    // provenance array. It is still an authoritative linked source.
    if links.isEmpty, let conversationID = normalizedOptional(task.conversationId) {
      let route = conversationRoute(task: task, id: conversationID)
      links.append(
        TaskDetailSourceLink(
          id: sourceIdentity(route),
          title: task.source == "transcription:omi" ? "Omi capture" : "Conversation",
          subtitle: conversationID,
          systemImage: "bubble.left.and.bubble.right",
          route: route
        )
      )
    }

    return links
  }

  static func whyOmiAddedThis(for task: TaskActionItem) -> String {
    if task.source == nil || task.source == "manual" {
      return "You added this task directly."
    }
    if task.source?.contains("screen") == true || task.source == "screenshot" {
      return "It matched context on this Mac."
    }
    if task.source?.contains("transcription") == true || task.source?.contains("conversation") == true {
      return "It came from a conversation you captured."
    }
    return "It came from an authorized Omi source."
  }

  static func detailFields(for task: TaskActionItem) -> [TaskDetailField] {
    var fields = [
      TaskDetailField(label: "Status", value: task.completed ? "Completed" : "Active")
    ]
    if let category = task.category, !category.isEmpty {
      fields.append(TaskDetailField(label: "Category", value: category.capitalized))
    }
    if !task.tags.isEmpty {
      fields.append(TaskDetailField(label: "Tags", value: task.tags.joined(separator: ", ")))
    }
    if let priority = task.priority, !priority.isEmpty {
      fields.append(TaskDetailField(label: "Priority", value: priority.capitalized))
    }
    if let source = task.source, !source.isEmpty {
      fields.append(TaskDetailField(label: "Source", value: "\(task.sourceLabel) (\(source))"))
    }
    if let app = task.sourceApp, !app.isEmpty {
      fields.append(TaskDetailField(label: "Source App", value: app))
    }
    if let window = task.windowTitle, !window.isEmpty {
      fields.append(TaskDetailField(label: "Window", value: window))
    }
    fields.append(TaskDetailField(label: "Created", value: formatDate(task.createdAt)))
    if let dueAt = task.dueAt {
      fields.append(TaskDetailField(label: "Due", value: formatDate(dueAt)))
    }
    if let completedAt = task.completedAt {
      fields.append(TaskDetailField(label: "Completed", value: formatDate(completedAt)))
    }
    if let goalID = normalizedOptional(task.goalId) {
      fields.append(TaskDetailField(label: "Goal", value: goalID))
    }
    if let conversationID = normalizedOptional(task.conversationId) {
      fields.append(TaskDetailField(label: "Conversation", value: conversationID))
    }
    if let confidence = task.confidence {
      fields.append(TaskDetailField(label: "Confidence", value: "\(Int(confidence * 100))%"))
    }
    if let agentStatus = task.agentStatus, !agentStatus.isEmpty {
      fields.append(TaskDetailField(label: "Agent", value: agentStatus.capitalized))
    }
    if let files = task.agentEditedFiles, !files.isEmpty {
      fields.append(TaskDetailField(label: "Edited files", value: files.joined(separator: ", ")))
    }
    if let prompt = task.agentPrompt, !prompt.isEmpty {
      fields.append(TaskDetailField(label: "Agent prompt", value: String(prompt.prefix(2000))))
    }
    fields.append(contentsOf: metadataFields(for: task))
    return fields
  }

  /// Preserve the rich metadata that older task details exposed without
  /// duplicating values already represented by typed TaskActionItem fields.
  private static func metadataFields(for task: TaskActionItem) -> [TaskDetailField] {
    let handled: Set<String> = [
      "tags", "source_app", "window_title", "confidence",
      "source_category", "source_subcategory", "context_summary", "current_activity",
    ]
    guard let metadata = task.parsedMetadata else { return [] }

    return
      metadata
      .filter { !handled.contains($0.key) }
      .compactMap { key, value in
        let display: String
        if let string = value as? String, !string.isEmpty {
          display = string
        } else if let number = value as? NSNumber {
          display = number.stringValue
        } else if let strings = value as? [String], !strings.isEmpty {
          display = strings.joined(separator: ", ")
        } else {
          return nil
        }
        let label = key.replacingOccurrences(of: "_", with: " ").capitalized
        return TaskDetailField(label: label, value: display)
      }
      .sorted { lhs, rhs in lhs.label < rhs.label }
  }

  private static func conversationRoute(task: TaskActionItem, id: String) -> TaskDetailSourceRoute {
    task.source == "transcription:omi" ? .capture(id: id) : .conversation(id: id)
  }

  private static func sourceIdentity(_ route: TaskDetailSourceRoute) -> String {
    switch route {
    case .conversation(let id): return "conversation:\(id)"
    case .capture(let id): return "capture:\(id)"
    case .memory(let id): return "memory:\(id)"
    case .rewind: return "rewind"
    case .external(let url): return "external:\(url.absoluteString)"
    }
  }

  private static func normalized(_ value: String) -> String {
    value.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private static func normalizedOptional(_ value: String?) -> String? {
    guard let value else { return nil }
    let normalized = normalized(value)
    return normalized.isEmpty ? nil : normalized
  }

  private static func formatDate(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .short
    return formatter.string(from: date)
  }
}

@MainActor
enum TaskDetailSourceNavigator {
  static func open(_ route: TaskDetailSourceRoute) {
    switch route {
    case .conversation(let id), .capture(let id):
      ConversationDetailAutomationState.shared.requestOpen(conversationId: id, showTranscript: false)
      NotificationCenter.default.post(name: .desktopAutomationOpenConversationRequested, object: nil)
    case .memory(let id):
      // Both shells mount the memory detail owner from the Memories rail item.
      // Persisting the Memory Hub destination first keeps the legacy hub and
      // the typed Chat-first route aligned before the detail request arrives.
      UserDefaults.standard.set(MemoryHubDestination.memories.rawValue, forKey: MemoryHubDestination.storageKey)
      NotificationCenter.default.post(
        name: .navigateToSidebarItem,
        object: nil,
        userInfo: ["rawValue": SidebarNavItem.memories.rawValue]
      )
      DispatchQueue.main.async {
        NotificationCenter.default.post(
          name: .desktopAutomationMemoryDetailOpenRequested,
          object: nil,
          userInfo: ["memory_id": id]
        )
      }
    case .rewind:
      NotificationCenter.default.post(name: .navigateToRewind, object: nil)
    case .external(let url):
      NSWorkspace.shared.open(url)
    }
  }
}

// MARK: - Task detail panel

struct TaskDetailPanel: View {
  let task: TaskActionItem
  let onDismiss: () -> Void
  let onToggle: () -> Void
  let onEdit: () -> Void
  let onInvestigate: (() -> Void)?
  let onOpenChat: (() -> Void)?
  let onIncrementIndent: (() -> Void)?
  let onDecrementIndent: (() -> Void)?
  let onDelete: () -> Void

  @State private var isCopyingLink = false
  @State private var copyStatus: String?

  private var content: TaskDetailPanelContent {
    TaskDetailPanelContent.make(for: task)
  }

  init(
    task: TaskActionItem,
    onDismiss: @escaping () -> Void,
    onToggle: @escaping () -> Void,
    onEdit: @escaping () -> Void,
    onInvestigate: (() -> Void)? = nil,
    onOpenChat: (() -> Void)? = nil,
    onIncrementIndent: (() -> Void)? = nil,
    onDecrementIndent: (() -> Void)? = nil,
    onDelete: @escaping () -> Void
  ) {
    self.task = task
    self.onDismiss = onDismiss
    self.onToggle = onToggle
    self.onEdit = onEdit
    self.onInvestigate = onInvestigate
    self.onOpenChat = onOpenChat
    self.onIncrementIndent = onIncrementIndent
    self.onDecrementIndent = onDecrementIndent
    self.onDelete = onDelete
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      header
      Divider().overlay(OmiColors.border.opacity(0.25))

      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.xl) {
          descriptionSection
          whySection
          linkedSourcesSection
          detailsSection
          contextSection
          actionsSection
        }
        .padding(OmiSpacing.lg)
        .frame(maxWidth: .infinity, alignment: .leading)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .background(OmiColors.backgroundSecondary)
    .accessibilityIdentifier("task-detail-panel")
  }

  private var header: some View {
    HStack(spacing: OmiSpacing.sm) {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text("Task details")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(content.status)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      }
      Spacer(minLength: OmiSpacing.xs)
      DismissButton(action: onDismiss)
        .accessibilityIdentifier("task-detail-close")
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md)
  }

  private var descriptionSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      sectionTitle("Task")
      Text(content.description)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textPrimary)
        .fixedSize(horizontal: false, vertical: true)
        .textSelection(.enabled)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  private var whySection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      sectionTitle("Why Omi added this")
      Text(content.whyOmiAddedThis)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
            .fill(OmiColors.backgroundTertiary)
        )
        .accessibilityIdentifier("task-detail-why")
    }
  }

  private var linkedSourcesSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(alignment: .firstTextBaseline) {
        sectionTitle("Linked sources")
        Spacer()
        Text("\(content.linkedSources.count) linked source\(content.linkedSources.count == 1 ? "" : "s")")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      }

      if content.linkedSources.isEmpty {
        Text("No navigable source was attached to this task.")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      } else {
        VStack(spacing: OmiSpacing.xs) {
          ForEach(content.linkedSources) { source in
            Button {
              TaskDetailSourceNavigator.open(source.route)
            } label: {
              HStack(spacing: OmiSpacing.sm) {
                Image(systemName: source.systemImage)
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(OmiColors.textSecondary)
                  .frame(width: 20)
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text(source.title)
                    .scaledFont(size: OmiType.caption, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)
                  Text(source.subtitle)
                    .scaledFont(size: OmiType.micro)
                    .foregroundColor(OmiColors.textTertiary)
                    .lineLimit(1)
                }
                Spacer(minLength: OmiSpacing.xs)
                Image(systemName: "arrow.up.right")
                  .scaledFont(size: OmiType.micro, weight: .semibold)
                  .foregroundColor(OmiColors.textTertiary)
              }
              .padding(OmiSpacing.sm)
              .frame(maxWidth: .infinity, alignment: .leading)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
                  .fill(OmiColors.backgroundTertiary)
              )
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("task-detail-source-\(source.id)")
          }
        }
      }
    }
  }

  private var detailsSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      sectionTitle("Details")
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        ForEach(content.fields) { field in
          HStack(alignment: .top, spacing: OmiSpacing.sm) {
            Text(field.label)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(OmiColors.textTertiary)
              .frame(width: 84, alignment: .leading)
            Text(field.value)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textPrimary)
              .textSelection(.enabled)
          }
        }
      }
    }
  }

  @ViewBuilder
  private var contextSection: some View {
    let metadata = task.parsedMetadata ?? [:]
    if task.contextSummary != nil || task.currentActivity != nil || task.agentPlan != nil
      || metadata["context_summary"] as? String != nil
      || metadata["current_activity"] as? String != nil
      || metadata["reasoning"] as? String != nil
    {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        sectionTitle("Context")
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          if let summary = task.contextSummary ?? metadata["context_summary"] as? String, !summary.isEmpty {
            detailBlock("Summary", summary)
          }
          if let activity = task.currentActivity ?? metadata["current_activity"] as? String, !activity.isEmpty {
            detailBlock("Activity", activity)
          }
          if let reasoning = metadata["reasoning"] as? String, !reasoning.isEmpty {
            detailBlock("Reasoning", reasoning)
          }
          if let plan = task.agentPlan, !plan.isEmpty {
            detailBlock("Agent plan", String(plan.prefix(2000)))
          }
        }
      }
    }
  }

  private var actionsSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      sectionTitle("Actions")
      VStack(spacing: OmiSpacing.xs) {
        actionButton(
          title: task.completed ? "Mark as active" : "Mark complete",
          systemImage: task.completed ? "circle" : "checkmark.circle",
          action: onToggle,
          identifier: "task-detail-toggle"
        )
        actionButton(title: "Edit task", systemImage: "pencil", action: onEdit, identifier: "task-detail-edit")

        if let onInvestigate {
          actionButton(
            title: "Execute with Omi",
            systemImage: "sparkles",
            action: onInvestigate,
            identifier: "task-detail-execute"
          )
        }
        if let onOpenChat {
          actionButton(
            title: task.workstreamId == nil ? "Work on this with Omi" : "Open thread",
            systemImage: task.workstreamId == nil ? "sparkles" : "bubble.left",
            action: onOpenChat,
            identifier: "task-detail-chat"
          )
        }
        if let onDecrementIndent {
          actionButton(
            title: "Decrease indent",
            systemImage: "arrow.left.to.line",
            action: onDecrementIndent,
            identifier: "task-detail-outdent"
          )
        }
        if let onIncrementIndent {
          actionButton(
            title: "Increase indent",
            systemImage: "arrow.right.to.line",
            action: onIncrementIndent,
            identifier: "task-detail-indent"
          )
        }
        actionButton(
          title: isCopyingLink ? "Copying link…" : (copyStatus ?? "Copy task link"),
          systemImage: copyStatus == nil ? "arrowshape.turn.up.right" : "checkmark",
          action: copyShareLink,
          identifier: "task-detail-copy-link"
        )
        .disabled(isCopyingLink)

        Button(role: .destructive, action: onDelete) {
          Label("Delete task", systemImage: "trash")
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.plain)
        .foregroundColor(OmiColors.textSecondary)
        .padding(.vertical, OmiSpacing.xs)
        .accessibilityIdentifier("task-detail-delete")
      }
    }
  }

  private func actionButton(
    title: String,
    systemImage: String,
    action: @escaping () -> Void,
    identifier: String
  ) -> some View {
    Button(action: action) {
      Label(title, systemImage: systemImage)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
    .buttonStyle(.plain)
    .foregroundColor(OmiColors.textPrimary)
    .padding(.vertical, OmiSpacing.xs)
    .accessibilityIdentifier(identifier)
  }

  private func sectionTitle(_ title: String) -> some View {
    Text(title.uppercased())
      .scaledFont(size: OmiType.micro, weight: .semibold)
      .foregroundColor(OmiColors.textQuaternary)
      .tracking(0.6)
  }

  private func detailBlock(_ label: String, _ value: String) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
      Text(label)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)
      Text(value)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(OmiColors.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
        .textSelection(.enabled)
    }
  }

  private func copyShareLink() {
    guard !isCopyingLink else { return }
    isCopyingLink = true
    copyStatus = nil
    Task { @MainActor in
      defer { isCopyingLink = false }
      do {
        let response = try await APIClient.shared.shareTasks(taskIds: [task.id])
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(response.url, forType: .string)
        copyStatus = "Link copied"
      } catch {
        copyStatus = "Copy failed"
        log("Failed to get task share link: \(error)")
      }
    }
  }
}
