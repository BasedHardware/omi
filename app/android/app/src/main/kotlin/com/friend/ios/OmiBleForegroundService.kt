package com.friend.ios

import android.annotation.SuppressLint
import android.app.*
import android.bluetooth.BluetoothAdapter
import android.content.*
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat

/**
 * Persistent foreground service that keeps the app process alive while
 * connected to an Omi BLE device. Dynamically updates the notification
 * to reflect current connection state.
 */
@SuppressLint("MissingPermission")
class OmiBleForegroundService : Service() {

    companion object {
        private const val TAG = "OmiBle.FgService"
        private const val CHANNEL_ID = "omi_ble_channel"
        private const val NOTIFICATION_ID = 2001

        @Volatile
        private var instance: OmiBleForegroundService? = null

        fun isActive(): Boolean = instance != null

        fun startService(context: Context, deviceAddress: String, shouldConnect: Boolean = false) {
            Log.d(TAG, "startService: address=$deviceAddress, shouldConnect=$shouldConnect")
            val intent = Intent(context, OmiBleForegroundService::class.java).apply {
                putExtra("device_address", deviceAddress)
                putExtra("should_connect", shouldConnect)
            }
            try {
                context.startForegroundService(intent)
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

        fun reconnect(reason: String = "manual") {
            Log.d(TAG, "reconnect: reason=$reason")
            instance?.reconnectInternal()
        }

        fun disconnect() {
            Log.d(TAG, "disconnect")
            instance?.deviceAddress?.let { address ->
                OmiBleManager.instance.disconnectPeripheral(address)
            }
        }

        /** Update notification text from OmiBleManager connection state callbacks. */
        fun updateNotificationText(text: String) {
            instance?.updateNotification(text)
        }
    }

    private var deviceAddress: String? = null
    private val handler = Handler(Looper.getMainLooper())

    private val bluetoothReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == BluetoothAdapter.ACTION_STATE_CHANGED) {
                val state = intent.getIntExtra(BluetoothAdapter.EXTRA_STATE, BluetoothAdapter.ERROR)
                when (state) {
                    BluetoothAdapter.STATE_ON -> {
                        Log.d(TAG, "Bluetooth turned ON, reconnecting in 2s...")
                        updateNotification("Reconnecting...")
                        handler.postDelayed({ reconnectInternal() }, 2000)
                    }
                    BluetoothAdapter.STATE_OFF -> {
                        Log.d(TAG, "Bluetooth turned OFF, cleaning up GATT")
                        updateNotification("Bluetooth is off")
                        OmiBleManager.instance.disconnectAllPeripherals()
                    }
                }
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannel()
        registerReceiver(
            bluetoothReceiver,
            IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED),
            RECEIVER_NOT_EXPORTED
        )
        Log.d(TAG, "Service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val address = intent?.getStringExtra("device_address")
        val isConnected = address != null && OmiBleManager.instance.isPeripheralConnected(address)
        val initialText = if (isConnected) "Listening and transcribing" else "Connecting to Omi..."
        startForeground(NOTIFICATION_ID, buildNotification(initialText))

        if (address != null) {
            deviceAddress = address
            val shouldConnect = intent.getBooleanExtra("should_connect", false)
            if (shouldConnect) {
                connectToDevice(address)
            }
        }

        return START_STICKY
    }

    override fun onDestroy() {
        Log.d(TAG, "Service destroyed")
        instance = null
        try {
            unregisterReceiver(bluetoothReceiver)
        } catch (_: Exception) {}
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun connectToDevice(address: String) {
        Log.d(TAG, "Connecting to device: $address")
        OmiBleManager.instance.connectPeripheral(address)
    }

    private fun reconnectInternal() {
        val address = deviceAddress ?: return
        Log.d(TAG, "Reconnecting to $address")
        updateNotification("Reconnecting...")
        OmiBleManager.instance.reconnectKnownPeripheral(address)
    }

    private fun updateNotification(text: String) {
        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(NOTIFICATION_ID, buildNotification(text))
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
