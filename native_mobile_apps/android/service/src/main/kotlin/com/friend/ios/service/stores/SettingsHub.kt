package com.friend.ios.service.stores

import com.friend.ios.core.models.Subscription
import kotlin.math.roundToInt

/**
 * Port of `SettingsHub.swift`: the plain facts behind the top of Settings (the profile header and
 * its four tiles) and the status line on My Omi, kept free of views so they can be tested.
 */
object SettingsHub {
    /** What the Omi is doing, for the Settings tile, My Omi's status line and its dot. */
    sealed interface OmiState {
        /** No Omi was ever paired. */
        data object None : OmiState
        data object NotConnected : OmiState
        data object Connecting : OmiState
        /** Connected and sending audio (`listening`), connected but paused, or connected and idle. */
        data class Connected(override val battery: Int?, val activity: Activity) : OmiState

        enum class Activity { Idle, Listening, Paused }

        /** The dot beside the pendant: red while listening, green while connected, gray otherwise. */
        enum class Dot { Live, Connected, Off }

        val dot: Dot
            get() = when (this) {
                is Connected -> if (activity == Activity.Listening) Dot.Live else Dot.Connected
                else -> Dot.Off
            }

        val isConnected: Boolean get() = this is Connected

        val battery: Int? get() = null
    }

    fun omiState(isPaired: Boolean, connection: DeviceStore.Connection, battery: Int?, isMuted: Boolean, isListening: Boolean): OmiState {
        if (!isPaired) return OmiState.None
        return when (connection) {
            DeviceStore.Connection.Disconnected -> OmiState.NotConnected
            DeviceStore.Connection.Connecting -> OmiState.Connecting
            DeviceStore.Connection.Connected -> OmiState.Connected(
                battery,
                if (isMuted) OmiState.Activity.Paused else if (isListening) OmiState.Activity.Listening else OmiState.Activity.Idle,
            )
        }
    }

    /**
     * One or two letters for the avatar: the name's initials ("Ada Lovelace" -> "LS"); without a
     * name the email's first letter ("ada@..." -> "A"); "?" only when neither is known.
     */
    fun initials(name: String?, email: String?): String {
        val trimmed = name?.trim().orEmpty()
        if (trimmed.isNotEmpty()) {
            val words = trimmed.split(' ', '-', '.', '@').filter { it.isNotEmpty() }.take(2)
            val letters = words.map { it.first() }.filter { it.isLetter() }.joinToString("") { it.uppercase() }
            if (letters.isNotEmpty()) return letters
        }
        email?.trim()?.firstOrNull { it.isLetter() }?.let { return it.uppercase() }
        return "?"
    }

    /** The name shown on top of Settings: the account's name, else the part of the email before the "@". */
    fun headline(name: String?, email: String?): String? {
        name?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
        return email?.split("@")?.firstOrNull()?.takeIf { it.isNotEmpty() }
    }

    /** The limit closest to running out (the Plan tile's meter); null when every meter is unlimited. */
    fun busiestMeter(meters: List<UsageMeter>): UsageMeter? = meters.filter { it.fraction != null }.maxByOrNull { it.fraction ?: 0.0 }

    /** Whole percent of a 0...1 share, rounded down below 100 so "100%" means the limit is reached. */
    fun percent(fraction: Double): Int {
        val value = (fraction.coerceIn(0.0, 1.0) * 100).roundToInt()
        return if (fraction < 1) minOf(99, value) else 100
    }

    /** The free plan: the header offers Upgrade. */
    fun isFree(subscription: Subscription): Boolean = !subscription.isPaid

    /**
     * Connected apps for the Apps tile: calendar, mail and task apps, plus Health and Reminders when
     * they are on (the "Connected" group of Apps & integrations).
     */
    fun connectedApps(connectedIntegrations: Int, health: Boolean, reminders: Boolean): Int =
        connectedIntegrations + (if (health) 1 else 0) + (if (reminders) 1 else 0)
}
