package com.friend.ios

import android.app.Application
import android.app.ActivityManager
import android.content.Context
import android.content.SharedPreferences
import android.os.Build
import android.os.Process
import com.friend.ios.ble.DeviceHealthPersistence
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
        synchronized(DeviceHealthPersistence) {
            if (DeviceHealthPersistence.enabled(this) && Application.getProcessName() == packageName) {
                val now = System.currentTimeMillis()
                val previous = runCatching { JSONObject(prefs.getString("process_run", "{}")) }.getOrElse { JSONObject() }
                // Retirement clears this boundary with the other diagnostics.
                // Do not re-import a prior identity's OS history after opt-in.
                val notBefore = prefs.getLong("exit_history_since_ms", now)
                val collection = collectExitHistory(now, notBefore).put("coverage_started_at_ms", notBefore)
                val epoch = DeviceHealthPersistence.epoch(this)
                val match = ProcessExitDiagnostics.matchPrevious(collection, previous, epoch, now)
                prefs.edit()
                    .putLong("exit_history_since_ms", notBefore)
                    .putString("process_exit_collection", collection.toString())
                    .putString("previous_run_exit", JSONObject()
                        .put("legacy_run_open", previousRunOpen)
                        .put("match", if (match == null) "unknown" else "matched")
                        .put("exit", match ?: JSONObject.NULL).toString())
                    .putString("process_run", JSONObject().put("pid", Process.myPid())
                        .put("started_at_ms", now).put("identity_epoch", epoch).toString())
                    .apply()
            }
        }
        prefs.edit().putBoolean(RUN_OPEN_KEY, true).apply()
        for (event in DeviceDiagnosticsLifecyclePolicy.processStartEvents(previousRunOpen)) {
            appendLifecycleEvent(prefs, event)
        }
    }

    private fun collectExitHistory(now: Long, notBefore: Long): JSONObject {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return ProcessExitDiagnostics.collection(ExitCollectionOutcome.UNSUPPORTED, now)
        return try {
            val manager = getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
                ?: return ProcessExitDiagnostics.collection(ExitCollectionOutcome.UNAVAILABLE, now)
            val rows = manager.getHistoricalProcessExitReasons(packageName, 0, 10)
                .filter { it.timestamp >= notBefore && (it.processName == packageName || it.processName.startsWith("$packageName:")) }
                .map { JSONObject().put("pid", it.pid).put("main_process", it.processName == packageName)
                    .put("timestamp_ms", it.timestamp).put("reason", it.reason).put("status", it.status)
                    .put("importance", it.importance) }
            ProcessExitDiagnostics.collection(if (rows.isEmpty()) ExitCollectionOutcome.EMPTY else ExitCollectionOutcome.SUCCEEDED, now, rows)
        } catch (_: SecurityException) {
            ProcessExitDiagnostics.collection(ExitCollectionOutcome.REJECTED, now)
        } catch (_: RuntimeException) {
            ProcessExitDiagnostics.collection(ExitCollectionOutcome.FAILED, now)
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

internal enum class ExitCollectionOutcome { SUCCEEDED, EMPTY, UNSUPPORTED, UNAVAILABLE, REJECTED, FAILED }

/** Bounded OS evidence, never a crash counter. No descriptions or traces enter the bundle. */
internal object ProcessExitDiagnostics {
    private const val RETENTION_MS = 7L * 24 * 3600 * 1000

    fun collection(outcome: ExitCollectionOutcome, now: Long, rows: List<JSONObject> = emptyList()): JSONObject {
        val bounded = rows.filter { it.optLong("timestamp_ms") in (now - RETENTION_MS)..now }
            .distinctBy { Triple(it.optInt("pid"), it.optBoolean("main_process"), it.optLong("timestamp_ms")) }
            .sortedByDescending { it.optLong("timestamp_ms") }.take(10)
        val observedOutcome = if (outcome == ExitCollectionOutcome.SUCCEEDED && bounded.isEmpty()) ExitCollectionOutcome.EMPTY else outcome
        return JSONObject().put("outcome", observedOutcome.name.lowercase()).put("observed_at_ms", now).put("records", JSONArray(bounded))
    }

    fun matchPrevious(collection: JSONObject, previous: JSONObject, epoch: Long, now: Long): JSONObject? {
        if (collection.optString("outcome") != "succeeded" || previous.optLong("identity_epoch", -1) != epoch) return null
        val start = previous.optLong("started_at_ms", 0)
        val pid = previous.optInt("pid", 0)
        if (start <= 0 || start >= now || pid <= 0) return null
        val rows = collection.optJSONArray("records") ?: return null
        val matches = (0 until rows.length()).mapNotNull { rows.optJSONObject(it) }.filter {
            it.optBoolean("main_process") && it.optInt("pid") == pid && it.optLong("timestamp_ms") in start until now
        }
        // Ambiguous PID reuse is not a joined exit.
        return matches.singleOrNull()
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
