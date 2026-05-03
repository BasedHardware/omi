import SwiftUI

// MARK: - Data Models

struct LabQuestion: Identifiable {
    let id = UUID()
    var text: String
    var contextType: String  // memories, conversations, screen, search, tasks
}

struct LabEvaluation: Identifiable {
    let id = UUID()
    let questionText: String
    var response: String = ""
    var aiScore: Int = 0
    var aiComment: String = ""
    var humanScore: Int = 0
    var humanComment: String = ""
    var isRunning: Bool = false
}

struct LabPromptVersion: Identifiable {
    let id = UUID()
    var name: String
    var floatingPrefix: String
    var mainPrompt: String
    var evaluations: [LabEvaluation] = []
    var avgAIScore: Double { evaluations.isEmpty ? 0 : Double(evaluations.map(\.aiScore).reduce(0, +)) / Double(evaluations.count) }
    var avgHumanScore: Double { evaluations.isEmpty ? 0 : Double(evaluations.map(\.humanScore).reduce(0, +)) / Double(evaluations.count) }
}

/// A historical prompt version with production rating data
struct PromptHistoryEntry: Identifiable {
    let id = UUID()
    let version: Int
    let date: String          // "Apr 7"
    let commitMsg: String
    let commitHash: String
    var thumbsUp: Int = 0
    var thumbsDown: Int = 0
    var promptSnippet: String = ""  // First ~200 chars of the prompt at that version
    var fullPrompt: String = ""

    /// Satisfaction ratio: likes / (likes + dislikes). 1.0 = perfect, 0.0 = all dislikes.
    var satisfactionRatio: Double {
        let total = thumbsUp + thumbsDown
        guard total > 0 else { return 0 }
        return Double(thumbsUp) / Double(total)
    }

    /// Formatted as percentage
    var satisfactionPct: String {
        let total = thumbsUp + thumbsDown
        guard total > 0 else { return "—" }
        return "\(Int(satisfactionRatio * 100))%"
    }
}

// MARK: - View Model

@MainActor
class ChatLabViewModel: ObservableObject {
    @Published var questions: [LabQuestion] = []
    @Published var versions: [LabPromptVersion] = []
    @Published var selectedVersionIndex: Int = 0
    @Published var isRunningAll = false
    @Published var isGenerating = false
    @Published var editingFloatingPrefix = ""
    @Published var editingMainPrompt = ""
    @Published var promptHistory: [PromptHistoryEntry] = []
    @Published var isLoadingHistory = false
    @Published var expandedHistoryVersion: Int? = nil

    let chatProvider: ChatProvider

    /// User must provide their own Anthropic API key for ChatLab.
    /// Persisted in UserDefaults so they don't have to re-enter each session.
    @Published var userApiKey: String {
        didSet { UserDefaults.standard.set(userApiKey, forKey: "chatlab_anthropic_api_key") }
    }

    private var anthropicKey: String {
        userApiKey.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    init(chatProvider: ChatProvider) {
        self.chatProvider = chatProvider
        self.userApiKey = UserDefaults.standard.string(forKey: "chatlab_anthropic_api_key") ?? ""
        loadDefaultQuestions()
        loadCurrentPrompt()
        // Load history in background — don't block the UI
        Task.detached(priority: .background) { [weak self] in
            guard let self else { return }
            await self.loadPromptHistory()
        }
    }

    func loadDefaultQuestions() {
        questions = [
            LabQuestion(text: "what should I focus on today?", contextType: "tasks"),
            LabQuestion(text: "summarize my last conversation", contextType: "conversations"),
            LabQuestion(text: "what do you know about me?", contextType: "memories"),
            LabQuestion(text: "how old am I?", contextType: "memories"),
            LabQuestion(text: "what apps did I use most today?", contextType: "tasks"),
            LabQuestion(text: "what did I talk about with my team?", contextType: "conversations"),
            LabQuestion(text: "which option should I pick?", contextType: "screen"),
            LabQuestion(text: "compare these two for me", contextType: "search"),
            LabQuestion(text: "create a task to follow up with John", contextType: "tasks"),
            LabQuestion(text: "what meetings do I have tomorrow?", contextType: "conversations"),
        ]
    }

    // MARK: - Production Prompt History

    /// Load prompt version history by checking git commits that modified the prompt files,
    /// then fetch ratings from the Omi backend API and attribute them to each version.
    func loadPromptHistory() async {
        isLoadingHistory = true

        // 1. Get git log of prompt-changing commits
        let versions = await getPromptVersionsFromGit()

        // 2. Fetch all rated messages from the backend
        let ratings = await fetchRatingsFromBackend()

        // 3. Attribute ratings to versions by date range
        var history = versions
        for i in 0..<history.count {
            let versionDate = history[i].date
            let nextDate = i + 1 < history.count ? history[i + 1].date : nil

            for (dateStr, up, down) in ratings {
                // Check if this rating falls within this version's date range
                if dateStr >= versionDate && (nextDate == nil || dateStr < nextDate!) {
                    history[i].thumbsUp += up
                    history[i].thumbsDown += down
                }
            }
        }

        promptHistory = history
        isLoadingHistory = false
    }

    /// Parse git log for commits that changed ChatPrompts.swift or ChatProvider's floating prefix
    private func getPromptVersionsFromGit() async -> [PromptHistoryEntry] {
        // Find the repo root (go up from the app bundle or use known path)
        let repoPath = "/Users/nik/projects/omi"
        let promptFile = "desktop/Desktop/Sources/Chat/ChatPrompts.swift"
        let providerFile = "desktop/Desktop/Sources/Providers/ChatProvider.swift"

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
        process.arguments = ["-C", repoPath, "log", "--format=%H|%ci|%s", "-n", "30", "origin/main", "--", promptFile, providerFile]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = Pipe()

        do {
            try process.run()
            // Timeout after 10 seconds
            let deadline = Date().addingTimeInterval(10)
            while process.isRunning && Date() < deadline {
                Thread.sleep(forTimeInterval: 0.1)
            }
            if process.isRunning { process.terminate() }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let output = String(data: data, encoding: .utf8) ?? ""

            let lines = output.components(separatedBy: "\n").filter { !$0.isEmpty }

            // Deduplicate by date and take last 10
            var seenDates = Set<String>()
            var entries: [PromptHistoryEntry] = []
            let dateFmt = DateFormatter()
            dateFmt.dateFormat = "yyyy-MM-dd"

            let displayFmt = DateFormatter()
            displayFmt.dateFormat = "MMM d"

            for line in lines {
                let parts = line.components(separatedBy: "|")
                guard parts.count >= 3 else { continue }
                let hash = parts[0]
                let dateRaw = String(parts[1].prefix(10))  // "2026-04-09"
                let msg = parts[2]

                // Only one version per day
                guard !seenDates.contains(dateRaw) else { continue }
                seenDates.insert(dateRaw)

                let displayDate = dateFmt.date(from: dateRaw).map { displayFmt.string(from: $0) } ?? dateRaw

                // Get the prompt content at this commit
                let promptContent = getFileAtCommit(repoPath: repoPath, hash: hash, file: promptFile)
                let snippet = String(promptContent.prefix(200))

                entries.append(PromptHistoryEntry(
                    version: 0,
                    date: dateRaw,
                    commitMsg: msg,
                    commitHash: String(hash.prefix(8)),
                    promptSnippet: snippet.isEmpty ? "—" : snippet + "...",
                    fullPrompt: promptContent
                ))

                if entries.count >= 10 { break }
            }

            // Number versions in reverse (most recent = highest)
            for i in 0..<entries.count {
                entries[i] = PromptHistoryEntry(
                    version: entries.count - i,
                    date: entries[i].date,
                    commitMsg: entries[i].commitMsg,
                    commitHash: entries[i].commitHash,
                    promptSnippet: entries[i].promptSnippet,
                    fullPrompt: entries[i].fullPrompt
                )
            }

            return entries.reversed()  // oldest first
        } catch {
            log("ChatLab: git log failed: \(error)")
            return []
        }
    }

    private func getFileAtCommit(repoPath: String, hash: String, file: String) -> String {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
        process.arguments = ["-C", repoPath, "show", "\(hash):\(file)"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = Pipe()  // suppress errors

        do {
            try process.run()
            process.waitUntilExit()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            return String(data: data, encoding: .utf8) ?? ""
        } catch {
            return ""
        }
    }

    /// Fetch rated messages from the Omi backend, return (date, ups, downs) tuples
    private func fetchRatingsFromBackend() async -> [(String, Int, Int)] {
        do {
            let authHeader = try await AuthService.shared.getAuthHeader()

            // Fetch messages with ratings from the last 60 days
            let baseURL = await APIClient.shared.baseURL
            let url = URL(string: "\(baseURL)v2/messages?limit=500")!
            var request = URLRequest(url: url)
            request.setValue(authHeader, forHTTPHeaderField: "Authorization")

            let (data, _) = try await URLSession.shared.data(for: request)
            let messages = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] ?? []

            // Group by date
            var byDate: [String: (up: Int, down: Int)] = [:]
            let dateFmt = DateFormatter()
            dateFmt.dateFormat = "yyyy-MM-dd"

            for msg in messages {
                guard let rating = msg["rating"] as? Int, rating != 0 else { continue }
                let createdAt = msg["created_at"] as? String ?? ""
                let dateStr = String(createdAt.prefix(10))
                guard !dateStr.isEmpty else { continue }

                var entry = byDate[dateStr] ?? (up: 0, down: 0)
                if rating > 0 { entry.up += 1 } else { entry.down += 1 }
                byDate[dateStr] = entry
            }

            return byDate.map { ($0.key, $0.value.up, $0.value.down) }
                .sorted { $0.0 < $1.0 }
        } catch {
            log("ChatLab: Failed to fetch ratings: \(error)")
            return []
        }
    }

    private func inferContextType(_ text: String) -> String {
        let lower = text.lowercased()
        if lower.contains("task") || lower.contains("focus") || lower.contains("todo") || lower.contains("create a") { return "tasks" }
        if lower.contains("talk") || lower.contains("conversation") || lower.contains("meeting") || lower.contains("call") || lower.contains("said") { return "conversations" }
        if lower.contains("screen") || lower.contains("option") || lower.contains("pick") || lower.contains("which") || lower.contains("see") { return "screen" }
        if lower.contains("compare") || lower.contains("search") || lower.contains("find") || lower.contains("look up") { return "search" }
        return "memories"
    }

    func loadCurrentPrompt() {
        let floatingPrefix = ChatProvider.floatingBarSystemPromptPrefix
        let mainPrompt = ChatPromptBuilder.buildDesktopChat(
            userName: "{user_name}",
            memoriesSection: "{memories_section}",
            goalSection: "{goal_section}",
            tasksSection: "{tasks_section}",
            aiProfileSection: "{ai_profile_section}",
            databaseSchema: "{database_schema}"
        )

        editingFloatingPrefix = floatingPrefix
        editingMainPrompt = mainPrompt

        if versions.isEmpty {
            versions.append(LabPromptVersion(
                name: "v1 (current)",
                floatingPrefix: floatingPrefix,
                mainPrompt: mainPrompt
            ))
        }
    }

    func runAllQuestions() async {
        isRunningAll = true
        let vIdx = selectedVersionIndex
        guard vIdx < versions.count else { isRunningAll = false; return }

        var evals: [LabEvaluation] = []
        for q in questions {
            evals.append(LabEvaluation(questionText: q.text))
        }
        versions[vIdx].evaluations = evals

        for i in 0..<questions.count {
            let q = questions[i]
            versions[vIdx].evaluations[i].isRunning = true

            // Build the real system prompt — same as ChatProvider does
            let systemPrompt = buildRealSystemPrompt(version: versions[vIdx])

            // Run through the real agent bridge (with tools, real context)
            let response = await runThroughBridge(
                question: q.text,
                systemPrompt: systemPrompt,
                sessionKey: "chat-lab-\(vIdx)-\(i)"
            )

            versions[vIdx].evaluations[i].response = response

            // AI-grade the response
            let (aiScore, aiComment) = await gradeResponse(question: q.text, response: response)
            versions[vIdx].evaluations[i].aiScore = aiScore
            versions[vIdx].evaluations[i].aiComment = aiComment
            versions[vIdx].evaluations[i].isRunning = false
        }

        isRunningAll = false
    }

    /// Build a system prompt using the version's template with real user context.
    /// Uses ChatProvider's public labBuildSystemPrompt() for the real context injection.
    private func buildRealSystemPrompt(version: LabPromptVersion) -> String {
        let chatProvider = chatProvider
        return chatProvider.labBuildSystemPrompt(
            floatingPrefix: version.floatingPrefix,
            mainTemplate: version.mainPrompt
        )
    }

    /// Send a question through the real agent bridge (same path as floating bar / main chat).
    /// Falls back to direct API if bridge isn't available.
    private func runThroughBridge(question: String, systemPrompt: String, sessionKey: String) async -> String {
        let chatProvider = chatProvider
        let result = await chatProvider.labRunQuestion(
            question: question,
            systemPrompt: systemPrompt,
            sessionKey: sessionKey
        )
        return result
    }

    func generateNextVersion() async {
        guard !anthropicKey.isEmpty else { return }
        isGenerating = true

        let currentVersion = versions[selectedVersionIndex]
        let evalSummary = currentVersion.evaluations.map { e in
            "Q: \(e.questionText)\nResponse: \(e.response.prefix(200))\nAI Score: \(e.aiScore)/5 (\(e.aiComment))\nHuman Score: \(e.humanScore)/5 (\(e.humanComment))"
        }.joined(separator: "\n---\n")

        let metaPrompt = """
        You are an expert prompt engineer. Below is a system prompt for an AI assistant called Omi, and the evaluation results from testing it with real user questions.

        CURRENT FLOATING BAR PREFIX:
        \(currentVersion.floatingPrefix)

        CURRENT MAIN PROMPT:
        \(currentVersion.mainPrompt)

        EVALUATION RESULTS:
        \(evalSummary)

        Based on the evaluation results, generate an IMPROVED version of the prompt. Focus on:
        - Questions that scored low — what context or instruction was missing?
        - Making responses more personalized and specific
        - Reducing generic/vague answers
        - Keeping responses concise (1-3 sentences for floating bar)

        Return ONLY the improved main prompt (not the floating bar prefix — keep that as-is). Do not explain your changes, just output the new prompt.
        """

        let (newPrompt, _, _) = await callClaude(systemPrompt: "You are a prompt engineering expert.", userMessage: metaPrompt)

        if !newPrompt.isEmpty {
            let newVersion = LabPromptVersion(
                name: "v\(versions.count + 1)",
                floatingPrefix: currentVersion.floatingPrefix,
                mainPrompt: newPrompt
            )
            versions.append(newVersion)
            selectedVersionIndex = versions.count - 1
            editingFloatingPrefix = newVersion.floatingPrefix
            editingMainPrompt = newVersion.mainPrompt
        }

        isGenerating = false
    }

    func saveAsNewVersion(name: String) {
        let newVersion = LabPromptVersion(
            name: name,
            floatingPrefix: editingFloatingPrefix,
            mainPrompt: editingMainPrompt
        )
        versions.append(newVersion)
        selectedVersionIndex = versions.count - 1
    }

    private func callClaude(systemPrompt: String, userMessage: String) async -> (String, Int, String) {
        guard !anthropicKey.isEmpty else { return ("No API key", 0, "") }

        do {
            let url = URL(string: "https://api.anthropic.com/v1/messages")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue(anthropicKey, forHTTPHeaderField: "x-api-key")
            request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")

            let body: [String: Any] = [
                "model": ModelQoS.Claude.chatLabQuery,
                "max_tokens": 1024,
                "system": systemPrompt.prefix(50000),
                "messages": [["role": "user", "content": userMessage]],
            ]
            request.httpBody = try JSONSerialization.data(withJSONObject: body)

            let (data, _) = try await URLSession.shared.data(for: request)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let content = json?["content"] as? [[String: Any]]
            let responseText = content?.first?["text"] as? String ?? "No response"

            // Grade the response
            let (aiScore, aiComment) = await gradeResponse(question: userMessage, response: responseText)

            return (responseText, aiScore, aiComment)
        } catch {
            log("ChatLab: Claude API error: \(error)")
            return ("Error: \(error.localizedDescription)", 0, "")
        }
    }

    private func gradeResponse(question: String, response: String) async -> (Int, String) {
        do {
            let url = URL(string: "https://api.anthropic.com/v1/messages")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue(anthropicKey, forHTTPHeaderField: "x-api-key")
            request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")

            let gradePrompt = """
            Rate this AI assistant response on a 0-5 scale. Consider:
            - Relevance to the question
            - Personalization (does it use user context?)
            - Conciseness (is it brief and direct?)
            - Helpfulness (does it actually help?)

            Question: \(question)
            Response: \(response)

            Reply with ONLY a JSON object: {"score": N, "comment": "brief reason"}
            """

            let body: [String: Any] = [
                "model": ModelQoS.Claude.chatLabGrade,
                "max_tokens": 200,
                "messages": [["role": "user", "content": gradePrompt]],
            ]
            request.httpBody = try JSONSerialization.data(withJSONObject: body)

            let (data, _) = try await URLSession.shared.data(for: request)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let content = json?["content"] as? [[String: Any]]
            let text = content?.first?["text"] as? String ?? ""

            // Parse JSON from response
            if let jsonData = text.data(using: .utf8),
               let grade = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any]
            {
                let score = grade["score"] as? Int ?? 0
                let comment = grade["comment"] as? String ?? ""
                return (score, comment)
            }

            return (0, "Failed to parse grade")
        } catch {
            return (0, "Grading error")
        }
    }
}

// MARK: - Chat Lab View

struct ChatLabView: View {
    let chatProvider: ChatProvider
    @StateObject private var vm: ChatLabViewModel

    @State private var showSaveDialog = false
    @State private var newVersionName = ""

    init(chatProvider: ChatProvider) {
        self.chatProvider = chatProvider
        _vm = StateObject(wrappedValue: ChatLabViewModel(chatProvider: chatProvider))
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                promptHistorySection
                promptEditorSection
                evaluationSection
                versionComparisonSection
            }
            .padding(24)
        }
        .frame(minWidth: 900, minHeight: 600)
        .background(OmiColors.backgroundPrimary)
    }

    // MARK: - Production Prompt History

    private var promptHistorySection: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Prompt Version History")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: {
                    Task { await vm.loadPromptHistory() }
                }) {
                    HStack(spacing: 4) {
                        if vm.isLoadingHistory {
                            ProgressView().scaleEffect(0.6).frame(width: 12, height: 12)
                        } else {
                            Image(systemName: "arrow.clockwise").scaledFont(size: 11)
                        }
                        Text("Refresh").scaledFont(size: 12, weight: .medium)
                    }
                    .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }

            if vm.isLoadingHistory && vm.promptHistory.isEmpty {
                HStack {
                    Spacer()
                    ProgressView()
                    Text("Loading git history & ratings...")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                    Spacer()
                }
                .padding(.vertical, 40)
            } else if vm.promptHistory.isEmpty {
                Text("No prompt history found")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textQuaternary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 40)
            } else {
                // Table header
                HStack(spacing: 0) {
                    Text("V")
                        .frame(width: 30, alignment: .center)
                    Text("Date")
                        .frame(width: 70, alignment: .leading)
                    Text("Change")
                        .frame(maxWidth: .infinity, alignment: .leading)
                    Text("👍")
                        .frame(width: 40, alignment: .center)
                    Text("👎")
                        .frame(width: 40, alignment: .center)
                    Text("Score")
                        .frame(width: 60, alignment: .center)
                }
                .scaledFont(size: 11, weight: .semibold)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)

                Divider()

                ForEach(vm.promptHistory) { entry in
                    VStack(spacing: 0) {
                        Button(action: {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                vm.expandedHistoryVersion = vm.expandedHistoryVersion == entry.version ? nil : entry.version
                            }
                        }) {
                            HStack(spacing: 0) {
                                Text("v\(entry.version)")
                                    .scaledFont(size: 13, weight: .semibold)
                                    .foregroundColor(OmiColors.purplePrimary)
                                    .frame(width: 30, alignment: .center)

                                Text(formatHistoryDate(entry.date))
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textSecondary)
                                    .frame(width: 70, alignment: .leading)

                                Text(entry.commitMsg)
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textPrimary)
                                    .lineLimit(1)
                                    .frame(maxWidth: .infinity, alignment: .leading)

                                let total = entry.thumbsUp + entry.thumbsDown
                                Text("\(entry.thumbsUp)")
                                    .scaledFont(size: 13, weight: .medium)
                                    .foregroundColor(.green)
                                    .frame(width: 40, alignment: .center)

                                Text("\(entry.thumbsDown)")
                                    .scaledFont(size: 13, weight: .medium)
                                    .foregroundColor(.red)
                                    .frame(width: 40, alignment: .center)

                                // Satisfaction score: single number
                                Group {
                                    if total == 0 {
                                        Text("—")
                                            .foregroundColor(OmiColors.textQuaternary)
                                    } else {
                                        Text(entry.satisfactionPct)
                                            .foregroundColor(satisfactionColor(entry.satisfactionRatio))
                                    }
                                }
                                .scaledFont(size: 14, weight: .bold)
                                .frame(width: 60, alignment: .center)

                                Image(systemName: vm.expandedHistoryVersion == entry.version ? "chevron.up" : "chevron.down")
                                    .scaledFont(size: 10)
                                    .foregroundColor(OmiColors.textQuaternary)
                                    .frame(width: 20)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 10)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)

                        // Expanded: show full prompt
                        if vm.expandedHistoryVersion == entry.version {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Commit: \(entry.commitHash)")
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)

                                ScrollView {
                                    Text(entry.fullPrompt.isEmpty ? "Prompt not available" : entry.fullPrompt)
                                        .scaledFont(size: 11)
                                        .foregroundColor(OmiColors.textSecondary)
                                        .textSelection(.enabled)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                }
                                .frame(maxHeight: 300)
                                .padding(12)
                                .background(OmiColors.backgroundTertiary)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                            }
                            .padding(.horizontal, 16)
                            .padding(.bottom, 12)
                            .transition(.opacity.combined(with: .move(edge: .top)))
                        }

                        if entry.version < vm.promptHistory.last?.version ?? 0 {
                            Divider().padding(.horizontal, 12)
                        }
                    }
                }
            }
        }
        .padding(20)
        .omiPanel(fill: OmiColors.backgroundSecondary)
    }

    private func formatHistoryDate(_ dateStr: String) -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd"
        guard let date = fmt.date(from: dateStr) else { return dateStr }
        let display = DateFormatter()
        display.dateFormat = "MMM d"
        return display.string(from: date)
    }

    private func satisfactionColor(_ ratio: Double) -> Color {
        if ratio >= 0.75 { return .green }
        if ratio >= 0.50 { return .yellow }
        return .red
    }

    // MARK: - Prompt Editor

    private var promptEditorSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Prompt Editor")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                // Version picker
                Picker("", selection: $vm.selectedVersionIndex) {
                    ForEach(vm.versions.indices, id: \.self) { i in
                        Text(vm.versions[i].name).tag(i)
                    }
                }
                .pickerStyle(.menu)
                .frame(width: 180)
                .onChange(of: vm.selectedVersionIndex) { _, idx in
                    if idx < vm.versions.count {
                        vm.editingFloatingPrefix = vm.versions[idx].floatingPrefix
                        vm.editingMainPrompt = vm.versions[idx].mainPrompt
                    }
                }
            }

            // Anthropic API key (user must provide their own)
            VStack(alignment: .leading, spacing: 6) {
                Text("Anthropic API Key")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)

                SecureField("sk-ant-...", text: $vm.userApiKey)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12, design: .monospaced))
                    .padding(8)
                    .background(OmiColors.backgroundTertiary)
                    .clipShape(RoundedRectangle(cornerRadius: 8))

                if vm.userApiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text("Enter your own Anthropic API key to use ChatLab evaluation features.")
                        .scaledFont(size: 11)
                        .foregroundColor(.orange)
                }
            }

            // Floating prefix
            VStack(alignment: .leading, spacing: 6) {
                Text("Floating Bar Prefix")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)

                TextEditor(text: $vm.editingFloatingPrefix)
                    .font(.system(size: 12, design: .monospaced))
                    .frame(height: 100)
                    .padding(8)
                    .background(OmiColors.backgroundTertiary)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }

            // Main prompt
            VStack(alignment: .leading, spacing: 6) {
                Text("Main Prompt")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)

                TextEditor(text: $vm.editingMainPrompt)
                    .font(.system(size: 12, design: .monospaced))
                    .frame(height: 200)
                    .padding(8)
                    .background(OmiColors.backgroundTertiary)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }

            HStack(spacing: 12) {
                Button(action: { showSaveDialog = true }) {
                    HStack(spacing: 6) {
                        Image(systemName: "square.and.arrow.down")
                            .scaledFont(size: 12)
                        Text("Save as New Version")
                            .scaledFont(size: 13, weight: .medium)
                    }
                    .foregroundColor(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(OmiColors.purplePrimary)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)

                Button(action: {
                    Task { await vm.generateNextVersion() }
                }) {
                    HStack(spacing: 6) {
                        if vm.isGenerating {
                            ProgressView()
                                .scaleEffect(0.6)
                                .frame(width: 14, height: 14)
                        } else {
                            Image(systemName: "sparkles")
                                .scaledFont(size: 12)
                        }
                        Text("Generate Next Version")
                            .scaledFont(size: 13, weight: .medium)
                    }
                    .foregroundColor(OmiColors.textPrimary)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(OmiColors.backgroundTertiary)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
                .disabled(vm.isGenerating)
            }
        }
        .padding(20)
        .omiPanel(fill: OmiColors.backgroundSecondary)
        .alert("Save as New Version", isPresented: $showSaveDialog) {
            TextField("Version name", text: $newVersionName)
            Button("Save") {
                if !newVersionName.isEmpty {
                    vm.saveAsNewVersion(name: newVersionName)
                    newVersionName = ""
                }
            }
            Button("Cancel", role: .cancel) { newVersionName = "" }
        }
    }

    // MARK: - Evaluation Section

    private var evaluationSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Evaluation")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: {
                    Task { await vm.runAllQuestions() }
                }) {
                    HStack(spacing: 6) {
                        if vm.isRunningAll {
                            ProgressView()
                                .scaleEffect(0.6)
                                .frame(width: 14, height: 14)
                        } else {
                            Image(systemName: "play.fill")
                                .scaledFont(size: 12)
                        }
                        Text("Run All Questions")
                            .scaledFont(size: 13, weight: .medium)
                    }
                    .foregroundColor(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(vm.isRunningAll ? OmiColors.textTertiary : OmiColors.purplePrimary)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
                .disabled(vm.isRunningAll)
            }

            // Questions table
            VStack(spacing: 0) {
                // Header
                HStack {
                    Text("Question")
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 200, alignment: .leading)

                    Text("Context")
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 80)

                    Text("Response")
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    Text("AI")
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 40)

                    Text("You")
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 80)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)

                Divider()

                // Rows
                let evals = vm.selectedVersionIndex < vm.versions.count
                    ? vm.versions[vm.selectedVersionIndex].evaluations
                    : []

                ForEach(vm.questions.indices, id: \.self) { qi in
                    let q = vm.questions[qi]
                    let eval = qi < evals.count ? evals[qi] : nil

                    HStack(alignment: .top) {
                        Text(q.text)
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textPrimary)
                            .frame(width: 200, alignment: .leading)
                            .lineLimit(3)

                        contextBadge(q.contextType)
                            .frame(width: 80)

                        if let eval = eval {
                            if eval.isRunning {
                                HStack(spacing: 6) {
                                    ProgressView().scaleEffect(0.6)
                                    Text("Running...")
                                        .scaledFont(size: 12)
                                        .foregroundColor(OmiColors.textTertiary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                            } else if eval.response.isEmpty {
                                Text("Not evaluated")
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textQuaternary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            } else {
                                Text(eval.response)
                                    .scaledFont(size: 12)
                                    .foregroundColor(OmiColors.textSecondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .textSelection(.enabled)
                            }

                            // AI score
                            Text("\(eval.aiScore)")
                                .scaledFont(size: 13, weight: .semibold)
                                .foregroundColor(scoreColor(eval.aiScore))
                                .frame(width: 40)

                            // Human rating stars
                            starRating(score: Binding(
                                get: { eval.humanScore },
                                set: { newScore in
                                    if qi < vm.versions[vm.selectedVersionIndex].evaluations.count {
                                        vm.versions[vm.selectedVersionIndex].evaluations[qi].humanScore = newScore
                                    }
                                }
                            ))
                            .frame(width: 80)
                        } else {
                            Text("—")
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textQuaternary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Text("—").frame(width: 40)
                            Text("—").frame(width: 80)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)

                    if qi < vm.questions.count - 1 {
                        Divider().padding(.horizontal, 12)
                    }
                }
            }
            .omiPanel(fill: OmiColors.backgroundSecondary)
        }
    }

    // MARK: - Version Comparison

    private var versionComparisonSection: some View {
        Group {
            if vm.versions.count > 1 {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Version Comparison")
                        .scaledFont(size: 18, weight: .semibold)
                        .foregroundColor(OmiColors.textPrimary)

                    HStack(spacing: 24) {
                        ForEach(vm.versions.indices, id: \.self) { i in
                            let v = vm.versions[i]
                            VStack(spacing: 6) {
                                Text(v.name)
                                    .scaledFont(size: 14, weight: .semibold)
                                    .foregroundColor(OmiColors.textPrimary)
                                HStack(spacing: 12) {
                                    VStack(spacing: 2) {
                                        Text("AI")
                                            .scaledFont(size: 10)
                                            .foregroundColor(OmiColors.textTertiary)
                                        Text(String(format: "%.1f", v.avgAIScore))
                                            .scaledFont(size: 18, weight: .bold)
                                            .foregroundColor(scoreColor(Int(v.avgAIScore)))
                                    }
                                    VStack(spacing: 2) {
                                        Text("Human")
                                            .scaledFont(size: 10)
                                            .foregroundColor(OmiColors.textTertiary)
                                        Text(String(format: "%.1f", v.avgHumanScore))
                                            .scaledFont(size: 18, weight: .bold)
                                            .foregroundColor(scoreColor(Int(v.avgHumanScore)))
                                    }
                                }
                            }
                            .padding(16)
                            .frame(maxWidth: .infinity)
                            .omiPanel(fill: i == vm.selectedVersionIndex
                                ? OmiColors.purplePrimary.opacity(0.1)
                                : OmiColors.backgroundSecondary)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Helpers

    private func contextBadge(_ type: String) -> some View {
        let colors: [String: (Color, Color)] = [
            "memories": (Color.blue.opacity(0.2), Color.blue),
            "conversations": (Color.green.opacity(0.2), Color.green),
            "screen": (Color.orange.opacity(0.2), Color.orange),
            "search": (Color.purple.opacity(0.2), Color.purple),
            "tasks": (Color.yellow.opacity(0.2), Color.yellow),
        ]
        let (bg, fg) = colors[type] ?? (OmiColors.backgroundTertiary, OmiColors.textTertiary)

        return Text(type)
            .scaledFont(size: 10, weight: .medium)
            .foregroundColor(fg)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(bg)
            .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func scoreColor(_ score: Int) -> Color {
        switch score {
        case 5: return .green
        case 4: return Color.green.opacity(0.7)
        case 3: return .yellow
        case 2: return .orange
        case 1: return .red
        default: return OmiColors.textQuaternary
        }
    }

    private func starRating(score: Binding<Int>) -> some View {
        HStack(spacing: 2) {
            ForEach(1...5, id: \.self) { star in
                Image(systemName: star <= score.wrappedValue ? "star.fill" : "star")
                    .scaledFont(size: 11)
                    .foregroundColor(star <= score.wrappedValue ? .yellow : OmiColors.textQuaternary)
                    .onTapGesture {
                        score.wrappedValue = score.wrappedValue == star ? 0 : star
                    }
            }
        }
    }
}

// MARK: - Window Manager

@MainActor
class ChatLabWindowManager {
    static let shared = ChatLabWindowManager()

    private var window: NSWindow?

    func openWindow(chatProvider: ChatProvider? = nil) {
        if let existing = window, existing.isVisible {
            existing.makeKeyAndOrderFront(nil)
            return
        }

        guard let provider = chatProvider else {
            log("ChatLab: No ChatProvider available")
            return
        }

        let chatLabView = ChatLabView(chatProvider: provider)
        let hostingView = NSHostingView(rootView: chatLabView)

        let w = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1100, height: 750),
            styleMask: [.titled, .closable, .resizable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        w.title = "Chat Lab — Prompt Iteration"
        w.contentView = hostingView
        w.center()
        w.isReleasedWhenClosed = false
        w.makeKeyAndOrderFront(nil)

        window = w
    }
}
