// Android Mock Device Kit bridge.
//
// Wraps `MockDeviceKit.getInstance(context)` and exposes its surface to
// the Dart facade. Paired devices are sourced from `kit.pairedDevices`
// on demand and keyed by `device.deviceIdentifier.toString()`, so the
// kit remains the single source of truth — disable/enable cycles can't
// leave stale dictionary entries behind.
//
// Mock devices ship from `mwdat-mockdevice` and are intended for
// hardware-less development. Production builds that do not want mock
// device code in the binary should strip the dependency from
// `build.gradle` instead — the plugin returns `MOCK_ERROR` cleanly when
// the kit is not linked.

package com.iseelabs.meta_wearables_dat_flutter

import android.content.Context
import android.net.Uri
import android.util.Log
import com.meta.wearable.dat.mockdevice.MockDeviceKit
import com.meta.wearable.dat.mockdevice.api.MockRaybanMeta
import com.meta.wearable.dat.mockdevice.api.camera.CameraFacing
import io.flutter.plugin.common.EventChannel

internal class MetaMockDeviceManager(context: Context) {

    private companion object {
        private const val TAG = "MWDATMockDevice"
    }

    // SDK 0.6.x: `MockDeviceKit.getInstance(...)` returns `MockDeviceKitInterface`,
    // not `MockDeviceKit` itself. Letting Kotlin infer the type keeps the field
    // compatible across any future repackaging of the implementation class.
    private val kit = MockDeviceKit.getInstance(context.applicationContext)

    private var sink: EventChannel.EventSink? = null

    /**
     * Tracks whether `kit.enable()` has been called by this plugin.
     * `MockDeviceKit.isEnabled` is not exposed on the Android SDK 0.6.x
     * Kotlin API, so we mirror it here.
     */
    private var enabled: Boolean = false

    fun setMockDevicesSink(sink: EventChannel.EventSink?) {
        this.sink = sink
        emitDevices()
    }

    // --- Lifecycle ------------------------------------------------------

    /**
     * Enables (or re-enables) MockDeviceKit. The
     * `initiallyRegistered` / `initialPermissionsGranted` overrides are
     * currently unsupported on the Android SDK; this method logs a
     * structured warning when either is non-default but still enables
     * the kit so test harnesses don't crash.
     */
    fun enable(initiallyRegistered: Boolean, initialPermissionsGranted: Boolean) {
        if (!initiallyRegistered || !initialPermissionsGranted) {
            Log.w(
                TAG,
                "enableMockDevice: initiallyRegistered/" +
                    "initialPermissionsGranted overrides are not yet " +
                    "supported on Android; enabling MockDeviceKit with " +
                    "default settings.",
            )
        }
        if (enabled) {
            kit.disable()
            enabled = false
        }
        kit.enable()
        enabled = true
        emitDevices()
    }

    fun disable() {
        if (enabled) {
            kit.disable()
            enabled = false
        }
        emitDevices()
    }

    fun isEnabled(): Boolean = enabled

    // --- Pairing --------------------------------------------------------

    fun pairRayBanMeta(): String {
        ensureEnabled()
        val mock = kit.pairRaybanMeta()
        emitDevices()
        return mock.deviceIdentifier.toString()
    }

    fun unpair(uuid: String) {
        val mock = requireDevice(uuid)
        kit.unpairDevice(mock)
        emitDevices()
    }

    /** Returns a serialisable snapshot of every paired mock device. */
    fun pairedDevices(): List<Map<String, Any?>> =
        kit.pairedDevices.map(::encodeDevice)

    // --- Device control -------------------------------------------------

    fun powerOn(uuid: String) {
        requireDevice(uuid).powerOn()
    }

    fun powerOff(uuid: String) {
        requireDevice(uuid).powerOff()
    }

    fun don(uuid: String) {
        requireDevice(uuid).don()
    }

    fun doff(uuid: String) {
        requireDevice(uuid).doff()
    }

    fun fold(uuid: String) {
        requireDevice(uuid).fold()
    }

    fun unfold(uuid: String) {
        requireDevice(uuid).unfold()
    }

    // --- Permissions (kit-level) ----------------------------------------

    /**
     * The Android `MockDeviceKit` 0.6.x surface does not expose a
     * programmatic permission-injection hook analogous to iOS's
     * `MockDeviceKit.shared.permissions`. We retain the method for API
     * parity with iOS so the Dart facade has a uniform shape, but emit
     * a structured warning that is no-op'd until Meta lights up the
     * Kotlin equivalent.
     */
    @Suppress("UNUSED_PARAMETER")
    fun setPermission(permission: String, status: String) {
        Log.w(
            TAG,
            "setMockPermission: MockPermissions API is not yet exposed " +
                "on Android (permission=$permission status=$status). " +
                "Treating call as no-op.",
        )
    }

    @Suppress("UNUSED_PARAMETER")
    fun setPermissionRequestResult(permission: String, status: String) {
        Log.w(
            TAG,
            "setMockPermissionRequestResult: MockPermissions API is not " +
                "yet exposed on Android (permission=$permission " +
                "status=$status). Treating call as no-op.",
        )
    }

    // --- Camera ---------------------------------------------------------

    fun setCameraFacing(uuid: String, facing: String) {
        // SDK 0.6.x: the enum value is `BACK` (not `REAR`).
        val mapped = when (facing.lowercase()) {
            "front" -> CameraFacing.FRONT
            else -> CameraFacing.BACK
        }
        requireDevice(uuid).services.camera.setCameraFeed(mapped)
    }

    fun setCameraFeed(uuid: String, filePath: String?) {
        val device = requireDevice(uuid)
        if (filePath.isNullOrEmpty()) return
        device.services.camera.setCameraFeed(Uri.parse("file://$filePath"))
    }

    fun setCapturedImage(uuid: String, filePath: String?) {
        val device = requireDevice(uuid)
        if (filePath.isNullOrEmpty()) return
        device.services.camera.setCapturedImage(Uri.parse("file://$filePath"))
    }

    // --- Helpers --------------------------------------------------------

    private fun ensureEnabled() {
        if (!enabled) {
            kit.enable()
            enabled = true
        }
    }

    private fun requireDevice(uuid: String): MockRaybanMeta {
        val device = kit.pairedDevices.find {
            it.deviceIdentifier.toString() == uuid
        } ?: error("Mock device not found: $uuid")
        if (device !is MockRaybanMeta) {
            error("Mock device $uuid is not a Ray-Ban Meta")
        }
        return device
    }

    private fun emitDevices() {
        sink?.success(pairedDevices())
    }

    private fun encodeDevice(device: Any): Map<String, Any?> {
        val id = when (device) {
            is MockRaybanMeta -> device.deviceIdentifier.toString()
            else -> device.toString()
        }
        return mapOf(
            "uuid" to id,
            "name" to "Mock Ray-Ban Meta",
            "kind" to "rayBanMeta",
        )
    }
}
