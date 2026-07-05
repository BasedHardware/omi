// `meta_wearables_dat_flutter` Android plugin.
//
// Bridges Meta's MWDAT* Kotlin SDKs to a Dart MethodChannel + EventChannel
// surface. Responsibilities:
//   * Request runtime permissions (BLUETOOTH_CONNECT etc) on demand.
//   * Registration: startRegistration, startUnregistration, handleUrl
//     (no-op on Android; the SDK consumes deep links via the host
//     activity's intent-filter), plus registration_state and
//     active_device EventChannels.
//   * Streaming: startStreamSession, stopStreamSession, pause/resume,
//     plus session_state, session_errors and video_stream_size
//     EventChannels. Frame plumbing lives in MetaSessionManager.
//   * Mock Device Kit pass-throughs.
//
// Meta's `Wearables.initialize(activity)` is called exactly once, only
// AFTER `BLUETOOTH_CONNECT` is granted - calling it earlier silently
// breaks device discovery. Stream handlers therefore wait on a Mutex/flag
// until init has run; if a Dart subscriber attaches before init,
// collection starts as soon as init fires.

package com.iseelabs.meta_wearables_dat_flutter

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.ComponentActivity
import androidx.activity.result.ActivityResultLauncher
import androidx.core.app.ActivityCompat
import com.meta.wearable.dat.camera.types.VideoQuality
import com.meta.wearable.dat.core.Wearables
import com.meta.wearable.dat.core.selectors.AutoDeviceSelector
import com.meta.wearable.dat.core.types.DeviceIdentifier
import com.meta.wearable.dat.core.types.Permission
import com.meta.wearable.dat.core.types.PermissionStatus
import com.meta.wearable.dat.core.types.RegistrationState
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.embedding.engine.plugins.activity.ActivityAware
import io.flutter.embedding.engine.plugins.activity.ActivityPluginBinding
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.plugin.common.MethodChannel.MethodCallHandler
import io.flutter.plugin.common.MethodChannel.Result
import io.flutter.plugin.common.PluginRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class MetaWearablesDatPlugin :
    FlutterPlugin,
    MethodCallHandler,
    ActivityAware,
    PluginRegistry.RequestPermissionsResultListener {

    private lateinit var channel: MethodChannel
    private lateinit var registrationStateChannel: EventChannel
    private lateinit var activeDeviceChannel: EventChannel
    private lateinit var devicesChannel: EventChannel
    private lateinit var compatibilityChannel: EventChannel
    private lateinit var streamSessionStateChannel: EventChannel
    private lateinit var streamSessionErrorChannel: EventChannel
    private lateinit var deviceSessionStateChannel: EventChannel
    private lateinit var deviceSessionErrorChannel: EventChannel
    private lateinit var videoSizeChannel: EventChannel
    private lateinit var videoFramesChannel: EventChannel
    private lateinit var mockDevicesChannel: EventChannel
    private lateinit var displayStateChannel: EventChannel
    private lateinit var displayEventsChannel: EventChannel

    private var sessionManager: MetaSessionManager? = null
    private var mockManager: MetaMockDeviceManager? = null
    private var displayManager: MetaDisplayManager? = null

    private var activityBinding: ActivityPluginBinding? = null
    private var activity: Activity? = null
    private var appContext: android.content.Context? = null

    private var pendingPermissionResult: Result? = null
    private var pendingCameraPermissionResult: Result? = null

    /**
     * Activity-result launcher driving Meta's
     * `Wearables.RequestPermissionContract`. Registered with the host
     * activity's `ActivityResultRegistry` from `onAttachedToActivity` and
     * unregistered on detach. `null` when the activity has not been
     * attached yet, or when the activity isn't a `ComponentActivity` (in
     * which case `requestCameraPermission` returns
     * `MISSING_FRAGMENT_ACTIVITY`).
     */
    private var cameraPermissionLauncher: ActivityResultLauncher<Permission>? = null

    /**
     * Gated initialisation. Flips to `true` exactly once after
     * `BLUETOOTH_CONNECT` is granted and `Wearables.initialize(activity)`
     * has returned. Stream handlers observe this flow and defer collection
     * until it flips, then start automatically.
     */
    private val wearablesInitialised = MutableStateFlow(false)

    private val pluginScope =
        CoroutineScope(Dispatchers.Main.immediate + SupervisorJob())

    private val registrationStateHandler = RegistrationStateStreamHandler()
    private val activeDeviceHandler = ActiveDeviceStreamHandler()
    private val devicesHandler = DevicesStreamHandler()
    private val compatibilityHandler = CompatibilityStreamHandler()
    private val streamSessionStateHandler = PassthroughStreamHandler { sink ->
        sessionManager?.setStateSink(sink)
    }
    private val streamSessionErrorHandler = PassthroughStreamHandler { sink ->
        sessionManager?.setErrorSink(sink)
    }
    private val deviceSessionStateHandler = PassthroughStreamHandler { sink ->
        sessionManager?.setDeviceStateSink(sink)
    }
    private val deviceSessionErrorHandler = PassthroughStreamHandler { sink ->
        sessionManager?.setDeviceErrorSink(sink)
    }
    private val videoSizeHandler = PassthroughStreamHandler { sink ->
        sessionManager?.setSizeSink(sink)
    }
    private val videoFramesHandler = PassthroughStreamHandler { sink ->
        sessionManager?.setFramesSink(sink)
    }
    private val mockDevicesHandler = PassthroughStreamHandler { sink ->
        mockManager?.setMockDevicesSink(sink)
    }
    private val displayStateHandler = PassthroughStreamHandler { sink ->
        displayManager?.setDisplayStateSink(sink)
    }
    private val displayEventsHandler = PassthroughStreamHandler { sink ->
        displayManager?.setDisplayEventsSink(sink)
    }

    // --- FlutterPlugin --------------------------------------------------------

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        appContext = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, "meta_wearables_dat_flutter")
        channel.setMethodCallHandler(this)

        registrationStateChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/registration_state",
        )
        registrationStateChannel.setStreamHandler(registrationStateHandler)

        activeDeviceChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/active_device",
        )
        activeDeviceChannel.setStreamHandler(activeDeviceHandler)

        devicesChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/devices",
        )
        devicesChannel.setStreamHandler(devicesHandler)

        compatibilityChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/compatibility",
        )
        compatibilityChannel.setStreamHandler(compatibilityHandler)

        streamSessionStateChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/stream_session_state",
        )
        streamSessionStateChannel.setStreamHandler(streamSessionStateHandler)

        streamSessionErrorChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/stream_session_errors",
        )
        streamSessionErrorChannel.setStreamHandler(streamSessionErrorHandler)

        deviceSessionStateChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/device_session_state",
        )
        deviceSessionStateChannel.setStreamHandler(deviceSessionStateHandler)

        deviceSessionErrorChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/device_session_errors",
        )
        deviceSessionErrorChannel.setStreamHandler(deviceSessionErrorHandler)

        videoSizeChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/video_stream_size",
        )
        videoSizeChannel.setStreamHandler(videoSizeHandler)

        videoFramesChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/video_frames",
        )
        videoFramesChannel.setStreamHandler(videoFramesHandler)

        mockDevicesChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/mock_devices",
        )
        mockDevicesChannel.setStreamHandler(mockDevicesHandler)

        displayStateChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/display_state",
        )
        displayStateChannel.setStreamHandler(displayStateHandler)

        displayEventsChannel = EventChannel(
            binding.binaryMessenger,
            "meta_wearables_dat_flutter/display_events",
        )
        displayEventsChannel.setStreamHandler(displayEventsHandler)

        sessionManager = MetaSessionManager(binding.textureRegistry)
        mockManager = MetaMockDeviceManager(binding.applicationContext)
        displayManager = MetaDisplayManager()

        // Force-link Meta's SDK so missing-dependency errors surface here at
        // attach time rather than later when a real method is invoked.
        @Suppress("UNUSED_VARIABLE")
        val wearablesClass = Wearables::class.java
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
        registrationStateChannel.setStreamHandler(null)
        activeDeviceChannel.setStreamHandler(null)
        devicesChannel.setStreamHandler(null)
        compatibilityChannel.setStreamHandler(null)
        streamSessionStateChannel.setStreamHandler(null)
        streamSessionErrorChannel.setStreamHandler(null)
        deviceSessionStateChannel.setStreamHandler(null)
        deviceSessionErrorChannel.setStreamHandler(null)
        videoSizeChannel.setStreamHandler(null)
        videoFramesChannel.setStreamHandler(null)
        mockDevicesChannel.setStreamHandler(null)
        displayStateChannel.setStreamHandler(null)
        displayEventsChannel.setStreamHandler(null)
        registrationStateHandler.cancel()
        activeDeviceHandler.cancel()
        devicesHandler.cancel()
        compatibilityHandler.cancel()
        sessionManager?.dispose()
        sessionManager = null
        mockManager = null
        displayManager?.dispose()
        displayManager = null
        pluginScope.cancel()
    }

    // --- ActivityAware --------------------------------------------------------

    override fun onAttachedToActivity(binding: ActivityPluginBinding) {
        activityBinding = binding
        activity = binding.activity
        binding.addRequestPermissionsResultListener(this)
        registerCameraPermissionLauncher(binding.activity)
    }

    override fun onDetachedFromActivityForConfigChanges() = onDetachedFromActivity()

    override fun onReattachedToActivityForConfigChanges(binding: ActivityPluginBinding) =
        onAttachedToActivity(binding)

    override fun onDetachedFromActivity() {
        activityBinding?.removeRequestPermissionsResultListener(this)
        activityBinding = null
        activity = null
        cameraPermissionLauncher?.unregister()
        cameraPermissionLauncher = null
    }

    private fun registerCameraPermissionLauncher(activity: Activity) {
        if (activity !is ComponentActivity) return
        cameraPermissionLauncher = activity.activityResultRegistry.register(
            "meta_wearables_dat_camera_permission",
            Wearables.RequestPermissionContract(),
        ) { result ->
            val pending = pendingCameraPermissionResult
            pendingCameraPermissionResult = null
            // Wearables.RequestPermissionContract returns
            // `Result<PermissionStatus>` (Meta's own Result type, not
            // kotlin.Result) so we use getOrDefault to coerce to a
            // PermissionStatus regardless of failure shape.
            val status = result.getOrDefault(PermissionStatus.Denied)
            pending?.success(status == PermissionStatus.Granted)
        }
    }

    // --- MethodCallHandler ----------------------------------------------------

    override fun onMethodCall(call: MethodCall, result: Result) {
        when (call.method) {
            "getPlatformVersion" -> result.success("Android ${Build.VERSION.RELEASE}")
            "dumpDiagnostics" -> result.success(dumpDiagnostics())
            "requestAndroidPermissions" -> requestAndroidPermissions(result)
            "startRegistration" -> startRegistration(result)
            "startUnregistration" -> startUnregistration(result)
            "handleUrl" -> handleUrl(result)
            "getRegistrationState" -> getRegistrationState(result)
            "getDevices" -> getDevices(result)
            "openFirmwareUpdate" -> result.error("UNAVAILABLE", "Firmware update flow is handled by Meta AI on iOS.", null)
            "openDATGlassesAppUpdate" -> result.error("UNAVAILABLE", "DAT glasses app update flow is handled by Meta AI on iOS.", null)
            "requestCameraPermission" -> requestCameraPermission(result)
            "getCameraPermissionStatus" -> getCameraPermissionStatus(result)
            "startStreamSession" -> startStreamSession(call, result)
            "stopStreamSession" -> stopStreamSession(result)
            "pauseStreamSession" -> pauseStreamSession(result)
            "resumeStreamSession" -> resumeStreamSession(result)
            "capturePhoto" -> capturePhoto(result)
            "enableBackgroundStreaming" -> enableBackgroundStreaming(call, result)
            "disableBackgroundStreaming" -> disableBackgroundStreaming(result)
            "startDisplaySession" -> startDisplaySession(call, result)
            "sendDisplayView" -> sendDisplayView(call, result)
            "stopDisplaySession" -> stopDisplaySession(result)
            "enableMockDevice" -> mockCall(result) {
                it.enable(
                    call.argument<Boolean>("initiallyRegistered") ?: true,
                    call.argument<Boolean>("initialPermissionsGranted") ?: true,
                )
            }
            "disableMockDevice" -> mockCall(result) { it.disable() }
            "isMockDeviceEnabled" -> mockCallReturning(result) { it.isEnabled() }
            "pairMockRayBanMeta" -> mockCallReturning(result) { it.pairRayBanMeta() }
            "pairedMockDevices" -> mockCallReturning(result) { it.pairedDevices() }
            "unpairMockDevice" -> mockCall(result) {
                it.unpair(call.argument<String>("uuid") ?: "")
            }
            "mockPowerOn" -> mockCall(result) {
                it.powerOn(call.argument<String>("uuid") ?: "")
            }
            "mockPowerOff" -> mockCall(result) {
                it.powerOff(call.argument<String>("uuid") ?: "")
            }
            "mockDon" -> mockCall(result) {
                it.don(call.argument<String>("uuid") ?: "")
            }
            "mockDoff" -> mockCall(result) {
                it.doff(call.argument<String>("uuid") ?: "")
            }
            "mockFold" -> mockCall(result) {
                it.fold(call.argument<String>("uuid") ?: "")
            }
            "mockUnfold" -> mockCall(result) {
                it.unfold(call.argument<String>("uuid") ?: "")
            }
            "setMockCameraFacing" -> mockCall(result) {
                it.setCameraFacing(
                    call.argument<String>("uuid") ?: "",
                    call.argument<String>("facing") ?: "rear",
                )
            }
            "setMockCameraFeed" -> mockCall(result) {
                it.setCameraFeed(
                    call.argument<String>("uuid") ?: "",
                    call.argument<String>("filePath"),
                )
            }
            "setMockCapturedImage" -> mockCall(result) {
                it.setCapturedImage(
                    call.argument<String>("uuid") ?: "",
                    call.argument<String>("filePath"),
                )
            }
            "setMockPermission" -> mockCall(result) {
                it.setPermission(
                    call.argument<String>("permission") ?: "",
                    call.argument<String>("status") ?: "",
                )
            }
            "setMockPermissionRequestResult" -> mockCall(result) {
                it.setPermissionRequestResult(
                    call.argument<String>("permission") ?: "",
                    call.argument<String>("status") ?: "",
                )
            }
            else -> result.notImplemented()
        }
    }

    private inline fun mockCall(result: Result, block: (MetaMockDeviceManager) -> Unit) {
        val manager = mockManager ?: run {
            result.error("MOCK_ERROR", "Mock manager unavailable", null)
            return
        }
        try {
            block(manager)
            result.success(null)
        } catch (e: Exception) {
            result.error("MOCK_ERROR", e.message ?: e::class.java.simpleName, null)
        }
    }

    private inline fun <T> mockCallReturning(
        result: Result,
        block: (MetaMockDeviceManager) -> T,
    ) {
        val manager = mockManager ?: run {
            result.error("MOCK_ERROR", "Mock manager unavailable", null)
            return
        }
        try {
            result.success(block(manager))
        } catch (e: Exception) {
            result.error("MOCK_ERROR", e.message ?: e::class.java.simpleName, null)
        }
    }

    private fun capturePhoto(result: Result) {
        val manager = sessionManager
        if (manager == null) {
            result.error(
                "CAPTURE_ERROR",
                "Plugin not attached to engine.",
                null,
            )
            return
        }
        pluginScope.launch {
            try {
                val (bytes, format) = manager.capturePhoto()
                result.success(mapOf("bytes" to bytes, "format" to format))
            } catch (e: Exception) {
                result.error(
                    "CAPTURE_ERROR",
                    e.message ?: e::class.java.simpleName,
                    null,
                )
            }
        }
    }

    // --- Background streaming --------------------------------------------------

    private fun enableBackgroundStreaming(call: MethodCall, result: Result) {
        val act = activity ?: appContext
        if (act == null) {
            result.error(
                "NO_ACTIVITY",
                "Cannot enable background streaming without an Activity or " +
                    "application Context.",
                null,
            )
            return
        }
        val notification = call.argument<Map<String, Any?>>("androidNotification")
        if (notification == null) {
            result.error(
                "SESSION_ERROR",
                "androidNotification is required on Android. Pass a " +
                    "BackgroundNotification with title/text/channelId/channelName.",
                null,
            )
            return
        }
        if (!ensurePostNotificationsPermission(act)) {
            android.util.Log.w(
                "MetaWearablesDat",
                "POST_NOTIFICATIONS is not yet granted; the foreground " +
                    "service notification may be suppressed. Request the " +
                    "permission from your host app on API 33+.",
            )
        }
        val intent = android.content.Intent(
            act.applicationContext,
            BackgroundStreamingService::class.java,
        ).apply {
            putExtra(
                BackgroundStreamingService.EXTRA_TITLE,
                notification["title"] as? String,
            )
            putExtra(
                BackgroundStreamingService.EXTRA_TEXT,
                notification["text"] as? String,
            )
            putExtra(
                BackgroundStreamingService.EXTRA_CHANNEL_ID,
                notification["channelId"] as? String,
            )
            putExtra(
                BackgroundStreamingService.EXTRA_CHANNEL_NAME,
                notification["channelName"] as? String,
            )
            putExtra(
                BackgroundStreamingService.EXTRA_ICON_RESOURCE_NAME,
                notification["iconResourceName"] as? String,
            )
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                act.applicationContext.startForegroundService(intent)
            } else {
                act.applicationContext.startService(intent)
            }
            result.success(null)
        } catch (e: Throwable) {
            result.error(
                "SESSION_ERROR",
                "Failed to start BackgroundStreamingService: ${e.message}",
                null,
            )
        }
    }

    private fun disableBackgroundStreaming(result: Result) {
        val act = activity ?: appContext
        if (act == null) {
            result.success(null)
            return
        }
        try {
            act.applicationContext.stopService(
                android.content.Intent(
                    act.applicationContext,
                    BackgroundStreamingService::class.java,
                ),
            )
            result.success(null)
        } catch (e: Throwable) {
            result.success(null)
        }
    }

    /**
     * Best-effort runtime request for `POST_NOTIFICATIONS` on API 33+.
     * Returns `true` if the permission is currently granted (i.e. the
     * foreground-service notification will display). The actual prompt
     * is fire-and-forget; host apps that want a synchronous answer
     * should pre-request the permission themselves through `permission_handler`
     * or `requestAndroidPermissions` first.
     */
    private fun ensurePostNotificationsPermission(
        context: android.content.Context,
    ): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        val granted = ActivityCompat.checkSelfPermission(
            context,
            "android.permission.POST_NOTIFICATIONS",
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) {
            val act = activity
            if (act != null) {
                ActivityCompat.requestPermissions(
                    act,
                    arrayOf("android.permission.POST_NOTIFICATIONS"),
                    PERMISSION_REQUEST_CODE,
                )
            }
        }
        return granted
    }

    // --- Streaming flow -------------------------------------------------------

    private fun startStreamSession(call: MethodCall, result: Result) {
        val manager = sessionManager
        if (manager == null) {
            result.error(
                "SESSION_ERROR",
                "Plugin not attached to engine.",
                null,
            )
            return
        }
        val deviceUuid = call.argument<String>("deviceUuid")
        val fps = call.argument<Int>("fps") ?: 30
        val qualityRaw = call.argument<String>("quality") ?: "high"
        val quality = when (qualityRaw) {
            "low" -> VideoQuality.LOW
            "medium" -> VideoQuality.MEDIUM
            else -> VideoQuality.HIGH
        }
        val deviceKinds = call.argument<List<String>>("deviceKinds")?.toSet()
        val videoCodec = call.argument<String>("videoCodec") ?: "raw"
        pluginScope.launch {
            try {
                val id = manager.startSession(
                    deviceUuid,
                    fps,
                    quality,
                    deviceKinds,
                    videoCodec,
                )
                result.success(id)
            } catch (e: Exception) {
                result.error(
                    "SESSION_ERROR",
                    e.message ?: e::class.java.simpleName,
                    null,
                )
            }
        }
    }

    private fun stopStreamSession(result: Result) {
        val manager = sessionManager ?: run { result.success(null); return }
        pluginScope.launch {
            manager.stopSession()
            result.success(null)
        }
    }

    // --- Display --------------------------------------------------------------

    private fun startDisplaySession(call: MethodCall, result: Result) {
        val manager = displayManager
        if (manager == null) {
            result.error("DISPLAY_ERROR", "Plugin not attached to engine.", null)
            return
        }
        val deviceUuid = call.argument<String>("deviceUuid")
        pluginScope.launch {
            try {
                manager.startDisplaySession(deviceUuid)
                result.success(null)
            } catch (e: Exception) {
                result.error(
                    "DISPLAY_ERROR",
                    e.message ?: e::class.java.simpleName,
                    null,
                )
            }
        }
    }

    private fun sendDisplayView(call: MethodCall, result: Result) {
        val manager = displayManager
        if (manager == null) {
            result.error("DISPLAY_ERROR", "Plugin not attached to engine.", null)
            return
        }
        @Suppress("UNCHECKED_CAST")
        val view = call.argument<Map<String, Any?>>("view") ?: emptyMap()
        pluginScope.launch {
            try {
                manager.sendDisplayView(view)
                result.success(null)
            } catch (e: Exception) {
                result.error(
                    "DISPLAY_ERROR",
                    e.message ?: e::class.java.simpleName,
                    null,
                )
            }
        }
    }

    private fun stopDisplaySession(result: Result) {
        displayManager?.stopDisplaySession()
        result.success(null)
    }

    private fun pauseStreamSession(result: Result) {
        sessionManager?.pauseSession()
        result.success(null)
    }

    private fun resumeStreamSession(result: Result) {
        sessionManager?.resumeSession()
        result.success(null)
    }

    // --- Diagnostics ----------------------------------------------------------

    /// Mirrors the iOS `dumpDiagnostics` shape so cross-platform UIs can
    /// render the same map. Android's permission/manifest validation happens
    /// at runtime rather than at SDK init, so the `preflight` block is
    /// intentionally minimal.
    private fun dumpDiagnostics(): Map<String, Any?> {
        val act = activity
        val ctx = act ?: appContext
        val pkg = ctx?.packageName
        val pm = ctx?.packageManager
        val appInfo = if (pkg != null && pm != null) {
            try {
                pm.getApplicationInfo(
                    pkg,
                    PackageManager.GET_META_DATA,
                )
            } catch (_: Throwable) {
                null
            }
        } else {
            null
        }
        val metaData = appInfo?.metaData
        val applicationId = metaData?.get(
            "com.meta.wearable.mwdat.APPLICATION_ID",
        )?.toString()
        val clientToken = metaData?.get(
            "com.meta.wearable.mwdat.CLIENT_TOKEN",
        )?.toString()

        val regState: Int = try {
            // SDK 0.6.x: `RegistrationState` is a sealed class, not an
            // enum, so it has no `.ordinal`. Reuse the cross-platform
            // int mapping `stateToInt` already implements via `is` checks.
            stateToInt(Wearables.registrationState.value)
        } catch (_: Throwable) {
            -1
        }

        val bluetoothConnectGranted = if (act != null) {
            ActivityCompat.checkSelfPermission(
                act,
                Manifest.permission.BLUETOOTH_CONNECT,
            ) == PackageManager.PERMISSION_GRANTED
        } else {
            false
        }

        return mapOf(
            "platform" to "Android",
            "androidVersion" to Build.VERSION.RELEASE,
            "sdkInt" to Build.VERSION.SDK_INT,
            "bundleId" to (pkg ?: "<unknown>"),
            "wearablesInitialised" to wearablesInitialised.value,
            "registrationState" to mapOf(
                "raw" to regState,
                "name" to runCatching {
                    // DAT 0.7 `RegistrationState` is an enum; use the entry
                    // name (e.g. "REGISTERED").
                    (Wearables.registrationState.value as? Enum<*>)?.name ?: "unknown"
                }.getOrDefault("unknown"),
            ),
            "manifestMetaData" to mapOf(
                "applicationId" to applicationId,
                "clientToken" to clientToken,
            ),
            "preflight" to mapOf(
                "bluetoothConnectGranted" to bluetoothConnectGranted,
                "applicationIdNonEmpty" to !applicationId.isNullOrEmpty(),
            ),
        )
    }

    // --- Permission flow ------------------------------------------------------

    private fun requestAndroidPermissions(result: Result) {
        val act = activity
        if (act == null) {
            result.error(
                "NO_ACTIVITY",
                "No Activity is attached to the plugin. Are you calling " +
                    "requestAndroidPermissions before runApp / before the engine " +
                    "is attached?",
                null,
            )
            return
        }

        val required = requiredPermissions()
        val missing = required.filter { perm ->
            ActivityCompat.checkSelfPermission(act, perm) !=
                PackageManager.PERMISSION_GRANTED
        }

        if (missing.isEmpty()) {
            ensureWearablesInitialised()
            result.success(true)
            return
        }

        if (pendingPermissionResult != null) {
            result.error(
                "ALREADY_REQUESTING",
                "A permission request is already in flight.",
                null,
            )
            return
        }

        pendingPermissionResult = result
        ActivityCompat.requestPermissions(
            act,
            missing.toTypedArray(),
            PERMISSION_REQUEST_CODE,
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ): Boolean {
        if (requestCode != PERMISSION_REQUEST_CODE) return false

        val pending = pendingPermissionResult ?: return true
        pendingPermissionResult = null

        val allGranted = grantResults.isNotEmpty() &&
            grantResults.all { it == PackageManager.PERMISSION_GRANTED }

        if (allGranted) {
            ensureWearablesInitialised()
        }
        pending.success(allGranted)
        return true
    }

    /**
     * Initialises Meta's DAT SDK exactly once, only after BLUETOOTH_CONNECT
     * has been granted. See plan risk 2.
     */
    private fun ensureWearablesInitialised() {
        if (wearablesInitialised.value) return
        val act = activity ?: return
        Wearables.initialize(act)
        wearablesInitialised.value = true
    }

    private fun requiredPermissions(): List<String> {
        val perms = mutableListOf(Manifest.permission.INTERNET)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            perms += Manifest.permission.BLUETOOTH_CONNECT
        }
        return perms
    }

    // --- Registration flow ----------------------------------------------------

    private fun startRegistration(result: Result) {
        val act = activity
        if (act == null) {
            result.error(
                "NO_ACTIVITY",
                "Cannot start registration without an Activity. Make sure your " +
                    "MainActivity extends FlutterFragmentActivity.",
                null,
            )
            return
        }
        try {
            Wearables.startRegistration(act)
            result.success(null)
        } catch (e: Exception) {
            result.error(
                "REGISTRATION_ERROR",
                e.message ?: e::class.java.simpleName,
                null,
            )
        }
    }

    private fun startUnregistration(result: Result) {
        val act = activity
        if (act == null) {
            result.error(
                "NO_ACTIVITY",
                "Cannot start unregistration without an Activity.",
                null,
            )
            return
        }
        try {
            Wearables.startUnregistration(act)
            result.success(null)
        } catch (e: Exception) {
            val caseName = e::class.java.simpleName ?: "unknown"
            result.error(
                "UNREGISTRATION_ERROR",
                caseName,
                mapOf(
                    "case" to caseName,
                    "description" to (e.message ?: caseName),
                ),
            )
        }
    }

    /**
     * Documented no-op on Android. Meta's Android SDK consumes the
     * registration callback through the host activity's intent-filter
     * automatically, not through an explicit `handleUrl` API. Host apps
     * still need to declare the matching intent-filter and use
     * `launchMode="singleTop"`. See `doc/registration_flow.md`.
     *
     * Mirrors iOS by returning `false` for consumed (no callback) rather
     * than throwing `HANDLE_URL_ERROR` - on Android, deep-links flow
     * through the manifest intent-filter and the SDK reacts internally.
     */
    private fun handleUrl(result: Result) {
        result.success(false)
    }

    private fun getRegistrationState(result: Result) {
        if (!wearablesInitialised.value) {
            result.success(stateToInt(null))
            return
        }
        pluginScope.launch {
            val state = Wearables.registrationState.first()
            result.success(stateToInt(state))
        }
    }

    /**
     * One-shot snapshot of every currently-paired device. Mirrors the iOS
     * `encodeAllDevices()` shape consumed by `DeviceInfo.fromMap`. Returns
     * an empty list when the SDK is not yet initialised so callers can
     * call this unconditionally during startup.
     */
    private fun getDevices(result: Result) {
        if (!wearablesInitialised.value) {
            result.success(emptyList<Map<String, Any?>>())
            return
        }
        pluginScope.launch {
            val ids = try {
                Wearables.devices.first()
            } catch (_: Throwable) {
                emptyList()
            }
            result.success(encodeDevices(ids))
        }
    }

    // --- Camera permission ----------------------------------------------------

    private fun requestCameraPermission(result: Result) {
        val launcher = cameraPermissionLauncher
        if (launcher == null) {
            result.error(
                "MISSING_FRAGMENT_ACTIVITY",
                "Camera permission requires the host Activity to extend " +
                    "FlutterFragmentActivity (a ComponentActivity). See " +
                    "doc/getting_started.md for the required MainActivity " +
                    "snippet.",
                null,
            )
            return
        }
        if (pendingCameraPermissionResult != null) {
            result.error(
                "ALREADY_REQUESTING",
                "A camera permission request is already in flight.",
                null,
            )
            return
        }
        pendingCameraPermissionResult = result
        launcher.launch(Permission.CAMERA)
    }

    private fun getCameraPermissionStatus(result: Result) {
        pluginScope.launch {
            val outcome = Wearables.checkPermissionStatus(Permission.CAMERA)
            // Wearables.checkPermissionStatus returns Meta's own `Result`
            // wrapper. Treat any failure as "not granted" - host apps can
            // call requestCameraPermission to surface the underlying
            // PermissionError, if any.
            val status = outcome.getOrDefault(PermissionStatus.Denied)
            result.success(status == PermissionStatus.Granted)
        }
    }

    // --- Stream handlers ------------------------------------------------------

    /**
     * Forwards `Wearables.registrationState` to a Flutter EventSink as
     * `Int` values matching Dart's `RegistrationState.fromInt`. Defers
     * collection until `wearablesInitialised` flips to `true`.
     */
    private inner class RegistrationStateStreamHandler : EventChannel.StreamHandler {
        private var job: Job? = null

        override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
            job?.cancel()
            job = pluginScope.launch {
                wearablesInitialised.first { it }
                Wearables.registrationState.collectLatest { state ->
                    events.success(stateToInt(state))
                }
            }
        }

        override fun onCancel(arguments: Any?) {
            job?.cancel()
            job = null
        }

        fun cancel() {
            job?.cancel()
            job = null
        }
    }

    /**
     * Forwards `AutoDeviceSelector().activeDeviceFlow()` to a Flutter
     * EventSink as a serialised `DeviceInfo` map (or `null` when no device
     * is active). Long-lived: the selector instance is recreated per
     * subscription so old jobs don't leak across hot restarts.
     */
    private inner class ActiveDeviceStreamHandler : EventChannel.StreamHandler {
        private var job: Job? = null

        override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
            job?.cancel()
            job = pluginScope.launch {
                wearablesInitialised.first { it }
                val selector = AutoDeviceSelector()
                selector.activeDeviceFlow().collectLatest { deviceId ->
                    events.success(encodeDeviceWithMetadata(deviceId))
                }
            }
        }

        override fun onCancel(arguments: Any?) {
            job?.cancel()
            job = null
        }

        fun cancel() {
            job?.cancel()
            job = null
        }
    }

    /**
     * Forwards `Wearables.devices` events as the full list of paired
     * devices (active or not) on the `meta_wearables_dat_flutter/devices`
     * channel. The current value is delivered eagerly on subscribe.
     */
    private inner class DevicesStreamHandler : EventChannel.StreamHandler {
        private var job: Job? = null

        override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
            job?.cancel()
            job = pluginScope.launch {
                wearablesInitialised.first { it }
                Wearables.devices.collectLatest { ids ->
                    events.success(encodeDevices(ids))
                }
            }
        }

        override fun onCancel(arguments: Any?) {
            job?.cancel()
            job = null
        }

        fun cancel() {
            job?.cancel()
            job = null
        }
    }

    /**
     * Forwards per-device compatibility updates on the
     * `meta_wearables_dat_flutter/compatibility` channel.
     *
     * Listens to `Wearables.devices` for the paired-device set and to
     * `Wearables.devicesMetadata[id]` for each individual device's
     * compatibility verdict. Per-device collection jobs are torn down as
     * soon as the device leaves the paired set so we don't leak jobs.
     */
    private inner class CompatibilityStreamHandler : EventChannel.StreamHandler {
        private var rootJob: Job? = null
        private val perDeviceJobs = mutableMapOf<DeviceIdentifier, Job>()

        override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
            cancel()
            rootJob = pluginScope.launch {
                wearablesInitialised.first { it }
                Wearables.devices.collectLatest { ids ->
                    val live = ids.toSet()
                    // Cancel jobs for devices that have left the set.
                    perDeviceJobs.keys.toList().forEach { id ->
                        if (!live.contains(id)) {
                            perDeviceJobs.remove(id)?.cancel()
                        }
                    }
                    for (id in live) {
                        if (perDeviceJobs.containsKey(id)) continue
                        val flow = try {
                            Wearables.devicesMetadata[id]
                        } catch (_: Throwable) {
                            null
                        } ?: continue
                        perDeviceJobs[id] = pluginScope.launch {
                            flow.collectLatest { meta ->
                                events.success(
                                    mapOf(
                                        "deviceUuid" to id.toString(),
                                        "compatibility" to compatibilityForMetadata(meta),
                                    ),
                                )
                            }
                        }
                    }
                }
            }
        }

        override fun onCancel(arguments: Any?) {
            cancel()
        }

        fun cancel() {
            rootJob?.cancel()
            rootJob = null
            perDeviceJobs.values.forEach { it.cancel() }
            perDeviceJobs.clear()
        }
    }

    // --- Helpers --------------------------------------------------------------

    /**
     * Maps `RegistrationState` to the int value the Dart enum understands
     * (`unavailable=0, available=1, registering=2, registered=3`). DAT 0.7's
     * `RegistrationState` is an enum, so we key off the (normalised) entry
     * name - `UNREGISTERING` is treated as transitional `registering` and
     * anything unrecognised falls back to `unavailable`.
     */
    private fun stateToInt(state: RegistrationState?): Int =
        when (state?.name?.uppercase()?.replace("_", "")) {
            null -> 0
            "REGISTERED" -> 3
            "REGISTERING" -> 2
            "UNREGISTERING" -> 2
            "AVAILABLE" -> 1
            else -> 0
        }

    /**
     * Serialises a [DeviceIdentifier] to the map shape that
     * `DeviceInfo.fromMap` expects on the Dart side, or `null` when no
     * device is active.
     *
     * Looks up `Wearables.devicesMetadata[id]` for richer fields
     * (display name, device kind). When metadata isn't ready yet we fall
     * back to the id as the name and `unknown` as the kind.
     */
    private suspend fun encodeDeviceWithMetadata(
        id: DeviceIdentifier?,
    ): Map<String, Any?>? {
        if (id == null) return null
        val meta = try {
            Wearables.devicesMetadata[id]?.first()
        } catch (_: Throwable) {
            null
        }
        val idString = id.toString()
        return mapOf(
            "uuid" to idString,
            "name" to (nameForMetadata(meta) ?: idString),
            "kind" to wireKindForMetadata(meta),
        )
    }

    /**
     * Encodes every paired device as the `DeviceInfo.fromMap` shape.
     * Looks up each device's metadata for richer fields. Best-effort:
     * metadata can be missing on hot start.
     */
    internal suspend fun encodeDevices(
        // Accept `Collection` so callers can pass `Wearables.devices`'s
        // `Set<DeviceIdentifier>` directly without an extra `.toList()`.
        ids: Collection<DeviceIdentifier>,
    ): List<Map<String, Any?>> {
        return ids.map { id ->
            val meta = try {
                Wearables.devicesMetadata[id]?.first()
            } catch (_: Throwable) {
                null
            }
            val idString = id.toString()
            mapOf(
                "uuid" to idString,
                "name" to (nameForMetadata(meta) ?: idString),
                "kind" to wireKindForMetadata(meta),
            )
        }
    }

    companion object {
        // Arbitrary unique request code; range 1..65535 per Android.
        private const val PERMISSION_REQUEST_CODE = 10_001

        /**
         * Returns the wire-kind string (`rayBanMeta` / `rayBanDisplay` /
         * `oakleyMeta` / `unknown`) for the given device identifier.
         * Uses the latest cached metadata when available. Best-effort:
         * returns `unknown` when metadata isn't ready yet.
         */
        suspend fun wireKindForDevice(id: DeviceIdentifier): String {
            val meta = try {
                Wearables.devicesMetadata[id]?.first()
            } catch (_: Throwable) {
                null
            }
            return wireKindForMetadata(meta)
        }

        /**
         * Maps a `DeviceMetadata`-shaped object to the cross-platform
         * wire kind. Uses reflection so we don't depend on the precise
         * shape of `DeviceMetadata` (it has changed between SDK
         * versions). Falls back to `unknown` when the shape can't be
         * matched.
         */
        fun wireKindForMetadata(meta: Any?): String {
            if (meta == null) return "unknown"
            val typeValue = try {
                meta::class.java.methods.firstOrNull { m ->
                    m.parameterCount == 0 && (
                        m.name == "getDeviceType" ||
                            m.name == "getType" ||
                            m.name == "getKind"
                        )
                }?.invoke(meta)
            } catch (_: Throwable) {
                null
            } ?: return "unknown"

            val rawName = (typeValue as? Enum<*>)?.name ?: typeValue.toString()
            // Normalise to a canonical lower-case for matching against
            // SDK enum case names we know about across versions.
            val normalised = rawName
                .lowercase()
                .replace("_", "")
                .replace("-", "")
            return when {
                "raybanmetadisplay" in normalised ||
                    "metaraybandisplay" in normalised ||
                    "raybandisplay" in normalised -> "rayBanDisplay"
                "raybanmeta" in normalised -> "rayBanMeta"
                "oakleyhstn" in normalised ||
                    "oakleyvanguard" in normalised ||
                    "oakleymeta" in normalised -> "oakleyMeta"
                else -> "unknown"
            }
        }

        /**
         * Reflection-based extraction of a human-readable name from a
         * `DeviceMetadata`-shaped object. Returns `null` when no name
         * field is present.
         */
        fun nameForMetadata(meta: Any?): String? {
            if (meta == null) return null
            return try {
                meta::class.java.methods.firstOrNull { m ->
                    m.parameterCount == 0 && (
                        m.name == "getName" ||
                            m.name == "getDisplayName" ||
                            m.name == "getDeviceName"
                        )
                }?.invoke(meta) as? String
            } catch (_: Throwable) {
                null
            }
        }

        /**
         * Reflection-based extraction of compatibility verdict from a
         * `DeviceMetadata`-shaped object. Returns the canonical
         * cross-platform string (`compatible`, `deviceUpdateRequired`,
         * `sdkUpdateRequired`, `unknown`).
         */
        fun compatibilityForMetadata(meta: Any?): String {
            if (meta == null) return "unknown"
            val raw = try {
                meta::class.java.methods.firstOrNull { m ->
                    m.parameterCount == 0 && (
                        m.name == "getCompatibility" ||
                            m.name == "getCompatibilityStatus"
                        )
                }?.invoke(meta)
            } catch (_: Throwable) {
                null
            } ?: return "unknown"
            val name = (raw as? Enum<*>)?.name ?: raw.toString()
            val normalised = name.lowercase().replace("_", "").replace("-", "")
            return when {
                "compatible" == normalised -> "compatible"
                "deviceupdaterequired" in normalised -> "deviceUpdateRequired"
                "sdkupdaterequired" in normalised -> "sdkUpdateRequired"
                else -> "unknown"
            }
        }
    }
}

/**
 * Tiny [EventChannel.StreamHandler] that simply hands its EventSink off to a
 * callback - lets the [MetaSessionManager] decide when to emit values
 * rather than baking that logic into the channel handler itself.
 */
internal class PassthroughStreamHandler(
    private val onSinkChange: (EventChannel.EventSink?) -> Unit,
) : EventChannel.StreamHandler {
    override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
        onSinkChange(events)
    }

    override fun onCancel(arguments: Any?) {
        onSinkChange(null)
    }
}
