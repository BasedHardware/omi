package com.friend.ios.features.settings

import android.text.format.DateFormat
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiPickerRow
import com.friend.ios.features.components.OmiToggleRow
import com.friend.ios.service.LocalSettingsStore
import kotlinx.coroutines.launch
import java.time.LocalTime
import java.time.format.DateTimeFormatter

/**
 * Port of `AssistantScreen.swift`. How Omi helps > Assistant: how Omi answers out loud and in which
 * voice, how often it reaches out with tips, and the daily recap. The one place for tips and the
 * recap (Notifications links here).
 */
@Composable
fun AssistantScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val navigator = LocalSettingsNavigator.current
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { settings.loadNotifications() }
    LaunchedEffect(Unit) { settings.loadVoices() }
    val spoken = listOf(L("nativeSpokenOff"), L("nativeSpokenHeadphones"), L("nativeSpokenAlways"))
    val frequencies = (0 until 6).map { frequencyTitle(it) }
    val hours = (0 until 24).map { hourLabel(it) }
    val spokenTitle = L("nativeSpokenReplies")
    val voiceTitle = L("nativeAssistantVoice")
    val proactiveTitle = L("nativeProactiveNotifications")
    val recapTitle = L("nativeDailyRecap")
    val timeTitle = L("nativeDailySummaryTime")
    val selectedVoiceName = settings.voices.firstOrNull { it.id == settings.selectedVoice }?.name
    val icon = OmiListMetrics.iconSeparatorInset
    SettingsListPage(L("nativeAssistant"), onBack) {
        section {
            row(separatorInset = icon) {
                OmiPickerRow((0..2).toList(), settings.voiceResponseMode, { spoken[it] }, { settings.voiceResponseMode = it }) {
                    SettingsRowLabel(spokenTitle, "speaker.wave.2")
                }
            }
            row(onClick = { navigator.push(SettingsTopic.VoicePicker) }, chevron = true, separatorInset = icon) {
                SettingsRowLabel(voiceTitle, "person.wave.2", value = selectedVoiceName)
            }
        }
        section(footer = frequencyDescription(settings.notificationFrequency)) {
            // Flutter's six levels (`mentor-notification-settings` 0...5; 3 is the backend default).
            row(separatorInset = icon) {
                OmiPickerRow((0 until 6).toList(), settings.notificationFrequency, { frequencies[it] }, { scope.launch { settings.setNotificationFrequency(it) } }) {
                    SettingsRowLabel(proactiveTitle, "lightbulb")
                }
            }
        }
        section(footer = L("nativeDailySummaryFooter")) {
            row(separatorInset = icon) {
                OmiToggleRow(settings.dailySummaryEnabled, { value -> scope.launch { settings.setDailySummary(value, settings.dailySummaryHour) } }) {
                    SettingsRowLabel(recapTitle, "sun.horizon")
                }
            }
            if (settings.dailySummaryEnabled) {
                row(separatorInset = icon) {
                    OmiPickerRow((0 until 24).toList(), settings.dailySummaryHour, { hours[it] }, { hour -> scope.launch { settings.setDailySummary(true, hour) } }) {
                        SettingsRowLabel(timeTitle, "clock")
                    }
                }
            }
        }
    }
}

/** `AssistantScreen.hourLabel`: the hour in the phone's time format ("10 PM", "22:00"). */
@Composable
fun hourLabel(hour: Int): String {
    val context = LocalContext.current
    val pattern = if (DateFormat.is24HourFormat(context)) "HH:mm" else "h:mm a"
    return LocalTime.of(hour, 0).format(DateTimeFormatter.ofPattern(pattern))
}

@Composable
fun frequencyTitle(level: Int): String = when (level) {
    1 -> L("frequencyMinimal")
    2 -> L("frequencyLow")
    3 -> L("frequencyBalanced")
    4 -> L("frequencyHigh")
    5 -> L("frequencyMaximum")
    else -> L("frequencyOff")
}

@Composable
fun frequencyDescription(level: Int): String = when (level) {
    1 -> L("frequencyDescMinimal")
    2 -> L("frequencyDescLow")
    3 -> L("frequencyDescBalanced")
    4 -> L("frequencyDescHigh")
    5 -> L("nativeFrequencyDescMaximum")
    else -> L("nativeProactiveFooter")
}

/** Assistant > Voice: every voice with a play button; tapping a row picks it. */
@Composable
fun VoicePickerScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val playback = com.friend.ios.service.LocalVoicePlaybackStore.current
    LaunchedEffect(Unit) { settings.loadVoices() }
    androidx.compose.runtime.DisposableEffect(Unit) { onDispose { playback?.stop() } }
    SettingsListPage(L("nativeAssistantVoice"), onBack) {
        section(footer = if (playback?.previewFailed == true) L("nativeVoicePreviewFailed") else L("nativeVoicePickerFooter")) {
            if (settings.voices.isEmpty()) {
                row { Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { OmiProgress() } }
            }
            settings.voices.forEach { voice ->
                row(key = voice.id, separatorInset = 58.dp) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                        PreviewButton(voice.id, playback)
                        Row(
                            Modifier.weight(1f).plainButton {
                                haptics.selection()
                                scope.launch { settings.selectVoice(voice.id) }
                            },
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(voice.name, style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.weight(1f))
                            if (settings.selectedVoice == voice.id) SFImage("checkmark", weight = FontWeight.SemiBold, tint = DS.Palette.ink)
                        }
                    }
                }
            }
        }
    }
}

/** Plays a sample in that voice (the backend voice only, no system stand-in), or stops it. */
@Composable
private fun PreviewButton(voiceID: String, playback: com.friend.ios.service.stores.VoicePlaybackStore?) {
    val haptics = rememberHaptics()
    val playing = playback?.playingID == "preview:" + voiceID
    val sample = L("voicePreviewSample")
    val label = if (playing) L("nativeStopReading") else L("nativePlayVoicePreview")
    Box(
        Modifier
            .size(30.dp)
            .semantics { contentDescription = label }
            .plainButton {
                haptics.selection()
                playback?.preview(voiceID, sample)
            }
            .then(if (playing) Modifier.background(DS.Palette.ink, CircleShape) else Modifier.border(1.dp, DS.Palette.hairline, CircleShape)),
        contentAlignment = Alignment.Center,
    ) {
        if (playing && playback?.isLoading == true) {
            OmiProgress(Modifier.size(16.dp), tint = DS.Palette.onAccent)
        } else {
            SFImage(if (playing) "stop.fill" else "play.fill", size = 11.sp, weight = FontWeight.SemiBold, tint = if (playing) DS.Palette.onAccent else DS.Palette.ink)
        }
    }
}
