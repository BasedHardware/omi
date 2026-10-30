package com.friend.ios.features.conversations

import android.content.Context
import android.net.Uri
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.setProgress
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.friend.ios.design.DS
import com.friend.ios.design.HStack
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.omiCard
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.service.stores.ConversationDetailStore
import kotlinx.coroutines.delay
import java.io.File
import java.util.Locale

/** Port of `AudioPlayerBar.swift`: the recording at the top of the transcript: play/pause, scrub, speed, share. */
@Composable
fun AudioPlayerBar(store: ConversationDetailStore, onShare: () -> Unit) {
    val context = LocalContext.current
    val playback = remember { AudioPlayback(context.applicationContext) }
    LaunchedEffect(Unit) { store.loadAudio() }
    DisposableEffect(Unit) { onDispose { playback.stop() } }
    HStack(
        Modifier
            .omiCard(padding = DS.Spacing.xs)
            .heightIn(min = 52.dp)
            .padding(horizontal = DS.Spacing.md),
        spacing = DS.Spacing.md,
    ) {
        when (val audio = store.audio) {
            ConversationDetailStore.AudioState.Idle, ConversationDetailStore.AudioState.Preparing -> {
                OmiProgress(Modifier.size(18.dp))
                Text(L("nativeAudioPreparing"), style = DS.Typography.callout, color = DS.Palette.inkSecondary, modifier = Modifier.weight(1f))
            }
            ConversationDetailStore.AudioState.Unavailable -> {
                SFImage("waveform.slash", tint = DS.Palette.inkTertiary)
                Text(L("nativeAudioUnavailable"), style = DS.Typography.callout, color = DS.Palette.inkSecondary, modifier = Modifier.weight(1f))
            }
            is ConversationDetailStore.AudioState.Ready -> {
                LaunchedEffect(audio.url) { playback.load(audio.url, audio.duration) }
                Controls(playback, onShare, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun Controls(playback: AudioPlayback, onShare: () -> Unit, modifier: Modifier) {
    val haptics = rememberHaptics()
    var scrubbing by remember { mutableStateOf<Double?>(null) }
    // Position and duration, a few times a second while it plays.
    LaunchedEffect(playback.isPlaying) {
        while (playback.isPlaying) {
            playback.tick()
            delay(250)
        }
        playback.tick()
    }
    HStack(modifier, spacing = DS.Spacing.sm) {
        Box(
            Modifier
                .size(36.dp)
                .background(DS.Palette.accent, CircleShape)
                .plainButton {
                    haptics.tap()
                    if (playback.isPlaying) playback.pause() else playback.play()
                },
            contentAlignment = Alignment.Center,
        ) {
            SFImage(
                if (playback.isPlaying) "pause.fill" else "play.fill", size = 16.sp, weight = FontWeight.SemiBold, tint = DS.Palette.onAccent,
                contentDescription = if (playback.isPlaying) L("nativePause") else L("nativePlay"),
            )
        }
        Scrubber(
            value = scrubbing ?: playback.position,
            range = maxOf(playback.duration, 1.0),
            onChange = { scrubbing = it },
            onCommit = {
                scrubbing?.let(playback::seek)
                scrubbing = null
            },
            label = L("nativePlaybackPosition"),
            modifier = Modifier.weight(1f),
        )
        Text(
            time(scrubbing ?: playback.position),
            style = DS.Typography.micro.copy(fontFeatureSettings = "tnum"),
            color = DS.Palette.inkSecondary,
            textAlign = TextAlign.End,
            modifier = Modifier.widthIn(min = 36.dp),
        )
        OmiMenu(
            listOf(
                MenuSection(
                    items = listOf(0.75f, 1f, 1.25f, 1.5f, 2f).map { value ->
                        MenuItem(rate(value), if (playback.rate == value) "checkmark" else null) { playback.rate = value }
                    },
                ),
            ),
            contentDescription = L("nativePlaybackSpeed"),
        ) {
            Text(
                rate(playback.rate),
                style = DS.Typography.micro,
                color = DS.Palette.ink,
                modifier = Modifier.background(DS.Palette.cardRaised, CircleShape).padding(horizontal = DS.Spacing.sm, vertical = DS.Spacing.xs),
            )
        }
        SFImage("square.and.arrow.up", Modifier.plainButton(onClick = onShare), tint = DS.Palette.inkSecondary, contentDescription = L("shareAudio"))
    }
}

/** `Slider` in the iOS look: a thin track, the played part in agent blue, a round white thumb. */
@Composable
private fun Scrubber(value: Double, range: Double, onChange: (Double) -> Unit, onCommit: () -> Unit, label: String, modifier: Modifier) {
    var width by remember { mutableFloatStateOf(1f) }
    val fraction = (value / range).coerceIn(0.0, 1.0).toFloat()
    val track = DS.Palette.fill
    val played = DS.Palette.agent
    Box(
        modifier
            .height(28.dp)
            // A slider for TalkBack: its position, and swipes up or down seek.
            .semantics {
                contentDescription = label
                progressBarRangeInfo = ProgressBarRangeInfo(value.toFloat(), 0f..range.toFloat())
                setProgress { target ->
                    onChange(target.toDouble().coerceIn(0.0, range))
                    onCommit()
                    true
                }
            }
            .pointerInput(range) {
                detectTapGestures { offset ->
                    onChange((offset.x / size.width).coerceIn(0f, 1f) * range)
                    onCommit()
                }
            }
            .pointerInput(range) {
                detectHorizontalDragGestures(
                    onDragEnd = onCommit,
                    onDragCancel = onCommit,
                ) { change, _ -> onChange((change.position.x / size.width).coerceIn(0f, 1f).toDouble() * range) }
            },
        contentAlignment = Alignment.CenterStart,
    ) {
        Canvas(Modifier.fillMaxWidth().height(4.dp)) {
            width = size.width
            drawRoundRect(track, cornerRadius = CornerRadius(size.height / 2))
            drawRoundRect(played, size = Size(size.width * fraction, size.height), cornerRadius = CornerRadius(size.height / 2))
        }
        val thumb = 22.dp
        Box(
            Modifier
                .padding(start = with(androidx.compose.ui.platform.LocalDensity.current) { ((width * fraction).toDp() - thumb / 2).coerceAtLeast(0.dp) })
                .size(thumb)
                .shadow(2.dp, CircleShape)
                .background(Color.White, CircleShape),
        )
    }
}

internal fun time(seconds: Double): String {
    val total = Math.floor(seconds).toInt()
    return String.format(Locale.ROOT, "%d:%02d", total / 60, total % 60)
}

internal fun rate(rate: Float): String =
    if (rate == Math.round(rate).toFloat()) "${rate.toInt()}×" else "${String.format(Locale.getDefault(), "%.2f", rate).trimEnd('0').trimEnd('.', ',')}×"

/** Port of `AudioPlayback` (`AVPlayer`): Media3 for one signed URL or local file, publishing position and play state. */
@Stable
class AudioPlayback(private val context: Context) {
    var isPlaying by mutableStateOf(false)
        private set
    var position by mutableStateOf(0.0)
        private set
    var duration by mutableStateOf(0.0)
        private set
    private var rateState by mutableFloatStateOf(1f)
    var rate: Float
        get() = rateState
        set(value) {
            rateState = value
            player?.playbackParameters = PlaybackParameters(value)
        }
    private var player: ExoPlayer? = null
    private var loadedURL: String? = null

    fun load(url: String, duration: Double?) {
        if (url == loadedURL) return
        stop()
        loadedURL = url
        this.duration = duration ?: 0.0
        val exo = ExoPlayer.Builder(context)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_SPEECH).build(), true)
            .build()
        exo.addListener(
            object : Player.Listener {
                override fun onPlaybackStateChanged(state: Int) {
                    if (state == Player.STATE_ENDED) {
                        isPlaying = false
                        exo.pause()
                        exo.seekTo(0)
                        position = 0.0
                    }
                    tick()
                }
            },
        )
        val uri = if (url.startsWith("http")) Uri.parse(url) else Uri.fromFile(File(url))
        exo.setMediaItem(MediaItem.fromUri(uri))
        exo.prepare()
        player = exo
    }

    fun play() {
        val exo = player ?: return
        exo.playbackParameters = PlaybackParameters(rate)
        exo.play()
        isPlaying = true
    }

    fun pause() {
        player?.pause()
        isPlaying = false
    }

    /** Releases the player (the transcript tab closed); [load] starts over. */
    fun stop() {
        pause()
        player?.release()
        player = null
        loadedURL = null
    }

    fun seek(seconds: Double) {
        position = seconds
        player?.seekTo((seconds * 1000).toLong())
    }

    internal fun tick() {
        val exo = player ?: return
        position = exo.currentPosition / 1000.0
        val known = exo.duration
        if (known != C.TIME_UNSET && known > 0) duration = known / 1000.0
    }
}
