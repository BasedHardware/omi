import Foundation

/// Service that automatically generates goals once per day
/// and removes stale goals with no progress for 3+ days
@MainActor
class GoalGenerationService {
    static let shared = GoalGenerationService()

    private static let kLastGenerationDate = "goalGeneration_lastDate"
    private let maxActiveGoals = 3
    private let staleGoalDays: TimeInterval = 3 * 86400 // 3 days

    private init() {}

    // MARK: - Conversation Hook

    /// Called after each conversation is saved.
    /// Removes stale goals and checks if a day has passed since last generation.
    func onConversationCreated() {
        Task {
            await removeStaleGoals()
            await checkDailyGeneration()
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

    // MARK: - Daily Generation Check

    /// Check if a new calendar day has started since last goal generation
    private func checkDailyGeneration() async {
        let lastDate = UserDefaults.standard.object(forKey: Self.kLastGenerationDate) as? Date

        if lastDate == nil {
            log("GoalGenerationService: First run, generating immediately")
            await generateGoalIfNeeded()
            return
        }

        let calendar = Calendar.current
        guard let lastDate = lastDate, !calendar.isDateInToday(lastDate) else {
            log("GoalGenerationService: Already generated today (lastDate: \(lastDate!)), skipping")
            return
        }

        log("GoalGenerationService: New day — last generation was \(lastDate), triggering generation")
        await generateGoalIfNeeded()
    }

    /// Generate a goal if the user has room for more
    private func generateGoalIfNeeded() async {
        do {
            let goals = try await APIClient.shared.getGoals()
            let activeGoals = goals.filter { $0.isActive }

            if activeGoals.count >= maxActiveGoals {
                log("GoalGenerationService: User already has \(activeGoals.count) active goals (max \(maxActiveGoals)), skipping")
                UserDefaults.standard.set(Date(), forKey: Self.kLastGenerationDate)
                return
            }

            log("GoalGenerationService: User has \(activeGoals.count)/\(maxActiveGoals) goals, generating one...")

            let goal = try await GoalsAIService.shared.generateGoal()

            UserDefaults.standard.set(Date(), forKey: Self.kLastGenerationDate)
            log("GoalGenerationService: Successfully created goal '\(goal.title)'")

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

    /// Manual trigger that bypasses the daily check
    func generateNow() async {
        log("GoalGenerationService: Manual generation triggered")
        await removeStaleGoals()
        await generateGoalIfNeeded()
    }
}
