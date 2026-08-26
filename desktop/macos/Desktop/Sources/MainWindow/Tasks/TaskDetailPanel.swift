import AppKit
import OmiTheme
import SwiftUI

// MARK: - Task detail panel

struct TaskDetailPanel: View {
  let task: TaskActionItem
  let onDismiss: () -> Void
  let onToggle: () -> Void
  let onEdit: () -> Void
  let onOpenChat: (() -> Void)?
  let onIncrementIndent: (() -> Void)?
  let onDecrementIndent: (() -> Void)?
  let onDelete: () -> Void
  let onPriorityChange: ((String) -> Void)?

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
    onOpenChat: (() -> Void)? = nil,
    onIncrementIndent: (() -> Void)? = nil,
    onDecrementIndent: (() -> Void)? = nil,
    onDelete: @escaping () -> Void,
    onPriorityChange: ((String) -> Void)? = nil
  ) {
    self.task = task
    self.onDismiss = onDismiss
    self.onToggle = onToggle
    self.onEdit = onEdit
    self.onOpenChat = onOpenChat
    self.onIncrementIndent = onIncrementIndent
    self.onDecrementIndent = onDecrementIndent
    self.onDelete = onDelete
    self.onPriorityChange = onPriorityChange
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      header
      Divider().overlay(Ink.separator.opacity(0.25))

      ScrollView {
        VStack(alignment: .leading, spacing: OmiSpacing.xl) {
          descriptionSection
          prioritySection
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
    .background(Ink.rowFill)
    .accessibilityIdentifier("task-detail-panel")
  }

  private var header: some View {
    HStack(spacing: OmiSpacing.sm) {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text("Task details")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)
        Text(content.status)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
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
        .foregroundColor(Ink.primary)
        .fixedSize(horizontal: false, vertical: true)
        .textSelection(.enabled)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  /// Priority lives here rather than on the task row: it is a rarely-changed
  /// attribute, and the row's hover strip is reserved for per-task actions.
  @ViewBuilder
  private var prioritySection: some View {
    if let onPriorityChange {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        sectionTitle("Priority")
        HStack(spacing: OmiSpacing.xs) {
          ForEach(TaskDetailPanel.priorityOptions, id: \.value) { option in
            let isSelected = task.priority?.lowercased() == option.value
            Button {
              guard !isSelected else { return }
              onPriorityChange(option.value)
            } label: {
              Text(option.label)
                .scaledFont(size: OmiType.caption, weight: isSelected ? .semibold : .regular)
                .foregroundColor(isSelected ? Ink.surface : Ink.primary)
                .padding(.horizontal, OmiSpacing.md)
                .padding(.vertical, OmiSpacing.xs)
                .background(
                  Capsule().fill(isSelected ? Ink.primary : Ink.rowFillHover)
                )
                .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .help("Set \(option.label.lowercased()) priority")
            .accessibilityIdentifier("task-detail-priority-\(option.value)")
          }
        }
      }
    }
  }

  private static let priorityOptions: [(value: String, label: String)] = [
    ("low", "Low"), ("medium", "Medium"), ("high", "High"),
  ]

  private var whySection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      sectionTitle("Why Omi added this")
      Text(content.whyOmiAddedThis)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(OmiSpacing.md)
        .background(
          RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
            .fill(Ink.rowFillHover)
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
          .foregroundColor(Ink.secondary)
      }

      if content.linkedSources.isEmpty {
        Text("No navigable source was attached to this task.")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
      } else {
        VStack(spacing: OmiSpacing.xs) {
          ForEach(content.linkedSources) { source in
            Button {
              TaskDetailSourceNavigator.open(source.route)
            } label: {
              HStack(spacing: OmiSpacing.sm) {
                Image(systemName: source.systemImage)
                  .scaledFont(size: OmiType.body)
                  .foregroundColor(Ink.secondary)
                  .frame(width: 20)
                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                  Text(source.title)
                    .scaledFont(size: OmiType.caption, weight: .medium)
                    .foregroundColor(Ink.primary)
                  Text(source.subtitle)
                    .scaledFont(size: OmiType.micro)
                    .foregroundColor(Ink.secondary)
                    .lineLimit(1)
                }
                Spacer(minLength: OmiSpacing.xs)
                Image(systemName: "arrow.up.right")
                  .scaledFont(size: OmiType.micro, weight: .semibold)
                  .foregroundColor(Ink.secondary)
              }
              .padding(OmiSpacing.sm)
              .frame(maxWidth: .infinity, alignment: .leading)
              .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
                  .fill(Ink.rowFillHover)
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
              .foregroundColor(Ink.secondary)
              .frame(width: 84, alignment: .leading)
            Text(field.value)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.primary)
              .textSelection(.enabled)
          }
        }
      }
    }
  }

  @ViewBuilder
  private var contextSection: some View {
    let metadata = task.parsedMetadata ?? [:]
    if task.contextSummary != nil || task.currentActivity != nil
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
        .foregroundColor(Ink.secondary)
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
    .foregroundColor(Ink.primary)
    .padding(.vertical, OmiSpacing.xs)
    .accessibilityIdentifier(identifier)
  }

  private func sectionTitle(_ title: String) -> some View {
    Text(title.uppercased())
      .scaledFont(size: OmiType.micro, weight: .semibold)
      .foregroundColor(Ink.secondary)
      .tracking(0.6)
  }

  private func detailBlock(_ label: String, _ value: String) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
      Text(label)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)
      Text(value)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
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
