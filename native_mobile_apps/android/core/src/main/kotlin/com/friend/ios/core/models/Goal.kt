package com.friend.ios.core.models

import java.time.Instant

/**
 * Port of `Goal.swift`: something the user works toward, with a number to track (`GoalResponse`,
 * numeric goals as in Flutter's goals widget: current of target).
 */
data class Goal(
    val id: String,
    val title: String,
    val current: Double,
    val target: Double,
    val unit: String? = null,
    val createdAt: Instant? = null,
) {
    /** 0...1, as Flutter's `progressPercentage`: a goal without a target is done once it has any progress. */
    val progress: Double
        get() {
            if (target <= 0) return if (current > 0) 1.0 else 0.0
            return (current / target).coerceIn(0.0, 1.0)
        }
}
