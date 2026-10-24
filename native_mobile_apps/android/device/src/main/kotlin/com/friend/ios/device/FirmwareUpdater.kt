package com.friend.ios.device

import android.annotation.SuppressLint
import android.bluetooth.BluetoothManager
import android.content.Context
import android.util.Pair
import io.runtime.mcumgr.ble.McuMgrBleTransport
import io.runtime.mcumgr.dfu.FirmwareUpgradeCallback
import io.runtime.mcumgr.dfu.FirmwareUpgradeController
import io.runtime.mcumgr.dfu.FirmwareUpgradeManager
import io.runtime.mcumgr.exception.McuMgrException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import java.io.File
import java.util.zip.ZipFile

/** Flashes a firmware package to the wearable (real: [McuFirmwareUpdater]; tests: a fake). */
interface FirmwareUpdating {
    /**
     * Uploads `firmware` (an MCUboot OTA zip or a signed .bin on disk) to `deviceID` and has the
     * bootloader install it. Emits upload progress from 0 to 1 and completes once the device took
     * the image and resets into it; throws when it did not. The caller frees the device first:
     * this opens its own Bluetooth connection.
     */
    fun update(deviceID: String, firmware: File): Flow<Double>
}

/**
 * Port of `McuFirmwareUpdater` (`FirmwareUpdater.swift`): Omi firmware update over SMP (MCUmgr)
 * with Nordic's mcumgr-android, the library the Flutter app's `mcumgr_flutter` wraps. The Omi CV1
 * runs MCUboot in overwrite-only mode with two images (app core, network core) and
 * `CONFIG_NCS_SAMPLE_MCUMGR_BT_OTA_DFU` (`omi/firmware/omi/sysbuild.conf`, `omi.conf`). Settings
 * match iOS (`firmware_mixin.dart` `startMCUDfu`).
 */
class McuFirmwareUpdater(context: Context) : FirmwareUpdating {
    private val context = context.applicationContext

    @SuppressLint("MissingPermission")
    override fun update(deviceID: String, firmware: File): Flow<Double> = callbackFlow {
        val images = try {
            McuMgrPackage.images(firmware)
        } catch (e: Exception) {
            close(e)
            awaitClose {}
            return@callbackFlow
        }
        val adapter = (context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager).adapter
        val transport = McuMgrBleTransport(context, adapter.getRemoteDevice(deviceID.uppercase()))
        val total = maxOf(1, images.sumOf { it.second.size })
        // Overall progress across images: the library reports bytes per image.
        var finishedBytes = 0
        var lastSent = 0
        var lastSize = 0
        val callback = object : FirmwareUpgradeCallback {
            override fun onUpgradeStarted(controller: FirmwareUpgradeController?) {}
            override fun onStateChanged(prevState: FirmwareUpgradeManager.State?, newState: FirmwareUpgradeManager.State?) {}

            override fun onUpgradeCompleted() {
                trySend(1.0)
                close()
            }

            override fun onUpgradeFailed(state: FirmwareUpgradeManager.State?, error: McuMgrException?) {
                close(error ?: McuMgrException("upgrade failed in $state"))
            }

            override fun onUpgradeCanceled(state: FirmwareUpgradeManager.State?) {
                close(CancellationException("upgrade canceled"))
            }

            override fun onUploadProgressChanged(bytesSent: Int, imageSize: Int, timestamp: Long) {
                // A smaller count than before means the next image started.
                if (bytesSent < lastSent) finishedBytes += lastSize
                lastSent = bytesSent
                lastSize = imageSize
                trySend(minOf(1.0, (finishedBytes + bytesSent).toDouble() / total))
            }
        }
        val manager = FirmwareUpgradeManager(transport, callback)
        manager.setEstimatedSwapTime(0)
        manager.setWindowUploadCapacity(1)
        manager.setMemoryAlignment(4)
        manager.setMode(FirmwareUpgradeManager.Mode.CONFIRM_ONLY)
        try {
            manager.start(images, true)
        } catch (e: McuMgrException) {
            close(e)
        }
        awaitClose {
            if (manager.isInProgress) manager.cancel()
            transport.release()
        }
    }
}

/** `McuMgrPackage`: the images of an OTA zip (`manifest.json` `files[].image_index`) or a bare .bin. */
object McuMgrPackage {
    fun images(file: File): List<Pair<Int, ByteArray>> {
        if (!file.name.endsWith(".zip", ignoreCase = true)) return listOf(Pair(0, file.readBytes()))
        ZipFile(file).use { zip ->
            val manifest = zip.getEntry("manifest.json") ?: throw IllegalArgumentException("manifest.json missing")
            val json = Json.parseToJsonElement(zip.getInputStream(manifest).readBytes().toString(Charsets.UTF_8)).jsonObject
            val files = json["files"]?.jsonArray ?: throw IllegalArgumentException("manifest.json has no files")
            return files.map { element ->
                val entry = element.jsonObject
                val name = (entry["file"] as? JsonPrimitive)?.content ?: throw IllegalArgumentException("file name missing")
                val index = (entry["image_index"] as? JsonPrimitive)?.content?.toIntOrNull() ?: 0
                val data = zip.getEntry(name)?.let { zip.getInputStream(it).readBytes() } ?: throw IllegalArgumentException("$name missing")
                Pair(index, data)
            }
        }
    }
}
