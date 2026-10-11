package com.friend.ios

import android.app.Application
import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject
import io.maido.intercom.IntercomFlutterPlugin

class MyApp : Application() {
    override fun onCreate() {
        super.onCreate()
        recordProcessStart()
        if (BuildConfig.INTERCOM_APP_ID.isNotEmpty() && BuildConfig.INTERCOM_ANDROID_API_KEY.isNotEmpty()) {
            IntercomFlutterPlugin.initSdk(this, appId = BuildConfig.INTERCOM_APP_ID, androidApiKey = BuildConfig.INTERCOM_ANDROID_API_KEY)
        }
    }

    private fun recordProcessStart() {
        val prefs = getSharedPreferences(DIAGNOSTICS_PREFS, Context.MODE_PRIVATE)
        val previousRunOpen = prefs.getBoolean(RUN_OPEN_KEY, false)
        prefs.edit().putBoolean(RUN_OPEN_KEY, true).apply()
        for (event in DeviceDiagnosticsLifecyclePolicy.processStartEvents(previousRunOpen)) {
            appendLifecycleEvent(prefs, event)
        }
    }

    private fun appendLifecycleEvent(prefs: SharedPreferences, event: String) {
        val source = runCatching { JSONArray(prefs.getString(LIFECYCLE_KEY, "[]")) }.getOrElse { JSONArray() }
        val now = System.currentTimeMillis()
        val kept = JSONArray()
        for (i in 0 until source.length()) {
            val row = source.optJSONObject(i) ?: continue
            if (row.optLong("ts", 0L) >= now - LIFECYCLE_RETENTION_MS) kept.put(row)
        }
        kept.put(JSONObject().put("ts", now).put("event", event))
        while (kept.length() > MAX_LIFECYCLE_EVENTS) kept.remove(0)
        prefs.edit().putString(LIFECYCLE_KEY, kept.toString()).apply()
    }

    companion object {
        private const val DIAGNOSTICS_PREFS = "ble_diagnostics"
        private const val RUN_OPEN_KEY = "run_open"
        private const val LIFECYCLE_KEY = "lifecycle"
        private const val MAX_LIFECYCLE_EVENTS = 500
        private const val LIFECYCLE_RETENTION_MS = 7L * 24 * 3600 * 1000
    }
}

internal object DeviceDiagnosticsLifecyclePolicy {
    fun processStartEvents(previousRunOpen: Boolean): List<String> = buildList {
        if (previousRunOpen) add("previous_run_unclean")
        add("app_launch")
    }

    fun shouldMarkRunClosed(isFinishing: Boolean, bleServiceMustPersist: Boolean): Boolean =
        isFinishing && !bleServiceMustPersist
}
