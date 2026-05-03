package com.omi.ambientcompanion

import android.Manifest
import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.media.projection.MediaProjectionManager
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONObject
import kotlin.concurrent.thread

class MainActivity : Activity() {
    private lateinit var prefs: AppPrefs
    private lateinit var status: TextView
    private lateinit var audit: TextView
    private lateinit var storage: TextView
    private lateinit var diagnostics: TextView
    private lateinit var pluginUrl: EditText
    private lateinit var userId: EditText

    private val healthReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val json = intent?.getStringExtra("health") ?: return
            status.text = prettyHealth(JSONObject(json))
            refreshAudit()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = AppPrefs(this)
        setContentView(buildUi())
    }

    override fun onResume() {
        super.onResume()
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(healthReceiver, IntentFilter(AmbientForegroundMicService.ACTION_HEALTH_CHANGED), RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            registerReceiver(healthReceiver, IntentFilter(AmbientForegroundMicService.ACTION_HEALTH_CHANGED))
        }
        refreshAudit()
    }

    override fun onPause() {
        runCatching { unregisterReceiver(healthReceiver) }
        super.onPause()
    }

    private fun buildUi(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 48, 36, 36)
            setBackgroundColor(0xff050507.toInt())
        }
        root.addView(text("Omi Ambient Companion", 26, bold = true))
        root.addView(text("Visible ambient capture with VAD, local spool, caption fallback, and Omi plugin sync.", 14))

        pluginUrl = field("Plugin base URL", prefs.pluginBaseUrl)
        userId = field("Omi user id", prefs.omiUserId)
        root.addView(pluginUrl)
        root.addView(userId)
        root.addView(row(
            button("Register") { registerDevice() },
            button("Sync") { SyncWorker.drainAsync(this) },
        ))
        root.addView(row(
            button("Start") { startFullCapture() },
            button("Pause") { AmbientForegroundMicService.command(this, AmbientForegroundMicService.ACTION_PAUSE) },
            button("Stop") { AmbientForegroundMicService.command(this, AmbientForegroundMicService.ACTION_STOP) },
            button("Private") { AmbientForegroundMicService.command(this, AmbientForegroundMicService.ACTION_PRIVATE) },
        ))
        root.addView(row(
            button("Screen Audio") { requestMediaProjection() },
            button("Stop Screen Audio") { MediaProjectionSessionService.stop(this) },
        ))
        root.addView(row(
            button("Permissions") { requestRuntimePermissions() },
            button("Accessibility") { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) },
            button("Notifications") { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) },
        ))
        root.addView(row(
            button("Battery") { openBatterySettings() },
            button("App Info") { openAppInfo() },
        ))
        root.addView(row(
            button("Refresh Diagnostics") { refreshDiagnostics() },
        ))
        root.addView(row(
            button("Delete Synced") { deleteSpool("synced") },
            button("Delete Pending") { deleteSpool("pending") },
            button("Delete All Audio") { deleteSpool(null) },
        ))
        status = text("Status: ${AmbientForegroundMicService.lastHealthState().name}", 16, bold = true)
        root.addView(status)
        storage = text("", 12)
        root.addView(storage)
        audit = text("", 12)
        diagnostics = text("", 12)
        root.addView(text("Diagnostics", 18, bold = true))
        root.addView(diagnostics)
        root.addView(text("Audit log", 18, bold = true))
        root.addView(audit)
        refreshStorage()
        refreshDiagnostics()
        return ScrollView(this).apply { addView(root) }
    }

    @Deprecated("Deprecated by platform, but sufficient for this simple personal native activity.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == MEDIA_PROJECTION_REQUEST && resultCode == RESULT_OK && data != null) {
            MediaProjectionSessionService.start(this, resultCode, data)
        }
    }

    private fun registerDevice() {
        prefs.pluginBaseUrl = pluginUrl.text.toString()
        prefs.omiUserId = userId.text.toString()
        thread {
            val ok = PluginClient(this).registerDevice(prefs.pluginBaseUrl, prefs.omiUserId)
            runOnUiThread {
                status.text = if (ok) "Registered controller: ${prefs.controllerKeyId}" else "Registration failed"
                refreshAudit()
            }
        }
    }

    private fun startFullCapture() {
        requestRuntimePermissions()
        AmbientForegroundMicService.start(this, "manual_start")
    }

    private fun requestRuntimePermissions() {
        val permissions = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= 33) permissions += Manifest.permission.POST_NOTIFICATIONS
        if (Build.VERSION.SDK_INT >= 31) permissions += Manifest.permission.BLUETOOTH_CONNECT
        requestPermissions(permissions.toTypedArray(), 42)
    }

    private fun openBatterySettings() {
        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:$packageName"))
        runCatching { startActivity(intent) }.onFailure { openAppInfo() }
    }

    private fun openAppInfo() {
        startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).setData(Uri.parse("package:$packageName")))
    }

    private fun requestMediaProjection() {
        val manager = getSystemService(MediaProjectionManager::class.java)
        startActivityForResult(manager.createScreenCaptureIntent(), MEDIA_PROJECTION_REQUEST)
    }

    private fun refreshAudit() {
        audit.text = AuditLog(this).tail(40).joinToString("\n")
        refreshStorage()
    }

    private fun refreshStorage() {
        if (::storage.isInitialized) {
            val currentSession = CaptureSessionStore(this).current()?.toString() ?: "none"
            storage.text = "Storage: ${CaptureSpoolStore(this).stats()}\nCurrent session: $currentSession\nContext: ${ContextSignals.snapshot()}"
        }
    }

    private fun refreshDiagnostics() {
        if (::diagnostics.isInitialized) {
            DiagnosticsStore(this).write("ui_refresh")
            diagnostics.text = DiagnosticsStore(this).read()
        }
    }

    private fun deleteSpool(status: String?) {
        CaptureSpoolStore(this).deleteByStatus(status)
        AuditLog(this).record("spool_deleted", mapOf("status" to (status ?: "all")))
        refreshAudit()
    }

    private fun prettyHealth(json: JSONObject): String {
        return "Status: ${json.optString("state")} (${json.optString("reason")})\nForeground: ${json.optString("foreground_app")}"
    }

    private fun text(value: String, size: Int, bold: Boolean = false): TextView {
        return TextView(this).apply {
            text = value
            textSize = size.toFloat()
            setTextColor(0xffffffff.toInt())
            if (bold) typeface = android.graphics.Typeface.DEFAULT_BOLD
            setPadding(0, 10, 0, 10)
        }
    }

    private fun field(hint: String, value: String): EditText {
        return EditText(this).apply {
            setHint(hint)
            setText(value)
            textSize = 14f
            setTextColor(0xffffffff.toInt())
            setHintTextColor(0xff888888.toInt())
            setSingleLine(true)
        }
    }

    private fun button(label: String, action: () -> Unit): Button {
        return Button(this).apply {
            text = label
            setOnClickListener { action() }
        }
    }

    private fun row(vararg views: View): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
            views.forEach { addView(it, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)) }
        }
    }

    companion object {
        private const val MEDIA_PROJECTION_REQUEST = 7304
    }
}
