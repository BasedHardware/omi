package com.friend.ios.ble

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class BatteryHistorySessionStoreTest {
    @Test fun `process death does not turn the live session start into an outage`() {
        val disk = mutableMapOf<String, String>()
        fun process() = BatteryHistorySessionStore({ disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        process().start("device", 1000, "new+2")
        val restarted = process()
        assertNull(restarted.openSince("device"))
        restarted.start("device", 12000, "new+2")
        assertNull(restarted.openSince("device"))
        assertFalse(disk.keys.any { it.startsWith("audio_outage_") })
        assertTrue(disk["session_device"]!!.contains("new+2"))
    }
    @Test fun `measured disconnect marker survives reconnect until recovery`() {
        val disk = mutableMapOf<String, String>()
        fun process() = BatteryHistorySessionStore({ disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        val first = process()
        first.start("device", 1000, "new+2")
        // The service commits this row before end() writes the marker.
        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 5000))
            .toString()
        first.end("device", 5000)
        val restarted = process()
        assertEquals(5000L, restarted.openSince("device"))
        restarted.start("device", 12000, "new+2")
        assertEquals(5000L, restarted.openSince("device"))
        disk.remove("audio_outage_device")
        assertNull(restarted.openSince("device"))
    }
    @Test fun `session start echo is discarded and not revived`() {
        val disk = mutableMapOf<String, String>()
        fun process() = BatteryHistorySessionStore({ disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        val first = process()
        first.start("device", 1000, "build")
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "1000"
        // A later disconnect does not prove this marker's row was absent.
        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 80000))
            .toString()
        val restarted = process()
        assertEquals(
            AudioOutageMarkerVerdict.AMBIGUOUS,
            judgeAudioOutageMarker(disk["disconnect_history_device"], disk["session_device"], 7L, 1000L, true),
        )
        assertNull(restarted.openSince("device"))
        assertEquals("1000", disk["audio_outage_device"])
        restarted.start("device", 12000, "build")
        assertNull(restarted.openSince("device"))
        assertFalse(disk.keys.any { it.startsWith("audio_outage_") })
        assertTrue(disk["session_device"]!!.contains("12000"))
        // A few seconds before this session, with no row of its own, is not billed.
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "9000"
        assertNull(restarted.openSince("device"))
        assertEquals("9000", disk["audio_outage_device"])
    }
    @Test fun `pruned disconnect history keeps a genuine marker`() {
        val disk = mutableMapOf<String, String>()
        val store = BatteryHistorySessionStore({ disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        store.start("device", 1000, "build")
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "90000"
        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 90000))
            .toString()
        assertEquals(90000L, store.openSince("device"))
        assertEquals("90000", disk["audio_outage_device"])
        val plan = planAudioOutageCleanup("[]", disk["session_device"], 7L, 90000L, markerEpochMatches = true)
        assertFalse(plan.dropMarker)
        assertNull(plan.rewrittenHistory)
        // Pruned to [] cannot tell a session-start copy from a same-millisecond disconnect.
        disk["audio_outage_device"] = "1000"
        disk["disconnect_history_device"] = "[]"
        assertNull(store.openSince("device"))
        assertEquals("1000", disk["audio_outage_device"])
        assertEquals("7", disk["audio_outage_epoch_device"])
    }
    @Test fun `unreadable disconnect history keeps a genuine marker`() {
        val session = JSONObject().put("device", "device").put("started_at", 1000).put("identity_epoch", 7).toString()
        val genuine = planAudioOutageCleanup("{", session, 7L, 90000L, markerEpochMatches = true)
        assertFalse(genuine.dropMarker)
        assertNull(genuine.rewrittenHistory)
        val echo = planAudioOutageCleanup("{", session, 7L, 1000L, markerEpochMatches = true)
        assertFalse(echo.dropMarker)
        assertNull(echo.rewrittenHistory)
        val recoveryOnly = JSONArray()
            .put(JSONObject().put("eventType", "audio_recovered").put("timestamp", 1000).put("lostAudioResolvedAt", 2000))
            .toString()
        val untouched = planAudioOutageCleanup(recoveryOnly, session, 7L, 1000L, markerEpochMatches = true)
        assertFalse(untouched.dropMarker)
        assertNull(untouched.rewrittenHistory)
        val mismatchedEpoch = planAudioOutageCleanup("[]", session, 8L, 1000L, markerEpochMatches = true)
        assertFalse(mismatchedEpoch.dropMarker)
        assertNull(mismatchedEpoch.rewrittenHistory)
        val disk = mutableMapOf<String, String>()
        disk["session_device"] = session
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "1000"
        disk["disconnect_history_device"] = "{"
        val store = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        assertNull(store.openSince("device"))
        assertEquals("1000", disk["audio_outage_device"])
        assertEquals("7", disk["audio_outage_epoch_device"])
    }
    @Test fun `only a session-start echo recovery is dropped`() {
        val history = JSONArray()
            .put(JSONObject().put("eventType", "audio_recovered").put("timestamp", 1000).put("lostAudioResolvedAt", 20000))
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 8000))
            .put(JSONObject().put("eventType", "audio_recovered").put("timestamp", 90000).put("lostAudioResolvedAt", 91000))
        val kept = dropUnmeasuredAudioRecoveries(history, 1000)
        assertEquals(2, kept.length())
        assertEquals("disconnect", kept.getJSONObject(0).getString("eventType"))
        assertEquals(90000L, kept.getJSONObject(1).getLong("timestamp"))
        assertSame(history, dropUnmeasuredAudioRecoveries(history, null))
        val beforeSession = JSONArray().put(JSONObject().put("eventType", "audio_recovered").put("timestamp", 9000))
        assertSame(beforeSession, dropUnmeasuredAudioRecoveries(beforeSession, 12000))
        val shortLink = JSONArray().put(
            JSONObject().put("eventType", "audio_recovered").put("timestamp", 12003).put("lostAudioResolvedAt", 13000))
        assertSame(shortLink, dropUnmeasuredAudioRecoveries(shortLink, 12000))
    }
    @Test fun `stale session keeps a short-link disconnect marker`() {
        val session = JSONObject().put("device", "device").put("started_at", 12000).put("identity_epoch", 7).toString()
        val history = JSONArray().put(JSONObject().put("eventType", "disconnect").put("timestamp", 12003)).toString()
        val plan = planAudioOutageCleanup(history, session, 7L, 12003L, markerEpochMatches = true)
        assertFalse(plan.dropMarker)
        assertNull(plan.rewrittenHistory)
        // The crash window is after the marker write and before history or session removal.
        val beforeHistory = planAudioOutageCleanup("[]", session, 7L, 12003L, markerEpochMatches = true)
        assertFalse(beforeHistory.dropMarker)
        val disk = mutableMapOf<String, String>()
        disk["session_device"] = session
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "12003"
        disk["disconnect_history_device"] = history
        val store = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        assertEquals(
            AudioOutageMarkerVerdict.GENUINE,
            judgeAudioOutageMarker(history, session, 7L, 12003L, true),
        )
        assertEquals(12003L, store.openSince("device"))
        assertEquals("12003", disk["audio_outage_device"])
        val echo = planAudioOutageCleanup("[]", session, 7L, 12000L, markerEpochMatches = true)
        assertFalse(echo.dropMarker)
        assertNull(echo.rewrittenHistory)
        val supported = JSONArray().put(JSONObject().put("eventType", "disconnect").put("timestamp", 12000)).toString()
        assertFalse(planAudioOutageCleanup(supported, session, 7L, 12000L, markerEpochMatches = true).dropMarker)
        val later = JSONArray().put(JSONObject().put("eventType", "disconnect").put("timestamp", 80000)).toString()
        val oldSession = JSONObject().put("started_at", 1000).put("identity_epoch", 7).toString()
        assertEquals(
            AudioOutageMarkerVerdict.AMBIGUOUS,
            judgeAudioOutageMarker(later, oldSession, 7L, 1000L, true),
        )
        assertFalse(planAudioOutageCleanup(later, oldSession, 7L, 1000L, markerEpochMatches = true).dropMarker)
    }
    @Test fun `recovery proofs keep genuine standalone resolutions`() {
        val now = 10_000_000L
        val once = appendAudioRecoveryProof(null, 1000, 5000, 7, now)
        val twice = appendAudioRecoveryProof(once, 8000, 9000, 7, now)
        val stamps = audioRecoveryStamps(twice, 7, now)
        assertEquals(2, stamps.size)
        assertEquals(1000L, stamps[0].start)
        assertEquals(9000L, stamps[1].at)
        val payload = putAudioRecoveryStamps(JSONObject(), twice, 7, now)
        assertEquals(8000L, payload.getLong("audio_outage_resolved_start"))
        assertEquals(9000L, payload.getLong("audio_outage_resolved_at"))
        assertEquals(2, payload.getJSONArray("audio_outage_recovery_proofs").length())
        assertTrue(audioRecoveryStamps(twice, 8, now).isEmpty())
        assertTrue(audioRecoveryStamps(twice, 7, now + AUDIO_RECOVERY_PROOF_RETENTION_MS + 1).isEmpty())
    }
    @Test fun `manual teardown writes marker before session cleanup`() {
        val disk = mutableMapOf<String, String>()
        val operations = mutableListOf<String>()
        val store = BatteryHistorySessionStore({ disk[it] }, { k, v -> operations.add("write:$k"); disk[k] = v },
            { operations.add("remove:$it"); disk.remove(it) }, { 1L }, { true })
        store.start("device", 1000, "build")
        operations.clear()
        store.end("device", 2000)
        assertEquals(listOf("write:audio_outage_epoch_device", "write:audio_outage_device", "remove:session_device"), operations)
        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 2000))
            .toString()
        assertEquals(2000L, store.openSince("device"))
    }
    @Test fun `ambiguous marker is cleared when the next session starts`() {
        val disk = mutableMapOf<String, String>()
        fun process() = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        for (history in listOf("[]", "{")) {
            disk.clear()
            disk["session_device"] = JSONObject().put("device", "device").put("started_at", 1000)
                .put("identity_epoch", 7).toString()
            disk["audio_outage_epoch_device"] = "7"
            disk["audio_outage_device"] = "1000"
            disk["disconnect_history_device"] = history
            val restarted = process()
            assertNull(restarted.openSince("device"))
            assertEquals("1000", disk["audio_outage_device"])
            restarted.start("device", 30000, "build")
            assertNull(history, restarted.openSince("device"))
            assertFalse(history, disk.keys.any { it.startsWith("audio_outage_") })
            assertTrue(disk["session_device"]!!.contains("30000"))
        }
    }

    @Test fun `genuine same-millisecond disconnect is kept when its row is present`() {
        val disk = mutableMapOf<String, String>()
        val session = JSONObject().put("device", "device").put("started_at", 20000).put("identity_epoch", 7).toString()
        disk["session_device"] = session
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "20000"
        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 1000))
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 20000))
            .toString()
        val store = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        assertEquals(20000L, store.openSince("device"))
        assertEquals("20000", disk["audio_outage_device"])
        assertFalse(planAudioOutageCleanup(disk["disconnect_history_device"], session, 7L, 20000L, true).dropMarker)
        store.start("device", 80000, "build")
        assertEquals(20000L, store.openSince("device"))
    }

    @Test fun `echo covered by an older disconnect row is dropped`() {
        val disk = mutableMapOf<String, String>()
        val session = JSONObject().put("device", "device").put("started_at", 20000).put("identity_epoch", 7).toString()
        disk["session_device"] = session
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "20000"
        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 1000))
            .toString()
        val store = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        assertEquals(
            AudioOutageMarkerVerdict.ECHO,
            judgeAudioOutageMarker(disk["disconnect_history_device"], session, 7L, 20000L, true),
        )
        assertNull(store.openSince("device"))
        assertFalse(disk.keys.any { it.startsWith("audio_outage_") })
        assertTrue(planAudioOutageCleanup(disk["disconnect_history_device"], session, 7L, 20000L, true).dropMarker)
        store.start("device", 80000, "build")
        assertNull(store.openSince("device"))
        assertFalse(disk.keys.any { it.startsWith("audio_outage_") })
    }

    @Test fun `disconnect row without a timestamp is not coverage and keeps the marker`() {
        val disk = mutableMapOf<String, String>()
        val session = JSONObject().put("device", "device").put("started_at", 90000).put("identity_epoch", 7).toString()
        disk["session_device"] = session
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "90000"
        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect"))
            .toString()
        val store = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        assertEquals(
            AudioOutageMarkerVerdict.AMBIGUOUS,
            judgeAudioOutageMarker(disk["disconnect_history_device"], session, 7L, 90000L, true),
        )
        assertNull(store.openSince("device"))
        assertEquals("90000", disk["audio_outage_device"])
        assertEquals("7", disk["audio_outage_epoch_device"])
        assertFalse(planAudioOutageCleanup(disk["disconnect_history_device"], session, 7L, 90000L, true).dropMarker)
    }

    @Test fun `numeric string timestamp is not coverage or direct evidence and keeps the marker`() {
        val disk = mutableMapOf<String, String>()
        val session = JSONObject().put("device", "device").put("started_at", 90000).put("identity_epoch", 7).toString()
        disk["session_device"] = session
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "90000"
        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", "1"))
            .toString()
        val store = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        val history = parsedDisconnectHistory(disk["disconnect_history_device"])!!
        assertFalse(historyCoversMarker(history, 90000L))
        assertEquals(
            AudioOutageMarkerVerdict.AMBIGUOUS,
            judgeAudioOutageMarker(disk["disconnect_history_device"], session, 7L, 90000L, true),
        )
        assertNull(store.openSince("device"))
        assertEquals("90000", disk["audio_outage_device"])
        assertEquals("7", disk["audio_outage_epoch_device"])
        assertFalse(planAudioOutageCleanup(disk["disconnect_history_device"], session, 7L, 90000L, true).dropMarker)

        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", "90000"))
            .toString()
        val stringMarker = parsedDisconnectHistory(disk["disconnect_history_device"])!!
        assertFalse(disconnectEvidenceSupportsMarker(stringMarker, 90000L))
        assertEquals(
            AudioOutageMarkerVerdict.AMBIGUOUS,
            judgeAudioOutageMarker(disk["disconnect_history_device"], session, 7L, 90000L, true),
        )
        assertNull(store.openSince("device"))
        assertEquals("90000", disk["audio_outage_device"])
        assertEquals("7", disk["audio_outage_epoch_device"])
        assertFalse(planAudioOutageCleanup(disk["disconnect_history_device"], session, 7L, 90000L, true).dropMarker)

        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 90000.5))
            .toString()
        val fractionalMarker = parsedDisconnectHistory(disk["disconnect_history_device"])!!
        assertFalse(disconnectEvidenceSupportsMarker(fractionalMarker, 90000L))
        assertEquals(
            AudioOutageMarkerVerdict.AMBIGUOUS,
            judgeAudioOutageMarker(disk["disconnect_history_device"], session, 7L, 90000L, true),
        )
        assertNull(store.openSince("device"))
        assertEquals("90000", disk["audio_outage_device"])
        assertEquals("7", disk["audio_outage_epoch_device"])
        assertFalse(planAudioOutageCleanup(disk["disconnect_history_device"], session, 7L, 90000L, true).dropMarker)
    }

    @Test fun `fractional started_at is not a session start and cannot clear an outage marker`() {
        val disk = mutableMapOf<String, String>()
        // started_at 90000.5 truncated to 90000 would turn the real outage
        // marker at 90000 into a session-start echo and delete it.
        val session = JSONObject().put("device", "device").put("started_at", 90000.5).put("identity_epoch", 7).toString()
        disk["session_device"] = session
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "90000"
        disk["disconnect_history_device"] = JSONArray().toString()
        val store = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        assertNull(store.openSince("device"))
        // The malformed session row proves nothing: the marker survives.
        assertEquals("90000", disk["audio_outage_device"])
        assertEquals("7", disk["audio_outage_epoch_device"])
        val verdict = judgeAudioOutageMarker(disk["disconnect_history_device"], session, 7L, 90000L, true)
        assertEquals(AudioOutageMarkerVerdict.AMBIGUOUS, verdict)
        assertFalse(planAudioOutageCleanup(disk["disconnect_history_device"], session, 7L, 90000L, true).dropMarker)
    }

    @Test fun `fractional recovery proof start or at is not a stamp`() {
        val disk = mutableMapOf<String, String>()
        disk["audio_recovery_proofs_device"] = JSONArray()
            .put(
                JSONObject()
                    .put("start", 60000.5)
                    .put("at", 91000)
                    .put("identity_epoch", 7),
            )
            .put(
                JSONObject()
                    .put("start", 60000)
                    .put("at", 92000.5)
                    .put("identity_epoch", 7),
            )
            .toString()
        // Neither fractional pair may back a recovery: no stamps survive.
        assertTrue(audioRecoveryStamps(disk["audio_recovery_proofs_device"], 7, 100_000L).isEmpty())
    }

    @Test fun `ambiguous marker within echo tolerance of the overwritten start is cleared`() {
        val disk = mutableMapOf<String, String>()
        val startedAt = 12_000L
        val marker = startedAt - AUDIO_OUTAGE_ECHO_TOLERANCE_MS
        disk["session_device"] = JSONObject().put("device", "device").put("started_at", startedAt)
            .put("identity_epoch", 7).toString()
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = marker.toString()
        disk["disconnect_history_device"] = "[]"
        val store = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        assertEquals(startedAt, sessionStartMatchingMarker(disk["session_device"], 7L, marker))
        assertEquals(
            AudioOutageMarkerVerdict.AMBIGUOUS,
            judgeAudioOutageMarker(disk["disconnect_history_device"], disk["session_device"], 7L, marker, true),
        )
        assertNull(store.openSince("device"))
        assertEquals(marker.toString(), disk["audio_outage_device"])
        store.start("device", 30_000, "build")
        assertNull(store.openSince("device"))
        assertFalse(disk.keys.any { it.startsWith("audio_outage_") })
        assertTrue(disk["session_device"]!!.contains("30000"))
    }

    @Test fun `ambiguous marker far after the overwritten start is kept and not billed`() {
        val disk = mutableMapOf<String, String>()
        val startedAt = 12_000L
        val marker = 90_000L
        disk["session_device"] = JSONObject().put("device", "device").put("started_at", startedAt)
            .put("identity_epoch", 7).toString()
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = marker.toString()
        disk["disconnect_history_device"] = "[]"
        val store = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        assertNull(sessionStartMatchingMarker(disk["session_device"], 7L, marker))
        assertEquals(
            AudioOutageMarkerVerdict.AMBIGUOUS,
            judgeAudioOutageMarker(disk["disconnect_history_device"], disk["session_device"], 7L, marker, true),
        )
        assertNull(store.openSince("device"))
        store.start("device", 200_000, "build")
        assertEquals(marker.toString(), disk["audio_outage_device"])
        assertEquals("7", disk["audio_outage_epoch_device"])
        // openSince is what recordAudioPacket and both diagnostics emitters publish.
        // Ambiguous stays null, so none of them write lost audio for this marker.
        assertNull(store.openSince("device"))
        val session = disk["session_device"]
        assertEquals(
            AudioOutageMarkerVerdict.AMBIGUOUS,
            judgeAudioOutageMarker(disk["disconnect_history_device"], session, 7L, marker, true),
        )
        val plan = planAudioOutageCleanup(disk["disconnect_history_device"], session, 7L, marker, true)
        assertFalse(plan.dropMarker)
        assertNull(plan.rewrittenHistory)
    }

    @Test fun `later row does not bill a historical marker that is not an echo`() {
        val disk = mutableMapOf<String, String>()
        disk["session_device"] = JSONObject().put("device", "device").put("started_at", 30000)
            .put("identity_epoch", 7).toString()
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "1000"
        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 80000))
            .toString()
        val store = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        assertEquals(
            AudioOutageMarkerVerdict.AMBIGUOUS,
            judgeAudioOutageMarker(disk["disconnect_history_device"], disk["session_device"], 7L, 1000L, true),
        )
        assertNull(store.openSince("device"))
        assertEquals("1000", disk["audio_outage_device"])
        assertEquals("7", disk["audio_outage_epoch_device"])
        assertFalse(planAudioOutageCleanup(
            disk["disconnect_history_device"], disk["session_device"], 7L, 1000L, true,
        ).dropMarker)
    }

    @Test fun `orphan marker without a supporting row is not billed and start keeps it`() {
        val disk = mutableMapOf<String, String>()
        disk["session_device"] = JSONObject().put("device", "device").put("started_at", 1000)
            .put("identity_epoch", 7).toString()
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "90000"
        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 1000))
            .toString()
        val store = BatteryHistorySessionStore(
            { disk[it] }, { key, value -> disk[key] = value }, { disk.remove(it) }, { 7L }, { true })
        assertNull(store.openSince("device"))
        assertEquals("90000", disk["audio_outage_device"])
        assertFalse(planAudioOutageCleanup(disk["disconnect_history_device"], disk["session_device"], 7L, 90000L, true).dropMarker)
        store.start("device", 100000, "build")
        assertNull(store.openSince("device"))
        assertEquals("90000", disk["audio_outage_device"])
        assertEquals("7", disk["audio_outage_epoch_device"])
        assertEquals(
            AudioOutageMarkerVerdict.AMBIGUOUS,
            judgeAudioOutageMarker(disk["disconnect_history_device"], disk["session_device"], 7L, 90000L, true),
        )
    }

    @Test fun `disconnect row is sealed only after an unproven marker is gone`() {
        val disk = mutableMapOf<String, String>()
        val operations = mutableListOf<String>()
        val store = BatteryHistorySessionStore(
            { disk[it] },
            { key, value -> operations.add("write:$key"); disk[key] = value },
            { operations.add("remove:$it"); disk.remove(it) },
            { 7L },
            { true },
        )
        store.start("device", 1000, "build")
        disk["audio_outage_epoch_device"] = "7"
        disk["audio_outage_device"] = "1000"
        operations.clear()
        val sealed = store.prepareDisconnect("device", 20000)
        assertEquals(20000L, sealed)
        assertFalse(disk.keys.any { it.startsWith("audio_outage_") })
        disk["disconnect_history_device"] = JSONArray()
            .put(JSONObject().put("eventType", "disconnect").put("timestamp", 20000))
            .toString()
        store.sealDisconnect("device", sealed!!)
        assertEquals(
            listOf(
                "remove:audio_outage_device",
                "remove:audio_outage_epoch_device",
                "write:audio_outage_epoch_device",
                "write:audio_outage_device",
                "remove:session_device",
            ),
            operations,
        )
        assertEquals(20000L, store.openSince("device"))
        assertFalse(disk.containsKey("session_device"))
    }

    @Test fun `consent and identity fence restart records`() {
        val disk = mutableMapOf<String, String>()
        var epoch = 1L
        var enabled = true
        fun store() = BatteryHistorySessionStore({ disk[it] }, { k, v -> disk[k] = v }, { disk.remove(it) }, { epoch }, { enabled })
        store().start("device", 1000, "build")
        epoch++
        assertNull(store().openSince("device"))
        disk.clear()
        enabled = false
        store().start("device", 2000, "build")
        store().end("device", 3000)
        assertTrue(disk.isEmpty())
    }
}
