package com.friend.ios.features.agent

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ChatCitation
import com.friend.ios.core.models.ChatMessage
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.Formatted
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.DecisionCard
import com.friend.ios.features.settings.HEALTH_CONNECT
import com.friend.ios.features.settings.capabilityFailureMessage
import com.friend.ios.features.settings.capabilityName
import com.friend.ios.service.LocalAppleHealthStore
import com.friend.ios.service.LocalCapabilitiesStore
import com.friend.ios.service.LocalChatStore
import com.friend.ios.service.stores.AppleHealthStore
import com.friend.ios.service.stores.CapabilitiesStore
import com.friend.ios.service.stores.ChatStacking
import com.friend.ios.service.stores.kind
import com.friend.ios.service.stores.ChatCard
import com.friend.ios.service.stores.answerDeviceTool
import kotlinx.coroutines.launch
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.util.Locale

/**
 * Port of `AnswerCards` (`ChatCards.swift`). The cards under one answer, drawn by the app from
 * what the turn did (never from the answer's own text markup): Omi's open question, a missing
 * connection, tasks Omi added or ticked off. Cards of one kind in a row stack into "2 more".
 */
@Composable
fun AnswerCards(message: ChatMessage, modifier: Modifier = Modifier) {
    val chat = LocalChatStore.current
    val capabilities = LocalCapabilitiesStore.current
    val health = LocalAppleHealthStore.current
    val scope = rememberCoroutineScope()
    val uri = LocalUriHandler.current
    val cards = chat.cards(message.id).filter { isRelevant(it, capabilities, health) }
    val pending = chat.pendingDeviceTool?.takeIf { chat.pendingDeviceToolMessageID == message.id }
    if (pending == null && cards.isEmpty()) return
    // As wide as Omi's bubbles, not the whole row.
    Column(modifier.bubbleWide(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs + 2.dp)) {
        if (pending != null) {
            com.friend.ios.features.components.OmiAsksCard(pending, onAnswer = { choice -> chat.answerDeviceTool(choice) })
        }
        // Never two cards of one kind in a row: the first, and "2 more".
        for (stack in ChatStacking.stacks(cards) { it.kind }) {
            ChatCardStack(stack, stackKey = "${message.id}|${stack.first().id}") { card ->
                when (card) {
                    is ChatCard.Connect -> ConnectCard(card.integration, onDismiss = { chat.dismiss(card, message.id) })
                    is ChatCard.TaskAdded, is ChatCard.TaskCompleted -> TaskChangeCard(
                        card,
                        onOpen = { uri.openUri("omi://task/${if (card is ChatCard.TaskAdded) card.taskID else (card as ChatCard.TaskCompleted).taskID}") },
                        onUndo = { scope.launch { chat.undo(card, message.id) } },
                    )
                }
            }
        }
    }
}

/** A connect card only while that connection is still missing. */
private fun isRelevant(card: ChatCard, capabilities: CapabilitiesStore, health: AppleHealthStore): Boolean {
    if (card !is ChatCard.Connect) return true
    if (card.integration == AppleHealthStore.KEY) return !health.isConnected && health.isAvailable
    val integration = capabilities.integrations.firstOrNull { it.id == card.integration } ?: return false
    return !integration.isConnected
}

/**
 * Port of `ConnectCard`. "Connect Google Calendar": the answer failed on a missing connection;
 * connecting happens right here (the same sign-in as Settings and Home). The login opens in the
 * browser, as Home's card does; back in the app the connections are read again.
 */
@Composable
internal fun ConnectCard(id: String, onDismiss: () -> Unit, modifier: Modifier = Modifier) {
    val capabilities = LocalCapabilitiesStore.current
    val health = LocalAppleHealthStore.current
    val uriHandler = LocalUriHandler.current
    val scope = rememberCoroutineScope()
    var awaitingLogin by remember { mutableStateOf(false) }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME && awaitingLogin) {
                awaitingLogin = false
                scope.launch { capabilities.load() }
            }
        }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    val isHealth = id == AppleHealthStore.KEY
    // Apple Health is Health Connect on Android.
    val name = if (isHealth) HEALTH_CONNECT else capabilityName(id)
    val isConnecting = if (isHealth) health.phase == AppleHealthStore.Phase.Connecting else capabilities.connecting == id
    val failure = if (isHealth) null else capabilities.failures[id]
    val subtitle = when {
        failure != null && !isConnecting -> capabilityFailureMessage(failure, name)
        isHealth -> L("nativeCapabilityHealth")
        else -> L(capabilityPurposeKey(id))
    }

    fun connect() {
        scope.launch {
            if (isHealth) {
                health.connect()
                return@launch
            }
            val integration = capabilities.integrations.firstOrNull { it.id == id } ?: return@launch
            val url = capabilities.authorizationURL(integration) ?: return@launch
            awaitingLogin = true
            runCatching { uriHandler.openUri(url) }.onFailure { capabilities.loginEnded(integration, cancelled = false) }
        }
    }

    DecisionCard(
        kicker = DecisionCard.Kicker("link", L("nativeChatConnectKicker"), DS.Palette.agent),
        title = L("nativeChatConnectTitle", name),
        subtitle = subtitle,
        pulses = isConnecting,
        pills = listOf(
            DecisionCard.Pill(L("nativeConnect"), isPrimary = true) { connect() },
            DecisionCard.Pill(L("notNow"), action = onDismiss),
        ),
        compact = true,
        onTap = { connect() },
        modifier = modifier.testTag("chat.connect.$id"),
    )
}

/** `CapabilitiesList.purposeKey`: why a connection helps. */
private fun capabilityPurposeKey(id: String): String = when (id) {
    "google_calendar" -> "nativeCapabilityCalendar"
    "gmail" -> "nativeCapabilityMail"
    else -> "nativeCapabilityTasks"
}

/** "Added task: …" / "Marked done: …": a tap opens the task, Undo takes it back. */
@Composable
fun TaskChangeCard(card: ChatCard, onOpen: () -> Unit, onUndo: () -> Unit, modifier: Modifier = Modifier) {
    val isDone = card is ChatCard.TaskCompleted
    val title = when (card) {
        is ChatCard.TaskAdded -> card.title
        is ChatCard.TaskCompleted -> card.title
        is ChatCard.Connect -> ""
    }
    Row(
        modifier
            .fillMaxWidth()
            .background(DS.Palette.card, ContinuousRoundedShape(DS.Radius.bubble))
            .padding(horizontal = 14.dp, vertical = DS.Spacing.sm + 1.dp),
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        HStack(Modifier.weight(1f).plainButton(onClick = onOpen).semantics(mergeDescendants = true) {}, spacing = DS.Spacing.md) {
            SFImage(if (isDone) "checkmark.circle.fill" else "plus.circle", size = 16.sp, tint = if (isDone) DS.Palette.success else DS.Palette.agent)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
                Text(if (isDone) L("nativeChatTaskMarkedDone") else L("nativeChatTaskAdded"), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
                Text(title, style = DS.Typography.callout, color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        Text(L("undo"), style = DS.Typography.caption.semibold(), color = DS.Palette.agent, modifier = Modifier.plainButton(onClick = onUndo))
    }
}

/** The conversations an answer drew on, as chips "Q4 roadmap · 14:05"; a tap opens that one. */
@Composable
fun CitationChips(citations: List<ChatCitation>, onOpen: ((String) -> Unit)?, modifier: Modifier = Modifier) {
    val haptics = rememberHaptics()
    val untitled = L("untitledConversation")
    Row(modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        for (citation in citations) {
            HStack(
                Modifier
                    .plainButton(enabled = onOpen != null) {
                        haptics.selection()
                        onOpen?.invoke(citation.conversationID)
                    }
                    .background(DS.Palette.fill, CircleShape)
                    .padding(horizontal = DS.Spacing.sm + 2.dp, vertical = DS.Spacing.xs + 1.dp),
                spacing = DS.Spacing.xs,
            ) {
                val emoji = citation.emoji
                if (!emoji.isNullOrEmpty()) {
                    Text(emoji, style = DS.Typography.caption)
                } else {
                    SFImage("bubble.left", size = 10.sp, tint = DS.Palette.ink)
                }
                Text(CitationLabel.label(citation, untitled), style = DS.Typography.caption, color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

object CitationLabel {
    /** "Q4 roadmap · 14:05"; an older one carries its day ("Q4 roadmap · Tue 14:05"). */
    fun label(citation: ChatCitation, untitled: String, now: Instant = Instant.now(), zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): String {
        val title = citation.title.ifEmpty { untitled }
        val time = citation.time ?: return title
        val text = when {
            time.atZone(zone).toLocalDate() == now.atZone(zone).toLocalDate() -> Formatted.shortTime(time, locale, zone)
            Duration.between(time, now).seconds < 6 * 86400 -> MessageTime.skeleton("EEEjmm", locale).format(time.atZone(zone))
            else -> MessageTime.skeleton("dMMM", locale).format(time.atZone(zone))
        }
        return "$title · $text"
    }
}
