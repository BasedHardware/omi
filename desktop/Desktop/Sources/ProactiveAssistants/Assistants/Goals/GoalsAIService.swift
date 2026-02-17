import Foundation

/// Service for AI-powered goal features using direct Gemini calls
actor GoalsAIService {
    static let shared = GoalsAIService()

    private var geminiClient: GeminiClient?

    private init() {
        do {
            self.geminiClient = try GeminiClient(model: "gemini-3-pro-preview")
        } catch {
            log("GoalsAIService: Failed to initialize GeminiClient: \(error)")
            self.geminiClient = nil
        }
    }

    /// Response schema for goal generation
    private var goalSuggestionSchema: GeminiRequest.GenerationConfig.ResponseSchema {
        GeminiRequest.GenerationConfig.ResponseSchema(
            type: "object",
            properties: [
                "suggested_title": .init(type: "string", description: "Brief, actionable goal title"),
                "suggested_description": .init(type: "string", description: "1-2 sentence description explaining why this goal matters and what success looks like"),
                "suggested_type": .init(type: "string", enum: ["boolean", "scale", "numeric"], description: "Type of goal"),
                "suggested_target": .init(type: "number", description: "Target value for the goal"),
                "suggested_min": .init(type: "number", description: "Minimum value"),
                "suggested_max": .init(type: "number", description: "Maximum value"),
                "reasoning": .init(type: "string", description: "Why this goal fits the user"),
                "linked_task_ids": .init(type: "array", description: "IDs of existing tasks relevant to this goal", items: .init(type: "string", properties: nil, required: nil))
            ],
            required: ["suggested_title", "suggested_description", "suggested_type", "suggested_target", "suggested_min", "suggested_max", "reasoning"]
        )
    }

    // MARK: - Rich Context Fetching

    /// Fetch rich user context for goal generation/suggestion
    private func fetchRichContext() async -> (memories: String, conversations: String, actionItems: String, persona: String, existingGoals: String, completedGoals: String, abandonedGoals: String, rawTasks: [TaskActionItem]) {
        // Fetch all context in parallel — no truncation, full items
        async let memoriesFetch = { () async -> [ServerMemory] in
            do { return try await APIClient.shared.getMemories(limit: 500) }
            catch { log("GoalsAI: Failed to fetch memories: \(error.localizedDescription)"); return [] }
        }()
        async let conversationsFetch = { () async -> [ServerConversation] in
            do { return try await APIClient.shared.getConversations(limit: 100, statuses: [.completed]) }
            catch { log("GoalsAI: Failed to fetch conversations: \(error.localizedDescription)"); return [] }
        }()
        async let actionItemsFetch = { () async -> ActionItemsListResponse? in
            do { return try await APIClient.shared.getActionItems(limit: 100, completed: false) }
            catch { log("GoalsAI: Failed to fetch action items: \(error.localizedDescription)"); return nil }
        }()
        async let personaFetch = { () async -> Persona? in
            do { return try await APIClient.shared.getPersona() }
            catch { log("GoalsAI: Failed to fetch persona: \(error.localizedDescription)"); return nil }
        }()
        async let goalsFetch = { () async -> [Goal] in
            do { return try await APIClient.shared.getGoals() }
            catch { log("GoalsAI: Failed to fetch goals: \(error.localizedDescription)"); return [] }
        }()
        async let historyFetch = { () async -> [Goal] in
            do { return try await APIClient.shared.getCompletedGoals() }
            catch { log("GoalsAI: Failed to fetch goal history: \(error.localizedDescription)"); return [] }
        }()

        let (memories, conversations, actionItems, persona, goals, goalHistory) = await (memoriesFetch, conversationsFetch, actionItemsFetch, personaFetch, goalsFetch, historyFetch)

        // Split goal history into completed vs abandoned
        let completed = goalHistory.filter { $0.completedAt != nil }
        let abandoned = goalHistory.filter { $0.completedAt == nil }

        let tasks = actionItems?.items ?? []
        log("GoalsAI: Fetched context — \(memories.count) memories, \(conversations.count) conversations, \(tasks.count) tasks, persona: \(persona != nil ? "yes" : "no"), \(goals.count) existing goals, \(completed.count) completed, \(abandoned.count) abandoned")

        // Build context strings — full content, no truncation
        let memoryContext = memories.map { $0.content }.joined(separator: "\n")
        let conversationContext = conversations
            .compactMap { $0.structured.overview.isEmpty ? nil : $0.structured.overview }
            .joined(separator: "\n")
        // Include task IDs so the AI can reference them for linking
        let actionItemsContext = tasks.map { "[\($0.id)] \($0.description)" }.joined(separator: "\n")
        let personaContext: String
        if let p = persona {
            personaContext = "\(p.name): \(p.description)"
        } else {
            personaContext = "No persona set"
        }
        let existingGoalsContext = goals.isEmpty
            ? "None"
            : goals.map { "- \($0.title) (\(Int($0.currentValue))/\(Int($0.targetValue)))" }.joined(separator: "\n")
        let completedGoalsContext = completed.isEmpty
            ? "None"
            : completed.map { "- \($0.title) (achieved \(Int($0.currentValue))/\(Int($0.targetValue)))" }.joined(separator: "\n")
        let abandonedGoalsContext = abandoned.isEmpty
            ? "None"
            : abandoned.map { "- \($0.title) (stopped at \(Int($0.currentValue))/\(Int($0.targetValue)))" }.joined(separator: "\n")

        return (memoryContext, conversationContext, actionItemsContext, personaContext, existingGoalsContext, completedGoalsContext, abandonedGoalsContext, tasks)
    }

    // MARK: - Generate Goal (automatic)

    /// Automatically generate and create a goal based on rich user context
    func generateGoal() async throws -> Goal {
        guard let client = geminiClient else {
            throw GoalsAIError.clientNotInitialized
        }

        let ctx = await fetchRichContext()

        // Check if there's enough context to generate a meaningful goal
        if ctx.memories.isEmpty && ctx.conversations.isEmpty && ctx.actionItems.isEmpty {
            log("GoalsAI: Not enough context to generate a goal")
            throw GoalsAIError.insufficientContext
        }

        // Build prompt
        let prompt = GoalPrompts.generateGoal
            .replacingOccurrences(of: "{persona_context}", with: ctx.persona)
            .replacingOccurrences(of: "{memory_context}", with: ctx.memories.isEmpty ? "No memories yet" : ctx.memories)
            .replacingOccurrences(of: "{conversation_context}", with: ctx.conversations.isEmpty ? "No recent conversations" : ctx.conversations)
            .replacingOccurrences(of: "{action_items_context}", with: ctx.actionItems.isEmpty ? "No active tasks" : ctx.actionItems)
            .replacingOccurrences(of: "{existing_goals}", with: ctx.existingGoals)
            .replacingOccurrences(of: "{completed_goals}", with: ctx.completedGoals)
            .replacingOccurrences(of: "{abandoned_goals}", with: ctx.abandonedGoals)

        log("GoalsAI: Model: gemini-3-pro-preview")
        log("GoalsAI: Context sizes — memories: \(ctx.memories.count) chars, conversations: \(ctx.conversations.count) chars, tasks: \(ctx.actionItems.count) chars, persona: \(ctx.persona.count) chars, existing goals: \(ctx.existingGoals), completed: \(ctx.completedGoals.count) chars, abandoned: \(ctx.abandonedGoals.count) chars")
        log("GoalsAI: Full prompt:\n\(prompt)")

        // Call Gemini
        let responseText = try await client.sendRequest(
            prompt: prompt,
            systemPrompt: "You are a goal coach. Generate one meaningful, achievable goal based on the user's full context.",
            responseSchema: goalSuggestionSchema
        )

        guard let data = responseText.data(using: .utf8) else {
            throw GoalsAIError.invalidResponse
        }

        let suggestion = try JSONDecoder().decode(GoalSuggestion.self, from: data)
        log("GoalsAI: Generated goal suggestion: '\(suggestion.suggestedTitle)' (\(suggestion.suggestedType)), description: \(suggestion.suggestedDescription ?? "none"), linked tasks: \(suggestion.linkedTaskIds ?? [])")

        // Auto-create the goal via API
        let goal = try await APIClient.shared.createGoal(
            title: suggestion.suggestedTitle,
            description: suggestion.suggestedDescription,
            goalType: suggestion.goalType,
            targetValue: suggestion.suggestedTarget,
            currentValue: 0,
            minValue: suggestion.suggestedMin,
            maxValue: suggestion.suggestedMax
        )

        // Sync to local storage
        _ = try? await GoalStorage.shared.syncServerGoal(goal)

        log("GoalsAI: Auto-created goal '\(goal.title)' (id: \(goal.id))")

        // Link suggested tasks to the goal
        if let taskIds = suggestion.linkedTaskIds, !taskIds.isEmpty {
            // Validate task IDs against actual fetched tasks
            let validIds = Set(ctx.rawTasks.map { $0.id })
            let confirmedIds = taskIds.filter { validIds.contains($0) }
            log("GoalsAI: Linking \(confirmedIds.count) tasks to goal \(goal.id)")

            for taskId in confirmedIds {
                do {
                    _ = try await APIClient.shared.updateActionItem(id: taskId, goalId: goal.id)
                    log("GoalsAI: Linked task \(taskId) to goal \(goal.id)")
                } catch {
                    log("GoalsAI: Failed to link task \(taskId): \(error.localizedDescription)")
                }
            }
        }

        return goal
    }

    // MARK: - Get Goal Advice

    /// Get AI-generated actionable advice for achieving a goal
    func getGoalAdvice(goal: Goal) async throws -> String {
        guard let client = geminiClient else {
            throw GoalsAIError.clientNotInitialized
        }

        // 1. Fetch context
        let memories = try await APIClient.shared.getMemories(limit: 15)
        let conversations = try await APIClient.shared.getConversations(limit: 10, statuses: [.completed])

        let memoryContext = memories
            .map { String($0.content.prefix(150)) }
            .joined(separator: "\n")

        let conversationContext = conversations
            .compactMap { $0.structured.overview.isEmpty ? nil : String($0.structured.overview.prefix(250)) }
            .joined(separator: "\n")

        let progressPct = goal.targetValue > 0
            ? (goal.currentValue / goal.targetValue) * 100
            : 0

        // 2. Build prompt
        let prompt = GoalPrompts.goalAdvice
            .replacingOccurrences(of: "{goal_title}", with: goal.title)
            .replacingOccurrences(of: "{current_value}", with: String(format: "%.0f", goal.currentValue))
            .replacingOccurrences(of: "{target_value}", with: String(format: "%.0f", goal.targetValue))
            .replacingOccurrences(of: "{progress_pct}", with: String(format: "%.1f", progressPct))
            .replacingOccurrences(of: "{conversation_context}", with: conversationContext.isEmpty ? "No recent conversations" : conversationContext)
            .replacingOccurrences(of: "{memory_context}", with: memoryContext.isEmpty ? "No facts available" : memoryContext)

        // 3. Call Gemini (text response, no schema)
        let response = try await client.sendTextRequest(
            prompt: prompt,
            systemPrompt: "You are a strategic advisor. Give specific, actionable advice based on user context. Be concise."
        )

        return response
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "\"'"))
    }

    // MARK: - Extract Progress from All Goals

    /// Extract progress for all active goals from text (e.g., after chat or conversation)
    func extractProgressFromAllGoals(text: String) async {
        guard text.count >= 10 else { return }

        do {
            let goals = try await APIClient.shared.getGoals()
            guard !goals.isEmpty else { return }

            log("GoalsAI: Checking \(goals.count) goals for progress in text (\(text.prefix(50))...)")

            for goal in goals {
                do {
                    if let result = try await extractProgress(text: text, goal: goal, updateIfFound: true),
                       result.found, let value = result.value {
                        log("GoalsAI: Found progress for '\(goal.title)': \(value)")
                    }
                } catch {
                    // Swallow per-goal errors to continue checking other goals
                    log("GoalsAI: Error extracting progress for '\(goal.title)': \(error.localizedDescription)")
                }
            }
        } catch {
            log("GoalsAI: Failed to fetch goals for progress extraction: \(error.localizedDescription)")
        }
    }

    // MARK: - Extract Progress

    /// Extract goal progress from text and optionally update via API
    func extractProgress(text: String, goal: Goal, updateIfFound: Bool = true) async throws -> ProgressExtraction? {
        guard let client = geminiClient else {
            throw GoalsAIError.clientNotInitialized
        }

        guard text.count >= 5 else {
            return nil
        }

        // Build prompt
        let prompt = GoalPrompts.extractProgress
            .replacingOccurrences(of: "{goal_title}", with: goal.title)
            .replacingOccurrences(of: "{goal_type}", with: goal.goalType.rawValue)
            .replacingOccurrences(of: "{current_value}", with: String(format: "%.0f", goal.currentValue))
            .replacingOccurrences(of: "{target_value}", with: String(format: "%.0f", goal.targetValue))
            .replacingOccurrences(of: "{text}", with: String(text.prefix(500)))

        // Build response schema
        let responseSchema = GeminiRequest.GenerationConfig.ResponseSchema(
            type: "object",
            properties: [
                "found": .init(type: "boolean", description: "Whether progress was found"),
                "value": .init(type: "number", description: "The extracted progress value"),
                "reasoning": .init(type: "string", description: "Brief explanation")
            ],
            required: ["found"]
        )

        // Call Gemini
        let responseText = try await client.sendRequest(
            prompt: prompt,
            systemPrompt: "Extract goal progress from text. Only return found=true if confident about the specific goal.",
            responseSchema: responseSchema
        )

        guard let data = responseText.data(using: .utf8) else {
            return nil
        }

        let result = try JSONDecoder().decode(ProgressExtraction.self, from: data)

        // Update via API if found and requested
        if updateIfFound, result.found, let value = result.value, value != goal.currentValue {
            log("GoalsAI: Updating progress for '\(goal.title)': \(goal.currentValue) -> \(value)")
            _ = try await APIClient.shared.updateGoalProgress(goalId: goal.id, currentValue: value)
        }

        return result
    }
}

// MARK: - Errors

enum GoalsAIError: LocalizedError {
    case clientNotInitialized
    case invalidResponse
    case insufficientContext

    var errorDescription: String? {
        switch self {
        case .clientNotInitialized:
            return "Gemini client not initialized. Check GEMINI_API_KEY."
        case .invalidResponse:
            return "Invalid response from AI service"
        case .insufficientContext:
            return "Not enough user context to generate a meaningful goal"
        }
    }
}
