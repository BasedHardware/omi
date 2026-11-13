package com.friend.ios.wear

import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.WearableListenerService

/**
 * The phone's messages, state and queued messages (the `WCSessionDelegate` callbacks of
 * `WatchConnection.swift`). The system starts the app for them when it is not running.
 */
class WatchListenerService : WearableListenerService() {
    private val connection get() = (application as OmiWatchApp).connection

    override fun onMessageReceived(event: MessageEvent) {
        connection.receiveMessage(event.path, event.data)
    }

    override fun onDataChanged(events: DataEventBuffer) {
        connection.receiveData(events)
    }
}
