import Foundation
import GRDB

// MARK: - Database Record

/// Database record for AI-generated user profile history
struct AIUserProfileRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var profileText: String
    var dataSourcesUsed: Int
    var backendSynced: Bool
    var generatedAt: Date

    static let databaseTableName = "ai_user_profiles"

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}

// MARK: - Service

/// Service that generates and maintains an AI-generated user profile.
/// Inspired by the ContextAgent paper (arXiv:2505.14668).
/// Runs once daily, fetches data from multiple sources, and calls Gemini to synthesize a concise profile.
/// All generated profiles are stored in the local database for history tracking.
actor AIUserProfileService {
    static let shared = AIUserProfileService()

    private let model = "gemini-3-pro-preview"
    private let maxProfileLength = 2000

    /// Whether profile generation is currently in progress
    private var isGenerating = false

    /// Cached database pool
    private var _dbQueue: DatabasePool?

    /// Invalidate cached DB queue (called on user switch / sign-out)
    func invalidateCache() {
        _dbQueue = nil
    }

    // MARK: - Database Access

    private func ensureDB() async throws -> DatabasePool {
        if let db = _dbQueue { return db }
        try await RewindDatabase.shared.initialize()
        guard let db = await RewindDatabase.shared.getDatabaseQueue() else {
            throw ProfileError.databaseNotAvailable
        }
        _dbQueue = db
        return db
    }

    // MARK: - Public Interface

    /// Check if we should generate a new profile (>24h since last generation)
    func shouldGenerate() async -> Bool {
        guard let db = try? await ensureDB() else { return false }
        do {
            let latest = try await db.read { database in
                try AIUserProfileRecord
                    .order(Column("generatedAt").desc)
                    .fetchOne(database)
            }
            guard let latest else { return true } // Never generated
            return Date().timeIntervalSince(latest.generatedAt) > 86400
        } catch {
            return true
        }
    }

    /// Get the latest stored profile
    func getLatestProfile() async -> AIUserProfileRecord? {
        guard let db = try? await ensureDB() else { return nil }
        return try? await db.read { database in
            try AIUserProfileRecord
                .order(Column("generatedAt").desc)
                .fetchOne(database)
        }
    }

    /// Delete a profile by ID and return the next latest profile
    func deleteProfile(id: Int64) async -> AIUserProfileRecord? {
        guard let db = try? await ensureDB() else { return nil }
        _ = try? await db.write { database in
            try database.execute(
                sql: "DELETE FROM ai_user_profiles WHERE id = ?",
                arguments: [id]
            )
        }
        return await getLatestProfile()
    }

    /// Update the profile text of an existing record
    func updateProfileText(id: Int64, newText: String) async -> Bool {
        guard let db = try? await ensureDB() else { return false }
        do {
            try await db.write { database in
                try database.execute(
                    sql: "UPDATE ai_user_profiles SET profileText = ? WHERE id = ?",
                    arguments: [newText, id]
                )
            }
            return true
        } catch {
            return false
        }
    }

    /// Delete all stored profiles
    func deleteAllProfiles() async {
        guard let db = try? await ensureDB() else { return }
        _ = try? await db.write { database in
            try database.execute(sql: "DELETE FROM ai_user_profiles")
        }
    }

    /// Get all stored profiles (newest first)
    func getAllProfiles(limit: Int = 30) async -> [AIUserProfileRecord] {
        guard let db = try? await ensureDB() else { return [] }
        return (try? await db.read { database in
            try AIUserProfileRecord
                .order(Column("generatedAt").desc)
                .limit(limit)
                .fetchAll(database)
        }) ?? []
    }

    /// Generate a new AI user profile from all available data sources
    func generateProfile() async throws -> AIUserProfileRecord {
        guard !isGenerating else {
            throw ProfileError.alreadyGenerating
        }
        isGenerating = true
        defer { isGenerating = false }

        log("AIUserProfileService: Starting profile generation")

        // 1. Fetch all data sources in parallel
        let (memories, tasks, goals, conversations, messages) = await fetchDataSources()

        // 2. Count total data items
        let dataSourcesUsed = memories.count + tasks.count + goals.count + conversations.count + messages.count
        log("AIUserProfileService: Fetched \(dataSourcesUsed) data items (memories=\(memories.count), tasks=\(tasks.count), goals=\(goals.count), convos=\(conversations.count), messages=\(messages.count))")

        guard dataSourcesUsed > 0 else {
            throw ProfileError.insufficientData
        }

        // 3. Build prompt
        let prompt = buildPrompt(memories: memories, tasks: tasks, goals: goals, conversations: conversations, messages: messages)

        // 4. Call Gemini
        let gemini = try GeminiClient(model: model)
        let systemPrompt = """
        You are generating a structured user profile that will be injected as context into AI pipelines \
        (task extraction, goal extraction, memory extraction) that analyze the user's screen and audio activity.

        OUTPUT FORMAT:
        - A flat list of factual statements, one per line, prefixed with "- "
        - Each statement must be a concrete fact directly supported by the provided data
        - No prose, no paragraphs, no headers, no markdown formatting
        - No adjectives like "passionate", "dedicated", "impressive"
        - Write in third person ("User works at...", not "You work at...")

        WHAT TO INCLUDE (only if clearly supported by the data):
        - Full name, role, company, industry
        - Current projects and what tools/apps they use for each
        - Key people they interact with (names, roles, relationship)
        - Active goals and their progress
        - Recurring meetings, deadlines, routines
        - Communication platforms they use (Slack, email, iMessage, etc.)
        - Technical stack, programming languages, frameworks
        - Topics they frequently discuss or research
        - Pending tasks and commitments to others
        - Time zone, work schedule patterns

        CRITICAL RULES:
        - ONLY include facts that are directly evidenced in the provided data
        - If a category has no supporting data, skip it entirely — do not guess or infer
        - Do NOT hallucinate names, roles, companies, or relationships not present in the data
        - Do NOT add personality descriptions or subjective assessments
        - When uncertain, omit rather than speculate
        - NEVER fabricate email addresses, phone numbers, URLs, or contact information
        - The provided data contains NO email addresses — do not invent any
        - If you cannot find a piece of information verbatim in the data, do not include it

        The output MUST be under 2000 characters total.
        """

        let stageOneText = try await gemini.sendTextRequest(prompt: prompt, systemPrompt: systemPrompt)
        log("AIUserProfileService: Stage 1 complete (\(stageOneText.count) chars)")

        // 5. Stage 2 — Consolidate with past profiles for holistic view
        let pastProfiles = await getAllProfiles(limit: 5)
        let finalText: String
        if pastProfiles.isEmpty {
            finalText = stageOneText
        } else {
            let consolidationPrompt = buildConsolidationPrompt(
                newProfile: stageOneText,
                pastProfiles: pastProfiles
            )
            let consolidationSystemPrompt = """
            You are merging a newly generated user profile with historical profiles to create \
            one holistic, up-to-date user profile. This profile is injected as context into AI pipelines \
            (task extraction, goal extraction, memory extraction) that analyze the user's screen and audio activity.

            OUTPUT FORMAT:
            - A flat list of factual statements, one per line, prefixed with "- "
            - Each statement must be a concrete fact
            - No prose, no paragraphs, no headers, no markdown formatting
            - No adjectives or subjective assessments
            - Write in third person

            MERGE RULES:
            - The NEW profile reflects today's data and takes priority for current state
            - Past profiles provide historical context — retain facts that are still relevant
            - If a fact from the past contradicts the new profile, use the new one
            - Remove outdated information (completed tasks, past deadlines, old routines)
            - Keep stable facts (name, role, company, key relationships, tech stack)
            - Accumulate knowledge: if past profiles mention people, projects, or patterns \
              not in today's data, keep them if they seem ongoing
            - Do NOT hallucinate — only include facts present in the provided profiles
            - Do NOT add commentary about changes or evolution over time

            The output MUST be under 2000 characters total.
            """
            finalText = try await gemini.sendTextRequest(
                prompt: consolidationPrompt,
                systemPrompt: consolidationSystemPrompt
            )
            log("AIUserProfileService: Stage 2 consolidation complete (\(finalText.count) chars)")
        }

        // 6. Truncate if needed
        let truncated = String(finalText.prefix(maxProfileLength))
        let generatedAt = Date()

        // 6. Save to database
        let db = try await ensureDB()
        let record = AIUserProfileRecord(
            profileText: truncated,
            dataSourcesUsed: dataSourcesUsed,
            backendSynced: false,
            generatedAt: generatedAt
        )
        try await db.write { database in
            try record.insert(database)
        }

        // 7. Sync to backend (fire-and-forget)
        let recordId = record.id
        Task {
            do {
                try await APIClient.shared.syncAIUserProfile(
                    profileText: truncated,
                    generatedAt: generatedAt,
                    dataSourcesUsed: dataSourcesUsed
                )
                // Mark as synced
                if let id = recordId, let db = try? await self.ensureDB() {
                    _ = try? await db.write { database in
                        try database.execute(
                            sql: "UPDATE ai_user_profiles SET backendSynced = 1 WHERE id = ?",
                            arguments: [id]
                        )
                    }
                }
                log("AIUserProfileService: Synced profile to backend")
            } catch {
                log("AIUserProfileService: Failed to sync profile to backend: \(error.localizedDescription)")
            }
        }

        log("AIUserProfileService: Profile generated successfully (\(truncated.count) chars, \(dataSourcesUsed) data items)")
        return record
    }

    // MARK: - Data Fetching

    private func fetchDataSources() async -> (
        memories: [String],
        tasks: [String],
        goals: [String],
        conversations: [String],
        messages: [String]
    ) {
        async let memoriesTask = fetchMemories()
        async let tasksTask = fetchTasks()
        async let goalsTask = fetchGoals()
        async let conversationsTask = fetchConversations()
        async let messagesTask = fetchMessages()

        let memories = await memoriesTask
        let tasks = await tasksTask
        let goals = await goalsTask
        let conversations = await conversationsTask
        let messages = await messagesTask

        return (memories, tasks, goals, conversations, messages)
    }

    private func fetchMemories() async -> [String] {
        do {
            let memories = try await APIClient.shared.getMemories(limit: 100)
            return memories.map { "[\($0.category.rawValue)] \($0.content)" }
        } catch {
            log("AIUserProfileService: Failed to fetch memories: \(error.localizedDescription)")
            return []
        }
    }

    private func fetchTasks() async -> [String] {
        do {
            let response = try await APIClient.shared.getActionItems(limit: 50)
            return response.items.map { item in
                let status = item.completed ? "done" : "todo"
                let priority = item.priority ?? "medium"
                return "[\(status)/\(priority)] \(item.description)"
            }
        } catch {
            log("AIUserProfileService: Failed to fetch tasks: \(error.localizedDescription)")
            return []
        }
    }

    private func fetchGoals() async -> [String] {
        do {
            let goals = try await APIClient.shared.getGoals()
            return goals.filter { $0.isActive }.map { goal in
                let progress = goal.targetValue > 0 ? Int((goal.currentValue / goal.targetValue) * 100) : 0
                return "\(goal.title) (\(progress)% complete)"
            }
        } catch {
            log("AIUserProfileService: Failed to fetch goals: \(error.localizedDescription)")
            return []
        }
    }

    private func fetchConversations() async -> [String] {
        do {
            let sevenDaysAgo = Calendar.current.date(byAdding: .day, value: -7, to: Date())
            let conversations = try await APIClient.shared.getConversations(
                limit: 20,
                startDate: sevenDaysAgo
            )
            return conversations.compactMap { convo in
                let title = convo.structured.title
                let summary = convo.structured.overview
                guard !title.isEmpty else { return nil }
                return "\(title): \(summary)"
            }
        } catch {
            log("AIUserProfileService: Failed to fetch conversations: \(error.localizedDescription)")
            return []
        }
    }

    private func fetchMessages() async -> [String] {
        do {
            let messages = try await APIClient.shared.getMessages(limit: 30)
            return messages.map { "[\($0.sender)] \($0.text)" }
        } catch {
            log("AIUserProfileService: Failed to fetch messages: \(error.localizedDescription)")
            return []
        }
    }

    // MARK: - Prompt Building

    private func buildPrompt(
        memories: [String],
        tasks: [String],
        goals: [String],
        conversations: [String],
        messages: [String]
    ) -> String {
        var sections: [String] = []

        if !memories.isEmpty {
            sections.append("## Memories about the user\n\(memories.joined(separator: "\n"))")
        }

        if !tasks.isEmpty {
            sections.append("## Recent tasks\n\(tasks.joined(separator: "\n"))")
        }

        if !goals.isEmpty {
            sections.append("## Active goals\n\(goals.joined(separator: "\n"))")
        }

        if !conversations.isEmpty {
            sections.append("## Recent conversations (past 7 days)\n\(conversations.joined(separator: "\n"))")
        }

        if !messages.isEmpty {
            sections.append("## Recent AI chat messages\n\(messages.joined(separator: "\n"))")
        }

        return """
        Generate a factual user profile from the following data. \
        Output a flat list of concrete facts (one per line, prefixed with "- "). \
        This profile will be used as context for AI pipelines that analyze the user's screen and audio activity \
        to extract tasks, goals, and memories. Focus on facts that help identify who is who, what projects are active, \
        and what the user's current priorities are. Under 2000 characters.

        \(sections.joined(separator: "\n\n"))
        """
    }

    private func buildConsolidationPrompt(
        newProfile: String,
        pastProfiles: [AIUserProfileRecord]
    ) -> String {
        let dateFormatter = DateFormatter()
        dateFormatter.dateStyle = .medium
        dateFormatter.timeStyle = .none

        var pastSection = ""
        for profile in pastProfiles {
            let dateStr = dateFormatter.string(from: profile.generatedAt)
            pastSection += "--- Profile from \(dateStr) ---\n\(profile.profileText)\n\n"
        }

        return """
        Merge the following into one holistic user profile. Under 2000 characters.

        === NEW PROFILE (generated today from latest data) ===
        \(newProfile)

        === PAST PROFILES (oldest to newest, up to 5) ===
        \(pastSection)
        """
    }

    // MARK: - Errors

    enum ProfileError: LocalizedError {
        case alreadyGenerating
        case insufficientData
        case databaseNotAvailable

        var errorDescription: String? {
            switch self {
            case .alreadyGenerating:
                return "Profile generation is already in progress"
            case .insufficientData:
                return "Not enough data to generate a profile"
            case .databaseNotAvailable:
                return "Database is not available"
            }
        }
    }
}
