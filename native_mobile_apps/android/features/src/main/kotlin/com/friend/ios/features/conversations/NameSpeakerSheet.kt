package com.friend.ios.features.conversations

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.VoiceMatch
import com.friend.ios.design.DS
import com.friend.ios.design.Detent
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.features.components.SpeakerNamePicker
import com.friend.ios.features.components.rememberAudioClipPlayer
import com.friend.ios.features.settings.talkTime
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.TranscriptSpeakersStore
import kotlinx.coroutines.launch

/**
 * Port of `NameSpeakerSheet.swift`: "Who is this?" for one transcript line (Flutter
 * `name_speaker_sheet`): `SpeakerNamePicker` on this conversation's `TranscriptSpeakersStore`.
 */
@Composable
fun NameSpeakerSheet(line: ConversationDetail.Line, speakers: TranscriptSpeakersStore, onDismiss: () -> Unit) {
    val settings = LocalSettingsStore.current
    val scope = rememberCoroutineScope()
    SpeakerNamePicker(
        SpeakerNamePicker.Line(
            text = line.text, isUser = line.isUser, personID = line.personID, hasVoice = line.speakerID != null,
            sameVoiceCount = speakers.lines(line).size, offersNotAPerson = true,
        ),
        isSaving = speakers.isSaving,
        onDismiss = onDismiss,
    ) { choice, chosen ->
        scope.launch { if (speakers.assign(line, choice, chosen) != null) settings.loadPeople() }
    }
}

/**
 * "Is this also <name>?" for each earlier conversation where the same voice speaks (Flutter
 * `earlier_voice_matches_sheet`).
 */
@Composable
fun VoiceMatchesSheet(speakers: TranscriptSpeakersStore, onDismiss: () -> Unit) {
    val player = rememberAudioClipPlayer()
    var unplayable by remember { mutableStateOf(setOf<String>()) }
    val empty = speakers.matches?.items?.isEmpty() ?: true
    LaunchedEffect(empty) { if (empty) onDismiss() }
    OmiSheet(onDismiss = onDismiss, detents = setOf(Detent.Medium, Detent.Large)) {
        SheetBar(
            L("nativeVoiceMatchesTitle", speakers.matches?.person?.name ?: ""),
            trailing = { SheetBarButton(L("done"), prominent = true, onClick = onDismiss) },
        )
        val matches = speakers.matches
        OmiGroupedList(contentPadding = PaddingValues(top = DS.Spacing.lg, bottom = DS.Spacing.section)) {
            if (matches != null) {
                section(footer = L("nativeVoiceMatchesFooter")) {
                    matches.items.forEach { match ->
                        row(key = match.id) {
                            MatchRow(match, speakers, player, match.id in unplayable) {
                                unplayable = unplayable + match.id
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MatchRow(
    match: VoiceMatch,
    speakers: TranscriptSpeakersStore,
    player: com.friend.ios.features.components.AudioClipPlayer,
    unavailable: Boolean,
    onUnplayable: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    val subtitle = subtitle(match)
    Column(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.xs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                Text(match.title.ifEmpty { L("untitledConversation") }, style = DS.Typography.cardTitle, color = DS.Palette.ink)
                Text(subtitle, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
            }
            val isPlaying = player.playingID == match.id
            SFImage(
                if (isPlaying) "stop.circle.fill" else "play.circle.fill",
                Modifier.plainButton(enabled = !unavailable) {
                    scope.launch {
                        val played = player.toggle(match.id) { speakers.clip(match) }
                        if (!played) onUnplayable()
                    }
                },
                size = 22.sp,
                tint = if (unavailable) DS.Palette.inkDisabled else DS.Palette.agent,
                contentDescription = L("speakerTagPromptPlayClip"),
            )
        }
        if (unavailable) Text(L("speakerTagPromptClipUnavailable"), style = DS.Typography.caption, color = DS.Palette.inkTertiary)
        HStack(spacing = DS.Spacing.sm) {
            OmiPillButton(L("yes")) { scope.launch { speakers.answer(match, same = true) } }
            OmiPillButton(L("no"), prominent = false) { scope.launch { speakers.answer(match, same = false) } }
        }
    }
}

@Composable
private fun subtitle(match: VoiceMatch): String {
    val talk = L("speakerLabelTalkTime", talkTime(match.talkSeconds))
    val date = match.startedAt ?: return talk
    return "${DetailDates.monthDay(date)} · $talk"
}
