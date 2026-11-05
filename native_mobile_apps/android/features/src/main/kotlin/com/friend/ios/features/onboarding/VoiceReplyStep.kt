package com.friend.ios.features.onboarding

import android.content.Context
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import androidx.compose.animation.core.withInfiniteAnimationFrameMillis
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.service.stores.VoicePlaybackStore
import com.friend.ios.service.stores.VoicePlaybackStore.ReplyMode
import kotlin.math.abs
import kotlin.math.sin

/** Where the phone plays sound right now (`AudioRoute`): private listening, or the speaker. */
internal sealed interface AudioRoute {
    data class Headphones(val name: String?) : AudioRoute
    data object Speaker : AudioRoute

    companion object {
        private val private = setOf(
            AudioDeviceInfo.TYPE_WIRED_HEADPHONES, AudioDeviceInfo.TYPE_WIRED_HEADSET, AudioDeviceInfo.TYPE_BLUETOOTH_A2DP,
            AudioDeviceInfo.TYPE_USB_HEADSET, AudioDeviceInfo.TYPE_BLE_HEADSET,
        )

        fun current(context: Context): AudioRoute {
            val manager = context.getSystemService(AudioManager::class.java) ?: return Speaker
            val device = manager.getDevices(AudioManager.GET_DEVICES_OUTPUTS).firstOrNull { it.type in private } ?: return Speaker
            return Headphones(device.productName?.toString()?.takeIf { it.isNotBlank() })
        }
    }
}

/**
 * Port of `VoiceReplyStep.swift`. "Hear Omi's answers" (Flutter `voice_reply_step`): a preview of
 * the last answer (or a sample) in the chosen assistant voice, and when answers are spoken: off,
 * headphones only, always (the same setting as Settings > Assistant > Spoken replies); one line
 * says what happens right now.
 */
@Composable
internal fun VoiceReplyStep(
    mode: ReplyMode,
    /** The answer from the ask step, when there was one. */
    lastAnswer: String?,
    voice: VoicePlaybackStore?,
    onChoose: (ReplyMode) -> Unit,
    onContinue: () -> Unit,
) {
    val context = LocalContext.current
    var output by remember { mutableStateOf(AudioRoute.current(context)) }
    val playing = voice?.playingID == VoicePlaybackStore.REPLY_PREVIEW_ID
    val sample = L("deviceOnboardingVoiceReplySample")
    OnboardingLayout(
        kicker = L("nativeKickerYourOmi"),
        title = L("deviceOnboardingVoiceReplyTitle"),
        subtitle = L("nativeVoiceReplyShort"),
        button = StepButton(L("continueButton"), action = onContinue),
    ) {
        Preview(voice, playing, lastAnswer, output, sample)
        RowList(
            listOf(
                { ChoiceRow("speaker.slash", L("nativeSpokenOff"), mode == ReplyMode.Off) { onChoose(ReplyMode.Off) } },
                { ChoiceRow("headphones", L("nativeSpokenHeadphones"), mode == ReplyMode.HeadphonesOnly) { onChoose(ReplyMode.HeadphonesOnly) } },
                { ChoiceRow("speaker.wave.2", L("nativeSpokenAlways"), mode == ReplyMode.Always) { onChoose(ReplyMode.Always) } },
            ),
        )
        Status(mode, output)
    }
    // `AVAudioSession.routeChangeNotification`.
    DisposableEffect(context) {
        val manager = context.getSystemService(AudioManager::class.java)
        val callback = object : AudioDeviceCallback() {
            override fun onAudioDevicesAdded(addedDevices: Array<out AudioDeviceInfo>?) { output = AudioRoute.current(context) }
            override fun onAudioDevicesRemoved(removedDevices: Array<out AudioDeviceInfo>?) { output = AudioRoute.current(context) }
        }
        manager?.registerAudioDeviceCallback(callback, Handler(Looper.getMainLooper()))
        onDispose {
            manager?.unregisterAudioDeviceCallback(callback)
            if (voice?.playingID == VoicePlaybackStore.REPLY_PREVIEW_ID) voice.stop()
        }
    }
    // --ez omiPreviewReply true: plays the preview on arrival (check of the audio path).
    LaunchedEffect(Unit) { if (DebugLaunch.flag("omiPreviewReply")) voice?.previewReply(lastAnswer ?: sample) }
}

@Composable
private fun Preview(voice: VoicePlaybackStore?, playing: Boolean, lastAnswer: String?, output: AudioRoute, sample: String) {
    val haptics = rememberHaptics()
    val title = if (playing) {
        if (lastAnswer == null) L("nativeVoiceReplyPreviewPlayingSample") else L("deviceOnboardingVoiceReplyPreviewPlaying")
    } else {
        if (lastAnswer == null) L("nativeVoiceReplyPreviewSample") else L("nativeVoiceReplyPreviewLast")
    }
    val routeLine = when (output) {
        is AudioRoute.Headphones -> L("deviceOnboardingVoiceReplyPreviewThroughDevice", output.name ?: L("deviceOnboardingVoiceReplyGenericHeadphones"))
        AudioRoute.Speaker -> L("deviceOnboardingVoiceReplyPreviewThroughPhoneSpeaker")
    }
    val loading = voice?.isLoading == true
    val label = if (playing) L("nativeStopReading") else title
    HStack(
        Modifier.padding(horizontal = DS.Spacing.gutter).onboardingCard()
            .plainButton { haptics.tap(); voice?.previewReply(lastAnswer ?: sample) }
            .semantics(mergeDescendants = true) { contentDescription = label },
        spacing = DS.Spacing.md,
    ) {
        Box(Modifier.size(48.dp).background(DS.Palette.ink, CircleShape), contentAlignment = Alignment.Center) {
            if (playing && loading) {
                OmiProgress(tint = DS.Palette.onAccent)
            } else {
                SFImage(if (playing) "stop.fill" else "play.fill", size = 17.sp, weight = FontWeight.Bold, tint = DS.Palette.onAccent)
            }
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
            Text(title, style = TextStyles.body.semibold(), color = DS.Palette.ink)
            Text(routeLine, style = TextStyles.footnote, color = DS.Palette.inkSecondary)
            SpeakingBars(active = playing && !loading, modifier = Modifier.padding(top = DS.Spacing.xxs).height(16.dp))
        }
    }
}

/** What the chosen mode does with the headphones connected (or not) right now. */
@Composable
private fun Status(mode: ReplyMode, output: AudioRoute) {
    val headphones = (output as? AudioRoute.Headphones)?.let { it.name ?: L("deviceOnboardingVoiceReplyGenericHeadphones") }
    val line = when (mode) {
        ReplyMode.Off -> StatusLine(L("deviceOnboardingVoiceReplyStatusOff"), "speaker.slash", DS.Palette.inkSecondary)
        ReplyMode.HeadphonesOnly -> if (headphones != null) {
            StatusLine(L("deviceOnboardingVoiceReplyStatusHeadphonesConnected", headphones), "headphones", DS.Palette.success)
        } else {
            StatusLine(L("nativeVoiceReplyNoHeadphones"), "headphones", DS.Palette.warning)
        }
        ReplyMode.Always -> if (headphones != null) {
            StatusLine(L("nativeVoiceReplyAlwaysThrough", headphones), "headphones", DS.Palette.success)
        } else {
            StatusLine(L("deviceOnboardingVoiceReplyStatusAlwaysSpeaker"), "speaker.wave.2", DS.Palette.warning)
        }
    }
    line.View(Modifier.padding(horizontal = DS.Spacing.gutter))
}

/** Bars that move while Omi speaks, flat and faint when it does not. */
@Composable
private fun SpeakingBars(active: Boolean, modifier: Modifier = Modifier) {
    var phase by remember { mutableFloatStateOf(0f) }
    LaunchedEffect(active) {
        if (!active) return@LaunchedEffect
        while (true) withInfiniteAnimationFrameMillis { phase = it / 1000f * 6f }
    }
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = Alignment.CenterVertically) {
        for (index in 0 until 18) {
            val base = if (active) 0.3 + ((index * 7) % 11) / 16.0 else 0.22
            val pulse = if (active) 0.55 + 0.45 * abs(sin(phase + index * 0.72)) else 1.0
            Box(
                Modifier.weight(1f).height(maxOf(3.0, 16 * base * pulse).dp)
                    .background(DS.Palette.ink.copy(alpha = if (active) 1f else 0.24f), CircleShape),
            )
        }
    }
}
