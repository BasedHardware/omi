import Foundation
import OmiCore
import OmiNetwork

/// "What matters now" on Home: the backend's recommendations, minus what Omi already has, what
/// the user answered and what went stale; every answer goes back as feedback.
public extension AgentStore {
    /// Backend recommendations minus tasks Omi already has (a run or a workstream), ones the user
    /// decided about, and stale ones (past `expires_at`).
    func openRecommendations(tasks: [ActionItem]) -> [Recommendation] {
        let handled = Set(runs.keys).union(tasks.filter { $0.workstreamID != nil || $0.isCompleted }.map(\.id))
        let now = now()
        return recommendations.filter { recommendation in
            guard !decidedRecommendations.contains(recommendation.dedupeKey), !recommendation.isExpired(at: now) else { return false }
            guard let taskID = recommendation.taskID else { return true }
            return !handled.contains(taskID)
        }
    }

    /// The user's answer to a recommendation: it leaves Home at once, and the backend hears it
    /// (so it does not come back: later pauses it a day, not now a month).
    func decide(_ recommendation: Recommendation, _ decision: Recommendation.Decision) async {
        decidedRecommendations.insert(recommendation.dedupeKey)
        do {
            let generation = try await api.accountGeneration()
            try await api.sendRecommendationFeedback(recommendation, decision: decision, generation: generation)
        } catch {
            // Stays hidden for this session; the backend asks again on a later launch.
        }
    }

    func loadRecommendations() async {
        recommendations = await (try? api.whatMattersNow()) ?? []
    }
}
