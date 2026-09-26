package com.friend.ios.widget

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.view.View
import android.widget.RemoteViews
import com.friend.ios.MainActivity
import com.friend.ios.R

/**
 * AppWidgetProvider for the Omi Battery and Connection Status home screen widget.
 *
 * Displays live device name, battery percentage, connection status, and mic state.
 * Tapping the widget opens the main application.
 */
class OmiBatteryWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(context: Context, appWidgetManager: AppWidgetManager, appWidgetIds: IntArray) {
        for (appWidgetId in appWidgetIds) {
            updateAppWidget(context, appWidgetManager, appWidgetId)
        }
    }

    companion object {
        const val PREFS_NAME = "OmiBatteryWidgetPrefs"
        const val KEY_DEVICE_NAME = "widget_device_name"
        const val KEY_BATTERY_LEVEL = "widget_battery_level"
        const val KEY_DEVICE_TYPE = "widget_device_type"
        const val KEY_IS_CONNECTED = "widget_is_connected"
        const val KEY_IS_MUTED = "widget_is_muted"
        const val KEY_LAST_UPDATED = "widget_last_updated"

        fun updateBatteryInfo(
            context: Context,
            deviceName: String,
            batteryLevel: Int,
            deviceType: String,
            isConnected: Boolean
        ) {
            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            prefs.edit()
                .putString(KEY_DEVICE_NAME, deviceName)
                .putInt(KEY_BATTERY_LEVEL, batteryLevel)
                .putString(KEY_DEVICE_TYPE, deviceType)
                .putBoolean(KEY_IS_CONNECTED, isConnected)
                .putLong(KEY_LAST_UPDATED, System.currentTimeMillis())
                .apply()

            notifyWidgets(context)
        }

        fun updateMuteState(context: Context, isMuted: Boolean) {
            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            prefs.edit()
                .putBoolean(KEY_IS_MUTED, isMuted)
                .apply()

            notifyWidgets(context)
        }

        fun notifyWidgets(context: Context) {
            val appWidgetManager = AppWidgetManager.getInstance(context)
            val componentName = ComponentName(context, OmiBatteryWidgetProvider::class.java)
            val appWidgetIds = appWidgetManager.getAppWidgetIds(componentName) ?: return
            if (appWidgetIds.isEmpty()) return

            val views = buildRemoteViews(context)
            for (id in appWidgetIds) {
                appWidgetManager.updateAppWidget(id, views)
            }
        }

        fun updateAppWidget(context: Context, appWidgetManager: AppWidgetManager, appWidgetId: Int) {
            val views = buildRemoteViews(context)
            appWidgetManager.updateAppWidget(appWidgetId, views)
        }

        fun buildRemoteViews(context: Context): RemoteViews {
            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            val deviceName = prefs.getString(KEY_DEVICE_NAME, "Omi") ?: "Omi"
            val batteryLevel = prefs.getInt(KEY_BATTERY_LEVEL, -1)
            val isConnected = prefs.getBoolean(KEY_IS_CONNECTED, false)
            val isMuted = prefs.getBoolean(KEY_IS_MUTED, false)

            val views = RemoteViews(context.packageName, R.layout.omi_battery_widget)

            // Tap on widget container to open main activity
            val launchIntent = Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            }
            val pendingIntent = PendingIntent.getActivity(
                context,
                0,
                launchIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            views.setOnClickPendingIntent(R.id.widget_container, pendingIntent)

            if (isConnected) {
                views.setTextViewText(R.id.widget_device_name, deviceName.ifEmpty { "Omi" })
                views.setViewVisibility(R.id.widget_connected_layout, View.VISIBLE)
                views.setViewVisibility(R.id.widget_disconnected_text, View.GONE)

                if (batteryLevel >= 0) {
                    views.setTextViewText(R.id.widget_battery_text, "$batteryLevel%")
                } else {
                    views.setTextViewText(R.id.widget_battery_text, "--%")
                }

                views.setViewVisibility(R.id.widget_mic_icon, View.VISIBLE)
                if (isMuted) {
                    views.setImageViewResource(R.id.widget_mic_icon, R.drawable.ic_widget_mic_off)
                } else {
                    views.setImageViewResource(R.id.widget_mic_icon, R.drawable.ic_widget_mic)
                }
            } else {
                views.setTextViewText(R.id.widget_device_name, "Omi")
                views.setViewVisibility(R.id.widget_connected_layout, View.GONE)
                views.setViewVisibility(R.id.widget_disconnected_text, View.VISIBLE)
                views.setViewVisibility(R.id.widget_mic_icon, View.GONE)
            }

            return views
        }
    }
}
