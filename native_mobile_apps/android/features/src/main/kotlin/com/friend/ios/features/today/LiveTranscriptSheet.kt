package com.friend.ios.features.today

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.livePillElapsed
import com.friend.ios.design.plainButton
import com.friend.ios.design.pressable
import com.friend.ios.design.semibold
import com.friend.ios.features.components.SpeakerNamePicker
import com.friend.ios.network.listen.LiveSegment
import com.friend.ios.service.LocalCaptureStore
import com.friend.ios.service.LocalLiveSpeakersStore
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.CaptureStore
import com.friend.ios.service.stores.LiveSpeakersStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Port of `LiveTranscriptSheet.swift`: the conversation being recorded, in full (Flutter
 * `conversation_capturing/page.dart`): every segment with its speaker, how long it runs, where the
 * audio comes from, Pause/Resume and Stop. A tap on a speaker names the voice, as on a finished
 * conversation.
 */
@Composable
fun LiveTranscriptSheet(onDismiss: () -> Unit) {
    val capture = LocalCaptureStore.current
    LaunchedEffect(capture.phase) { if (capture.phase == CaptureStore.Phase.Idle) onDismiss() }
    OmiSheet(onDismiss = onDismiss) {
        // The inline navigation bar: Done on the left, the title in the middle.
        Box(Modifier.statusBarsPadding().fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = DS.Spacing.lg)) {
            Text(L("nativeDone"), style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.align(Alignment.CenterStart).plainButton(onClick = onDismiss))
            Text(L("nativeLiveTranscript"), style = TextStyles.headline, color = DS.Palette.ink, modifier = Modifier.align(Alignment.Center))
        }
        Box(Modifier.weight(1f, fill = true)) { Transcript(capture) }
        Controls(capture)
    }
}

@Composable
private fun Transcript(capture: CaptureStore) {
    val speakers = LocalLiveSpeakersStore.current
    var naming by remember { mutableStateOf<LiveSegment?>(null) }
    // The transcript's scope: a naming finishes after the picker has closed.
    val scope = rememberCoroutineScope()
    val lines = capture.segments + listOfNotNull(capture.partial)
    val listState = rememberLazyListState()
    LaunchedEffect(capture.transcriptText) {
        if (lines.isNotEmpty()) listState.animateScrollToItem(lines.size)
    }
    LazyColumn(
        Modifier.fillMaxSize(),
        state = listState,
        contentPadding = PaddingValues(start = DS.Spacing.lg, end = DS.Spacing.lg, bottom = DS.Spacing.section),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.md),
    ) {
        item(key = "header") { Header(capture) }
        if (lines.isEmpty()) {
            item(key = "hint") {
                Text(
                    if (capture.isPaused) L("paused") else L("nativeListeningHint"),
                    style = DS.Typography.callout,
                    color = DS.Palette.inkSecondary,
                    modifier = Modifier.padding(top = DS.Spacing.xl),
                )
            }
        }
        items(lines, key = { it.id }) { line ->
            Row(line, isPartial = line.id == capture.partial?.id, capture, speakers) { naming = line }
        }
    }
    naming?.let { segment -> NamingSheet(segment, speakers, scope) { naming = null } }
}

/** "Who is this?" for a live line: you, one of your people or a new name (no "Not a person" while recording). */
@Composable
private fun NamingSheet(segment: LiveSegment, speakers: LiveSpeakersStore, scope: CoroutineScope, onDismiss: () -> Unit) {
    val settings = LocalSettingsStore.current
    LaunchedEffect(Unit) { if (settings.people.isEmpty()) settings.loadPeople() }
    val label = speakers.label(segment)
    SpeakerNamePicker(
        SpeakerNamePicker.Line(
            text = segment.text, isUser = label.isUser, personID = label.personID, hasVoice = segment.speakerID != null,
            sameVoiceCount = speakers.lines(sameVoiceAs = segment).size, offersNotAPerson = false,
        ),
        isSaving = speakers.isSaving,
        onDismiss = onDismiss,
    ) { choice, chosen ->
        scope.launch { if (speakers.assign(segment, choice, chosen) != null) settings.loadPeople() }
    }
}

/** Recording since, the source, and the star mark from a double tap. */
@Composable
private fun Header(capture: CaptureStore) {
    val style = DS.Typography.caption.semibold()
    HStack(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.sm), spacing = DS.Spacing.sm) {
        Box(Modifier.size(8.dp).background(if (capture.isPaused) DS.Palette.inkTertiary else DS.Palette.live, CircleShape))
        (capture.phase as? CaptureStore.Phase.Live)?.let { Elapsed(it.sinceMillis, style) }
        if (capture.isPaused) Text(L("paused"), style = style, color = DS.Palette.inkSecondary)
        Spacer(Modifier.weight(1f))
        if (capture.starsConversation) SFImage("star.fill", size = 12.sp, tint = DS.Palette.warning, contentDescription = L("starConversation"))
        val device = capture.source == CaptureStore.Source.Device
        HStack(spacing = DS.Spacing.xs) {
            SFImage(if (device) "circle.circle.fill" else "iphone", size = 12.sp, tint = DS.Palette.agent)
            // iOS: "Audio from this iPhone"; Android names the phone with the Flutter key `phone`.
            Text(if (device) L("nativeAudioFromOmi") else L("phone"), style = style, color = DS.Palette.agent)
        }
    }
}

/** The running time, ticking each second ("4:07"). */
@Composable
private fun Elapsed(sinceMillis: Long, style: TextStyle) {
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(sinceMillis) {
        while (true) {
            now = System.currentTimeMillis()
            delay(1000 - (now - sinceMillis) % 1000)
        }
    }
    Text(livePillElapsed((now - sinceMillis) / 1000.0), style = style.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkSecondary)
}

@Composable
private fun Row(line: LiveSegment, isPartial: Boolean, capture: CaptureStore, speakers: LiveSpeakersStore, onName: () -> Unit) {
    val label = speakers.label(line)
    val hint = L("nativeTapToNameVoice")
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
        Text(
            speakerName(line, label, speakers),
            style = DS.Typography.micro,
            color = if (label.isUser) DS.Palette.agent else DS.Palette.inkTertiary,
            modifier = if (!isPartial && capture.isLive) {
                Modifier.plainButton(onClick = onName).semantics { onClick(label = hint) { onName(); true } }
            } else {
                Modifier
            },
        )
        Text(line.text, style = DS.Typography.body, color = if (isPartial) DS.Palette.inkSecondary else DS.Palette.ink)
    }
}

/** You, the named person, else "Speaker N". */
@Composable
private fun speakerName(line: LiveSegment, label: LiveSpeakersStore.Label, speakers: LiveSpeakersStore): String {
    if (label.isUser) return L("nativeYou")
    val settings = LocalSettingsStore.current
    label.personID?.let { id ->
        (settings.people.firstOrNull { it.id == id }?.name ?: speakers.name(id))?.let { return it }
    }
    return L("speakerWithId", ((line.speakerID ?: 0) + 1).toString())
}

@Composable
private fun Controls(capture: CaptureStore) {
    val enabled = capture.isLive
    Row(
        Modifier.fillMaxWidth()
            .background(DS.Palette.background)
            .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm)
            .navigationBarsPadding()
            .alpha(if (enabled) 1f else 0.4f),
        horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md),
    ) {
        PillSubtle(
            if (capture.isPaused) L("resume") else L("pause"),
            if (capture.isPaused) "play.fill" else "pause.fill",
            enabled,
        ) {
            if (capture.isPaused) capture.perform { resume() } else capture.pause()
        }
        PillSubtle(L("nativeStopRecording"), "stop.fill", enabled) { capture.perform { stop() } }
    }
}

/** `.omiPillSubtle` around a `Label` stretched to its half of the bar. */
@Composable
private fun RowScope.PillSubtle(title: String, systemImage: String, enabled: Boolean, onClick: () -> Unit) {
    Box(
        Modifier.weight(1f)
            .pressable(enabled = enabled, pressedScale = 1f, pressedAlpha = 0.8f, haptic = false, onClick = onClick)
            .background(DS.Palette.cardRaised, CircleShape)
            .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
        contentAlignment = Alignment.Center,
    ) {
        HStack(spacing = DS.Spacing.xs + 2.dp) {
            SFImage(systemImage, size = 13.sp, tint = DS.Palette.ink)
            Text(title, style = TextStyles.subheadline.semibold(), color = DS.Palette.ink)
        }
    }
}
