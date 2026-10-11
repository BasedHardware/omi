package com.omi.fgsprobe

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.friend.ios.sync.SyncTransferForegroundService

class ProbeActivity : Activity() {
    private var stopAfterBackground = false

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

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val handler = Handler(Looper.getMainLooper())
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
                handler.postDelayed({ Log.i("FGS_PROBE", "ACTIVE mode=$mode") }, 1500)
                handler.postDelayed({ SyncTransferForegroundService.stop(this) }, 4000)
            }
            handler.postDelayed({ Log.i("FGS_PROBE", "SURVIVED mode=$mode") }, 6000)
        }, 500)
    }
}
