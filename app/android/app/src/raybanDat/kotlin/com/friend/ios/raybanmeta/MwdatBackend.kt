package com.friend.ios.raybanmeta

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.os.SystemClock
import android.util.Log
import androidx.exifinterface.media.ExifInterface
import com.friend.ios.FlutterError
import com.friend.ios.RayBanMetaGlasses
import com.meta.wearable.dat.camera.Camera
import com.meta.wearable.dat.camera.Stream
import com.meta.wearable.dat.camera.addCamera
import com.meta.wearable.dat.camera.types.PhotoData
import com.meta.wearable.dat.camera.types.StreamConfiguration
import com.meta.wearable.dat.camera.types.StreamState
import com.meta.wearable.dat.camera.types.VideoQuality
import com.meta.wearable.dat.core.Wearables
import com.meta.wearable.dat.core.selectors.AutoDeviceSelector
import com.meta.wearable.dat.core.selectors.SpecificDeviceSelector
import com.meta.wearable.dat.core.session.DeviceSession
import com.meta.wearable.dat.core.session.DeviceSessionState
import com.meta.wearable.dat.core.types.DeviceIdentifier
import com.meta.wearable.dat.core.types.Permission
import com.meta.wearable.dat.core.types.PermissionStatus
import com.meta.wearable.dat.core.types.RegistrationState
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Meta Wearables Device Access Toolkit (mwdat 1.0) backend — the Android
 * counterpart of the `#if canImport(MWDATCore)` half of
 * ios/Runner/RayBanMeta/RayBanMetaHostApiImpl.swift.
 *
 * Developer Mode (glasses Developer Mode on in the Meta AI app) needs no
 * credentials: the manifest's APPLICATION_ID/CLIENT_TOKEN placeholders stay "0"
 * until a Wearables Developer Center app exists for beta distribution.
 *
 * All public methods run on the main thread; collectors run on [scope]
 * (Dispatchers.Main), so state below is main-thread confined.
 */
internal class MwdatBackend(
    private val context: Context,
    private val events: RayBanMetaEventSink,
) : RayBanMetaDatBackend {

    companion object {
        private const val TAG = "RayBanMeta.Dat"
        private const val DEFAULT_NAME = "Ray-Ban Meta"

        // The stream exists to arm photo capture (and the hardware privacy LED),
        // not to ship video: lowest resolution and the lowest allowed frame rate.
        private const val STREAM_FRAME_RATE = 2

        // Photos travel to the backend as base64 image_chunk frames; cap the long
        // side so a FULL-resolution capture can't balloon the upload.
        private const val MAX_PHOTO_EDGE = 1280
        private const val JPEG_QUALITY = 85
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    private var initialized = false
    private var registration = "unregistered"
    private var latestGlasses: List<RayBanMetaGlasses> = emptyList()
    private val metadataJobs = mutableMapOf<DeviceIdentifier, Job>()

    private var session: DeviceSession? = null
    private var sessionJobs = mutableListOf<Job>()
    private var connectedDeviceId: String? = null
    private var connection = "disconnected"

    private var camera: Camera? = null
    private var stream: Stream? = null
    private var streamState = StreamState.STOPPED
    private var cameraJobs = mutableListOf<Job>()

    private var pendingPermissionCallback: ((String) -> Unit)? = null
    private var pendingPermissionRequestCode: Int? = null

    // MARK: - Lifecycle

    override fun initialize() {
        if (initialized) return
        val started = SystemClock.elapsedRealtime()
        Wearables.initialize(context).errorOrNull()?.let { error ->
            throw FlutterError("dat_init", error.description, null)
        }
        initialized = true
        Log.i(TAG, "Wearables initialized duration_ms=${SystemClock.elapsedRealtime() - started} devMode=${Wearables.isDevMode}")

        scope.launch {
            Wearables.registrationState.collect { state ->
                registration = normalizeRegistration(state)
                Log.i(TAG, "registration state=$state")
                events.onRegistrationStateChanged(registration)
            }
        }
        scope.launch {
            Wearables.registrationErrorStream.collect { error ->
                events.onError("registration", error.description)
            }
        }
        scope.launch {
            Wearables.devices.collect { identifiers -> onDevicesChanged(identifiers) }
        }
    }

    private fun onDevicesChanged(identifiers: Set<DeviceIdentifier>) {
        (metadataJobs.keys - identifiers).forEach { metadataJobs.remove(it)?.cancel() }
        publishGlasses(identifiers)
        // Names arrive through per-device metadata flows; republish as they resolve.
        (identifiers - metadataJobs.keys).forEach { id ->
            val flow = Wearables.devicesMetadata[id] ?: return@forEach
            metadataJobs[id] = scope.launch {
                var lastName: String? = null
                flow.collect { device ->
                    if (device.name != lastName) {
                        lastName = device.name
                        publishGlasses(Wearables.devices.value)
                    }
                }
            }
        }
    }

    private fun publishGlasses(identifiers: Set<DeviceIdentifier>) {
        latestGlasses = identifiers.map { id ->
            val name = Wearables.devicesMetadata[id]?.value?.name.orEmpty()
            RayBanMetaGlasses(id = id.identifier, name = name.ifBlank { DEFAULT_NAME })
        }
        latestGlasses.forEach { events.onGlassesDiscovered(it) }
    }

    override fun handleIntent(activity: Activity, intent: Intent): Boolean {
        val result = Wearables.handleIntent(intent) { request ->
            Log.i(TAG, "registration request from Meta AI flow=${request.flowId}")
            request.continueRegistration(activity).errorOrNull()?.let { error ->
                events.onError("registration_callback", error.description)
            }
        }
        result.errorOrNull()?.let { events.onError("registration_callback", it.description) }
        return result.getOrNull() == true
    }

    // MARK: - Registration

    override fun registrationState(): String =
        if (initialized) normalizeRegistration(Wearables.registrationState.value) else "unregistered"

    override fun startRegistration(activity: Activity) {
        Wearables.startRegistration(activity)
    }

    override fun startUnregistration(activity: Activity) {
        if (!initialized) return
        Wearables.startUnregistration(activity)
    }

    private fun normalizeRegistration(state: RegistrationState): String = when (state) {
        RegistrationState.REGISTERED -> "registered"
        RegistrationState.REGISTERING -> "registering"
        else -> "unregistered"
    }

    override fun availableGlasses(): List<RayBanMetaGlasses> = latestGlasses

    // MARK: - Session

    override fun connect(deviceId: String) {
        if (session != null) return
        val started = SystemClock.elapsedRealtime()
        connectedDeviceId = deviceId
        setConnection("connecting")

        val known = Wearables.devices.value.firstOrNull { it.identifier == deviceId }
        val selector = if (known != null) SpecificDeviceSelector(known) else AutoDeviceSelector()
        val result = Wearables.createSession(selector)
        val created = result.getOrNull()
        if (created == null) {
            setConnection("disconnected")
            connectedDeviceId = null
            throw FlutterError("session", result.errorOrNull()?.description ?: "Could not create a DAT session", null)
        }
        session = created

        // Subscribe before start() so no initial transitions are missed.
        sessionJobs += scope.launch {
            created.state.collect { state ->
                Log.i(TAG, "session state=$state t=${SystemClock.elapsedRealtime() - started}ms")
                when (state) {
                    DeviceSessionState.STARTED -> setConnection("connected")
                    DeviceSessionState.STOPPED -> onSessionEnded()
                    else -> Unit
                }
            }
        }
        sessionJobs += scope.launch {
            created.errors.collect { error ->
                Log.w(TAG, "session error=${error.name}: ${error.description}")
                events.onError("session_${error.name.lowercase()}", error.description)
            }
        }
        created.start()
    }

    override fun disconnect() {
        stopCamera()
        val current = session ?: return
        current.stop()
        onSessionEnded()
    }

    private fun onSessionEnded() {
        if (session == null) return
        clearCamera(emitStopped = camera != null)
        sessionJobs.forEach { it.cancel() }
        sessionJobs.clear()
        session = null
        setConnection("disconnected")
        connectedDeviceId = null
    }

    override fun connectionState(): String = connection

    private fun setConnection(state: String) {
        connection = state
        val deviceId = connectedDeviceId ?: return
        events.onConnectionStateChanged(deviceId, state)
    }

    // MARK: - Camera permission

    override fun cameraPermissionStatus(callback: (String) -> Unit) {
        scope.launch {
            val status = Wearables.checkPermissionStatus(Permission.CAMERA).getOrNull()
            callback(status?.let(::normalizePermission) ?: "not_determined")
        }
    }

    override fun requestCameraPermission(activity: Activity, requestCode: Int, callback: (String) -> Unit) {
        val contract = Wearables.RequestPermissionContract()
        contract.getSynchronousResult(activity, Permission.CAMERA)?.let { sync ->
            callback(sync.value.getOrNull()?.let(::normalizePermission) ?: "denied")
            return
        }
        // MainActivity is a FlutterActivity, not a ComponentActivity, so drive
        // the contract by hand and receive the result via onActivityResult.
        pendingPermissionCallback?.invoke("denied")
        pendingPermissionCallback = callback
        pendingPermissionRequestCode = requestCode
        activity.startActivityForResult(contract.createIntent(activity, Permission.CAMERA), requestCode)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?): Boolean {
        if (requestCode != pendingPermissionRequestCode) return false
        val callback = pendingPermissionCallback
        pendingPermissionCallback = null
        pendingPermissionRequestCode = null
        val status = Wearables.RequestPermissionContract().parseResult(resultCode, data).getOrNull()
        callback?.invoke(status?.let(::normalizePermission) ?: "denied")
        return true
    }

    private fun normalizePermission(status: PermissionStatus): String = when (status) {
        PermissionStatus.Granted -> "granted"
        PermissionStatus.Denied -> "denied"
    }

    // MARK: - Camera

    override fun startCamera() {
        val current = session ?: throw FlutterError("not_connected", "Connect to the glasses first", null)
        if (camera != null) return
        val started = SystemClock.elapsedRealtime()
        events.onCameraStateChanged("starting")

        val added = current.addCamera(
            StreamConfiguration(videoQuality = VideoQuality.LOW, frameRate = STREAM_FRAME_RATE),
        ).getOrNull()
        if (added == null) {
            events.onCameraStateChanged("stopped")
            throw FlutterError("camera_stream", "Could not add the DAT camera to the session", null)
        }
        camera = added
        val newStream = added.stream
        stream = newStream

        cameraJobs += scope.launch {
            newStream.state.collect { state ->
                streamState = state
                Log.i(TAG, "camera stream state=$state t=${SystemClock.elapsedRealtime() - started}ms")
                events.onCameraStateChanged(state.name.lowercase())
                if (state == StreamState.CLOSED) clearCamera(emitStopped = false)
            }
        }
        cameraJobs += scope.launch {
            newStream.errorStream.collect { error ->
                events.onError("camera_stream", error.description)
            }
        }
        newStream.start().errorOrNull()?.let { error ->
            clearCamera(emitStopped = true)
            throw FlutterError("camera_stream", error.description, null)
        }
    }

    override fun stopCamera() {
        val current = camera ?: return
        current.stop()
        clearCamera(emitStopped = true)
    }

    private fun clearCamera(emitStopped: Boolean) {
        cameraJobs.forEach { it.cancel() }
        cameraJobs.clear()
        camera = null
        stream = null
        streamState = StreamState.STOPPED
        if (emitStopped) events.onCameraStateChanged("stopped")
    }

    override fun capturePhoto() {
        val current = stream ?: throw FlutterError(
            "camera_not_started",
            "Start the camera before capturing a photo",
            null,
        )
        if (streamState != StreamState.STREAMING) {
            throw FlutterError("capture_failed", "The camera stream is not ready to capture yet", null)
        }
        val started = SystemClock.elapsedRealtime()
        scope.launch {
            val result = current.capturePhoto()
            val photo = result.getOrNull()
            if (photo == null) {
                events.onError("capture_failed", result.errorOrNull()?.description ?: "Photo capture failed")
                return@launch
            }
            val jpeg = withContext(Dispatchers.Default) { encodeJpeg(photo) }
            if (jpeg == null) {
                events.onError("capture_failed", "Could not decode the captured photo")
                return@launch
            }
            Log.i(TAG, "photo captured bytes=${jpeg.size} duration_ms=${SystemClock.elapsedRealtime() - started}")
            // Pixels are already upright (EXIF applied below), so orientation is 0.
            events.onPhotoCaptured(jpeg, 0)
        }
    }

    // MARK: - Photo encoding (Dispatchers.Default)

    /** The Dart pipeline and backend expect JPEG; DAT delivers a Bitmap or HEIC. */
    private fun encodeJpeg(photo: PhotoData): ByteArray? {
        val upright = when (photo) {
            is PhotoData.Bitmap -> photo.bitmap
            is PhotoData.HEIC -> decodeHeicUpright(photo)
        } ?: return null
        val scaled = downscale(upright)
        return ByteArrayOutputStream().use { out ->
            if (!scaled.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, out)) return null
            out.toByteArray()
        }
    }

    // HEIC carries orientation in EXIF, which BitmapFactory does not apply.
    private fun decodeHeicUpright(photo: PhotoData.HEIC): Bitmap? {
        val buffer = photo.data.duplicate().apply { rewind() }
        val bytes = ByteArray(buffer.remaining()).also { buffer.get(it) }
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return null
        val degrees = runCatching {
            ByteArrayInputStream(bytes).use { ExifInterface(it).rotationDegrees }
        }.getOrDefault(0)
        if (degrees == 0) return bitmap
        val matrix = Matrix().apply { postRotate(degrees.toFloat()) }
        return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
    }

    private fun downscale(bitmap: Bitmap): Bitmap {
        val longest = maxOf(bitmap.width, bitmap.height)
        if (longest <= MAX_PHOTO_EDGE) return bitmap
        val scale = MAX_PHOTO_EDGE.toFloat() / longest
        return Bitmap.createScaledBitmap(bitmap, (bitmap.width * scale).toInt(), (bitmap.height * scale).toInt(), true)
    }
}
