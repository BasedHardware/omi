package com.friend.ios.system

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationChannelGroup
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.friend.ios.MainActivity
import com.friend.ios.R
import com.friend.ios.core.DeepLink
import com.friend.ios.core.TaskReminderChange
import com.friend.ios.design.Strings
import com.friend.ios.network.APIClientProtocol
import com.friend.ios.persistence.Preferences
import com.friend.ios.service.stores.SessionStore
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import java.security.MessageDigest
import java.time.ZoneId

/**
 * Port of `PushNotifications.swift`: push for the signed-in user. The FCM token goes to
 * `POST v1/users/fcm-token` after sign-in and on every refresh; banners show in the foreground
 * too; a tap opens its [DeepLink] through the [DeepLinkRouter].
 *
 * The local harness's Firebase project (`demo-...`) has no messaging backend, and there is no
 * google-services.json in local builds: every Firebase Messaging call is guarded and only logs.
 */
class PushNotifications(
    private val context: Context,
    private val api: APIClientProtocol,
    private val preferences: Preferences,
    private val scope: CoroutineScope,
) {
    private var token: String? = null
    private var userID: String? = null
    /** `uid|token` last stored by the backend (once per launch, as Flutter does). */
    private var uploaded: String? = null

    init {
        shared = this
        createChannels(context)
        if (messagingAvailable) {
            try {
                FirebaseMessaging.getInstance().isAutoInitEnabled = true
                scope.launch {
                    runCatching { FirebaseMessaging.getInstance().token.await() }
                        .onSuccess { tokenChanged(it) }
                        .onFailure { Log.w(TAG, "FCM token unavailable: ${it.message}") }
                }
            } catch (e: Exception) {
                Log.w(TAG, "Firebase Messaging unavailable: ${e.message}")
            }
        }
    }

    fun sessionChanged(phase: SessionStore.Phase) {
        userID = when (phase) {
            is SessionStore.Phase.Consent -> phase.userID
            is SessionStore.Phase.Onboarding -> phase.userID
            is SessionStore.Phase.Ready -> phase.userID
            else -> null
        }
        upload()
    }

    fun tokenChanged(token: String?) {
        this.token = token
        token?.let(SupportChat::registerPushToken)
        upload()
    }

    private fun upload() {
        val userID = userID ?: return
        val token = token ?: return
        val key = "$userID|$token"
        if (uploaded == key) return
        uploaded = key
        val hash = deviceIDHash()
        scope.launch {
            try {
                api.saveNotificationToken(token, ZoneId.systemDefault().id, hash)
            } catch (e: Exception) {
                Log.e(TAG, "FCM token upload failed: $e")
                if (uploaded == key) uploaded = null
            }
        }
    }

    /**
     * Flutter's `PlatformManager.deviceIdHash` (first 8 hex of SHA-256 of device_info_plus'
     * `androidInfo.id`, which is `Build.ID`), read from its preferences when present, so the
     * backend's `android_<hash>` token entry is replaced.
     */
    private fun deviceIDHash(): String {
        preferences.deviceIdHash?.let { return it }
        val hash = MessageDigest.getInstance("SHA-256").digest(Build.ID.toByteArray())
            .joinToString("") { "%02x".format(it) }.take(8)
        preferences.set(Preferences.Key.DeviceIdHash, hash)
        return hash
    }

    companion object {
        const val TAG = "omi.push"

        /** Flutter's awesome_notifications channel: same key, so the user's choice in Android Settings carries over. */
        const val CHANNEL_ID = "channel"
        const val CHANNEL_GROUP_ID = "channel_group_key"
        /** Intent extra holding a notification's link (an `omi://` URL). */
        const val EXTRA_LINK = "omi.link"

        /** Set once the app process built its environment; the messaging service reaches it here. */
        @Volatile
        var shared: PushNotifications? = null
            private set

        val messagingAvailable: Boolean
            get() = runCatching {
                val options = FirebaseApp.getInstance().options
                !(options.projectId ?: "").startsWith("demo-") && options.gcmSenderId?.trim('0').isNullOrEmpty().not()
            }.getOrDefault(false)

        /** Flutter's channel names (`NotificationChannelStrings`), English and Japanese only there too. */
        fun createChannels(context: Context) {
            val manager = context.getSystemService(NotificationManager::class.java) ?: return
            val japanese = context.resources.configuration.locales[0].language == "ja"
            val name = if (japanese) "Omi の通知" else "Omi Notifications"
            manager.createNotificationChannelGroup(NotificationChannelGroup(CHANNEL_GROUP_ID, name))
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, name, NotificationManager.IMPORTANCE_HIGH).apply {
                    description = if (japanese) "Omi の通知チャンネル" else "Notification channel for Omi"
                    group = CHANNEL_GROUP_ID
                },
            )
        }

        /** Posts a banner whose tap opens [link] (notifications, agent runs, the device). */
        fun post(context: Context, id: String, title: String, body: String, link: DeepLink? = null, group: String? = null) {
            if (Build.VERSION.SDK_INT >= 33 &&
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
            ) {
                return
            }
            createChannels(context)
            val notification = NotificationCompat.Builder(context, CHANNEL_ID)
                .setSmallIcon(R.mipmap.ic_stat_launcher)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(NotificationCompat.BigTextStyle().bigText(body))
                .setAutoCancel(true)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setContentIntent(openIntent(context, id, link))
                .apply { group?.let(::setGroup) }
                .build()
            runCatching { NotificationManagerCompat.from(context).notify(id, 0, notification) }
        }

        fun openIntent(context: Context, id: String, link: DeepLink?): PendingIntent {
            val intent = Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                .apply { link?.let { putExtra(EXTRA_LINK, it.url) } }
            return PendingIntent.getActivity(context, id.hashCode(), intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        }

        /** The link of a tapped notification: ours ([EXTRA_LINK]) or FCM's data keys (background pushes). */
        fun link(intent: Intent): DeepLink? {
            intent.getStringExtra(EXTRA_LINK)?.let { return DeepLink.fromUrl(it) }
            val extras = intent.extras ?: return null
            // FCM puts the data keys of a background push straight into the launch intent.
            if (extras.getString("google.message_id") == null && extras.getString("navigate_to") == null) return null
            val data = extras.keySet().associateWith { extras.getString(it) }
            return DeepLink.fromNotification(data)
        }
    }
}

/**
 * The FCM entry: token refreshes, data-only task reminder pushes, and foreground banners (iOS
 * shows banners in the foreground too; Android only does for us when the app is in the background).
 */
class OmiMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        PushNotifications.shared?.let { push -> android.os.Handler(mainLooper).post { push.tokenChanged(token) } }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        TaskReminderChange.fromNotification(data)?.let {
            TaskReminders.apply(this, it)
            return
        }
        val notification = message.notification ?: return
        PushNotifications.post(
            this, message.messageId ?: data.hashCode().toString(),
            notification.title.orEmpty(), notification.body.orEmpty(), DeepLink.fromNotification(data),
        )
    }
}

/**
 * Port of `TaskReminders` (`PushNotifications.swift`): local task reminders the backend schedules
 * through data pushes, an hour before the due time (alarms on Android).
 */
object TaskReminders {
    private const val EXTRA_TASK = "omi.reminder.task"
    private const val EXTRA_TEXT = "omi.reminder.text"

    fun apply(context: Context, change: TaskReminderChange) {
        val alarms = context.getSystemService(AlarmManager::class.java) ?: return
        when (change) {
            is TaskReminderChange.Cancel -> change.taskIDs.forEach { alarms.cancel(intent(context, it, null)) }
            is TaskReminderChange.Schedule -> {
                val pending = intent(context, change.taskID, change.description)
                alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, change.fireAt.toEpochMilli(), pending)
            }
        }
    }

    private fun intent(context: Context, taskID: String, description: String?): PendingIntent {
        val intent = Intent(context, TaskReminderReceiver::class.java)
            .setAction("omi.reminder.$taskID")
            .putExtra(EXTRA_TASK, taskID)
            .apply { description?.let { putExtra(EXTRA_TEXT, it) } }
        return PendingIntent.getBroadcast(context, taskID.hashCode(), intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    }

    class TaskReminderReceiver : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val id = intent.getStringExtra(EXTRA_TASK) ?: return
            val text = intent.getStringExtra(EXTRA_TEXT) ?: return
            // L("actionItemReminderTitle")
            PushNotifications.post(
                context, "omi.reminder.$id", "⏰ " + Strings.get(context, "actionItemReminderTitle"), text,
                DeepLink.Task(id), group = "omi.reminder",
            )
        }
    }
}

/** Port of `AgentNotifications.swift`: tells the user when a hand-over ends while Omi is not on screen. */
object AgentNotifications {
    // L("nativeOmiFinished") L("nativeOmiCouldNotFinish")
    fun runEnded(context: Context, taskID: String, description: String, finished: Boolean, appInForeground: Boolean) {
        if (appInForeground) return
        val title = Strings.get(context, if (finished) "nativeOmiFinished" else "nativeOmiCouldNotFinish")
        PushNotifications.post(context, "omi.agent.$taskID", title, description, DeepLink.Task(taskID), group = "omi.agent")
    }
}

/** Port of `DeviceNotifications.swift`: local notifications about the Omi wearable itself. */
object DeviceNotifications {
    // L("nativeOmiBatteryLowTitle") L("nativeOmiBatteryLowBody") L("nativeAskOmiAnswerTitle")
    /** Once per discharge (`LowBatteryAlert`); replaces an earlier one still on screen. */
    fun lowBattery(context: Context, level: Int, deviceName: String?) {
        PushNotifications.post(
            context, "omi.device.lowBattery",
            Strings.get(context, "nativeOmiBatteryLowTitle", deviceName ?: "Omi"),
            Strings.get(context, "nativeOmiBatteryLowBody", level.toString()),
            group = "omi.device",
        )
    }

    /** The answer to a question asked with the Omi's button (it is in the chat too). */
    fun answer(context: Context, text: String) {
        PushNotifications.post(
            context, "omi.device.ask.${java.util.UUID.randomUUID()}", Strings.get(context, "nativeAskOmiAnswerTitle"),
            text.take(400), DeepLink.Chat, group = "omi.device.ask",
        )
    }
}
