package com.friend.ios.phonemic

import android.content.SharedPreferences
import com.friend.ios.batch.BaseBatchAudioWriter
import com.friend.ios.batch.CaptureAdmissionLatch
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class PhoneMicBatchAudioWriterTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    @Before fun resetCaptureAdmissionLatch() {
        CaptureAdmissionLatch.resetForTest()
    }

    private class Preferences : SharedPreferences {
        private val values = mutableMapOf<String, Any?>()
        var onGet: ((String) -> Unit)? = null

        fun put(key: String, value: Any?) {
            if (value == null) values.remove(key) else values[key] = value
        }

        override fun getAll(): Map<String, *> = values.toMap()
        override fun getString(key: String, defValue: String?): String? {
            val value = values[key] as? String
            onGet?.invoke(key)
            return value ?: defValue
        }
        override fun getStringSet(key: String, defValues: MutableSet<String>?): MutableSet<String>? =
            (values[key] as? Set<*>)?.filterIsInstance<String>()?.toMutableSet() ?: defValues
        override fun getInt(key: String, defValue: Int): Int = values[key] as? Int ?: defValue
        override fun getLong(key: String, defValue: Long): Long = values[key] as? Long ?: defValue
        override fun getFloat(key: String, defValue: Float): Float = values[key] as? Float ?: defValue
        override fun getBoolean(key: String, defValue: Boolean): Boolean = values[key] as? Boolean ?: defValue
        override fun contains(key: String): Boolean = values.containsKey(key)
        override fun edit(): SharedPreferences.Editor = Editor()
        override fun registerOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener) {}
        override fun unregisterOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener) {}

        private inner class Editor : SharedPreferences.Editor {
            private val updates = mutableMapOf<String, Any?>()
            private var clear = false
            override fun putString(key: String, value: String?): SharedPreferences.Editor = apply { updates[key] = value }
            override fun putStringSet(key: String, values: MutableSet<String>?): SharedPreferences.Editor = apply { updates[key] = values }
            override fun putInt(key: String, value: Int): SharedPreferences.Editor = apply { updates[key] = value }
            override fun putLong(key: String, value: Long): SharedPreferences.Editor = apply { updates[key] = value }
            override fun putFloat(key: String, value: Float): SharedPreferences.Editor = apply { updates[key] = value }
            override fun putBoolean(key: String, value: Boolean): SharedPreferences.Editor = apply { updates[key] = value }
            override fun remove(key: String): SharedPreferences.Editor = apply { updates[key] = null }
            override fun clear(): SharedPreferences.Editor = apply { clear = true }
            override fun commit(): Boolean { apply(); return true }
            override fun apply() {
                if (clear) values.clear()
                updates.forEach { (key, value) -> if (value == null) values.remove(key) else values[key] = value }
            }
        }
    }

    private fun prefs(vararg values: Pair<String, Any?>): Preferences = Preferences().also { prefs ->
        values.forEach { (key, value) -> prefs.put("flutter.$key", value) }
    }

    private fun writer(preferences: Preferences, directory: File): PhoneMicBatchAudioWriter =
        PhoneMicBatchAudioWriter(directory.path, { preferences }, { }, { _, _ -> })

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

    @Test fun `legacy mute suppresses phone batch bytes and explicit unmute admits them`() {
        val preferences = prefs("batchMuted" to true)
        val writer = writer(preferences, temporaryFolder.root)
        writer.append(listOf(byteArrayOf(1, 2, 3)), "omibatchphone")
        assertFalse(temporaryFolder.root.exists() && temporaryFolder.root.listFiles()?.isNotEmpty() == true)

        preferences.put("flutter.capturePolicy", "{\"version\":1,\"revision\":2,\"muted\":false}")
        writer.append(listOf(byteArrayOf(4, 5)), "omibatchphone")
        val part = temporaryFolder.root.listFiles()!!.single { it.name.endsWith(".bin.part") }
        assertEquals(6L, part.length())
        writer.closeNow("test")
    }

    @Test fun `invalid policy fails closed at the phone batch write boundary`() {
        val preferences = prefs("capturePolicy" to "not-json")
        val writer = writer(preferences, temporaryFolder.root)
        writer.append(listOf(byteArrayOf(1, 2, 3)), "omibatchphone")
        assertFalse(temporaryFolder.root.exists() && temporaryFolder.root.listFiles()?.isNotEmpty() == true)
    }

    @Test fun `new revision observed during file setup prevents stale phone bytes`() {
        val preferences = prefs("capturePolicy" to "{\"version\":1,\"revision\":1,\"muted\":false}")
        var reads = 0
        preferences.onGet = { key ->
            if (key == "flutter.capturePolicy" && ++reads == 3) {
                preferences.put("flutter.capturePolicy", "{\"version\":1,\"revision\":2,\"muted\":true}")
            }
        }
        val writer = writer(preferences, temporaryFolder.root)
        writer.append(listOf(byteArrayOf(1, 2, 3)), "omibatchphone")
        writer.closeNow("test")
        val binaries = temporaryFolder.root.listFiles().orEmpty().filter { it.name.endsWith(".bin") }
        assertTrue(binaries.isEmpty())
    }

    private fun phoneBatchFileName(marker: String, startSec: Long): String =
        "audio_${marker}_opus_fs320_16000_1_fs320_${startSec}.bin"
}
