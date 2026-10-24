package com.friend.ios.wear

import android.content.Context
import android.net.Uri
import android.util.Log
import com.friend.ios.core.watch.WatchMessage
import com.friend.ios.core.watch.WatchPhoneState
import com.friend.ios.core.watch.WatchWire
import com.google.android.gms.wearable.CapabilityClient
import com.google.android.gms.wearable.ChannelClient
import com.google.android.gms.wearable.DataClient
import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataItem
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import java.io.OutputStream
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

/**
 * Port of `WatchConnection.swift`: the watch's end of the link, on the Wear OS Data Layer.
 *
 * iOS sends live with `sendMessage` while the iPhone is reachable and otherwise queues with
 * `transferUserInfo`, in order; once one message of a recording was queued, the rest is queued
 * too, so the stop never overtakes the last audio. Here a recording is one `ChannelClient` stream
 * (`startRecording`, the audio, `stopRecording`: in order by construction) that is reopened while
 * the phone is away; other messages go live with `MessageClient` and fall back to a queued data
 * item. Everything leaves through one outbox, in the order it was sent.
 */
class WatchConnection(context: Context, private val scope: CoroutineScope) {
    private val context = context.applicationContext
    private val messageSink = Channel<WatchMessage>(Channel.UNLIMITED)
    private val stateSink = MutableStateFlow<WatchPhoneState?>(null)
    /** Messages from the phone, in arrival order. */
    val messages: Flow<WatchMessage> = messageSink.receiveAsFlow()
    /** What the phone reported last (iOS application context). */
    val phoneStates: StateFlow<WatchPhoneState?> = stateSink

    private sealed interface Outgoing {
        data class Live(val message: WatchMessage) : Outgoing
        data class Recording(val message: WatchMessage) : Outgoing
        /** The recording's stream is done: close it once what came before is out. */
        data object EndRecording : Outgoing
    }

    private val outbox = Channel<Outgoing>(Channel.UNLIMITED)
    private val lock = Any()
    /** Between `beginRecording` and its stop, recording messages go to the recording stream. */
    private var recording = false
    /** Audio waiting in the outbox: beyond [MAX_QUEUED_AUDIO] new audio is dropped. */
    private val queuedAudio = AtomicInteger(0)
    private var stream: OutputStream? = null
    private var channel: ChannelClient.Channel? = null

    fun activate() {
        scope.launch(Dispatchers.IO) { drain() }
        scope.launch(Dispatchers.IO) { readStoredItems() }
    }

    /** A new recording: its messages go to a new stream (the last one is closed first). */
    fun beginRecording() {
        synchronized(lock) {
            if (recording) outbox.trySend(Outgoing.EndRecording)
            recording = true
        }
    }

    /** The phone ended the recording: the watch sends no stop, so its stream is closed here. */
    fun endRecording() {
        synchronized(lock) {
            if (!recording) return
            recording = false
            outbox.trySend(Outgoing.EndRecording)
        }
    }

    /** Any thread (the microphone hands its chunks over on its own). */
    fun send(message: WatchMessage) {
        synchronized(lock) {
            val partOfRecording = recording && (
                message is WatchMessage.StartRecording || message is WatchMessage.AudioChunk ||
                    message is WatchMessage.StopRecording || message is WatchMessage.RecordingError
                )
            if (!partOfRecording) {
                outbox.trySend(Outgoing.Live(message))
                return
            }
            if (message is WatchMessage.AudioChunk && !message.chunk.isLast) {
                if (queuedAudio.get() >= MAX_QUEUED_AUDIO) return
                queuedAudio.incrementAndGet()
            }
            outbox.trySend(Outgoing.Recording(message))
            if (message is WatchMessage.StopRecording) {
                recording = false
                outbox.trySend(Outgoing.EndRecording)
            }
        }
    }

    // MARK: Out

    private suspend fun drain() {
        for (item in outbox) {
            when (item) {
                is Outgoing.Live -> deliverLive(item.message)
                is Outgoing.Recording -> {
                    deliverToRecording(item.message)
                    if (item.message is WatchMessage.AudioChunk && !item.message.chunk.isLast) queuedAudio.decrementAndGet()
                }
                Outgoing.EndRecording -> closeRecording()
            }
        }
    }

    /** Written once a stream to the phone is open; while the phone is away it waits and retries. */
    private suspend fun deliverToRecording(message: WatchMessage) {
        var wait = RETRY_START_MILLIS
        while (true) {
            try {
                val out = stream ?: openRecording()
                if (out != null) {
                    WatchWire.writeFrame(out, message)
                    return
                }
            } catch (error: Exception) {
                Log.w(TAG, "recording stream: ${error.message}")
                closeRecording()
            }
            delay(wait)
            wait = minOf(wait * 2, RETRY_MAX_MILLIS)
        }
    }

    private suspend fun openRecording(): OutputStream? {
        val node = phoneNodeID() ?: return null
        val client = Wearable.getChannelClient(context)
        val opened = client.openChannel(node, WatchWire.RECORDING_CHANNEL_PATH).await()
        channel = opened
        return client.getOutputStream(opened).await().also { stream = it }
    }

    private suspend fun closeRecording() {
        runCatching { stream?.close() }
        stream = null
        channel?.let { runCatching { Wearable.getChannelClient(context).close(it).await() } }
        channel = null
    }

    private suspend fun deliverLive(message: WatchMessage) {
        val bytes = WatchWire.encode(message)
        val node = runCatching { phoneNodeID() }.getOrNull()
        if (node != null) {
            val sent = runCatching { Wearable.getMessageClient(context).sendMessage(node, WatchWire.MESSAGE_PATH, bytes).await() }
            if (sent.isSuccess) return
        }
        queue(bytes)
    }

    /** iOS `transferUserInfo`: a data item the Data Layer keeps until the phone takes it. */
    private suspend fun queue(bytes: ByteArray) {
        val request = PutDataMapRequest.create(WatchWire.QUEUED_TO_PHONE + UUID.randomUUID()).apply {
            dataMap.putByteArray(WatchWire.PAYLOAD_KEY, bytes)
        }.asPutDataRequest().setUrgent()
        runCatching { Wearable.getDataClient(context).putDataItem(request).await() }
            .onFailure { Log.w(TAG, "queue: ${it.message}") }
    }

    /** The phone running the Omi app, nearby first; any connected phone before the capability is known. */
    private suspend fun phoneNodeID(): String? {
        val capable = Wearable.getCapabilityClient(context)
            .getCapability(WatchWire.PHONE_CAPABILITY, CapabilityClient.FILTER_REACHABLE).await().nodes
        val nodes = capable.ifEmpty { Wearable.getNodeClient(context).connectedNodes.await().toSet() }
        return (nodes.firstOrNull { it.isNearby } ?: nodes.firstOrNull())?.id
    }

    // MARK: In (WatchListenerService, on the Data Layer's thread)

    fun receiveMessage(path: String, bytes: ByteArray) {
        if (path != WatchWire.MESSAGE_PATH) return
        WatchWire.message(bytes)?.let { messageSink.trySend(it) }
    }

    /** The events are only valid during the call: everything is read before it returns. */
    fun receiveData(events: DataEventBuffer) {
        for (event in events) {
            if (event.type == DataEvent.TYPE_CHANGED) receive(event.dataItem)
        }
    }

    private fun receive(item: DataItem) {
        val path = item.uri.path ?: return
        val bytes = runCatching { DataMapItem.fromDataItem(item).dataMap.getByteArray(WatchWire.PAYLOAD_KEY) }.getOrNull() ?: return
        when {
            path == WatchWire.PHONE_STATE_PATH -> WatchWire.phoneState(bytes)?.let { stateSink.value = it }
            path.startsWith(WatchWire.QUEUED_TO_WATCH) -> {
                WatchWire.message(bytes)?.let { messageSink.trySend(it) }
                val uri = item.uri
                scope.launch(Dispatchers.IO) { runCatching { Wearable.getDataClient(context).deleteDataItems(uri).await() } }
            }
        }
    }

    /** At launch: the phone's last state and anything it queued while the app was not running. */
    private suspend fun readStoredItems() {
        val buffer = runCatching {
            Wearable.getDataClient(context).getDataItems(Uri.parse("wear://*/omi/watch/"), DataClient.FILTER_PREFIX).await()
        }.getOrNull() ?: return
        try {
            buffer.forEach { receive(it) }
        } finally {
            buffer.release()
        }
    }

    companion object {
        private const val TAG = "omi.watch"
        /** About ten minutes of audio waits for a phone that is away; newer audio is dropped after that. */
        const val MAX_QUEUED_AUDIO = 400
        private const val RETRY_START_MILLIS = 1_000L
        private const val RETRY_MAX_MILLIS = 5_000L
    }
}
