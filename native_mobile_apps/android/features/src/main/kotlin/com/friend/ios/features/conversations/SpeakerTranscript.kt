package com.friend.ios.features.conversations

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.background
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.medium
import com.friend.ios.design.omiCard
import com.friend.ios.design.plainButton
import com.friend.ios.design.pressable
import com.friend.ios.design.rememberHaptics
import com.friend.ios.service.LocalConversationsStore
import com.friend.ios.service.stores.SettingsStore
import com.friend.ios.service.stores.TranscriptSpeakersStore
import com.friend.ios.service.stores.person
import kotlinx.coroutines.launch

// Port of `SpeakerTranscript.swift`: speakers in the transcript: tapping a label asks "Who is
// this?"; after a change Omi offers to rewrite the summary with the names and to label the same
// voice elsewhere. Used by `TranscriptView`.

/** The small "Anna" label over a paragraph; tapping it names the voice. */
@Composable
fun SpeakerLabel(name: String, line: ConversationDetail.Line, onName: (ConversationDetail.Line) -> Unit) {
    val haptics = rememberHaptics()
    Text(
        name,
        style = DS.Typography.caption.medium(),
        color = DS.Palette.inkSecondary,
        modifier = Modifier
            .plainButton(enabled = line.segmentID != null) {
                haptics.selection()
                onName(line)
            }
            .padding(vertical = DS.Spacing.xxs),
    )
}

/** Follow-ups after a name changed: rewrite the summary, review the same voice elsewhere. */
@Composable
fun SpeakerTools(speakers: TranscriptSpeakersStore, onReviewMatches: () -> Unit) {
    val conversations = LocalConversationsStore.current
    val scope = rememberCoroutineScope()
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg)) {
        if (speakers.offersSummaryRefresh) {
            HStack(
                Modifier
                    .pressable(enabled = !speakers.isRefreshingSummary, pressedScale = 1f, pressedAlpha = 0.8f, haptic = false) {
                        scope.launch {
                            speakers.refreshSummary()
                            conversations.load()
                        }
                    }
                    .background(DS.Palette.cardRaised, CircleShape)
                    .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
                spacing = DS.Spacing.sm,
            ) {
                if (speakers.isRefreshingSummary) OmiProgress(Modifier.padding(0.dp)) else SFImage("arrow.clockwise", size = 15.sp, tint = DS.Palette.ink)
                Text(L("updateSummaryWithNewNames"), style = DS.Typography.callout.medium(), color = DS.Palette.ink)
            }
        }
        val matches = speakers.matches
        if (matches != null && matches.items.isNotEmpty()) {
            Row(Modifier.omiCard(padding = DS.Spacing.md), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                SFImage("waveform.badge.magnifyingglass", tint = DS.Palette.agent)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                    Text(L("nativeVoiceMatchesTitle", matches.person.name), style = DS.Typography.cardTitle, color = DS.Palette.ink)
                    Text(L("nativeVoiceMatchesBody", "${matches.items.size}"), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                    Box(Modifier.padding(top = DS.Spacing.xs)) { OmiPillButton(L("nativeVoiceMatchesReview"), onClick = onReviewMatches) }
                }
                SFImage("xmark", Modifier.plainButton { speakers.dismissMatches() }, size = 15.sp, weight = FontWeight.Normal, tint = DS.Palette.inkTertiary, contentDescription = L("close"))
            }
        }
        if (speakers.lastError != null) {
            Text(L("speakerTagPromptAnswerFailed"), style = DS.Typography.caption, color = DS.Palette.live)
        }
    }
}

/** "You", the person's name, or "Speaker N" for a voice nobody named yet. */
@Composable
fun SettingsStore.speakerName(line: ConversationDetail.Line): String {
    if (line.isUser) return L("nativeSpeakerYou")
    line.personID?.let { id -> person(id)?.name?.takeIf { it.isNotEmpty() }?.let { return it } }
    line.speakerID?.let { return L("speakerWithId", "${it + 1}") }
    return line.speaker
}
