package com.friend.ios

import android.util.Log
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.Node
import com.google.android.gms.wearable.WearableListenerService
import java.io.ByteArrayInputStream
import java.io.DataInputStream

/**
 * WearableListenerService that receives audio data from the omi4wearOS
 * watch app via the Wear Data Layer MessageClient.
 *
 * Listens on:
 *   /omi4wos/audio/speech — Opus-encoded speech audio chunks
 *   /omi4wos/audio/control — Control messages (start/stop/status)
 *
 * Deserializes the binary AudioChunk format (matching DataLayerSender.kt
 * on the watch) and forwards audio data to Flutter via [WearOsAudioBridge].
 */
class WearOsListenerService : WearableListenerService() {

    companion object {
        private const val TAG = "WearOsListener"
        private const val SPEECH_PATH = "/omi4wos/audio/speech"
        private const val CONTROL_PATH = "/omi4wos/audio/control"
    }

    override fun onMessageReceived(messageEvent: MessageEvent) {
        val path = messageEvent.path
        Log.d(TAG, "Message received: path=$path size=${messageEvent.data?.size ?: 0}")

        when {
            path.startsWith(SPEECH_PATH) -> handleAudioMessage(messageEvent)
            path == CONTROL_PATH -> handleControlMessage(messageEvent)
            else -> super.onMessageReceived(messageEvent)
        }
    }

    /**
     * Deserialize and forward an audio speech chunk.
     *
     * Binary format (from DataLayerSender.serializeChunk):
     *   segmentId:       UTF string (DataOutputStream.writeUTF)
     *   chunkIndex:      int
     *   timestampMs:     long
     *   durationMs:      long
     *   speechConfidence: float
     *   isFinal:         boolean
     *   audioDataLength: int
     *   audioData:       byte[audioDataLength]
     */
    private fun handleAudioMessage(messageEvent: MessageEvent) {
        val data = messageEvent.data ?: return

        try {
            val dis = DataInputStream(ByteArrayInputStream(data))

            val segmentId = dis.readUTF()
            val chunkIndex = dis.readInt()
            val timestampMs = dis.readLong()
            val durationMs = dis.readLong()
            val speechConfidence = dis.readFloat()
            val isFinal = dis.readBoolean()
            val audioDataLength = dis.readInt()
            val audioData = ByteArray(audioDataLength)
            dis.readFully(audioData)

            Log.d(
                TAG, "Audio chunk: seg=$segmentId idx=$chunkIndex " +
                        "ts=$timestampMs dur=${durationMs}ms conf=$speechConfidence " +
                        "final=$isFinal audioSize=$audioDataLength"
            )

            // Forward to Flutter via the bridge
            WearOsAudioBridge.onAudioDataReceived(
                audioData = audioData,
                isFinal = isFinal,
                segmentId = segmentId,
                confidence = speechConfidence.toDouble()
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to deserialize audio chunk", e)
        }
    }

    /**
     * Handle control messages from the watch.
     * Format: UTF command string, then int count of key-value extras.
     */
    private fun handleControlMessage(messageEvent: MessageEvent) {
        val data = messageEvent.data ?: return

        try {
            val dis = DataInputStream(ByteArrayInputStream(data))
            val command = dis.readUTF()
            val extrasCount = dis.readInt()
            val extras = mutableMapOf<String, String>()
            for (i in 0 until extrasCount) {
                val key = dis.readUTF()
                val value = dis.readUTF()
                extras[key] = value
            }

            Log.i(TAG, "Control message: command=$command extras=$extras")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to deserialize control message", e)
        }
    }

    override fun onPeerConnected(node: Node) {
        super.onPeerConnected(node)
        Log.i(TAG, "Watch peer connected: ${node.displayName} (${node.id})")
        WearOsAudioBridge.onWatchConnectionChanged(
            nodeId = node.id,
            displayName = node.displayName,
            connected = true
        )
    }

    override fun onPeerDisconnected(node: Node) {
        super.onPeerDisconnected(node)
        Log.i(TAG, "Watch peer disconnected: ${node.displayName} (${node.id})")
        WearOsAudioBridge.onWatchConnectionChanged(
            nodeId = node.id,
            displayName = node.displayName,
            connected = false
        )
    }
}
