import SwiftUI

// MARK: - Task Classification Badge

/// Displays a task tag as-is
struct TaskClassificationBadge: View {
    let category: String

    var body: some View {
        Text(category.capitalized)
            .scaledFont(size: 10, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)
    }
}

// MARK: - Agent Status Indicator

/// Shows the status of a Claude agent working on a task
/// Main click opens the detail modal; terminal icon opens Terminal directly
/// Shows a launch button when no session exists
struct AgentStatusIndicator: View {
    let task: TaskActionItem
    @Binding var showAgentDetail: Bool
    var onLaunchWithChat: ((TaskActionItem) -> Void)? = nil
    @ObservedObject private var manager = TaskAgentManager.shared

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
        HStack(spacing: 4) {
            // Terminal icon — always visible, opens detail modal
            Button {
                showAgentDetail = true
            } label: {
                Image(systemName: "terminal")
                    .scaledFont(size: 10)
                    .foregroundColor(OmiColors.textTertiary)
                    .frame(width: 20, height: 20)
            }
            .buttonStyle(.plain)
            .help("View Agent Details")

            if let session = session {
                // Status text — opens detail modal
                Button {
                    showAgentDetail = true
                } label: {
                    HStack(spacing: 4) {
                        statusIcon(for: session.status)

                        Text(statusText)
                            .scaledFont(size: 10, weight: .medium)
                    }
                    .foregroundColor(statusColor(for: session.status))
                }
                .buttonStyle(.plain)
                .help("View Agent Details")
            } else {
                // Run Agent button — launches immediately
                AgentLaunchButton(task: task, onLaunchWithChat: onLaunchWithChat)
            }
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
                .scaledFont(size: 10)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .scaledFont(size: 10)
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

// MARK: - Agent Launch Button

/// Button to launch a Claude agent for a task
struct AgentLaunchButton: View {
    let task: TaskActionItem
    var onLaunchWithChat: ((TaskActionItem) -> Void)? = nil
    @ObservedObject private var manager = TaskAgentManager.shared
    @ObservedObject private var settings = TaskAgentSettings.shared
    @State private var isLaunching = false
    @State private var showError = false
    @State private var errorMessage = ""

    private var canLaunch: Bool {
        settings.isEnabled && !manager.hasSession(for: task.id)
    }

    var body: some View {
        if canLaunch {
            Button {
                launchAgent()
            } label: {
                HStack(spacing: 4) {
                    if isLaunching {
                        ProgressView()
                            .scaleEffect(0.6)
                            .frame(width: 12, height: 12)
                    }

                    Text(isLaunching ? "Launching..." : "Run Agent")
                        .scaledFont(size: 10, weight: .medium)
                }
                .foregroundColor(OmiColors.textSecondary)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(
                    Capsule()
                        .fill(OmiColors.textSecondary.opacity(0.15))
                )
            }
            .buttonStyle(.plain)
            .disabled(isLaunching)
            .alert("Agent Error", isPresented: $showError) {
                Button("OK") {}
            } message: {
                Text(errorMessage)
            }
        }
    }

    private func launchAgent() {
        isLaunching = true

        Task {
            do {
                // Re-fetch the latest task from the store in case the user edited it
                let store = TasksStore.shared
                let latestTask = store.incompleteTasks.first(where: { $0.id == task.id })
                    ?? store.completedTasks.first(where: { $0.id == task.id })
                    ?? task

                let context = TaskAgentContext()
                try await manager.launchAgent(for: latestTask, context: context)

                // Also open chat panel for this task
                onLaunchWithChat?(latestTask)
            } catch {
                errorMessage = error.localizedDescription
                showError = true
            }
            isLaunching = false
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
                VStack(alignment: .leading, spacing: 20) {
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
                .padding(20)
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
            VStack(alignment: .leading, spacing: 4) {
                Text("Task Agent")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                HStack(spacing: 4) {
                    ForEach(task.tags.prefix(3), id: \.self) { tag in
                        TaskClassificationBadge(category: tag)
                    }
                }
            }

            Spacer()

            DismissButton(action: dismissSheet)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 16)
    }

    private var taskInfoSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Task")
                .scaledFont(size: 13, weight: .semibold)
                .foregroundColor(OmiColors.textSecondary)

            Text(task.description)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textPrimary)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(OmiColors.backgroundSecondary)
                )
        }
    }

    private func agentStatusSection(session: TaskAgentManager.AgentSession) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Agent Status")
                .scaledFont(size: 13, weight: .semibold)
                .foregroundColor(OmiColors.textSecondary)

            HStack(spacing: 16) {
                // Status badge
                HStack(spacing: 8) {
                    Image(systemName: session.status.icon)
                        .scaledFont(size: 16)
                        .foregroundColor(statusColor(for: session.status))

                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Text(session.status.displayName)
                                .scaledFont(size: 14, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)

                            if !session.editedFiles.isEmpty {
                                Text("\(session.editedFiles.count) files edited")
                                    .scaledFont(size: 11, weight: .medium)
                                    .foregroundColor(OmiColors.textSecondary)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(
                                        Capsule()
                                            .fill(OmiColors.textSecondary.opacity(0.15))
                                    )
                            }
                        }

                        Text("Session: \(session.sessionName)")
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }

                Spacer()

                // Action buttons
                HStack(spacing: 8) {
                    Button {
                        manager.openInTerminal(taskId: task.id)
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "terminal")
                                .scaledFont(size: 11)
                            Text("Open Terminal")
                                .scaledFont(size: 12, weight: .medium)
                        }
                        .foregroundColor(OmiColors.textSecondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(OmiColors.textSecondary.opacity(0.1))
                        )
                    }
                    .buttonStyle(.plain)

                    if session.status == .processing || session.status == .pending || session.status == .editing {
                        Button {
                            manager.stopAgent(taskId: task.id)
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "stop.fill")
                                    .scaledFont(size: 11)
                                Text("Stop")
                                    .scaledFont(size: 12, weight: .medium)
                            }
                            .foregroundColor(OmiColors.textSecondary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(OmiColors.textSecondary.opacity(0.1))
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    private var launchSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Agent Status")
                .scaledFont(size: 13, weight: .semibold)
                .foregroundColor(OmiColors.textSecondary)

            VStack(spacing: 12) {
                Image(systemName: "terminal")
                    .scaledFont(size: 32)
                    .foregroundColor(OmiColors.textTertiary)

                Text("No agent running")
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)

                Text("Launch a Claude agent to analyze this task and create an implementation plan.")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                    .multilineTextAlignment(.center)

                AgentLaunchButton(task: task)
            }
            .frame(maxWidth: .infinity)
            .padding(20)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    private var disabledSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Agent Status")
                .scaledFont(size: 13, weight: .semibold)
                .foregroundColor(OmiColors.textSecondary)

            VStack(spacing: 12) {
                Image(systemName: "terminal")
                    .scaledFont(size: 32)
                    .foregroundColor(OmiColors.textTertiary)

                Text("Task Agent Disabled")
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)

                Text("Enable Task Agent in settings to launch Claude agents for code-related tasks.")
                    .scaledFont(size: 12)
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
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)
                }
                .buttonStyle(.plain)
            }
            .frame(maxWidth: .infinity)
            .padding(20)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(OmiColors.backgroundSecondary)
            )
        }
    }

    private func promptSection(session: TaskAgentManager.AgentSession) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Prompt")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)

                Spacer()

                if !isEditingPrompt {
                    Button {
                        editedPrompt = session.prompt
                        isEditingPrompt = true
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "pencil")
                                .scaledFont(size: 10)
                            Text("Edit")
                                .scaledFont(size: 11, weight: .medium)
                        }
                        .foregroundColor(OmiColors.textSecondary)
                    }
                    .buttonStyle(.plain)
                }
            }

            if isEditingPrompt {
                VStack(spacing: 8) {
                    TextEditor(text: $editedPrompt)
                        .scaledFont(size: 12, design: .monospaced)
                        .frame(minHeight: 150)
                        .padding(8)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(OmiColors.backgroundSecondary)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
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
                    .scaledFont(size: 12, design: .monospaced)
                    .foregroundColor(OmiColors.textSecondary)
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(OmiColors.backgroundSecondary)
                    )
            }
        }
    }

    private func outputSection(output: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Agent Output")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(OmiColors.textSecondary)

                Spacer()

                Button {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(output, forType: .string)
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "doc.on.doc")
                            .scaledFont(size: 10)
                        Text("Copy")
                            .scaledFont(size: 11, weight: .medium)
                    }
                    .foregroundColor(OmiColors.textSecondary)
                }
                .buttonStyle(.plain)
            }

            ScrollView {
                Text(output)
                    .scaledFont(size: 11, design: .monospaced)
                    .foregroundColor(OmiColors.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 200)
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 8)
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
        .padding(20)
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

#Preview("Classification Badge") {
    VStack(spacing: 8) {
        ForEach(["feature", "bug", "code", "work", "personal", "research"], id: \.self) { category in
            TaskClassificationBadge(category: category)
        }
    }
    .padding()
}

#Preview("Agent Status") {
    VStack(spacing: 16) {
        AgentStatusIndicator(task: TaskActionItem(id: "test-1", description: "Test task", completed: false, createdAt: Date()), showAgentDetail: .constant(false))
    }
    .padding()
}
