package com.friend.ios.network.endpoints

import com.friend.ios.core.AppConfiguration
import com.friend.ios.core.models.Recommendation
import com.friend.ios.core.models.Workstream
import com.friend.ios.core.models.WorkstreamRef
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
import org.junit.Before
import org.junit.Test
import java.net.URI

class AgentEndpointsTest {
    private lateinit var server: MockWebServer
    private lateinit var agent: AgentAPI

    @Before
    fun setUp() {
        server = MockWebServer().apply { start() }
        val configuration = AppConfiguration(AppConfiguration.Profile.LocalDev, URI(server.url("/").toString()), null, "1.0", "1")
        agent = AgentEndpoints(HttpCore(configuration, { "token" }))
    }

    @After
    fun tearDown() = server.shutdown()

    private fun body(): JsonObject = Json.parseToJsonElement(server.takeRequest().body.readUtf8()).jsonObject

    @Test
    fun startWorkIsIdempotentPerTaskAndCarriesTheGeneration() = runTest {
        server.enqueue(
            MockResponse().setBody(
                """{"created_at":"2026-10-08T10:00:00Z","newly_created":true,"receipt_id":"r","task_id":"t1","workstream_id":"ws9"}""",
            ),
        )
        assertEquals("ws9", agent.startWork("t1", "Draft the memo", 3))
        val request = server.takeRequest()
        assertEquals("/v1/work-intents", request.path)
        assertEquals("work-intent:task:t1", request.getHeader("Idempotency-Key"))
        assertEquals("3", request.getHeader("X-Account-Generation"))
        val json = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
        assertEquals("task", json["origin"]!!.jsonPrimitive.content)
        assertEquals("t1", json["task_id"]!!.jsonPrimitive.content)
    }

    @Test
    fun eventsCarryEvidenceAndAreCappedAt2000() = runTest {
        server.enqueue(
            MockResponse().setBody(
                """{"created_at":"2026-10-08T10:00:00Z","event_id":"e1","kind":"agent_update","sensitivity":"normal","sequence":1,"summary":"x","workstream_id":"ws"}""",
            ),
        )
        val id = agent.recordWorkstreamEvent(
            WorkstreamRef("ws", 2), "agent_update", "a".repeat(2500),
            listOf(mapOf("kind" to "external", "id" to "chat_session:s1", "scope" to "canonical")), "run:r:start",
        )
        assertEquals("e1", id)
        val json = body()
        assertEquals(2000, json["summary"]!!.jsonPrimitive.content.length)
        assertEquals("chat_session:s1", json["evidence_refs"]!!.jsonArray[0].jsonObject["id"]!!.jsonPrimitive.content)
    }

    @Test
    fun alreadyHandledIsADismissWithAReason() {
        val recommendation = Recommendation("i1", "Send", "", "", taskID = "t1", feedbackSubjectKind = "task", feedbackSubjectID = "t1")
        val body = RecommendationMapper.feedbackBody(recommendation, Recommendation.Decision.AlreadyHandled)
        assertEquals("dismiss", body["action"]!!.jsonPrimitive.content)
        assertEquals("already_handled", body["reason"]!!.jsonPrimitive.content)
        assertEquals("i1", body["intervention_id"]!!.jsonPrimitive.content)
        assertEquals("do_now", RecommendationMapper.feedbackBody(recommendation, Recommendation.Decision.DoNow)["action"]!!.jsonPrimitive.content)
    }

    @Test
    fun updateWorkstreamSendsOnlyWhatChanged() = runTest {
        server.enqueue(MockResponse().setBody("{}"))
        agent.updateWorkstream(WorkstreamRef("ws", 1), Workstream.Status.Completed, null)
        val request = server.takeRequest()
        assertEquals("PATCH", request.method)
        assertEquals("""{"status":"completed"}""", request.body.readUtf8())
    }
}
