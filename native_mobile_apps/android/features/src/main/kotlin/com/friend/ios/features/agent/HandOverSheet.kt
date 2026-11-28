package com.friend.ios.features.agent

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ActionItem
import com.friend.ios.design.CalmBackground
import com.friend.ios.design.CircleIconButton
import com.friend.ios.design.DS
import com.friend.ios.design.DSHaptics
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.medium
import com.friend.ios.design.omiCard
import com.friend.ios.design.plainButton
import com.friend.ios.design.pressable
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.MarkdownBlocks
import com.friend.ios.service.LocalAgentStore
import com.friend.ios.service.LocalTasksStore
import com.friend.ios.service.stores.AgentStore
import com.friend.ios.service.stores.canTakeOver
import com.friend.ios.service.stores.loadHistory
import kotlinx.coroutines.delay
import java.time.Instant

/**
 * Port of `HandOverSheet.swift`: "Omi takes over": preview, live progress, result (PLAN.md 4.4).
 * Shown in an `OmiSheet` (large detent, as on iOS: one height for every state).
 */
@Composable
fun HandOverSheet(task: ActionItem, conversationTitle: String?, onDismiss: () -> Unit) {
    val agent = LocalAgentStore.current
    val tasks = LocalTasksStore.current
    val haptics = rememberHaptics()
    var showsSteps by remember { mutableStateOf(false) }
    /** This session's run, or one recovered from the task's workstream (opened from Home later). */
    val run = agent.runs[task.id] ?: agent.workItems(listOf(task)).firstOrNull()
    val isFinished = run?.state is AgentStore.RunState.Done

    // A finished result seen here is no longer news on Home.
    LaunchedEffect(isFinished) { if (isFinished) agent.markOpened(task.id) }
    // An earlier run (after a restart): its steps and text from the backend.
    LaunchedEffect(task.id) { if (agent.runs[task.id] == null && task.workstreamID != null) agent.loadHistory(task) }

    val hasAction = when (run?.state) {
        null, is AgentStore.RunState.Done -> true
        is AgentStore.RunState.Failed -> run?.failure?.let { AgentWording.action(it) } != null && agent.canTakeOver(task)
        else -> false
    }

    Box(Modifier.fillMaxSize()) {
        CalmBackground()
        Column(Modifier.fillMaxSize()) {
            HStack(Modifier.padding(horizontal = DS.Spacing.gutter).padding(top = DS.Spacing.xs)) {
                CircleIconButton("xmark", contentDescription = L("close"), onClick = onDismiss)
                Spacer(Modifier.weight(1f))
            }
            Column(
                Modifier
                    .weight(1f)
                    .verticalScroll(rememberScrollState())
                    .padding(DS.Spacing.gutter)
                    .padding(bottom = if (hasAction) 96.dp else 0.dp),
                verticalArrangement = Arrangement.spacedBy(DS.Spacing.xl),
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                    HandOverKicker("sparkles", L("nativeOmiTakesOver"), DS.Palette.agent)
                    Text(task.description, style = DS.Typography.title, color = DS.Palette.ink)
                    if (conversationTitle != null) {
                        Text(L("nativeFromConversation", conversationTitle), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
                    }
                }
                if (run != null) Progress(run, showsSteps) { showsSteps = !showsSteps } else Preview()
            }
        }
        // The sheet's one action, over a fade: the result scrolls out under it, never shows below it.
        if (hasAction) {
            val page = DS.Palette.background
            Box(
                Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .background(Brush.verticalGradient(0f to page.copy(alpha = 0f), 0.4f to page))
                    .navigationBarsPadding()
                    .padding(horizontal = DS.Spacing.gutter)
                    .padding(top = DS.Spacing.xl, bottom = DS.Spacing.sm),
            ) {
                when (run?.state) {
                    null -> PrimaryButton(L("nativeStart"), "sparkles") {
                        haptics.tap(DSHaptics.Style.Medium)
                        agent.background { agent.takeOver(task, conversationTitle) }
                    }
                    is AgentStore.RunState.Done -> PrimaryButton(L("nativeMarkDone"), "checkmark") {
                        haptics.success()
                        agent.background { tasks.setCompleted(task.id, true) }
                        onDismiss()
                    }
                    is AgentStore.RunState.Failed -> PrimaryButton(run?.failure?.let { AgentWording.action(it) } ?: L("retry"), "arrow.clockwise") {
                        // Resume a stopped run in its own thread; try again otherwise.
                        haptics.tap(DSHaptics.Style.Medium)
                        agent.background { agent.resume(task, conversationTitle) }
                    }
                    else -> Unit
                }
            }
        }
    }
}

/** What Omi will do, text first: a thin gray glyph, one line each. */
@Composable
private fun Preview() {
    Column(Modifier.omiCard(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
        PreviewRow("magnifyingglass", L("nativeHandOverResearch"))
        PreviewRow("calendar", L("nativeHandOverCalendar"))
        PreviewRow("doc.text", L("nativeHandOverDrafts"))
        PreviewRow("hand.raised", L("nativeHandOverTrust"))
    }
}

@Composable
private fun PreviewRow(icon: String, text: String) {
    HStack(spacing = DS.Spacing.md, alignment = Alignment.Top) {
        Box(Modifier.width(22.dp), contentAlignment = Alignment.Center) {
            SFImage(icon, size = 15.sp, tint = DS.Palette.inkSecondary)
        }
        Text(text, style = DS.Typography.callout, color = DS.Palette.ink)
    }
}

/**
 * While Omi works: what it is doing right now, then the steps so far. Once it is done the result
 * leads and the steps fold away.
 */
@Composable
private fun Progress(run: AgentStore.Run, showsSteps: Boolean, onToggleSteps: () -> Unit) {
    val agent = com.friend.ios.service.LocalAgentStore.current
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg)) {
        when (val state = run.state) {
            is AgentStore.RunState.Working -> {
                agent.deviceToolRequests[run.id]?.let { com.friend.ios.features.components.OmiAsksCard(it) }
                WorkingCard(state.step.ifEmpty { L("nativeWriting") }, run.startedAt)
                // The steps before the current one, plus what Omi has written so far.
                if (run.steps.size > 1) StepList(run.steps.dropLast(1), isWorking = false)
                if (run.partialText.isNotEmpty()) MarkdownBlocks(run.partialText, Modifier.omiCard())
                HStack(spacing = DS.Spacing.xs) {
                    SFImage("moon.zzz", size = 12.sp, tint = DS.Palette.inkTertiary)
                    Text(L("nativeKeepsWorkingHint"), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
                }
            }
            AgentStore.RunState.Starting -> WorkingCard(L("nativePreparing"), run.startedAt)
            is AgentStore.RunState.Done -> {
                Column(Modifier.omiCard(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                    HandOverKicker("checkmark.circle", L("nativeOmiFinished"), DS.Palette.success)
                    MarkdownBlocks(state.result)
                }
                Steps(run, showsSteps, onToggleSteps)
            }
            is AgentStore.RunState.Failed -> {
                HStack(Modifier.omiCard(), spacing = DS.Spacing.sm, alignment = Alignment.Top) {
                    SFImage("exclamationmark.triangle", size = 15.sp, tint = DS.Palette.warning)
                    Text(AgentWording.failure(state.code), style = DS.Typography.callout, color = DS.Palette.warning)
                }
                // What Omi had written before it stopped.
                if (run.partialText.isNotEmpty()) MarkdownBlocks(run.partialText, Modifier.omiCard())
                Steps(run, showsSteps, onToggleSteps)
            }
        }
    }
}

/** The steps, folded (`DisclosureGroup`). */
@Composable
private fun Steps(run: AgentStore.Run, expanded: Boolean, onToggle: () -> Unit) {
    if (run.steps.isEmpty()) return
    val count = run.steps.count { it.isNotEmpty() }
    val rotation by animateFloatAsState(if (expanded) 90f else 0f, DS.Motion.standard(), label = "steps")
    Column {
        HStack(Modifier.fillMaxWidth().heightIn(min = 36.dp).plainButton(onClick = onToggle), spacing = DS.Spacing.sm) {
            SFImage("list.bullet", size = 15.sp, tint = DS.Palette.inkSecondary)
            Text(if (count == 1) L("nativeStepsCountOne") else L("nativeStepsCount", "$count"), style = DS.Typography.callout, color = DS.Palette.inkSecondary)
            Spacer(Modifier.weight(1f))
            SFImage("chevron.right", Modifier.rotate(rotation), size = 12.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkSecondary)
        }
        AnimatedVisibility(expanded) { StepList(run.steps, isWorking = false, modifier = Modifier.padding(top = DS.Spacing.sm)) }
    }
}

/**
 * Omi at work, as a For you card: the blue "Omi is on it" kicker (its glyph breathes), how long it
 * has been going, and the current step.
 */
@Composable
internal fun WorkingCard(step: String, since: Instant) {
    val now by produceState(Instant.now(), since) {
        while (true) {
            value = Instant.now()
            delay(1_000)
        }
    }
    // One element for TalkBack: what Omi is on, for how long, and the step.
    Column(Modifier.omiCard().semantics(mergeDescendants = true) {}, verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        HStack {
            HandOverKicker("sparkles", L("nativeOmiOnIt"), DS.Palette.agent, pulses = true)
            Spacer(Modifier.weight(1f))
            Text(
                elapsed(since, now),
                style = DS.Typography.caption.copy(fontFeatureSettings = "tnum"),
                color = DS.Palette.inkTertiary,
            )
        }
        AnimatedContent(step, transitionSpec = { fadeIn(DS.Motion.standard()) togetherWith fadeOut(DS.Motion.standard()) }, label = "step") { text ->
            Text(text, style = TextStyles.body.medium(), color = DS.Palette.ink)
        }
    }
}

/**
 * The small colored line over a hand-over card (as the For you cards' kicker): a glyph and a few
 * words, blue for Omi's work, green once it is done.
 */
@Composable
internal fun HandOverKicker(symbol: String, text: String, color: Color, pulses: Boolean = false) {
    val alpha = if (pulses) {
        val transition = rememberInfiniteTransition(label = "pulse")
        val value by transition.animateFloat(1f, 0.35f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "glyph")
        value
    } else {
        1f
    }
    HStack(spacing = 6.dp) {
        SFImage(symbol, Modifier.alpha(alpha), size = 12.sp, weight = FontWeight.SemiBold, tint = color)
        Text(text, style = TextStyles.footnote.semibold(), color = color)
    }
}

/** `.omiPrimary` with a `Label`: the glyph before the title. */
@Composable
private fun PrimaryButton(title: String, symbol: String, onClick: () -> Unit) {
    androidx.compose.foundation.layout.Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = DS.Size.primaryButtonHeight)
            .pressable(pressedScale = 0.98f, pressedAlpha = 0.85f, onClick = onClick)
            .background(DS.Palette.accent, CircleShape),
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm, Alignment.CenterHorizontally),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        SFImage(symbol, size = 15.sp, weight = FontWeight.SemiBold, tint = DS.Palette.onAccent)
        Text(title, style = DS.Typography.button, color = DS.Palette.onAccent)
    }
}
