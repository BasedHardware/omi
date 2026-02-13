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
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Text("Tasks")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                if totalTaskCount > 0 {
                    Text("\(totalTaskCount) incomplete")
                        .font(.system(size: 12).monospacedDigit())
                        .foregroundColor(OmiColors.textTertiary)
                }
            }

            if totalTaskCount == 0 {
                // Empty state
                VStack(spacing: 8) {
                    Image(systemName: "checkmark.circle")
                        .font(.system(size: 28))
                        .foregroundColor(OmiColors.textQuaternary)
                    Text("No incomplete tasks")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 20)
            } else {
                ScrollView {
                    VStack(spacing: 16) {
                        // Today section (includes overdue tasks, like Flutter)
                        if !combinedTodayTasks.isEmpty {
                            TaskSectionView(
                                title: "Today",
                                titleColor: OmiColors.textSecondary,
                                icon: "calendar",
                                tasks: Array(combinedTodayTasks.prefix(3)),
                                totalCount: combinedTodayTasks.count,
                                showDueDate: true,
                                onToggle: onToggleCompletion
                            )
                        }

                        // Recent tasks without due date
                        if !recentTasks.isEmpty {
                            TaskSectionView(
                                title: "No Due Date",
                                titleColor: OmiColors.textSecondary,
                                icon: "tray",
                                tasks: Array(recentTasks.prefix(3)),
                                totalCount: recentTasks.count,
                                showDueDate: false,
                                onToggle: onToggleCompletion
                            )
                        }
                    }
                }
                .frame(maxHeight: 280)

                // View all link
                Button(action: {
                    // Navigate to Tasks tab
                    NotificationCenter.default.post(
                        name: NSNotification.Name("NavigateToTasks"),
                        object: nil
                    )
                }) {
                    HStack {
                        Spacer()
                        Text("View all tasks")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(OmiColors.textSecondary)
                        Image(systemName: "chevron.right")
                            .font(.system(size: 10))
                            .foregroundColor(OmiColors.textSecondary)
                        Spacer()
                    }
                }
                .buttonStyle(.plain)
                .padding(.top, 4)
            }
        }
        .padding(20)
        .frame(maxHeight: .infinity, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
                )
        )
    }
}

// MARK: - Task Section View

struct TaskSectionView: View {
    let title: String
    let titleColor: Color
    let icon: String
    let tasks: [TaskActionItem]
    let totalCount: Int
    let showDueDate: Bool
    let onToggle: (TaskActionItem) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Section header
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 12))
                    .foregroundColor(titleColor)
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(titleColor)
                if totalCount > tasks.count {
                    Text("(\(totalCount))")
                        .font(.system(size: 11).monospacedDigit())
                        .foregroundColor(OmiColors.textTertiary)
                }
            }

            // Tasks
            VStack(spacing: 6) {
                ForEach(tasks) { task in
                    TaskRowView(
                        task: task,
                        showDueDate: showDueDate,
                        onToggle: { onToggle(task) }
                    )
                }
            }
        }
    }
}

// MARK: - Task Row View

struct TaskRowView: View {
    let task: TaskActionItem
    let showDueDate: Bool
    let isOverdue: Bool
    let onToggle: () -> Void

    @State private var isToggling = false

    /// Check if the task's due date is in the past
    private var taskIsOverdue: Bool {
        guard let dueAt = task.dueAt else { return false }
        return dueAt < Calendar.current.startOfDay(for: Date())
    }

    init(task: TaskActionItem, showDueDate: Bool = false, isOverdue: Bool = false, onToggle: @escaping () -> Void) {
        self.task = task
        self.showDueDate = showDueDate
        self.isOverdue = isOverdue
        self.onToggle = onToggle
    }

    var body: some View {
        HStack(spacing: 10) {
            // Checkbox
            Button(action: {
                guard !isToggling else { return }
                isToggling = true
                onToggle()
                // Reset after a short delay
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                    isToggling = false
                }
            }) {
                Image(systemName: task.completed ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 18))
                    .foregroundColor(task.completed ? OmiColors.textPrimary : OmiColors.textTertiary)
            }
            .buttonStyle(.plain)
            .disabled(isToggling)
            .opacity(isToggling ? 0.5 : 1)

            // Task description
            VStack(alignment: .leading, spacing: 2) {
                Text(task.description)
                    .font(.system(size: 13))
                    .foregroundColor(task.completed ? OmiColors.textTertiary : OmiColors.textPrimary)
                    .strikethrough(task.completed)
                    .lineLimit(2)

                // Due date chip
                if showDueDate, let dueAt = task.dueAt {
                    Text(formatDueDate(dueAt))
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(OmiColors.textSecondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(
                            Capsule()
                                .fill(OmiColors.backgroundTertiary)
                        )
                }
            }

            Spacer()

            // Priority indicator
            if let priority = task.priority, priority != "low" {
                Text(priority.capitalized)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(OmiColors.textSecondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .background(
                        Capsule()
                            .fill(OmiColors.backgroundTertiary)
                    )
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 10)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(task.completed ? OmiColors.backgroundQuaternary.opacity(0.3) : Color.clear)
        )
    }

    private func formatDueDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: date, relativeTo: Date())
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
