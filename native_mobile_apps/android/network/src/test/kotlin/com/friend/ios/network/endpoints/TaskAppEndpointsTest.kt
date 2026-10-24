package com.friend.ios.network.endpoints

import com.friend.ios.core.AppConfiguration
import com.friend.ios.network.APIError
import com.friend.ios.network.HttpCore
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
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

/** `APIClient+TaskAppSettings.swift` and the recap delete of `APIClient+ConversationContent.swift`. */
class TaskAppEndpointsTest {
    private lateinit var server: MockWebServer
    private lateinit var http: HttpCore

    @Before
    fun setUp() {
        server = MockWebServer().apply { start() }
        val configuration = AppConfiguration(AppConfiguration.Profile.LocalDev, URI(server.url("/").toString()), null, "1.0", "1")
        http = HttpCore(configuration, { "token" })
    }

    @After
    fun tearDown() = server.shutdown()

    @Test
    fun optionsListUnderTheParentAndSkipRowsWithoutAnID() = runTest {
        val tasks = TasksEndpoints(http)
        server.enqueue(MockResponse().setBody("""{"projects":[{"gid":"p1","name":"Launch"},{"name":"no id"},{"gid":"p2"}]}"""))
        val options = tasks.taskAppOptions(TaskAppLevel.AsanaProject, "w1")
        assertEquals(listOf(TaskAppOption("p1", "Launch"), TaskAppOption("p2", "p2")), options)
        assertEquals("/v1/task-integrations/asana/projects/w1", server.takeRequest().path)
        // A level below an unpicked parent asks nothing.
        assertTrue(tasks.taskAppOptions(TaskAppLevel.ClickupList, null).isEmpty())
        assertEquals(0, server.requestCount - 1)
    }

    @Test
    fun aSelectionMergesAndClearsTheLevelsBelow() = runTest {
        server.enqueue(MockResponse().setBody("{}"))
        TasksEndpoints(http).saveTaskAppSelection(
            "clickup",
            mapOf(TaskAppLevel.ClickupTeam to TaskAppOption("t1", "Team"), TaskAppLevel.ClickupSpace to null),
        )
        val request = server.takeRequest()
        assertEquals("PUT", request.method)
        assertEquals("/v1/task-integrations/clickup", request.path)
        val json = Json.parseToJsonElement(request.body.readUtf8()).jsonObject
        assertEquals("true", json["connected"]!!.jsonPrimitive.content)
        assertEquals("t1", json["team_id"]!!.jsonPrimitive.content)
        assertEquals("Team", json["team_name"]!!.jsonPrimitive.content)
        assertEquals(JsonNull, json["space_id"])
        assertEquals(JsonNull, json["space_name"])
    }

    @Test
    fun theDefaultAppReadsEmptyAsNone() = runTest {
        val tasks = TasksEndpoints(http)
        server.enqueue(MockResponse().setBody("""{"default_app":""}"""))
        assertNull(tasks.defaultTaskApp())
        server.enqueue(MockResponse().setBody("""{"default_app":"asana"}"""))
        assertEquals("asana", tasks.defaultTaskApp())
        server.enqueue(MockResponse().setBody("{}"))
        tasks.setDefaultTaskApp("todoist")
        server.takeRequest()
        server.takeRequest()
        val request = server.takeRequest()
        assertEquals("/v1/task-integrations/default", request.path)
        assertEquals("todoist", Json.parseToJsonElement(request.body.readUtf8()).jsonObject["app_key"]!!.jsonPrimitive.content)
    }

    @Test
    fun aRecapAlreadyGoneCountsAsDeleted() = runTest {
        val conversations = ConversationsEndpoints(http)
        server.enqueue(MockResponse().setResponseCode(404).setBody("{}"))
        conversations.deleteDailySummary("r1")
        assertEquals("/v1/users/daily-summaries/r1", server.takeRequest().path)
        server.enqueue(MockResponse().setResponseCode(500).setBody("{}"))
        val error = runCatching { conversations.deleteDailySummary("r2") }.exceptionOrNull()
        assertTrue(error is APIError.Http && error.status == 500)
    }
}
