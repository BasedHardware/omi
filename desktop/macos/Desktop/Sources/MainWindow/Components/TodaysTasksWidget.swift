import OmiTheme
import SwiftUI

struct TasksWidget: View {
  let overdueTasks: [TaskActionItem]
  let todaysTasks: [TaskActionItem]
  let recentTasks: [TaskActionItem]
  let onToggleCompletion: (TaskActionItem) -> Void

  private var totalTaskCount: Int {
    overdueTasks.count + todaysTasks.count + recentTasks.count
  }

  /// Combine overdue + today tasks into one "Today" section (like Flutter)
  private var combinedTodayTasks: [TaskActionItem] {
    // Sort: overdue first (by due date), then today's tasks (by due date)
    let sorted = (overdueTasks + todaysTasks).sorted { a, b in
      guard let aDate = a.dueAt, let bDate = b.dueAt else { return a.dueAt != nil }
      return aDate < bDate
    }
    return sorted
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      // Header
      HStack {
        Text("Tasks")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)
      }

      if totalTaskCount == 0 {
        // Empty state — vertically centered in the cell
        VStack(spacing: 0) {
          Spacer(minLength: 0)

          VStack(spacing: OmiSpacing.sm) {
            Image(systemName: "checkmark.circle")
              .scaledFont(size: OmiType.title)
              .foregroundColor(Ink.secondary)
            Text("No incomplete tasks")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
          }

          Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        let allTasks = (combinedTodayTasks + recentTasks).prefix(3)

        // Task rows + "View all" centered vertically in remaining
        // cell height — when the Goals card is taller, the row
        // group floats to the middle instead of pinning to the top.
        VStack(spacing: 0) {
          Spacer(minLength: 0)

          VStack(spacing: OmiSpacing.sm) {
            ForEach(Array(allTasks)) { task in
              TaskRowView(
                task: task,
                onToggle: { onToggleCompletion(task) }
              )
            }
          }

          Button(action: {
            NotificationCenter.default.post(
              name: .navigateToTasks,
              object: nil
            )
          }) {
            HStack {
              Spacer()
              Text("View all tasks")
                .scaledFont(size: OmiType.caption, weight: .semibold)
                .foregroundColor(Ink.secondary)
              Image(systemName: "chevron.right")
                .scaledFont(size: OmiType.micro)
                .foregroundColor(Ink.secondary)
              Spacer()
            }
          }
          .buttonStyle(.plain)
          .padding(.top, OmiSpacing.sm)

          Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
    .padding(OmiSpacing.xl)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    .glassCard()
  }
}

// MARK: - Task Row View

struct TaskRowView: View {
  let task: TaskActionItem
  let onToggle: () -> Void

  @State private var isToggling = false

  var body: some View {
    HStack(spacing: OmiSpacing.md) {
      // Checkbox
      Button(action: {
        guard !isToggling else { return }
        isToggling = true
        onToggle()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
          isToggling = false
        }
      }) {
        Image(systemName: task.completed ? "checkmark.circle.fill" : "circle")
          .scaledFont(size: OmiType.heading)
          .foregroundColor(task.completed ? Ink.primary : Ink.secondary)
      }
      .buttonStyle(.plain)
      .disabled(isToggling)
      .opacity(isToggling ? 0.5 : 1)

      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        HStack(spacing: OmiSpacing.xs) {
          Text(task.description)
            .scaledFont(size: OmiType.body)
            .foregroundColor(task.completed ? Ink.secondary : Ink.primary)
            .strikethrough(task.completed)
            .lineLimit(2)

          if task.recurrenceRule == "daily" {
            Image(systemName: "repeat")
              .scaledFont(size: OmiType.micro)
              .foregroundColor(Ink.secondary)
          }
        }

        if task.recurrenceRule == "daily" {
          Text("Daily")
            .scaledFont(size: OmiType.micro, weight: .medium)
            .foregroundColor(Ink.secondary)
            .padding(.horizontal, OmiSpacing.xs)
            .padding(.vertical, OmiSpacing.hairline)
            .background(
              RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
                .fill(Ink.rowFillHover)
            )
        }
      }

      Spacer()
    }
    .padding(.vertical, OmiSpacing.sm)
    .padding(.horizontal, OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.chipRadius, style: .continuous)
        .fill(task.completed ? Ink.rowFill.opacity(0.55) : Ink.rowFillHover.opacity(0.45))
    )
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    TasksWidget(
      overdueTasks: [],
      todaysTasks: [],
      recentTasks: [],
      onToggleCompletion: { _ in }
    )
    .frame(width: 350)
    .padding()
    .background(Ink.surface)
  }
#endif
