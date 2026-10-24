package com.friend.ios.service.stores

import com.friend.ios.core.models.Announcement
import com.friend.ios.persistence.Preferences
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Port of `AnnouncementsStoreTests.swift`: what's new after an update, one at a time. */
class AnnouncementsStoreTest {
    private val changelog = Announcement("c1", "1.1", Announcement.Kind.Changelog("1.1", listOf(Announcement.Change("✨", "New", "Text"))))
    private val message = Announcement("m1", "Hello", Announcement.Kind.Message("Body", null, null, null))
    private val pendingChangelog = Announcement("c2", "1.1", Announcement.Kind.Changelog("1.1", emptyList()))

    @Test fun freshInstallShowsNothingAndRemembersTheVersion() = runTest {
        val api = fakeAPI()
        val preferences = freshPreferences()
        val store = AnnouncementsStore(api.client, preferences)
        store.checkAfterLaunch("1.1.0+5")
        assertNull(store.current)
        assertTrue(api.calls.isEmpty())
        assertEquals("1.1.0+5", preferences.string(Preferences.Key.LastKnownAppVersion))
    }

    @Test fun updateShowsChangesThenPendingMessagesOnce() = runTest {
        val api = fakeAPI {
            "changelogs" returns listOf(changelog)
            "pendingAnnouncements" returns listOf(pendingChangelog, message)
            "dismissAnnouncement" returns Unit
        }
        val preferences = freshPreferences().apply { set(Preferences.Key.LastKnownAppVersion, "1.0.0+1") }
        val store = AnnouncementsStore(api.client, preferences)
        store.checkAfterLaunch("1.1.0+5")
        store.checkAfterLaunch("1.1.0+5")
        assertEquals(listOf(listOf("1.0.0+1", "1.1.0+5", 5)), api.called("changelogs"))
        assertEquals(listOf(listOf("1.1.0+5", true)), api.called("pendingAnnouncements"))
        assertEquals(changelog, store.current)
        // Changelogs are not tracked by the backend.
        store.dismiss()
        assertEquals(message, store.current)
        assertTrue(api.called("dismissAnnouncement").isEmpty())
        store.dismiss(buttonTapped = true)
        assertNull(store.current)
        assertEquals(listOf(listOf("m1", true)), api.called("dismissAnnouncement"))
    }

    @Test fun sameVersionOnlyAsksForPending() = runTest {
        val api = fakeAPI { "pendingAnnouncements" returns listOf(message) }
        val preferences = freshPreferences().apply { set(Preferences.Key.LastKnownAppVersion, "1.1.0+5") }
        val store = AnnouncementsStore(api.client, preferences)
        store.checkAfterLaunch("1.1.0+5")
        assertTrue(api.called("changelogs").isEmpty())
        assertEquals(listOf(listOf("1.1.0+5", false)), api.called("pendingAnnouncements"))
        assertEquals(message, store.current)
        store.later()
        assertNull(store.current)
    }
}
