import SwiftUI

/// Page showing completed goals history
struct GoalsHistoryPage: View {
    @State private var completedGoals: [Goal] = []
    @State private var isLoading = true
    @State private var error: String?
    let onDismiss: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Button(action: onDismiss) {
                    HStack(spacing: 6) {
                        Image(systemName: "chevron.left")
                            .font(.system(size: 12, weight: .semibold))
                        Text("Back")
                            .font(.system(size: 14, weight: .medium))
                    }
                    .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)

                Spacer()

                Text("Goals History")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                // Spacer to balance the back button
                Color.clear.frame(width: 60)
            }
            .padding(.horizontal, 20)
            .padding(.top, 20)
            .padding(.bottom, 16)

            Divider()
                .background(OmiColors.backgroundTertiary)

            if isLoading {
                VStack(spacing: 12) {
                    ProgressView()
                        .scaleEffect(1.0)
                    Text("Loading history...")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = error {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(.orange)
                    Text(error)
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textSecondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if completedGoals.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "trophy")
                        .font(.system(size: 40))
                        .foregroundColor(OmiColors.textTertiary.opacity(0.5))
                    Text("No goals history yet")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundColor(OmiColors.textTertiary)
                    Text("Completed and removed goals will appear here")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary.opacity(0.7))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    VStack(spacing: 8) {
                        ForEach(completedGoals) { goal in
                            CompletedGoalRow(goal: goal)
                        }
                    }
                    .padding(20)
                }
            }
        }
        .background(OmiColors.backgroundSecondary)
        .task {
            await loadCompletedGoals()
        }
    }

    private func loadCompletedGoals() async {
        isLoading = true
        do {
            completedGoals = try await APIClient.shared.getCompletedGoals()
            isLoading = false
        } catch {
            self.error = error.localizedDescription
            isLoading = false
        }
    }
}

// MARK: - Completed Goal Row

struct CompletedGoalRow: View {
    let goal: Goal

    private var goalEmoji: String {
        let title = goal.title.lowercased()
        if title.contains("revenue") || title.contains("money") || title.contains("income") { return "💰" }
        if title.contains("users") || title.contains("growth") || title.contains("subscribers") { return "🚀" }
        if title.contains("workout") || title.contains("gym") || title.contains("exercise") { return "💪" }
        if title.contains("run") || title.contains("steps") || title.contains("walk") { return "🏃" }
        if title.contains("read") || title.contains("book") || title.contains("pages") { return "📚" }
        if title.contains("code") || title.contains("program") || title.contains("app") { return "💻" }
        if title.contains("meditat") || title.contains("mindful") || title.contains("yoga") { return "🧘" }
        if title.contains("sleep") || title.contains("rest") { return "😴" }
        if title.contains("water") || title.contains("hydrat") { return "💧" }
        if title.contains("learn") || title.contains("study") || title.contains("course") { return "🎓" }
        if title.contains("write") || title.contains("blog") || title.contains("content") { return "✍️" }
        if title.contains("habit") || title.contains("streak") || title.contains("daily") { return "🔥" }
        return "🎯"
    }

    private var isCompleted: Bool {
        goal.completedAt != nil
    }

    private var completionDateText: String {
        guard let completedAt = goal.completedAt else { return "" }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: completedAt, relativeTo: Date())
    }

    private var typeBadgeText: String {
        switch goal.goalType {
        case .boolean: return "Yes/No"
        case .scale: return "Scale"
        case .numeric: return "Numeric"
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            // Emoji
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundTertiary.opacity(0.6))
                    .frame(width: 36, height: 36)
                Text(goalEmoji)
                    .font(.system(size: 18))
            }

            // Content
            VStack(alignment: .leading, spacing: 4) {
                Text(goal.title)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(OmiColors.textPrimary)
                    .lineLimit(1)

                HStack(spacing: 8) {
                    // Type badge
                    Text(typeBadgeText)
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(OmiColors.purplePrimary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(
                            Capsule()
                                .fill(OmiColors.purplePrimary.opacity(0.15))
                        )

                    // Final value
                    Text("\(Int(goal.currentValue))/\(Int(goal.targetValue))\(goal.unit.map { " \($0)" } ?? "")")
                        .font(.system(size: 11))
                        .foregroundColor(OmiColors.textTertiary)
                }
            }

            Spacer()

            // Status indicator
            VStack(alignment: .trailing, spacing: 4) {
                if isCompleted {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 16))
                        .foregroundColor(Color(red: 0.133, green: 0.773, blue: 0.369))

                    if !completionDateText.isEmpty {
                        Text(completionDateText)
                            .font(.system(size: 11))
                            .foregroundColor(OmiColors.textTertiary)
                    }
                } else {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 16))
                        .foregroundColor(OmiColors.textTertiary.opacity(0.5))

                    Text("Removed")
                        .font(.system(size: 11))
                        .foregroundColor(OmiColors.textTertiary.opacity(0.7))
                }
            }
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 14)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary.opacity(0.3))
        )
    }
}
