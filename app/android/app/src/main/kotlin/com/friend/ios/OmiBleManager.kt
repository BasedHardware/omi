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
 * Native Android BLE manager — scanning, GATT lifecycle, characteristic ops, and audio batching.
 * Uses a serialized command queue (Android allows one pending GATT operation at a time).
 * GATT callbacks arrive on binder threads; Pigeon calls are posted to mainHandler.
 */
@SuppressLint("MissingPermission")
class OmiBleManager private constructor(private val application: Application) {

    companion object {
        private const val TAG = "OmiBle"
        private const val RECONNECT_DELAY_MS = 3000L // 3s between retries
        private const val MTU_REQUEST_DELAY_MS = 100L // Small delay for BLE stack stability
        private const val STABILITY_TIMER_MS = 60000L // 60s — reset retry count after stable connection

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

    @Volatile
    var flutterApi: BleFlutterApi? = null

    private val bluetoothManager = application.getSystemService(Application.BLUETOOTH_SERVICE) as BluetoothManager
    private val bluetoothAdapter: BluetoothAdapter? = bluetoothManager.adapter
    private val mainHandler = Handler(Looper.getMainLooper())

    private val connectedGatts = ConcurrentHashMap<String, BluetoothGatt>()
    private val readCompletions = ConcurrentHashMap<String, (Result<ByteArray>) -> Unit>()
    private val writeCompletions = ConcurrentHashMap<String, (Result<Unit>) -> Unit>()
    private val manuallyDisconnected = ConcurrentHashMap.newKeySet<String>()
    @Volatile var appClosed = false

    private val reconnectRetryCount = ConcurrentHashMap<String, Int>()

    private val servicesDiscoveredFor = ConcurrentHashMap.newKeySet<String>()

    private var isScanning = false
    private var scanCallback: ScanCallback? = null
    private var scanTimeoutRunnable: Runnable? = null

    private val gattQueue: ConcurrentLinkedQueue<Runnable> = ConcurrentLinkedQueue()
    @Volatile
    private var isProcessingCommand = false

    private var rssiKeepAliveRunnable: Runnable? = null
    private val rssiKeepAliveInterval = 500L // ms

    private var stabilityTimerRunnable: Runnable? = null
    private var pendingReconnectRunnable: Runnable? = null

    init {
        Log.i(TAG, "OmiBleManager initialized")
    }

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

    fun connectPeripheral(address: String) {
        val addr = address.uppercase()
        appClosed = false
        manuallyDisconnected.remove(addr)
        reconnectRetryCount[addr] = 0

        connectedGatts[addr]?.let { gatt ->
            if (bluetoothManager.getConnectionState(gatt.device, BluetoothProfile.GATT) == BluetoothProfile.STATE_CONNECTED) {
                Log.i(TAG, "connectPeripheral: $addr already connected, re-notifying Dart")
                mainHandler.post { flutterApi?.onPeripheralConnected(addr) {} }
                val services = gatt.services
                if (services != null && services.isNotEmpty()) {
                    val bleServices = services.map { svc ->
                        BleService(
                            uuid = svc.uuid.toString().lowercase(),
                            characteristicUuids = svc.characteristics?.map { it.uuid.toString().lowercase() } ?: emptyList()
                        )
                    }
                    mainHandler.post { flutterApi?.onServicesDiscovered(addr, bleServices) {} }
                }
                return
            }
        }

        connectedGatts[addr]?.close()
        connectedGatts.remove(addr)
        servicesDiscoveredFor.remove(addr)

        val adapter = bluetoothAdapter ?: return
        val device = adapter.getRemoteDevice(addr)
        Log.i(TAG, "connectPeripheral: $addr")
        val gatt = device.connectGatt(application, false, gattCallback, BluetoothDevice.TRANSPORT_LE)
        connectedGatts[addr] = gatt
    }

    fun disconnectPeripheral(address: String) {
        val addr = address.uppercase()
        manuallyDisconnected.add(addr)
        cleanupPeripheral(addr)
        connectedGatts[addr]?.apply {
            disconnect()
            close()
        }
        connectedGatts.remove(addr)
        OmiBleForegroundService.stopService(application)
    }

    fun disconnectAllPeripherals() {
        appClosed = true
        for ((addr, gatt) in connectedGatts) {
            manuallyDisconnected.add(addr)
            cleanupPeripheral(addr)
            gatt.disconnect()
            gatt.close()
        }
        connectedGatts.clear()
        OmiBleForegroundService.stopService(application)
    }

    fun reconnectKnownPeripheral(address: String) {
        val addr = address.uppercase()
        appClosed = false
        manuallyDisconnected.remove(addr)
        reconnectRetryCount[addr] = 0

        if (isPeripheralConnected(addr)) {
            Log.i(TAG, "reconnectKnownPeripheral: $addr already connected, notifying Dart")
            mainHandler.post { flutterApi?.onPeripheralConnected(addr) {} }
            val gatt = connectedGatts[addr]
            val services = gatt?.services
            if (services != null && services.isNotEmpty() && servicesDiscoveredFor.contains(addr)) {
                val bleServices = services.map { svc ->
                    BleService(
                        uuid = svc.uuid.toString().lowercase(),
                        characteristicUuids = svc.characteristics?.map { it.uuid.toString().lowercase() } ?: emptyList()
                    )
                }
                mainHandler.post { flutterApi?.onServicesDiscovered(addr, bleServices) {} }
            }
            return
        }

        connectedGatts[addr]?.close()
        connectedGatts.remove(addr)
        servicesDiscoveredFor.remove(addr)

        val adapter = bluetoothAdapter ?: return
        val device = adapter.getRemoteDevice(addr)
        Log.i(TAG, "reconnectKnownPeripheral: $addr (autoConnect=true)")
        val gatt = device.connectGatt(application, true, gattCallback, BluetoothDevice.TRANSPORT_LE)
        connectedGatts[addr] = gatt
    }

    fun isPeripheralConnected(address: String): Boolean {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr] ?: return false
        return bluetoothManager.getConnectionState(gatt.device, BluetoothProfile.GATT) == BluetoothProfile.STATE_CONNECTED
    }

    fun discoverServices(address: String) {
        val addr = address.uppercase()
        connectedGatts[addr]?.discoverServices()
    }

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
            } else if (writeType == BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) {
                // No onCharacteristicWrite callback for no-response writes
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

        val descriptor = characteristic.getDescriptor(CCCD_UUID)
        enqueueCommand {
            gatt.setCharacteristicNotification(characteristic, true)
            if (descriptor != null) {
                gatt.writeDescriptor(descriptor, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
            } else {
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

    private fun startRssiKeepAlive(address: String) {
        stopRssiKeepAlive()
        val runnable = object : Runnable {
            override fun run() {
                // Direct call — bypasses GATT queue since readRemoteRssi operates at HCI level
                connectedGatts[address]?.readRemoteRssi()
                mainHandler.postDelayed(this, rssiKeepAliveInterval)
            }
        }
        rssiKeepAliveRunnable = runnable
        mainHandler.postDelayed(runnable, rssiKeepAliveInterval)
    }

    private fun stopRssiKeepAlive() {
        rssiKeepAliveRunnable?.let { mainHandler.removeCallbacks(it) }
        rssiKeepAliveRunnable = null
    }

    private fun startStabilityTimer(address: String) {
        stopStabilityTimer()
        val runnable = Runnable {
            Log.i(TAG, "Connection stable for 60s, resetting retry count for $address")
            reconnectRetryCount[address] = 0
        }
        stabilityTimerRunnable = runnable
        mainHandler.postDelayed(runnable, STABILITY_TIMER_MS)
    }

    private fun stopStabilityTimer() {
        stabilityTimerRunnable?.let { mainHandler.removeCallbacks(it) }
        stabilityTimerRunnable = null
    }

    private fun cancelPendingReconnect() {
        pendingReconnectRunnable?.let { mainHandler.removeCallbacks(it) }
        pendingReconnectRunnable = null
    }

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

    @Synchronized
    private fun enqueueCommand(command: Runnable) {
        gattQueue.add(command)
        processNextCommand()
    }

    @Synchronized
    private fun processNextCommand() {
        if (isProcessingCommand) return // Already processing
        val cmd = gattQueue.poll()
        if (cmd != null) {
            isProcessingCommand = true
            mainHandler.post(cmd)
        }
    }

    @Synchronized
    private fun completeCommand() {
        isProcessingCommand = false
        processNextCommand()
    }

    private fun findCharacteristic(gatt: BluetoothGatt?, serviceUuid: String, characteristicUuid: String): BluetoothGattCharacteristic? {
        val service = gatt?.getService(UUID.fromString(serviceUuid)) ?: return null
        return service.getCharacteristic(UUID.fromString(characteristicUuid))
    }

    private fun cleanupPeripheral(address: String) {
        val addr = address.uppercase()
        servicesDiscoveredFor.remove(addr)
        stopRssiKeepAlive()

        for (key in readCompletions.keys().toList().filter { it.startsWith(addr.lowercase()) }) {
            readCompletions.remove(key)?.invoke(Result.failure(Exception("Peripheral disconnected")))
        }
        for (key in writeCompletions.keys().toList().filter { it.startsWith(addr.lowercase()) }) {
            writeCompletions.remove(key)?.invoke(Result.failure(Exception("Peripheral disconnected")))
        }

        gattQueue.clear()
        isProcessingCommand = false
    }

    private val gattCallback = object : BluetoothGattCallback() {

        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            val address = gatt.device.address.uppercase()
            Log.i(TAG, "onConnectionStateChange: address=$address, status=$status, newState=$newState")

            if (connectedGatts[address] != null && connectedGatts[address] !== gatt) {
                Log.w(TAG, "Ignoring stale GATT event from $address")
                return
            }

            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    Log.i(TAG, "Connected to $address, discovering services")
                    connectedGatts[address] = gatt
                    reconnectRetryCount[address] = 0
                    cancelPendingReconnect()

                    OmiBleForegroundService.startService(application, address)
                    OmiBleForegroundService.updateNotificationText("Listening and transcribing")

                    mainHandler.post {
                        flutterApi?.onPeripheralConnected(address) {}
                    }

                    startRssiKeepAlive(address)
                    startStabilityTimer(address)
                    enqueueCommand {
                        if (!gatt.discoverServices()) {
                            Log.e(TAG, "discoverServices returned false")
                            completeCommand()
                        }
                    }
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    Log.i(TAG, "Disconnected from $address (status=$status)")
                    cleanupPeripheral(address)
                    stopStabilityTimer()
                    cancelPendingReconnect()
                    mainHandler.post {
                        flutterApi?.onPeripheralDisconnected(address, if (status != 0) "status=$status" else null) {}
                    }

                    if (!manuallyDisconnected.contains(address)) {
                        val retries = reconnectRetryCount.getOrDefault(address, 0)
                        val isRetryable = status == 0 || RETRYABLE_STATUS_CODES.contains(status)

                        if (isRetryable) {
                            reconnectRetryCount[address] = retries + 1
                            Log.i(TAG, "Auto-reconnecting to $address in ${RECONNECT_DELAY_MS}ms (retry ${retries + 1})")
                            OmiBleForegroundService.updateNotificationText("Reconnecting...")
                            val runnable = Runnable {
                                pendingReconnectRunnable = null
                                gatt.close()
                                connectedGatts.remove(address)
                                val device = bluetoothAdapter?.getRemoteDevice(address) ?: return@Runnable
                                val newGatt = device.connectGatt(application, true, this, BluetoothDevice.TRANSPORT_LE)
                                connectedGatts[address] = newGatt
                            }
                            pendingReconnectRunnable = runnable
                            mainHandler.postDelayed(runnable, RECONNECT_DELAY_MS)
                        } else {
                            Log.w(TAG, "Not retrying $address: non-retryable status=$status")
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
                Log.e(TAG, "MTU request failed for $address (status=$status)")
            } else {
                Log.i(TAG, "MTU changed to $mtu for $address")
            }
            completeCommand()
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            val address = gatt.device.address.uppercase()

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

            if (!gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)) {
                Log.w(TAG, "Failed to request high connection priority")
            }

            completeCommand()

            mainHandler.post {
                flutterApi?.onServicesDiscovered(address, bleServices) {}
            }

            mainHandler.postDelayed({
                enqueueCommand {
                    if (!gatt.requestMtu(512)) {
                        Log.e(TAG, "requestMtu returned false")
                        completeCommand()
                    }
                }
            }, MTU_REQUEST_DELAY_MS)
        }

        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
            val address = gatt.device.address.uppercase()
            val serviceUuid = characteristic.service.uuid.toString().lowercase()
            val charUuid = characteristic.uuid.toString().lowercase()
            mainHandler.post {
                flutterApi?.onCharacteristicValueUpdated(address, serviceUuid, charUuid, value) {}
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

        override fun onReadRemoteRssi(gatt: BluetoothGatt, rssi: Int, status: Int) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.w(TAG, "RSSI read failed: status=$status for ${gatt.device.address}")
            }
        }
    }
}
