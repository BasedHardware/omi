package com.friend.ios.audio

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File

/**
 * Port of `AudioFileCapture.swift`: plays an audio file through the capture pipeline in real time,
 * as if it came from the microphone. For emulator and CI runs, never used in release builds.
 * Android reads a WAV that is already 16 kHz mono PCM16 (`say -o x.wav --data-format=LEI16@16000`).
 */
class AudioFileCapture(private val file: File) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var job: Job? = null
    private var stopHandler: (() -> Unit)? = null

    fun start(): PhoneMicCapture.Output {
        val data = file.readBytes()
        val pcm = Channel<ByteArray>(512, BufferOverflow.DROP_OLDEST)
        val level = Channel<Float>(1, BufferOverflow.DROP_OLDEST)
        val samples = data.copyOfRange(dataOffset(data), data.size)
        job = scope.launch {
            var offset = 0
            while (isActive && offset < samples.size) {
                val end = minOf(offset + CHUNK_BYTES, samples.size)
                val chunk = samples.copyOfRange(offset, end)
                pcm.trySend(chunk)
                level.trySend(PhoneMicCapture.rms(chunk))
                offset = end
                delay(chunk.size / 32L) // 32 bytes per ms at 16 kHz PCM16
            }
            level.trySend(0f)
            // Keep the streams open (silence) until stopped, like a quiet room.
        }
        stopHandler = {
            pcm.close()
            level.close()
        }
        return PhoneMicCapture.Output(pcm.receiveAsFlow(), level.receiveAsFlow())
    }

    fun stop() {
        job?.cancel()
        stopHandler?.invoke()
        stopHandler = null
    }

    companion object {
        private const val CHUNK_BYTES = 2560

        /** Where the `data` chunk of a RIFF/WAVE file starts; 0 for raw PCM. */
        internal fun dataOffset(bytes: ByteArray): Int {
            if (bytes.size < 12 || String(bytes, 0, 4) != "RIFF") return 0
            var index = 12
            while (index + 8 <= bytes.size) {
                val id = String(bytes, index, 4)
                val size = (bytes[index + 4].toInt() and 0xFF) or ((bytes[index + 5].toInt() and 0xFF) shl 8) or
                    ((bytes[index + 6].toInt() and 0xFF) shl 16) or ((bytes[index + 7].toInt() and 0xFF) shl 24)
                if (id == "data") return index + 8
                index += 8 + size + (size and 1)
            }
            return 44
        }
    }
}
