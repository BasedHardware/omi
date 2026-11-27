package com.friend.ios

import android.content.Context
import io.flutter.util.PathUtils
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import java.io.File

@RunWith(RobolectricTestRunner::class)
class LiveWalReceiptDurabilityChannelTest {
    private val context: Context = RuntimeEnvironment.getApplication()

    @Test
    fun `accepts the path provider documents directory and its descendants`() {
        val documents = LiveWalReceiptDurabilityChannel.documentsDirectory(context)
        documents.mkdirs()
        val nested = File(documents, "nested").apply { mkdirs() }

        assertEquals(PathUtils.getDataDirectory(context).canonicalFile, documents)
        assertEquals(
            documents.canonicalFile,
            LiveWalReceiptDurabilityChannel.checkedDirectory(context, documents.path),
        )
        assertEquals(nested.canonicalFile, LiveWalReceiptDurabilityChannel.checkedDirectory(context, nested.path))
        assertEquals("app_flutter", documents.name)
    }

    @Test
    fun `rejects application support and external directories`() {
        val supportDirectory = context.filesDir.apply { mkdirs() }
        val externalDirectory = File(context.cacheDir.parentFile, "outside-live-wal").apply { mkdirs() }

        assertTrue(
            supportDirectory.canonicalPath !=
                LiveWalReceiptDurabilityChannel.documentsDirectory(context).canonicalPath,
        )
        assertThrows(SecurityException::class.java) {
            LiveWalReceiptDurabilityChannel.checkedDirectory(context, supportDirectory.path)
        }
        assertThrows(SecurityException::class.java) {
            LiveWalReceiptDurabilityChannel.checkedDirectory(context, externalDirectory.path)
        }
    }
}
