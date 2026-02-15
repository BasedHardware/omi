import Foundation
import Combine

/// Manages Claude Code agent sessions for code-related tasks
class TaskAgentManager: ObservableObject {
    static let shared = TaskAgentManager()

    /// Categories that trigger agent execution
    static let agentCategories: Set<String> = ["feature", "bug", "code"]

    /// Active agent sessions: taskId -> session info
    @Published private(set) var activeSessions: [String: AgentSession] = [:]

    private var pollingTasks: [String: Task<Void, Never>] = [:]
    private var cancellables = Set<AnyCancellable>()

    struct AgentSession: Identifiable {
        var id: String { taskId }
        let taskId: String
        let sessionName: String  // tmux session name
        var prompt: String
        var startedAt: Date
        var status: AgentStatus
        var output: String?
        var plan: String?
        var completedAt: Date?
        var editedFiles: [String] = []
    }

    enum AgentStatus: String, CaseIterable {
        case pending = "pending"
        case processing = "processing"
        case editing = "editing"
        case completed = "completed"
        case failed = "failed"

        var displayName: String {
            switch self {
            case .pending: return "Starting..."
            case .processing: return "Running..."
            case .editing: return "Editing..."
            case .completed: return "Done"
            case .failed: return "Failed"
            }
        }

        var icon: String {
            switch self {
            case .pending: return "clock"
            case .processing: return "bolt.fill"
            case .editing: return "pencil"
            case .completed: return "checkmark.circle.fill"
            case .failed: return "xmark.circle.fill"
            }
        }
    }

    private init() {
        logMessage("TaskAgentManager: Initialized")
    }

    // MARK: - Public API

    /// Check if a task should trigger an agent
    func shouldTriggerAgent(for task: TaskActionItem) -> Bool {
        return TaskAgentSettings.shared.isEnabled
    }

    /// Check if a task has an active or completed agent session
    func hasSession(for taskId: String) -> Bool {
        return activeSessions[taskId] != nil
    }

    /// Get session for a task
    func getSession(for taskId: String) -> AgentSession? {
        return activeSessions[taskId]
    }

    /// Launch agent for a task
    func launchAgent(for task: TaskActionItem, context: TaskAgentContext) async throws {
        guard !hasSession(for: task.id) else {
            logMessage("TaskAgentManager: Session already exists for task \(task.id)")
            return
        }

        let sessionName = "omi-task-\(task.id.prefix(8))"
        let prompt = buildPrompt(for: task, context: context)

        logMessage("TaskAgentManager: Launching agent for task \(task.id) (\(task.description))")

        // Create session entry
        let session = AgentSession(
            taskId: task.id,
            sessionName: sessionName,
            prompt: prompt,
            startedAt: Date(),
            status: .pending,
            output: nil,
            plan: nil
        )

        await MainActor.run {
            activeSessions[task.id] = session
        }
        persistSession(session)

        // Launch tmux session with Claude
        do {
            try await launchTmuxSession(sessionName: sessionName, prompt: prompt, workingDir: context.workingDirectory)

            await MainActor.run {
                activeSessions[task.id]?.status = .processing
            }
            if let s = activeSessions[task.id] { persistSession(s) }

            // Start polling for completion
            startPolling(taskId: task.id, sessionName: sessionName)
        } catch {
            logMessage("TaskAgentManager: Failed to launch agent - \(error)")
            await MainActor.run {
                activeSessions[task.id]?.status = .failed
            }
            if let s = activeSessions[task.id] { persistSession(s) }
            throw error
        }
    }

    /// Open session in Terminal
    func openInTerminal(taskId: String) {
        guard let session = activeSessions[taskId] else {
            logMessage("TaskAgentManager: No session found for task \(taskId)")
            return
        }
        logMessage("TaskAgentManager: Opening terminal for \(session.sessionName)")
        openTmuxSessionInTerminal(sessionName: session.sessionName)
    }

    /// Update prompt and restart agent
    func updatePromptAndRestart(taskId: String, newPrompt: String, context: TaskAgentContext) async throws {
        guard let session = activeSessions[taskId] else { return }
        let sessionName = session.sessionName

        logMessage("TaskAgentManager: Restarting agent for task \(taskId) with new prompt")

        // Cancel existing polling
        pollingTasks[taskId]?.cancel()
        pollingTasks[taskId] = nil

        // Kill existing session
        killTmuxSession(sessionName: sessionName)

        // Update session directly in activeSessions
        await MainActor.run {
            activeSessions[taskId]?.prompt = newPrompt
            activeSessions[taskId]?.startedAt = Date()
            activeSessions[taskId]?.status = .pending
            activeSessions[taskId]?.output = nil
            activeSessions[taskId]?.plan = nil
            activeSessions[taskId]?.completedAt = nil
            activeSessions[taskId]?.editedFiles = []
        }
        if let s = activeSessions[taskId] { persistSession(s) }

        try await launchTmuxSession(sessionName: sessionName, prompt: newPrompt, workingDir: context.workingDirectory)

        await MainActor.run {
            activeSessions[taskId]?.status = .processing
        }
        if let s = activeSessions[taskId] { persistSession(s) }

        startPolling(taskId: taskId, sessionName: sessionName)
    }

    /// Stop and remove agent session
    func stopAgent(taskId: String) {
        guard let session = activeSessions[taskId] else { return }

        logMessage("TaskAgentManager: Stopping agent for task \(taskId)")

        // Cancel polling
        pollingTasks[taskId]?.cancel()
        pollingTasks[taskId] = nil

        // Kill tmux session
        killTmuxSession(sessionName: session.sessionName)

        // Remove from active sessions
        activeSessions.removeValue(forKey: taskId)

        // Clear persisted agent state
        Task {
            try? await ActionItemStorage.shared.clearAgentState(taskId: taskId)
        }
    }

    /// Remove completed session (cleanup)
    func removeSession(taskId: String) {
        pollingTasks[taskId]?.cancel()
        pollingTasks[taskId] = nil
        activeSessions.removeValue(forKey: taskId)

        // Clear persisted agent state
        Task {
            try? await ActionItemStorage.shared.clearAgentState(taskId: taskId)
        }
    }

    // MARK: - Private Implementation

    private func buildPrompt(for task: TaskActionItem, context: TaskAgentContext) -> String {
        TaskAgentSettings.shared.buildTaskPrompt(for: task)
    }

    private func launchTmuxSession(sessionName: String, prompt: String, workingDir: String) async throws {
        // Kill any stale tmux session with the same name (e.g. survived an app restart)
        killTmuxSession(sessionName: sessionName)

        // Check if tmux is available (source user's shell config to get full PATH)
        let tmuxCheck = Process()
        tmuxCheck.executableURL = URL(fileURLWithPath: "/bin/zsh")
        tmuxCheck.arguments = ["-c", "source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; which tmux"]
        let tmuxCheckPipe = Pipe()
        tmuxCheck.standardOutput = tmuxCheckPipe
        tmuxCheck.standardError = tmuxCheckPipe

        try tmuxCheck.run()
        tmuxCheck.waitUntilExit()

        guard tmuxCheck.terminationStatus == 0 else {
            throw AgentError.tmuxNotInstalled
        }

        // Check if claude is available (source user's shell config to get full PATH)
        let claudeCheck = Process()
        claudeCheck.executableURL = URL(fileURLWithPath: "/bin/zsh")
        claudeCheck.arguments = ["-c", "source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; which claude"]
        let claudeCheckPipe = Pipe()
        claudeCheck.standardOutput = claudeCheckPipe
        claudeCheck.standardError = claudeCheckPipe

        try claudeCheck.run()
        claudeCheck.waitUntilExit()

        guard claudeCheck.terminationStatus == 0 else {
            throw AgentError.claudeNotInstalled
        }

        // Write prompt to a temp file to avoid escaping issues
        let tempDir = FileManager.default.temporaryDirectory
        let promptFile = tempDir.appendingPathComponent("omi-task-prompt-\(UUID().uuidString).txt")
        try prompt.write(to: promptFile, atomically: true, encoding: .utf8)

        // Escape working directory for shell
        let escapedWorkingDir = workingDir.replacingOccurrences(of: "'", with: "'\\''")

        // Build command that reads prompt from file
        // Source shell profiles INSIDE the tmux session so claude (via nvm) is in PATH
        // Note: \\" produces \" in the output (escaped quote for the shell), NOT just "
        let command = """
        tmux new-session -d -s '\(sessionName)' "source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; cd '\(escapedWorkingDir)' && claude --dangerously-skip-permissions \\"$(cat '\(promptFile.path)')\\" ; rm -f '\(promptFile.path)'"
        """

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-c", "source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; \(command)"]

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe

        try process.run()
        process.waitUntilExit()

        guard process.terminationStatus == 0 else {
            let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            logMessage("TaskAgentManager: tmux launch failed - \(output)")
            throw AgentError.launchFailed(output)
        }

        logMessage("TaskAgentManager: Launched tmux session '\(sessionName)'")

        // Wait for Claude to initialize
        try await Task.sleep(nanoseconds: 3_000_000_000) // 3 seconds
    }

    private func startPolling(taskId: String, sessionName: String) {
        // Cancel any existing polling for this task
        pollingTasks[taskId]?.cancel()

        let task = Task { [weak self] in
            // Track last persisted state to avoid redundant writes
            var lastPersistedStatus: AgentStatus?
            var lastPersistedFileCount = 0

            while !Task.isCancelled {
                guard let self = self else { break }
                let currentStatus = self.activeSessions[taskId]?.status
                guard currentStatus == .processing || currentStatus == .editing else { break }

                try? await Task.sleep(nanoseconds: 5_000_000_000) // 5 seconds

                guard !Task.isCancelled else { break }

                let output = self.readTmuxOutput(sessionName: sessionName)
                let editedFiles = self.parseEditedFiles(from: output)

                await MainActor.run {
                    self.activeSessions[taskId]?.output = output
                    if !editedFiles.isEmpty {
                        self.activeSessions[taskId]?.editedFiles = editedFiles
                    }
                }

                // Check if session has completed (waiting for user input)
                if self.isSessionCompleted(output: output) {
                    await MainActor.run {
                        self.activeSessions[taskId]?.status = .completed
                        self.activeSessions[taskId]?.plan = self.extractPlan(from: output)
                        self.activeSessions[taskId]?.completedAt = Date()
                    }
                    if let s = self.activeSessions[taskId] { self.persistSession(s) }
                    logMessage("TaskAgentManager: Session completed for task \(taskId) (\(editedFiles.count) files edited)")
                    break
                }

                // Update status based on activity
                if !editedFiles.isEmpty {
                    await MainActor.run {
                        if self.activeSessions[taskId]?.status == .processing {
                            self.activeSessions[taskId]?.status = .editing
                        }
                    }
                }

                // Throttled persistence: only persist when status or file count changes
                if let session = self.activeSessions[taskId] {
                    if session.status != lastPersistedStatus || editedFiles.count != lastPersistedFileCount {
                        self.persistSession(session)
                        lastPersistedStatus = session.status
                        lastPersistedFileCount = editedFiles.count
                    }
                }

                // Check if session still exists
                if !self.isSessionAlive(sessionName: sessionName) {
                    await MainActor.run {
                        let status = self.activeSessions[taskId]?.status
                        if status == .processing || status == .editing {
                            // If files were edited before session ended, mark as completed
                            if !editedFiles.isEmpty {
                                self.activeSessions[taskId]?.status = .completed
                                self.activeSessions[taskId]?.completedAt = Date()
                            } else {
                                self.activeSessions[taskId]?.status = .failed
                            }
                        }
                    }
                    if let s = self.activeSessions[taskId] { self.persistSession(s) }
                    logMessage("TaskAgentManager: Session ended for task \(taskId) (\(editedFiles.count) files edited)")
                    break
                }
            }
        }

        pollingTasks[taskId] = task
    }

    private func readTmuxOutput(sessionName: String) -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-c", "source ~/.zprofile 2>/dev/null; tmux capture-pane -t '\(sessionName)' -p -S -500 2>/dev/null"]

        let pipe = Pipe()
        process.standardOutput = pipe

        try? process.run()
        process.waitUntilExit()

        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        return String(data: data, encoding: .utf8) ?? ""
    }

    private func isSessionAlive(sessionName: String) -> Bool {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-c", "source ~/.zprofile 2>/dev/null; tmux has-session -t '\(sessionName)' 2>/dev/null"]

        try? process.run()
        process.waitUntilExit()

        return process.terminationStatus == 0
    }

    private func isSessionCompleted(output: String) -> Bool {
        let lower = output.lowercased()

        // Claude Code plan mode completion markers
        let completionMarkers = [
            "would you like to proceed",           // Claude Code plan mode prompt
            "ready to execute",                     // "written a plan and is ready to execute"
            "ready to implement",
            // Claude Code interactive options (numbered choices shown after plan)
            "yes, clear context and bypass",
            "yes, and bypass permissions",
            "yes, manually approve",
            // Generic Claude completion patterns
            "should i proceed",
            "would you like me to",
            "do you want me to",
            "let me know if",
            "waiting for approval",
            "plan complete",
        ]

        for marker in completionMarkers {
            if lower.contains(marker) {
                return true
            }
        }

        return false
    }

    private func parseEditedFiles(from output: String) -> [String] {
        // Detect files edited by Claude Code from tmux output
        // Claude Code shows patterns like:
        //   ⏺ Update(path/to/file.swift)
        //   ● Update(path/to/file.swift)
        //   ⏺ Write(path/to/file.swift)
        //   Update(path/to/file.swift)
        var files = Set<String>()

        let editPatterns = [
            "Update(", "Edit(", "Write(", "Created "
        ]

        for line in output.components(separatedBy: .newlines) {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            for pattern in editPatterns {
                if trimmed.contains(pattern),
                   let start = trimmed.range(of: pattern)?.upperBound {
                    let rest = trimmed[start...]
                    if let end = rest.firstIndex(of: ")") {
                        let filePath = String(rest[..<end]).trimmingCharacters(in: .whitespaces)
                        if !filePath.isEmpty {
                            files.insert(filePath)
                        }
                    }
                }
            }
        }

        return Array(files).sorted()
    }

    private func extractPlan(from output: String) -> String {
        // Extract the plan section from Claude's output
        // For now, return the full output - could be refined later
        return output
    }

    private func openTmuxSessionInTerminal(sessionName: String) {
        // Check if session is alive before opening terminal
        guard isSessionAlive(sessionName: sessionName) else {
            logMessage("TaskAgentManager: Cannot open terminal - session '\(sessionName)' does not exist")
            return
        }

        // Create flag file to skip .zshrc auto-resume (which hijacks the shell via exec)
        let flagPath = "/tmp/.omi-skip-resume"
        FileManager.default.createFile(atPath: flagPath, contents: nil)

        let script = """
        tell application "Terminal"
            activate
            do script "source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; tmux attach -t '\(sessionName)'"
        end tell
        """

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = ["-e", script]

        try? process.run()
        logMessage("TaskAgentManager: Opened terminal for session '\(sessionName)'")

        // Remove flag file after Terminal has started (delay to ensure .zshrc has been sourced)
        DispatchQueue.global().asyncAfter(deadline: .now() + 3.0) {
            try? FileManager.default.removeItem(atPath: flagPath)
        }
    }

    private func killTmuxSession(sessionName: String) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = ["-c", "source ~/.zprofile 2>/dev/null; tmux kill-session -t '\(sessionName)' 2>/dev/null"]

        try? process.run()
        process.waitUntilExit()
    }

    private func logMessage(_ message: String) {
        log(message)
    }

    // MARK: - Persistence

    /// Persist current session state to SQLite (fire-and-forget)
    private func persistSession(_ session: AgentSession) {
        let editedFilesJson: String?
        if !session.editedFiles.isEmpty,
           let data = try? JSONEncoder().encode(session.editedFiles),
           let json = String(data: data, encoding: .utf8) {
            editedFilesJson = json
        } else {
            editedFilesJson = nil
        }

        let taskId = session.taskId
        let status = session.status.rawValue
        let sessionName = session.sessionName
        let prompt = session.prompt
        let plan = session.plan
        let startedAt = session.startedAt
        let completedAt = session.completedAt

        Task {
            do {
                try await ActionItemStorage.shared.updateAgentState(
                    taskId: taskId,
                    status: status,
                    sessionName: sessionName,
                    prompt: prompt,
                    plan: plan,
                    startedAt: startedAt,
                    completedAt: completedAt,
                    editedFilesJson: editedFilesJson
                )
            } catch {
                log("TaskAgentManager: Failed to persist session for \(taskId): \(error)")
            }
        }
    }

    /// Restore agent sessions from database on app launch
    func restoreSessionsFromDatabase() async {
        logMessage("TaskAgentManager: Restoring agent sessions from database...")

        do {
            let records = try await ActionItemStorage.shared.getActiveAgentSessions()

            guard !records.isEmpty else {
                logMessage("TaskAgentManager: No active agent sessions to restore")
                return
            }

            logMessage("TaskAgentManager: Found \(records.count) active agent session(s) to restore")

            for record in records {
                guard let sessionName = record.agentSessionName,
                      let statusStr = record.agentStatus,
                      let status = AgentStatus(rawValue: statusStr) else {
                    continue
                }

                let taskId = record.backendId ?? "local_\(record.id ?? 0)"

                let session = AgentSession(
                    taskId: taskId,
                    sessionName: sessionName,
                    prompt: record.agentPrompt ?? "",
                    startedAt: record.agentStartedAt ?? record.createdAt,
                    status: status,
                    output: nil,
                    plan: record.agentPlan,
                    completedAt: record.agentCompletedAt,
                    editedFiles: record.agentEditedFiles
                )

                if isSessionAlive(sessionName: sessionName) {
                    await MainActor.run {
                        activeSessions[taskId] = session
                    }
                    startPolling(taskId: taskId, sessionName: sessionName)
                    logMessage("TaskAgentManager: Restored live session for task \(taskId)")
                } else {
                    // Session is dead — mark final state
                    let finalStatus: AgentStatus = session.editedFiles.isEmpty ? .failed : .completed
                    var finalSession = session
                    finalSession.status = finalStatus
                    finalSession.completedAt = finalSession.completedAt ?? Date()

                    let sessionToStore = finalSession
                    await MainActor.run {
                        activeSessions[taskId] = sessionToStore
                    }
                    persistSession(sessionToStore)
                    logMessage("TaskAgentManager: Session dead for task \(taskId), marked as \(finalStatus.rawValue)")
                }
            }
        } catch {
            logMessage("TaskAgentManager: Failed to restore sessions - \(error)")
        }
    }

    // MARK: - Errors

    enum AgentError: LocalizedError {
        case tmuxNotInstalled
        case claudeNotInstalled
        case launchFailed(String)

        var errorDescription: String? {
            switch self {
            case .tmuxNotInstalled:
                return "tmux is not installed. Install with: brew install tmux"
            case .claudeNotInstalled:
                return "Claude CLI is not installed. Install from: https://claude.ai/claude-code"
            case .launchFailed(let output):
                return "Failed to launch agent: \(output)"
            }
        }
    }
}

/// Context for agent prompt building
struct TaskAgentContext {
    let workingDirectory: String
    let contextSummary: String?
    let recentScreenshots: [String]?  // Paths to recent screenshots
    let relatedConversation: String?  // Conversation transcript if available

    init(
        workingDirectory: String? = nil,
        contextSummary: String? = nil,
        recentScreenshots: [String]? = nil,
        relatedConversation: String? = nil
    ) {
        self.workingDirectory = workingDirectory ?? TaskAgentSettings.shared.workingDirectory
        self.contextSummary = contextSummary
        self.recentScreenshots = recentScreenshots
        self.relatedConversation = relatedConversation
    }
}
