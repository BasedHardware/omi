package com.friend.ios.raybanmeta

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.friend.ios.BluetoothHfpInput
import com.friend.ios.FlutterError
import com.friend.ios.RayBanMetaFlutterAPI
import com.friend.ios.RayBanMetaGlasses
import com.friend.ios.RayBanMetaHostAPI

/**
 * Pigeon host API for Ray-Ban Meta glasses on Android — mirrors
 * ios/Runner/RayBanMeta/RayBanMetaHostApiImpl.swift so the shared Dart layer
 * (discoverer, transport, connection) behaves identically on both platforms.
 *
 * Two build modes, reported through getAvailabilityMode():
 * - "full": the `raybanDat` flavor links the Meta Wearables Device Access
 *   Toolkit — camera/photo capture plus HFP microphone audio.
 * - "audio_only": dev/prod flavors, no toolkit — only the labeled Bluetooth
 *   HFP microphone fallback. Camera calls report unavailable; nothing is faked.
 *
 * Meta ordering constraint: HFP audio must be fully active before the DAT
 * camera stream starts, otherwise the audio route can fail silently. This is
 * why startCamera() queues behind any in-flight audio routing.
 */
class RayBanMetaHostApiImpl(
    context: Context,
    private val flutterApi: RayBanMetaFlutterAPI,
    private val getActivity: () -> Activity?,
) : RayBanMetaHostAPI, RayBanMetaEventSink {

    companion object {
        private const val TAG = "RayBanMeta.HostApi"
        const val CAMERA_PERMISSION_REQUEST_CODE = 0x5242 // "RB"
    }

    private val appContext = context.applicationContext
    private val mainHandler = Handler(Looper.getMainLooper())
    private val audioCapture = RayBanMetaAudioCapture(appContext)
    private val dat: RayBanMetaDatBackend? = RayBanMetaDatBackendFactory.create(appContext, this)

    // Foreground-service holders; the service runs while either is true and is
    // promoted only with the types actually in use.
    private var audioActive = false
    private var cameraActive = false

    // Bumped by stopCamera/disconnect so a camera start still queued behind
    // audio routing is cancelled instead of starting after the caller stopped.
    private var cameraStartGeneration = 0

    init {
        audioCapture.onFrame = { frame, sampleRate ->
            onMain { flutterApi.onAudioFrame(frame, sampleRate) {} }
        }
        audioCapture.onRouteChanged = { active ->
            onMain { flutterApi.onAudioRouteChanged(active) {} }
        }
        audioCapture.onError = { code, message -> onError(code, message) }
        audioCapture.onRunningChanged = { running ->
            onMain {
                audioActive = running
                updateForegroundService()
            }
        }
        RayBanMetaForegroundService.onPromotionFailed = { reason ->
            onError(
                "background_capture_unavailable",
                "Android refused the background capture service ($reason); capture continues while Omi is open",
            )
        }
        Log.i(TAG, "initialized mode=${getAvailabilityMode()}")
    }

    private fun onMain(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) block() else mainHandler.post(block)
    }

    private fun requireActivity(): Activity =
        getActivity() ?: throw FlutterError("no_activity", "Ray-Ban Meta setup needs the app in the foreground", null)

    private fun requireDat(): RayBanMetaDatBackend =
        dat ?: throw FlutterError(
            "dat_unavailable",
            "This build does not include the Meta Wearables toolkit",
            null,
        )

    private fun updateForegroundService() {
        if (audioActive || cameraActive) {
            RayBanMetaForegroundService.update(appContext, microphone = audioActive, connectedDevice = cameraActive)
        } else {
            RayBanMetaForegroundService.stop(appContext)
        }
    }

    /** The engine dies with the activity: end capture and the DAT session with it. */
    fun dispose() {
        try {
            disconnect()
        } catch (e: Throwable) {
            Log.w(TAG, "dispose: disconnect failed: ${e.message}")
        }
        audioCapture.release()
        RayBanMetaForegroundService.onPromotionFailed = null
        dat?.close()
        audioActive = false
        cameraActive = false
        updateForegroundService()
    }

    // MARK: - Activity plumbing (forwarded from MainActivity)

    fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean =
        dat?.onActivityResult(requestCode, resultCode, data) ?: false

    /**
     * Registration requests initiated from the Meta AI app arrive as VIEW intents
     * on the app's callback scheme; Omi's https app links are never the toolkit's.
     */
    fun handleIntent(activity: Activity, intent: Intent?): Boolean {
        val backend = dat ?: return false
        if (intent == null || intent.action != Intent.ACTION_VIEW) return false
        val scheme = intent.data?.scheme
        if (scheme == "https" || scheme == "http") return false
        return try {
            backend.initialize()
            backend.handleIntent(activity, intent)
        } catch (e: Throwable) { // FlutterError is a Throwable, not an Exception
            Log.w(TAG, "handleIntent failed: ${e.message}")
            false
        }
    }

    // MARK: - Availability

    override fun getAvailabilityMode(): String = if (dat != null) "full" else "audio_only"

    // MARK: - Audio (HFP route — available in both modes)

    override fun startAudioCapture(inputUid: String?) {
        try {
            audioCapture.start(inputUid)
        } catch (e: IllegalStateException) {
            throw FlutterError("audio_start_failed", e.message, null)
        }
        // Promote now, while the app is visibly in the foreground; Android rejects
        // starting a microphone FGS from the background.
        audioActive = true
        updateForegroundService()
    }

    override fun stopAudioCapture() {
        audioCapture.stop()
    }

    override fun isGlassesAudioRouteActive(): Boolean = audioCapture.isSelectedRouteActive

    override fun getBluetoothHfpInputs(): List<BluetoothHfpInput> =
        audioCapture.availableHfpInputs().map { BluetoothHfpInput(uid = it.uid, name = it.name) }

    // MARK: - DAT (full mode) / labeled no-ops (audio-only mode)

    override fun initialize() {
        dat?.initialize()
    }

    override fun getRegistrationState(): String {
        val backend = dat ?: return "unavailable"
        // Initialize lazily so a registration persisted from an earlier launch is
        // reported (discovery is the first caller after a restart).
        try {
            backend.initialize()
        } catch (e: Throwable) {
            Log.w(TAG, "DAT initialize failed: ${e.message}")
        }
        return backend.registrationState()
    }

    override fun startRegistration() {
        val backend = requireDat()
        backend.initialize()
        backend.startRegistration(requireActivity())
    }

    override fun unregister() {
        val backend = dat ?: return
        backend.startUnregistration(requireActivity())
    }

    override fun getAvailableGlasses(callback: (Result<List<RayBanMetaGlasses>>) -> Unit) {
        val backend = dat ?: return callback(Result.success(emptyList()))
        try {
            backend.initialize()
            callback(Result.success(backend.availableGlasses()))
        } catch (e: Throwable) {
            callback(Result.failure(e))
        }
    }

    override fun connect(deviceId: String) {
        val backend = dat ?: return
        backend.initialize()
        backend.connect(deviceId)
    }

    override fun disconnect() {
        audioCapture.stop()
        stopCamera()
        dat?.disconnect()
    }

    override fun getConnectionState(): String {
        val backend = dat ?: return if (audioCapture.isHfpInputAvailable()) "connected" else "disconnected"
        return backend.connectionState()
    }

    override fun requestCameraPermission(callback: (Result<String>) -> Unit) {
        val backend = dat ?: return callback(Result.success("unavailable"))
        try {
            backend.initialize()
            backend.requestCameraPermission(requireActivity(), CAMERA_PERMISSION_REQUEST_CODE) { status ->
                onCameraPermissionChanged(status)
                onMain { callback(Result.success(status)) }
            }
        } catch (e: Throwable) {
            callback(Result.failure(e))
        }
    }

    override fun getCameraPermissionStatus(callback: (Result<String>) -> Unit) {
        val backend = dat ?: return callback(Result.success("unavailable"))
        try {
            backend.initialize()
        } catch (e: Throwable) {
            return callback(Result.success("not_determined"))
        }
        backend.cameraPermissionStatus { status -> onMain { callback(Result.success(status)) } }
    }

    override fun startCamera(callback: (Result<Unit>) -> Unit) {
        val backend = dat ?: return callback(
            Result.failure(
                FlutterError("camera_unavailable", "Image capture requires the Meta Wearables toolkit build", null),
            ),
        )
        try {
            backend.initialize()
        } catch (e: Throwable) {
            return callback(Result.failure(e))
        }
        if (backend.connectionState() != "connected") {
            return callback(Result.failure(FlutterError("not_connected", "Connect to the glasses first", null)))
        }
        val generation = ++cameraStartGeneration
        cameraActive = true
        updateForegroundService()
        // Meta's ordering rule: HFP must be fully routed before the DAT stream
        // starts, so the start runs after any in-flight audio routing. The Pigeon
        // call completes only then, with the real outcome.
        val queued = runCatching {
            audioCapture.runAfterPendingStart {
                if (generation != cameraStartGeneration) {
                    callback(
                        Result.failure(
                            FlutterError("camera_start_cancelled", "The camera was stopped before it started", null),
                        ),
                    )
                    return@runAfterPendingStart
                }
                try {
                    backend.startCamera()
                    callback(Result.success(Unit))
                } catch (e: Throwable) {
                    cameraActive = false
                    updateForegroundService()
                    callback(Result.failure(e))
                }
            }
        }
        queued.exceptionOrNull()?.let { e ->
            // The audio worker is gone (bridge disposed); nothing will run the start.
            cameraActive = false
            updateForegroundService()
            callback(Result.failure(FlutterError("camera_stream", e.message ?: "Camera start could not be scheduled", null)))
        }
    }

    override fun stopCamera() {
        cameraStartGeneration++
        dat?.stopCamera()
        if (cameraActive) {
            cameraActive = false
            updateForegroundService()
        }
    }

    override fun capturePhoto() {
        val backend = dat ?: throw FlutterError(
            "camera_unavailable",
            "Image capture requires the Meta Wearables toolkit build",
            null,
        )
        backend.capturePhoto()
    }

    // MARK: - RayBanMetaEventSink (DAT backend → Dart)

    override fun onRegistrationStateChanged(state: String) = onMain {
        flutterApi.onRegistrationStateChanged(state) {}
    }

    override fun onGlassesDiscovered(glasses: RayBanMetaGlasses) = onMain {
        flutterApi.onGlassesDiscovered(glasses) {}
    }

    override fun onConnectionStateChanged(deviceId: String, state: String) = onMain {
        if (state == "disconnected") {
            cameraStartGeneration++ // a start queued for the lost session must not run
            if (cameraActive) {
                cameraActive = false
                updateForegroundService()
            }
        }
        flutterApi.onConnectionStateChanged(deviceId, state) {}
    }

    override fun onPhotoCaptured(jpegBytes: ByteArray, orientationDegrees: Int) = onMain {
        flutterApi.onPhotoCaptured(jpegBytes, orientationDegrees.toLong()) {}
    }

    override fun onCameraStateChanged(state: String) = onMain {
        flutterApi.onCameraStateChanged(state) {}
    }

    override fun onCameraPermissionChanged(status: String) = onMain {
        flutterApi.onCameraPermissionChanged(status) {}
    }

    override fun onError(code: String, message: String) {
        Log.w(TAG, "error $code: $message")
        onMain { flutterApi.onError(code, message) {} }
    }
}
