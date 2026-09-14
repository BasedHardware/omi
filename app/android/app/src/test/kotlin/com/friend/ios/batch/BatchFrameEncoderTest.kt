package com.friend.ios.batch

import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile

class BatchFrameEncoderTest {
    @get:Rule val temporaryFolder = TemporaryFolder()

    private class CountingFile(file: File) : RandomAccessFile(file, "rw") {
        var writes = 0
        var failAfter: Int? = null
        override fun write(bytes: ByteArray, offset: Int, length: Int) {
            writes++
            val partial = failAfter
            if (partial != null) {
                super.write(bytes, offset, partial.coerceAtMost(length))
                throw IOException("injected partial write")
            }
            super.write(bytes, offset, length)
        }
    }

    @Test fun `one immediate write per frame preserves wire bytes through buffer reuse`() {
        val file = temporaryFolder.newFile()
        CountingFile(file).use { out ->
            val encoder = BatchFrameEncoder()
            assertEquals(7, encoder.write(out, byteArrayOf(10, 11, 12), 0))
            assertEquals(5, encoder.write(out, byteArrayOf(20), 7))
            assertEquals(4, encoder.write(out, byteArrayOf(), 12))
            assertEquals(3, out.writes)
            assertArrayEquals(byteArrayOf(3,0,0,0,10,11,12,1,0,0,0,20,0,0,0,0), file.readBytes())
        }
    }

    @Test fun `failed writes roll back every torn header or payload boundary then permit append`() {
        for (partial in 0..6) {
            val file = temporaryFolder.newFile()
            CountingFile(file).use { out ->
                val encoder = BatchFrameEncoder()
                encoder.write(out, byteArrayOf(42), 0)
                out.failAfter = partial
                assertThrows(IOException::class.java) { encoder.write(out, byteArrayOf(1, 2, 3), 5) }
            }
            RandomAccessFile(file, "rw").use { out ->
                assertEquals(5L, out.length())
                out.seek(out.length())
                BatchFrameEncoder().write(out, byteArrayOf(43), 5)
            }
            assertArrayEquals(byteArrayOf(1,0,0,0,42,1,0,0,0,43), file.readBytes())
        }
    }

}
