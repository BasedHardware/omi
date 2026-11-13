package com.friend.ios.features.today

import android.content.SharedPreferences
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.features.components.DecisionCard
import com.friend.ios.features.components.rememberConnectIntegration
import com.friend.ios.features.settings.HEALTH_CONNECT
import com.friend.ios.features.settings.capabilityFailureMessage
import com.friend.ios.features.settings.capabilityName
import com.friend.ios.service.LocalAppleHealthStore
import com.friend.ios.service.LocalCapabilitiesStore
import com.friend.ios.service.stores.AppleHealthStore
import com.friend.ios.service.stores.CapabilitiesStore
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import java.time.Instant

/**
 * Port of `ConnectSuggestion.swift`: Home's "Connect Google Calendar?" card, the connections that
 * make Omi useful (calendar, mail, Health Connect where iOS has Apple Health), one at a time while
 * the account is new or nothing is connected yet. "Connect" signs in right here; "Not now" hides
 * that one for good (Settings > Apps & integrations still has it). Health Connect is offered only
 * on phones that have it (Settings hides its row there too).
 */
object ConnectSuggestion {
    /** Most useful first. */
    val order = listOf("google_calendar", "gmail", AppleHealthStore.KEY)
    /** Days after the first Home visit in which the card is offered while something is connected. */
    const val newAccountDays = 14L
    /** `@AppStorage("omi.connectDismissed")`, comma separated. */
    const val dismissedKey = "omi.connectDismissed"
    /** `@AppStorage("omi.firstHomeAt")`, epoch seconds (stored as a string on Android). */
    const val firstHomeKey = "omi.firstHomeAt"

    /** What to suggest now: unconnected, not dismissed, and only early on (or while nothing at all is connected). */
    fun ids(connected: Set<String>, dismissed: Set<String>, firstSeen: Instant?, now: Instant = Instant.now()): List<String> {
        val isNew = firstSeen?.let { now.epochSecond - it.epochSecond < newAccountDays * 86_400 } ?: true
        if (!isNew && connected.isNotEmpty()) return emptyList()
        return order.filter { it !in connected && it !in dismissed }
    }

    /** `ids(connected:...)` from the stores and Home's stored state. */
    fun ids(capabilities: CapabilitiesStore, health: AppleHealthStore, dismissed: String, firstHomeAt: Long): List<String> = ids(
        connected = capabilities.integrations.filter { it.isConnected }.map { it.id }.toSet() + listOfNotNull(AppleHealthStore.KEY.takeIf { health.isConnected }),
        dismissed = dismissed.split(",").filter { it.isNotEmpty() }.toSet() + listOfNotNull(AppleHealthStore.KEY.takeIf { !health.isAvailable }),
        firstSeen = if (firstHomeAt == 0L) null else Instant.ofEpochSecond(firstHomeAt),
    )

    /** Notes the first Home visit (returns it). */
    fun firstHomeAt(defaults: SharedPreferences): Long {
        val stored = defaults.getLong(firstHomeKey, 0L)
        if (stored != 0L) return stored
        val now = Instant.now().epochSecond
        defaults.edit().putLong(firstHomeKey, now).apply()
        return now
    }

    /** Refreshes what is connected. */
    suspend fun prepare(capabilities: CapabilitiesStore, health: AppleHealthStore) {
        coroutineScope {
            launch { capabilities.load() }
            launch { health.load() }
        }
    }

    fun name(id: String): String = if (id == AppleHealthStore.KEY) HEALTH_CONNECT else capabilityName(id)

    @Composable
    fun purpose(id: String): String = when (id) {
        AppleHealthStore.KEY -> L("nativeCapabilityHealth")
        "google_calendar" -> L("nativeCapabilityCalendar")
        "gmail" -> L("nativeCapabilityMail")
        else -> L("nativeCapabilityTasks")
    }
}

/** Port of `ConnectSuggestionCard`: kicker, the question, why it helps (or why connecting did not work), and Connect / Not now. */
@Composable
internal fun ConnectSuggestionCard(id: String, onDismiss: () -> Unit) {
    val capabilities = LocalCapabilitiesStore.current
    val health = LocalAppleHealthStore.current
    val scope = rememberCoroutineScope()
    val connectIntegration = rememberConnectIntegration()
    val isConnecting = if (id == AppleHealthStore.KEY) health.phase == AppleHealthStore.Phase.Connecting else capabilities.connecting == id
    val failure = capabilities.failures[id]
    val subtitle = if (id != AppleHealthStore.KEY && failure != null && !isConnecting) {
        capabilityFailureMessage(failure, ConnectSuggestion.name(id))
    } else {
        ConnectSuggestion.purpose(id)
    }

    fun connect() {
        if (id == AppleHealthStore.KEY) {
            scope.launch { health.connect() }
        } else {
            capabilities.integrations.firstOrNull { it.id == id }?.let(connectIntegration)
        }
    }

    DecisionCard(
        kicker = DecisionCard.Kicker("link", L("nativeForYouConnect"), DS.Palette.agent),
        title = L("nativeForYouConnectTitle", ConnectSuggestion.name(id)),
        subtitle = subtitle,
        pulses = isConnecting,
        pills = listOf(
            DecisionCard.Pill(L("nativeConnect"), isPrimary = true) { connect() },
            DecisionCard.Pill(L("notNow"), action = onDismiss),
        ),
        // The card itself connects too (no dead tap).
        onTap = { connect() },
    )
}
