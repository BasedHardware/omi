import Foundation

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
    isMultiSelectMode: Bool,
    isDeletedTask: Bool,
    isTextFieldFocused: Bool,
    isDetailPanelPresented: Bool
  ) -> Bool {
    guard !isDetailPanelPresented else { return false }
    return isRowHovering
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

// MARK: - Source resolution

enum TaskDetailSourceLinkPolicy {
  /// Metadata keys shown in the Context section instead of the Details table.
  private static let contextMetadataKeys: Set<String> = [
    "context_summary", "current_activity", "reasoning", "agent_plan",
  ]

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
    // Priority is not a read-only field here — the panel edits it directly.
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
  /// duplicating values already represented by typed TaskActionItem fields
  /// or narrative context shown in the Context section.
  private static func metadataFields(for task: TaskActionItem) -> [TaskDetailField] {
    let handled = Set([
      "tags", "source_app", "window_title", "confidence",
      "source_category", "source_subcategory",
    ]).union(contextMetadataKeys)
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
