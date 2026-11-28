package com.friend.ios.features.agent

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.isTraversalGroup
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiHairline
import com.friend.ios.design.SFImage
import com.friend.ios.design.medium
import com.friend.ios.design.plainButton
import com.friend.ios.design.semibold
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.RunFailure
import kotlinx.coroutines.delay
import java.time.Duration
import java.time.Instant

/**
 * Port of `RunningStrip` (`ChatRunning.swift`). "Running now", pinned under the chat tab's header:
 * every hand-over Omi is working on, with what it is doing right now and for how long, so the
 * state never scrolls away in the thread. Tap opens the run, "Stop" ends it. Not there while
 * nothing runs.
 */
@Composable
fun RunningStrip(onOpen: (AgentStore.Run) -> Unit, modifier: Modifier = Modifier) {
    val agent = LocalAgentStore.current
    val runs = agent.activeRuns
    if (runs.isEmpty()) return
    val shape = ContinuousRoundedShape(DS.Radius.card)
    val label = L("nativeChatRunningNow")
    Column(
        modifier
            .fillMaxWidth()
            .background(DS.Palette.cardRaised, shape)
            .border(1.dp, DS.Palette.cardStroke, shape)
            .semantics {
                isTraversalGroup = true
                contentDescription = label
            },
    ) {
        runs.forEachIndexed { index, run ->
            if (index > 0) OmiHairline(leading = DS.Spacing.lg + 22.dp)
            RunningRow(run, onOpen = { onOpen(run) }, onStop = { agent.stop(run.id) })
        }
    }
}

@Composable
private fun RunningRow(run: AgentStore.Run, onOpen: () -> Unit, onStop: () -> Unit) {
    val agent = LocalAgentStore.current
    val asks = run.id in agent.deviceToolRequests
    val pulse by rememberInfiniteTransition(label = "pulse").animateFloat(1f, 0.35f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "pulse")
    var now by remember { mutableStateOf(Instant.now()) }
    LaunchedEffect(run.id) {
        while (true) {
            delay(1_000)
            now = Instant.now()
        }
    }
    Row(
        Modifier.padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm + 2.dp),
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        HStack(Modifier.weight(1f).plainButton(onClick = onOpen).accessibilityHint(L("nativeChatRunOpenHint")), spacing = DS.Spacing.md) {
            SFImage(
                if (asks) "questionmark.bubble" else "sparkles", size = 14.sp, weight = FontWeight.SemiBold, tint = DS.Palette.agent,
                modifier = Modifier.width(22.dp).alpha(if (asks) 1f else pulse),
            )
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(run.taskTitle, style = DS.Typography.callout.medium(), color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                HStack(spacing = DS.Spacing.xs) {
                    Text(detail(run, asks), style = DS.Typography.caption, color = DS.Palette.inkSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    Text("·", style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                    Text(elapsed(run.startedAt, now), style = DS.Typography.caption.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkSecondary)
                }
            }
        }
        Text(
            L("nativeChatRunStop"),
            style = DS.Typography.caption.semibold(),
            color = DS.Palette.ink,
            modifier = Modifier
                .plainButton(onClick = onStop)
                .heightIn(min = 32.dp)
                .border(1.dp, DS.Palette.hairline, CircleShape)
                .padding(horizontal = DS.Spacing.md, vertical = 7.dp),
        )
    }
}

/** What Omi is doing, in plain words; a question waiting comes first. */
@Composable
private fun detail(run: AgentStore.Run, asks: Boolean): String {
    if (asks) return L("nativeChatRunWaitsForYou")
    (run.state as? AgentStore.RunState.Working)?.let { working -> AgentWording.step(working.step)?.let { return it } }
    run.steps.lastOrNull { AgentWording.step(it) != null }?.let { AgentWording.step(it) }?.let { return it }
    return L("nativeChatRunStarting")
}

/** "0:42", "12:05", "1:02:10". */
fun elapsed(start: Instant, now: Instant): String {
    val seconds = maxOf(0L, Duration.between(start, now).seconds)
    val hours = seconds / 3600
    val minutes = seconds / 60 % 60
    val rest = seconds % 60
    return if (hours > 0) "%d:%02d:%02d".format(hours, minutes, rest) else "%d:%02d".format(minutes, rest)
}

/**
 * A finished hand-over in the thread, where it ended: "Done: <its first line>" (or why it
 * stopped). Tap opens the result.
 */
@Composable
fun RunOutcomeRow(run: AgentStore.Run, onOpen: () -> Unit, modifier: Modifier = Modifier) {
    val shape = ContinuousRoundedShape(DS.Radius.bubble)
    val line = when (val state = run.state) {
        is AgentStore.RunState.Done -> L("nativeChatRunDone", firstLine(state.result))
        is AgentStore.RunState.Failed -> AgentWording.failure(state.code)
        else -> ""
    }
    // In Omi's column, in the bubbles' family: their radius and fill, as wide as one.
    Row(
        modifier
            .bubbleWide()
            .plainButton(onClick = onOpen)
            .background(DS.Palette.card, shape)
            .padding(horizontal = 14.dp, vertical = DS.Spacing.sm + 1.dp),
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        SFImage(
            if (run.failure == null) "checkmark.circle.fill" else "pause.circle", size = 13.sp, weight = FontWeight.SemiBold,
            tint = if (run.failure == null) DS.Palette.success else DS.Palette.inkTertiary, modifier = Modifier.padding(top = 2.dp),
        )
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(run.taskTitle, style = DS.Typography.caption, color = DS.Palette.inkTertiary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(line, style = DS.Typography.callout, color = DS.Palette.ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        SFImage("chevron.right", size = 12.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkTertiary, modifier = Modifier.align(Alignment.CenterVertically))
    }
}

/** The result's first real line, without Markdown marks. */
fun firstLine(text: String): String {
    val line = text.lines().map { it.trim() }.firstOrNull { it.isNotEmpty() && !it.all { c -> c in "#-*_>" } } ?: ""
    return line.trim { it in "#*_> -" }.replace("**", "")
}

/**
 * The part of `AgentWording` (`OmiComponents/AgentWording.swift`) the chat page needs: user-facing
 * words for agent states whose stored text is a fixed English marker.
 */
internal object AgentWording {
    /**
     * Why a run stopped, in plain words: the state carries a [RunFailure] code (older runs the bare
     * English marker); free text from elsewhere stays as it is.
     */
    @Composable
    fun failure(message: String): String {
        val failure = RunFailure.from(message) ?: RunFailure.fromEvent(message) ?: return message
        return words(failure)
    }

    /**
     * The button that deals with it: resume a stopped run, try again otherwise; null when trying
     * again cannot help (a used-up plan, a refusal).
     */
    @Composable
    fun action(failure: RunFailure): String? {
        if (!failure.canRetry) return null
        return if (failure == RunFailure.Stopped) L("nativeRunResume") else L("tryAgain")
    }

    @Composable
    fun words(failure: RunFailure): String {
        return when (failure) {
            RunFailure.QuotaExceeded -> L("nativeRunFailedQuota")
            RunFailure.Timeout -> L("nativeRunFailedTimeout")
            RunFailure.ToolLoop -> L("nativeRunFailedStuck")
            RunFailure.ServerError -> L("nativeRunFailedServer")
            RunFailure.Offline -> L("nativeRunFailedOffline")
            RunFailure.Stopped -> L("nativeRunFailedStopped")
            RunFailure.NoAnswer -> L("nativeRunFailedNoAnswer")
            RunFailure.Refused -> L("nativeRunFailedRefused")
            RunFailure.NotConnected -> L("nativeRunFailedNotConnected")
            RunFailure.CouldNotFinish -> L("nativeOmiCouldNotFinish")
        }
    }

    /**
     * A run's current step as a person reads it, or null when it says nothing (a heartbeat, a
     * marker, machine text). Trailing dots go ("Searching the web…" becomes "Searching the web").
     */
    fun step(line: String): String? {
        if (isBoilerplate(line)) return null
        return line.trim().trimEnd('.', '…').ifEmpty { null }
    }

    private val boilerplate = setOf(AgentStore.FAILED_SUMMARY, "Omi started working on this task.", "Work initiated by the user")
    private val machinePrefixes = listOf("calling ", "tool:", "tool call", "running tool", "work initiated", "started")

    private fun isBoilerplate(raw: String): Boolean {
        val line = raw.trim()
        if (line.isEmpty() || line in boilerplate || AgentStore.isHeartbeat(line) || RunFailure.fromEvent(line) != null) return true
        val words = line.split(Regex("\\s+"))
        if (words.size < 2) return true
        if (words.any { it.contains("_") || it.contains("()") }) return true
        val lowered = line.lowercase()
        return machinePrefixes.any { lowered.startsWith(it) }
    }
}
