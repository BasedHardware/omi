package com.friend.ios.service.stores

import com.friend.ios.core.models.Recommendation

/**
 * Port of `Recommendation+Wording.swift`: how a "What matters now" recommendation reads on Home:
 * the backend's next action as a question, and where it comes from. Pure (no model call), so the
 * wording is testable.
 */

/** Where the recommendation comes from, beyond a conversation the app can name itself. */
sealed interface RecommendationOrigin {
    /** The user wrote the task themselves. */
    data object AddedByYou : RecommendationOrigin
    /** Someone or something is waiting on the user. */
    data object WaitingOnYou : RecommendationOrigin
    /** The backend's own words (an LLM preview), shown as they are. */
    data class Text(val text: String) : RecommendationOrigin
}

/**
 * "Send Anna the Thursday follow-up?": the next action (or the headline when the action is
 * missing or a long sentence) without its closing period, asked.
 */
val Recommendation.question: String
    get() {
        var text = plainAction(action)
        if (text.isEmpty() || text.length > 90) text = plainAction(headline)
        while (text.isNotEmpty() && text.last() in ".!:;") text = text.dropLast(1)
        text = text.trim()
        if (text.isEmpty()) return headline
        return if (text.endsWith("?")) text else "$text?"
    }

private val whyNowTemplates = listOf(
    "^this (task|item|commitment) (is|was) (due|overdue)\\b",
    "^(it is|it's|this is) (due|overdue)\\b",
    "^(due|overdue) (today|tomorrow|in \\d+ days?|by \\d+ days?)\\.?$",
    "concrete next action",
    "^(this|the) (task|item) (was )?(recently|explicitly) created",
    "^created (directly )?by you",
    "^the due date (has passed|is (today|soon|near))",
    "^(it|this) has a (due date|deadline)( (today|soon|coming up))?\\.?$",
).map(::Regex)

/**
 * `whyNow` when it says something specific (a person, a place, a reason); null for the
 * backend's template eligibility lines ("This task is due today and has a concrete next
 * action.", "This task is overdue by 2 days."), which only restate the due date.
 */
val Recommendation.specificWhyNow: String?
    get() {
        val text = whyNow.trim()
        if (text.isEmpty()) return null
        val lowered = text.lowercase()
        if (whyNowTemplates.any { it.containsMatchIn(lowered) }) return null
        return text
    }

/** The goal or workstream, when it says more than the title (the backend often repeats it). */
val Recommendation.distinctGoalLabel: String?
    get() {
        val label = goalLabel?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        val normalized = normalizedWords(label)
        return if (listOf(headline, action, question).any { normalizedWords(it) == normalized }) null else label
    }

/**
 * The evidence preview in words worth showing. The backend's canonical previews about due
 * dates repeat `whyNow` and "Linked to 2 evidence sources" says nothing, so those are null.
 */
val Recommendation.origin: RecommendationOrigin?
    get() {
        val preview = evidencePreview.trim()
        if (preview.isEmpty()) return null
        if (preview == "Created directly by you.") return RecommendationOrigin.AddedByYou
        if (preview == "Progress is waiting on input.") return RecommendationOrigin.WaitingOnYou
        val quiet = listOf("Due in ", "Due date has passed", "Linked to ", "Canonical state ", "Relevant context is active")
        if (quiet.any { preview.startsWith(it) }) return null
        return RecommendationOrigin.Text(preview)
    }

/** Action texts can arrive coded as `verb:text`; the text part reads as a sentence. */
private fun plainAction(text: String): String {
    val trimmed = text.trim()
    val colon = trimmed.indexOf(':')
    if (colon > 0) {
        val verb = trimmed.substring(0, colon)
        if (verb.all { it.isLetter() || it == '_' } && verb.none { it.isUpperCase() }) return trimmed.substring(colon + 1).trim()
    }
    return trimmed
}

private fun normalizedWords(text: String): String = text.lowercase().trim { !it.isLetterOrDigit() }
