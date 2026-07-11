import SwiftUI
import OmiTheme

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
                    HStack(spacing: OmiSpacing.xs) {
                        Image(systemName: "chevron.left")
                            .scaledFont(size: OmiType.caption, weight: .semibold)
                        Text("Back")
                            .scaledFont(size: OmiType.body, weight: .medium)
                    }
                    .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)

                Spacer()

                Text("Goals History")
                    .scaledFont(size: OmiType.heading, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                // Spacer to balance the back button
                Color.clear.frame(width: 60)
            }
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.top, OmiSpacing.xl)
            .padding(.bottom, OmiSpacing.lg)

            Divider()
                .background(OmiColors.backgroundTertiary)

            if isLoading {
                VStack(spacing: OmiSpacing.md) {
                    ProgressView()
                        .scaleEffect(1.0)
                    Text("Loading history...")
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = error {
                VStack(spacing: OmiSpacing.md) {
                    Image(systemName: "exclamationmark.triangle")
                        .scaledFont(size: 32)
                        .foregroundColor(.orange)
                    Text(error)
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textSecondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if completedGoals.isEmpty {
                VStack(spacing: OmiSpacing.md) {
                    Image(systemName: "trophy")
                        .scaledFont(size: OmiType.hero)
                        .foregroundColor(OmiColors.textTertiary.opacity(0.5))
                    Text("No goals history yet")
                        .scaledFont(size: OmiType.subheading, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                    Text("Completed and removed goals will appear here")
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textTertiary.opacity(0.7))
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(spacing: OmiSpacing.sm) {
                        ForEach(completedGoals) { goal in
                            CompletedGoalRow(goal: goal)
                        }
                    }
                    .padding(OmiSpacing.xl)
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
            self.error = UserFacingErrorPresentation.message(for: error, while: .goals)
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
        HStack(spacing: OmiSpacing.md) {
            // Emoji
            ZStack {
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                    .fill(OmiColors.backgroundTertiary.opacity(0.6))
                    .frame(width: 36, height: 36)
                Text(goalEmoji)
                    .scaledFont(size: 18)
            }

            // Content
            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text(goal.title)
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)
                    .lineLimit(1)

                HStack(spacing: OmiSpacing.sm) {
                    // Type badge
                    Text(typeBadgeText)
                        .scaledFont(size: OmiType.micro, weight: .medium)
                        .foregroundColor(OmiColors.accent)
                        .padding(.horizontal, OmiSpacing.xs)
                        .padding(.vertical, OmiSpacing.hairline)
                        .background(
                            Capsule()
                                .fill(OmiColors.accent.opacity(0.15))
                        )

                    // Final value
                    Text("\(Int(goal.currentValue))/\(Int(goal.targetValue))\(goal.unit.map { " \($0)" } ?? "")")
                        .scaledFont(size: OmiType.caption)
                        .foregroundColor(OmiColors.textTertiary)
                }
            }

            Spacer()

            // Status indicator
            VStack(alignment: .trailing, spacing: OmiSpacing.xxs) {
                if isCompleted {
                    Image(systemName: "checkmark.circle.fill")
                        .scaledFont(size: OmiType.subheading)
                        .foregroundColor(Color(red: 0.133, green: 0.773, blue: 0.369))

                    if !completionDateText.isEmpty {
                        Text(completionDateText)
                            .scaledFont(size: OmiType.caption)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                } else {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: OmiType.subheading)
                        .foregroundColor(OmiColors.textTertiary.opacity(0.5))

                    Text("Removed")
                        .scaledFont(size: OmiType.caption)
                        .foregroundColor(OmiColors.textTertiary.opacity(0.7))
                }
            }
        }
        .padding(.vertical, OmiSpacing.sm)
        .padding(.horizontal, OmiSpacing.md)
        .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                .fill(OmiColors.backgroundTertiary.opacity(0.3))
        )
    }
}
