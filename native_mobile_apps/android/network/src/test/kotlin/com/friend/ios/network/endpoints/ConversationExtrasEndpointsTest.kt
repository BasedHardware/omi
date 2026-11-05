package com.friend.ios.network.endpoints

import com.friend.ios.core.AppConfiguration
import com.friend.ios.core.models.ConversationAudio
import com.friend.ios.core.models.SpeakerTarget
import com.friend.ios.core.models.TaskLayout
import com.friend.ios.network.HttpCore
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.URI
import java.time.Instant

class ConversationExtrasEndpointsTest {
    private lateinit var server: MockWebServer
    private lateinit var http: HttpCore

    /** The smallest conversation the generated DTO decodes. */
    private val conversationJSON =
        """{"id":"c1","created_at":"2026-10-08T10:00:00Z","started_at":"2026-10-08T10:00:00Z","finished_at":"2026-10-08T10:30:00Z",""" +
            """"structured":{"title":"Standup","overview":"We met."},"transcript_segments":[],""" +
            """"calendar_event":{"event_id":"e1","title":"Standup","start_time":"2026-10-08T10:00:00Z","end_time":"2026-10-08T10:30:00Z","attendees":["anna@x.com"]},""" +
            """"capture_group":{"id":"g","primary_id":"c1","members":[{"id":"c1","source":"omi"},{"id":"c2","source":"phone","started_at":"2026-10-08T09:59:00Z"}]}}"""

    @Before
    fun setUp() {
        server = MockWebServer().apply { start() }
        val configuration = AppConfiguration(AppConfiguration.Profile.LocalDev, URI(server.url("/").toString()), null, "1.0", "1")
        http = HttpCore(configuration, { "token" })
    }

    @After
    fun tearDown() = server.shutdown()

    private fun body(): JsonObject = Json.parseToJsonElement(server.takeRequest().body.readUtf8()).jsonObject

    @Test
    fun audioMapperPrefersTheDenseFileThenPartsThenPending() {
        assertEquals(
            ConversationAudio.Ready("https://a/full.mp3", 30.0),
            ConversationAudioMapper.map(JsonAccessTest.obj("""{"conversation_audio":{"status":"cached","signed_url":"https://a/full.mp3","duration":30.0}}""")),
        )
        val parts = ConversationAudioMapper.map(
            JsonAccessTest.obj("""{"audio_files":[{"id":"a","status":"cached","signed_url":"https://a/1.wav","duration":5},{"id":"b","status":"cached","signed_url":"https://a/2.wav","duration":6}]}"""),
        )
        assertEquals(2, (parts as ConversationAudio.Parts).parts.size)
        assertEquals(
            ConversationAudio.Pending(1.5),
            ConversationAudioMapper.map(JsonAccessTest.obj("""{"poll_after_ms":1500,"audio_files":[{"id":"a","status":"pending"}]}""")),
        )
        assertEquals(ConversationAudio.Unavailable, ConversationAudioMapper.map(JsonAccessTest.obj("""{"audio_files":[]}""")))
    }

    @Test
    fun detailCarriesCalendarEventAndRecordings() = runTest {
        server.enqueue(MockResponse().setBody(conversationJSON))
        val detail = ConversationsEndpoints(http).conversationDetail("c1")
        assertEquals("e1", detail.calendarEvent!!.eventID)
        // Both recordings, the earlier phone one first; this one is current.
        assertEquals(listOf("c2", "c1"), detail.recordings.map { it.id })
        assertTrue(detail.recordings.last().isCurrent)
    }

    @Test
    fun screenshotsBannerFirstThenStripByRank() {
        val shots = ScreenshotMapper.map(
            JsonAccessTest.obj("""{"banner":{"id":"b","caption":"Banner"},"strip":[{"id":"s2","rank":2},{"id":"s1","rank":1,"thumbnail_url":"https://t"}]}"""),
        )
        assertEquals(listOf("b", "s1", "s2"), shots.map { it.id })
        assertEquals("https://t", shots[1].thumbnailURL)
    }

    @Test
    fun feedbackNeedsAPersistedReceipt() = runTest {
        server.enqueue(MockResponse().setBody("""{"schema_version":"mobile_feedback_receipt.v1","persisted":true,"feedback_id":"f1"}"""))
        assertTrue(ConversationExtrasEndpoints(http).sendConversationFeedback("c1", com.friend.ios.core.models.ConversationFeedbackKind.Summary, false, com.friend.ios.core.models.SummaryFeedbackReason.Incomplete, "f1"))
        val json = body()
        assertEquals("-1", json["value"]!!.jsonPrimitive.content)
        assertEquals("summary_incomplete", json["reason"]!!.jsonPrimitive.content)
    }

    @Test
    fun calendarCandidatesSkipIncompleteEvents() = runTest {
        server.enqueue(
            MockResponse().setBody("""[{"event_id":"e1","title":"A","start_time":"2026-10-08T10:00:00Z","end_time":"2026-10-08T11:00:00Z"},{"event_id":"e2"}]"""),
        )
        val events = ConversationExtrasEndpoints(http).calendarEvents(Instant.parse("2026-10-08T08:00:00Z"), Instant.parse("2026-10-08T12:00:00Z"))
        assertEquals(listOf("e1"), events.map { it.id })
        val request = server.takeRequest()
        assertEquals("2026-10-08T08:00:00Z", request.requestUrl!!.queryParameter("time_min"))
    }

    @Test
    fun searchSendsTheFilter() = runTest {
        server.enqueue(MockResponse().setBody("""{"items":[$conversationJSON]}"""))
        val found = SearchEndpoints(http).searchConversations("", 1, 30, ConversationSearchFilter(start = Instant.parse("2026-10-01T00:00:00Z"), speakerID = "p1"))
        assertEquals(listOf("c1"), found.map { it.id })
        val json = body()
        assertEquals("p1", json["speaker_id"]!!.jsonPrimitive.content)
        assertEquals("2026-10-01T00:00:00Z", json["start_date"]!!.jsonPrimitive.content)
        assertNull(json["end_date"])
    }

    @Test
    fun assignSpeakerUsesTheVoiceRouteWithASpeaker() = runTest {
        server.enqueue(MockResponse().setBody(conversationJSON))
        TranscriptLabelsEndpoints(http).assignSpeaker("c1", listOf("s1", "s2"), 1, SpeakerTarget.Person("p1"))
        val request = server.takeRequest()
        assertEquals("/v1/conversations/c1/assign-speaker/1?assign_type=person_id&value=p1", request.path)
        server.enqueue(MockResponse().setBody(conversationJSON))
        TranscriptLabelsEndpoints(http).assignSpeaker("c1", listOf("s1"), null, SpeakerTarget.User)
        assertEquals("/v1/conversations/c1/segments/assign-bulk", server.takeRequest().path)
    }

    @Test
    fun taskLayoutSendsOnlyChangedFields() = runTest {
        server.enqueue(MockResponse().setBody("{}"))
        TaskExtrasEndpoints(http).setTaskLayout(listOf(TaskLayout("a", sortOrder = 1000), TaskLayout("b", indentLevel = 1)))
        val items = body()["items"]!!.jsonArray.map { it.jsonObject }
        assertEquals(setOf("id", "sort_order"), items[0].keys)
        assertEquals(setOf("id", "indent_level"), items[1].keys)
    }
}

/** `JsonAccess.obj` for tests. */
private object JsonAccessTest {
    fun obj(text: String): JsonObject = JsonAccess.obj(text)
}
