package com.rnruntime

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper

class OmiWearableService : Service() {
  private var ticket = 0L

  override fun onBind(intent: Intent?): IBinder? = null

  override fun onCreate() {
    super.onCreate()
    instance = this
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      getSystemService(NotificationManager::class.java).createNotificationChannel(
        NotificationChannel(CHANNEL, "Omi device connection", NotificationManager.IMPORTANCE_LOW)
      )
    }
  }

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    val requested = intent?.getLongExtra("session", 0) ?: 0
    if (!sessions.current(requested)) {
      if (!sessions.current(ticket)) stopSelfResult(startId)
      return START_NOT_STICKY
    }
    if (intent?.action == DISCONNECT) {
      terminate(requested)
      return START_NOT_STICKY
    }
    ticket = requested
    try {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        startForeground(NOTIFICATION, notification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
      } else startForeground(NOTIFICATION, notification())
    } catch (_: RuntimeException) {
      terminate(ticket)
    }
    return START_NOT_STICKY
  }

  private fun notification(): Notification {
    val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    val disconnect = PendingIntent.getService(this, ticket.toInt(), Intent(this, OmiWearableService::class.java)
      .setAction(DISCONNECT).putExtra("session", ticket), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(this, CHANNEL) else Notification.Builder(this)
    return builder.setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
      .setContentTitle("Omi device connection")
      .setContentText(status)
      .setContentIntent(open)
      .setOngoing(true)
      .setOnlyAlertOnce(true)
      .addAction(Notification.Action.Builder(null, "Disconnect", disconnect).build())
      .build()
  }

  private fun stopIfRetired() {
    synchronized(sessions) {
      if (sessions.active()) return
      stopForeground(STOP_FOREGROUND_REMOVE)
      stopSelf()
    }
  }

  private fun terminate(expected: Long) {
    val callback = synchronized(sessions) {
      if (!sessions.retire(expected)) null else onStopped.also { onStopped = null }
    }
    stopIfRetired()
    callback?.invoke(expected)
  }

  override fun onTaskRemoved(rootIntent: Intent?) {
    terminate(ticket)
    super.onTaskRemoved(rootIntent)
  }

  override fun onDestroy() {
    if (instance === this) instance = null
    terminate(ticket)
    super.onDestroy()
  }

  companion object {
    private const val CHANNEL = "omi-device-connection"
    private const val NOTIFICATION = 4822
    private const val DISCONNECT = "com.rnruntime.DISCONNECT_WEARABLE"
    private val sessions = OmiWearableSession()
    private val main = Handler(Looper.getMainLooper())
    private var instance: OmiWearableService? = null
    private var onStopped: ((Long) -> Unit)? = null
    @Volatile private var status = "Connecting to Omi…"

    fun start(context: Context, stopped: (Long) -> Unit): Long {
      val ticket = synchronized(sessions) {
        onStopped = stopped
        status = "Connecting to Omi…"
        sessions.begin()
      }
      try {
        val intent = Intent(context, OmiWearableService::class.java).putExtra("session", ticket)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(intent) else context.startService(intent)
      } catch (error: RuntimeException) {
        stop(ticket)
        throw error
      }
      return ticket
    }

    fun update(ticket: Long, message: String) {
      main.post {
        if (!sessions.current(ticket)) return@post
        status = message
        instance?.takeIf { it.ticket == ticket }?.let {
          it.getSystemService(NotificationManager::class.java).notify(NOTIFICATION, it.notification())
        }
      }
    }

    fun stop(ticket: Long) {
      synchronized(sessions) {
        if (!sessions.retire(ticket)) return
        onStopped = null
      }
      main.post { instance?.stopIfRetired() }
    }
  }
}
