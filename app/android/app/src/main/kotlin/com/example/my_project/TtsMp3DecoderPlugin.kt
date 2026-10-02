package com.friend.ios

import android.os.Handler
import android.os.Looper
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.os.Build
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.Executors
import kotlin.concurrent.thread

object TtsMp3DecoderPlugin {
    init {
        System.loadLibrary("phonemicopus")
    }

    private external fun decodeMp3(bytes: ByteArray): ByteArray?

    fun register(flutterEngine: FlutterEngine) {
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.omi/tts_mp3_decoder",
        ).setMethodCallHandler { call, result ->
            if (call.method != "decode") {
                result.notImplemented()
                return@setMethodCallHandler
            }
            val bytes = call.argument<ByteArray>("bytes")
            if (bytes == null) {
                result.error("invalid_mp3", "decode requires MP3 bytes", null)
                return@setMethodCallHandler
            }
            thread(name = "omi-tts-mp3-decode") {
                val decoded = decodeMp3(bytes)
                val decodedResult = runCatching {
                    if (decoded == null || decoded.size < 8) {
                        error("MP3 prefix has no complete audio frame")
                    }
                    val header = ByteBuffer.wrap(decoded, 0, 8).order(ByteOrder.LITTLE_ENDIAN)
                    mapOf(
                        "channels" to header.int,
                        "sample_rate" to header.int,
                        "pcm" to decoded.copyOfRange(8, decoded.size),
                    )
                }
                Handler(Looper.getMainLooper()).post {
                    decodedResult.onSuccess { value ->
                        result.success(value)
                    }.onFailure { error ->
                        result.error("decode_failed", error.message, null)
                    }
                }
            }
        }
    }
}

object TtsPcmPlayerPlugin {
    private val mainHandler = Handler(Looper.getMainLooper())
    private val executor = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "omi-tts-pcm-player")
    }

    @Volatile private var track: AudioTrack? = null
    @Volatile private var generation = 0
    private var channels = 0
    private var writtenFrames = 0L

    fun register(flutterEngine: FlutterEngine) {
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "com.omi/tts_pcm_player",
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "start" -> {
                    val requestedChannels = call.argument<Int>("channels")
                    val sampleRate = call.argument<Int>("sample_rate")
                    if (requestedChannels == null || sampleRate == null || requestedChannels !in 1..2) {
                        result.error("invalid_pcm", "Invalid PCM geometry", null)
                        return@setMethodCallHandler
                    }
                    executor.execute {
                        runCatching {
                            stopNow()
                            val channelMask = if (requestedChannels == 1) {
                                AudioFormat.CHANNEL_OUT_MONO
                            } else {
                                AudioFormat.CHANNEL_OUT_STEREO
                            }
                            val minimum = AudioTrack.getMinBufferSize(
                                sampleRate,
                                channelMask,
                                AudioFormat.ENCODING_PCM_16BIT,
                            )
                            val attributes = AudioAttributes.Builder()
                                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                                .setUsage(
                                    if (Build.VERSION.SDK_INT >= 26) {
                                        AudioAttributes.USAGE_ASSISTANT
                                    } else {
                                        AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE
                                    },
                                )
                                .build()
                            val format = AudioFormat.Builder()
                                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                                .setSampleRate(sampleRate)
                                .setChannelMask(channelMask)
                                .build()
                            val player = AudioTrack(
                                attributes,
                                format,
                                maxOf(minimum, 16 * 1024),
                                AudioTrack.MODE_STREAM,
                                AudioManager.AUDIO_SESSION_ID_GENERATE,
                            )
                            channels = requestedChannels
                            writtenFrames = 0
                            generation++
                            track = player
                            player.play()
                        }.fold(
                            onSuccess = { mainHandler.post { result.success(null) } },
                            onFailure = { error ->
                                mainHandler.post { result.error("pcm_start_failed", error.message, null) }
                            },
                        )
                    }
                }
                "feed" -> {
                    val pcm = call.argument<ByteArray>("pcm")
                    if (pcm == null) {
                        result.error("invalid_pcm", "feed requires PCM bytes", null)
                        return@setMethodCallHandler
                    }
                    executor.execute {
                        runCatching {
                            val player = checkNotNull(track) { "PCM player is not started" }
                            var offset = 0
                            while (offset < pcm.size && player === track) {
                                val written = player.write(pcm, offset, pcm.size - offset, AudioTrack.WRITE_BLOCKING)
                                check(written >= 0) { "AudioTrack write failed: $written" }
                                offset += written
                            }
                            writtenFrames += pcm.size / (2L * channels)
                        }.fold(
                            onSuccess = { mainHandler.post { result.success(null) } },
                            onFailure = { error ->
                                mainHandler.post { result.error("pcm_feed_failed", error.message, null) }
                            },
                        )
                    }
                }
                "drain" -> {
                    val expectedGeneration = generation
                    val targetFrames = writtenFrames
                    executor.execute {
                        while (expectedGeneration == generation) {
                            val head = (track?.playbackHeadPosition ?: 0).toLong() and 0xffffffffL
                            if (head >= targetFrames) break
                            Thread.sleep(10)
                        }
                        mainHandler.post { result.success(null) }
                    }
                }
                "pause" -> {
                    track?.pause()
                    result.success(null)
                }
                "resume" -> {
                    track?.play()
                    result.success(null)
                }
                "stop" -> {
                    generation++
                    track?.pause()
                    track?.flush()
                    executor.execute {
                        stopNow()
                        mainHandler.post { result.success(null) }
                    }
                }
                else -> result.notImplemented()
            }
        }
    }

    private fun stopNow() {
        val player = track
        track = null
        runCatching { player?.stop() }
        player?.release()
        channels = 0
        writtenFrames = 0
    }
}
