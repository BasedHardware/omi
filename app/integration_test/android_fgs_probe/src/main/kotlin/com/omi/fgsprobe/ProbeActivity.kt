package com.omi.fgsprobe

import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.core.content.ContextCompat
import com.friend.ios.sync.SyncTransferForegroundService

class ProbeActivity : Activity() {
    companion object {
        /** The runner broadcasts this once it has verified the ACTIVE service state. */
        const val ACTION_VERIFIED = "com.omi.fgsprobe.VERIFIED"
        private const val VERIFY_TIMEOUT_MS = 30_000L
    }

    private val handler = Handler(Looper.getMainLooper())
    private var stopAfterBackground = false
    private var verifiedReceiver: BroadcastReceiver? = null

    private fun startTransfer() {
        check(SyncTransferForegroundService.start(this)) { "Foreground start was rejected" }
        Log.i("FGS_PROBE", "ACCEPTED")
    }

    override fun onStop() {
        super.onStop()
        if (stopAfterBackground) {
            stopAfterBackground = false
            Log.i("FGS_PROBE", "BACKGROUND_STOP")
            SyncTransferForegroundService.stop(this)
        }
    }

    override fun onDestroy() {
        unregisterVerifiedReceiver()
        super.onDestroy()
    }

    private fun unregisterVerifiedReceiver() {
        verifiedReceiver?.let { unregisterReceiver(it) }
        verifiedReceiver = null
    }

    /**
     * Report ACTIVE, then stop only after the runner acknowledges its check.
     * Every queued start command is delivered on this thread before the
     * ACTIVE message, so a wall-clock stop would land right behind ACTIVE on a
     * slow emulator and the runner would read the intended teardown as a lost
     * transfer. A bounded fallback keeps a silent runner from hanging the case.
     */
    private fun reportActiveThenStopWhenVerified(mode: String) {
        var finished = false
        lateinit var fallback: Runnable
        fun finish(reason: String) {
            if (finished) return
            finished = true
            handler.removeCallbacks(fallback)
            unregisterVerifiedReceiver()
            Log.i("FGS_PROBE", "$reason mode=$mode")
            SyncTransferForegroundService.stop(this)
            handler.postDelayed({ Log.i("FGS_PROBE", "SURVIVED mode=$mode") }, 2000)
        }
        fallback = Runnable { finish("VERIFY_TIMEOUT") }
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                finish("VERIFIED")
            }
        }
        verifiedReceiver = receiver
        ContextCompat.registerReceiver(
            this, receiver, IntentFilter(ACTION_VERIFIED), ContextCompat.RECEIVER_EXPORTED
        )
        handler.postDelayed(fallback, VERIFY_TIMEOUT_MS)
        Log.i("FGS_PROBE", "ACTIVE mode=$mode")
    }

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val mode = intent.getStringExtra("mode") ?: "empty"
        handler.postDelayed({
            Log.i("FGS_PROBE", "BEGIN mode=$mode")
            when (mode) {
                "burst" -> {
                    repeat(100) {
                        startTransfer()
                        SyncTransferForegroundService.stop(this)
                    }
                    startTransfer()
                }
                "restart" -> {
                    startTransfer()
                    handler.postDelayed({
                        SyncTransferForegroundService.stop(this)
                        startTransfer()
                    }, 100)
                }
                "empty" -> {
                    startTransfer()
                    SyncTransferForegroundService.stop(this)
                }
                "background-stop" -> {
                    startTransfer()
                    stopAfterBackground = true
                    check(moveTaskToBack(true)) { "Activity could not enter the background" }
                }
                "orphan-stop" -> SyncTransferForegroundService.stop(this)
                else -> error("Unknown probe scenario: $mode")
            }
            if (mode == "burst" || mode == "restart") {
                handler.postDelayed({ reportActiveThenStopWhenVerified(mode) }, 1500)
            } else {
                handler.postDelayed({ Log.i("FGS_PROBE", "SURVIVED mode=$mode") }, 6000)
            }
        }, 500)
    }
}
