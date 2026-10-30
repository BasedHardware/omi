package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.ConversationFilter
import com.friend.ios.core.models.DailySummary
import com.friend.ios.core.models.Goal
import com.friend.ios.core.models.Recommendation
import com.friend.ios.network.endpoints.ForYouItem
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset

@OptIn(ExperimentalCoroutinesApi::class)
class ConversationsStoreTest {
    private val zone: ZoneId = ZoneOffset.UTC
    private val now: Instant = Instant.parse("2026-10-08T15:00:00Z")

    @Test
    fun loadGroupsByDayNewestFirst() = runTest {
        val api = HomeFakeAPI()
        api.conversationList = mutableListOf(
            Fixtures.conversation("a", now.minusSeconds(3_600)),
            Fixtures.conversation("b", now.minusSeconds(86_400)),
            Fixtures.conversation("c", now.minusSeconds(600)),
        )
        val store = ConversationsStore(api, backgroundScope, zone)
        store.load()
        assertEquals(ConversationsStore.Phase.Loaded, store.phase)
        assertEquals(listOf(LocalDate.parse("2026-10-08"), LocalDate.parse("2026-10-07")), store.sections.map { it.day })
        assertEquals(listOf("c", "a"), store.sections[0].conversations.map { it.id })
        assertFalse(store.hasMore)
    }

    @Test
    fun failureOnEmptyListShowsFailed() = runTest {
        val api = HomeFakeAPI().apply { failing = true }
        val store = ConversationsStore(api, backgroundScope, zone)
        store.load()
        assertTrue(store.phase is ConversationsStore.Phase.Failed)
    }

    @Test
    fun recapSlotOffersYesterdayWithoutRecap() = runTest {
        val api = HomeFakeAPI()
        api.conversationList = mutableListOf(Fixtures.conversation("y", now.minusSeconds(86_400)))
        api.recapList = mutableListOf(DailySummary("r1", "2026-10-06", "Busy day.", "Overview", null, 3, emptyList(), emptyList()))
        val store = ConversationsStore(api, backgroundScope, zone)
        store.load()
        store.loadRecaps()
        assertEquals(ConversationsStore.RecapSlot.Write(LocalDate.parse("2026-10-07")), store.recapSlot(LocalDate.parse("2026-10-07"), now))
        assertEquals("r1", (store.recapSlot(LocalDate.parse("2026-10-06"), now) as ConversationsStore.RecapSlot.Recap).recap.id)
        assertNull(store.recapSlot(LocalDate.parse("2026-10-08"), now))
        store.createRecap(LocalDate.parse("2026-10-07"))
        assertTrue(store.recapSlot(LocalDate.parse("2026-10-07"), now) is ConversationsStore.RecapSlot.Recap)
    }

    @Test
    fun deleteWithUndoWaitsThenSends() = runTest {
        val api = HomeFakeAPI()
        api.conversationList = mutableListOf(Fixtures.conversation("a", now), Fixtures.conversation("b", now.minusSeconds(60)))
        val store = ConversationsStore(api, backgroundScope, zone, undoWindowMillis = 1_000)
        store.load()
        store.deleteWithUndo(listOf("a"))
        assertEquals(listOf("b"), store.conversations.map { it.id })
        store.undoDelete()
        assertEquals(listOf("a", "b"), store.conversations.map { it.id })
        store.deleteWithUndo(listOf("a"))
        advanceTimeBy(1_500)
        runCurrent()
        assertTrue("delete.a" in api.calls)
        assertNull(store.pendingDeletion)
    }

    @Test
    fun starRollsBackWhenRefused() = runTest {
        val api = HomeFakeAPI()
        api.conversationList = mutableListOf(Fixtures.conversation("a", now))
        val store = ConversationsStore(api, backgroundScope, zone)
        store.load()
        store.setStarred("a", true)
        assertTrue(store.conversations[0].isStarred)
        api.failing = true
        store.setStarred("a", false)
        assertTrue(store.conversations[0].isStarred)
    }

    @Test
    fun starredFilterLoadsFromBackend() = runTest {
        val api = HomeFakeAPI()
        api.conversationList = mutableListOf(Fixtures.conversation("a", now, starred = true), Fixtures.conversation("b", now))
        val store = ConversationsStore(api, backgroundScope, zone)
        store.load()
        store.setFilter(ConversationFilter.Starred)
        assertEquals(listOf("a"), store.visible.map { it.id })
        assertNull(store.recapSlot(LocalDate.parse("2026-10-07"), now))
        store.setFilter(ConversationFilter.All)
        assertEquals(2, store.visible.size)
    }

    @Test
    fun shortConversationsHideBelowThreshold() = runTest {
        val api = HomeFakeAPI()
        api.conversationList = mutableListOf(Fixtures.conversation("short", now, minutes = 1), Fixtures.conversation("long", now, minutes = 20))
        val store = ConversationsStore(api, backgroundScope, zone)
        store.load()
        store.hideShorter(120)
        assertEquals(listOf("long"), store.visible.map { it.id })
        store.hideShorter(null)
        assertEquals(2, store.visible.size)
    }
}

class TasksStoreTest {
    private val zone: ZoneId = ZoneOffset.UTC
    private val now: Instant = Instant.parse("2026-10-08T15:00:00Z")

    @Test
    fun loadHidesCancelledAndMerged() = runTest {
        val api = HomeFakeAPI()
        api.taskList = mutableListOf(
            Fixtures.task("1", "Send the deck"),
            Fixtures.task("2", "Old").copy(status = ActionItem.Status.Cancelled),
            Fixtures.task("3", "Merged").copy(status = ActionItem.Status.Superseded),
        )
        val store = TasksStore(api, zone)
        store.load()
        assertEquals(listOf("1"), store.tasks.map { it.id })
        assertEquals(1, store.openCount)
    }

    @Test
    fun completeIsOptimisticAndRollsBack() = runTest {
        val api = HomeFakeAPI()
        api.taskList = mutableListOf(Fixtures.task("1", "Send the deck"))
        val store = TasksStore(api, zone)
        store.load()
        api.failing = true
        store.complete(listOf("1"))
        assertFalse(store.tasks[0].isCompleted)
        assertTrue(store.lastError != null)
        api.failing = false
        store.complete(listOf("1"))
        assertTrue(store.tasks[0].isCompleted)
        assertEquals(ActionItem.Status.Completed, store.tasks[0].status)
    }

    @Test
    fun notATaskLeavesTheList() = runTest {
        val api = HomeFakeAPI()
        api.taskList = mutableListOf(Fixtures.task("1", "Send the deck"))
        val store = TasksStore(api, zone)
        store.load()
        store.markNotTask(listOf("1"))
        assertTrue(store.tasks.isEmpty())
        assertTrue("status.1.cancelled" in api.calls)
    }

    @Test
    fun snoozeUntilTomorrowMorning() {
        val store = TasksStore(HomeFakeAPI(), zone)
        store.snooze(listOf("1"), now)
        assertEquals(Instant.parse("2026-10-09T00:00:00Z"), store.snoozes["1"])
        store.unsnooze(listOf("1"))
        assertTrue(store.snoozes.isEmpty())
    }

    @Test
    fun bucketsByDueDate() {
        val store = TasksStore(HomeFakeAPI(), zone)
        assertEquals(TasksStore.Bucket.Overdue, store.bucket(Fixtures.task("1", "a b", due = now.minusSeconds(86_400)), now))
        assertEquals(TasksStore.Bucket.Today, store.bucket(Fixtures.task("1", "a b", due = now.plusSeconds(600)), now))
        assertEquals(TasksStore.Bucket.Upcoming, store.bucket(Fixtures.task("1", "a b", due = now.plusSeconds(3 * 86_400)), now))
        assertEquals(TasksStore.Bucket.Someday, store.bucket(Fixtures.task("1", "a b"), now))
        assertEquals(TasksStore.Bucket.WaitingOnOthers, store.bucket(Fixtures.task("1", "a b", owner = ActionItem.Owner.Other), now))
    }

    @Test
    fun tidyUpDueAfterSixOnce() {
        val store = TasksStore(HomeFakeAPI(), zone)
        assertFalse(store.tidyUpIsDue(Instant.parse("2026-10-08T05:00:00Z")))
        assertTrue(store.tidyUpIsDue(now))
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class GoalsAndForYouStoreTest {
    @Test
    fun goalsDeleteWithUndo() = runTest {
        val api = HomeFakeAPI()
        api.goalList = mutableListOf(Goal("g1", "Workouts", 3.0, 4.0), Goal("g2", "Books", 1.0, 10.0))
        val store = GoalsStore(api, backgroundScope, undoWindowMillis = 1_000)
        store.load()
        store.deleteWithUndo("g1")
        assertEquals(listOf("g2"), store.goals.map { it.id })
        store.undoDelete()
        assertEquals(listOf("g1", "g2"), store.goals.map { it.id })
        store.deleteWithUndo("g1")
        advanceTimeBy(1_500)
        runCurrent()
        assertTrue("deleteGoal.g1" in api.calls)
    }

    @Test
    fun goalProgressNeverNegative() = runTest {
        val api = HomeFakeAPI()
        api.goalList = mutableListOf(Goal("g1", "Workouts", 0.0, 4.0))
        val store = GoalsStore(api, backgroundScope)
        store.load()
        store.setProgress("g1", -1.0)
        assertEquals(0.0, store.goals[0].current, 0.0)
        assertEquals(0.75, Goal("x", "t", 3.0, 4.0).progress, 0.0)
    }

    @Test
    fun forYouHidesOffFeedAndStoppedProducers() = runTest {
        val api = HomeFakeAPI()
        val a = ForYouItem("1", "p1", "Tip", "Body", null)
        val b = ForYouItem("2", "p2", "Other", "Body", ForYouItem.Target.Task("t1"))
        api.feed = listOf(a, b)
        val store = ForYouStore(api, scope = backgroundScope)
        store.load()
        assertEquals(2, store.items.size)
        store.send(ForYouItem.Feedback.StopThese, a)
        assertEquals(listOf("2"), store.items.map { it.id })
        store.load()
        assertEquals(listOf("2"), store.items.map { it.id })
        store.send(ForYouItem.Feedback.Helpful, b)
        assertEquals("thumbs_up", store.items[0].feedback)
        api.feed = null
        store.load()
        assertTrue(store.items.isEmpty())
    }
}

class HomeAttentionTest {
    private val zone: ZoneId = ZoneOffset.UTC
    private val now: Instant = Instant.parse("2026-10-08T15:00:00Z")

    @Test
    fun onlyImportantTasksRankedOverdueFirst() {
        val tasks = listOf(
            Fixtures.task("today", "Send Anna the follow-up draft", due = now.plusSeconds(3_600), created = now.minusSeconds(86_400)),
            Fixtures.task("overdue", "Book the physio appointment", due = now.minusSeconds(3 * 86_400), created = now.minusSeconds(5 * 86_400)),
            Fixtures.task("someday", "Think about the garden layout", created = now),
            Fixtures.task("other", "Leo sends the firmware build", due = now),
        )
        val inbox = HomeAttention.inbox(HomeAttention.Input(tasks = tasks, now = now, zone = zone))
        assertEquals(listOf("task.overdue", "task.today"), inbox.needsYou.map { it.id })
        val kickers = inbox.needsYou.map { (it as HomeAttention.Item.Task).card.kicker }
        assertEquals(listOf(TaskConsolidation.Card.Kicker.Overdue, TaskConsolidation.Card.Kicker.DueToday), kickers)
    }

    @Test
    fun overflowAndSnoozedGoToLater() {
        val texts = listOf("Email Anna the budget", "Book the dentist", "Draft the memo", "Order printer paper", "Reply to Leo", "Schedule the review", "Research flights home")
        val tasks = texts.mapIndexed { index, text -> Fixtures.task("${index + 1}", text, due = now.minusSeconds(86_400L * (index + 1))) }
        val inbox = HomeAttention.inbox(
            HomeAttention.Input(tasks = tasks, snoozes = mapOf("1" to now.plusSeconds(3_600)), now = now, zone = zone),
        )
        assertEquals(HomeAttention.needsYouLimit, inbox.needsYou.size)
        assertEquals(2, inbox.later.size)
        assertEquals("task.1", inbox.later.last().id)
    }

    @Test
    fun duplicatesMergeIntoOneCard() {
        val groups = TaskConsolidation.groups(
            listOf(Fixtures.task("1", "Send the roadmap deck to the team"), Fixtures.task("2", "Send roadmap deck to team")),
        )
        assertEquals(1, groups.size)
        assertEquals(listOf("1", "2"), groups[0].ids)
    }

    @Test
    fun recommendationWithoutTaskIsOwnCard() {
        val recommendation = Recommendation("r1", "Follow up", "", "send:Send Anna the notes.", taskID = null)
        val inbox = HomeAttention.inbox(HomeAttention.Input(recommendations = listOf(recommendation), now = now, zone = zone))
        assertEquals(listOf("recommendation.r1"), inbox.needsYou.map { it.id })
        assertEquals("Send Anna the notes?", recommendation.question)
        assertEquals(HomeTapTargets.Target.Ask("send:Send Anna the notes."), HomeTapTargets.target(inbox.needsYou[0]))
    }

    @Test
    fun takeOverOnlyForDigitalOwnTasks() {
        assertTrue(TakeOverEligibility.canTakeOver(Fixtures.task("1", "Book the physio follow-up for the knee")))
        assertFalse(TakeOverEligibility.canTakeOver(Fixtures.task("1", "Go climbing at the gym")))
        assertFalse(TakeOverEligibility.canTakeOver(Fixtures.task("1", "Leo unblocks the firmware release")))
        assertTrue(TaskConsolidation.isRequestToSomeoneElse("Send me the deck", "could you send me the deck"))
        assertTrue(TaskConsolidation.isFragment("um yeah"))
    }
}
