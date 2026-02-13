import Foundation

/// Service that automatically generates goals every 100 conversations
/// and removes stale goals with no progress for 3+ days
@MainActor
class GoalGenerationService {
    static let shared = GoalGenerationService()

    private static let kLastGenerationConversationCount = "goalGeneration_lastConversationCount"
    private let conversationInterval = 100
    private let maxActiveGoals = 3
    private let staleGoalDays: TimeInterval = 3 * 86400 // 3 days

    private init() {}

    // MARK: - Conversation Hook

    /// Called after each conversation is saved.
    /// Removes stale goals and checks if we've hit the 100-conversation milestone.
    func onConversationCreated() {
        Task {
            await removeStaleGoals()
            await checkConversationMilestone()
        }
    }

    // MARK: - Stale Goal Removal

    /// Complete (deactivate) goals that haven't had any progress update in 3+ days
    /// Instead of deleting, marks them as completed so they appear in history
    private func removeStaleGoals() async {
        do {
            let goals = try await APIClient.shared.getGoals()
            let now = Date()

            for goal in goals where goal.isActive {
                let daysSinceUpdate = now.timeIntervalSince(goal.updatedAt)
                if daysSinceUpdate >= staleGoalDays {
                    log("GoalGenerationService: Completing stale goal '\(goal.title)' — no update for \(Int(daysSinceUpdate / 86400)) days")
                    _ = try await APIClient.shared.completeGoal(id: goal.id)
                    try? await GoalStorage.shared.markCompleted(backendId: goal.id)
                    NotificationCenter.default.post(name: .goalAutoCreated, object: nil)
                }
            }
        } catch {
            log("GoalGenerationService: Failed to check/complete stale goals: \(error.localizedDescription)")
        }
    }

    // MARK: - Conversation Milestone Check

    /// Check if the user has crossed the next 100-conversation milestone
    private func checkConversationMilestone() async {
        do {
            let totalCount = try await APIClient.shared.getConversationsCount()
            let lastCount = UserDefaults.standard.integer(forKey: Self.kLastGenerationConversationCount)

            // First time: seed the count without generating
            if lastCount == 0 {
                UserDefaults.standard.set(totalCount, forKey: Self.kLastGenerationConversationCount)
                log("GoalGenerationService: Seeded conversation count at \(totalCount)")
                return
            }

            let conversationsSinceLast = totalCount - lastCount
            if conversationsSinceLast < conversationInterval {
                return
            }

            log("GoalGenerationService: Milestone reached — \(conversationsSinceLast) conversations since last generation (total: \(totalCount))")
            await generateGoalIfNeeded(totalCount: totalCount)

        } catch {
            log("GoalGenerationService: Failed to check conversation count: \(error.localizedDescription)")
        }
    }

    /// Generate a goal if the user has room for more
    private func generateGoalIfNeeded(totalCount: Int) async {
        do {
            let goals = try await APIClient.shared.getGoals()
            let activeGoals = goals.filter { $0.isActive }

            if activeGoals.count >= maxActiveGoals {
                log("GoalGenerationService: User already has \(activeGoals.count) active goals (max \(maxActiveGoals)), skipping")
                UserDefaults.standard.set(totalCount, forKey: Self.kLastGenerationConversationCount)
                return
            }

            log("GoalGenerationService: User has \(activeGoals.count)/\(maxActiveGoals) goals, generating one...")

            let goal = try await GoalsAIService.shared.generateGoal()

            UserDefaults.standard.set(totalCount, forKey: Self.kLastGenerationConversationCount)
            log("GoalGenerationService: Successfully created goal '\(goal.title)' at conversation #\(totalCount)")

            NotificationService.shared.sendNotification(
                title: "New Goal",
                message: goal.title,
                assistantId: "goals"
            )

            NotificationCenter.default.post(name: .goalAutoCreated, object: goal)

        } catch {
            log("GoalGenerationService: Failed to generate goal: \(error.localizedDescription)")
        }
    }

    /// Manual trigger that bypasses the conversation count check
    func generateNow() async {
        log("GoalGenerationService: Manual generation triggered")
        await removeStaleGoals()
        let totalCount = (try? await APIClient.shared.getConversationsCount()) ?? 0
        await generateGoalIfNeeded(totalCount: totalCount)
    }
}
