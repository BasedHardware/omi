package com.friend.ios

import android.content.Context
import android.graphics.Bitmap
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMetadataRetriever
import android.media.MediaMuxer
import android.os.Handler
import android.os.Looper
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.nio.ByteBuffer
import java.util.UUID
import kotlin.concurrent.thread
import kotlin.math.floor
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * `com.omi/chat_video` — reduce a picked clip to what chat reads: stills and the audio track.
 *
 * Same candidate set as the backend (backend/utils/media/video_frames.py) and the iOS/macOS
 * samplers: at most 48 frames, at most 4 per second, longest edge 384 px. The AAC track is
 * copied into an .m4a without re-encoding; any other codec uploads frames only.
 */
object ChatVideoSamplerPlugin {
    private const val MAX_FRAMES = 48
    private const val MAX_FPS = 4.0
    private const val FRAME_EDGE = 384
    private const val MAX_AUDIO_US = 600_000_000L

    fun register(flutterEngine: FlutterEngine, context: Context) {
        val appContext = context.applicationContext
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "com.omi/chat_video")
            .setMethodCallHandler { call, result ->
                val path = call.argument<String>("path")
                if (call.method != "sample" || path == null) {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                thread(name = "omi-chat-video") {
                    val outcome = runCatching { sample(appContext, path) }
                    Handler(Looper.getMainLooper()).post {
                        outcome.onSuccess { result.success(it) }
                            .onFailure { result.error("sample_failed", it.message, null) }
                    }
                }
            }
    }

    fun sampleTimes(durationSeconds: Double): List<Double> {
        if (!durationSeconds.isFinite() || durationSeconds <= 0) return listOf(0.0)
        // As many frames as fit at most 4 per second from 0 to just before the end, spread to the end.
        val reach = max(0.0, durationSeconds - 0.05)
        val count = min(MAX_FRAMES, floor(reach * MAX_FPS).toInt() + 1)
        if (count == 1) return listOf(0.0)
        val step = reach / (count - 1)
        return (0 until count).map { (it * step * 100).roundToInt() / 100.0 }
    }

    private fun sample(context: Context, path: String): Map<String, Any?> {
        val directory = File(context.cacheDir, "omi-chat-video-${UUID.randomUUID()}").apply { mkdirs() }
        val retriever = MediaMetadataRetriever()
        try {
            retriever.setDataSource(path)
            if (retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_HAS_VIDEO) != "yes") {
                error("That file has no video to read.")
            }
            val durationMs = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
            val duration = durationMs / 1000.0
            val frames = mutableListOf<String>()
            val times = mutableListOf<Double>()
            for (t in sampleTimes(duration)) {
                val bitmap = retriever.getScaledFrameAtTime(
                    (t * 1_000_000).toLong(),
                    // Exact frame, so its time label is the requested one (CLOSEST_SYNC can jump seconds).
                    MediaMetadataRetriever.OPTION_CLOSEST,
                    FRAME_EDGE,
                    FRAME_EDGE,
                ) ?: continue
                val file = File(directory, "frame-${frames.size}.jpg")
                file.outputStream().use { bitmap.compress(Bitmap.CompressFormat.JPEG, 75, it) }
                bitmap.recycle()
                frames.add(file.path)
                times.add(t)
            }
            if (frames.isEmpty()) error("Couldn't read frames from that video.")
            val audio = runCatching { copyAacTrack(path, File(directory, "audio.m4a"), durationMs * 1000) }.getOrNull()
            if (audio == null && hasAudioTrack(path)) {
                // Speech we can't remux (Opus/Vorbis in WebM/MKV): the caller uploads the clip
                // whole and the server transcribes it.
                directory.deleteRecursively()
                return mapOf("audio_unsupported" to true)
            }
            return mapOf(
                "frames" to frames,
                "times" to times,
                "duration" to if (duration > 0) duration else times.last(),
                "audio" to audio,
                "directory" to directory.path,
            )
        } catch (error: Throwable) {
            directory.deleteRecursively()
            throw error
        } finally {
            retriever.release()
        }
    }

    private fun hasAudioTrack(source: String): Boolean {
        val extractor = MediaExtractor()
        return try {
            extractor.setDataSource(source)
            (0 until extractor.trackCount).any {
                extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true
            }
        } catch (_: Exception) {
            false
        } finally {
            extractor.release()
        }
    }

    /** Remux the first AAC track (phone cameras record AAC) into an .m4a; null when there is none. */
    private fun copyAacTrack(source: String, output: File, durationUs: Long): String? {
        val extractor = MediaExtractor()
        try {
            extractor.setDataSource(source)
            val track = (0 until extractor.trackCount).firstOrNull {
                extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME) == MediaFormat.MIMETYPE_AUDIO_AAC
            } ?: return null
            val format = extractor.getTrackFormat(track)
            extractor.selectTrack(track)
            val muxer = MediaMuxer(output.path, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
            try {
                val target = muxer.addTrack(format)
                muxer.start()
                val capacity = if (format.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)) {
                    format.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE)
                } else {
                    256 * 1024
                }
                val buffer = ByteBuffer.allocate(capacity)
                val info = MediaCodec.BufferInfo()
                val limit = min(if (durationUs > 0) durationUs else MAX_AUDIO_US, MAX_AUDIO_US)
                while (true) {
                    val size = extractor.readSampleData(buffer, 0)
                    if (size < 0 || extractor.sampleTime > limit) break
                    info.set(0, size, extractor.sampleTime, extractor.sampleFlags)
                    muxer.writeSampleData(target, buffer, info)
                    extractor.advance()
                }
                muxer.stop()
            } finally {
                muxer.release()
            }
            return output.path
        } finally {
            extractor.release()
        }
    }
}
