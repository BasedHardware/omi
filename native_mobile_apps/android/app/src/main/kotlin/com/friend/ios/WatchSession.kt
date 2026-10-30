package com.friend.ios

import android.content.Context
import android.net.Uri
import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.friend.ios.core.watch.WatchMessage
import com.friend.ios.core.watch.WatchPhoneState
import com.friend.ios.core.watch.WatchWire
import com.friend.ios.service.watch.WatchLink
import com.google.android.gms.wearable.CapabilityClient
import com.google.android.gms.wearable.ChannelClient
import com.google.android.gms.wearable.DataClient
import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataItem
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable
import com.google.android.gms.wearable.WearableListenerService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import java.util.UUID

/**
 * Port of `App/WatchSession.swift`: `WatchLink` over the Wear OS Data Layer (WatchConnectivity on
 * iOS). Built at launch, so a recording started on the watch (which can start the app in the
 * background through [WatchListenerService]) is heard. Messages go out live with `MessageClient`
 * when the watch is reachable and fall back to a queued data item, which the Data Layer keeps and
 * delivers (iOS `transferUserInfo`); the state is one data item (iOS application context).
 * Without the Wear OS app on the phone every call fails quietly and no watch is paired.
 */
class WatchSession(context: Context, private val scope: CoroutineScope) : WatchLink {
    private val context = context.applicationContext
    private val inbox = Channel<WatchMessage>(Channel.UNLIMITED)
    override val messages: Flow<WatchMessage> = inbox.receiveAsFlow()

    override var isWatchPaired: Boolean by mutableStateOf(false)
        private set
    override var isWatchAppInstalled: Boolean by mutableStateOf(false)
        private set

    /** Everything to the watch leaves in the order it was sent. */
    private val outbox = Channel<suspend () -> Unit>(Channel.UNLIMITED)

    init {
        scope.launch { for (job in outbox) runCatching { job() }.onFailure { Log.w(TAG, "send: ${it.message}") } }
        scope.launch { refreshNodes() }
        scope.launch(Dispatchers.IO) { readStoredItems() }
        runCatching {
            Wearable.getCapabilityClient(this.context)
                .addListener({ scope.launch { refreshNodes() } }, WatchWire.WATCH_CAPABILITY)
        }
    }

    override fun send(message: WatchMessage) {
        val bytes = WatchWire.encode(message)
        outbox.trySend {
            val nodes = refreshNodes()
            if (!isWatchAppInstalled) return@trySend
            val messages = Wearable.getMessageClient(context)
            val delivered = nodes.isNotEmpty() && nodes.all { node ->
                runCatching { messages.sendMessage(node, WatchWire.MESSAGE_PATH, bytes).await() }.isSuccess
            }
            if (!delivered) put(WatchWire.QUEUED_TO_WATCH + UUID.randomUUID(), bytes)
        }
    }

    override fun updateState(state: WatchPhoneState) {
        val bytes = WatchWire.encode(state.payload)
        outbox.trySend { put(WatchWire.PHONE_STATE_PATH, bytes) }
    }

    private suspend fun put(path: String, bytes: ByteArray) {
        val request = PutDataMapRequest.create(path).apply { dataMap.putByteArray(WatchWire.PAYLOAD_KEY, bytes) }
            .asPutDataRequest().setUrgent()
        Wearable.getDataClient(context).putDataItem(request).await()
    }

    /** Updates [isWatchPaired] and [isWatchAppInstalled]; returns the reachable watches running Omi. */
    private suspend fun refreshNodes(): List<String> {
        val connected = runCatching { Wearable.getNodeClient(context).connectedNodes.await() }.getOrDefault(emptyList())
        val withApp = runCatching {
            Wearable.getCapabilityClient(context).getCapability(WatchWire.WATCH_CAPABILITY, CapabilityClient.FILTER_ALL).await().nodes
        }.getOrDefault(emptySet())
        withContext(Dispatchers.Main) {
            isWatchPaired = connected.isNotEmpty()
            isWatchAppInstalled = withApp.isNotEmpty()
        }
        val connectedIDs = connected.map { it.id }.toSet()
        return withApp.filter { it.id in connectedIDs }.sortedByDescending { it.isNearby }.map { it.id }
    }

    // MARK: In ([WatchListenerService], on the Data Layer's thread)

    internal fun receiveMessage(path: String, bytes: ByteArray) {
        if (path != WatchWire.MESSAGE_PATH) return
        WatchWire.message(bytes)?.let { inbox.trySend(it) }
    }

    /** The events are only valid during the call: everything is read before it returns. */
    internal fun receiveData(events: DataEventBuffer) {
        for (event in events) {
            if (event.type == DataEvent.TYPE_CHANGED) receive(event.dataItem)
        }
    }

    /** A recording: its frames, in order, until the watch closes the stream. */
    internal fun receiveRecording(channel: ChannelClient.Channel) {
        if (channel.path != WatchWire.RECORDING_CHANNEL_PATH) return
        scope.launch(Dispatchers.IO) {
            val client = Wearable.getChannelClient(context)
            runCatching {
                client.getInputStream(channel).await().use { input ->
                    while (true) {
                        val message = WatchWire.readFrame(input) ?: break
                        inbox.trySend(message)
                    }
                }
            }.onFailure { Log.w(TAG, "recording stream: ${it.message}") }
            runCatching { client.close(channel).await() }
        }
    }

    private fun receive(item: DataItem) {
        val path = item.uri.path ?: return
        if (!path.startsWith(WatchWire.QUEUED_TO_PHONE)) return
        val bytes = runCatching { DataMapItem.fromDataItem(item).dataMap.getByteArray(WatchWire.PAYLOAD_KEY) }.getOrNull() ?: return
        WatchWire.message(bytes)?.let { inbox.trySend(it) }
        val uri = item.uri
        scope.launch(Dispatchers.IO) { runCatching { Wearable.getDataClient(context).deleteDataItems(uri).await() } }
    }

    /** At launch: what the watch queued while the app was not running. */
    private suspend fun readStoredItems() {
        val buffer = runCatching {
            Wearable.getDataClient(context).getDataItems(Uri.parse("wear://*" + WatchWire.QUEUED_TO_PHONE), DataClient.FILTER_PREFIX).await()
        }.getOrNull() ?: return
        try {
            buffer.forEach { receive(it) }
        } finally {
            buffer.release()
        }
    }

    private companion object {
        const val TAG = "omi.watch"
    }
}

/**
 * The watch's messages, recordings and queued messages (the `WCSessionDelegate` callbacks of
 * `WatchSession.swift`). The system starts the app for them when it is not running.
 */
class WatchListenerService : WearableListenerService() {
    private val session get() = (application as OmiApplication).environment.watchSession

    override fun onMessageReceived(event: MessageEvent) {
        session.receiveMessage(event.path, event.data)
    }

    override fun onDataChanged(events: DataEventBuffer) {
        session.receiveData(events)
    }

    override fun onChannelOpened(channel: ChannelClient.Channel) {
        session.receiveRecording(channel)
    }
}
