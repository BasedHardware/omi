package com.friend.ios

import android.annotation.SuppressLint
import android.app.Application
import android.bluetooth.*
import android.bluetooth.le.*
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.util.Log
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * Native Android BLE manager that handles scanning, GATT connection lifecycle,
 * service discovery, characteristic operations, and audio batching.
 *
 * Port of OmiBleManager.swift using Android's BluetoothManager API.
 * Uses a GATT command queue (Android only allows one pending operation at a time).
 *
 * Thread safety: All mutable state uses ConcurrentHashMap or is guarded by synchronized blocks.
 * GATT callbacks run on a binder thread; Pigeon calls are posted to mainHandler.
 */
@SuppressLint("MissingPermission")
class OmiBleManager private constructor(private val application: Application) {

    companion object {
        private const val TAG = "OmiBle"
        private const val MAX_RECONNECT_RETRIES = 3
        private const val RECONNECT_DELAY_MS = 1000L // 1s between retries
        private const val MTU_REQUEST_DELAY_MS = 100L // Small delay for BLE stack stability

        /** GATT status codes that are transient and worth retrying. */
        private val RETRYABLE_STATUS_CODES = setOf(8, 19, 62, 133, 257)

        @Volatile
        private var _instance: OmiBleManager? = null

        val instance: OmiBleManager
            get() = _instance ?: throw IllegalStateException("OmiBleManager not initialized")

        fun initialize(application: Application) {
            if (_instance == null) {
                synchronized(this) {
                    if (_instance == null) {
                        _instance = OmiBleManager(application)
                    }
                }
            }
        }

        /** CCCD UUID for enabling/disabling notifications. */
        private val CCCD_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")
    }

    // Pigeon Flutter API for callbacks to Dart
    @Volatile
    var flutterApi: BleFlutterApi? = null

    private val bluetoothManager = application.getSystemService(Application.BLUETOOTH_SERVICE) as BluetoothManager
    private val bluetoothAdapter: BluetoothAdapter? = bluetoothManager.adapter
    private val mainHandler = Handler(Looper.getMainLooper())

    // Thread-safe collections for state accessed from GATT binder thread + main thread
    private val connectedGatts = ConcurrentHashMap<String, BluetoothGatt>()
    private val readCompletions = ConcurrentHashMap<String, (Result<ByteArray>) -> Unit>()
    private val writeCompletions = ConcurrentHashMap<String, (Result<Unit>) -> Unit>()
    private val manuallyDisconnected = ConcurrentHashMap.newKeySet<String>()

    // Reconnect retry tracking per device
    private val reconnectRetryCount = ConcurrentHashMap<String, Int>()

    // Track whether services have been discovered for this connection cycle
    // Prevents duplicate discovery when MTU response arrives after Dart-initiated discovery
    private val servicesDiscoveredFor = ConcurrentHashMap.newKeySet<String>()

    // Scanning state (main thread only)
    private var isScanning = false
    private var scanCallback: ScanCallback? = null
    private var scanTimeoutRunnable: Runnable? = null

    // GATT command queue — Android only allows ONE pending GATT operation at a time
    private val gattQueue: ConcurrentLinkedQueue<Runnable> = ConcurrentLinkedQueue()
    @Volatile
    private var isProcessingCommand = false

    // Audio batching
    private val audioCharacteristicUuids = ConcurrentHashMap.newKeySet<String>()
    @Volatile
    private var audioBatchingEnabled = false
    private val audioBatchBuffers = ConcurrentHashMap<String, ByteArray>()
    private val audioBatchCounts = ConcurrentHashMap<String, Int>()
    private val audioBatchRunnables = ConcurrentHashMap<String, Runnable>()
    private val audioBatchInterval = 60L // ms
    private val audioBatchMaxSize = 4096
    var audioHeaderBytesToStrip = 3

    init {
        Log.i(TAG, "OmiBleManager initialized")
    }

    // ============================================================
    // Scanning
    // ============================================================

    fun startScan(timeout: Int, serviceUuids: List<String>) {
        val state = getBluetoothState()
        Log.i(TAG, "startScan called, state=$state, timeout=$timeout, serviceUuids=$serviceUuids")

        val adapter = bluetoothAdapter ?: return
        if (!adapter.isEnabled) {
            Log.w(TAG, "Bluetooth not enabled, cannot scan")
            return
        }

        stopScan()

        val scanner = adapter.bluetoothLeScanner ?: return

        val filters = if (serviceUuids.isNotEmpty()) {
            serviceUuids.map { uuid ->
                ScanFilter.Builder()
                    .setServiceUuid(ParcelUuid(UUID.fromString(uuid)))
                    .build()
            }
        } else {
            null
        }

        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()

        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val device = result.device
                val address = device.address.uppercase()
                val name = device.name ?: ""
                val rssi = result.rssi
                val advServiceUuids = result.scanRecord?.serviceUuids?.map { it.uuid.toString() } ?: emptyList()

                val peripheral = BlePeripheral(
                    uuid = address,
                    name = name,
                    rssi = rssi.toLong(),
                    serviceUuids = advServiceUuids
                )
                mainHandler.post {
                    flutterApi?.onPeripheralDiscovered(peripheral) {}
                }
            }
        }
        scanCallback = callback
        isScanning = true

        if (filters != null) {
            scanner.startScan(filters, settings, callback)
        } else {
            scanner.startScan(null, settings, callback)
        }

        if (timeout > 0) {
            val runnable = Runnable { stopScan() }
            scanTimeoutRunnable = runnable
            mainHandler.postDelayed(runnable, timeout * 1000L)
        }
    }

    fun stopScan() {
        if (!isScanning) return
        isScanning = false

        scanTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }
        scanTimeoutRunnable = null

        scanCallback?.let { cb ->
            try {
                bluetoothAdapter?.bluetoothLeScanner?.stopScan(cb)
            } catch (e: Exception) {
                Log.w(TAG, "stopScan failed: ${e.message}")
            }
        }
        scanCallback = null
    }

    // ============================================================
    // Connection
    // ============================================================

    fun connectPeripheral(address: String) {
        val addr = address.uppercase()
        manuallyDisconnected.remove(addr)
        reconnectRetryCount[addr] = 0

        // Already connected?
        connectedGatts[addr]?.let { gatt ->
            if (bluetoothManager.getConnectionState(gatt.device, BluetoothProfile.GATT) == BluetoothProfile.STATE_CONNECTED) {
                mainHandler.post { flutterApi?.onPeripheralConnected(addr) {} }
                return
            }
        }

        // Close stale GATT before new connection
        connectedGatts[addr]?.close()
        connectedGatts.remove(addr)

        val adapter = bluetoothAdapter ?: return
        val device = adapter.getRemoteDevice(addr)
        Log.i(TAG, "connectPeripheral: $addr (autoConnect=true)")
        // autoConnect=true so the BLE controller maintains the connection in background
        val gatt = device.connectGatt(application, true, gattCallback, BluetoothDevice.TRANSPORT_LE)
        connectedGatts[addr] = gatt
    }

    fun disconnectPeripheral(address: String) {
        val addr = address.uppercase()
        manuallyDisconnected.add(addr)
        connectedGatts[addr]?.apply {
            disconnect()
            close()
        }
        connectedGatts.remove(addr)
        // Stop foreground service — user explicitly disconnected
        OmiBleForegroundService.stopService(application)
    }

    /** Disconnect all peripherals. Called when Bluetooth is turned off. */
    fun disconnectAllPeripherals() {
        for ((addr, gatt) in connectedGatts) {
            manuallyDisconnected.add(addr)
            gatt.disconnect()
            gatt.close()
        }
        connectedGatts.clear()
        OmiBleForegroundService.stopService(application)
    }

    fun reconnectKnownPeripheral(address: String) {
        val addr = address.uppercase()
        manuallyDisconnected.remove(addr)
        reconnectRetryCount[addr] = 0

        // Close existing GATT before reconnecting
        connectedGatts[addr]?.close()
        connectedGatts.remove(addr)

        val adapter = bluetoothAdapter ?: return
        val device = adapter.getRemoteDevice(addr)
        Log.i(TAG, "reconnectKnownPeripheral: $addr (autoConnect=true)")
        // autoConnect=true queues at the BLE controller level — zero CPU/radio until device is in range
        val gatt = device.connectGatt(application, true, gattCallback, BluetoothDevice.TRANSPORT_LE)
        connectedGatts[addr] = gatt
    }

    fun isPeripheralConnected(address: String): Boolean {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr] ?: return false
        return bluetoothManager.getConnectionState(gatt.device, BluetoothProfile.GATT) == BluetoothProfile.STATE_CONNECTED
    }

    // ============================================================
    // Service Discovery
    // ============================================================

    fun discoverServices(address: String) {
        val addr = address.uppercase()
        connectedGatts[addr]?.discoverServices()
    }

    // ============================================================
    // Characteristic Operations (queued)
    // ============================================================

    fun readCharacteristic(
        address: String,
        serviceUuid: String,
        characteristicUuid: String,
        completion: (Result<ByteArray>) -> Unit
    ) {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr]
        val characteristic = findCharacteristic(gatt, serviceUuid, characteristicUuid)
        if (gatt == null || characteristic == null) {
            completion(Result.failure(Exception("Characteristic not found")))
            return
        }

        val key = "$addr:$serviceUuid:$characteristicUuid".lowercase()
        readCompletions[key] = completion

        enqueueCommand {
            if (!gatt.readCharacteristic(characteristic)) {
                Log.e(TAG, "readCharacteristic returned false for $key")
                readCompletions.remove(key)?.invoke(Result.failure(Exception("Read request rejected")))
                completeCommand()
            }
        }
    }

    fun writeCharacteristic(
        address: String,
        serviceUuid: String,
        characteristicUuid: String,
        data: ByteArray,
        completion: (Result<Unit>) -> Unit
    ) {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr]
        val characteristic = findCharacteristic(gatt, serviceUuid, characteristicUuid)
        if (gatt == null || characteristic == null) {
            completion(Result.failure(Exception("Characteristic not found")))
            return
        }

        val writeType = if (characteristic.properties and BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE != 0) {
            BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
        } else {
            BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        }

        val key = "$addr:$serviceUuid:$characteristicUuid".lowercase()
        if (writeType == BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) {
            writeCompletions[key] = completion
        }

        enqueueCommand {
            val result = gatt.writeCharacteristic(characteristic, data, writeType)
            if (result != BluetoothStatusCodes.SUCCESS) {
                Log.e(TAG, "writeCharacteristic returned $result for $key")
                writeCompletions.remove(key)?.invoke(Result.failure(Exception("Write request rejected: $result")))
                completeCommand()
            }
        }

        if (writeType == BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) {
            completion(Result.success(Unit))
        }
    }

    fun subscribeCharacteristic(address: String, serviceUuid: String, characteristicUuid: String) {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr] ?: return
        val characteristic = findCharacteristic(gatt, serviceUuid, characteristicUuid) ?: return

        // Queue both setCharacteristicNotification + CCCD write together to avoid race
        val descriptor = characteristic.getDescriptor(CCCD_UUID)
        enqueueCommand {
            gatt.setCharacteristicNotification(characteristic, true)
            if (descriptor != null) {
                gatt.writeDescriptor(descriptor, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
            } else {
                // No CCCD — complete immediately
                completeCommand()
            }
        }
    }

    fun unsubscribeCharacteristic(address: String, serviceUuid: String, characteristicUuid: String) {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr] ?: return
        val characteristic = findCharacteristic(gatt, serviceUuid, characteristicUuid) ?: return

        val descriptor = characteristic.getDescriptor(CCCD_UUID)
        enqueueCommand {
            gatt.setCharacteristicNotification(characteristic, false)
            if (descriptor != null) {
                gatt.writeDescriptor(descriptor, BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE)
            } else {
                completeCommand()
            }
        }
    }

    // ============================================================
    // Audio Batching
    // ============================================================

    fun setAudioBatchingEnabled(enabled: Boolean) {
        audioBatchingEnabled = enabled
        if (!enabled) {
            for (key in audioBatchBuffers.keys().toList()) {
                flushAudioBatch(key)
            }
        }
    }

    fun registerAudioCharacteristic(characteristicUuid: String) {
        audioCharacteristicUuids.add(characteristicUuid.lowercase())
    }

    // ============================================================
    // Bluetooth State
    // ============================================================

    fun getBluetoothState(): String {
        val adapter = bluetoothAdapter ?: return "unsupported"
        return when (adapter.state) {
            BluetoothAdapter.STATE_ON -> "on"
            BluetoothAdapter.STATE_OFF -> "off"
            BluetoothAdapter.STATE_TURNING_ON -> "resetting"
            BluetoothAdapter.STATE_TURNING_OFF -> "resetting"
            else -> "unknown"
        }
    }

    // ============================================================
    // GATT Command Queue
    // ============================================================

    private fun enqueueCommand(command: Runnable) {
        gattQueue.add(command)
        if (!isProcessingCommand) processNextCommand()
    }

    private fun processNextCommand() {
        val cmd = gattQueue.poll()
        if (cmd != null) {
            isProcessingCommand = true
            mainHandler.post(cmd)
        } else {
            isProcessingCommand = false
        }
    }

    private fun completeCommand() {
        isProcessingCommand = false
        processNextCommand()
    }

    // ============================================================
    // Private Helpers
    // ============================================================

    private fun findCharacteristic(gatt: BluetoothGatt?, serviceUuid: String, characteristicUuid: String): BluetoothGattCharacteristic? {
        val service = gatt?.getService(UUID.fromString(serviceUuid)) ?: return null
        return service.getCharacteristic(UUID.fromString(characteristicUuid))
    }

    private fun isAudioCharacteristic(characteristicUuid: String): Boolean {
        return audioCharacteristicUuids.contains(characteristicUuid.lowercase())
    }

    private fun handleAudioNotification(address: String, serviceUuid: String, charUuid: String, data: ByteArray) {
        val key = "$address|$serviceUuid|$charUuid".lowercase()

        val isFirstInBatch = audioBatchBuffers[key] == null || audioBatchBuffers[key]!!.isEmpty()
        if (isFirstInBatch) {
            audioBatchBuffers[key] = ByteArray(0)
            audioBatchCounts[key] = 0
        }

        val bytesToAppend = if (isFirstInBatch) {
            data // Keep first frame's header intact
        } else if (audioHeaderBytesToStrip > 0 && data.size > audioHeaderBytesToStrip) {
            data.copyOfRange(audioHeaderBytesToStrip, data.size)
        } else {
            data
        }

        audioBatchBuffers[key] = audioBatchBuffers[key]!! + bytesToAppend
        audioBatchCounts[key] = audioBatchCounts[key]!! + 1

        // Flush if buffer exceeds max size
        if (audioBatchBuffers[key]!!.size >= audioBatchMaxSize) {
            flushAudioBatch(key)
            return
        }

        // Start coalescing timer if not already running
        if (audioBatchRunnables[key] == null) {
            val runnable = Runnable { flushAudioBatch(key) }
            audioBatchRunnables[key] = runnable
            mainHandler.postDelayed(runnable, audioBatchInterval)
        }
    }

    private fun flushAudioBatch(key: String) {
        audioBatchRunnables[key]?.let { mainHandler.removeCallbacks(it) }
        audioBatchRunnables.remove(key)

        val buffer = audioBatchBuffers[key] ?: return
        if (buffer.isEmpty()) return
        val count = audioBatchCounts[key] ?: return

        val parts = key.split("|")
        if (parts.size != 3) return

        val address = parts[0]
        val serviceUuid = parts[1]
        val charUuid = parts[2]

        audioBatchBuffers[key] = ByteArray(0)
        audioBatchCounts[key] = 0

        mainHandler.post {
            flutterApi?.onAudioBatchReceived(address, serviceUuid, charUuid, buffer, count.toLong()) {}
        }
    }

    private fun cleanupPeripheral(address: String) {
        val addr = address.uppercase()
        servicesDiscoveredFor.remove(addr)

        // Flush pending audio batches
        for (key in audioBatchBuffers.keys().toList().filter { it.startsWith(addr.lowercase()) }) {
            flushAudioBatch(key)
            audioBatchBuffers.remove(key)
            audioBatchCounts.remove(key)
            audioBatchRunnables[key]?.let { mainHandler.removeCallbacks(it) }
            audioBatchRunnables.remove(key)
        }

        // Fail pending completions
        for (key in readCompletions.keys().toList().filter { it.startsWith(addr.lowercase()) }) {
            readCompletions.remove(key)?.invoke(Result.failure(Exception("Peripheral disconnected")))
        }
        for (key in writeCompletions.keys().toList().filter { it.startsWith(addr.lowercase()) }) {
            writeCompletions.remove(key)?.invoke(Result.failure(Exception("Peripheral disconnected")))
        }

        // Clear command queue
        gattQueue.clear()
        isProcessingCommand = false
    }

    // ============================================================
    // BluetoothGattCallback
    // ============================================================

    private val gattCallback = object : BluetoothGattCallback() {

        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            val address = gatt.device.address.uppercase()
            Log.i(TAG, "onConnectionStateChange: address=$address, status=$status, newState=$newState")

            // Validate this is the current GATT instance (ignore stale events)
            if (connectedGatts[address] != null && connectedGatts[address] !== gatt) {
                Log.w(TAG, "Ignoring stale GATT event from $address")
                return
            }

            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    Log.i(TAG, "Connected to $address, requesting MTU after ${MTU_REQUEST_DELAY_MS}ms")
                    connectedGatts[address] = gatt
                    reconnectRetryCount[address] = 0 // Reset retries on successful connect

                    // Start foreground service to keep process alive in background
                    OmiBleForegroundService.startService(application, address)
                    OmiBleForegroundService.updateNotificationText("Listening and transcribing")

                    mainHandler.post {
                        flutterApi?.onPeripheralConnected(address) {}
                    }

                    // Request high connection priority for background stability
                    if (!gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)) {
                        Log.w(TAG, "requestConnectionPriority(HIGH) returned false")
                    }

                    // Delay MTU request slightly for BLE stack stability
                    mainHandler.postDelayed({
                        if (!gatt.requestMtu(512)) {
                            Log.e(TAG, "requestMtu returned false, discovering services directly")
                            gatt.discoverServices()
                        }
                    }, MTU_REQUEST_DELAY_MS)
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    Log.i(TAG, "Disconnected from $address (status=$status)")
                    cleanupPeripheral(address)
                    mainHandler.post {
                        flutterApi?.onPeripheralDisconnected(address, if (status != 0) "status=$status" else null) {}
                    }

                    // Auto-reconnect unless manually disconnected
                    if (!manuallyDisconnected.contains(address)) {
                        val retries = reconnectRetryCount.getOrDefault(address, 0)
                        val isRetryable = status == 0 || RETRYABLE_STATUS_CODES.contains(status)

                        if (isRetryable && retries < MAX_RECONNECT_RETRIES) {
                            reconnectRetryCount[address] = retries + 1
                            val delay = RECONNECT_DELAY_MS * (retries + 1) // Simple linear backoff
                            Log.i(TAG, "Auto-reconnecting to $address in ${delay}ms (retry ${retries + 1}/$MAX_RECONNECT_RETRIES)")
                            OmiBleForegroundService.updateNotificationText("Reconnecting...")
                            mainHandler.postDelayed({
                                gatt.close()
                                connectedGatts.remove(address)
                                val device = bluetoothAdapter?.getRemoteDevice(address) ?: return@postDelayed
                                val newGatt = device.connectGatt(application, true, this, BluetoothDevice.TRANSPORT_LE)
                                connectedGatts[address] = newGatt
                            }, delay)
                        } else {
                            Log.w(TAG, "Not retrying $address: retryable=$isRetryable, retries=$retries, status=$status")
                            OmiBleForegroundService.updateNotificationText("Connection failed")
                            gatt.close()
                            connectedGatts.remove(address)
                        }
                    } else {
                        gatt.close()
                        connectedGatts.remove(address)
                    }
                }
            }
        }

        override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) {
            val address = gatt.device.address.uppercase()
            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.e(TAG, "MTU request failed for $address (status=$status), discovering services anyway")
            } else {
                Log.i(TAG, "MTU changed to $mtu for $address")
            }
            // Skip if services already discovered (Dart may have triggered discovery first)
            if (servicesDiscoveredFor.contains(address)) {
                Log.i(TAG, "Services already discovered for $address, skipping")
                return
            }
            gatt.discoverServices()
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            val address = gatt.device.address.uppercase()

            // Skip duplicate discovery callbacks
            if (servicesDiscoveredFor.contains(address)) {
                Log.i(TAG, "Ignoring duplicate onServicesDiscovered for $address")
                return
            }

            Log.i(TAG, "Services discovered for $address (status=$status)")

            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.e(TAG, "Service discovery failed for $address (status=$status)")
                return
            }

            val services = gatt.services ?: return
            val bleServices = services.map { svc ->
                BleService(
                    uuid = svc.uuid.toString().lowercase(),
                    characteristicUuids = svc.characteristics?.map { it.uuid.toString().lowercase() } ?: emptyList()
                )
            }

            servicesDiscoveredFor.add(address)

            mainHandler.post {
                flutterApi?.onServicesDiscovered(address, bleServices) {}
            }
        }

        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
            val address = gatt.device.address.uppercase()
            val serviceUuid = characteristic.service.uuid.toString().lowercase()
            val charUuid = characteristic.uuid.toString().lowercase()

            if (audioBatchingEnabled && isAudioCharacteristic(charUuid)) {
                handleAudioNotification(address, serviceUuid, charUuid, value)
            } else {
                mainHandler.post {
                    flutterApi?.onCharacteristicValueUpdated(address, serviceUuid, charUuid, value) {}
                }
            }
        }

        override fun onCharacteristicRead(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray, status: Int) {
            val address = gatt.device.address.uppercase()
            val serviceUuid = characteristic.service.uuid.toString().lowercase()
            val charUuid = characteristic.uuid.toString().lowercase()
            val key = "$address:$serviceUuid:$charUuid".lowercase()

            val completion = readCompletions.remove(key)
            if (status == BluetoothGatt.GATT_SUCCESS) {
                completion?.invoke(Result.success(value))
            } else {
                completion?.invoke(Result.failure(Exception("Read failed with status $status")))
            }

            completeCommand()
        }

        override fun onCharacteristicWrite(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            val address = gatt.device.address.uppercase()
            val serviceUuid = characteristic.service.uuid.toString().lowercase()
            val charUuid = characteristic.uuid.toString().lowercase()
            val key = "$address:$serviceUuid:$charUuid".lowercase()

            val completion = writeCompletions.remove(key)
            if (status == BluetoothGatt.GATT_SUCCESS) {
                completion?.invoke(Result.success(Unit))
            } else {
                completion?.invoke(Result.failure(Exception("Write failed with status $status")))
            }

            completeCommand()
        }

        override fun onDescriptorWrite(gatt: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.e(TAG, "Descriptor write failed (status=$status) for ${descriptor.characteristic.uuid}")
            }
            completeCommand()
        }
    }
}
