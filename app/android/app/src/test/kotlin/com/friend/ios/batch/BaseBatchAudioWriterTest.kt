package com.friend.ios.batch

import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile

class BaseBatchAudioWriterTest {
    @get:Rule val temporaryFolder = TemporaryFolder()

    private class Faults {
        var partialWrite: Int? = null
        var truncateFails = false
        fun open(file: File) = object : RandomAccessFile(file, "rw") {
            override fun write(bytes: ByteArray, offset: Int, length: Int) {
                val partial = partialWrite
                if (partial != null) {
                    super.write(bytes, offset, partial.coerceAtMost(length))
                    throw IOException("injected write failure")
                }
                super.write(bytes, offset, length)
            }
            override fun setLength(length: Long) {
                if (truncateFails) throw IOException("injected rollback failure")
                super.setLength(length)
            }
        }
    }

    private class Writer(val directory: File, faults: Faults, finalized: MutableList<String>) : BaseBatchAudioWriter(
        "audio_test_", { error("preferences not used") }, { finalized.add(it) }, { _, _ -> }, faults::open,
    ) {
        fun open(name: String = "audio_test_1.bin.part") = synchronized(lock) {
            openLocked(directory.path, name, 1, 0)
        }
        fun append(vararg values: Byte) = synchronized(lock) { writeFramesLocked(listOf(values)) }
        fun failedBarrier() = synchronized(lock) { consumeCloseSyncFailureLocked() }
    }

    @Test fun `failed rollback holds publication and failed restart repair remains pending`() {
        val dir = temporaryFolder.root
        val faults = Faults()
        val finalized = mutableListOf<String>()
        val writer = Writer(dir, faults, finalized)
        assertTrue(writer.open())
        assertTrue(writer.append(42))
        faults.partialWrite = 5 // header and one byte of a three-byte payload
        faults.truncateFails = true
        assertFalse(writer.append(1, 2, 3))
        assertTrue(writer.failedBarrier())
        val pending = File(dir, "audio_test_1.bin.part")
        val complete = File(dir, "audio_test_1.bin")
        assertTrue(pending.exists())
        assertFalse(complete.exists())
        assertTrue(finalized.isEmpty())

        assertFalse(writer.open()) // same-name reopen must not append to an unrepaired tail
        assertEquals(10L, pending.length())
        val restarted = Writer(dir, faults, finalized)
        assertTrue(restarted.open("audio_test_2.bin.part"))
        restarted.stop("test")
        assertTrue(pending.exists())
        assertFalse(complete.exists())

        faults.partialWrite = null
        faults.truncateFails = false
        val repaired = Writer(dir, faults, finalized)
        assertTrue(repaired.open("audio_test_2.bin.part"))
        repaired.stop("test")
        assertFalse(pending.exists())
        assertArrayEquals(byteArrayOf(1, 0, 0, 0, 42), complete.readBytes())
    }

    @Test fun `same-name reopen can retry repair and append without publishing torn data`() {
        val dir = temporaryFolder.root
        val faults = Faults()
        val finalized = mutableListOf<String>()
        val writer = Writer(dir, faults, finalized)
        assertTrue(writer.open())
        assertTrue(writer.append(42))
        faults.partialWrite = 2
        faults.truncateFails = true
        assertFalse(writer.append(1, 2, 3))
        assertFalse(writer.open())
        faults.partialWrite = null
        faults.truncateFails = false
        assertTrue(writer.open())
        assertTrue(writer.append(43))
        writer.stop("test")
        assertEquals(listOf("audio_test_1.bin"), finalized)
        assertArrayEquals(byteArrayOf(1, 0, 0, 0, 42, 1, 0, 0, 0, 43),
            File(dir, "audio_test_1.bin").readBytes())
    }

    @Test fun `restart repairs every torn header and payload including first-frame failures`() {
        for (priorFrame in listOf(false, true)) for (partial in 1..6) {
            val dir = temporaryFolder.newFolder()
            val faults = Faults()
            val writer = Writer(dir, faults, mutableListOf())
            assertTrue(writer.open())
            if (priorFrame) assertTrue(writer.append(42))
            faults.partialWrite = partial
            faults.truncateFails = true
            assertFalse(writer.append(1, 2, 3))
            assertTrue(File(dir, "audio_test_1.bin.part").exists())
            assertFalse(File(dir, "audio_test_1.bin").exists())
            assertTrue(writer.failedBarrier())
            faults.partialWrite = null
            faults.truncateFails = false
            val restarted = Writer(dir, faults, mutableListOf())
            assertTrue(restarted.open("audio_test_2.bin.part"))
            restarted.stop("test")
            assertFalse(File(dir, "audio_test_1.bin.part").exists())
            val repaired = File(dir, "audio_test_1.bin")
            if (priorFrame) assertArrayEquals(byteArrayOf(1, 0, 0, 0, 42), repaired.readBytes())
            else assertFalse(repaired.exists())
        }
    }

    @Test fun `successful rollback still immediately finalizes safe frames`() {
        val faults = Faults()
        val finalized = mutableListOf<String>()
        val writer = Writer(temporaryFolder.root, faults, finalized)
        assertTrue(writer.open())
        assertTrue(writer.append(42))
        faults.partialWrite = 5
        assertFalse(writer.append(1, 2, 3))
        assertFalse(writer.failedBarrier())
        assertEquals(listOf("audio_test_1.bin"), finalized)
        assertArrayEquals(byteArrayOf(1, 0, 0, 0, 42), File(temporaryFolder.root, finalized.single()).readBytes())
    }
}
