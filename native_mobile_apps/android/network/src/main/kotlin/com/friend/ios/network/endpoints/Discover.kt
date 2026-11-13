package com.friend.ios.network.endpoints

import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.UUID

// Port of the "For you" part of `APIClient+Discover.swift`. Its other parts live with their
// areas: the announcements in `Announcements.kt`, conversation and recap search (with
// `ConversationSearchFilter`) in `Search.kt`.

/** One "For you" card (`GET v1/proactivity/feed`, Flutter `home_for_you`). */
data class ForYouItem(
    val id: String,
    /** Who made it; "Stop these" hides every item from the same producer. */
    val producer: String,
    val title: String,
    val body: String,
    val target: Target?,
    /** `none`, `thumbs_up`, `thumbs_down`. */
    val feedback: String = "none",
) {
    sealed interface Target {
        data class Conversation(val id: String) : Target
        data class Task(val id: String) : Target
    }

    /** Flutter's outcome actions; `StopThese` is `producer_disabled`. */
    enum class Feedback(val rawValue: String) {
        Shown("shown"), Opened("opened"), Helpful("thumbs_up"), NotHelpful("thumbs_down"), StopThese("producer_disabled"), Dismissed("dismissed")
    }
}

interface DiscoverAPI {
    /** `GET v1/proactivity/feed?limit=20`; null when the feed is turned off for the user. */
    suspend fun forYouFeed(): List<ForYouItem>?

    /** `POST v1/proactivity/items/{id}/outcomes` with a fresh `event_id` (extra fields are rejected). */
    suspend fun sendForYouFeedback(itemID: String, feedback: ForYouItem.Feedback)
}

internal class DiscoverEndpoints(private val http: HttpCore) : DiscoverAPI {
    override suspend fun forYouFeed(): List<ForYouItem>? {
        val text = http.data(Method.GET, "v1/proactivity/feed", query = listOf("limit" to "20"))
        val root = http.decode(JsonElement.serializer(), text) as? JsonObject ?: JsonObject(emptyMap())
        if ((root["enabled"] as? JsonPrimitive)?.booleanOrNull != true) return null
        return (root["items"] as? JsonArray).orEmpty().mapNotNull { element ->
            val item = element as? JsonObject ?: return@mapNotNull null
            val id = item.string("id") ?: return@mapNotNull null
            if ((item["dismissed"] as? JsonPrimitive)?.booleanOrNull == true) return@mapNotNull null
            val target = item["target"] as? JsonObject
            val targetID = target?.string("id")
            ForYouItem(
                id = id, producer = item.string("producer") ?: "", title = item.string("title") ?: "",
                body = item.string("body") ?: "",
                target = targetID?.let { if (target.string("kind") == "action_item") ForYouItem.Target.Task(it) else ForYouItem.Target.Conversation(it) },
                feedback = item.string("feedback") ?: "none",
            )
        }
    }

    override suspend fun sendForYouFeedback(itemID: String, feedback: ForYouItem.Feedback) {
        val body = buildJsonObject {
            put("event_id", UUID.randomUUID().toString().lowercase())
            put("action", feedback.rawValue)
            // The same channel names as iOS; the backend only knows `ios` and `flutter` surfaces.
            put("surface", "ios")
            put("channel", "feed")
        }
        http.data(Method.POST, "v1/proactivity/items/$itemID/outcomes", body = Body.Json(body.toString()))
    }
}
