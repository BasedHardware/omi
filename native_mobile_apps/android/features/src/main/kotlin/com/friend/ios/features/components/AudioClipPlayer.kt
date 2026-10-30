package com.friend.ios.features.components

import android.content.Context
import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Port of `AudioClipPlayer.swift`: plays one short voice clip at a time: WAV bytes the backend
 * sent (speaker prompts, earlier voice matches) or a signed sample URL (a person's voice samples;
 * no auth headers needed). Media3 stands in for `AVAudioPlayer` / `AVPlayer`.
 */
@Stable
class AudioClipPlayer(private val context: Context) {
    /** What is playing now, by the caller's id. */
    var playingID: String? by mutableStateOf(null)
        private set
    /** The clip the caller is waiting for (download in flight). */
    var loadingID: String? by mutableStateOf(null)
        private set
    private var player: ExoPlayer? = null

    /** Starts [id], or stops it when it is already playing. [load] fetches the WAV; false when nothing could play. */
    suspend fun toggle(id: String, load: suspend () -> ByteArray?): Boolean {
        if (playingID == id || loadingID == id) {
            stop()
            return true
        }
        stop()
        loadingID = id
        val data = load()
        if (loadingID != id) return true
        loadingID = null
        data ?: return false
        val file = withContext(Dispatchers.IO) {
            runCatching { File(context.cacheDir, "clip-${id.hashCode()}.wav").apply { writeBytes(data) } }.getOrNull()
        } ?: return false
        start(id, Uri.fromFile(file))
        return playingID != null
    }

    /** Streams a remote clip, or stops it when it is already playing. */
    fun toggle(id: String, url: String) {
        if (playingID == id) {
            stop()
            return
        }
        stop()
        start(id, Uri.parse(url))
    }

    fun stop() {
        player?.release()
        player = null
        playingID = null
        loadingID = null
    }

    private fun start(id: String, uri: Uri) {
        val exo = ExoPlayer.Builder(context)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_SPEECH).build(), true)
            .build()
        exo.addListener(
            object : Player.Listener {
                override fun onPlaybackStateChanged(state: Int) {
                    if (state == Player.STATE_ENDED && player === exo) stop()
                }

                override fun onPlayerError(error: PlaybackException) {
                    if (player === exo) stop()
                }
            },
        )
        exo.setMediaItem(MediaItem.fromUri(uri))
        exo.prepare()
        exo.play()
        player = exo
        playingID = id
    }
}

/** One player per screen, released when the screen goes away (`.onDisappear { player.stop() }`). */
@Composable
fun rememberAudioClipPlayer(): AudioClipPlayer {
    val context = LocalContext.current.applicationContext
    val player = remember { AudioClipPlayer(context) }
    DisposableEffect(player) { onDispose { player.stop() } }
    return player
}
