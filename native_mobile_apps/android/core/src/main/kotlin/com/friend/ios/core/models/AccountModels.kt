package com.friend.ios.core.models

/** Port of `AccountModels.swift`. */

/**
 * Who is signed in, as the backend knows it (`GET v1/users/profile`): the name and email shown on
 * top of Settings when this phone has none saved.
 */
data class UserProfile(val name: String?, val email: String?)

/** Usage for one period (`GET v1/users/me/usage`, Flutter `usage_page`). */
data class UsageStats(
    val totals: Totals,
    /** Hourly (today), daily (month), monthly (year) or yearly (all time) buckets, oldest first. */
    val history: List<Pair<String, Totals>>,
) {
    enum class Period(val rawValue: String) { Today("today"), Monthly("monthly"), Yearly("yearly"), AllTime("all_time") }

    data class Totals(val transcriptionSeconds: Int, val words: Int, val insights: Int, val memories: Int) {
        val isEmpty: Boolean get() = transcriptionSeconds == 0 && words == 0 && insights == 0 && memories == 0
    }
}

/** Fair-use standing (`GET v1/fair-use/status`). */
data class FairUseStatus(
    /** `none`, `warning`, `throttle` or `restrict`. */
    val stage: String,
    val caseReference: String?,
    val today: Window,
    val threeDays: Window,
    val week: Window,
    /** Ready-to-show text from the server. */
    val message: String,
) {
    data class Window(val usedHours: Double, val limitHours: Double, val percent: Double) {
        companion object {
            fun of(used: Double, limit: Double) = Window(used, limit, if (limit > 0) used / limit * 100 else 0.0)
        }
    }
}

/** An installed app that reads or writes the user's data (Flutter `data_privacy_page`). */
data class AppDataAccess(
    val id: String,
    val name: String,
    val imageURL: String?,
    val readsConversations: Boolean,
    val readsMemories: Boolean,
    /** `memory_creation`, `transcript_processed`, `audio_bytes`. */
    val trigger: String?,
)
