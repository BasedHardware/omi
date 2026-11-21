package com.friend.ios.service.stores

import com.friend.ios.network.APIClientProtocol
import com.friend.ios.network.APIError
import com.friend.ios.network.endpoints.TaskAppLevel
import com.friend.ios.network.endpoints.TaskAppOption
import com.friend.ios.persistence.Preferences
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Port of `TaskAppSettingsTests` (`AppCatalogAndChatAppsTests.swift`). */
class TaskAppSettingsStoreTest {
    private val api = FakeTaskAppsAPI()

    @Test
    fun choosingAParentClearsTheLevelsBelowAndIsRemembered() = runTest {
        val prefs = Preferences(FakePrefs())
        api.options = mapOf(
            TaskAppLevel.ClickupTeam to mapOf("" to listOf(TaskAppOption("t1", "Team"))),
            TaskAppLevel.ClickupSpace to mapOf("t1" to listOf(TaskAppOption("s1", "Space"))),
            TaskAppLevel.ClickupList to mapOf("s1" to listOf(TaskAppOption("l1", "Inbox"))),
        )
        val store = TaskAppSettingsStore(api, prefs)
        store.load("clickup")
        assertEquals(listOf("t1"), store.options[TaskAppLevel.ClickupTeam]?.map { it.id })
        store.select("clickup", TaskAppLevel.ClickupTeam, TaskAppOption("t1", "Team"))
        assertEquals(listOf("s1"), store.options[TaskAppLevel.ClickupSpace]?.map { it.id })
        assertEquals("select:clickup:clickupList=nil,clickupSpace=nil,clickupTeam=t1", api.log.last())
        store.select("clickup", TaskAppLevel.ClickupSpace, TaskAppOption("s1", "Space"))
        store.select("clickup", TaskAppLevel.ClickupList, TaskAppOption("l1", "Inbox"))
        val again = TaskAppSettingsStore(api, prefs)
        assertEquals("Inbox", again.selection["clickup"]?.get(TaskAppLevel.ClickupList)?.name)
        again.load("clickup")
        assertEquals(listOf("l1"), again.options[TaskAppLevel.ClickupList]?.map { it.id })
    }

    @Test
    fun aRefusedChoiceGoesBack() = runTest {
        val store = TaskAppSettingsStore(api, Preferences(FakePrefs()))
        api.nextWriteError = APIError.Http(500, "")
        store.select("asana", TaskAppLevel.AsanaWorkspace, TaskAppOption("w", "Work"))
        assertNull(store.selection["asana"]?.get(TaskAppLevel.AsanaWorkspace))
        assertTrue(store.failed)
        store.makeDefault("asana")
        assertEquals("asana", store.defaultApp)
    }

    @Test
    fun forgettingAnAppDropsItsPlaceAndDefault() = runTest {
        val prefs = Preferences(FakePrefs())
        val store = TaskAppSettingsStore(api, prefs)
        store.makeDefault("asana")
        store.select("asana", TaskAppLevel.AsanaWorkspace, TaskAppOption("w", "Work"))
        store.forget("asana")
        assertNull(store.defaultApp)
        assertTrue(TaskAppSettingsStore(api, prefs).selection.isEmpty())
    }
}

/** `FakeAPIClient.devApps`: the task app places by level and parent id, with a log of the writes. */
private class FakeTaskAppsAPI(
    private val base: APIClientProtocol = HomeFakeAPI.unimplemented(),
) : APIClientProtocol by base {
    var options: Map<TaskAppLevel, Map<String, List<TaskAppOption>>> = emptyMap()
    var nextWriteError: Exception? = null
    var default: String? = null
    val log = mutableListOf<String>()

    private fun write() {
        nextWriteError?.let {
            nextWriteError = null
            throw it
        }
    }

    override suspend fun taskAppOptions(level: TaskAppLevel, parent: String?): List<TaskAppOption> = options[level]?.get(parent ?: "").orEmpty()

    override suspend fun saveTaskAppSelection(app: String, selection: Map<TaskAppLevel, TaskAppOption?>) {
        write()
        log += "select:$app:" + selection.entries.sortedBy { it.key.rawValue }.joinToString(",") { "${it.key.rawValue}=${it.value?.id ?: "nil"}" }
    }

    override suspend fun defaultTaskApp(): String? = default

    override suspend fun setDefaultTaskApp(app: String) {
        write()
        default = app
    }
}
