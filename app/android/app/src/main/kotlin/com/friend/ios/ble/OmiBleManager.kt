package com.friend.ios.ble

import com.friend.ios.BleBatteryPoint
import com.friend.ios.BleFlutterApi
import com.friend.ios.BlePeripheral
import com.friend.ios.BleService


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
import com.friend.ios.ble.GattCommandQueue.Kind

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
        private const val RSSI_HISTORY_LIMIT = 120
        private const val BOND_TIMEOUT_MS = 15000L // 15s — bond request timeout
        private const val PREFS_BATTERY = "battery_history"
        private val BATTERY_LEVEL_CHAR_UUID = UUID.fromString("00002a19-0000-1000-8000-00805f9b34fb")

        @Volatile
        private var _instance: OmiBleManager? = null

        val instance: OmiBleManager
            get() = _instance ?: throw IllegalStateException("OmiBleManager not initialized")

        val isInitialized: Boolean
            get() = _instance != null

        /** True while the Flutter engine is alive. Set in MainActivity.configureFlutterEngine,
         *  cleared in MainActivity.onDestroy(isFinishing). The BLE foreground service can
         *  continue running after this becomes false. */
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

    interface CharacteristicValueListener {
        fun onCharacteristicValue(address: String, serviceUuid: String, characteristicUuid: String, value: ByteArray)
    }

    @Volatile
    var characteristicValueListener: CharacteristicValueListener? = null

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

    private val gattQueue = GattCommandQueue<BluetoothGatt>(
        post = { task -> mainHandler.post { task() } },
        schedule = { delay, task ->
            val runnable = Runnable { task() }
            mainHandler.postDelayed(runnable, delay)
            val cancel: () -> Unit = { mainHandler.removeCallbacks(runnable) }
            cancel
        },
        reportFailure = { Log.w(TAG, "GATT completion delivery failed", it) },
    )

    private var rssiKeepAliveRunnable: Runnable? = null
    private val rssiKeepAliveInterval = 10_000L // ms; only one low-cost local radio read per interval.
    @Volatile
    var isRssiStreamingEnabled = false

    /// Most recent RSSI per device (uppercase MAC). Used by the foreground service
    /// to annotate disconnect events so we can tell range-driven drops from healthy-signal drops.
    val lastRssi = java.util.concurrent.ConcurrentHashMap<String, Int>()

    /// Sliding window of recent (timestamp_ms, rssi_dbm) samples per device, used
    /// by the foreground service to classify RSSI trajectory at disconnect time.
    /// Synchronized on the deque itself for reader/writer safety.
    val rssiHistory = java.util.concurrent.ConcurrentHashMap<String, java.util.ArrayDeque<Pair<Long, Int>>>()
    val chargingState = java.util.concurrent.ConcurrentHashMap<String, Boolean>()

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

    private val adapterStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != BluetoothAdapter.ACTION_STATE_CHANGED) return
            val state = intent.getIntExtra(BluetoothAdapter.EXTRA_STATE, BluetoothAdapter.ERROR)
            mainHandler.post {
                flutterApi?.onBluetoothStateChanged(bluetoothStateFrom(state)) {}
            }
        }
    }

    init {
        Log.i(TAG, "OmiBleManager initialized")
        application.registerReceiver(bondStateReceiver, IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED))
        ContextCompat.registerReceiver(
            application,
            adapterStateReceiver,
            IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED),
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
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
                val record = result.scanRecord
                val name = discoveredPeripheralName(
                    advertisedName = record?.deviceName,
                    cachedName = device.name,
                    manufacturerData = record?.getManufacturerSpecificData(PLAUD_MANUFACTURER_ID),
                )
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
        val gatt = connectedGatts.remove(addr) ?: return
        cleanupPeripheral(addr, gatt)
        gatt.close()
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
        enqueueCommand(gatt, Kind.READ, key, failed = {
            readCompletions.remove(key, completion)
            completion(Result.failure(it))
        }) {
            readCompletions[key] = completion
            if (!gatt.readCharacteristic(characteristic)) {
                Log.e(TAG, "readCharacteristic returned false for $key")
                readCompletions.remove(key)?.invoke(Result.failure(Exception("Read request rejected")))
                completeCommand(gatt, Kind.READ, key)
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
        enqueueCommand(gatt, Kind.WRITE, key, failed = {
            writeCompletions.remove(key, completion)
            if (writeType == BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) completion(Result.failure(it))
        }) {
            if (writeType == BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) writeCompletions[key] = completion
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
                completeCommand(gatt, Kind.WRITE, key)
            } else if (writeType == BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) {
                completeCommand(gatt, Kind.WRITE, key)
            }
        }

        if (writeType == BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) {
            completion(Result.success(Unit))
        }
    }

    private val subscriptionCompletions =
        ConcurrentHashMap<BluetoothGattDescriptor, (Result<Unit>) -> Unit>()

    fun subscribeCharacteristic(address: String, serviceUuid: String, characteristicUuid: String,
                                completion: (Result<Unit>) -> Unit = {}) {
        val deliver = OnceCompletion(completion)
        try {
            val gatt = connectedGatts[address.uppercase()]
            val characteristic = findCharacteristic(gatt, serviceUuid, characteristicUuid)
            val descriptor = characteristic?.getDescriptor(CCCD_UUID)
            if (gatt == null || characteristic == null || descriptor == null) {
                deliver(Result.failure(IllegalStateException("Notification characteristic or CCCD not found")))
                return
            }
            val key = descriptorKey(descriptor)
            enqueueCommand(gatt, Kind.DESCRIPTOR, key, failed = {
                subscriptionCompletions.remove(descriptor, deliver)
                deliver(Result.failure(it))
            }, subscriptionDeadline = true) {
                subscriptionCompletions[descriptor] = deliver
                val success = gatt.setCharacteristicNotification(characteristic, true) &&
                    writeDescriptorCompat(gatt, descriptor, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                if (!success) {
                    gattQueue.complete(gatt, Kind.DESCRIPTOR, key) {
                        finishSubscription(descriptor, Result.failure(IllegalStateException("Notification enable/CCCD write rejected")))
                    }
                }
            }
        } catch (e: Exception) {
            deliver(Result.failure(e))
        }
    }

    private fun descriptorKey(descriptor: BluetoothGattDescriptor) =
        "${descriptor.characteristic.service.uuid}:${descriptor.characteristic.uuid}:${descriptor.uuid}".lowercase()

    private fun finishSubscription(descriptor: BluetoothGattDescriptor, result: Result<Unit>) {
        subscriptionCompletions.remove(descriptor)?.invoke(result)
    }

    fun unsubscribeCharacteristic(address: String, serviceUuid: String, characteristicUuid: String) {
        val gatt = connectedGatts[address.uppercase()] ?: return
        val characteristic = findCharacteristic(gatt, serviceUuid, characteristicUuid) ?: return
        val descriptor = characteristic.getDescriptor(CCCD_UUID) ?: return
        val key = descriptorKey(descriptor)
        enqueueCommand(gatt, Kind.DESCRIPTOR, key, subscriptionDeadline = true) {
            val success = gatt.setCharacteristicNotification(characteristic, false) &&
                writeDescriptorCompat(gatt, descriptor, BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE)
            if (!success) completeCommand(gatt, Kind.DESCRIPTOR, key)
        }
    }

    // ── RSSI keep-alive ──

    fun startRssiKeepAlive(address: String) {
        stopRssiKeepAlive()
        val normalizedAddress = address.uppercase()
        val runnable = object : Runnable {
            override fun run() {
                val gatt = connectedGatts[normalizedAddress]
                synchronized(this@OmiBleManager) {
                    if (rssiKeepAliveRunnable !== this || gatt == null || connectedGatts[normalizedAddress] !== gatt) {
                        if (rssiKeepAliveRunnable === this) rssiKeepAliveRunnable = null
                        return
                    }
                    gatt.readRemoteRssi()
                    mainHandler.postDelayed(this, rssiKeepAliveInterval)
                }
            }
        }
        synchronized(this) {
            rssiKeepAliveRunnable = runnable
            connectedGatts[normalizedAddress]?.let { gatt ->
                gatt.readRemoteRssi()
                mainHandler.postDelayed(runnable, rssiKeepAliveInterval)
            }
        }
    }

    fun sampleRssi(address: String) {
        connectedGatts[address.uppercase()]?.readRemoteRssi()
    }

    fun stopRssiKeepAlive() {
        synchronized(this) {
            rssiKeepAliveRunnable?.let { mainHandler.removeCallbacks(it) }
            rssiKeepAliveRunnable = null
        }
    }

    // ── State & utility ──

    fun getBluetoothState(): String {
        val adapter = bluetoothAdapter ?: return "unsupported"
        return bluetoothStateFrom(adapter.state)
    }

    private fun bluetoothStateFrom(state: Int): String {
        return when (state) {
            BluetoothAdapter.STATE_ON -> "on"
            BluetoothAdapter.STATE_OFF -> "off"
            BluetoothAdapter.STATE_TURNING_ON -> "resetting"
            BluetoothAdapter.STATE_TURNING_OFF -> "resetting"
            else -> "unknown"
        }
    }

    // ── Command queue ──

    internal fun enqueueCommand(
        gatt: BluetoothGatt,
        kind: Kind,
        key: String = "",
        failed: (Exception) -> Unit = { Log.w(TAG, "GATT command failed: ${it.message}") },
        subscriptionDeadline: Boolean = false,
        timeoutMs: Long? = null,
        command: () -> Unit,
    ) {
        gattQueue.enqueue(GattCommandQueue.Command(gatt, kind, key, {
            if (!isCurrentGatt(gatt)) throw IllegalStateException("Peripheral disconnected")
            command()
        }, failed), if (subscriptionDeadline) 15_000L else timeoutMs,
            if (subscriptionDeadline) ({ expireSubscription(gatt) }) else null)
    }

    private val mtuCompletions = ConcurrentHashMap<BluetoothGatt, () -> Unit>()

    internal fun requestMtu(gatt: BluetoothGatt, mtu: Int, ready: () -> Unit) {
        val finish = OnceCompletion<Unit> {
            mtuCompletions.remove(gatt)
            if (isCurrentGatt(gatt)) ready()
        }
        mtuCompletions[gatt] = { finish(Unit) }
        // MTU negotiation is optional: the default MTU remains usable on timeout.
        enqueueCommand(gatt, Kind.MTU, failed = { finish(Unit) }, timeoutMs = 15_000L) {
            if (!gatt.requestMtu(mtu)) {
                gattQueue.complete(gatt, Kind.MTU) { finish(Unit) }
            }
        }
    }

    internal fun completeCommand(gatt: BluetoothGatt, kind: Kind, key: String = "") {
        gattQueue.complete(gatt, kind, key)
    }

    internal fun isCurrentGatt(gatt: BluetoothGatt) = connectedGatts[gatt.device.address.uppercase()] === gatt

    private fun expireSubscription(gatt: BluetoothGatt) {
        val address = gatt.device.address.uppercase()
        if (!isCurrentGatt(gatt)) return
        // An accepted descriptor write cannot be cancelled or correlated with
        // a retry on the same GATT. Retire it before releasing queued work.
        connectedGatts.remove(address, gatt)
        try { cleanupPeripheral(address, gatt) } catch (e: Exception) { Log.w(TAG, "Timeout cleanup failed", e) }
        try { gatt.disconnect() } catch (e: Exception) { Log.w(TAG, "Timeout disconnect failed", e) }
        try { gatt.close() } catch (e: Exception) { Log.w(TAG, "Timeout close failed", e) }
        // Reuse the managed-device retry owner; never alter user disconnect/mute intent.
        connectionListener?.onGattDisconnected(address, gatt.hashCode(), BluetoothGatt.GATT_CONNECTION_TIMEOUT)
    }

    private fun findCharacteristic(gatt: BluetoothGatt?, serviceUuid: String, characteristicUuid: String): BluetoothGattCharacteristic? {
        val service = gatt?.getService(UUID.fromString(serviceUuid)) ?: return null
        return service.getCharacteristic(UUID.fromString(characteristicUuid))
    }

    @Suppress("deprecation")
    private fun writeDescriptorCompat(gatt: BluetoothGatt, descriptor: BluetoothGattDescriptor, value: ByteArray): Boolean {
        val success = if (Build.VERSION.SDK_INT >= 33) {
            gatt.writeDescriptor(descriptor, value) == BluetoothStatusCodes.SUCCESS
        } else {
            descriptor.value = value
            gatt.writeDescriptor(descriptor)
        }
        if (!success) {
            Log.e(TAG, "writeDescriptor failed for ${descriptor.uuid}")
        }
        return success
    }

    fun cleanupPeripheral(address: String, owner: BluetoothGatt? = connectedGatts[address.uppercase()]) {
        val addr = address.uppercase()
        servicesDiscoveredFor.remove(addr)
        stopRssiKeepAlive()
        bondingAddress = null
        bondTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }
        bondTimeoutRunnable = null
        val bondCompletion = bondCompletionCallback
        bondCompletionCallback = null
        try { bondCompletion?.invoke(false) } finally {
            if (owner != null) gattQueue.cancelOwner(owner, IllegalStateException("Peripheral disconnected"))
        }
    }

    // ── Battery history ──

    private fun batteryHistoryKey(address: String) = "battery_history_${address.uppercase()}"

    private val batteryHistoryRecorder by lazy {
        val prefs = application.getSharedPreferences(PREFS_BATTERY, Context.MODE_PRIVATE)
        BatteryHistoryRecorder(
            read = { key -> prefs.getString(key, "[]") ?: "[]" },
            write = { key, value -> prefs.edit().putString(key, value).apply() },
        )
    }

    private fun persistBatteryReading(address: String, level: Int) {
        batteryHistoryRecorder.record(batteryHistoryKey(address), level, System.currentTimeMillis(), chargingState[address.uppercase()])
    }

    fun getBatteryHistory(address: String): List<BleBatteryPoint> {
        val prefs = application.getSharedPreferences(PREFS_BATTERY, Context.MODE_PRIVATE)
        val key = batteryHistoryKey(address)
        val historyJson = prefs.getString(key, "[]") ?: "[]"
        val history = try { org.json.JSONArray(historyJson) } catch (_: Exception) { return emptyList() }

        val now = System.currentTimeMillis()
        val cutoff = now - BatteryHistoryRecorder.RETENTION_MS
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
            mainHandler.post {
                val address = gatt.device.address.uppercase()
                if (!isCurrentGatt(gatt)) return@post
                Log.i(TAG, "onConnectionStateChange: address=$address, status=$status, newState=$newState")

                when (newState) {
                    BluetoothProfile.STATE_CONNECTED -> {
                        Log.i(TAG, "Connected to $address, discovering services")
                        connectedGatts[address] = gatt

                        // Discover services
                        enqueueCommand(gatt, Kind.DISCOVER) {
                            if (!gatt.discoverServices()) {
                                Log.e(TAG, "discoverServices returned false for $address")
                                completeCommand(gatt, Kind.DISCOVER)
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
        }

        override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) {
            mainHandler.post {
                if (!isCurrentGatt(gatt) || !gattQueue.matches(gatt, Kind.MTU)) return@post
                val address = gatt.device.address.uppercase()
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    Log.e(TAG, "MTU request failed for $address (status=$status)")
                } else {
                    Log.i(TAG, "MTU changed to $mtu for $address")
                }
                gattQueue.complete(gatt, Kind.MTU) { mtuCompletions.remove(gatt)?.invoke() }
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            mainHandler.post {
                if (!isCurrentGatt(gatt) || !gattQueue.matches(gatt, Kind.DISCOVER)) return@post
                val address = gatt.device.address.uppercase()

                if (servicesDiscoveredFor.contains(address)) {
                    Log.i(TAG, "Ignoring duplicate onServicesDiscovered for $address")
                    completeCommand(gatt, Kind.DISCOVER)
                    return@post
                }

                Log.i(TAG, "Services discovered for $address (status=$status)")

                if (status != BluetoothGatt.GATT_SUCCESS) {
                    Log.e(TAG, "Service discovery failed for $address (status=$status)")
                    completeCommand(gatt, Kind.DISCOVER)
                    return@post
                }

                val services = gatt.services ?: run {
                    completeCommand(gatt, Kind.DISCOVER)
                    return@post
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

                completeCommand(gatt, Kind.DISCOVER)

                connectionListener?.onGattServicesDiscovered(address, bleServices)
            }
        }

        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
            mainHandler.post {
                val address = gatt.device.address.uppercase()
                if (!isCurrentGatt(gatt)) return@post
                val serviceUuid = characteristic.service.uuid.toString().lowercase()
                val charUuid = characteristic.uuid.toString().lowercase()

                if (characteristic.uuid == BATTERY_LEVEL_CHAR_UUID && value.isNotEmpty()) {
                    persistBatteryReading(address, value[0].toInt() and 0xFF)
                }

                characteristicValueListener?.onCharacteristicValue(address, serviceUuid, charUuid, value.copyOf())
                if (isFlutterAlive) {
                    mainHandler.post {
                        if (isCurrentGatt(gatt)) flutterApi?.onCharacteristicValueUpdated(address, serviceUuid, charUuid, value) {}
                    }
                }
            }
        }

        // Deprecated overload called on Android < 13 (API < 33)
        @Suppress("deprecation")
        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            onCharacteristicChanged(gatt, characteristic, characteristic.value ?: return)
        }

        override fun onCharacteristicRead(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray, status: Int) {
            mainHandler.post {
                val address = gatt.device.address.uppercase()
                val serviceUuid = characteristic.service.uuid.toString().lowercase()
                val charUuid = characteristic.uuid.toString().lowercase()
                val key = "$address:$serviceUuid:$charUuid".lowercase()

                if (!isCurrentGatt(gatt)) return@post
                gattQueue.complete(gatt, Kind.READ, key) {
                    val completion = readCompletions.remove(key)
                    if (status == BluetoothGatt.GATT_SUCCESS) {
                        completion?.invoke(Result.success(value))
                    } else {
                        completion?.invoke(Result.failure(Exception("Read failed with status $status")))
                    }
                }
            }
        }

        // Deprecated overload called on Android < 13 (API < 33)
        @Suppress("deprecation")
        override fun onCharacteristicRead(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            onCharacteristicRead(gatt, characteristic, characteristic.value ?: ByteArray(0), status)
        }

        override fun onCharacteristicWrite(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            mainHandler.post {
                if (characteristic.properties and BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE != 0) return@post
                val address = gatt.device.address.uppercase()
                val serviceUuid = characteristic.service.uuid.toString().lowercase()
                val charUuid = characteristic.uuid.toString().lowercase()
                val key = "$address:$serviceUuid:$charUuid".lowercase()

                if (!isCurrentGatt(gatt)) return@post
                gattQueue.complete(gatt, Kind.WRITE, key) {
                    val completion = writeCompletions.remove(key)
                    if (status == BluetoothGatt.GATT_SUCCESS) {
                        completion?.invoke(Result.success(Unit))
                    } else {
                        completion?.invoke(Result.failure(Exception("Write failed with status $status")))
                    }
                }
            }
        }

        override fun onDescriptorWrite(gatt: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
            mainHandler.post {
                if (!isCurrentGatt(gatt)) return@post
                gattQueue.complete(gatt, Kind.DESCRIPTOR, descriptorKey(descriptor)) {
                    finishSubscription(descriptor, if (status == BluetoothGatt.GATT_SUCCESS) Result.success(Unit)
                        else Result.failure(IllegalStateException("CCCD write failed: $status")))
                }
            }
        }

        override fun onReadRemoteRssi(gatt: BluetoothGatt, rssi: Int, status: Int) {
            mainHandler.post {
                if (!isCurrentGatt(gatt)) return@post
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    Log.w(TAG, "RSSI read failed: status=$status for ${gatt.device.address}")
                    return@post
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
                        if (isCurrentGatt(gatt)) flutterApi?.onRssiUpdate(address, rssi.toLong()) {}
                    }
                }
            }
        }
    }
}
