package com.friend.ios.wear

import android.app.Application
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/**
 * Port of `OmiWatchApp.swift`: the one recorder of the watch app. It lives as long as the process,
 * so the phone's messages (`WatchListenerService`) reach it with the screen off too.
 */
class OmiWatchApp : Application() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    val connection by lazy { WatchConnection(this, scope) }
    val recorder by lazy { WatchRecorder(this, connection, scope) }

    override fun onCreate() {
        super.onCreate()
        recorder
    }
}
