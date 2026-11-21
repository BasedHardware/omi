package com.friend.ios.core.models

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Port of `HealthSummary.swift`: what the health store (Apple Health on iOS, Health Connect here)
 * reports for the last days, in the shape Flutter's `AppleHealthService.swift` (`getHealthSummary`)
 * builds and `PUT v1/integrations/apple-health/sync` stores for the chat. Nested keys stay camelCase
 * (`dateMs`, `sleepHours` ...) as Flutter sends them.
 */
data class HealthSummary(
    val periodDays: Int,
    val dailySteps: List<DailySteps> = emptyList(),
    val dailyEnergy: List<DailyEnergy> = emptyList(),
    val dailySleep: List<DailySleep> = emptyList(),
    val sleepSessions: List<SleepSession> = emptyList(),
    val totalSleepHours: Double = 0.0,
    val totalInBedHours: Double = 0.0,
    val heartRate: HeartRate? = null,
    val workouts: List<Workout> = emptyList(),
) {
    data class DailySteps(val date: String, val dateMs: Double, val steps: Int)

    data class DailyEnergy(val date: String, val dateMs: Double, val calories: Double)

    data class DailySleep(val date: String, val sleepHours: Double)

    /** [type]: core, deep, rem, asleep, inBed, awake, unknown. */
    data class SleepSession(val startDate: Double, val endDate: Double, val durationMinutes: Double, val type: String)

    data class Workout(
        val type: String,
        val startDate: Double,
        val endDate: Double,
        val durationMinutes: Double,
        val caloriesBurned: Double?,
        val distanceKm: Double?,
    ) {
        val jsonObject: JsonObject
            get() = buildJsonObject {
                put("type", type)
                put("startDate", startDate)
                put("endDate", endDate)
                put("durationMinutes", durationMinutes)
                caloriesBurned?.let { put("caloriesBurned", it) }
                distanceKm?.let { put("distanceKm", it) }
            }
    }

    data class HeartRate(val average: Double?, val minimum: Double?, val maximum: Double?)

    val totalSteps: Int get() = dailySteps.sumOf { it.steps }

    val totalActiveEnergy: Double get() = dailyEnergy.sumOf { it.calories }

    /** Something to send: an all-empty summary means no access (or no data). */
    val hasData: Boolean
        get() = totalSteps > 0 || totalActiveEnergy > 0 || sleepSessions.isNotEmpty() || heartRate?.average != null || workouts.isNotEmpty()

    /**
     * The request body Flutter's `syncHealthDataToBackend` builds (backend `AppleHealthSyncData`).
     * Averages divide by the period as Flutter does (steps with integer division).
     */
    val syncBody: JsonObject
        get() {
            val days = maxOf(periodDays, 1)
            return buildJsonObject {
                put("period_days", periodDays)
                put("total_steps", totalSteps)
                put("average_steps_per_day", totalSteps / days)
                put("daily_steps", JsonArray(dailySteps.map { buildJsonObject { put("date", it.date); put("dateMs", it.dateMs); put("steps", it.steps) } }))
                put("total_sleep_hours", totalSleepHours)
                put("total_in_bed_hours", totalInBedHours)
                put("sleep_sessions_count", sleepSessions.size)
                put(
                    "sleep_sessions",
                    JsonArray(
                        sleepSessions.map {
                            buildJsonObject {
                                put("startDate", it.startDate)
                                put("endDate", it.endDate)
                                put("durationMinutes", it.durationMinutes)
                                put("type", it.type)
                            }
                        },
                    ),
                )
                put("daily_sleep", JsonArray(dailySleep.map { buildJsonObject { put("date", it.date); put("sleepHours", it.sleepHours) } }))
                put("total_active_energy", totalActiveEnergy)
                put("average_active_energy_per_day", totalActiveEnergy / days)
                put(
                    "daily_active_energy",
                    JsonArray(dailyEnergy.map { buildJsonObject { put("date", it.date); put("dateMs", it.dateMs); put("calories", it.calories) } }),
                )
                put("workouts", JsonArray(workouts.map { it.jsonObject }))
                val rate = heartRate
                if (rate?.average != null) {
                    put("heart_rate_average", rate.average)
                    // Swift drops a key assigned nil: a missing bound is left out, not null.
                    rate.minimum?.let { put("heart_rate_min", it) }
                    rate.maximum?.let { put("heart_rate_max", it) }
                }
            }
        }
}
