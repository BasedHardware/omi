package com.friend.ios.voice

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.friend.ios.service.voice.VoiceInput
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Port of `PhoneVoiceInput` (`VoiceInput.swift`): the phone microphone, 16 kHz mono PCM16 in
 * 100 ms chunks, as onboarding's voice steps and the chat's dictation read it.
 */
class PhoneVoiceInput(private val context: Context) : VoiceInput {
    private var record: AudioRecord? = null

    @SuppressLint("MissingPermission")
    override suspend fun start(): Flow<ByteArray> {
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            throw IllegalStateException("microphonePermission")
        }
        val minimum = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val recorder = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT, maxOf(minimum, CHUNK_BYTES * 4),
        )
        if (recorder.state != AudioRecord.STATE_INITIALIZED) {
            recorder.release()
            throw IllegalStateException("microphoneUnavailable")
        }
        recorder.startRecording()
        record = recorder
        return callbackFlow {
            val reader = launch(Dispatchers.IO) {
                val buffer = ByteArray(CHUNK_BYTES)
                while (isActive) {
                    val read = recorder.read(buffer, 0, buffer.size)
                    if (read <= 0) break
                    trySend(buffer.copyOf(read))
                }
                channel.close()
            }
            awaitClose { reader.cancel() }
        }.flowOn(Dispatchers.IO)
    }

    override fun stop() {
        record?.let {
            runCatching { it.stop() }
            it.release()
        }
        record = null
    }

    companion object {
        const val SAMPLE_RATE = 16000
        /** 100 ms of 16 kHz PCM16. */
        const val CHUNK_BYTES = 3200
    }
}
