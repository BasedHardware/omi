package com.friend.ios.features.settings

import android.Manifest
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.service.LocalSettingsStore

/**
 * Port of `NotificationsScreen.swift`. App > Notifications: whether Android lets Omi notify you,
 * and what Omi notifies about. The daily recap and tips are chosen in Assistant (one place); this
 * screen links there.
 */
@Composable
fun NotificationsScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val navigator = LocalSettingsNavigator.current
    val context = LocalContext.current
    var status by remember { mutableStateOf(notificationStatus(context)) }
    // `.task(id: scenePhase)`: read again when the app comes back from the system settings.
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) status = notificationStatus(context) }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    LaunchedEffect(Unit) { settings.loadNotifications() }
    val request = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        status = notificationStatus(context, asked = true)
    }
    val allowTitle = L("nativeNotificationsAllow")
    val allow = L("nativeAllow")
    val openSettings = L("openSettings")
    val on = L("nativeOn")
    val recapTitle = L("nativeDailyRecap")
    val recapValue = if (settings.dailySummaryEnabled) hourLabel(settings.dailySummaryHour) else L("off")
    val tipsTitle = L("nativeProactiveNotifications")
    val tipsValue = frequencyTitle(settings.notificationFrequency)
    SettingsListPage(L("notifications"), onBack) {
        section(footer = if (status == NotificationStatus.Denied) L("nativeNotificationsDeniedFooter") else null) {
            row(separatorInset = OmiListMetrics.iconSeparatorInset) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    SettingsRowLabel(allowTitle, "bell.badge", Modifier.weight(1f))
                    when (status) {
                        NotificationStatus.NotDetermined -> OmiPillButton(allow) {
                            if (Build.VERSION.SDK_INT >= 33) request.launch(Manifest.permission.POST_NOTIFICATIONS)
                        }
                        NotificationStatus.Denied -> OmiPillButton(openSettings) { openNotificationSettings(context) }
                        NotificationStatus.Authorized -> Text(on, style = DS.Typography.body, color = DS.Palette.inkSecondary)
                    }
                }
            }
        }
        section(header = L("nativeNotificationsWhat"), footer = L("nativeNotificationsAlsoFooter")) {
            row(onClick = { navigator.push(SettingsTopic.Assistant) }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
                SettingsRowLabel(recapTitle, "sun.horizon", value = recapValue)
            }
            row(onClick = { navigator.push(SettingsTopic.Assistant) }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
                SettingsRowLabel(tipsTitle, "lightbulb", value = tipsValue)
            }
        }
    }
}

/** `UNAuthorizationStatus` on Android: granted, never asked (13+), or turned off. */
enum class NotificationStatus { NotDetermined, Denied, Authorized }

private const val ASKED_KEY = "omi.notifications.asked"

private fun notificationStatus(context: Context, asked: Boolean = false): NotificationStatus {
    val prefs = context.getSharedPreferences("omi.settings", Context.MODE_PRIVATE)
    if (asked) prefs.edit().putBoolean(ASKED_KEY, true).apply()
    return when {
        NotificationManagerCompat.from(context).areNotificationsEnabled() -> NotificationStatus.Authorized
        Build.VERSION.SDK_INT >= 33 && !prefs.getBoolean(ASKED_KEY, false) -> NotificationStatus.NotDetermined
        else -> NotificationStatus.Denied
    }
}

/** `UIApplication.openNotificationSettingsURLString`: the app's notification settings. */
private fun openNotificationSettings(context: Context) {
    val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
    runCatching { context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
}
