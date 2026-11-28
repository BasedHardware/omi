package com.friend.ios.network.endpoints

import com.friend.ios.core.models.Announcement
import com.friend.ios.network.HttpCore
import com.friend.ios.network.HttpCore.Body
import com.friend.ios.network.HttpCore.Method
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Port of the announcement half of `APIClient+Discover.swift` (`backend/routers/announcements.py`). */
interface AnnouncementsAPI {
    /** `GET v1/announcements/changelogs`: from `fromVersion` (exclusive) to `toVersion`, or the latest `limit`. */
    suspend fun changelogs(fromVersion: String?, toVersion: String?, limit: Int): List<Announcement>
    /** `GET v1/announcements/pending?app_version=X.Y.Z+build&platform=android&trigger=`. */
    suspend fun pendingAnnouncements(appVersion: String, versionUpgrade: Boolean): List<Announcement>
    /** `POST v1/announcements/{id}/dismiss` with `{"cta_clicked": ...}`. */
    suspend fun dismissAnnouncement(id: String, buttonTapped: Boolean)
}

internal class AnnouncementsEndpoints(private val http: HttpCore) : AnnouncementsAPI {
    override suspend fun changelogs(fromVersion: String?, toVersion: String?, limit: Int): List<Announcement> {
        val query = if (fromVersion != null && toVersion != null) listOf("from_version" to fromVersion, "to_version" to toVersion) else listOf("limit" to "$limit")
        return JsonAccess.array(http.data(Method.GET, "v1/announcements/changelogs", query = query)).mapNotNull { (it as? JsonObject)?.let(AnnouncementMapper::map) }
    }

    override suspend fun pendingAnnouncements(appVersion: String, versionUpgrade: Boolean): List<Announcement> {
        val query = listOf("app_version" to appVersion, "platform" to "android", "trigger" to if (versionUpgrade) "version_upgrade" else "app_launch")
        return JsonAccess.array(http.data(Method.GET, "v1/announcements/pending", query = query)).mapNotNull { (it as? JsonObject)?.let(AnnouncementMapper::map) }
    }

    override suspend fun dismissAnnouncement(id: String, buttonTapped: Boolean) {
        http.data(Method.POST, "v1/announcements/$id/dismiss", body = Body.Json(buildJsonObject { put("cta_clicked", buttonTapped) }.toString()))
    }
}

internal object AnnouncementMapper {
    fun map(json: JsonObject): Announcement? {
        val id = json.string("id") ?: return null
        val content = json.obj("content") ?: return null
        val title = content.string("title").orEmpty()
        fun changes(key: String) = content.objects(key).mapNotNull { item ->
            val heading = item.string("title") ?: return@mapNotNull null
            Announcement.Change(item.string("icon"), heading, item.string("description").orEmpty(), item.string("image_url"))
        }
        return when (json.string("type")) {
            "changelog" -> Announcement(id, title, Announcement.Kind.Changelog(json.string("app_version"), changes("changes")))
            "feature" -> Announcement(id, title, Announcement.Kind.Feature(changes("steps")))
            "announcement" -> {
                val button = content.obj("cta")
                Announcement(
                    id, title,
                    Announcement.Kind.Message(content.string("body").orEmpty(), content.string("image_url"), button?.string("text"), button?.string("action")?.let(::link)),
                )
            }
            else -> null
        }
    }

    /** `url:https://...` or a bare https link opens in the browser; `navigate:/route` becomes `omi://route`. */
    fun link(action: String): String? = when {
        action.startsWith("url:") -> web(action.removePrefix("url:"))
        action.startsWith("navigate:") -> "omi:/" + action.removePrefix("navigate:")
        action.startsWith("/") -> "omi:/$action"
        else -> web(action)
    }

    private fun web(url: String): String? = url.takeIf { it.lowercase().startsWith("http://") || it.lowercase().startsWith("https://") }
}
