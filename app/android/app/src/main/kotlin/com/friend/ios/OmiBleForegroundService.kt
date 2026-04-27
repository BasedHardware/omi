package com.friend.ios

import android.annotation.SuppressLint
import android.app.*
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.content.*
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap

/**
 * Single owner of the BLE connection lifecycle.
 * Dart tells this service "manage device X" / "unmanage device X".
 * The service handles: connect, bond (if needed), MTU, retry on disconnect,
 * and Bluetooth state changes.
 *
 * OmiBleManager is a pure GATT wrapper — it never decides when to connect or retry.
 */
@SuppressLint("MissingPermission")
class OmiBleForegroundService : Service() {

    companion object {
        private const val TAG = "OmiBle.FgService"
        private const val CHANNEL_ID = "omi_ble_channel"
        private const val NOTIFICATION_ID = 2001
        private const val MTU_REQUEST_DELAY_MS = 100L
        private const val MTU_SIZE = 512
        private const val STABILITY_TIMER_MS = 60_000L
        private const val RECONNECT_DELAY_MS = 3_000L
        private const val COMPANION_RATE_LIMIT_MS = 15_000L
        private const val PREFS_NAME = "ble_config"
        private const val PREFS_KEY = "managed_device"
        private const val PREFS_USER_DISCONNECTED = "user_disconnected"
        private const val DFU_SERVICE_UUID = "00001530-1212-efde-1523-785feabcd123"
        private const val PREFS_DIAGNOSTICS = "ble_diagnostics"
        private const val KEY_DISCONNECT_HISTORY = "disconnect_history"
        private const val KEY_RECONNECT_COUNT = "reconnect_count"
        private const val KEY_FAIL_TO_CONNECT_COUNT = "fail_to_connect_count"
        private const val MAX_DISCONNECT_HISTORY = 20
        private const val RSSI_TREND_WINDOW_MS = 15_000L
        private const val RSSI_TREND_FADING_DROP_DB = 10

        /** Classify the RSSI trajectory in the window before [nowMs]. See BleDisconnectEvent.rssiTrend
         *  for the semantics of each label. */
        private fun classifyRssiTrend(samples: List<Pair<Long, Int>>, nowMs: Long): String {
            val windowStart = nowMs - RSSI_TREND_WINDOW_MS
            val recent = samples.filter { it.first >= windowStart }
            if (recent.isEmpty()) return "gap"
            if (recent.size < 3) return "unknown"
            val third = (recent.size / 3).coerceAtLeast(1)
            val oldestAvg = recent.take(third).sumOf { it.second } / third
            val newestAvg = recent.takeLast(third).sumOf { it.second } / third
            // RSSI is negative; a larger drop = newestAvg more negative than oldestAvg.
            val dropDb = oldestAvg - newestAvg
            return if (dropDb >= RSSI_TREND_FADING_DROP_DB) "fading" else "sudden"
        }

        @Volatile
        var instance: OmiBleForegroundService? = null
            private set

        @Volatile
        private var lastCompanionRequestTimestamp: Long = 0

        fun isActive(): Boolean = instance != null

        fun startService(context: Context, deviceAddress: String, requiresBond: Boolean = false, caller: String = "unknown") {
            if (caller.startsWith("CompanionSvc")) {
                val now = System.currentTimeMillis()
                if (now - lastCompanionRequestTimestamp < COMPANION_RATE_LIMIT_MS) {
                    Log.d(TAG, "startService($caller): rate-limited, skipping")
                    return
                }
                lastCompanionRequestTimestamp = now
            }

            val inst = instance
            if (inst != null) {
                Log.d(TAG, "startService($caller): service already running, managing $deviceAddress directly")
                inst.manageDevice(deviceAddress, requiresBond)
                return
            }

            Log.d(TAG, "startService($caller): address=$deviceAddress, requiresBond=$requiresBond")
            val intent = Intent(context, OmiBleForegroundService::class.java).apply {
                putExtra("device_address", deviceAddress)
                putExtra("requires_bond", requiresBond)
                putExtra("caller", caller)
            }
            try {
                ContextCompat.startForegroundService(context, intent)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start foreground service", e)
            }
        }

        fun stopService(context: Context) {
            try {
                context.stopService(Intent(context, OmiBleForegroundService::class.java))
            } catch (e: Exception) {
                Log.e(TAG, "Failed to stop service", e)
            }
        }
    }

    // ── Per-device state ──

    data class ManagedDevice(
        val address: String,
        var requiresBond: Boolean,
        var retryCount: Int = 0,
        var connectionStartTime: Long? = null,
        var currentGattHash: Int? = null,
        var hasEverConnected: Boolean = false,
        var pendingReconnect: Runnable? = null,
        var stabilityTimerRunnable: Runnable? = null,
        /** Reset to false on each connectGatt attempt; set true when the GATT
         *  callback reports CONNECTED. Used to distinguish fail-to-connect from
         *  an established link dropping. Independent of hasEverConnected which
         *  tracks the full device lifetime. */
        var currentAttemptEstablished: Boolean = false,
        /** Timestamp of the last persisted unexpected disconnect event, used to
         *  backfill time-to-reconnect on the next successful connect. */
        var pendingReconnectMarkerTs: Long? = null
    )

    private val managedDevices = ConcurrentHashMap<String, ManagedDevice>()
    private val handler = Handler(Looper.getMainLooper())
    private var isDestroying = false
    private var isBluetoothEnabled = true
    private val syncLock = Any()
    private val bleManager get() = OmiBleManager.instance

    // ── Connection listener — receives GATT events from OmiBleManager ──

    private val connectionListener = object : OmiBleManager.BleConnectionListener {

        override fun onGattConnected(address: String, gatt: BluetoothGatt) {
            val addr = address.uppercase()
            val managed = managedDevices[addr] ?: return

            Log.i(TAG, "onGattConnected: $addr")
            if (managed.hasEverConnected) {
                incrementReconnectionCount(addr)
                backfillTimeToReconnect(addr, managed)
            }
            managed.retryCount = 0
            managed.hasEverConnected = true
            managed.currentAttemptEstablished = true
            managed.pendingReconnect?.let { handler.removeCallbacks(it) }
            managed.pendingReconnect = null
            managed.connectionStartTime = System.currentTimeMillis()
            managed.currentGattHash = gatt.hashCode()

            startStabilityTimer(addr)
            bleManager.startRssiKeepAlive(addr)
            updateNotification("Connected to Omi")
        }

        override fun onGattDisconnected(address: String, gattHash: Int, status: Int) {
            val addr = address.uppercase()
            Log.i(TAG, "onGattDisconnected: $addr (status=$status)")
            handleDisconnection(addr, gattHash, status)
        }

        override fun onGattServicesDiscovered(address: String, services: List<BleService>) {
            val addr = address.uppercase()
            val managed = managedDevices[addr] ?: return

            Log.i(TAG, "onGattServicesDiscovered: $addr (${services.size} services)")

            if (services.isEmpty()) {
                Log.w(TAG, "No services discovered for $addr")
            }

            if (managed.requiresBond) {
                bleManager.requestBond(addr) { result ->
                    val bonded = result.getOrDefault(false)
                    Log.i(TAG, "Bond result for $addr: $bonded")
                    if (bonded) {
                        managed.retryCount = 0
                        managed.requiresBond = false
                    }
                    requestMtuThenNotifyReady(addr, services)
                }
            } else {
                requestMtuThenNotifyReady(addr, services)
            }
        }

        override fun onMtuChanged(address: String, mtu: Int, status: Int) {
            // Handled inline via the MTU flow in requestMtuThenNotifyReady
        }
    }

    // ── Post-discovery pipeline ──

    private fun requestMtuThenNotifyReady(address: String, services: List<BleService>) {
        val addr = address.uppercase()
        val gatt = bleManager.connectedGatts[addr] ?: return

        val originalListener = bleManager.connectionListener
        bleManager.connectionListener = object : OmiBleManager.BleConnectionListener by connectionListener {
            override fun onMtuChanged(address: String, mtu: Int, status: Int) {
                bleManager.connectionListener = originalListener
                Log.i(TAG, "MTU done for $addr (mtu=$mtu, status=$status)")
                fireDeviceReady(addr, services)
            }
        }

        handler.postDelayed({
            bleManager.enqueueCommand {
                try {
                    if (!gatt.requestMtu(MTU_SIZE)) {
                        Log.e(TAG, "requestMtu failed for $addr")
                        bleManager.completeCommand()
                        bleManager.connectionListener = originalListener
                        fireDeviceReady(addr, services)
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "requestMtu exception for $addr: ${e.message}")
                    bleManager.completeCommand()
                    bleManager.connectionListener = originalListener
                    fireDeviceReady(addr, services)
                }
            }
        }, MTU_REQUEST_DELAY_MS)
    }

    private fun fireDeviceReady(address: String, services: List<BleService>) {
        val addr = address.uppercase()
        bleManager.mainHandler.post {
            bleManager.flutterApi?.onDeviceReady(addr, services) {}
        }
    }

    // ── Managed device lifecycle ──

    fun manageDevice(address: String, requiresBond: Boolean) {
        val addr = address.uppercase()
        Log.i(TAG, "manageDevice: $addr (requiresBond=$requiresBond)")

        getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit()
            .putString(PREFS_KEY, "$addr|$requiresBond")
            .putBoolean(PREFS_USER_DISCONNECTED, false)
            .apply()

        if (!isBluetoothEnabled) {
            managedDevices[addr] = ManagedDevice(address = addr, requiresBond = requiresBond)
            updateNotification("Bluetooth is off")
            return
        }

        val existing = managedDevices[addr]
        if (existing != null && bleManager.isPeripheralConnected(addr)) return

        if (existing != null) {
            if (requiresBond && !existing.requiresBond) existing.requiresBond = true
            // Don't interfere with pending GATT connection or scheduled retry
            if (existing.currentGattHash != null || existing.pendingReconnect != null) return
            triggerReconnection(addr, "re-manage")
            return
        }

        managedDevices[addr] = ManagedDevice(address = addr, requiresBond = requiresBond)
        connectToDevice(addr, "manageDevice")
    }

    fun unmanageDevice(address: String) {
        val addr = address.uppercase()
        val managed = managedDevices.remove(addr) ?: return

        Log.i(TAG, "unmanageDevice: $addr")

        managed.pendingReconnect?.let { handler.removeCallbacks(it) }
        managed.stabilityTimerRunnable?.let { handler.removeCallbacks(it) }

        bleManager.disconnectGatt(addr)
        bleManager.closeGatt(addr)

        getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit()
            .putBoolean(PREFS_USER_DISCONNECTED, true)
            .apply()

        persistDisconnectEvent(addr, 0, isManual = true, eventType = "disconnect")

        bleManager.mainHandler.post {
            bleManager.flutterApi?.onPeripheralDisconnected(addr, "unmanaged") {}
        }

        stopSelf()
    }

    // ── Connection ──

    private fun connectToDevice(address: String, source: String) {
        synchronized(syncLock) {
            val addr = address.uppercase()
            val managed = managedDevices[addr] ?: return
            if (!isBluetoothEnabled || bleManager.isPeripheralConnected(addr)) return

            if (bleManager.connectedGatts.containsKey(addr)) bleManager.closeGatt(addr)

            // autoConnect=false for initial connection (device nearby, fast).
            // autoConnect=true for retries/reconnection (passive scan, survives BT toggle).
            val autoConnect = source != "manageDevice"

            Log.i(TAG, "connectToDevice($source): $addr (autoConnect=$autoConnect)")
            val gatt = try {
                bleManager.connectGatt(addr, autoConnect = autoConnect)
            } catch (e: SecurityException) {
                Log.e(TAG, "connectToDevice($source): BLUETOOTH_CONNECT permission denied for $addr")
                bleManager.mainHandler.post {
                    bleManager.flutterApi?.onPeripheralDisconnected(addr, "permission_denied") {}
                }
                return
            }
            if (gatt == null) {
                Log.e(TAG, "connectToDevice($source): connectGatt returned null for $addr")
                return
            }

            managed.currentGattHash = gatt.hashCode()
            managed.connectionStartTime = System.currentTimeMillis()
            managed.currentAttemptEstablished = false
            updateNotification("Connecting to Omi...")
        }
    }

    private fun triggerReconnection(address: String, source: String) {
        val addr = address.uppercase()
        val managed = managedDevices[addr] ?: return

        managed.pendingReconnect?.let { handler.removeCallbacks(it) }
        managed.pendingReconnect = null
        managed.retryCount = 0
        connectToDevice(addr, source)
    }

    // ── Disconnect handling + retry ──

    private fun handleDisconnection(address: String, gattHash: Int, status: Int) {
        synchronized(syncLock) {
            val addr = address.uppercase()
            val managed = managedDevices[addr] ?: return

            // Reject stale disconnect callbacks from old GATT objects
            if (managed.currentGattHash != null && managed.currentGattHash != gattHash) {
                Log.w(TAG, "Stale disconnect for $addr, ignoring")
                return
            }

            managed.pendingReconnect?.let { handler.removeCallbacks(it) }
            managed.pendingReconnect = null
            managed.stabilityTimerRunnable?.let { handler.removeCallbacks(it) }
            managed.stabilityTimerRunnable = null

            val duration = managed.connectionStartTime?.let { System.currentTimeMillis() - it } ?: 0
            if (duration >= STABILITY_TIMER_MS) {
                managed.retryCount = 0
            }

            bleManager.disconnectGatt(addr)
            bleManager.closeGatt(addr)
            managed.currentGattHash = null
        }

        val addr = address.uppercase()

        val error = when {
            status == 22 -> "paired_to_another_phone"
            status != 0 -> "gatt_status_$status"
            else -> null
        }

        val managed = managedDevices[addr]
        if (managed != null && !managed.hasEverConnected && status != -1) {
            Log.w(TAG, "Device $addr disconnected before ever connecting (status=$status)")
        }

        val userDisconnected = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
            .getBoolean(PREFS_USER_DISCONNECTED, false)
        if (!userDisconnected) {
            val attemptEstablished = managed?.currentAttemptEstablished ?: false
            val eventType = if (attemptEstablished) "disconnect" else "fail_to_connect"
            persistDisconnectEvent(addr, status, isManual = false, eventType = eventType)
            if (eventType == "fail_to_connect") {
                incrementFailToConnectCount(addr)
            }
        }

        bleManager.mainHandler.post {
            bleManager.flutterApi?.onPeripheralDisconnected(addr, error) {}
        }

        updateNotification("Disconnected")
        handleRetryLogic(addr, status)
    }

    private fun handleRetryLogic(address: String, status: Int) {
        val addr = address.uppercase()
        val managed = managedDevices[addr] ?: return

        if (isDestroying || status == -1 || !isBluetoothEnabled) return

        managed.retryCount++
        Log.i(TAG, "Retry #${managed.retryCount} for $addr in ${RECONNECT_DELAY_MS}ms (status=$status)")

        val runnable = Runnable {
            managed.pendingReconnect = null
            connectToDevice(addr, "retry_${managed.retryCount}")
        }
        managed.pendingReconnect = runnable
        handler.postDelayed(runnable, RECONNECT_DELAY_MS)
    }

    // ── Stability timer ──

    private fun startStabilityTimer(address: String) {
        val addr = address.uppercase()
        val managed = managedDevices[addr] ?: return

        managed.stabilityTimerRunnable?.let { handler.removeCallbacks(it) }
        val runnable = Runnable {
            managed.retryCount = 0
        }
        managed.stabilityTimerRunnable = runnable
        handler.postDelayed(runnable, STABILITY_TIMER_MS)
    }

    // ── Bond state receiver ──

    private val bondStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != BluetoothDevice.ACTION_BOND_STATE_CHANGED) return
            val device = intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE) ?: return
            val bondState = intent.getIntExtra(BluetoothDevice.EXTRA_BOND_STATE, BluetoothDevice.BOND_NONE)
            val address = device.address.uppercase()

            val managed = managedDevices[address] ?: return

            when (bondState) {
                BluetoothDevice.BOND_BONDED -> {
                    Log.i(TAG, "Bond completed for $address")
                    managed.retryCount = 0
                }
                BluetoothDevice.BOND_NONE -> {
                    Log.w(TAG, "Bond removed/failed for $address")
                }
            }
        }
    }

    // ── Bluetooth state receiver ──

    private val bluetoothReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != BluetoothAdapter.ACTION_STATE_CHANGED) return
            val state = intent.getIntExtra(BluetoothAdapter.EXTRA_STATE, BluetoothAdapter.ERROR)

            when (state) {
                BluetoothAdapter.STATE_TURNING_OFF -> {
                    Log.i(TAG, "Bluetooth turning off, cleaning up GATT")
                    isBluetoothEnabled = false
                    for ((addr, managed) in managedDevices) {
                        managed.pendingReconnect?.let { handler.removeCallbacks(it) }
                        managed.pendingReconnect = null
                        managed.stabilityTimerRunnable?.let { handler.removeCallbacks(it) }
                        managed.stabilityTimerRunnable = null
                        bleManager.stopRssiKeepAlive()
                        bleManager.closeGatt(addr)
                        managed.currentGattHash = null
                        bleManager.mainHandler.post {
                            bleManager.flutterApi?.onPeripheralDisconnected(addr, "bluetooth_off") {}
                        }
                    }
                }
                BluetoothAdapter.STATE_OFF -> {
                    isBluetoothEnabled = false
                    for ((addr, managed) in managedDevices) {
                        if (managed.currentGattHash != null) {
                            bleManager.closeGatt(addr)
                            managed.currentGattHash = null
                        }
                    }
                    updateNotification("Bluetooth is off")
                }
                BluetoothAdapter.STATE_TURNING_ON -> {
                    isBluetoothEnabled = false
                }
                BluetoothAdapter.STATE_ON -> {
                    Log.i(TAG, "Bluetooth on, reconnecting in 2s")
                    isBluetoothEnabled = true
                    updateNotification("Reconnecting...")
                    handler.postDelayed({
                        for ((addr, _) in managedDevices) {
                            triggerReconnection(addr, "bluetoothOn")
                        }
                    }, 2000)
                }
            }
        }
    }

    // ── Service lifecycle ──

    override fun onCreate() {
        super.onCreate()
        instance = this
        // Transition guard: old builds used START_STICKY, so Android may re-deliver
        // a pending intent after process death before MainActivity initializes OmiBleManager.
        if (!OmiBleManager.isInitialized) OmiBleManager.initialize(application)
        createNotificationChannel()
        registerReceiver(
            bluetoothReceiver,
            IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED),
            RECEIVER_NOT_EXPORTED
        )
        registerReceiver(
            bondStateReceiver,
            IntentFilter(BluetoothDevice.ACTION_BOND_STATE_CHANGED),
            RECEIVER_NOT_EXPORTED
        )
        bleManager.connectionListener = connectionListener
        Log.d(TAG, "Service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification("Connecting to Omi..."))

        val address = intent?.getStringExtra("device_address")

        if (address != null) {
            val requiresBond = intent.getBooleanExtra("requires_bond", false)
            manageDevice(address, requiresBond)
        } else {
            // No device specified — Omi streams via WebSocket which needs the app.
            // No point keeping BLE alive without it.
            Log.i(TAG, "onStartCommand: no device address, stopping")
            stopSelf()
        }

        return START_NOT_STICKY
    }

    override fun onDestroy() {
        Log.d(TAG, "Service destroying")
        isDestroying = true

        for ((addr, managed) in managedDevices) {
            managed.pendingReconnect?.let { handler.removeCallbacks(it) }
            managed.stabilityTimerRunnable?.let { handler.removeCallbacks(it) }
            persistDisconnectEvent(addr, -1, isManual = false, eventType = "disconnect")
            bleManager.disconnectGatt(addr)
            bleManager.closeGatt(addr)
            bleManager.mainHandler.post {
                bleManager.flutterApi?.onPeripheralDisconnected(addr, "service_destroyed") {}
            }
        }
        managedDevices.clear()

        bleManager.connectionListener = null
        instance = null

        try { unregisterReceiver(bluetoothReceiver) } catch (_: Exception) {}
        try { unregisterReceiver(bondStateReceiver) } catch (_: Exception) {}

        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ── Diagnostics persistence ──

    private fun hciStatusDescription(status: Int): String = when (status) {
        0 -> "clean_disconnect"
        8 -> "connection_timeout"
        19 -> "remote_device_terminated"
        22 -> "paired_to_another_phone"
        34 -> "link_key_mismatch"
        62 -> "connection_failed_instant_passed"
        -1 -> "app_closed"
        else -> "gatt_error_$status"
    }

    private fun historyKey(address: String) = "${KEY_DISCONNECT_HISTORY}_${address.uppercase()}"
    private fun reconnectKey(address: String) = "${KEY_RECONNECT_COUNT}_${address.uppercase()}"
    private fun failToConnectKey(address: String) = "${KEY_FAIL_TO_CONNECT_COUNT}_${address.uppercase()}"

    private fun currentAppState(): String = if (OmiBleManager.isAppForeground) "foreground" else "background"

    private fun persistDisconnectEvent(
        address: String,
        status: Int,
        isManual: Boolean,
        eventType: String
    ) {
        val prefs = getSharedPreferences(PREFS_DIAGNOSTICS, MODE_PRIVATE)
        val key = historyKey(address)
        val historyJson = prefs.getString(key, "[]") ?: "[]"
        val history = try { JSONArray(historyJson) } catch (_: Exception) { JSONArray() }

        val addr = address.uppercase()
        val managed = managedDevices[addr]
        val now = System.currentTimeMillis()
        val durationMs: Long = if (
            eventType == "disconnect" &&
            managed?.currentAttemptEstablished == true &&
            managed.connectionStartTime != null
        ) {
            now - (managed.connectionStartTime ?: now)
        } else {
            0L
        }

        val rssiSnapshot = bleManager.rssiHistory[addr]?.let { deque ->
            synchronized(deque) { deque.toList() }
        } ?: emptyList()
        val trend = classifyRssiTrend(rssiSnapshot, now)

        val event = JSONObject().apply {
            put("timestamp", now)
            put("reason", if (isManual) "manual" else hciStatusDescription(status))
            put("reasonCode", status)
            put("isManual", isManual)
            put("eventType", eventType)
            put("lastRssi", bleManager.lastRssi[addr] ?: 0)
            put("connectionDurationMs", durationMs)
            put("appState", currentAppState())
            put("timeToReconnectMs", 0L)
            put("rssiTrend", trend)
        }
        history.put(event)

        // Keep only the last MAX_DISCONNECT_HISTORY entries
        while (history.length() > MAX_DISCONNECT_HISTORY) {
            history.remove(0)
        }

        prefs.edit().putString(key, history.toString()).apply()

        // Remember the event timestamp so the next successful connect can backfill
        // the time-to-reconnect latency on this record.
        if (!isManual && managed != null) {
            managed.pendingReconnectMarkerTs = now
        }
    }

    private fun backfillTimeToReconnect(address: String, managed: ManagedDevice) {
        val markerTs = managed.pendingReconnectMarkerTs ?: return
        managed.pendingReconnectMarkerTs = null

        val prefs = getSharedPreferences(PREFS_DIAGNOSTICS, MODE_PRIVATE)
        val key = historyKey(address)
        val historyJson = prefs.getString(key, "[]") ?: "[]"
        val history = try { JSONArray(historyJson) } catch (_: Exception) { return }

        val now = System.currentTimeMillis()
        // Walk backwards; history is small (≤ MAX_DISCONNECT_HISTORY).
        for (i in history.length() - 1 downTo 0) {
            val obj = history.getJSONObject(i)
            if (obj.optLong("timestamp", 0L) == markerTs) {
                obj.put("timeToReconnectMs", (now - markerTs).coerceAtLeast(0L))
                prefs.edit().putString(key, history.toString()).apply()
                return
            }
        }
    }

    private fun incrementReconnectionCount(address: String) {
        val prefs = getSharedPreferences(PREFS_DIAGNOSTICS, MODE_PRIVATE)
        val key = reconnectKey(address)
        val count = prefs.getInt(key, 0)
        prefs.edit().putInt(key, count + 1).apply()
    }

    private fun incrementFailToConnectCount(address: String) {
        val prefs = getSharedPreferences(PREFS_DIAGNOSTICS, MODE_PRIVATE)
        val key = failToConnectKey(address)
        val count = prefs.getInt(key, 0)
        prefs.edit().putInt(key, count + 1).apply()
    }

    fun getDeviceDiagnostics(address: String): BleDeviceDiagnostics {
        val prefs = getSharedPreferences(PREFS_DIAGNOSTICS, MODE_PRIVATE)
        val historyJson = prefs.getString(historyKey(address), "[]") ?: "[]"
        val history = try { JSONArray(historyJson) } catch (_: Exception) { JSONArray() }
        val reconnectCount = prefs.getInt(reconnectKey(address), 0)
        val failToConnectCount = prefs.getInt(failToConnectKey(address), 0)

        val events = mutableListOf<BleDisconnectEvent>()
        for (i in 0 until history.length()) {
            val obj = history.getJSONObject(i)
            events.add(BleDisconnectEvent(
                timestamp = obj.getLong("timestamp"),
                reason = obj.getString("reason"),
                reasonCode = obj.getInt("reasonCode").toLong(),
                isManual = obj.getBoolean("isManual"),
                eventType = obj.optString("eventType", "disconnect"),
                lastRssi = obj.optLong("lastRssi", 0L),
                connectionDurationMs = obj.optLong("connectionDurationMs", 0L),
                appState = obj.optString("appState", ""),
                timeToReconnectMs = obj.optLong("timeToReconnectMs", 0L),
                rssiTrend = obj.optString("rssiTrend", "")
            ))
        }

        val addr = address.uppercase()
        val connectedAt = managedDevices[addr]?.connectionStartTime ?: 0L

        return BleDeviceDiagnostics(
            disconnectHistory = events,
            reconnectionCount = reconnectCount.toLong(),
            connectedAt = connectedAt,
            failToConnectCount = failToConnectCount.toLong()
        )
    }

    // ── Notification ──

    private fun updateNotification(text: String) {
        try {
            val nm = getSystemService(NotificationManager::class.java)
            nm.notify(NOTIFICATION_ID, buildNotification(text))
        } catch (e: Exception) {
            Log.w(TAG, "updateNotification failed: ${e.message}")
        }
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Omi BLE Connection",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Shows Omi device connection status"
            setShowBadge(false)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun buildNotification(contentText: String): Notification {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
        val pendingIntent = if (launchIntent != null) {
            PendingIntent.getActivity(this, 0, launchIntent, PendingIntent.FLAG_IMMUTABLE)
        } else null

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Omi")
            .setContentText(contentText)
            .setSmallIcon(applicationInfo.icon)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .apply { if (pendingIntent != null) setContentIntent(pendingIntent) }
            .build()
    }
}
