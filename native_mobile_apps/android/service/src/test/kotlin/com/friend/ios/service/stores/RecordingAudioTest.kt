package com.friend.ios.service.stores

import com.friend.ios.service.PendingRecording
import com.friend.ios.service.fakeAPI
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.File
import java.nio.file.Files

/** Playing and sharing an Omi recording (`SyncStore.audioFile`): frames decoded into a 16 kHz WAV. */
@OptIn(ExperimentalCoroutinesApi::class)
class RecordingAudioTest {
    private fun file(directory: File, name: String, frames: List<ByteArray>) {
        val bytes = java.io.ByteArrayOutputStream()
        for (frame in frames) {
            bytes.write(byteArrayOf(frame.size.toByte(), 0, 0, 0))
            bytes.write(frame)
        }
        File(directory, name).writeBytes(bytes.toByteArray())
    }

    @Test fun opusFramesGoThroughTheDecoderIntoAWav() = runTest {
        val directory = Files.createTempDirectory("recordings").toFile()
        val sync = SyncStore(fakeAPI {}.client, directory, backgroundScope)
        val name = "audio_omi_opus_fs320_16000_1_fs320_1760000000.bin"
        file(directory, name, listOf(byteArrayOf(1, 2), byteArrayOf(3)))
        sync.files.adopt(PendingRecording(name, 1_760_000_000.0, 0, 0.02))
        var decoded: List<ByteArray>? = null
        sync.decodeOpus = { frames ->
            decoded = frames
            byteArrayOf(10, 0, 20, 0)
        }
        val wav = sync.audioFile(name)!!
        assertEquals(listOf(listOf<Byte>(1, 2), listOf<Byte>(3)), decoded!!.map { it.toList() })
        assertEquals("RIFF", String(wav.copyOfRange(0, 4)))
        assertEquals(16000, java.nio.ByteBuffer.wrap(wav, 24, 4).order(java.nio.ByteOrder.LITTLE_ENDIAN).int)
        assertArrayEquals(byteArrayOf(10, 0, 20, 0), wav.copyOfRange(44, 48))
    }

    @Test fun withoutADecoderOpusIsUnavailableButPCMPlays() = runTest {
        val directory = Files.createTempDirectory("recordings").toFile()
        val sync = SyncStore(fakeAPI {}.client, directory, backgroundScope)
        val opus = "audio_omi_opus_16000_1_fs160_1760000000.bin"
        val pcm = "audio_phonemic_pcm16_16000_1_fs160_1760000001.bin"
        file(directory, opus, listOf(byteArrayOf(1)))
        file(directory, pcm, listOf(byteArrayOf(5, 6), byteArrayOf(7, 8)))
        sync.files.adopt(PendingRecording(opus, 1_760_000_000.0, 0, 0.01))
        sync.files.adopt(PendingRecording(pcm, 1_760_000_001.0, 0, 0.01))
        assertNull(sync.audioFile(opus))
        assertArrayEquals(byteArrayOf(5, 6, 7, 8), sync.audioFile(pcm)!!.copyOfRange(44, 48))
        assertNull(sync.audioFile("missing.bin"))
    }
}
