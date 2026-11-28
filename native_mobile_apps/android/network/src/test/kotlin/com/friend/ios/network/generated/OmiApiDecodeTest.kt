package com.friend.ios.network.generated

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OmiApiDecodeTest {

    @Test
    fun decodesMemoryDbWithMicrosecondDatesUnknownEnumAndExtraKeys() {
        val json = """
            {
              "id": "mem_01J9ZK4Q",
              "uid": "user_abc",
              "content": "Prefers oat milk in coffee",
              "category": "brand_new_category_from_backend",
              "subject_attribution": "third_party",
              "memory_tier": "core",
              "created_at": "2026-10-07T18:22:31.123456+00:00",
              "updated_at": "2026-10-08T09:01:02.654321Z",
              "invalid_at": null,
              "visibility": "private",
              "edited": false,
              "is_locked": true,
              "curation_weight": 3,
              "capture_confidence": 0.92,
              "arguments": {"beverage": "coffee", "milk": {"kind": "oat"}},
              "evidence": [],
              "tags": ["food"],
              "some_future_field": {"nested": [1, 2, 3]},
              "another_unknown": 42
            }
        """.trimIndent()

        val dto = OmiJson.decodeFromString(OmiAPI.MemoryDB.serializer(), json)

        assertEquals("mem_01J9ZK4Q", dto.id)
        assertEquals("Prefers oat milk in coffee", dto.content)
        assertEquals(OmiAPI.MemoryCategory._unknown, dto.category)
        assertEquals("__unknown__", dto.category?.rawValue)
        assertEquals(OmiAPI.SubjectAttribution.third_party, dto.subjectAttribution)
        assertEquals("2026-10-07T18:22:31.123456+00:00", dto.createdAt)
        assertNull(dto.invalidAt)
        assertEquals(true, dto.isLocked)
        assertEquals(3, dto.curationWeight)
        assertEquals("oat", dto.arguments?.get("milk")?.jsonObject?.get("kind")?.jsonPrimitive?.content)
        assertEquals(OmiAPI.MemoryCategory.interesting, omiRawEnumOf<OmiAPI.MemoryCategory>("interesting"))
    }

    @Test
    fun decodesConversationLikeObject() {
        val json = """
            {
              "id": "conv_123",
              "created_at": "2026-10-08T07:15:00.000001+00:00",
              "started_at": "2026-10-08T07:00:00.5+00:00",
              "finished_at": null,
              "source": "omi",
              "status": "completed",
              "discarded": false,
              "language": "en",
              "structured": {
                "title": "Coffee with Ana",
                "overview": "Talked about the trip.",
                "emoji": "x",
                "category": "a_category_we_do_not_know",
                "action_items": [{"description": "Book flights", "completed": false, "unknown_key": 1}],
                "events": [{"title": "Flight", "start": "2026-11-01T10:00:00Z", "duration": 120}],
                "short_summary": "Trip planned, flights to book."
              },
              "transcript_segments": [
                {"text": "hi", "speaker": "SPEAKER_00", "speaker_id": 0, "is_user": true, "start": 0.0, "end": 1.25}
              ],
              "geolocation": null,
              "apps_results": [],
              "brand_new_top_level": true
            }
        """.trimIndent()

        val dto = OmiJson.decodeFromString(OmiAPI.Conversation.serializer(), json)

        assertEquals("conv_123", dto.id)
        assertEquals(OmiAPI.ConversationSource.omi, dto.source)
        assertEquals(OmiAPI.ConversationStatus.completed, dto.status)
        assertEquals("Coffee with Ana", dto.structured.title)
        assertEquals(OmiAPI.CategoryEnum._unknown, dto.structured.category)
        assertEquals("Book flights", dto.structured.actionItems?.single()?.description_)
        assertEquals(120, dto.structured.events?.single()?.duration)
        // From docs/backend-patches/short-summary.openapi.json (omi-native).
        assertEquals("Trip planned, flights to book.", dto.structured.shortSummary)
        assertEquals(1.25, dto.transcriptSegments?.single()?.end ?: 0.0, 0.0)
        assertNull(dto.geolocation)
    }

    @Test
    fun patchFieldIsTriState() {
        val patch = OmiAPI.ActionItemUpdateRequest(
            completed = OmiAPI.OmiPatchField.Value(true),
            dueAt = OmiAPI.OmiPatchField.Null,
        )
        val encoded = OmiJson.encodeToJsonElement(OmiAPI.ActionItemUpdateRequest.serializer(), patch).jsonObject
        assertEquals(setOf("completed", "due_at"), encoded.keys)
        assertEquals(JsonPrimitive(true), encoded["completed"])
        assertEquals("null", encoded["due_at"].toString())

        val decoded = OmiJson.decodeFromString(
            OmiAPI.ActionItemUpdateRequest.serializer(),
            """{"due_at": null, "priority": "high", "unknown": 1}""",
        )
        assertEquals(OmiAPI.OmiPatchField.Null, decoded.dueAt)
        assertEquals(OmiAPI.OmiPatchField.Value(OmiAPI.TaskPriority.high), decoded.priority)
        assertEquals(OmiAPI.OmiPatchField.Omitted, decoded.completed)
    }

    @Test
    fun candidateRecordTaskChangeFollowsProposedAction() {
        fun record(action: String, kind: String, taskChange: String) = """
            {
              "candidate_id": "c1", "account_generation": 0, "capture_confidence": 0.5,
              "ownership_confidence": 0.5, "created_at": "2026-10-08T00:00:00.000000Z",
              "evidence_refs": [{"id": "e1", "kind": "conversation", "scope": "canonical"}],
              "idempotency_key": "k", "source_surface": "chat",
              "proposed_action": "$action", "subject_kind": "$kind",
              "task_change": $taskChange
            }
        """.trimIndent()

        val create = OmiJson.decodeFromString(
            OmiAPI.CandidateRecord.serializer(),
            record("create", "task", """{"description": "Call mom"}"""),
        )
        assertEquals("Call mom", (create.taskChange as OmiAPI.CandidateTaskChange.Create).value.description_)

        // A payload that would also satisfy TaskCreatePayload still decodes as a
        // change when the action is update, like the Swift init(from:).
        val update = OmiJson.decodeFromString(
            OmiAPI.CandidateRecord.serializer(),
            record("update", "task", """{"description": "Call dad"}"""),
        )
        assertTrue(update.taskChange is OmiAPI.CandidateTaskChange.Change)

        val workstream = OmiJson.decodeFromString(
            OmiAPI.CandidateRecord.serializer(),
            record("create", "workstream", """{"description": "x"}"""),
        )
        assertNull(workstream.taskChange)

        val roundTrip = OmiJson.encodeToJsonElement(OmiAPI.CandidateRecord.serializer(), create).jsonObject
        assertEquals("Call mom", (roundTrip["task_change"] as JsonObject)["description"]?.jsonPrimitive?.content)
        assertFalse(roundTrip.containsKey("task_id"))
    }

    @Test
    fun candidateCreateDispatchesOnDiscriminators() {
        val json = """
            {
              "subject_kind": "task", "proposed_action": "create",
              "capture_confidence": 0.9, "ownership_confidence": 0.8, "source_surface": "chat",
              "evidence_refs": [{"id": "e1", "kind": "brand_new_kind", "scope": "canonical"}],
              "task_change": {"description": "Water plants"}
            }
        """.trimIndent()
        val dto = OmiJson.decodeFromString(OmiAPI.CandidateCreate.serializer(), json)
        val arm = dto as OmiAPI.CandidateCreate.TaskCreate
        assertEquals("Water plants", arm.value.taskChange.description_)
        assertEquals(OmiAPI.EvidenceKind._unknown, arm.value.evidenceRefs.single().kind)
    }
}
