package com.friend.ios

import android.app.Application
import android.content.Context
import android.os.Looper
import io.flutter.util.PathUtils
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36], manifest = Config.NONE, application = Application::class)
class LiveWalReceiptDurabilityChannelTest {
    private val context: Context = RuntimeEnvironment.getApplication()

    private class CapturedResult : MethodChannel.Result {
        val completed = CountDownLatch(1)
        var success = false
        var errorCode: String? = null

        override fun success(result: Any?) {
            success = true
            completed.countDown()
        }

        override fun error(errorCode: String, errorMessage: String?, errorDetails: Any?) {
            this.errorCode = errorCode
            completed.countDown()
        }

        override fun notImplemented() {
            errorCode = "not_implemented"
            completed.countDown()
        }
    }

    private fun invokeDirectorySync(path: String): CapturedResult {
        val response = CapturedResult()
        LiveWalReceiptDurabilityChannel.handle(
            context,
            MethodCall("syncDirectory", mapOf("path" to path)),
            response,
        )
        val mainLooper = shadowOf(Looper.getMainLooper())
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
        var completed = false
        while (!completed && System.nanoTime() < deadline) {
            mainLooper.idle()
            completed = response.completed.await(10, TimeUnit.MILLISECONDS)
        }
        mainLooper.idle()
        assertTrue("native channel response timed out", completed || response.completed.await(1, TimeUnit.SECONDS))
        return response
    }

    @Test
    fun `accepts the path provider documents directory and its descendants`() {
        val documents = LiveWalReceiptDurabilityChannel.documentsDirectory(context)
        documents.mkdirs()
        val nested = File(documents, "nested").apply { mkdirs() }

        assertEquals(File(PathUtils.getDataDirectory(context)).canonicalFile, documents)
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

    @Test
    fun `registered handler syncs a documents directory successfully`() {
        val documents = LiveWalReceiptDurabilityChannel.documentsDirectory(context)
        val nested = File(documents, "durability-test").apply { mkdirs() }

        LiveWalReceiptDurabilityChannel.directoryFsyncForTesting = { _ -> }
        try {
            val response = invokeDirectorySync(nested.path)
            assertTrue(response.success)
            assertEquals(null, response.errorCode)
        } finally {
            LiveWalReceiptDurabilityChannel.directoryFsyncForTesting = null
        }
    }

    @Test
    fun `native directory barrier opens and fsyncs a real documents directory`() {
        val nested = File(
            LiveWalReceiptDurabilityChannel.documentsDirectory(context),
            "native-fsync-test",
        ).apply { mkdirs() }
        val marker = File(nested, "entry").apply { writeText("directory entry") }
        val previousOverride = LiveWalReceiptDurabilityChannel.directoryFsyncForTesting
        LiveWalReceiptDurabilityChannel.directoryFsyncForTesting = null

        try {
            LiveWalReceiptDurabilityChannel.syncDirectory(context, nested.path)
            assertTrue(marker.isFile)
        } finally {
            LiveWalReceiptDurabilityChannel.directoryFsyncForTesting = previousOverride
        }
    }

    @Test
    fun `registered handler rejects paths outside documents`() {
        val outside = File(context.cacheDir.parentFile, "outside-live-wal-sync").apply { mkdirs() }

        val response = invokeDirectorySync(outside.path)
        assertEquals("invalid_path", response.errorCode)
        assertEquals(false, response.success)
    }

    @Test
    fun `registered handler replies when directory sync throws an Error`() {
        val documents = LiveWalReceiptDurabilityChannel.documentsDirectory(context)
        val nested = File(documents, "durability-error-test").apply { mkdirs() }
        LiveWalReceiptDurabilityChannel.directoryFsyncForTesting = {
            throw LinkageError("injected native fsync error")
        }

        try {
            val response = invokeDirectorySync(nested.path)
            assertEquals("directory_sync_failed", response.errorCode)
            assertEquals(false, response.success)
        } finally {
            LiveWalReceiptDurabilityChannel.directoryFsyncForTesting = null
        }
    }
}
