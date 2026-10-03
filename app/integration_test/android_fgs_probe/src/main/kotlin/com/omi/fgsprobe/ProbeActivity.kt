package com.omi.fgsprobe

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.friend.ios.sync.SyncTransferForegroundService

class ProbeActivity : Activity() {
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val handler = Handler(Looper.getMainLooper())
        val mode = intent.getStringExtra("mode") ?: "empty"
        handler.postDelayed({
            Log.i("FGS_PROBE", "BEGIN mode=$mode")
            when (mode) {
                "burst" -> {
                    repeat(100) {
                        SyncTransferForegroundService.start(this)
                        SyncTransferForegroundService.stop(this)
                    }
                    SyncTransferForegroundService.start(this)
                }
                "restart" -> {
                    SyncTransferForegroundService.start(this)
                    handler.postDelayed({
                        SyncTransferForegroundService.stop(this)
                        SyncTransferForegroundService.start(this)
                    }, 100)
                }
                "empty" -> {
                    SyncTransferForegroundService.start(this)
                    SyncTransferForegroundService.stop(this)
                }
                "background-stop" -> {
                    SyncTransferForegroundService.start(this)
                    moveTaskToBack(true)
                    SyncTransferForegroundService.stop(this)
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
