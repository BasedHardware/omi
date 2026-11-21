package com.friend.ios.network.endpoints

import com.friend.ios.core.models.AppDataAccess
import com.friend.ios.core.models.FairUseStatus
import com.friend.ios.core.models.UsageStats
import com.friend.ios.core.models.UserProfile
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import com.friend.ios.network.await
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.File
import java.io.IOException
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * Port of `APIClient+Profile.swift` (account and data: export, usage, fair use, cancel
 * subscription, referral, app data access) and `APIClient+Users.swift` (language, delete account).
 */
interface ProfileAPI {
    /** `GET v1/users/profile` → the account's name and email (empty strings read as unknown). */
    suspend fun userProfile(): UserProfile
    /** `GET v1/users/export`: one JSON file with everything Omi stores, in [directory]. */
    suspend fun exportAllData(directory: File): File
    /** `GET v1/users/me/usage?period=&time_zone=`. */
    suspend fun usage(period: UsageStats.Period, timeZone: String): UsageStats
    /** `GET v1/fair-use/status`. Missing limits fall back to Flutter's 2 / 8 / 10 hours. */
    suspend fun fairUseStatus(): FairUseStatus
    /** `DELETE v1/payments/subscription` with `{reason, reason_details}`. */
    suspend fun cancelSubscription(reason: String?, details: String?)
    /** `GET v1/users/me/referral` → the user's invite link. */
    suspend fun referralURL(): String?
    /** Installed apps with an external integration, and what they read and when they run. */
    suspend fun appsWithDataAccess(): List<AppDataAccess>
    /** `GET v1/users/language` → primary language code, if set. */
    suspend fun primaryLanguage(): String?
    /** `PATCH v1/users/language`; the server also updates transcription preferences. */
    suspend fun setPrimaryLanguage(code: String)
    /** `DELETE v1/users/delete-account`. */
    suspend fun deleteAccount(reason: String?)

    // Sign-in and onboarding (and-onboarding), `APIClient+Users.swift`
    /** `GET v1/users/onboarding` → whether onboarding was finished and how the user found Omi. */
    suspend fun onboardingState(): OnboardingState
    /** `PATCH v1/users/onboarding` with whichever fields are set. */
    suspend fun updateOnboarding(completed: Boolean?, acquisitionSource: String?)
    /** `PUT v1/users/time-zone`. */
    suspend fun setTimeZone(identifier: String)
}

/** Port of `OnboardingState` (`APIClient+Users.swift`). */
data class OnboardingState(val completed: Boolean, val acquisitionSource: String?)

internal class ProfileEndpoints(private val http: HttpCore) : ProfileAPI {
    override suspend fun userProfile(): UserProfile {
        val o = http.jsonObject(Method.GET, "v1/users/profile")
        fun text(key: String) = o.string(key)?.trim()?.takeIf { it.isNotEmpty() }
        return UserProfile(text("name"), text("email"))
    }

    override suspend fun exportAllData(directory: File): File {
        val request = http.request(Method.GET, "v1/users/export")
        val client = http.client.newBuilder().callTimeout(300, TimeUnit.SECONDS).readTimeout(300, TimeUnit.SECONDS).build()
        val response = try {
            client.newCall(request).await()
        } catch (e: IOException) {
            throw APIError.Transport(e.message ?: e.toString())
        }
        return response.use {
            withContext(Dispatchers.IO) {
                if (it.code !in 200..299) throw APIError.Http(it.code, it.body?.string().orEmpty().take(500))
                val folder = File(directory, "omi-export-${UUID.randomUUID()}").apply { mkdirs() }
                val destination = File(folder, "omi-export.json")
                it.body?.byteStream()?.use { input -> destination.outputStream().use { out -> input.copyTo(out) } }
                destination
            }
        }
    }

    override suspend fun usage(period: UsageStats.Period, timeZone: String): UsageStats {
        val root = http.jsonObject(Method.GET, "v1/users/me/usage", query = listOf("period" to period.rawValue, "time_zone" to timeZone))
        fun totals(json: JsonObject?) = UsageStats.Totals(
            transcriptionSeconds = json?.int("transcription_seconds") ?: 0, words = json?.int("words_transcribed") ?: 0,
            insights = json?.int("insights_gained") ?: 0, memories = json?.int("memories_created") ?: 0,
        )
        val history = root.objects("history").mapNotNull { item -> item.string("date")?.let { it to totals(item) } }
        return UsageStats(totals(root.obj(period.rawValue)), history)
    }

    override suspend fun fairUseStatus(): FairUseStatus {
        val root = http.jsonObject(Method.GET, "v1/fair-use/status")
        val limits = root.obj("limits") ?: JsonObject(emptyMap())
        return FairUseStatus(
            stage = root.string("stage") ?: "none",
            caseReference = root.string("case_ref")?.takeIf { it.isNotEmpty() },
            today = FairUseStatus.Window.of(root.double("speech_hours_today") ?: 0.0, limits.double("daily_hours") ?: 2.0),
            threeDays = FairUseStatus.Window.of(root.double("speech_hours_3day") ?: 0.0, limits.double("three_day_hours") ?: 8.0),
            week = FairUseStatus.Window.of(root.double("speech_hours_weekly") ?: 0.0, limits.double("weekly_hours") ?: 10.0),
            message = root.string("message").orEmpty(),
        )
    }

    override suspend fun cancelSubscription(reason: String?, details: String?) {
        val fields = buildJsonObject {
            reason?.let { put("reason", it) }
            if (!details.isNullOrEmpty()) put("reason_details", details)
        }
        val body = if (fields.isEmpty()) Body.None else Body.Json(fields.toString())
        val text = http.data(Method.DELETE, "v1/payments/subscription", body = body)
        if (JsonAccess.obj(text).string("status") != "ok") throw APIError.Http(200, text.take(300))
    }

    override suspend fun referralURL(): String? = http.jsonObject(Method.GET, "v1/users/me/referral").string("referral_url")

    override suspend fun appsWithDataAccess(): List<AppDataAccess> {
        val query = listOf("offset" to "0", "limit" to "100", "installed_apps" to "true")
        return http.jsonObject(Method.GET, "v2/apps/search", query = query).objects("data").mapNotNull { app ->
            val id = app.string("id") ?: return@mapNotNull null
            if (app.bool("enabled") != true || "external_integration" !in app.strings("capabilities")) return@mapNotNull null
            val integration = app.obj("external_integration")
            val actions = integration?.objects("actions")?.mapNotNull { it.string("action") }?.toSet().orEmpty()
            AppDataAccess(
                id = id, name = app.string("name") ?: id, imageURL = app.string("image"),
                readsConversations = actions.any { it in setOf("create_conversation", "read_conversations") },
                readsMemories = actions.any { it in setOf("create_facts", "read_memories") },
                trigger = integration?.string("triggers_on"),
            )
        }
    }

    override suspend fun primaryLanguage(): String? = http.jsonObject(Method.GET, "v1/users/language").string("language")?.takeIf { it.isNotEmpty() }

    override suspend fun setPrimaryLanguage(code: String) {
        http.jsonObject(Method.PATCH, "v1/users/language", json = buildJsonObject { put("language", code) })
    }

    override suspend fun deleteAccount(reason: String?) {
        val body = reason?.let { Body.Json(buildJsonObject { put("reason", it) }.toString()) } ?: Body.None
        http.data(Method.DELETE, "v1/users/delete-account", body = body)
    }

    // Sign-in and onboarding (and-onboarding)
    override suspend fun onboardingState(): OnboardingState {
        val o = http.jsonObject(Method.GET, "v1/users/onboarding")
        val source = o.string("acquisition_source")
        return OnboardingState(completed = o.bool("completed") ?: false, acquisitionSource = source?.takeIf { it.isNotEmpty() })
    }

    override suspend fun updateOnboarding(completed: Boolean?, acquisitionSource: String?) {
        http.jsonObject(
            Method.PATCH, "v1/users/onboarding",
            json = buildJsonObject {
                completed?.let { put("completed", it) }
                acquisitionSource?.let { put("acquisition_source", it) }
            },
        )
    }

    override suspend fun setTimeZone(identifier: String) {
        http.data(Method.PUT, "v1/users/time-zone", body = Body.Json(buildJsonObject { put("time_zone", identifier) }.toString()))
    }
}
