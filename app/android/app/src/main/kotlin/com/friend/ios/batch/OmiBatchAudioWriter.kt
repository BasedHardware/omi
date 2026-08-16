package com.friend.ios.batch

import com.friend.ios.ble.OmiBleManager

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.util.Locale

/**
 * Batch (offline) capture sink. When the user enables "batch mode", incoming BLE
 * audio is NOT streamed to the transcription socket — instead each opus/pcm frame
 * is appended to a local `.bin` file with the exact length-prefixed layout the
 * Omi offline-sync backend (`POST /v2/sync-local-files`) expects.
 *
 * Files are named `audio_omibatch_{codec}_{sampleRate}_{channel}_fs{frameSize}_{startSec}.bin`
 * (the `omibatch` device marker distinguishes these from offline-sync WAL files,
 * which share this directory; the backend treats the device segment as a label.)
 * so the backend can parse the codec, frame size and start timestamp. Flutter later
 * scans the directory, registers each finalized file as a WAL and uploads it.
 *
 * This runs entirely native (called from [OmiBleForegroundService]'s characteristic
 * listener) so the Flutter engine does no per-packet work while the app is
 * minimized/closed. It self-gates on the `batchModeEnabled` pref and is mutually
 * exclusive with [OmiBackgroundAudioStreamer] (which is disabled in batch mode via
 * `nativeBleStreamingEnabled=false`).
 *
 * File mechanics (durability, .part promotion, recovery) live in [BaseBatchAudioWriter];
 * this class owns the notification-driven policy: config matching, mute/cut prefs,
 * per-device frame extraction, silence-gap finalize and wall-clock rotation.
 */
class OmiBatchAudioWriter(context: Context) : BaseBatchAudioWriter(context, TAG, "audio_omibatch_") {
    companion object {
        private const val TAG = "OmiBle.BatchWriter"
        private const val MAX_FILE_BYTES = 32L * 1024 * 1024 // ~32 MB per file
        private const val MAX_FILE_SECONDS = 900L // 15 min per file
        private const val GAP_MS = 30_000L // close current file after this silence gap
    }

    private data class Config(
        val deviceId: String,
        val codec: String,
        val sampleRate: Int,
        val serviceUuid: String,
        val characteristicUuid: String,
        val deviceType: String,
        val dir: String,
    )

    private var lastFrameMs: Long = 0

    @Volatile
    private var wasEnabled = false

    /** Audio target for this device if batch mode is on — used by the foreground
     *  service to subscribe to the audio characteristic when Flutter is dead. */
    fun configuredAudioTargetFor(address: String): Pair<String, String>? {
        val config = loadConfig() ?: return null
        if (!config.deviceId.equals(address, ignoreCase = true)) return null
        return config.serviceUuid to config.characteristicUuid
    }

    fun handleCharacteristic(address: String, serviceUuid: String, characteristicUuid: String, value: ByteArray) {
        val config = loadConfig()
        if (config == null) {
            // Offline mode is off (the common case). Finalize an in-progress file only on the
            // enabled->disabled edge — don't take the lock on every packet when batch mode is off.
            if (wasEnabled) {
                wasEnabled = false
                stop("disabled")
            }
            return
        }
        wasEnabled = true
        if (config.deviceType == "limitless") return // LimitlessFlashDrainEngine owns that device
        if (!config.deviceId.equals(address, ignoreCase = true)) return
        if (!matches(config, serviceUuid, characteristicUuid)) return

        // Muted: drop the packet but keep the open file's gap timer alive so unmute
        // resumes the same recording instead of starting a new one.
        if (boolPref("batchMuted", false)) {
            synchronized(lock) { if (isOpenLocked) lastFrameMs = System.currentTimeMillis() }
            return
        }
        // Manual "New recording": finalize the current file now; this packet opens a fresh one.
        if (boolPref("batchCutRequested", false)) {
            prefs().edit().putBoolean("flutter.batchCutRequested", false).apply()
            stop("manual")
        }

        val frames = transformFrames(config.deviceType, value)
        if (frames.isEmpty()) return

        synchronized(lock) {
            val now = System.currentTimeMillis()

            // Gap finalize: a pause longer than GAP_MS starts a new file (so the
            // backend places resumed audio as a separate conversation).
            if (isOpenLocked && lastFrameMs > 0 && now - lastFrameMs > GAP_MS) {
                closeCurrentLocked("gap")
            }
            // Rotation: bound file size/duration (between packets, never mid-packet).
            if (isOpenLocked && (currentBytes >= MAX_FILE_BYTES || (now / 1000 - currentStartSec) >= MAX_FILE_SECONDS)) {
                closeCurrentLocked("rotate")
            }

            if (!isOpenLocked) {
                val startSec = now / 1000
                val frameSize = if (config.codec == "opus_fs320") 320 else 160
                // Tag the device segment as `omibatch` so the Dart scanner can tell batch
                // recordings apart from offline-sync WAL flushes, which share this directory
                // and the same audio_*.bin naming. The backend ignores this segment; keep it
                // in sync with Dart's `batchRecordingDevice`.
                val name = "audio_omibatch_${config.codec}_${config.sampleRate}_1_fs${frameSize}_${startSec}.bin$PART_SUFFIX"
                if (!openLocked(config.dir, name, startSec, now)) return // storage full or open failed — drop this packet
            }

            if (!writeFramesLocked(frames)) return

            lastFrameMs = now
            maybeFsyncLocked(now)
        }
    }

    override fun onClosedLocked() {
        lastFrameMs = 0
    }

    // ── Frame extraction (mirrors OmiBackgroundAudioStreamer.transformFrames) ──

    private fun transformFrames(deviceType: String, value: ByteArray): List<ByteArray> =
        when (deviceType) {
            "omi", "openglass" -> if (value.size <= 3) emptyList() else listOf(value.copyOfRange(3, value.size))
            "friendPendant" -> {
                if (value.size <= 5) {
                    emptyList()
                } else {
                    val payload = value.copyOfRange(0, value.size - 5)
                    val frames = mutableListOf<ByteArray>()
                    var offset = 0
                    while (offset + 30 <= payload.size) {
                        frames.add(payload.copyOfRange(offset, offset + 30))
                        offset += 30
                    }
                    frames
                }
            }
            else -> {
                Log.w(TAG, "unsupported batch device type: $deviceType")
                emptyList()
            }
        }

    private fun matches(config: Config, serviceUuid: String, characteristicUuid: String): Boolean =
        config.serviceUuid.equals(serviceUuid, ignoreCase = true) &&
            config.characteristicUuid.equals(characteristicUuid, ignoreCase = true)

    // ── Config ──

    private fun loadConfig(): Config? {
        if (!boolPref("batchModeEnabled", false)) return null
        val dir = stringPref("batchAudioDir")
        if (dir.isEmpty()) return null
        val raw = stringPref("nativeBleStreamConfig")
        if (raw.isEmpty()) return null
        return try {
            val json = JSONObject(raw)
            val deviceId = json.optString("deviceId")
            val serviceUuid = json.optString("serviceUuid").lowercase(Locale.US)
            val characteristicUuid = json.optString("characteristicUuid").lowercase(Locale.US)
            if (deviceId.isEmpty() || serviceUuid.isEmpty() || characteristicUuid.isEmpty()) return null
            Config(
                deviceId = deviceId,
                codec = json.optString("codec", "opus"),
                sampleRate = json.optInt("sampleRate", 16000),
                serviceUuid = serviceUuid,
                characteristicUuid = characteristicUuid,
                deviceType = json.optString("deviceType", "omi"),
                dir = dir,
            )
        } catch (e: Exception) {
            Log.w(TAG, "invalid batch config: ${e.message}")
            null
        }
    }
}
