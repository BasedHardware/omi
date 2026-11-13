package com.friend.ios.features.components

import android.text.format.DateUtils
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Workstream
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.pressable
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.RunFailure
import java.time.Duration
import java.time.Instant

/** Port of `AgentWording.swift`: user-facing words for agent states whose stored text is a fixed English marker. */
object AgentWording {
    /**
     * Why a run stopped, in plain words: the state carries a [RunFailure] code (older runs the bare
     * English marker); free text from elsewhere stays as it is.
     */
    @Composable
    fun failure(message: String): String {
        val failure = RunFailure.from(message) ?: RunFailure.fromEvent(message) ?: return message
        return words(failure)
    }

    @Composable
    fun words(failure: RunFailure): String = when (failure) {
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

    /**
     * The button that deals with it: resume a stopped run, try again otherwise; null when trying
     * again cannot help (a used-up plan, a refusal).
     */
    @Composable
    fun action(failure: RunFailure): String? {
        if (!failure.canRetry) return null
        return if (failure == RunFailure.Stopped) L("nativeRunResume") else L("tryAgain")
    }

    /**
     * A run's current step as a person reads it, or null when it says nothing (a heartbeat, a
     * marker, machine text). Trailing dots go ("Searching the web…" becomes "Searching the web").
     */
    fun step(line: String): String? {
        if (isBoilerplate(line)) return null
        return line.trim().trimEnd('.', '…').ifEmpty { null }
    }

    /**
     * Lines that mean nothing to a person: the app's start and failure markers, the backend's
     * opening event, and machine text (tool names, ids, "started"): one word, snake_case,
     * "Calling search_web".
     */
    fun isBoilerplate(raw: String): Boolean {
        val line = raw.trim()
        if (line.isEmpty() || line in boilerplate || AgentStore.isHeartbeat(line) || RunFailure.fromEvent(line) != null) return true
        val words = line.split(Regex("\\s+"))
        if (words.size < 2) return true
        if (words.any { it.contains("_") || it.contains("()") }) return true
        val lowered = line.lowercase()
        return machinePrefixes.any { lowered.startsWith(it) }
    }

    private val boilerplate = setOf(AgentStore.FAILED_SUMMARY, AgentStore.STARTED_SUMMARY, "Work initiated by the user")
    private val machinePrefixes = listOf("calling ", "tool:", "tool call", "running tool", "work initiated", "started")
}

/**
 * Port of `AgentTaskStatus` (`AgentWording.swift`): where Omi stands on a task, shown on the task
 * wherever it appears: what it is doing right now (its current step and when that was), what it
 * finished, or why it stopped, in its own words.
 */
data class AgentTaskStatus(
    val kind: Kind,
    /** The current step, or the reason it stopped; null when Omi has not said. */
    val detail: Detail? = null,
    /** When the work last moved (a running step, the last event). */
    val updatedAt: Instant? = null,
    /** Running in this session right now (the glyph may breathe); a recovered run may be stale. */
    val isLive: Boolean = false,
) {
    enum class Kind { Working, Finished, Failed }

    /** What [title] says; the words resolve at render time (the localized ones need a context). */
    sealed interface Detail {
        /** Omi's own words: a step, or why it stopped. */
        data class Text(val text: String) : Detail
        /** A known reason ("Omi got stuck and stopped"). */
        data class Failure(val failure: RunFailure) : Detail
        /** "Stopped at: Checking your calendar". */
        data class StoppedAt(val step: String) : Detail
    }

    /** The line on the task: the step or reason when known, else a short default. */
    @Composable
    fun title(): String = when (val detail = detail) {
        is Detail.Text -> detail.text.ifEmpty { null }
        is Detail.Failure -> AgentWording.words(detail.failure)
        is Detail.StoppedAt -> L("nativeOmiStoppedAt", detail.step)
        null -> null
    } ?: when (kind) {
        Kind.Working -> L("nativeOmiOnIt")
        Kind.Finished -> L("nativeOmiFinished")
        Kind.Failed -> L("nativeOmiStoppedTapToSee")
    }

    val symbol: String
        get() = when (kind) {
            Kind.Working -> "sparkles"
            Kind.Finished -> "checkmark.circle"
            Kind.Failed -> "exclamationmark.triangle"
        }

    @Composable
    fun tint(): Color = when (kind) {
        Kind.Working -> DS.Palette.agent
        Kind.Finished -> DS.Palette.success
        Kind.Failed -> DS.Palette.warning
    }

    /** "2 min. ago" while Omi works (a finished or stopped task needs no clock). */
    fun age(now: Instant = Instant.now()): String? {
        val updatedAt = updatedAt ?: return null
        if (kind != Kind.Working || updatedAt <= Instant.EPOCH || Duration.between(updatedAt, now).seconds <= 30) return null
        return DateUtils.getRelativeTimeSpanString(
            updatedAt.toEpochMilli(), now.toEpochMilli(), DateUtils.MINUTE_IN_MILLIS, DateUtils.FORMAT_ABBREV_RELATIVE,
        ).toString()
    }

    companion object {
        val working = AgentTaskStatus(Kind.Working, isLive = true)
        val finished = AgentTaskStatus(Kind.Finished)
        val failed = AgentTaskStatus(Kind.Failed)

        /** Omi's state on [task], or null when Omi never had it. */
        fun of(task: ActionItem, agent: AgentStore): AgentTaskStatus? = of(
            task = task,
            workstream = task.workstreamID?.let { agent.workstreams[it] },
            liveRun = agent.runs[task.id],
            recoveredRun = agent.workItems(listOf(task)).firstOrNull(),
        )

        /**
         * The status from the parts of [AgentStore] it reads: this session's run, else the one
         * rebuilt from the task's workstream.
         */
        fun of(task: ActionItem, workstream: Workstream?, liveRun: AgentStore.Run?, recoveredRun: AgentStore.Run?): AgentTaskStatus? {
            // What the workstream says happened, newest first, without the start and failure markers.
            val events = workstream?.events.orEmpty().reversed().filter { !AgentWording.isBoilerplate(it.summary) }
            val run = liveRun ?: recoveredRun
                // A workstream not loaded yet still says Omi has it.
                ?: return if (task.workstreamID != null) AgentTaskStatus(Kind.Working) else null
            val live = liveRun != null
            val lastStep = run.steps.lastOrNull { !AgentWording.isBoilerplate(it) } ?: events.firstOrNull()?.summary
            return when (val state = run.state) {
                AgentStore.RunState.Starting -> AgentTaskStatus(Kind.Working, updatedAt = run.startedAt, isLive = live)
                is AgentStore.RunState.Working -> {
                    val step = if (AgentWording.isBoilerplate(state.step)) lastStep else state.step
                    AgentTaskStatus(
                        Kind.Working, step?.let { Detail.Text(it) },
                        updatedAt = if (live) run.startedAt else events.firstOrNull()?.createdAt, isLive = live,
                    )
                }
                is AgentStore.RunState.Done -> AgentTaskStatus(Kind.Finished, updatedAt = events.firstOrNull()?.createdAt)
                is AgentStore.RunState.Failed -> {
                    // The run's reason in plain words ("Omi got stuck and stopped"), else its own words, else
                    // where it stopped (a real step, never a heartbeat like "Preparing response").
                    val failure = run.failure
                    when {
                        failure != null && failure != RunFailure.CouldNotFinish -> AgentTaskStatus(Kind.Failed, Detail.Failure(failure))
                        !AgentWording.isBoilerplate(state.code) && RunFailure.from(state.code) == null ->
                            AgentTaskStatus(Kind.Failed, Detail.Text(state.code))
                        lastStep != null -> AgentTaskStatus(Kind.Failed, Detail.StoppedAt(lastStep))
                        else -> AgentTaskStatus(Kind.Failed)
                    }
                }
            }
        }
    }
}

/**
 * Port of `AgentStatusChip` (`TaskRow.swift`): Omi's state on a task as one quiet line: the
 * colored glyph says the state, the words say what Omi is doing or why it stopped, and while it
 * works, how long ago that was. Opens the run (live progress or result) when tapped.
 */
@Composable
fun AgentStatusChip(status: AgentTaskStatus, modifier: Modifier = Modifier, action: (() -> Unit)? = null) {
    val style = DS.Typography.caption
    Row(
        modifier
            .then(if (action != null) Modifier.pressable(onClick = action) else Modifier)
            .semantics(mergeDescendants = true) {},
        horizontalArrangement = Arrangement.spacedBy(5.dp),
        verticalAlignment = Alignment.Top,
    ) {
        SFImage(
            status.symbol, Modifier.padding(top = 2.dp).symbolPulse(status.kind == AgentTaskStatus.Kind.Working && status.isLive),
            size = 11.sp, tint = status.tint(),
        )
        Text(status.title(), style = style, color = DS.Palette.inkSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
        status.age()?.let { Text("· $it", style = style, color = DS.Palette.inkTertiary, maxLines = 1, softWrap = false) }
    }
}

/**
 * `.symbolEffect(.pulse, isActive:)`: the glyph breathes while [active] (Omi works). Still when
 * the system asks for less motion.
 */
fun Modifier.symbolPulse(active: Boolean): Modifier = composed {
    if (!active || rememberReduceMotion()) return@composed this
    val transition = rememberInfiniteTransition(label = "pulse")
    val alpha by transition.animateFloat(
        initialValue = 1f, targetValue = 0.35f,
        animationSpec = infiniteRepeatable(tween(durationMillis = 900), RepeatMode.Reverse), label = "pulse",
    )
    graphicsLayer { this.alpha = alpha }
}
