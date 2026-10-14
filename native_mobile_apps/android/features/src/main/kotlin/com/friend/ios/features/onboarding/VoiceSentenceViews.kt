package com.friend.ios.features.onboarding

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.semibold
import com.friend.ios.service.stores.VoiceIntroStore
import com.friend.ios.service.voice.GapSentence

// The voice step: its progress steps, the gap sentence filling in as it is said,
// and the quiet listening line under it.

/** One step per sentence: finished ones full, the current one filling as it is said. */
@Composable
internal fun SentenceSteps(done: Int, total: Int, current: Double, needsMore: Boolean) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
        for (index in 0 until total) {
            val fill = when {
                index < done || needsMore -> 1f
                // The current step stops short of full until the sentence is really done.
                index == done -> minOf(0.9, current).toFloat()
                else -> 0f
            }
            val animated by animateFloatAsState(fill, tween(if (index < done) 350 else 250), label = "sentence-step")
            val color = if (index < done) DS.Palette.success else DS.Palette.agent
            BoxWithConstraints(Modifier.weight(1f).height(4.dp).background(DS.Palette.ink.copy(alpha = 0.1f), CircleShape)) {
                Box(Modifier.width(maxWidth * animated).height(4.dp).background(color, CircleShape))
            }
        }
    }
}

/**
 * The sentence to say, filling in as it is said: fixed words turn from faint to solid when
 * heard, the gaps fill with the user's own words.
 */
@Composable
internal fun GapSentenceText(match: GapSentence.Match) {
    val style = DS.Typography.title
    FlowLayout(7.dp) {
        match.pieces.forEach { piece ->
            when (piece) {
                is GapSentence.Match.Piece.Word ->
                    Text(piece.text, style = style, color = if (piece.heard) DS.Palette.ink else DS.Palette.ink.copy(alpha = 0.45f))
                is GapSentence.Match.Piece.Blank ->
                    if (piece.text.isEmpty()) {
                        Box(Modifier.padding(top = 26.dp).width(64.dp).height(2.dp).background(DS.Palette.ink.copy(alpha = 0.18f), CircleShape))
                    } else {
                        piece.text.split(" ").filter { it.isNotEmpty() }.forEach { word ->
                            Column(Modifier.width(IntrinsicSize.Max).padding(bottom = 3.dp)) {
                                Text(word, style = style, color = DS.Palette.agent)
                                Box(Modifier.fillMaxWidth().height(2.dp).background(DS.Palette.agent.copy(alpha = 0.5f), CircleShape))
                            }
                        }
                    }
            }
        }
    }
}

/**
 * Where the audio comes from and the input level, in one quiet line. The dot is still: red
 * while listening, gray otherwise.
 */
@Composable
internal fun ListeningLine(voice: VoiceIntroStore) {
    HStack(spacing = DS.Spacing.md) {
        HStack(spacing = DS.Spacing.sm) {
            Box(Modifier.size(7.dp).background(if (voice.isListening) DS.Palette.live else DS.Palette.inkTertiary, CircleShape))
            Text(
                if (voice.isListening) L("nativeListening") else L("nativeConnecting"),
                style = TextStyles.footnote.semibold(), color = DS.Palette.inkSecondary, maxLines = 1,
            )
        }
        LevelBars(if (voice.isListening) voice.level else 0f, height = 16.dp, modifier = Modifier.weight(1f))
        HStack(spacing = DS.Spacing.xs) {
            val device = voice.source == VoiceIntroStore.Source.Device
            SFImage(if (device) "circle.circle" else "iphone", size = 13.sp, tint = DS.Palette.inkTertiary)
            Text(if (device) L("nativeSourceOmi") else L("nativeSourceIphone"), style = TextStyles.footnote, color = DS.Palette.inkTertiary, maxLines = 1)
        }
    }
}

/** A row of bars that follows the input level, newest on the right. */
@Composable
internal fun LevelBars(level: Float, height: Dp = 28.dp, modifier: Modifier = Modifier) {
    var history by remember { mutableStateOf(List(28) { 0f }) }
    LaunchedEffect(level) { history = history.drop(1) + level }
    Row(modifier.height(height), horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        history.forEach { value ->
            val amount = minOf(1f, value * 4)
            val barHeight by animateFloatAsState(maxOf(2f, amount * height.value), tween(80), label = "level-bar")
            Box(Modifier.weight(1f).height(barHeight.dp).background(DS.Palette.ink.copy(alpha = 0.2f + amount * 0.6f), CircleShape))
        }
    }
}
