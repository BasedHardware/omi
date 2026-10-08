package com.friend.ios.raybanmeta

import android.app.Activity
import android.content.Intent
import com.friend.ios.RayBanMetaGlasses

/**
 * Native → Dart events the DAT backend reports. Implemented by
 * [RayBanMetaHostApiImpl], which hops every call onto the main thread before
 * forwarding it to the Pigeon RayBanMetaFlutterAPI.
 */
interface RayBanMetaEventSink {
    fun onRegistrationStateChanged(state: String)
    fun onGlassesDiscovered(glasses: RayBanMetaGlasses)
    fun onConnectionStateChanged(deviceId: String, state: String)
    fun onPhotoCaptured(jpegBytes: ByteArray, orientationDegrees: Int)
    fun onCameraStateChanged(state: String)
    fun onCameraPermissionChanged(status: String)
    fun onError(code: String, message: String)
}

/**
 * The Meta Wearables Device Access Toolkit (DAT) side of Ray-Ban Meta support:
 * registration, device session, camera permission, and photo capture.
 *
 * Only the `raybanDat` product flavor links the toolkit and supplies a real
 * implementation (src/raybanDat). The dev/prod flavors compile the factory in
 * src/noDat, which returns null, so the default build stays audio-only and
 * never ships the proprietary SDK — the Android counterpart of the iOS
 * `#if canImport(MWDATCore)` split between Runner and RunnerRayBanDat.
 *
 * Microphone audio is not part of this interface: Meta's documented input path
 * is Bluetooth HFP, owned by [RayBanMetaAudioCapture] in every flavor.
 *
 * Every method is called on the main thread.
 */
interface RayBanMetaDatBackend {
    /** Idempotent. Throws FlutterError when the toolkit cannot initialize. */
    fun initialize()

    /** 'unregistered' | 'registering' | 'registered'. */
    fun registrationState(): String
    fun startRegistration(activity: Activity)
    fun startUnregistration(activity: Activity)

    fun availableGlasses(): List<RayBanMetaGlasses>
    fun connect(deviceId: String)
    fun disconnect()

    /** 'disconnected' | 'connecting' | 'connected'. */
    fun connectionState(): String

    /** Resolves 'granted' | 'denied' | 'not_determined'. */
    fun cameraPermissionStatus(callback: (String) -> Unit)

    /**
     * Launches the Meta AI camera-permission flow from [activity]; the outcome
     * arrives through [onActivityResult] with [requestCode].
     */
    fun requestCameraPermission(activity: Activity, requestCode: Int, callback: (String) -> Unit)

    /** Returns true when [requestCode] belonged to this backend. */
    fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean

    fun startCamera()
    fun stopCamera()
    fun capturePhoto()

    /**
     * Consumes a registration request the Meta AI app sent to this app.
     * Returns true when the intent belonged to the toolkit.
     */
    fun handleIntent(activity: Activity, intent: Intent): Boolean

    /** Ends any session and cancels every collector; the backend is unusable after. */
    fun close()
}
