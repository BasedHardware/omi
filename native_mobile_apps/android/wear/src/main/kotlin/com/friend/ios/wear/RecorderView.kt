package com.friend.ios.wear

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.EaseOut
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.wear.compose.material.CircularProgressIndicator
import androidx.wear.compose.material.Text
import android.os.SystemClock
import kotlinx.coroutines.delay

/**
 * Port of `RecorderView.swift`. One big button: tap to record, tap again to stop. Elapsed time
 * while recording, the Omi's battery on top while it is connected to the phone.
 */
@Composable
fun RecorderView(recorder: WatchRecorder) {
    // A round watch face clips the corners the rectangular Apple Watch has: the top and bottom
    // lines move inward (iOS: 4 pt side padding on a rectangle).
    val round = LocalConfiguration.current.isScreenRound
    Column(
        Modifier.fillMaxSize().background(WatchPalette.background)
            .padding(horizontal = if (round) 14.dp else 4.dp, vertical = if (round) 14.dp else 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        recorder.phone?.omiBattery?.let { battery ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                BatteryGlyph(battery, WatchPalette.secondary)
                Text(stringResource(R.string.watch__omiBattery, battery), style = WatchType.footnote, color = WatchPalette.secondary)
            }
        }
        Spacer(Modifier.weight(1f))
        val stop = stringResource(R.string.watch__accessibility__stopRecording)
        val start = stringResource(R.string.watch__accessibility__startRecording)
        RecordButtonFace(
            phase = recorder.phase,
            enabled = recorder.phase != WatchRecorder.Phase.Starting,
            label = if (recorder.isRecording) stop else start,
            onClick = recorder::toggle,
        )
        Spacer(Modifier.weight(1f))
        Box(
            Modifier.fillMaxWidth().heightIn(min = 40.dp).padding(horizontal = if (round) 10.dp else 0.dp),
            contentAlignment = Alignment.Center,
        ) {
            Status(recorder)
        }
    }
}

@Composable
private fun Status(recorder: WatchRecorder) {
    when (val phase = recorder.phase) {
        is WatchRecorder.Phase.Recording -> {
            var now by remember { mutableLongStateOf(SystemClock.elapsedRealtime()) }
            LaunchedEffect(phase) {
                while (true) {
                    now = SystemClock.elapsedRealtime()
                    delay(1_000 - (now - phase.sinceElapsed) % 1_000)
                }
            }
            val label = stringResource(R.string.watch__accessibility__elapsedRecordingTime)
            Text(
                timerText(now - phase.sinceElapsed), style = WatchType.timer, color = WatchPalette.primary,
                modifier = Modifier.semantics { contentDescription = label },
            )
        }
        WatchRecorder.Phase.Starting ->
            Text(stringResource(R.string.watch__starting), style = WatchType.headline, color = WatchPalette.primary, textAlign = TextAlign.Center)
        WatchRecorder.Phase.Idle -> {
            val notice = recorder.notice
            if (notice != null) {
                Text(stringResource(text(notice)), style = WatchType.footnote, color = WatchPalette.orange, textAlign = TextAlign.Center)
            } else {
                Text(stringResource(R.string.watch__tapToRecord), style = WatchType.headline, color = WatchPalette.primary, textAlign = TextAlign.Center)
            }
        }
    }
}

private fun text(notice: WatchRecorder.Notice): Int = when (notice) {
    WatchRecorder.Notice.MicrophoneDenied -> R.string.watch__error__microphoneDenied
    WatchRecorder.Notice.MicrophoneFailed -> R.string.watch__error__microphoneFailed
    WatchRecorder.Notice.PhoneBusy -> R.string.watch__error__phoneBusy
    WatchRecorder.Notice.PhoneSignedOut -> R.string.watch__error__phoneSignedOut
    WatchRecorder.Notice.PhoneFailed -> R.string.watch__error__phoneFailed
}

/** The level `battery.0/25/50/75/100percent` shows, as `RecorderView.batteryIcon` picks it. */
internal fun batteryFill(level: Int): Float = when {
    level < 13 -> 0f
    level < 38 -> 0.25f
    level < 63 -> 0.5f
    level < 88 -> 0.75f
    else -> 1f
}

/** SF Symbols' `battery.NNpercent` at footnote size: an outline, the cap, the fill. */
@Composable
private fun BatteryGlyph(level: Int, color: Color, height: Dp = 10.dp) {
    val fill = batteryFill(level)
    Canvas(Modifier.size(width = height * 2.2f, height = height)) {
        val stroke = 1.dp.toPx()
        val cap = size.width * 0.07f
        val body = Size(size.width - cap - stroke, size.height - stroke)
        val radius = CornerRadius(size.height * 0.28f)
        drawRoundRect(color, Offset(stroke / 2, stroke / 2), body, radius, style = Stroke(stroke))
        drawRoundRect(
            color, Offset(size.width - cap, size.height * 0.32f), Size(cap, size.height * 0.36f),
            CornerRadius(cap / 2),
        )
        if (fill > 0f) {
            val inset = stroke * 2
            drawRoundRect(
                color, Offset(inset, inset), Size((body.width - inset * 2 + stroke) * fill, size.height - inset * 2),
                CornerRadius(radius.x * 0.6f),
            )
        }
    }
}

@Composable
private fun RecordButtonFace(phase: WatchRecorder.Phase, enabled: Boolean, label: String, onClick: () -> Unit) {
    val isRecording = phase is WatchRecorder.Phase.Recording
    val fill by animateColorAsState(if (isRecording) WatchPalette.red else Color.White, tween(200), label = "fill")
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    Box(
        Modifier.size(104.dp)
            .semantics { contentDescription = label }
            .clickable(interactionSource = interaction, indication = null, enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        if (isRecording) PulsingRing()
        // `.buttonStyle(.plain)`: the face dims while pressed.
        Box(
            Modifier.size(92.dp).alpha(if (pressed) 0.6f else 1f).background(fill, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            AnimatedContent(
                targetState = phase::class,
                transitionSpec = { fadeIn(tween(200)) togetherWith fadeOut(tween(200)) },
                label = "face",
            ) { kind ->
                when (kind) {
                    WatchRecorder.Phase.Idle::class ->
                        Image(painterResource(R.drawable.omi_logo), contentDescription = null, modifier = Modifier.size(44.dp))
                    WatchRecorder.Phase.Starting::class ->
                        CircularProgressIndicator(Modifier.size(24.dp), indicatorColor = Color.Black, trackColor = Color.Transparent, strokeWidth = 2.5.dp)
                    else -> Box(Modifier.size(30.dp).background(Color.White, RoundedCornerShape(6.dp)))
                }
            }
        }
    }
}

/** The ring that grows and fades around the red button (`phaseAnimator`, ease out over 1.2 s). */
@Composable
private fun PulsingRing() {
    val transition = rememberInfiniteTransition(label = "ring")
    val expanded by transition.animateFloat(0f, 1f, infiniteRepeatable(tween(1200, easing = EaseOut), RepeatMode.Reverse), label = "expanded")
    Box(
        Modifier.size(104.dp)
            .scale(1f + 0.12f * expanded)
            .alpha(1f - expanded)
            .border(3.dp, WatchPalette.red.copy(alpha = 0.4f), CircleShape),
    )
}
