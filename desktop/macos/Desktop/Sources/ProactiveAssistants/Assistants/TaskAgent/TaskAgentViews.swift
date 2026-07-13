import SwiftUI
import OmiTheme

// MARK: - Task Classification Badge

/// Displays a task tag as-is
struct TaskClassificationBadge: View {
    let category: String

    var body: some View {
        Text(category.capitalized)
            .scaledFont(size: OmiType.micro, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)
    }
}

// MARK: - Agent Status Indicator

/// Shows the status of a Claude agent working on a task.
/// Terminal icon launches the agent (if none) or opens Terminal directly (if running/done).
/// No detail modal — purely a quick-action control.
struct AgentStatusIndicator: View {
    let task: TaskActionItem
    @ObservedObject private var manager = TaskAgentManager.shared
    @ObservedObject private var settings = TaskAgentSettings.shared
    @State private var isLaunching = false
    @State private var showError = false
    @State private var errorMessage = ""

    private var taskId: String { task.id }

    private var session: TaskAgentManager.AgentSession? {
        manager.getSession(for: taskId)
    }

    private var statusText: String {
        guard let session = session else { return "" }
        let fileCount = session.editedFiles.count
        switch session.status {
        case .pending:
            return "Starting..."
        case .processing:
            return "Running..."
        case .editing:
            return fileCount > 0 ? "Editing (\(fileCount))" : "Editing..."
        case .completed:
            return fileCount > 0 ? "Done (\(fileCount) files)" : "Done"
        case .failed:
            return "Failed"
        }
    }

    var body: some View {
        HStack(spacing: OmiSpacing.xxs) {
            if let session = session {
                // Has a session — terminal icon opens Terminal directly
                Button {
                    manager.openInTerminal(taskId: taskId)
                } label: {
                    Image(systemName: "terminal")
                        .scaledFont(size: OmiType.micro)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 20, height: 20)
                }
                .buttonStyle(.plain)
                .help("Open in Terminal")

                // Status text
                HStack(spacing: OmiSpacing.xxs) {
                    statusIcon(for: session.status)

                    Text(statusText)
                        .scaledFont(size: OmiType.micro, weight: .medium)
                }
                .foregroundColor(statusColor(for: session.status))
            } else if settings.isEnabled {
                // No session — terminal icon launches the agent
                Button {
                    launchAgent()
                } label: {
                    HStack(spacing: OmiSpacing.xxs) {
                        if isLaunching {
                            ProgressView()
                                .scaleEffect(0.5)
                                .frame(width: 12, height: 12)
                        } else {
                            Image(systemName: "terminal")
                                .scaledFont(size: OmiType.micro)
                                .foregroundColor(OmiColors.textTertiary)
                        }

                        Text(isLaunching ? "Launching..." : "Run Agent")
                            .scaledFont(size: OmiType.micro, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)
                    }
                }
                .buttonStyle(.plain)
                .disabled(isLaunching)
                .help("Launch Claude agent for this task")
                .alert("Agent Error", isPresented: $showError) {
                    Button("OK") {}
                } message: {
                    Text(errorMessage)
                }
            }
        }
    }

    private func launchAgent() {
        isLaunching = true

        Task {
            do {
                let store = TasksStore.shared
                let latestTask = store.incompleteTasks.first(where: { $0.id == task.id })
                    ?? store.completedTasks.first(where: { $0.id == task.id })
                    ?? task

                let context = TaskAgentContext()
                try await manager.launchAgent(for: latestTask, context: context)
            } catch {
                errorMessage = error.localizedDescription
                showError = true
            }
            isLaunching = false
        }
    }

    @ViewBuilder
    private func statusIcon(for status: TaskAgentManager.AgentStatus) -> some View {
        switch status {
        case .pending, .processing, .editing:
            ProgressView()
                .scaleEffect(0.5)
                .frame(width: 10, height: 10)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .scaledFont(size: OmiType.micro)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .scaledFont(size: OmiType.micro)
        }
    }

    private func statusColor(for status: TaskAgentManager.AgentStatus) -> Color {
        switch status {
        case .pending: return OmiColors.textTertiary
        case .processing: return OmiColors.textSecondary
        case .editing: return OmiColors.textSecondary
        case .completed: return OmiColors.textPrimary
        case .failed: return OmiColors.textTertiary
        }
    }
}

// MARK: - Task Agent Detail View

/// Detailed view showing agent status, prompt, and output for a task
struct TaskAgentDetailView: View {
    let task: TaskActionItem
    var onDismiss: (() -> Void)? = nil

    @ObservedObject private var manager = TaskAgentManager.shared
    @ObservedObject private var settings = TaskAgentSettings.shared
    @Environment(\.dismiss) private var environmentDismiss

    @State private var editedPrompt: String = ""
    @State private var isEditingPrompt = false
    @State private var isRestarting = false

    private var session: TaskAgentManager.AgentSession? {
        manager.getSession(for: task.id)
    }

    private func dismissSheet() {
        if let onDismiss = onDismiss {
            onDismiss()
        } else {
            environmentDismiss()
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            header

            Divider()

            // Content
            ScrollView {
                VStack(alignment: .leading, spacing: OmiSpacing.xl) {
                    // Task Info
                    taskInfoSection

                    // Agent Status
                    if let session = session {
                        agentStatusSection(session: session)
                    } else if settings.isEnabled {
                        launchSection
                    } else {
                        disabledSection
                    }

                    // Prompt Section
                    if let session = session {
                        promptSection(session: session)
                    }

                    // Output Section
                    if let session = session, let output = session.output, !output.isEmpty {
                        outputSection(output: output)
                    }
                }
                .padding(OmiSpacing.xl)
            }

            Divider()

            // Footer
            footer
        }
        .frame(width: 550, height: 600)
        .background(OmiColors.backgroundPrimary)
        .onAppear {
            if let session = session {
                editedPrompt = session.prompt
            }
        }
    }

    // MARK: - Sections

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                Text("Task Agent")
                    .scaledFont(size: OmiType.subheading, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                HStack(spacing: OmiSpacing.xxs) {
                    ForEach(task.tags.prefix(3), id: \.self) { tag in
                        TaskClassificationBadge(category: tag)
                    }
                }
            }

            Spacer()

            DismissButton(action: dismissSheet)
        }
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.lg)
    }

    private var taskInfoSection: some View {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("Task")
                .scaledFont(size: OmiType.body, weight: .semibold)
                .foregroundColor(OmiColors.textSecondary)

            Text(task.description)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textPrimary)
                .padding(OmiSpacing.md)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                        .fill(OmiColors.backgroundSecondary)
                )
        }
    }

    private func agentStatusSection(session: TaskAgentManager.AgentSession) -> some View {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
            Text("Agent Status")
                .scaledFont(size: OmiType.body, weight: .semibold)
                .foregroundColor(OmiColors.textSecondary)

            HStack(spacing: OmiSpacing.lg) {
                // Status badge
                HStack(spacing: OmiSpacing.sm) {
                    Image(systemName: session.status.icon)
                        .scaledFont(size: OmiType.subheading)
                        .foregroundColor(statusColor(for: session.status))

                    VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                        HStack(spacing: OmiSpacing.xs) {
                            Text(session.status.displayName)
                                .scaledFont(size: OmiType.body, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)

                            if !session.editedFiles.isEmpty {
                                Text("\(session.editedFiles.count) files edited")
                                    .scaledFont(size: OmiType.caption, weight: .medium)
                                    .foregroundColor(OmiColors.textSecondary)
                                    .padding(.horizontal, OmiSpacing.xs)
                                    .padding(.vertical, OmiSpacing.hairline)
                                    .background(
                                        Capsule()
                                            .fill(OmiColors.textSecondary.opacity(0.15))
                                    )
                            }
                        }

                        Text("Session: \(session.sessionName)")
                            .scaledFont(size: OmiType.caption)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }

                Spacer()

                // Action buttons
                HStack(spacing: OmiSpacing.sm) {
                    Button {
                        manager.openInTerminal(taskId: task.id)
                    } label: {
                        HStack(spacing: OmiSpacing.xxs) {
                            Image(systemName: "terminal")
                                .scaledFont(size: OmiType.caption)
                            Text("Open Terminal")
                                .scaledFont(size: OmiType.caption, weight: .medium)
                        }
                        .foregroundColor(OmiColors.textSecondary)
                        .padding(.horizontal, OmiSpacing.sm)
                        .padding(.vertical, OmiSpacing.xs)
                        .background(
                            RoundedRectangle(cornerRadius: OmiChrome.badgeRadius)
                                .fill(OmiColors.textSecondary.opacity(0.1))
                        )
                    }
                    .buttonStyle(.plain)

                    if session.status == .processing || session.status == .pending || session.status == .editing {
                        Button {
                            manager.stopAgent(taskId: task.id)
                        } label: {
                            HStack(spacing: OmiSpacing.xxs) {
                                Image(systemName: "stop.fill")
                                    .scaledFont(size: OmiType.caption)
                                Text("Stop")
                                    .scaledFont(size: OmiType.caption, weight: .medium)
                            }
                            .foregroundColor(OmiColors.textSecondary)
                            .padding(.horizontal, OmiSpacing.sm)
                            .padding(.vertical, OmiSpacing.xs)
                            .background(
                                RoundedRectangle(cornerRadius: OmiChrome.badgeRadius)
                                    .fill(OmiColors.textSecondary.opacity(0.1))
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(OmiSpacing.md)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    private var launchSection: some View {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
            Text("Agent Status")
                .scaledFont(size: OmiType.body, weight: .semibold)
                .foregroundColor(OmiColors.textSecondary)

            VStack(spacing: OmiSpacing.md) {
                Image(systemName: "terminal")
                    .scaledFont(size: 32)
                    .foregroundColor(OmiColors.textTertiary)

                Text("No agent running")
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)

                Text("Launch a Claude agent to analyze this task and create an implementation plan.")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity)
            .padding(OmiSpacing.xl)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    private var disabledSection: some View {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
            Text("Agent Status")
                .scaledFont(size: OmiType.body, weight: .semibold)
                .foregroundColor(OmiColors.textSecondary)

            VStack(spacing: OmiSpacing.md) {
                Image(systemName: "terminal")
                    .scaledFont(size: 32)
                    .foregroundColor(OmiColors.textTertiary)

                Text("Task Agent Disabled")
                    .scaledFont(size: OmiType.body, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)

                Text("Enable Task Agent in settings to launch Claude agents for code-related tasks.")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)

                Button {
                    NotificationCenter.default.post(
                        name: .navigateToTaskSettings,
                        object: nil
                    )
                    dismissSheet()
                } label: {
                    Text("Open Settings")
                        .scaledFont(size: OmiType.caption, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)
                }
                .buttonStyle(.plain)
            }
            .frame(maxWidth: .infinity)
            .padding(OmiSpacing.xl)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    private func promptSection(session: TaskAgentManager.AgentSession) -> some View {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            HStack {
                Text("Prompt")
                    .scaledFont(size: OmiType.body, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)

                Spacer()

                if !isEditingPrompt {
                    Button {
                        editedPrompt = session.prompt
                        isEditingPrompt = true
                    } label: {
                        HStack(spacing: OmiSpacing.xxs) {
                            Image(systemName: "pencil")
                                .scaledFont(size: OmiType.micro)
                            Text("Edit")
                                .scaledFont(size: OmiType.caption, weight: .medium)
                        }
                        .foregroundColor(OmiColors.textSecondary)
                    }
                    .buttonStyle(.plain)
                }
            }

            if isEditingPrompt {
                VStack(spacing: OmiSpacing.sm) {
                    TextEditor(text: $editedPrompt)
                        .scaledFont(size: OmiType.caption, design: .monospaced)
                        .frame(minHeight: 150)
                        .padding(OmiSpacing.sm)
                        .background(
                            RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                                .fill(OmiColors.backgroundSecondary)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                                .stroke(OmiColors.border, lineWidth: 1)
                        )

                    HStack {
                        Button("Cancel") {
                            isEditingPrompt = false
                            editedPrompt = session.prompt
                        }
                        .buttonStyle(.bordered)

                        Spacer()

                        Button {
                            Task {
                                await restartWithNewPrompt()
                            }
                        } label: {
                            if isRestarting {
                                ProgressView()
                                    .scaleEffect(0.8)
                            } else {
                                Text("Restart Agent")
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isRestarting || editedPrompt.isEmpty)
                    }
                }
            } else {
                Text(session.prompt)
                    .scaledFont(size: OmiType.caption, design: .monospaced)
                    .foregroundColor(OmiColors.textSecondary)
                    .padding(OmiSpacing.md)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                            .fill(OmiColors.backgroundSecondary)
                    )
            }
        }
    }

    private func outputSection(output: String) -> some View {
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            HStack {
                Text("Agent Output")
                    .scaledFont(size: OmiType.body, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)

                Spacer()

                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(output, forType: .string)
                } label: {
                    HStack(spacing: OmiSpacing.xxs) {
                        Image(systemName: "doc.on.doc")
                            .scaledFont(size: OmiType.micro)
                        Text("Copy")
                            .scaledFont(size: OmiType.caption, weight: .medium)
                    }
                    .foregroundColor(OmiColors.textSecondary)
                }
                .buttonStyle(.plain)
            }

            ScrollView {
                Text(output)
                    .scaledFont(size: OmiType.caption, design: .monospaced)
                    .foregroundColor(OmiColors.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 200)
            .padding(OmiSpacing.md)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                    .fill(Color.black.opacity(0.8))
            )
        }
    }

    private var footer: some View {
        HStack {
            if session != nil {
                Button("Remove Session") {
                    manager.removeSession(taskId: task.id)
                }
                .buttonStyle(.bordered)
                .foregroundColor(OmiColors.textSecondary)
            }

            Spacer()

            Button("Close") {
                dismissSheet()
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(OmiSpacing.xl)
    }

    // MARK: - Helpers

    private func statusColor(for status: TaskAgentManager.AgentStatus) -> Color {
        switch status {
        case .pending: return OmiColors.textTertiary
        case .processing: return OmiColors.textSecondary
        case .editing: return OmiColors.textSecondary
        case .completed: return OmiColors.textPrimary
        case .failed: return OmiColors.textTertiary
        }
    }

    private func restartWithNewPrompt() async {
        isRestarting = true

        do {
            let context = TaskAgentContext()
            try await manager.updatePromptAndRestart(
                taskId: task.id,
                newPrompt: editedPrompt,
                context: context
            )
            isEditingPrompt = false
        } catch {
            // Handle error
        }

        isRestarting = false
    }
}


// MARK: - Preview

#if canImport(PreviewsMacros)
#Preview("Classification Badge") {
    VStack(spacing: OmiSpacing.sm) {
        ForEach(["feature", "bug", "code", "work", "personal", "research"], id: \.self) { category in
            TaskClassificationBadge(category: category)
        }
    }
    .padding()
}
#endif

#if canImport(PreviewsMacros)
#Preview("Agent Status") {
    VStack(spacing: OmiSpacing.lg) {
        AgentStatusIndicator(task: TaskActionItem(id: "test-1", description: "Test task", completed: false, createdAt: Date()))
    }
    .padding()
}
#endif
