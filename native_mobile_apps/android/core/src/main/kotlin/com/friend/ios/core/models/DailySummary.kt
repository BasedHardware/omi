package com.friend.ios.core.models

import java.time.LocalDate

/** Port of `DailySummary.swift`: a day in review (`v1/users/daily-summaries`, Omi's "Daily Recaps"). */
data class DailySummary(
    val id: String,
    /** Local calendar date, `YYYY-MM-DD`. */
    val date: String,
    val headline: String,
    val overview: String,
    val emoji: String?,
    val conversationCount: Int?,
    val highlights: List<Highlight>,
    val decisions: List<String>,
) {
    data class Highlight(val topic: String, val emoji: String?, val summary: String)

    /** The date as a local day. */
    val day: LocalDate? get() = runCatching { LocalDate.parse(date) }.getOrNull()
}
