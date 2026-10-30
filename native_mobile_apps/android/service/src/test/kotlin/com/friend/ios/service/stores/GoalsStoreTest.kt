package com.friend.ios.service.stores

import com.friend.ios.core.models.Goal
import com.friend.ios.network.APIClientProtocol
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Port of `GoalsStoreTests` (`GoalsAndRemindersTests.swift`); Reminders is iOS only. */
@OptIn(ExperimentalCoroutinesApi::class)
class GoalsStoreTest {
    @Test
    fun createsEditsAndTracksProgress() = runTest {
        val api = FakeGoalsAPI()
        val store = GoalsStore(api, backgroundScope)
        store.load()
        assertTrue(store.goals.isEmpty())

        assertTrue(store.create("  Run 5k  ", 1.0, 5.0))
        assertFalse(store.create("  ", 0.0, 1.0))
        val id = store.goals[0].id
        assertEquals("Run 5k", store.goals[0].title)
        assertEquals(0.2, store.goals[0].progress, 1e-9)

        assertTrue(store.update(id, "Run 10k", 2.0, 10.0))
        assertTrue(store.setProgress(id, 12.0))
        assertEquals(1.0, store.goals[0].progress, 0.0)
        assertEquals(listOf("list:all", "create:Run 5k", "update:g1=Run 10k", "progress:g1=12.0"), api.log)
    }

    @Test
    fun allowsFourGoals() = runTest {
        val store = GoalsStore(FakeGoalsAPI(), backgroundScope)
        for (index in 1..4) assertTrue(store.create("Goal $index", 0.0, 1.0))
        assertFalse(store.canAdd)
        assertFalse(store.create("Fifth", 0.0, 1.0))
    }

    @Test
    fun rollsBackAFailedEdit() = runTest {
        val api = FakeGoalsAPI().apply { goals += Goal("g1", "Read", 3.0, 12.0) }
        val store = GoalsStore(api, backgroundScope)
        store.load()
        api.failing += "progress"
        assertFalse(store.setProgress("g1", 4.0))
        assertEquals(3.0, store.goals[0].current, 0.0)
        assertNotNull(store.lastError)
    }

    @Test
    fun deleteHasUndo() = runTest {
        val api = FakeGoalsAPI().apply { goals += listOf(Goal("g1", "Read", 3.0, 12.0), Goal("g2", "Save", 1.0, 2.0)) }
        val store = GoalsStore(api, backgroundScope, undoWindowMillis = 60_000)
        store.load()
        store.deleteWithUndo("g1")
        assertEquals(listOf("g2"), store.goals.map { it.id })
        store.undoDelete()
        assertEquals(listOf("g1", "g2"), store.goals.map { it.id })

        store.deleteWithUndo("g2")
        store.commitDeletion()
        assertEquals("delete:g2", api.log.last())
        assertEquals(listOf("g1"), api.goals.map { it.id })
    }
}

/** `FakeAPIClient.goalsBackend`: goals in memory, with a log and per-call failures. */
private class FakeGoalsAPI(
    private val base: APIClientProtocol = HomeFakeAPI.unimplemented(),
) : APIClientProtocol by base {
    val goals = mutableListOf<Goal>()
    val log = mutableListOf<String>()
    val failing = mutableSetOf<String>()

    private fun check(kind: String, entry: String) {
        if (kind in failing) throw IllegalStateException("offline")
        log += entry
    }

    override suspend fun goals(): List<Goal> {
        check("list", "list:all")
        return goals.toList()
    }

    override suspend fun createGoal(title: String, current: Double, target: Double): Goal {
        check("create", "create:$title")
        return Goal("g${goals.size + 1}", title, current, target).also { goals += it }
    }

    override suspend fun updateGoal(id: String, title: String, current: Double, target: Double): Goal {
        check("update", "update:$id=$title")
        return replace(id) { it.copy(title = title, current = current, target = target) }
    }

    override suspend fun setGoalProgress(id: String, current: Double): Goal {
        check("progress", "progress:$id=$current")
        return replace(id) { it.copy(current = current) }
    }

    override suspend fun deleteGoal(id: String) {
        check("delete", "delete:$id")
        goals.removeAll { it.id == id }
    }

    private fun replace(id: String, change: (Goal) -> Goal): Goal {
        val index = goals.indexOfFirst { it.id == id }
        return change(goals[index]).also { goals[index] = it }
    }
}
