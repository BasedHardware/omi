// Android streaming bridge.
//
// Owns:
//   - One `Session` (DeviceSession) per active capture - created via
//     `Wearables.createSession(selector)` and started before any stream
//     is added.
//   - One `Stream` (video capability) attached to that Session.
//   - One TextureRegistry SurfaceTextureEntry that backs the Flutter
//     `Texture` widget on the Dart side.
//   - Coroutine jobs collecting the Stream's video / state / error flows
//     plus the DeviceSession's state / error flows.
//
// Lifecycle (matches Meta 0.6 reference sample):
//   1. Wearables.createSession(selector)             // Result<Session>
//   2. session.start()
//   3. session.state.first { STARTED }               // wait
//   4. session.addStream(config)                     // Result<Stream>
//   5. stream.start()
//   6. collect videoStream / state / errorStream
//   ... later ...
//   7. stream.stop(); stream = null
//   8. session.stop(); session = null
//
// Frame pump:
//   videoStream Flow → VideoFrame (I420 planes) → YUV→ARGB conversion
//   → write into the SurfaceTexture's Surface via lockHardwareCanvas
//   → Flutter's TextureRegistry picks up the new contents.

package com.iseelabs.meta_wearables_dat_flutter

import android.graphics.Bitmap
import android.graphics.Matrix
import android.graphics.Paint
import android.os.Handler
import android.os.Looper
import android.view.Surface
import com.meta.wearable.dat.camera.Stream
import com.meta.wearable.dat.camera.addStream
import com.meta.wearable.dat.camera.types.PhotoData
import com.meta.wearable.dat.camera.types.StreamConfiguration
import com.meta.wearable.dat.camera.types.StreamError
import com.meta.wearable.dat.camera.types.StreamState
import com.meta.wearable.dat.camera.types.VideoFrame
import com.meta.wearable.dat.camera.types.VideoQuality
import com.meta.wearable.dat.core.Wearables
import com.meta.wearable.dat.core.selectors.SpecificDeviceSelector
import com.meta.wearable.dat.core.session.DeviceSession
import com.meta.wearable.dat.core.session.DeviceSessionState
import com.meta.wearable.dat.core.types.DeviceIdentifier
import io.flutter.plugin.common.EventChannel
import io.flutter.view.TextureRegistry
import java.io.ByteArrayOutputStream
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout

internal class MetaSessionManager(
    private val textureRegistry: TextureRegistry,
) {
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    private val mainHandler = Handler(Looper.getMainLooper())

    private var session: DeviceSession? = null
    private var stream: Stream? = null
    private var textureEntry: TextureRegistry.SurfaceTextureEntry? = null
    private var surface: Surface? = null

    private var deviceStateJob: Job? = null
    private var deviceErrorJob: Job? = null
    private var stateJob: Job? = null
    private var errorJob: Job? = null
    private var frameJob: Job? = null

    private var stateSink: EventChannel.EventSink? = null
    private var errorSink: EventChannel.EventSink? = null
    private var sizeSink: EventChannel.EventSink? = null
    private var deviceStateSink: EventChannel.EventSink? = null
    private var deviceErrorSink: EventChannel.EventSink? = null

    /**
     * Per-frame video payload sink. Gated behind subscriber presence:
     * the I420 payload (width * height * 3 / 2 bytes) is ≈1.3 MB at
     * 720p, so we skip the planes copy entirely when nobody is
     * listening. See `doc/frame_processing.md`.
     */
    private var framesSink: EventChannel.EventSink? = null

    private var streamStartElapsedNs: Long = 0L

    /**
     * Codec the caller asked for in `startStreamSession`. When set to
     * `"hvc1"`, the SDK is expected to emit `VideoFrame`s with the
     * compressed payload accessible via the same flow; the texture
     * preview path is disabled because surfacing compressed Android
     * frames requires a `MediaCodec` decoder that host apps must wire
     * themselves (see `doc/streaming.md`).
     */
    private var activeCodec: String = "raw"

    /**
     * Reused ARGB scratch bitmap. Recreated whenever the source frame
     * dimensions change. Keeping a single bitmap across frames avoids GC
     * pressure at 30fps.
     */
    private var argbBitmap: Bitmap? = null
    private var lastWidth = 0
    private var lastHeight = 0

    /**
     * Number of frames we've already emitted a per-frame diagnostic for
     * (Y / chroma min-max-mean stats). Capped at
     * [FRAME_DIAGNOSTIC_LIMIT] so the log doesn't get spammed once we
     * have enough signal to verify the conversion is alive and the data
     * is varying. Reset by [stopSession].
     */
    private var frameDiagnosticsLogged: Int = 0

    /**
     * Serialises concurrent [startSession] calls. The Flutter sample app
     * lets a user double-tap "Start" while the previous start is still
     * waiting on the device link to upgrade from BLE to Bluetooth-Classic
     * / Wi-Fi — without a guard we'd race two `Wearables.createSession`
     * calls and the second would fail with `sessionAlreadyExists`. With
     * the mutex, the second tap simply returns the texture id from the
     * first start (because `textureEntry` is non-null by then).
     */
    private val startMutex = Mutex()

    fun setStateSink(sink: EventChannel.EventSink?) { stateSink = sink }
    fun setErrorSink(sink: EventChannel.EventSink?) { errorSink = sink }
    fun setSizeSink(sink: EventChannel.EventSink?) { sizeSink = sink }
    fun setDeviceStateSink(sink: EventChannel.EventSink?) { deviceStateSink = sink }
    fun setDeviceErrorSink(sink: EventChannel.EventSink?) { deviceErrorSink = sink }
    fun setFramesSink(sink: EventChannel.EventSink?) { framesSink = sink }

    /**
     * Starts a stream for [deviceUuid] (or the auto-selected active device
     * when null). Returns the Flutter texture id.
     *
     * When [deviceKinds] is non-empty, only devices whose mapped DAT
     * kind (`rayBanMeta` / `rayBanDisplay` / `oakleyMeta` / `unknown`)
     * matches one of the entries is considered by the auto-selector
     * filter or explicit lookup.
     *
     * Mirrors the Meta reference sample lifecycle: create Session, start
     * it, wait for STARTED, add a Stream, then start the Stream.
     */
    suspend fun startSession(
        deviceUuid: String?,
        fps: Int,
        quality: VideoQuality,
        deviceKinds: Set<String>? = null,
        videoCodec: String = "raw",
    ): Long = startMutex.withLock {
        activeCodec = videoCodec
        textureEntry?.let { return@withLock it.id() }

        // 1. Resolve the target device.
        //
        // The DAT Android SDK 0.6.0's `AutoDeviceSelector` has stricter
        // eligibility than just "device id appears in `Wearables.devices`":
        // it requires don-sensor signal that may not be present even when
        // the glasses are paired and BLE-connected, and rejects with
        // `noEligibleDevice` otherwise. This is the same gotcha the iOS
        // bridge documents at `MetaSessionManager.swift` lines 113-131; we
        // mirror its strategy here:
        //
        //   1. If the caller passed a deviceUUID, pin
        //      `SpecificDeviceSelector` to that UUID.
        //   2. Otherwise, pick the first paired device (optionally filtered
        //      by `deviceKinds`) and pin `SpecificDeviceSelector` to it.
        //   3. Only error out when no paired device matches the request
        //      (nothing paired, or nothing matching `deviceKinds`).
        //
        // Note: iOS additionally prefers `linkState == .connected` then
        // `.connecting` then any paired id. The Android SDK 0.6.0 surface
        // we depend on does not expose a per-device link state, so we
        // simply take the first paired id; if a future SDK release exposes
        // it, prefer connected → connecting → any here too.
        val kindsFilter: Set<String>? = deviceKinds?.takeIf { it.isNotEmpty() }
        val allIds: List<DeviceIdentifier> = try {
            Wearables.devices.first().toList()
        } catch (_: Throwable) {
            emptyList()
        }
        val filteredIds: List<DeviceIdentifier> = if (kindsFilter != null) {
            allIds.filter { id ->
                kindsFilter.contains(MetaWearablesDatPlugin.wireKindForDevice(id))
            }
        } else {
            allIds
        }

        val selector: SpecificDeviceSelector
        val chosenIdSource: String
        when {
            deviceUuid != null -> {
                val match = filteredIds.firstOrNull { it.toString() == deviceUuid }
                if (match != null) {
                    selector = SpecificDeviceSelector(match)
                    chosenIdSource = "explicit deviceUuid ($match)"
                } else {
                    error(
                        "Wearables.createSession failed: explicit " +
                            "deviceUUID=$deviceUuid is not in the current " +
                            "paired set (paired=${allIds.size}, " +
                            "afterKindsFilter=${filteredIds.size}).",
                    )
                }
            }
            filteredIds.isNotEmpty() -> {
                val pick = filteredIds.first()
                selector = SpecificDeviceSelector(pick)
                chosenIdSource = "first paired device ($pick)"
            }
            kindsFilter != null -> {
                error(
                    "Wearables.createSession failed: no paired glasses " +
                        "match the requested kinds=$kindsFilter " +
                        "(paired=${allIds.size}). Open Meta AI to pair a " +
                        "matching device, then try again.",
                )
            }
            else -> {
                error(
                    "Wearables.createSession failed: no paired glasses " +
                        "found. Open Meta AI to pair Ray-Ban Meta or " +
                        "Oakley Meta glasses, then try again.",
                )
            }
        }
        android.util.Log.i(
            "MetaSessionManager",
            "startSession selector=$chosenIdSource",
        )

        // 2. Create the DeviceSession via Meta's `Result<Session>` API.
        //
        // Even with a [SpecificDeviceSelector] the SDK can refuse with
        // `noEligibleDevice` for a few seconds after the user opens the
        // app: the glasses are paired and BLE-connected but their
        // don-sensor / wear signal hasn't yet surfaced, which the
        // wearable manager treats as "not eligible". Empirically this
        // window is ≤ 5 s on fresh-out-of-the-case glasses, so we retry
        // up to [CREATE_SESSION_MAX_RETRIES] times with
        // [CREATE_SESSION_RETRY_DELAY_MS] between attempts before
        // surfacing the failure to Dart. Non-transient errors (e.g. an
        // unknown UUID) break out of the loop on the first attempt.
        var createError: String? = null
        var created: DeviceSession? = null
        var attempt = 0
        while (created == null && attempt < CREATE_SESSION_MAX_RETRIES) {
            createError = null
            Wearables.createSession(selector)
                .onSuccess { created = it }
                .onFailure { error, _ -> createError = error.description }
            if (created != null) break

            val msg = createError ?: "unknown"
            val isTransient = msg.contains("eligible", ignoreCase = true) ||
                msg.contains("not ready", ignoreCase = true) ||
                msg.contains("not connected", ignoreCase = true)
            attempt++
            if (!isTransient || attempt >= CREATE_SESSION_MAX_RETRIES) break

            android.util.Log.i(
                "MetaSessionManager",
                "createSession transient failure: '$msg'. " +
                    "Retrying in ${CREATE_SESSION_RETRY_DELAY_MS}ms " +
                    "(attempt $attempt/$CREATE_SESSION_MAX_RETRIES).",
            )
            delay(CREATE_SESSION_RETRY_DELAY_MS)
        }
        val newSession = created
            ?: error(
                "Wearables.createSession failed after $attempt attempt(s): " +
                    "${createError ?: "unknown"}. If this keeps happening, " +
                    "force-stop Meta AI on the phone so it stops holding " +
                    "the glasses connection, then try again.",
            )
        session = newSession

        // Forward DeviceSession-level state / error flows BEFORE start so
        // we capture the initial transitions.
        deviceStateJob = scope.launch {
            newSession.state.collectLatest { state ->
                mainHandler.post {
                    deviceStateSink?.success(encodeDeviceSessionState(state))
                }
            }
        }
        // `Session.errors` is exposed as a Flow; we forward it onto the
        // device_session_errors channel. If the SDK ever stops exposing it
        // we'll catch a NoSuchMethodError and skip — defensive copy.
        deviceErrorJob = scope.launch {
            try {
                @Suppress("UNCHECKED_CAST")
                val errorsField =
                    newSession::class.java.getMethod("getErrors").invoke(newSession)
                if (errorsField is kotlinx.coroutines.flow.Flow<*>) {
                    errorsField.collectLatest { error ->
                        mainHandler.post {
                            deviceErrorSink?.success(encodeDeviceSessionError(error))
                        }
                    }
                }
            } catch (_: Throwable) {
                // Older SDKs without the errors flow: silently ignore.
            }
        }

        // 3. Start and wait until STARTED before adding a stream.
        //
        // The Meta SDK's `start()` returns immediately and the actual
        // state transition happens asynchronously as the ACDC transport
        // negotiates a link. On a freshly-paired device that is only
        // reachable over BLE we have observed waits of 5-15 s while the
        // link upgrades to Bluetooth-Classic / Wi-Fi; on a glasses-side
        // failure (battery off, out of range, Meta AI app holding the
        // link) the state never advances. A 30 s ceiling lets us surface
        // a meaningful error to Dart instead of hanging the UI button.
        newSession.start()
        try {
            withTimeout(SESSION_STARTED_TIMEOUT_MS) {
                newSession.state.first { it == DeviceSessionState.STARTED }
            }
        } catch (timeout: TimeoutCancellationException) {
            // Roll back: the orphaned device-state listener jobs would
            // otherwise leak, and a future startSession call would fail
            // with "session already exists".
            deviceStateJob?.cancel(); deviceStateJob = null
            deviceErrorJob?.cancel(); deviceErrorJob = null
            try { newSession.stop() } catch (_: Throwable) { /* ignore */ }
            session = null
            throw IllegalStateException(
                "Wearables.createSession failed: device session never " +
                    "reached STARTED within ${SESSION_STARTED_TIMEOUT_MS / 1000}s. " +
                    "If Meta AI is still running on the phone, force-stop it " +
                    "(Settings → Apps → Meta AI → Force stop) so the glasses " +
                    "can hand the connection over to this app, then try again.",
                timeout,
            )
        }

        // 4. Add the Stream capability. When the caller selected
        // `hvc1`, ask the SDK for compressed HEVC frames via
        // `compressVideo = true`. Texture preview is intentionally
        // disabled in that mode (see frame rendering below).
        val config = buildStreamConfiguration(quality, fps, videoCodec == "hvc1")
        var streamError: String? = null
        var newStream: Stream? = null
        newSession.addStream(config)
            .onSuccess { newStream = it }
            .onFailure { error, _ -> streamError = error.description }
        val resolvedStream = newStream
            ?: run {
                // Rollback the DeviceSession we started above.
                newSession.stop()
                session = null
                deviceStateJob?.cancel(); deviceStateJob = null
                deviceErrorJob?.cancel(); deviceErrorJob = null
                error("addStream failed: ${streamError ?: "unknown"}")
            }
        stream = resolvedStream

        // 5. Allocate the Flutter texture before frames start flowing.
        val entry = textureRegistry.createSurfaceTexture()
        textureEntry = entry
        surface = Surface(entry.surfaceTexture())

        // 6. Wire stream listener jobs (state, error, frames). Frame
        // collection uses collectLatest so that if we ever fall behind on
        // conversion we skip stale frames rather than queuing them up.
        stateJob = scope.launch {
            resolvedStream.state.collectLatest { state -> postState(state) }
        }
        errorJob = scope.launch {
            resolvedStream.errorStream.collectLatest { error -> postError(error) }
        }
        frameJob = scope.launch {
            resolvedStream.videoStream.collectLatest { frame -> renderFrame(frame) }
        }

        // 7. Start the stream.
        streamStartElapsedNs = android.os.SystemClock.elapsedRealtimeNanos()
        resolvedStream.start()
        return@withLock entry.id()
    }

    /**
     * Stops the active Stream then the underlying Session. Idempotent.
     * Mirrors the iOS path: stop the stream first so any in-flight frames
     * are drained, then stop the DeviceSession so future
     * `createSession()` calls succeed without `sessionAlreadyExists`.
     */
    suspend fun stopSession() {
        // Cancel listener jobs first so we don't race on shutdown.
        stateJob?.cancel(); stateJob = null
        errorJob?.cancel(); errorJob = null
        frameJob?.cancel(); frameJob = null

        try {
            stream?.stop()
        } catch (_: Throwable) {
            // Stream may already be terminal; ignore.
        }
        stream = null

        deviceStateJob?.cancel(); deviceStateJob = null
        deviceErrorJob?.cancel(); deviceErrorJob = null

        try {
            session?.stop()
        } catch (_: Throwable) {
            // Session may already be terminal; ignore.
        }
        session = null

        withContext(Dispatchers.Main) {
            surface?.release()
            surface = null
            textureEntry?.release()
            textureEntry = null
        }
        argbBitmap?.recycle()
        argbBitmap = null
        lastWidth = 0
        lastHeight = 0
        streamStartElapsedNs = 0L
        frameDiagnosticsLogged = 0
    }

    /**
     * Captures a still photo mid-stream and returns it as a (bytes, format)
     * pair. The format is determined by the device side: HEIC frames are
     * passed through unchanged; Bitmap frames are encoded to JPEG at
     * quality 95 (a good balance for OCR and ML pipelines).
     */
    suspend fun capturePhoto(): Pair<ByteArray, String> {
        val stream = stream ?: error("No active stream session")
        val outcome = stream.capturePhoto()
        val photo = outcome.getOrNull()
            ?: error("capturePhoto failed: ${outcome.exceptionOrNull()?.message}")
        return when (photo) {
            is PhotoData.Bitmap -> {
                val bos = ByteArrayOutputStream()
                photo.bitmap.compress(Bitmap.CompressFormat.JPEG, 95, bos)
                bos.toByteArray() to "jpeg"
            }
            is PhotoData.HEIC -> {
                val buffer = photo.data.duplicate().apply { position(0) }
                val bytes = ByteArray(buffer.remaining())
                buffer.get(bytes)
                bytes to "heic"
            }
        }
    }

    fun pauseSession() {
        // Pause/resume is driven by the device side (hinges, thermal, ...)
        // rather than an explicit API on the 0.6.x surface. Documented as
        // no-op so host apps can call it unconditionally.
    }

    fun resumeSession() {
        // See pauseSession.
    }

    fun dispose() {
        scope.cancel()
        argbBitmap?.recycle()
        argbBitmap = null
    }

    // --- Frame rendering -----------------------------------------------------

    private fun renderFrame(frame: VideoFrame) {
        val width = frame.width
        val height = frame.height

        // hvc1 path: forward compressed bytes when subscribers exist
        // and bail out — no texture preview is rendered for hvc1 on
        // Android (see doc/streaming.md).
        if (activeCodec == "hvc1") {
            val sink = framesSink
            if (sink != null) {
                emitCompressedFrame(frame, width, height, sink)
            }
            if (lastWidth != width || lastHeight != height) {
                lastWidth = width
                lastHeight = height
                mainHandler.post {
                    sizeSink?.success(mapOf("width" to width, "height" to height))
                }
            }
            return
        }

        val surface = surface ?: return

        // The first time we see a frame (or when the resolution
        // changes mid-stream) tell the SurfaceTexture the producer
        // buffer size. Without this, `Surface.lockHardwareCanvas()`
        // returns a canvas sized to the texture's default
        // (Flutter-controlled) buffer, which is unrelated to the
        // 720×1280 video frame — the resulting bitmap-into-canvas
        // scale-fit then produces a tiny / squashed / wrong-colour
        // preview even though the YUV decode itself is correct.
        if (lastWidth != width || lastHeight != height) {
            textureEntry?.surfaceTexture()?.setDefaultBufferSize(width, height)
            android.util.Log.i(
                "MetaSessionManager",
                "SurfaceTexture defaultBufferSize -> ${width}x$height",
            )
        }

        // Forward raw I420 to the videoFramesStream sink before we
        // start mutating the bitmap. Gated on subscriber presence to
        // keep per-frame cost free when nobody is listening.
        val sink = framesSink
        if (sink != null) {
            emitVideoFrame(frame, width, height, sink)
        }

        val bitmap = ensureBitmap(width, height)

        // Per-frame diagnostic: log Y / chroma min-mean-max for the
        // first `FRAME_DIAGNOSTIC_LIMIT` frames, then drop to a low-rate
        // heartbeat (every `FRAME_DIAGNOSTIC_HEARTBEAT_INTERVAL` frames,
        // ≈ 1 Hz at 30 fps) for the rest of the stream. The detailed
        // window catches stream warm-up; the heartbeat catches the
        // transition to real video frames when the glasses are actually
        // worn / capturing, which can happen a few seconds after the
        // session reaches STREAMING.
        //
        // - Flat Y across both windows → SDK is feeding placeholders
        //   (glasses not worn or no don-sensor signal). No code fix
        //   helps; the preview will stay uniform.
        // - Flat chroma but varying Y → user is filming a near-mono-
        //   chrome real scene (white wall, hand, paper); preview will
        //   render mostly-gray correctly.
        val totalFrames = frameDiagnosticsLogged
        val shouldLog = totalFrames < FRAME_DIAGNOSTIC_LIMIT ||
            (totalFrames - FRAME_DIAGNOSTIC_LIMIT) %
                FRAME_DIAGNOSTIC_HEARTBEAT_INTERVAL == 0
        if (shouldLog) {
            logFrameDiagnostics(frame, width, height, totalFrames)
        }
        frameDiagnosticsLogged++

        // Meta DAT SDK 0.6.x always delivers tightly-packed I420 (verified
        // against the official Android sample's `YuvToBitmapConverter` and
        // confirmed at runtime by the HEVC decoder's `raw.pixel-format = 35`
        // and `raw.color.matrix = 1` config). YuvToArgb uses BT.709
        // coefficients matching the codec's advertised matrix.
        YuvToArgb.convert(
            yuvData = frame.buffer,
            width = width,
            height = height,
            output = bitmap,
        )

        try {
            val canvas = surface.lockHardwareCanvas() ?: return
            try {
                canvas.drawColor(android.graphics.Color.BLACK)
                val matrix = Matrix().apply {
                    val sx = canvas.width / width.toFloat()
                    val sy = canvas.height / height.toFloat()
                    val s = minOf(sx, sy)
                    postScale(s, s)
                    postTranslate(
                        (canvas.width - width * s) / 2f,
                        (canvas.height - height * s) / 2f,
                    )
                }
                canvas.drawBitmap(bitmap, matrix, framePaint)
            } finally {
                surface.unlockCanvasAndPost(canvas)
            }
        } catch (_: IllegalStateException) {
            // Surface released between check and lock - ignore.
        }

        if (lastWidth != width || lastHeight != height) {
            lastWidth = width
            lastHeight = height
            mainHandler.post {
                sizeSink?.success(mapOf("width" to width, "height" to height))
            }
        }
    }

    /**
     * Serialises a single I420 [VideoFrame] into the Flutter platform-channel
     * payload consumed by [`videoFramesStream`]. The three planes are
     * concatenated as `Y | U | V` to `width * height * 3/2` bytes
     * (Android I420 is always 8-bit, packed; no row stride padding for the
     * common SDK shape — if the underlying planes have stride > width we
     * strip the padding here so Dart callers see a tightly-packed buffer).
     *
     * The payload shape matches `VideoFrame.fromMap` on Dart:
     *   `{ codec, bytes, width, height, ptsUs, isKeyframe, bytesPerRow=null }`.
     */
    private fun emitVideoFrame(
        frame: VideoFrame,
        width: Int,
        height: Int,
        sink: EventChannel.EventSink,
    ) {
        val ySize = width * height
        val uvSize = (width / 2) * (height / 2)
        val total = ySize + 2 * uvSize
        // SDK 0.6.x: `VideoFrame.buffer` already contains I420 as
        // Y | U | V with no row-stride padding. Single bulk copy.
        val out = ByteArray(total)
        val src = frame.buffer.duplicate().apply { position(frame.buffer.position()) }
        val available = minOf(total, src.remaining())
        src.get(out, 0, available)

        val ptsUs = frame.presentationTimeUs

        mainHandler.post {
            sink.success(
                mapOf(
                    "codec" to "raw",
                    "bytes" to out,
                    "width" to width,
                    "height" to height,
                    "ptsUs" to ptsUs,
                    "isKeyframe" to true,
                    "bytesPerRow" to null,
                ),
            )
        }
    }

    /**
     * Serialises a compressed (hvc1) [VideoFrame] payload to the
     * `videoFramesStream` map shape.
     *
     * The Meta DAT 0.6.x [VideoFrame] type exposes the compressed bytes
     * via a `compressedData: ByteBuffer?` (or similar) field depending
     * on the SDK build. We use reflection so we don't break compilation
     * across SDK revisions, and gracefully fall back to skipping the
     * frame if the field cannot be resolved.
     */
    private fun emitCompressedFrame(
        frame: VideoFrame,
        width: Int,
        height: Int,
        sink: EventChannel.EventSink,
    ) {
        val payload = extractCompressedBytes(frame) ?: return
        val isKeyframe = extractIsKeyframe(frame)
        val nowNs = android.os.SystemClock.elapsedRealtimeNanos()
        val ptsUs = if (streamStartElapsedNs == 0L) 0L
        else (nowNs - streamStartElapsedNs) / 1_000L
        mainHandler.post {
            sink.success(
                mapOf(
                    "codec" to "hvc1",
                    "bytes" to payload,
                    "width" to width,
                    "height" to height,
                    "ptsUs" to ptsUs,
                    "isKeyframe" to isKeyframe,
                    "bytesPerRow" to null,
                ),
            )
        }
    }

    /**
     * Reads the compressed-payload bytes from a [VideoFrame] using
     * reflection. Tries the common field names that have appeared
     * across DAT SDK 0.6.x builds (`compressedData`, `compressed`,
     * `compressedBytes`). Returns `null` when no matching field is
     * present.
     */
    private fun extractCompressedBytes(frame: VideoFrame): ByteArray? {
        val candidates = listOf(
            "getCompressedData",
            "getCompressed",
            "getCompressedBytes",
            "getEncoded",
        )
        for (name in candidates) {
            val method = try {
                frame::class.java.getMethod(name)
            } catch (_: Throwable) {
                continue
            }
            val value = try { method.invoke(frame) } catch (_: Throwable) { null }
            when (value) {
                is ByteArray -> return value
                is java.nio.ByteBuffer -> {
                    val dup = value.duplicate()
                    dup.position(0)
                    val out = ByteArray(dup.remaining())
                    dup.get(out)
                    return out
                }
                else -> Unit
            }
        }
        return null
    }

    /**
     * Reads `isKeyframe` / `isKey` / `keyframe` from a [VideoFrame] via
     * reflection, defaulting to `true` when no matching getter is
     * present (single-NAL CMSampleBuffers).
     */
    private fun extractIsKeyframe(frame: VideoFrame): Boolean {
        val names = listOf("isKeyframe", "isKey", "getKeyframe", "isCompressedKey")
        for (name in names) {
            val method = try {
                frame::class.java.getMethod(name)
            } catch (_: Throwable) {
                continue
            }
            val value = try { method.invoke(frame) } catch (_: Throwable) { null }
            if (value is Boolean) return value
        }
        return true
    }

    private fun ensureBitmap(width: Int, height: Int): Bitmap {
        val existing = argbBitmap
        if (existing != null && existing.width == width && existing.height == height) {
            return existing
        }
        existing?.recycle()
        val created = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        argbBitmap = created
        return created
    }

    /**
     * Per-frame logcat diagnostic for the first
     * [FRAME_DIAGNOSTIC_LIMIT] decoded frames of a stream, then a
     * heartbeat every [FRAME_DIAGNOSTIC_HEARTBEAT_INTERVAL] frames.
     * Emits everything we need to verify the conversion pipeline is
     * alive and the source data is what we think it is:
     *
     * - `bufRemaining` — exact byte count, so we can compare against the
     *   tightly-packed I420 expected size (`w * h * 3 / 2`). Mismatches
     *   mean the SDK is handing us a shape we don't support.
     * - `Y[min/mean/max]` — luma plane stats over the first 4 KiB of Y.
     *   Flat values mean the SDK is emitting placeholder frames during
     *   stream warm-up; the symptom is a uniform preview.
     * - `C[min/mean/max]` — chroma stats over the first 4 KiB after the
     *   Y plane. Values clustered tightly around 128 indicate a
     *   near-monochrome real scene (white wall, hand, paper).
     * - On the very first frame, also dumps the first 32 bytes in hex
     *   for after-the-fact verification.
     */
    private fun logFrameDiagnostics(
        frame: VideoFrame,
        width: Int,
        height: Int,
        index: Int,
    ) {
        val frameSize = width * height
        val expected420 = frameSize + (frameSize shr 1)
        val remaining = frame.buffer.remaining()

        // Y plane stats over the first 4096 bytes — cheap and a good
        // proxy for whether luma is varying.
        val ySampleSize = minOf(4096, frameSize, remaining)
        val ySample = ByteArray(ySampleSize)
        frame.buffer.duplicate().apply { position(frame.buffer.position()) }
            .get(ySample, 0, ySampleSize)
        var yMin = 255
        var yMax = 0
        var ySum = 0L
        for (k in 0 until ySampleSize) {
            val v = ySample[k].toInt() and 0xff
            if (v < yMin) yMin = v
            if (v > yMax) yMax = v
            ySum += v
        }
        val yMean = if (ySampleSize > 0) ySum / ySampleSize else 0

        // Chroma area stats over the first 4096 bytes after Y.
        val chromaStart = frame.buffer.position() + frameSize
        val cAvailable = (frame.buffer.limit() - chromaStart).coerceAtLeast(0)
        val cSampleSize = minOf(4096, frameSize shr 1, cAvailable)
        var cMin = 255
        var cMax = 0
        var cMean = 0L
        if (cSampleSize > 0) {
            val cSample = ByteArray(cSampleSize)
            frame.buffer.duplicate().apply { position(chromaStart) }
                .get(cSample, 0, cSampleSize)
            for (k in 0 until cSampleSize) {
                val v = cSample[k].toInt() and 0xff
                if (v < cMin) cMin = v
                if (v > cMax) cMax = v
                cMean += v
            }
            cMean /= cSampleSize
        } else {
            cMin = 0; cMax = 0; cMean = 0L
        }

        val hexSuffix = if (index == 0) {
            val first32 = ByteArray(minOf(32, remaining))
            frame.buffer.duplicate().apply { position(frame.buffer.position()) }
                .get(first32, 0, first32.size)
            " first32=" + first32.joinToString(" ") {
                "%02x".format(it.toInt() and 0xff)
            }
        } else {
            ""
        }

        android.util.Log.i(
            "MetaSessionManager",
            "frame#$index ${width}x${height} codec=$activeCodec " +
                "bufRemaining=$remaining expectedI420=$expected420 " +
                "Y[min=$yMin mean=$yMean max=$yMax] " +
                "C[min=$cMin mean=$cMean max=$cMax]" +
                hexSuffix,
        )
    }

    // --- State / error encoding ---------------------------------------------

    private fun postState(state: StreamState) {
        // DAT 0.7.0 turned `StreamState` into an enum (was a sealed class in
        // 0.6.x), so match on `name` rather than the runtime class. The
        // enum adds `STARTED` and a terminal `CLOSED`; both collapse onto the
        // 6-value Dart `StreamSessionState` contract.
        val encoded = when (state.name.uppercase().replace("_", "")) {
            "STOPPED", "CLOSED" -> 0
            "WAITINGFORDEVICE" -> 1
            "STARTING" -> 2
            "STREAMING", "STARTED" -> 3
            "PAUSED" -> 4
            "STOPPING" -> 5
            else -> 0
        }
        // Mirror every Stream state transition to logcat so we can
        // reconstruct the lifecycle even when the Dart UI label appears
        // stuck (e.g. "Stopped" after a brief Streaming → Stopped flip).
        android.util.Log.i(
            "MetaSessionManager",
            "stream state -> ${state.name} (encoded=$encoded)",
        )
        mainHandler.post { stateSink?.success(encoded) }
    }

    private fun postError(error: StreamError) {
        // DAT 0.7.0: `StreamError` is an enum whose human-readable text lives
        // on `.description`. Match on `name` (0.6.x was a sealed class).
        val message = runCatching { error.description }
            .getOrNull()
            ?.takeIf { it.isNotEmpty() }
            ?: error.name
        // Match Dart's `StreamSessionError` code shape: typed codes
        // for the cases the Dart facade flips into `is*` getters.
        val code = when (error.name.uppercase().replace("_", "")) {
            "PERMISSIONDENIED" -> "permissionDenied"
            "THERMALCRITICAL" -> "thermalCritical"
            "HINGESCLOSED", "HINGECLOSED" -> "hingesClosed"
            "DEVICEDISCONNECTED", "DEVICENOTCONNECTED" -> "deviceDisconnected"
            "DEVICENOTFOUND" -> "deviceNotFound"
            "TIMEOUT" -> "timeout"
            "VIDEOSTREAMINGERROR", "STREAMERROR" -> "videoStreamingError"
            "INTERNALERROR" -> "internalError"
            else -> "sessionError"
        }
        android.util.Log.w(
            "MetaSessionManager",
            "stream error -> code=$code message=$message",
        )
        mainHandler.post {
            errorSink?.success(mapOf("code" to code, "message" to message))
        }
    }

    private fun encodeDeviceSessionState(state: DeviceSessionState): Int =
        // Map by name so we don't break compilation if Meta adds enum cases.
        when (state.name.uppercase()) {
            "IDLE" -> 0
            "STARTING" -> 1
            "STARTED", "RUNNING" -> 2
            "PAUSED" -> 3
            "STOPPING" -> 4
            "STOPPED", "CLOSED" -> 5
            else -> 0
        }

    private fun encodeDeviceSessionError(error: Any?): Map<String, Any?> {
        val message = error?.toString() ?: "unknown"
        // DAT 0.7.0: `DeviceSessionError` is an enum, so prefer the entry
        // `name`; fall back to the runtime class name for older sealed-class
        // shapes. Normalise SCREAMING_SNAKE / camelCase before matching.
        val name = ((error as? Enum<*>)?.name
            ?: error?.let { it::class.java.simpleName }
            ?: "")
            .uppercase()
            .replace("_", "")
        val code = when (name) {
            "NOELIGIBLEDEVICE" -> "noEligibleDevice"
            "SESSIONALREADYSTOPPED" -> "sessionAlreadyStopped"
            "SESSIONALREADYEXISTS" -> "sessionAlreadyExists"
            "SESSIONIDLE" -> "sessionIdle"
            "CAPABILITYALREADYACTIVE" -> "capabilityAlreadyActive"
            "CAPABILITYNOTFOUND" -> "capabilityNotFound"
            "DATAPPONTHEGLASSESUPDATEREQUIRED" -> "datAppUpdateRequired"
            else -> "unexpectedError"
        }
        return mapOf("code" to code, "message" to message)
    }

    /**
     * Builds a [StreamConfiguration] respecting [compressVideo]. The
     * SDK 0.6.x [StreamConfiguration] type only adds the
     * `compressVideo` knob in some shipping flavours, so we use
     * reflection to set it when present and fall back to the legacy
     * two-arg constructor otherwise. This avoids breaking compilation
     * if Meta changes the constructor surface.
     */
    private fun buildStreamConfiguration(
        quality: VideoQuality,
        fps: Int,
        compressVideo: Boolean,
    ): StreamConfiguration {
        if (!compressVideo) {
            return StreamConfiguration(videoQuality = quality, frameRate = fps)
        }
        // Try the three-arg constructor first via reflection.
        try {
            val ctor = StreamConfiguration::class.java
                .declaredConstructors
                .firstOrNull { it.parameterCount == 3 }
            if (ctor != null) {
                @Suppress("UNCHECKED_CAST")
                val instance = ctor.newInstance(quality, fps, compressVideo)
                    as StreamConfiguration
                return instance
            }
        } catch (_: Throwable) {
            // fall through
        }
        // Fall back to the two-arg constructor and try setting
        // `compressVideo` via reflection on the instance afterwards.
        val cfg = StreamConfiguration(videoQuality = quality, frameRate = fps)
        try {
            val field = cfg::class.java.declaredFields.firstOrNull {
                it.name == "compressVideo"
            }
            if (field != null) {
                field.isAccessible = true
                field.setBoolean(cfg, true)
            }
        } catch (_: Throwable) {
            android.util.Log.w(
                "MetaSessionManager",
                "Requested compressVideo=true but this Meta DAT SDK does " +
                    "not expose the field; falling back to raw frames. " +
                    "Update the dependency or report a bug.",
            )
        }
        return cfg
    }

    private companion object {
        val framePaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)

        /**
         * How long to wait for `Session.state` to reach
         * [DeviceSessionState.STARTED] before bailing out of
         * [startSession]. 30 s comfortably covers a worst-case BLE →
         * Bluetooth-Classic / Wi-Fi link upgrade on a fresh pair (we
         * see ≤ 15 s in practice) but trips fast enough on a hung
         * handover that the Flutter UI button never feels stuck.
         */
        const val SESSION_STARTED_TIMEOUT_MS: Long = 30_000L

        /**
         * How many frames to emit detailed `frame#N …` diagnostics for
         * at the start of a stream. 10 covers the typical 300-500 ms
         * warm-up window during which the glasses are pushing
         * placeholder / black frames before real video arrives, while
         * still terminating quickly enough that logcat doesn't fill
         * with per-frame spam for the lifetime of the stream.
         */
        const val FRAME_DIAGNOSTIC_LIMIT: Int = 10

        /**
         * After the initial [FRAME_DIAGNOSTIC_LIMIT] detailed frame
         * logs, emit one more `frame#N …` line every N frames so we
         * keep visibility on the stream without spamming logcat. 30
         * frames ≈ 1 s at 30 fps — enough to spot a flat-luma →
         * real-content transition (or its absence) over the lifetime
         * of a session.
         */
        const val FRAME_DIAGNOSTIC_HEARTBEAT_INTERVAL: Int = 30

        /**
         * How many times to retry [com.meta.wearable.dat.core.Wearables.createSession]
         * after a transient eligibility failure (the glasses are paired
         * but their `don sensor` / wear signal hasn't surfaced yet, so
         * the SDK refuses with `noEligibleDevice` even when we pass a
         * `SpecificDeviceSelector`). Combined with
         * [CREATE_SESSION_RETRY_DELAY_MS] this gives the device up to
         * ~9 s of warm-up before we surface the error to the user.
         */
        const val CREATE_SESSION_MAX_RETRIES: Int = 6

        /** Delay between [com.meta.wearable.dat.core.Wearables.createSession] retries, ms. */
        const val CREATE_SESSION_RETRY_DELAY_MS: Long = 1_500L
    }
}
