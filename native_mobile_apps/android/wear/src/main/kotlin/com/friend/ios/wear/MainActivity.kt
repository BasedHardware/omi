package com.friend.ios.wear

import android.Manifest
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import com.friend.ios.core.watch.WatchPhoneState
import kotlinx.coroutines.CompletableDeferred

/** The `WindowGroup` of `OmiWatchApp.swift`: the recorder screen, and the microphone dialog while on screen. */
class MainActivity : ComponentActivity() {
    private var permissionAnswer: CompletableDeferred<Boolean>? = null
    private val askMicrophone = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        permissionAnswer?.complete(granted)
        permissionAnswer = null
    }
    private val recorder get() = (application as OmiWatchApp).recorder

    private val requestMicrophone: suspend () -> Boolean = {
        val answer = CompletableDeferred<Boolean>()
        permissionAnswer?.complete(false)
        permissionAnswer = answer
        askMicrophone.launch(Manifest.permission.RECORD_AUDIO)
        answer.await()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        debugPreview(intent)
        setContent { RecorderView(recorder) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        debugPreview(intent)
    }

    override fun onResume() {
        super.onResume()
        recorder.permissionRequester = requestMicrophone
    }

    override fun onPause() {
        super.onPause()
        if (recorder.permissionRequester === requestMicrophone) recorder.permissionRequester = null
    }

    /**
     * Debug builds: `--es omiWatchNotice phoneBusy` and `--ei omiWatchOmiBattery 80` show those
     * states without a phone (screenshots next to the iOS watch app).
     */
    private fun debugPreview(intent: Intent?) {
        if (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE == 0 || intent == null) return
        val notice = intent.getStringExtra("omiWatchNotice")?.let { raw ->
            WatchRecorder.Notice.entries.firstOrNull { it.name.equals(raw, ignoreCase = true) }
        }
        val battery = intent.getIntExtra("omiWatchOmiBattery", -1).takeIf { it >= 0 }
        if (notice == null && battery == null) return
        recorder.preview(notice, battery?.let { WatchPhoneState(WatchPhoneState.Capture.Idle, it) })
    }
}
