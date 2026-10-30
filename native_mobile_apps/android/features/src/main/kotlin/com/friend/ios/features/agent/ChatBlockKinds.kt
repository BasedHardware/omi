package com.friend.ios.features.agent

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ChatBlock
import com.friend.ios.core.models.ChatMemoryReview
import com.friend.ios.core.models.ChatQuestion
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.service.LocalMemoriesStore
import com.friend.ios.service.stores.MemoriesStore
import kotlinx.coroutines.launch

/*
 * Port of `ChatBlockKinds.swift`: the cards that are a kind of their own: a discovery, a question
 * with prepared answers, a background run, and the day's memories to review.
 *
 * iOS keys its per-card state on the block's id (so two blocks of the same kind never share it) and
 * tags each card for screenshots; the Android port does the same for the state and leaves the tags
 * out, as the rest of the port does.
 */

// Discovery

/**
 * Something Omi found: a title, its summary, and the whole text behind Show More. Tappable only
 * while there is more to read than what is already shown.
 */
@Composable
fun DiscoveryBlockCard(blockID: String, title: String, summary: String, fullText: String, modifier: Modifier = Modifier) {
    var expanded by remember(blockID) { mutableStateOf(false) }
    val hasMore = fullText.isNotEmpty() && fullText != summary
    val body = if (expanded && hasMore) fullText else summary
    // Read here, not in the tap handler: `L` is composable (iOS's `L` is a plain function).
    val showMore = L(if (expanded) "chatBlockShowLess" else "chatBlockShowMore")
    ChatBlockCard(modifier, onTap = if (hasMore) ({ expanded = !expanded }) else null) {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs + 2.dp)) {
            ChatBlockEyebrow("sparkle.magnifyingglass", L("discovery"))
            if (title.isNotEmpty()) Text(title, style = DS.Typography.callout.semibold(), color = DS.Palette.ink)
            if (body.isNotEmpty()) Text(body, style = DS.Typography.callout, color = DS.Palette.ink)
            if (hasMore) {
                HStack(spacing = DS.Spacing.xs) {
                    Text(showMore, style = DS.Typography.caption.semibold(), color = DS.Palette.agent)
                    SFImage(if (expanded) "chevron.up" else "chevron.down", size = 10.sp, tint = DS.Palette.agent)
                }
            }
        }
    }
}

// Question

/**
 * Omi's question with the answers it prepared: tapping one sends it as the user's own words. Once
 * answered, only the chosen answer stays, marked and no longer tappable (Flutter `QuestionCardBlock`).
 */
@Composable
fun QuestionBlockCard(question: ChatQuestion, onSend: (String) -> Unit, modifier: Modifier = Modifier) {
    ChatBlockCard(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
            ChatBlockEyebrow("questionmark.circle", L("chatBlockQuestion"))
            if (question.text.isNotEmpty()) Text(question.text, style = DS.Typography.callout, color = DS.Palette.ink)
            Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
                for (option in question.visibleOptions) QuestionOption(question, option, onSend)
            }
        }
    }
}

@Composable
private fun QuestionOption(question: ChatQuestion, option: ChatQuestion.Option, onSend: (String) -> Unit) {
    val haptics = rememberHaptics()
    // What tapping sends: the answer the backend prepared, or the label when it prepared none.
    val answer = option.preparedAnswer.trim().ifEmpty { option.label.trim() }
    if (question.isAnswered) {
        HStack(spacing = DS.Spacing.sm) {
            SFImage(
                "checkmark.circle.fill",
                size = 14.sp,
                tint = if (option.id == question.selectedOptionID) DS.Palette.agent else DS.Palette.inkTertiary,
            )
            Text(option.label, style = DS.Typography.callout, color = DS.Palette.inkSecondary)
        }
    } else if (answer.isEmpty()) {
        // Nothing to send: a label, not a button.
        Text(option.label, style = DS.Typography.callout, color = DS.Palette.inkSecondary)
    } else {
        Text(
            option.label,
            style = DS.Typography.callout,
            color = DS.Palette.ink,
            modifier = Modifier
                .heightIn(min = 36.dp)
                .plainButton {
                    haptics.tap()
                    onSend(answer)
                }
                .border(1.dp, DS.Palette.cardStroke, CircleShape)
                .padding(horizontal = DS.Spacing.md, vertical = DS.Spacing.sm),
        )
    }
}

// Agent run

/**
 * A background run: what it is doing, or how it ended. Read-only on purpose: the phone has no
 * place to watch a run (Flutter `_AgentRunCard`).
 */
@Composable
fun AgentRunBlockCard(title: String, detail: String, status: ChatBlock.AgentRunStatus, modifier: Modifier = Modifier) {
    val symbol = when (status) {
        ChatBlock.AgentRunStatus.Running -> "cpu"
        ChatBlock.AgentRunStatus.Completed -> "checkmark.circle"
        ChatBlock.AgentRunStatus.Cancelled -> "slash.circle"
        ChatBlock.AgentRunStatus.TimedOut -> "clock.badge.exclamationmark"
        ChatBlock.AgentRunStatus.Failed -> "exclamationmark.triangle"
    }
    val label = when (status) {
        ChatBlock.AgentRunStatus.Running -> L("processing")
        ChatBlock.AgentRunStatus.Completed -> L("statusCompleted")
        ChatBlock.AgentRunStatus.Cancelled -> L("cancelled")
        ChatBlock.AgentRunStatus.TimedOut -> L("statusTimedOut")
        ChatBlock.AgentRunStatus.Failed -> L("statusFailed")
    }
    ChatBlockCard(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs + 2.dp)) {
            ChatBlockEyebrow(symbol, label)
            if (title.isNotEmpty()) Text(title, style = DS.Typography.callout.semibold(), color = DS.Palette.ink)
            if (detail.isNotEmpty()) {
                Text(detail, style = DS.Typography.callout, color = DS.Palette.inkSecondary, maxLines = 6, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

// Memory review

/**
 * "Things I learned today": up to three memories Omi stored, each named live from the store, with
 * the two verdicts the review API takes. A verdict is addressed by id, so a memory the list has not
 * loaded yet is still answerable; while a verdict is in flight its row does not offer another.
 */
@Composable
fun MemoryReviewBlockCard(review: ChatMemoryReview, modifier: Modifier = Modifier) {
    val memories = LocalMemoriesStore.current
    val scope = rememberCoroutineScope()
    // What this card has settled itself, by memory id: the load that follows reads the verdict back.
    var settled by remember(review.summaryID) { mutableStateOf<Map<String, Boolean>>(emptyMap()) }
    var inFlight by remember(review.summaryID) { mutableStateOf<Set<String>>(emptySet()) }
    var failed by remember(review.summaryID) { mutableStateOf<Set<String>>(emptySet()) }
    LaunchedEffect(review.summaryID) { if (memories.phase != MemoriesStore.Phase.Loaded) memories.load() }
    ChatBlockCard(modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                Text(L("memoryReviewTitle"), style = DS.Typography.callout.semibold(), color = DS.Palette.ink)
                Text(L("nativeMemoryReviewHint"), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
            }
            for (item in review.items) {
                // The recap's own text until the store has the memory: it may have been edited since.
                val memory = memories.memories.firstOrNull { it.id == item.memoryID }
                ReviewRow(
                    content = memory?.content ?: item.content,
                    category = item.category,
                    state = settled[item.memoryID] ?: memory?.userReview,
                    isBusy = inFlight.contains(item.memoryID),
                    didFail = failed.contains(item.memoryID),
                    onVote = { isRight ->
                        if (!inFlight.contains(item.memoryID)) {
                            inFlight = inFlight + item.memoryID
                            failed = failed - item.memoryID
                            scope.launch {
                                memories.review(item.memoryID, isRight)
                                inFlight = inFlight - item.memoryID
                                if (memories.lastError.isNullOrEmpty()) {
                                    settled = settled + (item.memoryID to isRight)
                                } else {
                                    // The store rolled its own change back: this row is unanswered again.
                                    failed = failed + item.memoryID
                                }
                            }
                        }
                    },
                )
            }
        }
    }
}

/** One memory and its two verdicts: "Right" keeps it, "Wrong" drops it. */
@Composable
private fun ReviewRow(
    content: String,
    category: String,
    state: Boolean?,
    isBusy: Boolean,
    didFail: Boolean,
    onVote: (Boolean) -> Unit,
) {
    Column(
        Modifier
            .fillMaxWidth()
            .background(DS.Palette.fill, ContinuousRoundedShape(DS.Radius.sm))
            .padding(DS.Spacing.md),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        Text(content, style = DS.Typography.callout, color = if (state == false) DS.Palette.inkTertiary else DS.Palette.ink)
        HStack(spacing = DS.Spacing.md) {
            if (category.isNotEmpty()) {
                Text(category, style = DS.Typography.caption, color = DS.Palette.inkTertiary, letterSpacing = DS.Tracking.label.sp)
            }
            if (state != null) {
                Text(
                    L(if (state) "memoryReviewConfirmed" else "memoryReviewDropped"),
                    style = DS.Typography.caption,
                    color = DS.Palette.inkSecondary,
                )
            } else {
                Spacer(Modifier.weight(1f))
                Verdict(L("memoryReviewRight"), on = true, enabled = !isBusy, onVote = onVote)
                Verdict(L("memoryReviewWrong"), on = false, enabled = !isBusy, onVote = onVote)
            }
        }
        AnimatedVisibility(didFail) {
            Text(L("memoryReviewSaveFailed"), style = DS.Typography.caption, color = DS.Palette.warning)
        }
    }
}

/** One verdict, left for the two answers the review API takes. */
@Composable
private fun Verdict(title: String, on: Boolean, enabled: Boolean, onVote: (Boolean) -> Unit) {
    val haptics = rememberHaptics()
    Text(
        title,
        style = DS.Typography.caption.semibold(),
        color = if (on) DS.Palette.agent else DS.Palette.inkSecondary,
        modifier = Modifier
            .heightIn(min = 36.dp)
            .plainButton(enabled = enabled) {
                haptics.tap()
                onVote(on)
            }
            .background(DS.Palette.background, CircleShape)
            .padding(horizontal = DS.Spacing.md),
    )
}
