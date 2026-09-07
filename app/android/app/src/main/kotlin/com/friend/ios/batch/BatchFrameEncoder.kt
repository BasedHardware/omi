package com.friend.ios.batch

import java.io.RandomAccessFile

/** Reuse one buffer and issue one immediate write per frame; no extra durability window. */
internal class BatchFrameEncoder {
    private var buffer = ByteArray(0)

    fun write(out: RandomAccessFile, frame: ByteArray, committedBytes: Long): Int {
        val size = Math.addExact(4, frame.size)
        if (buffer.size < size) buffer = ByteArray(size)
        for (index in 0..3) buffer[index] = (frame.size ushr (index * 8)).toByte()
        frame.copyInto(buffer, 4)
        try {
            out.write(buffer, 0, size)
        } catch (error: Exception) {
            // Same torn-frame rollback as the batch writer, before it finalizes the file.
            try { out.setLength(committedBytes) } catch (_: Exception) { }
            throw error
        }
        return size
    }
}
