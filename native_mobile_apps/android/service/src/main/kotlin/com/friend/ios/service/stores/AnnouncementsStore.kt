package com.friend.ios.service.stores

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.models.Announcement
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.persistence.Preferences

/**
 * Port of `AnnouncementsStore.swift`: what's new (Flutter `announcement_service`, `changelog_sheet`,
 * `feature_screen`, `announcement_dialog`). After an update the changes since the last version show
 * once; pending feature tours and messages follow, one at a time. Settings > What's new reads [recent].
 */
class AnnouncementsStore(private val api: APIClientProtocol, private val preferences: Preferences? = null) {
    /** What is on screen now; the rest waits in line. */
    var current: Announcement? by mutableStateOf(null)
        private set
    /** Settings > What's new: the latest versions. */
    var recent: List<Announcement> by mutableStateOf(emptyList())
        private set
    var recentFailed: Boolean by mutableStateOf(false)
        private set

    private val queue = ArrayDeque<Announcement>()
    private var checked = false

    /**
     * Once per launch. [appVersion] is `X.Y.Z+build`. A fresh install shows nothing (there is no
     * "before"); an update shows the changes in between, then anything pending. The last version
     * lives under Flutter's key, so a Flutter to native update sees the version it ran before.
     */
    suspend fun checkAfterLaunch(appVersion: String) {
        if (checked) return
        checked = true
        val last = preferences?.string(Preferences.Key.LastKnownAppVersion)
        if (last != appVersion) preferences?.set(Preferences.Key.LastKnownAppVersion, appVersion)
        if (last.isNullOrEmpty()) return
        val upgraded = last != appVersion
        if (upgraded) {
            val changes = runCatching { api.changelogs(last, appVersion, 5) }.getOrNull().orEmpty()
            if (changes.isNotEmpty()) enqueue(changes)
        }
        val pending = runCatching { api.pendingAnnouncements(appVersion, upgraded) }.getOrNull().orEmpty()
        pending.filter { it.kind !is Announcement.Kind.Changelog }.forEach { enqueue(listOf(it)) }
    }

    suspend fun loadRecent() {
        try {
            recent = api.changelogs(null, null, 5)
            recentFailed = false
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            recentFailed = true
        }
    }

    /** Answered (button, close, "Got it"): the backend stops offering it. Changelogs are not tracked. */
    suspend fun dismiss(buttonTapped: Boolean = false) {
        val item = current ?: return
        advance()
        if (item.kind is Announcement.Kind.Changelog) return
        runCatching { api.dismissAnnouncement(item.id, buttonTapped) }
    }

    /** "Not now": it comes back on the next launch. */
    fun later() {
        advance()
    }

    private fun enqueue(items: List<Announcement>) {
        queue.addAll(items)
        if (current == null) advance()
    }

    private fun advance() {
        current = queue.removeFirstOrNull()
    }
}
