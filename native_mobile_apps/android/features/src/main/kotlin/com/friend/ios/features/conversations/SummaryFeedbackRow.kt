package com.friend.ios.features.conversations

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ConversationFeedbackKind
import com.friend.ios.core.models.SummaryFeedbackReason
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiChip
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.medium
import com.friend.ios.design.omiCard
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.service.stores.SummaryFeedbackStore
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `SummaryFeedbackRow.swift`: "Was this helpful? · Give feedback · x" under Omi's own
 * summary, or the same row about the recording, now and then (`SummaryFeedbackStore` decides when
 * and which). "Give feedback" opens the reasons.
 */
@Composable
fun SummaryFeedbackRow(feedback: SummaryFeedbackStore) {
    val scope = rememberCoroutineScope()
    var choosing by remember { mutableStateOf(false) }
    when (feedback.state) {
        SummaryFeedbackStore.State.Hidden -> Unit
        SummaryFeedbackStore.State.Thanked -> {
            HStack(spacing = DS.Spacing.sm) {
                SFImage("checkmark.circle.fill", size = 15.sp, tint = DS.Palette.success)
                Text(L("nativeThanksForFeedback"), style = DS.Typography.callout, color = DS.Palette.success)
            }
            LaunchedEffect(Unit) {
                delay(2_000)
                feedback.finish()
            }
        }
        SummaryFeedbackStore.State.Asking, SummaryFeedbackStore.State.Sending, SummaryFeedbackStore.State.Failed -> {
            HStack(Modifier.omiCard(padding = DS.Spacing.md), spacing = DS.Spacing.sm) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                    Text(FeedbackReasons.question(feedback.kind), style = DS.Typography.callout.medium(), color = DS.Palette.ink)
                    if (feedback.state == SummaryFeedbackStore.State.Failed) {
                        Text(L("nativeFeedbackNotSent"), style = DS.Typography.caption, color = DS.Palette.live)
                    } else if (feedback.kind == ConversationFeedbackKind.Recording) {
                        Text(L("feedbackSubtitleAudioQuality"), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                    }
                }
                if (feedback.state == SummaryFeedbackStore.State.Sending) {
                    OmiProgress()
                } else {
                    OmiPillButton(L("feedbackGiveFeedback"), prominent = false) { choosing = true }
                }
                Box(Modifier.size(28.dp).plainButton { feedback.dismiss() }, contentAlignment = Alignment.Center) {
                    SFImage("xmark", size = 13.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkTertiary, contentDescription = L("close"))
                }
            }
        }
    }
    if (choosing) {
        FeedbackReasonsSheet(feedback.kind, onDismiss = { choosing = false }) { helpful, reason -> scope.launch { feedback.send(helpful, reason) } }
    }
}

/** "All good", or what was wrong with the summary or the recording; one tap sends. */
@Composable
private fun FeedbackReasonsSheet(kind: ConversationFeedbackKind, onDismiss: () -> Unit, onPick: (Boolean, SummaryFeedbackReason?) -> Unit) {
    val haptics = rememberHaptics()
    fun pick(helpful: Boolean, reason: SummaryFeedbackReason?) {
        haptics.tap()
        onPick(helpful, reason)
        onDismiss()
    }
    OmiSheet(onDismiss = onDismiss, detents = setOf(com.friend.ios.design.Detent.Medium)) {
        Column(
            Modifier.fillMaxWidth().padding(DS.Spacing.gutter),
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg),
        ) {
            Text(FeedbackReasons.question(kind), style = DS.Typography.sectionTitle, color = DS.Palette.ink)
            Box(Modifier.plainButton { pick(true, null) }) {
                OmiChip(L("feedbackAllGood"), systemImage = "hand.thumbsup", tint = DS.Palette.success)
            }
            FlowChips {
                SummaryFeedbackReason.reasons(kind).forEach { reason ->
                    Box(Modifier.plainButton { pick(false, reason) }) { OmiChip(FeedbackReasons.title(reason)) }
                }
            }
        }
    }
}

private object FeedbackReasons {
    /** The row's and the sheet's question. */
    @Composable
    fun question(kind: ConversationFeedbackKind): String = when (kind) {
        ConversationFeedbackKind.Summary -> L("wasThisHelpful")
        ConversationFeedbackKind.Recording -> L("feedbackTitleAudioQuality")
    }

    @Composable
    fun title(reason: SummaryFeedbackReason): String = when (reason) {
        SummaryFeedbackReason.Inaccurate -> L("feedbackReasonSummaryInaccurate")
        SummaryFeedbackReason.Incomplete -> L("feedbackReasonSummaryIncomplete")
        SummaryFeedbackReason.Irrelevant -> L("feedbackReasonSummaryIrrelevant")
        SummaryFeedbackReason.WrongContext -> L("feedbackReasonSummaryWrongContext")
        SummaryFeedbackReason.Other -> L("feedbackReasonSummaryOther")
        SummaryFeedbackReason.MissingAudio -> L("feedbackReasonRecordingMissingAudio")
        SummaryFeedbackReason.PoorTranscription -> L("feedbackReasonRecordingPoorTranscription")
        SummaryFeedbackReason.WrongSpeaker -> L("feedbackReasonRecordingWrongSpeaker")
        SummaryFeedbackReason.DelayedOrStuck -> L("feedbackReasonRecordingDelayedOrStuck")
        SummaryFeedbackReason.FragmentedOrDuplicated -> L("feedbackReasonRecordingFragmentedOrDuplicated")
        SummaryFeedbackReason.RecordingOther -> L("feedbackReasonRecordingOther")
    }
}

/** Chips that wrap onto the next line, each line centred vertically. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FlowChips(modifier: Modifier = Modifier, spacing: androidx.compose.ui.unit.Dp = DS.Spacing.sm, content: @Composable () -> Unit) {
    FlowRow(
        modifier,
        horizontalArrangement = Arrangement.spacedBy(spacing),
        verticalArrangement = Arrangement.spacedBy(spacing),
        itemVerticalAlignment = Alignment.CenterVertically,
    ) { content() }
}
