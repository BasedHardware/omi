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
        VStack(alignment: .leading, spacing: 16) {
            // Header
            HStack {
                Text("Tasks")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
            }

            if totalTaskCount == 0 {
                // Empty state — vertically centered in the cell
                VStack(spacing: 0) {
                    Spacer(minLength: 0)

                    VStack(spacing: 8) {
                        Image(systemName: "checkmark.circle")
                            .scaledFont(size: 28)
                            .foregroundColor(OmiColors.textQuaternary)
                        Text("No incomplete tasks")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
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

                    VStack(spacing: 10) {
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
                                .scaledFont(size: 12, weight: .semibold)
                                .foregroundColor(OmiColors.textSecondary)
                            Image(systemName: "chevron.right")
                                .scaledFont(size: 10)
                                .foregroundColor(OmiColors.textSecondary)
                            Spacer()
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 8)

                    Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .padding(22)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .omiPanel(fill: OmiColors.backgroundSecondary)
    }
}

// MARK: - Task Row View

struct TaskRowView: View {
    let task: TaskActionItem
    let onToggle: () -> Void

    @State private var isToggling = false

    var body: some View {
        HStack(spacing: 12) {
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
                    .scaledFont(size: 18)
                    .foregroundColor(task.completed ? OmiColors.textPrimary : OmiColors.textTertiary)
            }
            .buttonStyle(.plain)
            .disabled(isToggling)
            .opacity(isToggling ? 0.5 : 1)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(task.description)
                        .scaledFont(size: 13)
                        .foregroundColor(task.completed ? OmiColors.textTertiary : OmiColors.textPrimary)
                        .strikethrough(task.completed)
                        .lineLimit(2)

                    if task.recurrenceRule == "daily" {
                        Image(systemName: "repeat")
                            .scaledFont(size: 10)
                            .foregroundColor(OmiColors.purplePrimary.opacity(0.7))
                    }
                }

                if task.recurrenceRule == "daily" {
                    Text("Daily")
                        .scaledFont(size: 10, weight: .medium)
                        .foregroundColor(OmiColors.purplePrimary.opacity(0.8))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(
                            RoundedRectangle(cornerRadius: 4)
                                .fill(OmiColors.purplePrimary.opacity(0.1))
                        )
                }
            }

            Spacer()
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 12)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(task.completed ? OmiColors.backgroundRaised.opacity(0.55) : OmiColors.backgroundTertiary.opacity(0.45))
        )
    }
}

#Preview {
    TasksWidget(
        overdueTasks: [],
        todaysTasks: [],
        recentTasks: [],
        onToggleCompletion: { _ in }
    )
    .frame(width: 350)
    .padding()
    .background(OmiColors.backgroundPrimary)
}
