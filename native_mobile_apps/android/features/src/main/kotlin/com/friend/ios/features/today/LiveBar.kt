package com.friend.ios.features.today

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.OmiLivePill
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.medium
import com.friend.ios.design.omiSurface
import com.friend.ios.design.plainButton
import com.friend.ios.service.LocalCaptureStore
import com.friend.ios.service.stores.CaptureStore

/**
 * Port of `LiveBar` (`TodayScreen.swift`): Omi's live pill: where the audio comes from, the newest
 * words, a running timer and stop. Tapping it opens the full live transcript.
 */
@Composable
fun LiveBar(modifier: Modifier = Modifier) {
    val capture = LocalCaptureStore.current
    var showsTranscript by remember { mutableStateOf(false) }
    Box(modifier.plainButton { if (capture.isLive) showsTranscript = true }) {
        when (val phase = capture.phase) {
            CaptureStore.Phase.Finishing -> Quiet {
                OmiProgress(Modifier.size(16.dp), tint = DS.Palette.agent)
                Text(L("nativeSavingConversation"), style = DS.Typography.callout.medium(), color = DS.Palette.ink)
            }
            is CaptureStore.Phase.Failed -> Quiet {
                SFImage("exclamationmark.triangle.fill", tint = DS.Palette.warning)
                Text(liveBarMessage(phase.reason), style = DS.Typography.callout, color = DS.Palette.ink, maxLines = 2)
            }
            else -> OmiLivePill(
                sinceMillis = (phase as? CaptureStore.Phase.Live)?.sinceMillis?.takeUnless { capture.isPaused },
                title = liveBarTitle(capture),
                symbol = liveBarSymbol(capture.source),
            ) {
                if (capture.isLive) StopButton(capture)
            }
        }
    }
    if (showsTranscript) LiveTranscriptSheet(onDismiss = { showsTranscript = false })
}

@Composable
private fun StopButton(capture: CaptureStore) {
    val label = L("nativeStopRecording")
    Box(
        Modifier.size(32.dp)
            .semantics { contentDescription = label }
            .plainButton { capture.perform { stop() } }
            .background(DS.Palette.cardRaised, CircleShape),
        contentAlignment = androidx.compose.ui.Alignment.Center,
    ) {
        SFImage("stop.fill", size = 11.sp, weight = FontWeight.Bold, tint = DS.Palette.ink)
    }
}

@Composable
private fun Quiet(content: @Composable androidx.compose.foundation.layout.RowScope.() -> Unit) {
    HStack(
        Modifier.heightIn(min = 48.dp).omiSurface(CircleShape).padding(horizontal = DS.Spacing.lg),
        spacing = DS.Spacing.sm,
    ) {
        content()
        Spacer(Modifier.weight(1f))
    }
}

/** The newest words (the phone previews them before the server confirms), else what is going on. */
@Composable
private fun liveBarTitle(capture: CaptureStore): String {
    if (capture.isPaused) return L("paused")
    val words = capture.liveWords
    if (words.isNotEmpty()) return words.takeLast(80)
    if (capture.isBuffering) return L("nativeRecordingToPhone")
    return "${L("nativeListeningPhone")} · ${liveBarTag(capture.source)}"
}

/** The pendant for an Omi; the phone and the watch get their symbol. */
private fun liveBarSymbol(source: CaptureStore.Source?): String? = when (source) {
    CaptureStore.Source.Device -> null
    CaptureStore.Source.Watch -> "applewatch"
    CaptureStore.Source.Phone, null -> "iphone"
}

/** iOS says "iPhone"; Android says "Phone" (the Flutter key `phone`). */
@Composable
internal fun liveBarTag(source: CaptureStore.Source?): String = when (source) {
    CaptureStore.Source.Device -> "Omi"
    CaptureStore.Source.Watch -> "Apple Watch"
    CaptureStore.Source.Phone, null -> L("phone")
}

@Composable
internal fun liveBarMessage(reason: String): String = when (reason) {
    "microphone" -> L("nativeMicPermissionNeeded")
    "speech" -> L("nativeSpeechPermissionNeeded")
    "speechUnavailable" -> L("nativeSpeechUnavailable")
    else -> L("nativeCaptureFailed")
}
