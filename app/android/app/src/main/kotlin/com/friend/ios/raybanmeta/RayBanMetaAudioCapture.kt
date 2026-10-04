package com.friend.ios.raybanmeta

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioRouting
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import androidx.core.content.ContextCompat
import java.util.concurrent.Executors

/**
 * Captures the Ray-Ban Meta glasses microphone over the Bluetooth HFP (SCO)
 * route — the Android counterpart of ios/Runner/RayBanMeta/RayBanMetaAudioCapture.swift.
 *
 * The Meta Wearables Device Access Toolkit has no microphone API; Meta's
 * documented input path is HFP. This routes the communication device to the
 * glasses' SCO link, records PCM16 mono at 16 kHz with an AudioRecord pinned
 * to the glasses input, and hands fixed-size frames to the caller. It has no
 * DAT dependency, so the labeled audio-only fallback works in every flavor.
 *
 * Never falls back to the phone mic: if the SCO route cannot be established,
 * or drifts off the glasses mid-capture, capture stops and reports an error
 * instead of silently recording the wrong source.
 *
 * Ordering caveat from Meta's docs: when combining with DAT camera streaming,
 * HFP must be fully active before the camera stream starts or the audio route
 * can fail silently. [start] does its routing on [worker]; [runAfterPendingStart]
 * lets RayBanMetaHostApiImpl sequence startCamera behind it.
 */
class RayBanMetaAudioCapture(context: Context) {

    companion object {
        private const val TAG = "RayBanMeta.Audio"
        const val TARGET_SAMPLE_RATE = 16000
        private const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val AUDIO_ENCODING = AudioFormat.ENCODING_PCM_16BIT

        // 100 ms of PCM16 mono per frame keeps Pigeon hops to 10/s.
        private const val FRAME_BYTES = TARGET_SAMPLE_RATE / 10 * 2
        private const val SCO_CONNECT_TIMEOUT_MS = 4000L
        private const val SCO_POLL_INTERVAL_MS = 100L
        private const val ROUTE_CHECK_ATTEMPTS = 20
        private const val ROUTE_CHECK_INTERVAL_MS = 50L

        /** Stable identity for an HFP input; AudioDeviceInfo.id changes on every reconnect. */
        fun uidOf(device: AudioDeviceInfo): String =
            device.address?.takeIf { it.isNotBlank() } ?: "sco-${device.id}"
    }

    data class HfpInput(val uid: String, val name: String)

    private val context = context.applicationContext
    private val audioManager = this.context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val mainHandler = Handler(Looper.getMainLooper())

    // One worker serializes start/stop and the blocking SCO routing wait, so the
    // main thread (where Pigeon calls land) never blocks.
    private val worker = Executors.newSingleThreadExecutor { r -> Thread(r, "RayBanMetaAudio") }

    /** PCM16 little-endian mono frames at [TARGET_SAMPLE_RATE]. Called on the record thread. */
    @Volatile var onFrame: ((ByteArray, Double) -> Unit)? = null
    /** Whether the selected glasses input is the active capture route. */
    @Volatile var onRouteChanged: ((Boolean) -> Unit)? = null
    @Volatile var onError: ((String, String) -> Unit)? = null
    /** Capture actually started (true) or stopped for any reason (false). */
    @Volatile var onRunningChanged: ((Boolean) -> Unit)? = null

    @Volatile private var audioRecord: AudioRecord? = null
    @Volatile private var recordThread: Thread? = null
    @Volatile private var running = false
    @Volatile private var targetUid: String? = null
    @Volatile private var routedForGlasses = false
    private var previousMode = AudioManager.MODE_NORMAL
    private var routingListener: AudioRouting.OnRoutingChangedListener? = null
    @Volatile private var generation = 0

    private val deviceCallback = object : AudioDeviceCallback() {
        override fun onAudioDevicesRemoved(removedDevices: Array<out AudioDeviceInfo>) {
            val target = targetUid
            val lost = removedDevices.any {
                it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO && (target == null || uidOf(it) == target)
            }
            if (lost && running) failCapture("audio_route_lost", "Glasses microphone disconnected during capture")
        }
    }

    init {
        audioManager.registerAudioDeviceCallback(deviceCallback, mainHandler)
    }

    val isRunning: Boolean get() = running

    /** Bluetooth HFP inputs currently exposed by the OS. */
    fun availableHfpInputs(): List<HfpInput> = scoInputs().map {
        HfpInput(uid = uidOf(it), name = it.productName?.toString().orEmpty().ifBlank { "Bluetooth headset" })
    }

    /** True while capturing and the record route is the selected glasses SCO input. */
    val isSelectedRouteActive: Boolean
        get() {
            if (!running) return false
            val routed = audioRecord?.routedDevice ?: return false
            val target = targetUid
            return routed.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO && (target == null || uidOf(routed) == target)
        }

    /** True when any (or the given) glasses HFP input is present, captured or not. */
    fun isHfpInputAvailable(uid: String? = null): Boolean =
        scoInputs().any { uid == null || uidOf(it) == uid }

    /**
     * Validates synchronously (permission, input present) and throws on failure;
     * routing and recording continue on the worker. Later failures arrive via [onError].
     */
    fun start(inputUid: String?) {
        if (running) return
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            throw IllegalStateException("Microphone permission is not granted")
        }
        val input = selectInput(inputUid)
            ?: throw IllegalStateException(
                if (inputUid != null) "Selected Bluetooth microphone is unavailable"
                else "No Bluetooth HFP microphone is connected"
            )
        targetUid = inputUid
        running = true
        val startGeneration = ++generation
        val startedAt = SystemClock.elapsedRealtime()
        Log.i(TAG, "start @ 0ms — input=${input.productName} uid=${uidOf(input)}")

        worker.execute {
            if (startGeneration != generation) return@execute
            try {
                val routeOk = routeToGlasses(input)
                Log.d(TAG, "sco routing done duration_ms=${SystemClock.elapsedRealtime() - startedAt} ok=$routeOk")
                if (!routeOk) {
                    failCapture("audio_route_unavailable", "Could not route audio to the glasses microphone")
                    return@execute
                }
                if (startGeneration != generation) return@execute
                startRecording(input, startGeneration)
                Log.i(TAG, "done @ ${SystemClock.elapsedRealtime() - startedAt}ms — recording at ${TARGET_SAMPLE_RATE}Hz")
            } catch (e: Exception) {
                Log.e(TAG, "start failed after ${SystemClock.elapsedRealtime() - startedAt}ms", e)
                failCapture("audio_start_failed", e.message ?: e.javaClass.simpleName)
            }
        }
    }

    fun stop() {
        if (!running) return
        running = false
        generation++
        worker.execute { teardown() }
        onRunningChanged?.invoke(false)
    }

    /** Stops capture and releases the device callback and worker; the instance is unusable after. */
    fun release() {
        stop()
        audioManager.unregisterAudioDeviceCallback(deviceCallback)
        worker.shutdown()
    }

    /** Runs [action] on the main thread once any in-flight [start] has finished routing. */
    fun runAfterPendingStart(action: () -> Unit) {
        worker.execute { mainHandler.post(action) }
    }

    private fun scoInputs(): List<AudioDeviceInfo> = runCatching {
        audioManager.getDevices(AudioManager.GET_DEVICES_INPUTS)
            .filter { it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO }
    }.getOrDefault(emptyList())

    private fun selectInput(inputUid: String?): AudioDeviceInfo? {
        val inputs = scoInputs()
        // DAT mode has no mapping from its device id to the HFP port, so it
        // keeps the iOS first-HFP behavior.
        return if (inputUid != null) inputs.firstOrNull { uidOf(it) == inputUid } else inputs.firstOrNull()
    }

    // MARK: - Routing (worker thread)

    @SuppressLint("MissingPermission")
    private fun routeToGlasses(input: AudioDeviceInfo): Boolean {
        previousMode = audioManager.mode
        // Arm teardown before mutating system audio state so any failure restores it.
        routedForGlasses = true
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val commDevice = audioManager.availableCommunicationDevices.firstOrNull {
                it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO && uidOf(it) == uidOf(input)
            } ?: audioManager.availableCommunicationDevices.firstOrNull {
                it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO
            } ?: return false
            if (!audioManager.setCommunicationDevice(commDevice)) return false
            return awaitCondition { audioManager.communicationDevice?.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO }
        }

        @Suppress("DEPRECATION")
        run {
            audioManager.startBluetoothSco()
            audioManager.isBluetoothScoOn = true
        }
        @Suppress("DEPRECATION")
        return awaitCondition { audioManager.isBluetoothScoOn }
    }

    private fun awaitCondition(condition: () -> Boolean): Boolean {
        val deadline = SystemClock.elapsedRealtime() + SCO_CONNECT_TIMEOUT_MS
        while (SystemClock.elapsedRealtime() < deadline) {
            if (condition()) return true
            Thread.sleep(SCO_POLL_INTERVAL_MS)
        }
        return condition()
    }

    private fun releaseRoute() {
        if (!routedForGlasses) return
        routedForGlasses = false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            runCatching { audioManager.clearCommunicationDevice() }
        } else {
            @Suppress("DEPRECATION")
            runCatching {
                audioManager.isBluetoothScoOn = false
                audioManager.stopBluetoothSco()
            }
        }
        runCatching { audioManager.mode = previousMode }
    }

    // MARK: - Recording (worker thread)

    @SuppressLint("MissingPermission") // checked in start()
    private fun startRecording(input: AudioDeviceInfo, startGeneration: Int) {
        val minBuffer = AudioRecord.getMinBufferSize(TARGET_SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_ENCODING)
        if (minBuffer <= 0) throw IllegalStateException("AudioRecord rejected ${TARGET_SAMPLE_RATE}Hz PCM16 mono")

        // VOICE_RECOGNITION, as in Meta's CameraAccess sample: VOICE_COMMUNICATION's
        // wideband SCO processing competes with the DAT camera stream for airtime.
        val record = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            TARGET_SAMPLE_RATE,
            CHANNEL_CONFIG,
            AUDIO_ENCODING,
            maxOf(minBuffer * 2, FRAME_BYTES * 4),
        )
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            throw IllegalStateException("AudioRecord failed to initialize")
        }
        if (!record.setPreferredDevice(input)) {
            Log.w(TAG, "setPreferredDevice(glasses) not accepted; relying on route verification")
        }
        audioRecord = record
        record.startRecording()

        // routedDevice is null until capture is flowing; poll briefly before judging the route.
        var attempts = 0
        while (record.routedDevice == null && attempts++ < ROUTE_CHECK_ATTEMPTS) {
            Thread.sleep(ROUTE_CHECK_INTERVAL_MS)
        }
        if (!isSelectedRouteActive) {
            Log.w(TAG, "record route is ${record.routedDevice?.productName} (type=${record.routedDevice?.type}), not the glasses")
            failCapture("audio_route_unavailable", "Recording did not route to the glasses microphone")
            return
        }

        val listener = AudioRouting.OnRoutingChangedListener { routing ->
            val routed = routing.routedDevice
            val active = routed?.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO &&
                (targetUid == null || uidOf(routed) == targetUid)
            onRouteChanged?.invoke(active)
            if (!active && running) failCapture("audio_route_lost", "Glasses microphone route was lost during capture")
        }
        record.addOnRoutingChangedListener(listener, mainHandler)
        routingListener = listener

        onRouteChanged?.invoke(true)
        onRunningChanged?.invoke(true)

        val thread = Thread({ readLoop(record, startGeneration) }, "RayBanMetaAudioRead")
        recordThread = thread
        thread.start()
    }

    private fun readLoop(record: AudioRecord, startGeneration: Int) {
        val buffer = ByteArray(FRAME_BYTES)
        var filled = 0
        var frames = 0L
        while (running && startGeneration == generation) {
            val read = record.read(buffer, filled, FRAME_BYTES - filled)
            if (read < 0) {
                if (running && startGeneration == generation) {
                    failCapture("audio_interrupted", "Audio capture was interrupted (read error $read)")
                }
                break
            }
            filled += read
            if (filled == FRAME_BYTES) {
                onFrame?.invoke(buffer.copyOf(), TARGET_SAMPLE_RATE.toDouble())
                filled = 0
                frames++
                if (frames % 600 == 0L) Log.d(TAG, "streaming frames=$frames (~${frames / 10}s)")
            }
        }
    }

    private fun teardown() {
        val record = audioRecord
        audioRecord = null
        routingListener?.let { listener -> record?.removeOnRoutingChangedListener(listener) }
        routingListener = null
        record?.let {
            runCatching { it.stop() }
            it.release()
        }
        recordThread?.let { thread ->
            if (thread != Thread.currentThread()) runCatching { thread.join(500) }
        }
        recordThread = null
        releaseRoute()
        targetUid = null
        Log.i(TAG, "stopped")
    }

    private fun failCapture(code: String, message: String) {
        Log.w(TAG, "capture failed: $code — $message")
        val wasRunning = running
        running = false
        generation++
        worker.execute { teardown() }
        if (wasRunning) onRunningChanged?.invoke(false)
        onRouteChanged?.invoke(false)
        onError?.invoke(code, message)
    }
}
