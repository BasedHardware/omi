import SwiftUI

// MARK: - Goals Widget

struct GoalsWidget: View {
    let goals: [Goal]
    let onCreateGoal: (String, Double, Double) -> Void  // (title, currentValue, targetValue)
    let onUpdateProgress: (Goal, Double) -> Void
    let onDeleteGoal: (Goal) -> Void

    @State private var editingGoal: Goal? = nil
    @State private var showingCreateSheet = false
    @State private var showingHistory = false
    @State private var isGeneratingGoal = false
    @State private var autoGenerateEnabled: Bool = GoalGenerationService.shared.isAutoGenerationEnabled

    // AI Features
    @State private var selectedGoalForAdvice: Goal? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Text("Goals")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                // Auto-generate toggle
                Button(action: {
                    autoGenerateEnabled.toggle()
                    GoalGenerationService.shared.isAutoGenerationEnabled = autoGenerateEnabled
                }) {
                    Image(systemName: autoGenerateEnabled ? "wand.and.stars" : "wand.and.stars")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(autoGenerateEnabled ? OmiColors.purplePrimary : OmiColors.textTertiary.opacity(0.5))
                }
                .buttonStyle(.plain)
                .help(autoGenerateEnabled ? "Auto-generate goals: ON" : "Auto-generate goals: OFF")

                // History button
                Button(action: { showingHistory = true }) {
                    Image(systemName: "clock.arrow.circlepath")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)

                // AI goal generation button (when there are goals but room for more)
                if goals.count > 0 && goals.count < 3 {
                    Button(action: { triggerGoalGeneration() }) {
                        if isGeneratingGoal {
                            ProgressView()
                                .scaleEffect(0.6)
                                .frame(width: 14, height: 14)
                        } else {
                            Image(systemName: "sparkles")
                                .scaledFont(size: 14, weight: .medium)
                                .foregroundColor(OmiColors.purplePrimary.opacity(0.8))
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(isGeneratingGoal)
                }

                // Add goal button (only if less than 3 goals)
                if goals.count < 3 {
                    Button(action: { showingCreateSheet = true }) {
                        Image(systemName: "plus")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
            }

            // Number emojis for goal indices
            let numberEmojis = ["1️⃣", "2️⃣", "3️⃣"]

            if goals.isEmpty {
                // Empty state with AI suggestion
                VStack(spacing: 16) {
                    Button(action: { showingCreateSheet = true }) {
                        HStack {
                            Spacer()
                            Image(systemName: "plus")
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textTertiary)
                            Text("Tap to add goal")
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                            Spacer()
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 20)
                    }
                    .buttonStyle(.plain)

                    // AI goal generation button
                    Button(action: { triggerGoalGeneration() }) {
                        HStack(spacing: 6) {
                            if isGeneratingGoal {
                                ProgressView()
                                    .scaleEffect(0.6)
                                    .frame(width: 12, height: 12)
                            } else {
                                Image(systemName: "sparkles")
                                    .scaledFont(size: 12)
                            }
                            Text(isGeneratingGoal ? "Generating..." : "Generate AI Goal")
                                .scaledFont(size: 12, weight: .medium)
                        }
                        .foregroundColor(OmiColors.purplePrimary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(OmiColors.purplePrimary.opacity(0.1))
                        )
                    }
                    .buttonStyle(.plain)
                    .disabled(isGeneratingGoal)
                }
                .padding(.vertical, 12)
            } else {
                // Goals list
                VStack(spacing: 12) {
                    ForEach(Array(goals.enumerated()), id: \.element.id) { index, goal in
                        GoalRowView(
                            goal: goal,
                            index: index,
                            numberEmoji: index < numberEmojis.count ? numberEmojis[index] : "\(index + 1)",
                            onTap: { editingGoal = goal },
                            onUpdateProgress: { value in onUpdateProgress(goal, value) },
                            onDelete: { onDeleteGoal(goal) },
                            onGetAdvice: {
                                selectedGoalForAdvice = goal
                            }
                        )
                    }
                }
            }
        }
        .padding(16)
        .frame(maxHeight: .infinity, alignment: .topLeading)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(OmiColors.backgroundTertiary.opacity(0.3))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(OmiColors.backgroundTertiary.opacity(0.5), lineWidth: 1)
                )
        )
        .sheet(isPresented: $showingCreateSheet) {
            GoalEditSheet(
                goal: nil,
                onSave: { title, current, target in
                    onCreateGoal(title, current, target)
                },
                onDelete: nil,
                onDismiss: { showingCreateSheet = false }
            )
        }
        .sheet(item: $editingGoal) { goal in
            GoalEditSheet(
                goal: goal,
                onSave: { title, current, target in
                    onUpdateProgress(goal, current)
                },
                onDelete: {
                    onDeleteGoal(goal)
                },
                onDismiss: { editingGoal = nil }
            )
        }
        .sheet(item: $selectedGoalForAdvice) { goal in
            GoalAdviceSheet(
                goal: goal,
                onDismiss: { selectedGoalForAdvice = nil }
            )
        }
        .sheet(isPresented: $showingHistory) {
            GoalsHistoryPage(onDismiss: { showingHistory = false })
                .frame(width: 480, height: 500)
        }
    }

    private func triggerGoalGeneration() {
        isGeneratingGoal = true
        Task {
            await GoalGenerationService.shared.generateNow()
            isGeneratingGoal = false
        }
    }
}

// MARK: - Goal Row View

struct GoalRowView: View {
    let goal: Goal
    let index: Int
    let numberEmoji: String
    let onTap: () -> Void
    let onUpdateProgress: (Double) -> Void
    let onDelete: () -> Void
    var onGetAdvice: (() -> Void)? = nil

    @State private var isHovering = false
    @State private var isDragging = false
    @State private var dragValue: Double? = nil
    @State private var isExpanded = false
    @State private var linkedTasks: [TaskActionItem] = []
    @State private var hasLoadedTasks = false

    /// The progress fraction (0-1) to display, using drag value when active
    private var displayProgress: Double {
        if let dv = dragValue {
            return min(max(dv, 0), 1)
        }
        return min(goal.progress / 100.0, 1.0)
    }

    private var progressColor: Color {
        let progress = displayProgress
        if progress >= 0.8 {
            return Color(red: 0.133, green: 0.773, blue: 0.369) // #22C55E Green
        } else if progress >= 0.6 {
            return Color(red: 0.518, green: 0.8, blue: 0.086) // #84CC16 Lime
        } else if progress >= 0.4 {
            return Color(red: 0.984, green: 0.749, blue: 0.141) // #FBBF24 Yellow
        } else if progress >= 0.2 {
            return Color(red: 0.976, green: 0.451, blue: 0.086) // #F97316 Orange
        } else {
            return OmiColors.textTertiary
        }
    }

    private var dragProgressText: String {
        let currentVal: Double
        if let dv = dragValue {
            let raw = goal.minValue + dv * (goal.maxValue - goal.minValue)
            currentVal = max(goal.minValue, min(raw, goal.maxValue))
        } else {
            currentVal = goal.currentValue
        }
        let current = currentVal == currentVal.rounded()
            ? String(format: "%.0f", currentVal)
            : String(format: "%.1f", currentVal)
        let target = goal.targetValue == goal.targetValue.rounded()
            ? String(format: "%.0f", goal.targetValue)
            : String(format: "%.1f", goal.targetValue)
        return "\(current)/\(target)"
    }

    var body: some View {
        HStack(spacing: 12) {
            // Number icon - tapping opens edit sheet
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundTertiary.opacity(0.6))
                    .frame(width: 32, height: 32)
                Text(numberEmoji)
                    .scaledFont(size: 16)
            }
            .onTapGesture { onTap() }

            // Content
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(goal.title)
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                        .lineLimit(1)
                        .onTapGesture { onTap() }

                    Spacer()

                    // Expand/collapse button (if has description or linked tasks)
                    if goal.description != nil || !linkedTasks.isEmpty {
                        Button(action: {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                isExpanded.toggle()
                            }
                        }) {
                            Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                                .scaledFont(size: 9, weight: .medium)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)
                    }

                    // Advice button (shown on hover)
                    if isHovering, let onGetAdvice = onGetAdvice {
                        Button(action: onGetAdvice) {
                            Image(systemName: "lightbulb.fill")
                                .scaledFont(size: 11)
                                .foregroundColor(.yellow)
                        }
                        .buttonStyle(.plain)
                        .transition(.opacity)
                    }

                    // Progress value (current/target)
                    Text(dragProgressText)
                        .scaledFont(size: 11)
                        .foregroundColor(isDragging ? OmiColors.textPrimary : OmiColors.textTertiary)
                        .animation(.easeInOut(duration: 0.15), value: isDragging)
                }

                // Progress bar with drag gesture
                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        // Background track - visible light gray
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Color.white.opacity(0.12))
                            .frame(height: isDragging ? 8 : 6)

                        // Progress fill
                        RoundedRectangle(cornerRadius: 3)
                            .fill(progressColor)
                            .frame(
                                width: max(0, geometry.size.width * displayProgress),
                                height: isDragging ? 8 : 6
                            )

                        // Drag thumb - always visible
                        Circle()
                            .fill(.white)
                            .frame(width: 14, height: 14)
                            .shadow(color: .black.opacity(0.25), radius: 2, y: 1)
                            .offset(x: max(0, min(geometry.size.width * displayProgress - 7, geometry.size.width - 14)))
                    }
                    .frame(maxHeight: .infinity)
                    .contentShape(Rectangle())
                    .gesture(
                        DragGesture(minimumDistance: 0)
                            .onChanged { value in
                                isDragging = true
                                let fraction = value.location.x / geometry.size.width
                                dragValue = min(max(fraction, 0), 1)
                            }
                            .onEnded { _ in
                                if let dv = dragValue {
                                    let finalValue = goal.minValue + dv * (goal.maxValue - goal.minValue)
                                    let clampedValue = max(goal.minValue, min(finalValue, goal.maxValue))
                                    let roundedValue = (clampedValue * 10).rounded() / 10
                                    onUpdateProgress(roundedValue)
                                }
                                isDragging = false
                                dragValue = nil
                            }
                    )
                }
                .frame(height: 18)
                .animation(.easeInOut(duration: 0.15), value: isDragging)

                // Expanded section: description + linked tasks
                if isExpanded {
                    VStack(alignment: .leading, spacing: 8) {
                        // Description
                        if let desc = goal.description, !desc.isEmpty {
                            Text(desc)
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textSecondary)
                                .lineLimit(3)
                        }

                        // Linked tasks
                        if !linkedTasks.isEmpty {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Linked Tasks")
                                    .scaledFont(size: 10, weight: .semibold)
                                    .foregroundColor(OmiColors.textTertiary)
                                    .textCase(.uppercase)

                                ForEach(linkedTasks) { task in
                                    HStack(spacing: 6) {
                                        Image(systemName: task.completed ? "checkmark.circle.fill" : "circle")
                                            .scaledFont(size: 11)
                                            .foregroundColor(task.completed ? Color(red: 0.133, green: 0.773, blue: 0.369) : OmiColors.textTertiary)

                                        Text(task.description)
                                            .scaledFont(size: 12)
                                            .foregroundColor(task.completed ? OmiColors.textTertiary : OmiColors.textPrimary)
                                            .strikethrough(task.completed)
                                            .lineLimit(1)
                                    }
                                }
                            }
                        }
                    }
                    .padding(.top, 2)
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(OmiColors.backgroundTertiary.opacity(isHovering ? 0.5 : 0.3))
        )
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.15)) {
                isHovering = hovering
            }
        }
        .task {
            guard !hasLoadedTasks else { return }
            hasLoadedTasks = true
            await loadLinkedTasks()
        }
    }

    private func loadLinkedTasks() async {
        do {
            let response = try await APIClient.shared.getActionItems(limit: 100, completed: nil)
            linkedTasks = response.items.filter { $0.goalId == goal.id }
        } catch {
            // Silently fail — linked tasks are supplementary
        }
    }

    // goalEmoji computed property commented out — replaced with numbered icons
    // private var goalEmoji: String { ... }
}

// MARK: - Goal Edit Sheet

struct GoalEditSheet: View {
    let goal: Goal?
    let onSave: (String, Double, Double) -> Void
    let onDelete: (() -> Void)?
    let onDismiss: () -> Void

    @State private var title: String = ""
    @State private var currentValue: String = "0"
    @State private var targetValue: String = "100"
    @State private var selectedEmoji: String = "🎯"

    private let availableEmojis = [
        "🎯", "💪", "📚", "💰", "🏃", "🧘", "💡", "🔥",
        "⭐", "🚀", "💎", "🏆", "📈", "❤️", "🎨", "🎵",
        "✈️", "🏠", "🌱", "⏰"
    ]

    var isNewGoal: Bool { goal == nil }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text(isNewGoal ? "Add Goal" : "Edit Goal")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 28, height: 28)
                        .background(OmiColors.backgroundTertiary.opacity(0.5))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 20)
            .padding(.top, 20)
            .padding(.bottom, 16)

            Divider()
                .background(OmiColors.backgroundTertiary)

            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Emoji selector commented out — goals now use numbered icons
                    // if !isNewGoal { ... }

                    // Title field
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Goal Title")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)

                        TextField("Enter goal title", text: $title)
                            .textFieldStyle(.plain)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textPrimary)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 12)
                            .background(
                                RoundedRectangle(cornerRadius: 10)
                                    .fill(OmiColors.backgroundTertiary.opacity(0.5))
                            )
                    }

                    // Current & Target fields
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Current")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)

                            TextField("0", text: $currentValue)
                                .textFieldStyle(.plain)
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textPrimary)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 12)
                                .background(
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(OmiColors.backgroundTertiary.opacity(0.5))
                                )
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Target")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textTertiary)

                            TextField("100", text: $targetValue)
                                .textFieldStyle(.plain)
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textPrimary)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 12)
                                .background(
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(OmiColors.backgroundTertiary.opacity(0.5))
                                )
                        }
                    }
                }
                .padding(20)
            }

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Actions
            HStack(spacing: 12) {
                // Delete button (only for existing goals)
                if !isNewGoal, let onDelete = onDelete {
                    Button(action: {
                        onDelete()
                        onDismiss()
                    }) {
                        Text("Delete")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(.red)
                    }
                    .buttonStyle(.plain)
                }

                Spacer()

                // Cancel button
                Button(action: onDismiss) {
                    Text("Cancel")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)

                // Save button
                Button(action: {
                    let current = Double(currentValue) ?? 0
                    let target = Double(targetValue) ?? 100
                    onSave(title, current, target)
                    onDismiss()
                }) {
                    Text(isNewGoal ? "Add Goal" : "Save")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(.white)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(OmiColors.purplePrimary)
                        )
                }
                .buttonStyle(.plain)
                .disabled(title.isEmpty)
                .opacity(title.isEmpty ? 0.5 : 1)
            }
            .padding(20)
        }
        .frame(width: 400, height: isNewGoal ? 320 : 420)
        .background(OmiColors.backgroundSecondary)
        .onAppear {
            if let goal = goal {
                title = goal.title
                currentValue = goal.currentValue == goal.currentValue.rounded()
                    ? String(format: "%.0f", goal.currentValue)
                    : String(format: "%.1f", goal.currentValue)
                targetValue = goal.targetValue == goal.targetValue.rounded()
                    ? String(format: "%.0f", goal.targetValue)
                    : String(format: "%.1f", goal.targetValue)
            }
        }
    }
}

// MARK: - Goal Advice Sheet

struct GoalAdviceSheet: View {
    let goal: Goal
    let onDismiss: () -> Void

    @State private var isLoading = true
    @State private var advice: String? = nil
    @State private var errorMessage: String? = nil

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                HStack(spacing: 8) {
                    Image(systemName: "lightbulb.fill")
                        .scaledFont(size: 16)
                        .foregroundColor(.yellow)
                    Text("Goal Advice")
                        .scaledFont(size: 18, weight: .semibold)
                        .foregroundColor(OmiColors.textPrimary)
                }

                Spacer()

                Button(action: onDismiss) {
                    Image(systemName: "xmark")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 28, height: 28)
                        .background(OmiColors.backgroundTertiary.opacity(0.5))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 20)
            .padding(.top, 20)
            .padding(.bottom, 16)

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Goal info
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(goal.title)
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                        .lineLimit(1)

                    Text("\(Int(goal.currentValue))/\(Int(goal.targetValue)) (\(Int(goal.progress))%)")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                // Progress indicator
                ZStack {
                    Circle()
                        .stroke(OmiColors.backgroundTertiary, lineWidth: 3)
                    Circle()
                        .trim(from: 0, to: min(goal.progress / 100, 1.0))
                        .stroke(OmiColors.purplePrimary, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                }
                .frame(width: 36, height: 36)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(OmiColors.backgroundTertiary.opacity(0.3))

            // Content
            VStack(spacing: 16) {
                if isLoading {
                    VStack(spacing: 12) {
                        ProgressView()
                            .scaleEffect(1.2)
                        Text("Getting personalized advice...")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let error = errorMessage {
                    VStack(spacing: 12) {
                        Image(systemName: "exclamationmark.triangle")
                            .scaledFont(size: 32)
                            .foregroundColor(.orange)
                        Text(error)
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textSecondary)
                            .multilineTextAlignment(.center)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if let advice = advice {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("This week's action:")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)

                        Text(advice)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(20)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Actions
            HStack(spacing: 12) {
                // Refresh button
                Button(action: loadAdvice) {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.clockwise")
                            .scaledFont(size: 12)
                        Text("Refresh")
                    }
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
                .disabled(isLoading)

                Spacer()

                // Done button
                Button(action: onDismiss) {
                    Text("Done")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(.white)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(OmiColors.purplePrimary)
                        )
                }
                .buttonStyle(.plain)
            }
            .padding(20)
        }
        .frame(width: 400, height: 380)
        .background(OmiColors.backgroundSecondary)
        .onAppear {
            loadAdvice()
        }
    }

    private func loadAdvice() {
        isLoading = true
        errorMessage = nil

        Task {
            do {
                let result = try await GoalsAIService.shared.getGoalAdvice(goal: goal)
                await MainActor.run {
                    advice = result
                    isLoading = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }
        }
    }
}

#Preview {
    GoalsWidget(
        goals: [],
        onCreateGoal: { _, _, _ in },
        onUpdateProgress: { _, _ in },
        onDeleteGoal: { _ in }
    )
    .frame(width: 350)
    .padding()
    .background(OmiColors.backgroundPrimary)
}
