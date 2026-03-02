import Foundation

/// Service that periodically scans staged tasks and uses Gemini AI to detect
/// and remove semantic duplicates BEFORE they are promoted to action items.
/// Only operates on staged_tasks — never touches action_items.
actor TaskDeduplicationService {
    static let shared = TaskDeduplicationService()

    private var geminiClient: GeminiClient?
    private var timer: Task<Void, Never>?
    private var isRunning = false
    private var lastRunTime: Date?

    // Configuration
    private let intervalSeconds: TimeInterval = 3600    // 1 hour
    private let startupDelaySeconds: TimeInterval = 60  // 60s delay at app launch
    private let cooldownSeconds: TimeInterval = 1800    // 30-min cooldown
    private let minimumTaskCount = 3

    private init() {
        do {
            self.geminiClient = try GeminiClient(model: "gemini-pro-latest")
        } catch {
            log("TaskDedup: Failed to initialize GeminiClient: \(error)")
            self.geminiClient = nil
        }
    }

    // MARK: - Lifecycle

    func start() {
        guard !isRunning else { return }
        isRunning = true
        log("TaskDedup: Service started (staged tasks only)")

        timer = Task { [weak self] in
            // Startup delay
            try? await Task.sleep(nanoseconds: UInt64(60 * 1_000_000_000))

            while !Task.isCancelled {
                guard let self = self else { break }

                // Check cooldown
                if let lastRun = await self.lastRunTime,
                   Date().timeIntervalSince(lastRun) < self.cooldownSeconds {
                    let remaining = self.cooldownSeconds - Date().timeIntervalSince(lastRun)
                    try? await Task.sleep(nanoseconds: UInt64(remaining * 1_000_000_000))
                    continue
                }

                await self.runDeduplication()

                // Wait for next interval
                try? await Task.sleep(nanoseconds: UInt64(self.intervalSeconds * 1_000_000_000))
            }
        }
    }

    func stop() {
        guard isRunning else { return }
        timer?.cancel()
        timer = nil
        isRunning = false
        log("TaskDedup: Service stopped")
    }

    // MARK: - Deduplication Logic

    private func runDeduplication() async {
        guard let client = geminiClient else {
            log("TaskDedup: Skipping - Gemini client not initialized")
            return
        }

        lastRunTime = Date()
        log("TaskDedup: Starting deduplication run on staged tasks")

        // 1. Fetch staged tasks (not yet promoted to action items)
        let tasks: [TaskActionItem]
        do {
            let response = try await APIClient.shared.getStagedTasks(limit: 200)
            tasks = response.items
        } catch {
            log("TaskDedup: Failed to fetch staged tasks: \(error)")
            return
        }

        guard tasks.count >= minimumTaskCount else {
            log("TaskDedup: Only \(tasks.count) staged tasks, skipping (minimum: \(minimumTaskCount))")
            return
        }

        log("TaskDedup: Analyzing \(tasks.count) staged tasks for duplicates")

        // 2. Send all tasks to Gemini in a single call
        let totalDeleted = await analyzeAndDeleteDuplicates(tasks: tasks, client: client)

        log("TaskDedup: Run complete. Hard-deleted \(totalDeleted) duplicate staged tasks.")
    }

    private func analyzeAndDeleteDuplicates(tasks: [TaskActionItem], client: GeminiClient) async -> Int {
        // Build task list for prompt
        let taskDescriptions = tasks.map { task -> String in
            var parts = ["ID: \(task.id)", "Description: \(task.description)"]
            if let due = task.dueAt {
                parts.append("Due: \(ISO8601DateFormatter().string(from: due))")
            }
            if let priority = task.priority {
                parts.append("Priority: \(priority)")
            }
            if let source = task.source {
                parts.append("Source: \(source)")
            }
            parts.append("Created: \(ISO8601DateFormatter().string(from: task.createdAt))")
            return parts.joined(separator: "\n")
        }.joined(separator: "\n")

        let prompt = """
        Analyze the following tasks for semantic duplicates. Two tasks are duplicates if they \
        refer to the same action, even if worded differently.

        Tasks:
        \(taskDescriptions)

        For each group of duplicates, pick the best task to KEEP based on these criteria (in order):
        1. Most descriptive/specific wording
        2. Has a due date over one that doesn't
        3. Higher priority set (high > medium > low > none)
        4. More reliable source (manual > transcription > screenshot)
        5. Most recently created

        Only flag tasks as duplicates if you are confident they refer to the same action. \
        When in doubt, do NOT flag as duplicates.
        """

        let systemPrompt = """
        You are a task deduplication assistant. You identify semantically duplicate tasks \
        and choose the best one to keep. Be conservative - only flag clear duplicates. \
        Return has_duplicates: false if no duplicates are found.
        """

        let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
            type: "object",
            properties: [
                "has_duplicates": .init(type: "boolean", description: "Whether any duplicate groups were found"),
                "duplicate_groups": .init(
                    type: "array",
                    description: "Groups of duplicate tasks",
                    items: .init(
                        type: "object",
                        properties: [
                            "keep_id": .init(type: "string", description: "ID of the task to keep"),
                            "delete_ids": .init(
                                type: "array",
                                description: "IDs of tasks to delete",
                                items: .init(type: "string", properties: nil, required: nil)
                            ),
                            "reason": .init(type: "string", description: "Why these tasks are duplicates and which was kept")
                        ],
                        required: ["keep_id", "delete_ids", "reason"]
                    )
                )
            ],
            required: ["has_duplicates", "duplicate_groups"]
        )

        // Call Gemini
        let responseText: String
        do {
            responseText = try await client.sendRequest(
                prompt: prompt,
                systemPrompt: systemPrompt,
                responseSchema: responseSchema
            )
        } catch {
            log("TaskDedup: Gemini request failed: \(error)")
            return 0
        }

        // Parse response
        guard let data = responseText.data(using: .utf8) else {
            log("TaskDedup: Failed to convert response to data")
            return 0
        }

        let result: DedupResponse
        do {
            result = try JSONDecoder().decode(DedupResponse.self, from: data)
        } catch {
            log("TaskDedup: Failed to parse response: \(error)")
            return 0
        }

        guard result.hasDuplicates, !result.duplicateGroups.isEmpty else {
            log("TaskDedup: No duplicates found in batch of \(tasks.count) staged tasks")
            return 0
        }

        // Validate and delete
        let validTaskIDs = Set(tasks.map { $0.id })
        let taskLookup = Dictionary(tasks.map { ($0.id, $0) }, uniquingKeysWith: { _, latest in latest })
        var deletedCount = 0

        for group in result.duplicateGroups {
            // Safety: verify all IDs exist in our input
            guard validTaskIDs.contains(group.keepId) else {
                log("TaskDedup: Skipping group - keep_id '\(group.keepId)' not in input set")
                continue
            }

            let validDeleteIds = group.deleteIds.filter { validTaskIDs.contains($0) }
            if validDeleteIds.count != group.deleteIds.count {
                log("TaskDedup: Some delete IDs not in input set, filtering")
            }

            guard !validDeleteIds.isEmpty else { continue }

            let keptTask = taskLookup[group.keepId]

            for deleteId in validDeleteIds {
                let deletedTask = taskLookup[deleteId]

                // Log to SQLite
                let logRecord = TaskDedupLogRecord(
                    deletedTaskId: deleteId,
                    deletedDescription: deletedTask?.description ?? "unknown",
                    keptTaskId: group.keepId,
                    keptDescription: keptTask?.description ?? "unknown",
                    reason: group.reason,
                    deletedAt: Date()
                )

                do {
                    try await ProactiveStorage.shared.insertDedupLogRecord(logRecord)
                } catch {
                    log("TaskDedup: Failed to log deletion record: \(error)")
                }

                // Hard-delete staged task from backend
                do {
                    try await APIClient.shared.deleteStagedTask(id: deleteId)
                    deletedCount += 1
                    log("TaskDedup: Hard-deleted staged task '\(deletedTask?.description ?? deleteId)' (kept: '\(keptTask?.description ?? group.keepId)') - \(group.reason)")
                } catch {
                    log("TaskDedup: Failed to delete staged task \(deleteId) on backend: \(error)")
                }
            }
        }

        return deletedCount
    }
}

// MARK: - Response Models

private struct DedupResponse: Codable {
    let hasDuplicates: Bool
    let duplicateGroups: [DuplicateGroup]

    enum CodingKeys: String, CodingKey {
        case hasDuplicates = "has_duplicates"
        case duplicateGroups = "duplicate_groups"
    }

    struct DuplicateGroup: Codable {
        let keepId: String
        let deleteIds: [String]
        let reason: String

        enum CodingKeys: String, CodingKey {
            case keepId = "keep_id"
            case deleteIds = "delete_ids"
            case reason
        }
    }
}
