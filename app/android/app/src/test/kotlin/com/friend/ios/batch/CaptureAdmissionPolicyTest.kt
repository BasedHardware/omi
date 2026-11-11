package com.friend.ios.batch

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.json.JSONObject
import java.io.File

class CaptureAdmissionPolicyTest {
    private class Preferences(
        private val values: MutableMap<String, Any?> = mutableMapOf(),
    ) : NativeBlePreferences {
        override fun string(key: String, defaultValue: String): String = values[key] as? String ?: defaultValue
        override fun boolean(key: String, defaultValue: Boolean): Boolean = values[key] as? Boolean ?: defaultValue
        override fun integer(key: String, defaultValue: Int): Int = values[key] as? Int ?: defaultValue
        override fun contains(key: String): Boolean = values.containsKey(key)
    }

    @Before fun resetLatch() {
        CaptureAdmissionLatch.resetForTest()
    }

    @Test fun `missing canonical policy uses conservative legacy mute`() {
        val prefs = Preferences(mutableMapOf("deviceMuted" to false, "batchMuted" to true))

        assertEquals(CaptureAdmissionPolicy(true, 0), CaptureAdmissionPolicy.load(prefs))
    }

    @Test fun `valid canonical policy requires strict schema`() {
        val prefs = Preferences(mutableMapOf(
            "capturePolicy" to "{\"version\":1,\"revision\":7,\"muted\":false}",
            "deviceMuted" to true,
            "batchMuted" to true,
        ))

        val policy = CaptureAdmissionPolicy.load(prefs)
        assertFalse(policy.muted)
        assertEquals(7L, policy.revision)
    }

    @Test fun `malformed unsupported or weakly typed canonical policy denies audio`() {
        val invalid = listOf(
            "broken",
            "{\"version\":2,\"revision\":1,\"muted\":false}",
            "{\"version\":1,\"revision\":-1,\"muted\":false}",
            "{\"version\":1,\"revision\":1.0,\"muted\":false}",
            "{\"version\":1,\"revision\":1,\"muted\":1}",
            "{\"version\":1,\"revision\":1,\"muted\":false,\"extra\":true}",
        )
        for (raw in invalid) {
            val prefs = Preferences(mutableMapOf(
                "capturePolicy" to raw,
                "deviceMuted" to false,
                "batchMuted" to false,
            ))
            assertEquals("invalid policy $raw", CaptureAdmissionPolicy(true, 0), CaptureAdmissionPolicy.load(prefs))
        }
    }

    @Test fun `admission requires latest unmuted revision`() {
        val admitted = CaptureAdmissionPolicy(false, 3)
        assertTrue(CaptureAdmissionPolicy(false, 3).permits(admitted.revision))
        assertFalse(CaptureAdmissionPolicy(true, 3).permits(admitted.revision))
        assertFalse(CaptureAdmissionPolicy(false, 4).permits(admitted.revision))
    }

    @Test fun `process latch denies before persistence and rejects stale revisions`() {
        val prefs = Preferences(mutableMapOf(
            "capturePolicy" to "{\"version\":1,\"revision\":3,\"muted\":false}",
        ))
        assertTrue(CaptureAdmissionLatch.apply(muted = true, revision = 4))
        assertFalse(CaptureAdmissionLatch.apply(muted = false, revision = 3))
        assertEquals(CaptureAdmissionPolicy(true, 4), CaptureAdmissionPolicy.load(prefs))
        assertEquals(4L, CaptureAdmissionLatch.highWaterRevision())
        assertTrue(CaptureAdmissionLatch.apply(muted = false, revision = 5))
        assertEquals(CaptureAdmissionPolicy(false, 3), CaptureAdmissionPolicy.load(prefs))
    }

    @Test fun `unmuted latch never authorizes malformed policy`() {
        val prefs = Preferences(mutableMapOf(
            "capturePolicy" to "not-json",
        ))
        assertTrue(CaptureAdmissionLatch.apply(muted = false, revision = 7))
        assertEquals(CaptureAdmissionPolicy(true, 0), CaptureAdmissionPolicy.load(prefs))
    }

    @Test fun `newer durable unmute remains denied until explicit release`() {
        val prefs = Preferences(mutableMapOf(
            "capturePolicy" to "{\"version\":1,\"revision\":5,\"muted\":false}",
        ))
        assertTrue(CaptureAdmissionLatch.apply(muted = true, revision = 4))
        assertEquals(CaptureAdmissionPolicy(true, 5), CaptureAdmissionPolicy.load(prefs))
        assertTrue(CaptureAdmissionLatch.apply(muted = false, revision = 5))
        assertEquals(CaptureAdmissionPolicy(false, 5), CaptureAdmissionPolicy.load(prefs))
    }

    @Test fun `shared capture policy fixture matches Android parser`() {
        val fixture = listOf(
            File("../test/fixtures/capture_policy.json"),
            File("../../test/fixtures/capture_policy.json"),
        ).firstOrNull(File::isFile) ?: error("shared capture policy fixture not found")
        val cases = JSONObject(fixture.readText()).getJSONArray("cases")

        for (index in 0 until cases.length()) {
            val case = cases.getJSONObject(index)
            val values = mutableMapOf<String, Any?>(
                "deviceMuted" to case.getBoolean("deviceMuted"),
                "batchMuted" to case.getBoolean("batchMuted"),
            )
            if (!case.isNull("policy")) values["capturePolicy"] = case.getString("policy")

            val actual = CaptureAdmissionPolicy.load(Preferences(values))
            assertEquals(case.getString("name"), case.getBoolean("expectedMuted"), actual.muted)
            assertEquals(case.getString("name"), case.getLong("expectedRevision"), actual.revision)
        }
    }
}
