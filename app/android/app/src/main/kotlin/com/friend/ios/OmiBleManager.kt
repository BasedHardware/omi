package com.friend.ios

import android.annotation.SuppressLint
import android.app.Application
import android.bluetooth.*
import android.bluetooth.le.*
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import android.util.Log
import androidx.core.content.ContextCompat
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * Pure GATT wrapper — scanning, characteristic ops, and command queue.
 * Connection lifecycle (connect, retry, reconnect) is owned by OmiBleForegroundService.
 * Uses a serialized command queue (Android allows one pending GATT operation at a time).
 * GATT callbacks arrive on binder threads; Pigeon calls are posted to mainHandler.
 */
@SuppressLint("MissingPermission")
class OmiBleManager private constructor(private val application: Application) {

    companion object {
        private const val TAG = "OmiBle"
        private const val RSSI_HISTORY_LIMIT = 10
        private const val BOND_TIMEOUT_MS = 15000L // 15s — bond request timeout
        private const val PREFS_BATTERY = "battery_history"
        private const val MAX_BATTERY_HISTORY = 2000
        private const val BATTERY_RETENTION_MS = 7L * 24 * 3600 * 1000
        private val BATTERY_LEVEL_CHAR_UUID = UUID.fromString("00002a19-0000-1000-8000-00805f9b34fb")

        @Volatile
        private var _instance: OmiBleManager? = null

        val instance: OmiBleManager
            get() = _instance ?: throw IllegalStateException("OmiBleManager not initialized")

        val isInitialized: Boolean
            get() = _instance != null

        /** True while the Flutter engine is alive. Set in MainActivity.configureFlutterEngine,
         *  cleared in MainActivity.onDestroy(isFinishing). CompanionService checks this to
         *  avoid starting the foreground service when the app is dead — Omi needs the Flutter
         *  app for WebSocket audio streaming. */
        @Volatile
        var isFlutterAlive: Boolean = false

        /** True while MainActivity is resumed. Set from onResume/onPause. Used to tag
         *  diagnostic disconnect events with the app lifecycle state at the moment of the event. */
        @Volatile
        var isAppForeground: Boolean = false

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

    // ── Listener for the foreground service ──

    interface BleConnectionListener {
        fun onGattConnected(address: String, gatt: BluetoothGatt)
        fun onGattDisconnected(address: String, gattHash: Int, status: Int)
        fun onGattServicesDiscovered(address: String, services: List<BleService>)
        fun onMtuChanged(address: String, mtu: Int, status: Int)
    }

    @Volatile
    var connectionListener: BleConnectionListener? = null

    @Volatile
    var flutterApi: BleFlutterApi? = null

    private val bluetoothManager = application.getSystemService(Application.BLUETOOTH_SERVICE) as BluetoothManager
    private val bluetoothAdapter: BluetoothAdapter? = bluetoothManager.adapter
    val mainHandler = Handler(Looper.getMainLooper())

    val connectedGatts = ConcurrentHashMap<String, BluetoothGatt>()
    private val readCompletions = ConcurrentHashMap<String, (Result<ByteArray>) -> Unit>()
    private val writeCompletions = ConcurrentHashMap<String, (Result<Unit>) -> Unit>()

    private val servicesDiscoveredFor = ConcurrentHashMap.newKeySet<String>()

    private var isScanning = false
    private var scanCallback: ScanCallback? = null
    private var scanTimeoutRunnable: Runnable? = null

    private val gattQueue: ConcurrentLinkedQueue<Runnable> = ConcurrentLinkedQueue()
    @Volatile
    private var isProcessingCommand = false

    private var rssiKeepAliveRunnable: Runnable? = null
    private val rssiKeepAliveInterval = 3000L // ms
    @Volatile
    var isRssiStreamingEnabled = false

    /// Most recent RSSI per device (uppercase MAC). Used by the foreground service
    /// to annotate disconnect events so we can tell range-driven drops from healthy-signal drops.
    val lastRssi = java.util.concurrent.ConcurrentHashMap<String, Int>()

    /// Sliding window of recent (timestamp_ms, rssi_dbm) samples per device, used
    /// by the foreground service to classify RSSI trajectory at disconnect time.
    /// Synchronized on the deque itself for reader/writer safety.
    val rssiHistory = java.util.concurrent.ConcurrentHashMap<String, java.util.ArrayDeque<Pair<Long, Int>>>()

    private var bondCompletionCallback: ((Boolean) -> Unit)? = null
    private var bondTimeoutRunnable: Runnable? = null
    private var bondingAddress: String? = null

    private val bondStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != BluetoothDevice.ACTION_BOND_STATE_CHANGED) return
            val device = intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE) ?: return
            val bondState = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.BOND_NONE)
            val address = device.address.uppercase()

            Log.i(TAG, "Bond state changed: $address → $bondState")
            if (address != bondingAddress) return
            when (bondState) {
                BluetoothDevice.BOND_BONDED -> {
                    Log.i(TAG, "Bonding complete for $address")
                    bondingAddress = null
                    bondTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }
                    bondTimeoutRunnable = null
                    bondCompletionCallback?.invoke(true)
                    bondCompletionCallback = null
                }
                BluetoothDevice.BOND_NONE -> {
                    Log.w(TAG, "Bonding failed/removed for $address")
                    bondingAddress = null
                    bondTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }
                    bondTimeoutRunnable = null
                    bondCompletionCallback?.invoke(false)
                    bondCompletionCallback = null
                }
            }
        }
    }

    init {
        Log.i(TAG, "OmiBleManager initialized")
        application.registerReceiver(bondStateReceiver, IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED))
    }

    // ── Scanning ──

    fun startScan(timeout: Int, serviceUuids: List<String>) {
        val state = getBluetoothState()
        Log.i(TAG, "startScan called, state=$state, timeout=$timeout, serviceUuids=$serviceUuids")

        val adapter = bluetoothAdapter ?: return
        if (!adapter.isEnabled) {
            Log.w(TAG, "Bluetooth not enabled, cannot scan")
            return
        }

        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S &&
            ContextCompat.checkSelfPermission(application, android.Manifest.permission.BLUETOOTH_SCAN) != PackageManager.PERMISSION_GRANTED) {
            Log.w(TAG, "BLUETOOTH_SCAN permission not granted, cannot scan")
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

    // ── GATT connection methods ──

    fun connectGatt(address: String, autoConnect: Boolean): BluetoothGatt? {
        val addr = address.uppercase()
        val adapter = bluetoothAdapter ?: return null
        // Use getRemoteLeDevice with ADDRESS_TYPE_RANDOM to specify the correct address type.
        val device = if (android.os.Build.VERSION.SDK_INT >= 34) {
            adapter.getRemoteLeDevice(addr, BluetoothDevice.ADDRESS_TYPE_RANDOM)
        } else {
            adapter.getRemoteDevice(addr)
        }
        val callback = createGattCallback()
        val gatt = device.connectGatt(application, autoConnect, callback, BluetoothDevice.TRANSPORT_LE)
        if (gatt != null) {
            connectedGatts[addr] = gatt
        } else {
            Log.e(TAG, "connectGatt returned null for $addr")
        }
        return gatt
    }

    fun disconnectGatt(address: String) {
        connectedGatts[address.uppercase()]?.disconnect()
    }

    fun closeGatt(address: String) {
        val addr = address.uppercase()
        cleanupPeripheral(addr)
        connectedGatts[addr]?.close()
        connectedGatts.remove(addr)
    }

    fun isPeripheralConnected(address: String): Boolean {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr] ?: return false
        return bluetoothManager.getConnectionState(gatt.device, BluetoothProfile.GATT) == BluetoothProfile.STATE_CONNECTED
    }

    // ── Bonding ──

    fun requestBond(address: String, completion: (Result<Boolean>) -> Unit) {
        val addr = address.uppercase()
        val device = connectedGatts[addr]?.device
        if (device == null) {
            completion(Result.failure(Exception("Device not connected")))
            return
        }
        val state = device.bondState
        if (state == BluetoothDevice.BOND_BONDED) {
            Log.i(TAG, "requestBond: $addr already bonded")
            completion(Result.success(true))
            return
        }
        bondingAddress = addr
        bondCompletionCallback = { bonded -> completion(Result.success(bonded)) }
        val timeoutRunnable = Runnable {
            bondTimeoutRunnable = null
            bondingAddress = null
            Log.w(TAG, "requestBond: $addr bond timeout")
            bondCompletionCallback?.invoke(false)
            bondCompletionCallback = null
        }
        bondTimeoutRunnable = timeoutRunnable
        mainHandler.postDelayed(timeoutRunnable, BOND_TIMEOUT_MS)
        if (state == BluetoothDevice.BOND_BONDING) {
            // Peripheral already initiated SMP (firmware's bt_conn_set_security).
            // Don't call createBond() again — it can spawn a second pair dialog or restart SMP.
            Log.i(TAG, "requestBond: $addr already bonding, awaiting completion")
            return
        }
        Log.i(TAG, "requestBond: $addr initiating bond")
        device.createBond()
    }

    // ── Characteristic operations ──

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
            @Suppress("deprecation")
            val success = if (Build.VERSION.SDK_INT >= 33) {
                val result = gatt.writeCharacteristic(characteristic, data, writeType)
                if (result != BluetoothStatusCodes.SUCCESS) {
                    Log.e(TAG, "writeCharacteristic returned $result for $key")
                }
                result == BluetoothStatusCodes.SUCCESS
            } else {
                characteristic.value = data
                characteristic.writeType = writeType
                gatt.writeCharacteristic(characteristic)
            }
            if (!success) {
                Log.e(TAG, "writeCharacteristic failed for $key")
                writeCompletions.remove(key)?.invoke(Result.failure(Exception("Write request rejected")))
                completeCommand()
            } else if (writeType == BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) {
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
                writeDescriptorCompat(gatt, descriptor, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
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
                writeDescriptorCompat(gatt, descriptor, BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE)
            } else {
                completeCommand()
            }
        }
    }

    // ── RSSI keep-alive ──

    fun startRssiKeepAlive(address: String) {
        stopRssiKeepAlive()
        val runnable = object : Runnable {
            override fun run() {
                connectedGatts[address]?.readRemoteRssi()
                mainHandler.postDelayed(this, rssiKeepAliveInterval)
            }
        }
        rssiKeepAliveRunnable = runnable
        mainHandler.postDelayed(runnable, rssiKeepAliveInterval)
    }

    fun stopRssiKeepAlive() {
        rssiKeepAliveRunnable?.let { mainHandler.removeCallbacks(it) }
        rssiKeepAliveRunnable = null
    }

    // ── State & utility ──

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

    // ── Command queue ──

    @Synchronized
    fun enqueueCommand(command: Runnable) {
        gattQueue.add(command)
        processNextCommand()
    }

    @Synchronized
    private fun processNextCommand() {
        if (isProcessingCommand) return
        val cmd = gattQueue.peek() ?: return
        isProcessingCommand = true
        try {
            mainHandler.post(cmd)
        } catch (e: Exception) {
            Log.e(TAG, "Error posting command: ${e.message}")
            completeCommand()
        }
    }

    @Synchronized
    fun completeCommand() {
        gattQueue.poll()
        isProcessingCommand = false
        processNextCommand()
    }

    private fun findCharacteristic(gatt: BluetoothGatt?, serviceUuid: String, characteristicUuid: String): BluetoothGattCharacteristic? {
        val service = gatt?.getService(UUID.fromString(serviceUuid)) ?: return null
        return service.getCharacteristic(UUID.fromString(characteristicUuid))
    }

    @Suppress("deprecation")
    private fun writeDescriptorCompat(gatt: BluetoothGatt, descriptor: BluetoothGattDescriptor, value: ByteArray) {
        val success = if (Build.VERSION.SDK_INT >= 33) {
            gatt.writeDescriptor(descriptor, value) == BluetoothStatusCodes.SUCCESS
        } else {
            descriptor.value = value
            gatt.writeDescriptor(descriptor)
        }
        if (!success) {
            Log.e(TAG, "writeDescriptor failed for ${descriptor.uuid}")
            completeCommand()
        }
    }

    fun cleanupPeripheral(address: String) {
        val addr = address.uppercase()
        servicesDiscoveredFor.remove(addr)
        stopRssiKeepAlive()
        bondingAddress = null
        bondTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }
        bondTimeoutRunnable = null
        bondCompletionCallback?.invoke(false)
        bondCompletionCallback = null

        for (key in readCompletions.keys().toList().filter { it.startsWith(addr.lowercase()) }) {
            readCompletions.remove(key)?.invoke(Result.failure(Exception("Peripheral disconnected")))
        }
        for (key in writeCompletions.keys().toList().filter { it.startsWith(addr.lowercase()) }) {
            writeCompletions.remove(key)?.invoke(Result.failure(Exception("Peripheral disconnected")))
        }

        gattQueue.clear()
        isProcessingCommand = false
    }

    // ── Battery history ──

    private fun batteryHistoryKey(address: String) = "battery_history_${address.uppercase()}"

    private fun persistBatteryReading(address: String, level: Int) {
        val prefs = application.getSharedPreferences(PREFS_BATTERY, Context.MODE_PRIVATE)
        val key = batteryHistoryKey(address)
        val historyJson = prefs.getString(key, "[]") ?: "[]"
        val history = try { org.json.JSONArray(historyJson) } catch (_: Exception) { org.json.JSONArray() }

        val now = System.currentTimeMillis()
        val cutoff = now - BATTERY_RETENTION_MS

        val pruned = org.json.JSONArray()
        for (i in 0 until history.length()) {
            val obj = history.getJSONObject(i)
            if (obj.getLong("ts") >= cutoff) pruned.put(obj)
        }

        pruned.put(org.json.JSONObject().apply {
            put("ts", now)
            put("level", level)
        })

        while (pruned.length() > MAX_BATTERY_HISTORY) pruned.remove(0)

        prefs.edit().putString(key, pruned.toString()).apply()
    }

    fun getBatteryHistory(address: String): List<BleBatteryPoint> {
        val prefs = application.getSharedPreferences(PREFS_BATTERY, Context.MODE_PRIVATE)
        val key = batteryHistoryKey(address)
        val historyJson = prefs.getString(key, "[]") ?: "[]"
        val history = try { org.json.JSONArray(historyJson) } catch (_: Exception) { return emptyList() }

        val now = System.currentTimeMillis()
        val cutoff = now - BATTERY_RETENTION_MS
        val result = mutableListOf<BleBatteryPoint>()
        for (i in 0 until history.length()) {
            val obj = history.getJSONObject(i)
            val ts = obj.getLong("ts")
            if (ts >= cutoff) {
                result.add(BleBatteryPoint(timestamp = ts, level = obj.getInt("level").toLong()))
            }
        }
        return result
    }

    // ── GATT callback factory ──

    private fun createGattCallback() = object : BluetoothGattCallback() {

        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            val address = gatt.device.address.uppercase()
            Log.i(TAG, "onConnectionStateChange: address=$address, status=$status, newState=$newState")

            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    Log.i(TAG, "Connected to $address, discovering services")
                    connectedGatts[address] = gatt

                    // Discover services
                    enqueueCommand {
                        if (!gatt.discoverServices()) {
                            Log.e(TAG, "discoverServices returned false for $address")
                            completeCommand()
                        }
                    }

                    // Notify the connection owner
                    connectionListener?.onGattConnected(address, gatt)
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    Log.i(TAG, "Disconnected from $address (status=$status, gattHash=${gatt.hashCode()})")
                    cleanupPeripheral(address)

                    // Notify the connection owner with GATT hash for stale callback rejection
                    connectionListener?.onGattDisconnected(address, gatt.hashCode(), status)
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

            // Notify connection owner so it can fire onDeviceReady
            connectionListener?.onMtuChanged(address, mtu, status)
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
                completeCommand()
                return
            }

            val services = gatt.services ?: run {
                completeCommand()
                return
            }
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

            connectionListener?.onGattServicesDiscovered(address, bleServices)
        }

        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
            val address = gatt.device.address.uppercase()
            val serviceUuid = characteristic.service.uuid.toString().lowercase()
            val charUuid = characteristic.uuid.toString().lowercase()

            if (characteristic.uuid == BATTERY_LEVEL_CHAR_UUID && value.isNotEmpty()) {
                persistBatteryReading(address, value[0].toInt() and 0xFF)
            }

            mainHandler.post {
                flutterApi?.onCharacteristicValueUpdated(address, serviceUuid, charUuid, value) {}
            }
        }

        // Deprecated overload called on Android < 13 (API < 33)
        @Suppress("deprecation")
        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            onCharacteristicChanged(gatt, characteristic, characteristic.value ?: return)
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

        // Deprecated overload called on Android < 13 (API < 33)
        @Suppress("deprecation")
        override fun onCharacteristicRead(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            onCharacteristicRead(gatt, characteristic, characteristic.value ?: ByteArray(0), status)
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
                return
            }
            val address = gatt.device.address.uppercase()
            lastRssi[address] = rssi
            val deque = rssiHistory.getOrPut(address) { java.util.ArrayDeque() }
            synchronized(deque) {
                deque.addLast(Pair(System.currentTimeMillis(), rssi))
                while (deque.size > RSSI_HISTORY_LIMIT) deque.removeFirst()
            }
            if (isRssiStreamingEnabled) {
                mainHandler.post {
                    flutterApi?.onRssiUpdate(address, rssi.toLong()) {}
                }
            }
        }
    }
}
