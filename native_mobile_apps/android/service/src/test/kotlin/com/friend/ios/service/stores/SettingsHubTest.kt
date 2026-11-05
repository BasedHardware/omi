package com.friend.ios.service.stores

import com.friend.ios.core.models.Subscription
import com.friend.ios.service.stores.DeviceStore.Connection
import com.friend.ios.service.stores.SettingsHub.OmiState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Port of `SettingsHubTests.swift`: the top of Settings (profile header, the four tiles). */
class SettingsHubTest {
    @Test
    fun initialsComeFromTheNameThenTheEmail() {
        assertEquals("AL", SettingsHub.initials("Ada Lovelace", "ada@example.com"))
        assertEquals("A", SettingsHub.initials("  ada  ", null))
        assertEquals("JL", SettingsHub.initials("Jean-Luc Picard", null))
        // No name: the email's first letter, never a placeholder word's.
        assertEquals("A", SettingsHub.initials(null, "ada@example.com"))
        assertEquals("A", SettingsHub.initials("", "1ada@example.com"))
        assertEquals("?", SettingsHub.initials(null, null))
    }

    @Test
    fun headlineFallsBackToTheEmailsName() {
        assertEquals("Ada Lovelace", SettingsHub.headline("Ada Lovelace", "x@y.z"))
        assertEquals("ada", SettingsHub.headline(" ", "ada@example.com"))
        assertNull(SettingsHub.headline(null, null))
    }

    @Test
    fun omiStateFollowsTheConnection() {
        assertEquals(OmiState.None, SettingsHub.omiState(false, Connection.Connected, 50, false, true))
        val away = SettingsHub.omiState(true, Connection.Disconnected, 50, false, false)
        assertEquals(OmiState.NotConnected, away)
        assertEquals(OmiState.Dot.Off, away.dot)
        assertNull(away.battery)
        val live = SettingsHub.omiState(true, Connection.Connected, 76, false, true)
        assertEquals(OmiState.Connected(76, OmiState.Activity.Listening), live)
        assertEquals(OmiState.Dot.Live, live.dot)
        assertEquals(76, live.battery)
        // Paused wins over listening: the Omi sends nothing.
        val paused = SettingsHub.omiState(true, Connection.Connected, 76, true, true)
        assertEquals(OmiState.Connected(76, OmiState.Activity.Paused), paused)
        assertEquals(OmiState.Dot.Connected, paused.dot)
        assertEquals(OmiState.Connecting, SettingsHub.omiState(true, Connection.Connecting, null, false, false))
        assertTrue(live.isConnected)
        assertFalse(away.isConnected)
    }

    @Test
    fun busiestMeterSkipsUnlimited() {
        val meters = listOf(
            UsageMeter(UsageMeter.Kind.Listening, 100.0, 1000.0),
            UsageMeter(UsageMeter.Kind.Chat, 31.0, 50.0),
            UsageMeter(UsageMeter.Kind.Words, 9999.0, null),
        )
        assertEquals(UsageMeter.Kind.Chat, SettingsHub.busiestMeter(meters)?.kind)
        assertNull(SettingsHub.busiestMeter(listOf(UsageMeter(UsageMeter.Kind.Listening, 5.0, null))))
        assertEquals(62, SettingsHub.percent(0.62))
        // Nearly full is not full: 100 % only at the limit.
        assertEquals(99, SettingsHub.percent(0.997))
        assertEquals(100, SettingsHub.percent(1.0))
        assertEquals(0, SettingsHub.percent(0.0))
    }

    @Test
    fun connectedAppsCountHealthAndReminders() {
        assertEquals(2, SettingsHub.connectedApps(2, health = false, reminders = false))
        assertEquals(4, SettingsHub.connectedApps(2, health = true, reminders = true))
        assertEquals(0, SettingsHub.connectedApps(0, health = false, reminders = false))
    }

    @Test
    fun freePlanOffersUpgrade() {
        val free = Subscription("basic", "active", false, emptyList(), 0, 0, null, true, emptyList())
        assertTrue(SettingsHub.isFree(free))
        assertFalse(SettingsHub.isFree(free.copy(plan = "unlimited")))
        // A paid plan that is not active reads as free.
        assertTrue(SettingsHub.isFree(free.copy(plan = "unlimited", status = "canceled")))
    }
}
