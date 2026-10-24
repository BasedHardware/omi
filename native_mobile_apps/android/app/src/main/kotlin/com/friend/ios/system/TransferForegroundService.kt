package com.friend.ios.system

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.util.Log
import androidx.compose.runtime.snapshotFlow
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.friend.ios.R
import com.friend.ios.design.Strings
import com.friend.ios.service.DebugLog
import com.friend.ios.service.stores.SyncStore
import com.friend.ios.service.stores.TransferLease
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

/**
 * Port of `BackgroundTransferLease.swift`: the app's half of [TransferLease]. Where iOS asks for a
 * background task, Android runs this foreground service of type `dataSync` while a read off the
 * Omi or an upload is going, so a recording's upload finishes when the app is put away (a
 * phone-only recording has no Omi link keeping the app alive). Android 15 can end a `dataSync`
 * service when its daily time is used up ([onTimeout]): that is the lease's expiry.
 */
class TransferForegroundService : Service() {
    companion object {
        private const val TAG = "Omi.Transfer"
        private const val CHANNEL_ID = "omi_transfer"
        private const val NOTIFICATION_ID = 2005

        @Volatile
        private var instance: TransferForegroundService? = null

        /** The lease still wants the service: a stop that came before it started is honored on start. */
        @Volatile
        private var wanted = false

        /** The lease's expiry callback, while a grant is held. */
        @Volatile
        private var expire: (() -> Unit)? = null

        /** The notification's line (`nativeOfflineSyncing` with the progress), from the app. */
        @Volatile
        var statusText: () -> String? = { null }

        @Volatile
        var progress: () -> Int? = { null }

        /** The lease the running app uses for its transfers (`TransferLease.app(name:log:)`). */
        fun lease(context: Context, sync: SyncStore, scope: CoroutineScope, log: DebugLog?): TransferLease {
            val app = context.applicationContext
            statusText = {
                (sync.status as? SyncStore.Status.Syncing)?.let { Strings.get(app, "nativeOfflineSyncing", (it.progress * 100).toInt().toString()) }
            }
            progress = { (sync.status as? SyncStore.Status.Syncing)?.let { (it.progress * 100).toInt() } }
            scope.launch { snapshotFlow { sync.status }.collect { instance?.updateNotification() } }
            return TransferLease(
                begin = { expiration -> begin(app, expiration) },
                end = { end() },
                log = log,
            )
        }

        private fun begin(context: Context, expiration: () -> Unit): Boolean {
            wanted = true
            expire = expiration
            return try {
                ContextCompat.startForegroundService(context, Intent(context, TransferForegroundService::class.java))
                true
            } catch (e: Exception) {
                // Android 12+: no foreground start from the background (the app was put away first).
                Log.w(TAG, "no background time: ${e.message}")
                wanted = false
                expire = null
                false
            }
        }

        private fun end() {
            wanted = false
            expire = null
            // Not started yet: `onStartCommand` still has to go foreground, then stops right away.
            instance?.finish()
        }
    }

    override fun onCreate() {
        super.onCreate()
        val channel = NotificationChannel(CHANNEL_ID, "Omi", NotificationManager.IMPORTANCE_LOW).apply { setShowBadge(false) }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Every `startForegroundService` must reach `startForeground`, even one the lease already
        // gave back, or the system ends the app.
        try {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, buildNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } catch (e: Exception) {
            Log.e(TAG, "startForeground failed; the transfer runs without background time", e)
            timeUp()
            return START_NOT_STICKY
        }
        instance = this
        if (!wanted) finish()
        return START_NOT_STICKY
    }

    /** Android 15: the `dataSync` budget is used up. */
    override fun onTimeout(startId: Int, fgsType: Int) {
        timeUp()
    }

    /** The system takes the time back: the lease hears it, then the service goes. */
    private fun timeUp() {
        val callback = expire
        expire = null
        wanted = false
        callback?.invoke()
        finish()
    }

    private fun finish() {
        instance = null
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun updateNotification() {
        runCatching { getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, buildNotification()) }
    }

    private fun buildNotification(): Notification {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
        val open = launchIntent?.let { PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_IMMUTABLE) }
        val percent = progress()
        val builder = Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_stat_launcher)
            .setContentTitle("Omi")
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(Notification.CATEGORY_PROGRESS)
        statusText()?.let { builder.setContentText(it) }
        if (percent != null) builder.setProgress(100, percent, false) else builder.setProgress(0, 0, true)
        if (open != null) builder.setContentIntent(open)
        return builder.build()
    }
}
