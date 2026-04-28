package com.friend.ios

import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AmbientSpoolStoreInstrumentedTest {
    @Test
    fun writeChunkStopsWhenQuotaExceeded() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.getSharedPreferences("FlutterSharedPreferences", android.content.Context.MODE_PRIVATE)
            .edit()
            .putInt("flutter.ambient_capture_max_storage_mb", 0)
            .putInt("flutter.ambient_capture_min_free_storage_mb", 0)
            .apply()

        val store = AmbientSpoolStore(context)
        store.deleteByStatus(null)
        store.startSession()

        val result = store.writeChunk(ByteArray(320))

        assertFalse(result.written)
        assertEquals("ambient_spool_quota_exceeded", result.reason)

        store.closeSession()
        store.deleteByStatus(null)
    }

    @Test
    fun writeChunkStopsWhenFreeStorageIsTooLow() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        context.getSharedPreferences("FlutterSharedPreferences", android.content.Context.MODE_PRIVATE)
            .edit()
            .putInt("flutter.ambient_capture_max_storage_mb", 1024)
            .putInt("flutter.ambient_capture_min_free_storage_mb", Int.MAX_VALUE)
            .apply()

        val store = AmbientSpoolStore(context)
        store.deleteByStatus(null)
        store.startSession()

        val result = store.writeChunk(ByteArray(320))

        assertFalse(result.written)
        assertEquals("ambient_spool_low_storage", result.reason)

        store.closeSession()
        store.deleteByStatus(null)
    }
}
