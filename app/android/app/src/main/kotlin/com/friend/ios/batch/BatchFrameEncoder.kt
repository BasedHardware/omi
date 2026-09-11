package com.friend.ios.batch

import java.io.RandomAccessFile
import java.io.IOException

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
            try {
                out.setLength(committedBytes)
            } catch (rollback: Exception) {
                throw BatchFrameRollbackException(error, rollback)
            }
            throw error
        }
        return size
    }
    companion object {
        /** Recover the complete prefix of an existing recording before publishing or appending.
         * Only file boundaries are read; frame contents stay on disk. */
        fun recover(out: RandomAccessFile): Long {
            val length = out.length()
            var complete = 0L
            while (length - complete >= 4) {
                out.seek(complete)
                var frameSize = 0L
                repeat(4) { index ->
                    frameSize = frameSize or (out.readUnsignedByte().toLong() shl (index * 8))
                }
                if (frameSize > length - complete - 4) break
                complete += 4 + frameSize
            }
            if (complete != length) out.setLength(complete)
            out.seek(complete)
            return complete
        }
    }

}


internal class BatchFrameRollbackException(write: Exception, rollback: Exception) :
    IOException("Batch frame rollback failed", write) {
    init { addSuppressed(rollback) }
}
