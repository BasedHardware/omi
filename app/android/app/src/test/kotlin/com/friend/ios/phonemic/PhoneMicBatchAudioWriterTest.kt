package com.friend.ios.phonemic

import com.friend.ios.batch.BaseBatchAudioWriter
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class PhoneMicBatchAudioWriterTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    @Test
    fun `skips both finalized and pending same-second filenames`() {
        val marker = "omibatchphone"
        val initialStartSec = 1_700_000_000L
        val dir = temporaryFolder.root
        File(dir, phoneBatchFileName(marker, initialStartSec)).writeBytes(byteArrayOf(1))
        File(dir, phoneBatchFileName(marker, initialStartSec + 1) + BaseBatchAudioWriter.PART_SUFFIX)
            .writeBytes(byteArrayOf(1))

        assertEquals(initialStartSec + 2, nextPhoneMicBatchStartSec(dir, marker, initialStartSec))
    }

    private fun phoneBatchFileName(marker: String, startSec: Long): String =
        "audio_${marker}_opus_fs320_16000_1_fs320_${startSec}.bin"
}
