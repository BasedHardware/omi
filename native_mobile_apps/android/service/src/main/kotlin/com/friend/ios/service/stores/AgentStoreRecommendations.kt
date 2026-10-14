package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Recommendation
import kotlinx.coroutines.CancellationException

// Port of `AgentStore+Recommendations.swift`: "What matters now" on Home: the backend's
// recommendations, minus what Omi already has, what the user answered and what went stale;
// every answer goes back as feedback.

/**
 * Backend recommendations minus tasks Omi already has (a run or a workstream), ones the user
 * decided about, and stale ones (past `expires_at`).
 */
fun AgentStore.openRecommendations(tasks: List<ActionItem>): List<Recommendation> {
    val handled = runs.keys + tasks.filter { it.workstreamID != null || it.isCompleted }.map { it.id }
    val now = now()
    return recommendations.filter { recommendation ->
        if (recommendation.dedupeKey in decidedRecommendations || recommendation.isExpired(now)) return@filter false
        val taskID = recommendation.taskID ?: return@filter true
        taskID !in handled
    }
}

/**
 * The user's answer to a recommendation: it leaves Home at once, and the backend hears it (so it
 * does not come back: later pauses it a day, not now a month).
 */
suspend fun AgentStore.decide(recommendation: Recommendation, decision: Recommendation.Decision) {
    decidedRecommendations = decidedRecommendations + recommendation.dedupeKey
    try {
        val generation = api.accountGeneration()
        api.sendRecommendationFeedback(recommendation, decision, generation)
    } catch (e: CancellationException) {
        throw e
    } catch (_: Exception) {
        // Stays hidden for this session; the backend asks again on a later launch.
    }
}

suspend fun AgentStore.loadRecommendations() {
    recommendations = try {
        api.whatMattersNow()
    } catch (e: CancellationException) {
        throw e
    } catch (_: Exception) {
        emptyList()
    }
}
