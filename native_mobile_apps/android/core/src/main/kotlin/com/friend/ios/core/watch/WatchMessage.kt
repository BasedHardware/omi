package com.friend.ios.core.watch

// Port of `OmiService/Watch/WatchMessage.swift`: the contract between the phone app and the Omi
// watch app. Same dictionary keys and values as the iOS app (and the Flutter app), so the payloads
// stay comparable. Compiled into :service through :core and into :wear: plain Kotlin only.
// WatchConnectivity's dictionaries travel over the Wear OS Data Layer as `WatchWire` bytes.

/** 1.5 s of 16 kHz mono PCM16 from the watch microphone; the last one of a recording is empty. */
class WatchAudioChunk(
    val data: ByteArray,
    val index: Int,
    val isLast: Boolean,
    val sampleRate: Double = SAMPLE_RATE,
) {
    override fun equals(other: Any?): Boolean = other is WatchAudioChunk && data.contentEquals(other.data) &&
        index == other.index && isLast == other.isLast && sampleRate == other.sampleRate

    override fun hashCode(): Int = ((data.contentHashCode() * 31 + index) * 31 + isLast.hashCode()) * 31 + sampleRate.hashCode()

    override fun toString(): String = "WatchAudioChunk(bytes=${data.size}, index=$index, isLast=$isLast, sampleRate=$sampleRate)"

    companion object {
        const val SAMPLE_RATE: Double = 16000.0
        /** 1.5 s of PCM16 at 16 kHz (the iOS chunk, small enough for one message). */
        const val BYTES_PER_CHUNK = 48000
    }
}

data class WatchInfo(
    val name: String,
    val model: String,
    val systemVersion: String,
    val localizedModel: String,
)

/** Why the phone ended (or refused) a watch recording; shown on the watch. Native addition. */
enum class WatchStopReason(val rawValue: String) {
    /** Something else (the phone mic, the Omi) is already recording. */
    Busy("busy"),
    /** Nobody is signed in to Omi on the phone. */
    SignedOut("signedOut"),
    /** The phone could not open the live transcription. */
    Failed("failed"),
    ;

    companion object {
        fun from(raw: String?): WatchStopReason? = entries.firstOrNull { it.rawValue == raw }
    }
}

/** What the phone is doing, as the watch shows it (application context; native addition). */
data class WatchPhoneState(
    val capture: Capture,
    /** The Omi wearable's battery while it is connected to the phone. */
    val omiBattery: Int?,
) {
    enum class Capture(val rawValue: String) {
        Idle("idle"), Watch("watch"), Phone("phone"), Omi("omi");

        companion object {
            fun from(raw: String?): Capture? = entries.firstOrNull { it.rawValue == raw }
        }
    }

    val payload: Map<String, Any?>
        get() = buildMap {
            put("method", "phoneState")
            put("capture", capture.rawValue)
            omiBattery?.let { put("omiBattery", it) }
        }

    companion object {
        fun from(payload: Map<String, Any?>): WatchPhoneState? {
            if (payload["method"] as? String != "phoneState") return null
            val capture = Capture.from(payload["capture"] as? String) ?: return null
            return WatchPhoneState(capture, WatchMessage.number(payload["omiBattery"])?.toInt())
        }
    }
}

/**
 * One watch message. `StartRecording`/`StopRecording` travel both ways: from the watch they report
 * what it did, from the phone they ask the watch to do it.
 */
sealed interface WatchMessage {
    data object StartRecording : WatchMessage
    data class StopRecording(val reason: WatchStopReason?) : WatchMessage
    data class AudioChunk(val chunk: WatchAudioChunk) : WatchMessage
    data class RecordingError(val error: String) : WatchMessage
    data object RequestMicrophonePermission : WatchMessage
    data class MicrophonePermissionResult(val granted: Boolean) : WatchMessage
    data object RequestBattery : WatchMessage
    /** Watch battery, 0-100, and the platform's battery state (iOS `WKInterfaceDeviceBatteryState`). */
    data class BatteryUpdate(val level: Double, val state: Int) : WatchMessage
    data object RequestWatchInfo : WatchMessage
    data class WatchInfoUpdate(val info: WatchInfo) : WatchMessage

    val payload: Map<String, Any?>
        get() = when (this) {
            StartRecording -> mapOf("method" to "startRecording")
            is StopRecording -> buildMap {
                put("method", "stopRecording")
                reason?.let { put("reason", it.rawValue) }
            }
            is AudioChunk -> mapOf(
                "method" to "sendAudioChunk", "audioChunk" to chunk.data, "chunkIndex" to chunk.index,
                "isLast" to chunk.isLast, "sampleRate" to chunk.sampleRate,
            )
            is RecordingError -> mapOf("method" to "recordingError", "error" to error)
            RequestMicrophonePermission -> mapOf("method" to "requestMicrophonePermission")
            is MicrophonePermissionResult -> mapOf("method" to "microphonePermissionResult", "granted" to granted)
            RequestBattery -> mapOf("method" to "requestBattery")
            is BatteryUpdate -> mapOf("method" to "batteryUpdate", "batteryLevel" to level, "batteryState" to state)
            RequestWatchInfo -> mapOf("method" to "requestWatchInfo")
            is WatchInfoUpdate -> mapOf(
                "method" to "watchInfoUpdate", "name" to info.name, "model" to info.model,
                "systemVersion" to info.systemVersion, "localizedModel" to info.localizedModel,
            )
        }

    companion object {
        /** Null for an unknown method or a payload missing a required field. */
        fun from(payload: Map<String, Any?>): WatchMessage? = when (payload["method"] as? String) {
            "startRecording" -> StartRecording
            "stopRecording" -> StopRecording(WatchStopReason.from(payload["reason"] as? String))
            "sendAudioChunk" -> {
                val data = payload["audioChunk"] as? ByteArray
                val index = number(payload["chunkIndex"])
                if (data == null || index == null) {
                    null
                } else {
                    AudioChunk(
                        WatchAudioChunk(
                            data, index.toInt(), payload["isLast"] as? Boolean ?: false,
                            number(payload["sampleRate"]) ?: WatchAudioChunk.SAMPLE_RATE,
                        ),
                    )
                }
            }
            "recordingError" -> RecordingError(payload["error"] as? String ?: "")
            "requestMicrophonePermission" -> RequestMicrophonePermission
            "microphonePermissionResult" -> (payload["granted"] as? Boolean)?.let { MicrophonePermissionResult(it) }
            "requestBattery" -> RequestBattery
            "batteryUpdate" -> number(payload["batteryLevel"])?.let {
                BatteryUpdate(it, number(payload["batteryState"])?.toInt() ?: 0)
            }
            "requestWatchInfo" -> RequestWatchInfo
            "watchInfoUpdate" -> (payload["name"] as? String)?.let { name ->
                WatchInfoUpdate(
                    WatchInfo(
                        name, payload["model"] as? String ?: "", payload["systemVersion"] as? String ?: "",
                        payload["localizedModel"] as? String ?: "",
                    ),
                )
            }
            else -> null
        }

        /** Numbers arrive as whatever the other side wrote (the watch sends its battery as a Float). */
        fun number(value: Any?): Double? = (value as? Number)?.toDouble()
    }
}
