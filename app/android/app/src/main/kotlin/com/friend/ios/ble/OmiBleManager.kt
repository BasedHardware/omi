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
import java.util.IdentityHashMap
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong

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
        private const val GATT_OPERATION_TIMEOUT_MS = 30_000L
        private const val GATT_OPERATION_TIMEOUT_STATUS = -2
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
        fun onGattServicesDiscovered(address: String, services: List<BleService>, sessionId: Long)
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
    private val readCompletions = GattCompletionRegistry<ByteArray>()
    private val writeCompletions = GattCompletionRegistry<Unit>()
    private data class MtuCompletionKey(
        val address: String,
        val sessionId: Long,
    )

    private val mtuCompletions = ConcurrentHashMap<MtuCompletionKey, (Int, Int) -> Unit>()
    private val nextGattSessionId = AtomicLong(1L)
    private val gattSessionIds = IdentityHashMap<BluetoothGatt, Long>()

    private val servicesDiscoveredFor = ConcurrentHashMap.newKeySet<String>()

    private data class NotificationStateKey(
        val address: String,
        val sessionId: Long,
        val gattIdentity: Int,
        val serviceUuid: String,
        val characteristicUuid: String,
        val descriptorUuid: String,
    )

    private val notificationTransitions = ConcurrentHashMap<NotificationStateKey, NotificationTransitionState>()

    private var isScanning = false
    private var scanCallback: ScanCallback? = null
    private var scanTimeoutRunnable: Runnable? = null

    private val gattOperations = GattOperationQueue(
        dispatch = { command -> mainHandler.post(command) },
        schedule = { delayMillis, task ->
            val runnable = Runnable(task)
            mainHandler.postDelayed(runnable, delayMillis)
            val cancel: () -> Unit = { mainHandler.removeCallbacks(runnable) }
            cancel
        },
        timeoutMillis = GATT_OPERATION_TIMEOUT_MS,
    )

    private val rssiDiagnosticsPolicy = RssiDiagnosticsPolicy()
    private var rssiDiagnosticsRunnable: Runnable? = null
    private val rssiDiagnosticsInterval = 3000L // ms

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
            synchronized(gattSessionIds) {
                gattSessionIds[gatt] = nextGattSessionId.getAndIncrement()
            }
            connectedGatts.put(addr, gatt)?.let { retiredGatt ->
                retireGattSession(addr, retiredGatt, "replaced by a new GATT session")
                try {
                    retiredGatt.disconnect()
                } catch (_: Exception) {
                }
                try {
                    retiredGatt.close()
                } catch (_: Exception) {
                }
            }
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
        val gatt = connectedGatts.remove(addr)
        if (gatt != null) {
            cleanupPeripheral(addr, gatt, "GATT session closed")
        }
        gatt?.close()
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

        val operationKey =
            characteristicOperationKey(gatt, GattOperationKind.READ_CHARACTERISTIC, characteristic)
        val completionKey = characteristicCompletionKey(gatt, characteristic)
        if (operationKey == null || completionKey == null) {
            completion(Result.failure(Exception("GATT session is no longer active")))
            return
        }
        val finish = onceGattCompletion(completion)
        enqueueGattOperation(
            key = operationKey,
            start = {
                readCompletions
                    .register(completionKey, gatt, characteristic, finish)
                    ?.invoke(Result.failure(Exception("GATT read completion was superseded")))
                gatt.readCharacteristic(characteristic)
            },
            onFailure = { reason ->
                (readCompletions.takeMatching(completionKey, gatt, characteristic) ?: finish).invoke(
                    Result.failure(Exception("GATT read failed before callback: $reason")),
                )
            }
        )
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

        val writeType = preferredWriteType(characteristic)
        if (writeType == null) {
            completion(Result.failure(Exception("Characteristic is not writable")))
            return
        }

        val operationKey = characteristicOperationKey(
            gatt,
            if (writeType == BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) {
                GattOperationKind.WRITE_CHARACTERISTIC
            } else {
                GattOperationKind.WRITE_WITHOUT_RESPONSE
            },
            characteristic,
        )
        val completionKey = characteristicCompletionKey(gatt, characteristic)
        if (operationKey == null || completionKey == null) {
            completion(Result.failure(Exception("GATT session is no longer active")))
            return
        }
        val finish = onceGattCompletion(completion)
        enqueueGattOperation(
            key = operationKey,
            start = {
                if (writeType == BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) {
                    writeCompletions
                        .register(completionKey, gatt, characteristic, finish)
                        ?.invoke(Result.failure(Exception("GATT write completion was superseded")))
                }

                @Suppress("deprecation")
                val success = if (Build.VERSION.SDK_INT >= 33) {
                    val result = gatt.writeCharacteristic(characteristic, data, writeType)
                    if (result != BluetoothStatusCodes.SUCCESS) {
                        Log.e(TAG, "writeCharacteristic returned $result for $completionKey")
                    }
                    result == BluetoothStatusCodes.SUCCESS
                } else {
                    characteristic.value = data
                    characteristic.writeType = writeType
                    gatt.writeCharacteristic(characteristic)
                }

                if (success && writeType == BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) {
                    gattOperations.complete(operationKey) {
                        finish(Result.success(Unit))
                    }
                }
                success
            },
            onFailure = { reason ->
                val retained =
                    if (writeType == BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) {
                        writeCompletions.takeMatching(completionKey, gatt, characteristic)
                    } else {
                        null
                    }
                (retained ?: finish).invoke(Result.failure(Exception("GATT write failed before callback: $reason")))
            },
        )
    }

    fun subscribeCharacteristic(address: String, serviceUuid: String, characteristicUuid: String) {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr] ?: return
        val characteristic = findCharacteristic(gatt, serviceUuid, characteristicUuid) ?: return

        val descriptor = characteristic.getDescriptor(CCCD_UUID)
        enqueueNotificationChange(
            addr,
            gatt,
            characteristic,
            descriptor,
            enabled = true,
        )
    }

    fun unsubscribeCharacteristic(address: String, serviceUuid: String, characteristicUuid: String) {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr] ?: return
        val characteristic = findCharacteristic(gatt, serviceUuid, characteristicUuid) ?: return

        val descriptor = characteristic.getDescriptor(CCCD_UUID)
        enqueueNotificationChange(
            addr,
            gatt,
            characteristic,
            descriptor,
            enabled = false,
        )
    }

    // ── RSSI diagnostics ──

    fun startRssiStreaming(address: String) {
        val addr = address.uppercase()
        rssiDiagnosticsPolicy.subscribe(addr)
        resumeRssiDiagnostics(addr)
    }

    fun stopRssiStreaming(address: String) {
        if (rssiDiagnosticsPolicy.unsubscribe(address)) {
            pauseRssiDiagnostics()
        }
    }

    fun resumeRssiDiagnostics(address: String) {
        val addr = address.uppercase()
        if (!rssiDiagnosticsPolicy.shouldPoll(addr, connectedGatts.containsKey(addr))) return
        pauseRssiDiagnostics()
        val runnable = object : Runnable {
            override fun run() {
                val gatt = connectedGatts[addr]
                if (gatt != null && rssiDiagnosticsPolicy.shouldPoll(addr, isConnected = true)) {
                    val operationKey = gattOperationKey(gatt, GattOperationKind.READ_RSSI)
                    if (operationKey == null) {
                        mainHandler.postDelayed(this, rssiDiagnosticsInterval)
                        return
                    }
                    if (!gattOperations.contains(operationKey)) {
                        enqueueGattOperation(
                            key = operationKey,
                            start = { gatt.readRemoteRssi() },
                            onFailure = { reason ->
                                Log.w(TAG, "RSSI read was not completed for $addr: $reason")
                            },
                        )
                    }
                }
                if (rssiDiagnosticsPolicy.shouldPoll(addr, connectedGatts.containsKey(addr))) {
                    mainHandler.postDelayed(this, rssiDiagnosticsInterval)
                }
            }
        }
        rssiDiagnosticsRunnable = runnable
        mainHandler.postDelayed(runnable, rssiDiagnosticsInterval)
    }

    fun pauseRssiDiagnostics(address: String? = null) {
        if (address != null && !rssiDiagnosticsPolicy.isSubscribed(address)) return
        rssiDiagnosticsRunnable?.let { mainHandler.removeCallbacks(it) }
        rssiDiagnosticsRunnable = null
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

    // ── Serialized GATT operations ──

    private fun enqueueGattOperation(
        key: GattOperationKey,
        start: () -> Boolean,
        onFailure: (GattOperationFailure) -> Unit = {},
    ) {
        gattOperations.enqueue(
            key = key,
            start = start,
            onFailure = { reason ->
                onFailure(reason)
                if (reason == GattOperationFailure.TIMED_OUT && shouldRecoverAfterGattTimeout(key.kind)) {
                    recoverTimedOutGatt(key)
                }
            },
        )
    }

    private fun gattSessionId(gatt: BluetoothGatt): Long? =
        synchronized(gattSessionIds) {
            gattSessionIds[gatt]
        }

    internal fun activeGattSessionId(address: String): Long? {
        val gatt = connectedGatts[address.uppercase()] ?: return null
        return gattSessionId(gatt)
    }

    private fun gattOperationKey(
        gatt: BluetoothGatt,
        kind: GattOperationKind,
    ): GattOperationKey? {
        val sessionId = gattSessionId(gatt) ?: return null
        return GattOperationKey(
            address = gatt.device.address,
            kind = kind,
            sessionId = sessionId,
        )
    }

    private fun characteristicOperationKey(
        gatt: BluetoothGatt,
        kind: GattOperationKind,
        characteristic: BluetoothGattCharacteristic,
    ): GattOperationKey? {
        val sessionId = gattSessionId(gatt) ?: return null
        return GattOperationKey(
            address = gatt.device.address,
            kind = kind,
            target =
                "${characteristic.service.uuid}:${characteristic.uuid}:${characteristic.instanceId}".lowercase(),
            sessionId = sessionId,
        )
    }

    private fun characteristicCompletionKey(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
    ): GattCompletionKey? {
        val sessionId = gattSessionId(gatt) ?: return null
        return GattCompletionKey(
            address = gatt.device.address,
            sessionId = sessionId,
            serviceUuid = characteristic.service.uuid.toString(),
            characteristicUuid = characteristic.uuid.toString(),
            characteristicInstanceId = characteristic.instanceId,
        )
    }

    private fun notificationStateKey(
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        descriptor: BluetoothGattDescriptor?,
    ): NotificationStateKey? {
        val sessionId = gattSessionId(gatt) ?: return null
        return NotificationStateKey(
            address = gatt.device.address.uppercase(),
            sessionId = sessionId,
            gattIdentity = System.identityHashCode(gatt),
            serviceUuid = characteristic.service.uuid.toString().lowercase(),
            characteristicUuid = characteristic.uuid.toString().lowercase(),
            descriptorUuid = descriptor?.uuid?.toString()?.lowercase().orEmpty(),
        )
    }

    private fun notificationOperationKey(key: NotificationStateKey, enabled: Boolean) =
        GattOperationKey(
            address = key.address,
            kind = GattOperationKind.WRITE_DESCRIPTOR,
            target =
                "${key.gattIdentity}:${key.serviceUuid}:${key.characteristicUuid}:${key.descriptorUuid}:${if (enabled) "enable" else "disable"}",
            sessionId = key.sessionId,
        )

    private fun enqueueNotificationChange(
        address: String,
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        descriptor: BluetoothGattDescriptor?,
        enabled: Boolean,
    ) {
        val stateKey = notificationStateKey(gatt, characteristic, descriptor) ?: return
        val state = notificationTransitions.computeIfAbsent(stateKey) { NotificationTransitionState() }
        val transition = state.request(enabled) ?: return
        startNotificationTransition(address, gatt, characteristic, descriptor, stateKey, transition)
    }

    private fun startNotificationTransition(
        address: String,
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        descriptor: BluetoothGattDescriptor?,
        stateKey: NotificationStateKey,
        enabled: Boolean,
    ) {
        val operationKey = notificationOperationKey(stateKey, enabled)
        enqueueGattOperation(
            key = operationKey,
            start = {
                if (!gatt.setCharacteristicNotification(characteristic, enabled)) {
                    return@enqueueGattOperation false
                }
                if (descriptor == null) {
                    gattOperations.complete(operationKey) {
                        finishNotificationTransition(
                            address,
                            gatt,
                            characteristic,
                            descriptor,
                            stateKey,
                            enabled,
                            success = true,
                        )
                    }
                    true
                } else {
                    writeDescriptorCompat(
                        gatt,
                        descriptor,
                        if (enabled) {
                            BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                        } else {
                            BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE
                        },
                    )
                }
            },
            onFailure = { reason ->
                finishNotificationTransition(
                    address,
                    gatt,
                    characteristic,
                    descriptor,
                    stateKey,
                    enabled,
                    success = false,
                )
                Log.e(
                    TAG,
                    "Notification ${if (enabled) "enable" else "disable"} failed for ${characteristic.uuid}: $reason",
                )
                if (
                    reason == GattOperationFailure.REJECTED ||
                    reason == GattOperationFailure.EXCEPTION
                ) {
                    recoverRejectedGatt(operationKey, reason)
                }
            },
        )
    }

    private fun finishNotificationTransition(
        address: String,
        gatt: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
        descriptor: BluetoothGattDescriptor?,
        stateKey: NotificationStateKey,
        attempted: Boolean,
        success: Boolean,
    ) {
        val next = notificationTransitions[stateKey]?.complete(attempted, success) ?: return
        startNotificationTransition(address, gatt, characteristic, descriptor, stateKey, next)
    }

    private fun findCharacteristic(gatt: BluetoothGatt?, serviceUuid: String, characteristicUuid: String): BluetoothGattCharacteristic? {
        val service = gatt?.getService(UUID.fromString(serviceUuid)) ?: return null
        return service.getCharacteristic(UUID.fromString(characteristicUuid))
    }

    /**
     * A write-with-response property wins when a characteristic advertises
     * both modes. Its callback gives the queue an actual delivery boundary;
     * write-without-response is reserved for characteristics with no safer
     * option.
     */
    private fun preferredWriteType(characteristic: BluetoothGattCharacteristic): Int? =
        when (
            preferredGattWriteMode(
                supportsWrite =
                    characteristic.properties and BluetoothGattCharacteristic.PROPERTY_WRITE != 0,
                supportsWriteWithoutResponse =
                    characteristic.properties and BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE != 0,
            )
        ) {
            GattWriteMode.WITH_RESPONSE ->
                BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
            GattWriteMode.WITHOUT_RESPONSE ->
                BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
            null -> null
        }

    @Suppress("deprecation")
    private fun writeDescriptorCompat(
        gatt: BluetoothGatt,
        descriptor: BluetoothGattDescriptor,
        value: ByteArray,
    ): Boolean =
        if (Build.VERSION.SDK_INT >= 33) {
            gatt.writeDescriptor(descriptor, value) == BluetoothStatusCodes.SUCCESS
        } else {
            descriptor.value = value
            gatt.writeDescriptor(descriptor)
        }

    fun discoverServices(address: String) {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr] ?: return
        val operationKey = gattOperationKey(gatt, GattOperationKind.DISCOVER_SERVICES) ?: return
        enqueueGattOperation(
            key = operationKey,
            start = { gatt.discoverServices() },
            onFailure = { reason ->
                Log.e(TAG, "Service discovery did not start/finish for $addr: $reason")
                if (
                    reason == GattOperationFailure.REJECTED ||
                    reason == GattOperationFailure.EXCEPTION
                ) {
                    recoverRejectedGatt(operationKey, reason)
                }
            },
        )
    }

    /**
     * Requests MTU without replacing the process-wide connection listener.
     * Immediate rejection falls back to the default ATT MTU; a missing callback
     * is treated as an unresponsive GATT and recovered by reconnecting.
     */
    fun requestMtu(
        address: String,
        mtu: Int,
        expectedSessionId: Long,
        completion: (mtu: Int, status: Int) -> Unit,
    ) {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr]
        if (gatt == null) {
            completion(23, BluetoothGatt.GATT_FAILURE)
            return
        }
        val operationKey = gattOperationKey(gatt, GattOperationKind.REQUEST_MTU)
        if (operationKey == null || operationKey.sessionId != expectedSessionId) {
            completion(23, BluetoothGatt.GATT_FAILURE)
            return
        }
        val completionKey = MtuCompletionKey(addr, expectedSessionId)
        enqueueGattOperation(
            key = operationKey,
            start = {
                if (!isActiveGatt(gatt) || gattSessionId(gatt) != expectedSessionId) {
                    return@enqueueGattOperation false
                }
                mtuCompletions[completionKey] = completion
                gatt.requestMtu(mtu)
            },
            onFailure = { reason ->
                mtuCompletions.remove(completionKey)
                if (reason == GattOperationFailure.REJECTED || reason == GattOperationFailure.EXCEPTION) {
                    completion(23, BluetoothGatt.GATT_FAILURE)
                }
            },
        )
    }

    private fun cleanupPeripheral(
        address: String,
        gatt: BluetoothGatt,
        reason: String,
    ) {
        val addr = address.uppercase()
        if (gattSessionId(gatt) == null) return
        if (connectedGatts[addr]?.let { it !== gatt } == true) {
            // This session lost a race with a replacement after its callback
            // passed isActiveGatt(). Retire only its session-owned work.
            retireGattSession(addr, gatt, reason)
            return
        }
        servicesDiscoveredFor.remove(addr)
        pauseRssiDiagnostics(addr)
        bondingAddress = null
        bondTimeoutRunnable?.let { mainHandler.removeCallbacks(it) }
        bondTimeoutRunnable = null
        bondCompletionCallback?.invoke(false)
        bondCompletionCallback = null

        retireGattSession(addr, gatt, reason)
    }

    private fun retireGattSession(
        address: String,
        gatt: BluetoothGatt,
        reason: String,
    ) {
        val addr = address.uppercase()
        val sessionId = gattSessionId(gatt) ?: return
        gattOperations.cancelSession(addr, sessionId)
        readCompletions.failSession(sessionId) {
            Exception("GATT read failed because the session was retired: $reason")
        }
        writeCompletions.failSession(sessionId) {
            Exception("GATT write failed because the session was retired: $reason")
        }
        mtuCompletions.remove(MtuCompletionKey(addr, sessionId))
        notificationTransitions.keys
            .filter { it.address == addr && it.sessionId == sessionId }
            .forEach { notificationTransitions.remove(it) }
        synchronized(gattSessionIds) {
            gattSessionIds.remove(gatt)
        }
    }

    private fun recoverRejectedGatt(key: GattOperationKey, reason: GattOperationFailure) {
        // Rejection of discovery/CCCD setup leaves a connected-but-unusable
        // session. Reconnect instead of advertising a false ready state.
        Log.e(TAG, "Recovering unusable GATT after ${key.kind} $reason for ${key.address}")
        recoverGatt(key.address, key.sessionId, BluetoothGatt.GATT_FAILURE)
    }

    private fun recoverTimedOutGatt(key: GattOperationKey) {
        Log.e(TAG, "GATT operation timed out: ${key.kind} for ${key.address}")
        recoverGatt(key.address, key.sessionId, GATT_OPERATION_TIMEOUT_STATUS)
    }

    private fun recoverGatt(
        address: String,
        expectedSessionId: Long,
        status: Int,
    ) {
        val addr = address.uppercase()
        val gatt = connectedGatts[addr] ?: return
        if (gattSessionId(gatt) != expectedSessionId || !connectedGatts.remove(addr, gatt)) {
            Log.w(TAG, "Ignoring recovery from retired GATT session $expectedSessionId for $addr")
            return
        }
        val gattHash = gatt.hashCode()
        cleanupPeripheral(addr, gatt, "GATT recovery status $status")
        try {
            gatt.disconnect()
        } catch (_: Exception) {
        }
        try {
            gatt.close()
        } catch (_: Exception) {
        }
        connectionListener?.onGattDisconnected(addr, gattHash, status)
    }

    private fun isActiveGatt(gatt: BluetoothGatt): Boolean =
        connectedGatts[gatt.device.address.uppercase()] === gatt && gattSessionId(gatt) != null

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

            if (!isActiveGatt(gatt)) {
                Log.w(TAG, "Ignoring callback from retired GATT for $address (${gatt.hashCode()})")
                if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    try {
                        gatt.close()
                    } catch (_: Exception) {
                    }
                }
                return
            }

            when (newState) {
                BluetoothProfile.STATE_CONNECTED -> {
                    Log.i(TAG, "Connected to $address, discovering services")
                    discoverServices(address)

                    // Notify the connection owner
                    connectionListener?.onGattConnected(address, gatt)
                }
                BluetoothProfile.STATE_DISCONNECTED -> {
                    Log.i(TAG, "Disconnected from $address (status=$status, gattHash=${gatt.hashCode()})")
                    connectedGatts.remove(address, gatt)
                    cleanupPeripheral(address, gatt, "GATT disconnected with status $status")
                    try {
                        gatt.close()
                    } catch (_: Exception) {
                    }

                    // Notify the connection owner with GATT hash for stale callback rejection
                    connectionListener?.onGattDisconnected(address, gatt.hashCode(), status)
                }
            }
        }

        override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) {
            val address = gatt.device.address.uppercase()
            if (!isActiveGatt(gatt)) return
            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.e(TAG, "MTU request failed for $address (status=$status)")
            } else {
                Log.i(TAG, "MTU changed to $mtu for $address")
            }
            val operationKey = gattOperationKey(gatt, GattOperationKind.REQUEST_MTU) ?: return
            val completionKey = MtuCompletionKey(address, operationKey.sessionId)
            if (!gattOperations.complete(operationKey) {
                    mtuCompletions.remove(completionKey)?.invoke(mtu, status)
                }
            ) {
                Log.w(TAG, "Ignoring MTU callback with no matching request for $address")
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            val address = gatt.device.address.uppercase()
            if (!isActiveGatt(gatt)) return
            val operationKey = gattOperationKey(gatt, GattOperationKind.DISCOVER_SERVICES) ?: return

            // CoreBluetooth stacks can emit duplicate callbacks, but an
            // explicit rediscovery for an already-connected GATT is valid
            // (the foreground service uses it when Flutter reattaches).
            if (servicesDiscoveredFor.contains(address) && !gattOperations.isActive(operationKey)) {
                Log.i(TAG, "Ignoring duplicate onServicesDiscovered for $address")
                return
            }

            Log.i(TAG, "Services discovered for $address (status=$status)")

            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.e(TAG, "Service discovery failed for $address (status=$status)")
                if (!gattOperations.complete(operationKey) {
                        recoverRejectedGatt(operationKey, GattOperationFailure.REJECTED)
                    }
                ) {
                    Log.w(TAG, "Ignoring failed service callback with no matching discovery for $address")
                }
                return
            }

            val services = gatt.services ?: run {
                if (!gattOperations.complete(operationKey) {
                        recoverRejectedGatt(operationKey, GattOperationFailure.REJECTED)
                    }
                ) {
                    Log.w(TAG, "Ignoring empty service callback with no matching discovery for $address")
                }
                return
            }
            val bleServices = services.map { svc ->
                BleService(
                    uuid = svc.uuid.toString().lowercase(),
                    characteristicUuids = svc.characteristics?.map { it.uuid.toString().lowercase() } ?: emptyList()
                )
            }

            if (!gattOperations.complete(operationKey) {
                    servicesDiscoveredFor.add(address)
                    if (!gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)) {
                        Log.w(TAG, "Failed to request high connection priority")
                    }
                }
            ) {
                Log.w(TAG, "Ignoring service callback with no matching discovery for $address")
                return
            }

            connectionListener?.onGattServicesDiscovered(address, bleServices, operationKey.sessionId)
        }

        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray) {
            if (!isActiveGatt(gatt)) return
            val address = gatt.device.address.uppercase()
            val serviceUuid = characteristic.service.uuid.toString().lowercase()
            val charUuid = characteristic.uuid.toString().lowercase()

            if (characteristic.uuid == BATTERY_LEVEL_CHAR_UUID && value.isNotEmpty()) {
                persistBatteryReading(address, value[0].toInt() and 0xFF)
            }

            characteristicValueListener?.onCharacteristicValue(address, serviceUuid, charUuid, value.copyOf())
            if (isFlutterAlive) {
                mainHandler.post {
                    flutterApi?.onCharacteristicValueUpdated(address, serviceUuid, charUuid, value) {}
                }
            }
        }

        // Deprecated overload called on Android < 13 (API < 33)
        @Suppress("deprecation")
        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            onCharacteristicChanged(gatt, characteristic, characteristic.value ?: return)
        }

        override fun onCharacteristicRead(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, value: ByteArray, status: Int) {
            if (!isActiveGatt(gatt)) return
            val completionKey = characteristicCompletionKey(gatt, characteristic) ?: return
            val operationKey =
                characteristicOperationKey(gatt, GattOperationKind.READ_CHARACTERISTIC, characteristic) ?: return

            if (!gattOperations.complete(operationKey) {
                    val completion = readCompletions.takeMatching(completionKey, gatt, characteristic)
                    if (status == BluetoothGatt.GATT_SUCCESS) {
                        completion?.invoke(Result.success(value))
                    } else {
                        completion?.invoke(Result.failure(Exception("Read failed with status $status")))
                    }
                }
            ) {
                Log.w(TAG, "Ignoring characteristic read callback with no matching operation: $completionKey")
            }
        }

        // Deprecated overload called on Android < 13 (API < 33)
        @Suppress("deprecation")
        override fun onCharacteristicRead(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            onCharacteristicRead(gatt, characteristic, characteristic.value ?: ByteArray(0), status)
        }

        override fun onCharacteristicWrite(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            if (!isActiveGatt(gatt)) return
            val completionKey = characteristicCompletionKey(gatt, characteristic) ?: return
            if (preferredWriteType(characteristic) == BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) {
                // Some Android stacks emit this optional callback after the
                // accepted WNR operation was completed synchronously. Never
                // let it release a later operation for the same target.
                Log.d(TAG, "Ignoring optional write-without-response callback: $completionKey")
                return
            }
            val operationKey =
                characteristicOperationKey(gatt, GattOperationKind.WRITE_CHARACTERISTIC, characteristic) ?: return

            if (!gattOperations.complete(operationKey) {
                    val completion = writeCompletions.takeMatching(completionKey, gatt, characteristic)
                    if (status == BluetoothGatt.GATT_SUCCESS) {
                        completion?.invoke(Result.success(Unit))
                    } else {
                        completion?.invoke(Result.failure(Exception("Write failed with status $status")))
                    }
                }
            ) {
                Log.d(TAG, "Ignoring characteristic write callback with no matching operation: $completionKey")
            }
        }

        override fun onDescriptorWrite(gatt: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
            if (!isActiveGatt(gatt)) return
            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.e(TAG, "Descriptor write failed (status=$status) for ${descriptor.characteristic.uuid}")
            }
            val stateKey = notificationStateKey(gatt, descriptor.characteristic, descriptor) ?: return
            val enabled = notificationTransitions[stateKey]?.currentInFlight()
            if (enabled == null) {
                Log.w(TAG, "Ignoring descriptor callback with no notification transition for ${descriptor.uuid}")
                return
            }
            val operationKey = notificationOperationKey(stateKey, enabled)
            if (status == BluetoothGatt.GATT_SUCCESS) {
                if (!gattOperations.complete(operationKey) {
                        finishNotificationTransition(
                            gatt.device.address,
                            gatt,
                            descriptor.characteristic,
                            descriptor,
                            stateKey,
                            enabled,
                            success = true,
                        )
                    }
                ) {
                    Log.w(TAG, "Ignoring descriptor callback with no matching operation for ${descriptor.uuid}")
                }
            } else {
                if (!gattOperations.complete(operationKey) {
                        finishNotificationTransition(
                            gatt.device.address,
                            gatt,
                            descriptor.characteristic,
                            descriptor,
                            stateKey,
                            enabled,
                            success = false,
                        )
                        recoverRejectedGatt(operationKey, GattOperationFailure.REJECTED)
                    }
                ) {
                    Log.w(TAG, "Ignoring failed descriptor callback with no matching operation for ${descriptor.uuid}")
                }
            }
        }

        override fun onReadRemoteRssi(gatt: BluetoothGatt, rssi: Int, status: Int) {
            if (!isActiveGatt(gatt)) return
            val address = gatt.device.address.uppercase()
            val operationKey = gattOperationKey(gatt, GattOperationKind.READ_RSSI) ?: return
            if (!gattOperations.complete(operationKey)) {
                Log.d(TAG, "Ignoring RSSI callback with no matching operation for $address")
                return
            }
            if (status != BluetoothGatt.GATT_SUCCESS) {
                Log.w(TAG, "RSSI read failed: status=$status for ${gatt.device.address}")
                return
            }
            lastRssi[address] = rssi
            val deque = rssiHistory.getOrPut(address) { java.util.ArrayDeque() }
            synchronized(deque) {
                deque.addLast(Pair(System.currentTimeMillis(), rssi))
                while (deque.size > RSSI_HISTORY_LIMIT) deque.removeFirst()
            }
            if (rssiDiagnosticsPolicy.isSubscribed(address)) {
                mainHandler.post {
                    flutterApi?.onRssiUpdate(address, rssi.toLong()) {}
                }
            }
        }
    }
}
