package com.friend.ios.network.customstt

import com.friend.ios.network.await
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.concurrent.TimeUnit

/** Port of `CustomSTTSocket`: a live connection to a streaming provider (Deepgram): binary audio in, text messages out. */
interface CustomSTTSocket {
    /** Every text message; finishes when the connection closes or fails. */
    val messages: Flow<String>
    fun sendAudio(audio: ByteArray)
    fun sendText(text: String)
    fun close()
}

/**
 * Port of `CustomSTTTransport.swift`: how custom STT reaches its provider (real: OkHttp; tests: a
 * fake). Requests carry the user's key in a header: nothing here logs them.
 */
interface CustomSTTTransport {
    /** The body and HTTP status. */
    suspend fun send(request: Request): Pair<String, Int>
    fun openSocket(request: Request): CustomSTTSocket
}

class OkHttpCustomSTTTransport(private val client: OkHttpClient = defaultClient) : CustomSTTTransport {
    override suspend fun send(request: Request): Pair<String, Int> {
        val response = client.newCall(request).await()
        return response.use { withContext(Dispatchers.IO) { it.body?.string().orEmpty() } to it.code }
    }

    override fun openSocket(request: Request): CustomSTTSocket {
        val messages = Channel<String>(256, BufferOverflow.DROP_OLDEST)
        val socket = client.newWebSocket(
            request,
            object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, text: String) {
                    messages.trySend(text)
                }

                override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                    messages.trySend(bytes.utf8())
                }

                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                    messages.close()
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    messages.close()
                }
            },
        )
        return object : CustomSTTSocket {
            override val messages: Flow<String> = messages.receiveAsFlow()

            override fun sendAudio(audio: ByteArray) {
                socket.send(audio.toByteString())
            }

            override fun sendText(text: String) {
                socket.send(text)
            }

            override fun close() {
                socket.close(1000, null)
                messages.close()
            }
        }
    }

    companion object {
        /** A WAV upload waits up to a minute (iOS `timeoutInterval = 60`). */
        val defaultClient: OkHttpClient = OkHttpClient.Builder().callTimeout(60, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS).build()
    }
}
