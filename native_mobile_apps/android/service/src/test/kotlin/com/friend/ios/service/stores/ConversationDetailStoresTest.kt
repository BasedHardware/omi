package com.friend.ios.service.stores

import com.friend.ios.core.models.CalendarEventLink
import com.friend.ios.core.models.ConversationAudio
import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.core.models.DailySummary
import com.friend.ios.core.models.OmiApp
import com.friend.ios.core.models.Person
import com.friend.ios.core.models.SpeakerTarget
import com.friend.ios.core.models.SummaryTemplateDraft
import com.friend.ios.core.models.VoiceMatch
import com.friend.ios.persistence.Preferences
import com.friend.ios.service.InMemorySharedPreferences
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
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
import java.time.ZoneOffset

@OptIn(ExperimentalCoroutinesApi::class)
class ConversationDetailStoreTest {
    private val now = Instant.parse("2026-10-08T15:00:00Z")
    private val conversation = Fixtures.conversation("c1", now)

    private fun detail(hasAudio: Boolean = false) = ConversationDetail(
        conversation = conversation,
        summaryActionItems = listOf("Send the deck"),
        transcript = listOf(
            ConversationDetail.Line(0, "You", true, "Hello there", 0.0, segmentID = "s0"),
            ConversationDetail.Line(1, "Speaker 2", false, "Hi", 3.0, segmentID = "s1", speakerID = 1),
            ConversationDetail.Line(2, "Speaker 2", false, "How are you", 5.0, segmentID = "s2", speakerID = 1),
        ),
        summary = "The summary.",
        keyPoints = listOf("Point one"),
        hasAudio = hasAudio,
    )

    @Test
    fun loadsAndBuildsSummaryText() = runTest {
        val api = fakeAPI { "conversationDetail" returns detail() }
        val store = ConversationDetailStore(conversation, api.client)
        store.load()
        assertEquals(ConversationDetailStore.Phase.Loaded, store.phase)
        assertEquals("The summary.\n\n- Point one", store.summaryText)
    }

    @Test
    fun editLineRollsBackWhenRefused() = runTest {
        val api = fakeAPI {
            "conversationDetail" returns detail()
            "editTranscriptSegment" throws IllegalStateException("no")
        }
        val store = ConversationDetailStore(conversation, api.client)
        store.load()
        assertFalse(store.editLine(1, "Hey"))
        assertEquals("Hi", store.detail!!.transcript[1].text)
        // Unchanged words are not sent.
        assertFalse(store.editLine(0, "Hello there"))
        assertEquals(1, api.called("editTranscriptSegment").size)
    }

    @Test
    fun loadAudioPollsUntilReady() = runTest {
        var polls = 0
        val api = fakeAPI {
            "conversationDetail" returns detail(hasAudio = true)
            "precacheConversationAudio" returns Unit
            "conversationAudio" does { if (++polls < 2) ConversationAudio.Pending(0.0) else ConversationAudio.Ready("https://a/x.mp3", 12.0) }
        }
        val store = ConversationDetailStore(conversation, api.client)
        store.load()
        store.loadAudio()
        assertEquals(ConversationDetailStore.AudioState.Ready("https://a/x.mp3", 12.0), store.audio)
        assertEquals(2, polls)
    }

    @Test
    fun noAudioWithoutRecording() = runTest {
        val api = fakeAPI { "conversationDetail" returns detail(hasAudio = false) }
        val store = ConversationDetailStore(conversation, api.client)
        store.load()
        store.loadAudio()
        assertEquals(ConversationDetailStore.AudioState.Idle, store.audio)
    }

    @Test
    fun unlinkCalendarEventComesBackWhenRefused() = runTest {
        val link = CalendarEventLink("e1", "Standup", emptyList(), emptyList(), now, now.plusSeconds(1800), null)
        val api = fakeAPI {
            "conversationDetail" returns detail().copy(calendarEvent = link)
            "unlinkCalendarEvent" throws IllegalStateException("no")
        }
        val store = ConversationDetailStore(conversation, api.client)
        store.load()
        assertFalse(store.unlinkCalendarEvent())
        assertEquals(link, store.detail!!.calendarEvent)
    }

    @Test
    fun markEventAddedIsOptimistic() = runTest {
        val api = fakeAPI {
            "conversationDetail" returns detail().copy(events = listOf(ConversationDetail.Event("Lunch", "", now, 30)))
            "setEventsCreated" returns Unit
        }
        val store = ConversationDetailStore(conversation, api.client)
        store.load()
        store.markEventAdded(0)
        assertTrue(store.detail!!.events[0].isCreated)
        assertEquals(listOf(listOf("c1", listOf(0), true)), api.called("setEventsCreated"))
    }

    @Test
    fun testPromptDropsBold() = runTest {
        val api = fakeAPI { "testConversationPrompt" returns "**Bold** text" }
        assertEquals("Bold text", ConversationDetailStore(conversation, api.client).testPrompt("  Summarize  "))
        assertNull(ConversationDetailStore(conversation, api.client).testPrompt("   "))
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class TranscriptSpeakersStoreTest {
    private val now = Instant.parse("2026-10-08T15:00:00Z")
    private val conversation = Fixtures.conversation("c1", now)
    private val lines = listOf(
        ConversationDetail.Line(0, "Speaker 1", false, "Hi", 0.0, segmentID = "s0", speakerID = 0),
        ConversationDetail.Line(1, "Speaker 2", false, "Yo", 1.0, segmentID = "s1", speakerID = 1),
        ConversationDetail.Line(2, "Speaker 1", false, "Ok", 2.0, segmentID = "s2", speakerID = 0),
    )
    private val anna = Person("p1", "Anna", 0)

    @Test
    fun assignNamesTheWholeVoiceAndLoadsMatches() = runTest {
        val detail = ConversationDetail(conversation, emptyList(), lines)
        val match = VoiceMatch("c9", "Earlier", null, 2, 30.0, listOf("x"), 0.0, 5.0, true)
        val api = fakeAPI {
            "conversationDetail" returns detail
            "assignSpeaker" does { args -> detail.copy(transcript = lines.map { if (it.speakerID == 0) it.relabeled(false, "p1") else it }) }
            "voiceMatches" returns listOf(match, match.copy(conversationID = "c1"))
        }
        val store = ConversationDetailStore(conversation, api.client)
        store.load()
        val speakers = TranscriptSpeakersStore(store)
        speakers.assign(lines[0], TranscriptSpeakersStore.Choice.PersonChoice(anna), TranscriptSpeakersStore.Scope.Voice)
        val call = api.called("assignSpeaker").single()
        assertEquals(listOf("c1", listOf("s0", "s2"), 0, SpeakerTarget.Person("p1")), call)
        assertEquals("p1", store.detail!!.transcript[2].personID)
        assertTrue(speakers.offersSummaryRefresh)
        // The current conversation is not offered as a match.
        assertEquals(listOf("c9"), speakers.matches!!.items.map { it.conversationID })
    }

    @Test
    fun assignRollsBackWhenRefused() = runTest {
        val detail = ConversationDetail(conversation, emptyList(), lines)
        val api = fakeAPI {
            "conversationDetail" returns detail
            "assignSpeaker" throws IllegalStateException("no")
        }
        val store = ConversationDetailStore(conversation, api.client)
        store.load()
        val speakers = TranscriptSpeakersStore(store)
        speakers.assign(lines[1], TranscriptSpeakersStore.Choice.Me, TranscriptSpeakersStore.Scope.Line)
        assertEquals(detail, store.detail)
        assertFalse(speakers.offersSummaryRefresh)
        assertTrue(speakers.lastError != null)
    }

    @Test
    fun answerRemovesTheMatch() = runTest {
        val detail = ConversationDetail(conversation, emptyList(), lines)
        val match = VoiceMatch("c9", "Earlier", null, 2, 30.0, listOf("x"), 0.0, 5.0, true)
        val api = fakeAPI {
            "conversationDetail" returns detail
            "assignSpeaker" returns detail
            "voiceMatches" returns listOf(match)
            "rejectSpeaker" returns detail
        }
        val store = ConversationDetailStore(conversation, api.client)
        store.load()
        val speakers = TranscriptSpeakersStore(store)
        speakers.assign(lines[1], TranscriptSpeakersStore.Choice.PersonChoice(anna), TranscriptSpeakersStore.Scope.Line)
        speakers.answer(match, same = false)
        assertTrue(speakers.matches!!.items.isEmpty())
        assertEquals(1, api.called("rejectSpeaker").size)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class SummaryTemplatesStoreTest {
    private fun app(id: String, name: String, enabled: Boolean = true) =
        OmiApp(id, name, "", null, null, null, null, 0, enabled, setOf("memories"))

    @Test
    fun loadOrdersDefaultThenLastUsedThenName() = runTest {
        val preferences = freshPreferences()
        preferences.set(Preferences.Key.PreferredSummarizationAppId, "b")
        preferences.set(Preferences.Key.LastUsedSummarizationAppId, "c")
        val api = fakeAPI {
            "suggestedSummaryApps" returns listOf(app("a", "Alpha"), app("s", "Suggested"))
            "summaryApps" returns listOf(app("a", "Alpha"), app("b", "Beta"), app("c", "Gamma"), app("d", "Delta"))
        }
        val store = SummaryTemplatesStore(api.client, preferences)
        store.load("c1")
        assertEquals(listOf("b", "c", "a", "d"), store.apps.map { it.id })
        assertEquals(listOf("s"), store.suggested.map { it.id })
        assertEquals(SummaryTemplatesStore.Phase.Loaded, store.phase)
    }

    @Test
    fun setDefaultFailureIsReported() = runTest {
        val api = fakeAPI { "setPreferredSummaryApp" throws IllegalStateException("offline") }
        val store = SummaryTemplatesStore(api.client, freshPreferences())
        assertFalse(store.setDefault(app("a", "Alpha")))
        assertEquals(SummaryTemplatesStore.Failure.SaveDefault, store.failure)
    }

    @Test
    fun createInstallsTheNewApp() = runTest {
        val api = fakeAPI {
            "generateAppDescription" returns ("Writes notes" to "📝")
            "createSummaryApp" returns "new"
            "setApp" returns Unit
        }
        val store = SummaryTemplatesStore(api.client, null)
        val created = store.create(SummaryTemplateDraft("Notes", "Write short notes please")) { byteArrayOf(1) }
        assertEquals("new", created!!.id)
        assertEquals(listOf("new"), store.apps.map { it.id })
        assertNull(store.creationStep)
        assertNull(store.create(SummaryTemplateDraft("No", "short")) { byteArrayOf(1) })
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class SummaryFeedbackStoreTest {
    /** The first sampled id ("c<n>") found by brute force, so the test does not depend on a constant. */
    private val sampledID = (0 until 1000).map { "c$it" }.first { SummaryFeedbackStore.sampled(it) }
    private val unsampledID = (0 until 1000).map { "c$it" }.first { !SummaryFeedbackStore.sampled(it) }

    @Test
    fun asksOnceAWeekForSampledConversations() = runTest {
        val preferences = freshPreferences()
        var clock = 1_000_000_000_000L
        val api = fakeAPI { "sendConversationFeedback" returns true }
        val first = SummaryFeedbackStore(api.client, preferences, sampledID) { clock }
        first.start(hasOwnSummary = true)
        assertEquals(SummaryFeedbackStore.State.Asking, first.state)
        first.send(helpful = true)
        assertEquals(SummaryFeedbackStore.State.Thanked, first.state)
        // Another sampled conversation the same week does not ask.
        val other = (1000 until 3000).map { "c$it" }.first { SummaryFeedbackStore.sampled(it) }
        val second = SummaryFeedbackStore(api.client, preferences, other) { clock }
        second.start(hasOwnSummary = true)
        assertEquals(SummaryFeedbackStore.State.Hidden, second.state)
        clock += 8L * 24 * 3600 * 1000
        second.start(hasOwnSummary = true)
        assertEquals(SummaryFeedbackStore.State.Asking, second.state)
        val unsampled = SummaryFeedbackStore(api.client, freshPreferences(), unsampledID) { clock }
        unsampled.start(hasOwnSummary = true)
        assertEquals(SummaryFeedbackStore.State.Hidden, unsampled.state)
    }

    @Test
    fun failedSendKeepsTheRow() = runTest {
        val api = fakeAPI { "sendConversationFeedback" returns false }
        val store = SummaryFeedbackStore(api.client, freshPreferences(), sampledID)
        store.start(hasOwnSummary = true)
        store.send(helpful = false, reason = com.friend.ios.core.models.SummaryFeedbackReason.Inaccurate)
        assertEquals(SummaryFeedbackStore.State.Failed, store.state)
        store.dismiss()
        assertEquals(SummaryFeedbackStore.State.Hidden, store.state)
    }

    @Test
    fun asksAboutTheOneThingThereIsOrPicksByTheHash() {
        val summary = com.friend.ios.core.models.ConversationFeedbackKind.Summary
        val recording = com.friend.ios.core.models.ConversationFeedbackKind.Recording
        assertEquals(null, SummaryFeedbackStore.kind("demo-2", hasSummary = false, hasRecording = false))
        assertEquals(summary, SummaryFeedbackStore.kind("demo-1", hasSummary = true, hasRecording = false))
        assertEquals(recording, SummaryFeedbackStore.kind("demo-2", hasSummary = false, hasRecording = true))
        // Both: bit 0 of byte 4 of SHA-256(id), as Flutter's feedbackPromptKindForTarget.
        assertEquals(summary, SummaryFeedbackStore.kind("demo-2", hasSummary = true, hasRecording = true))
        assertEquals(recording, SummaryFeedbackStore.kind("demo-1", hasSummary = true, hasRecording = true))
        assertEquals(null, SummaryFeedbackStore.kind("", hasSummary = true, hasRecording = true))
    }

    @Test
    fun aFinishedRecordingAsksAboutTheRecording() = runTest {
        val preferences = freshPreferences()
        val now = 1_800_000_000_000L
        val api = fakeAPI { "sendConversationFeedback" returns true }
        val feedback = SummaryFeedbackStore(api.client, preferences, "demo-5") { now }
        feedback.start(hasOwnSummary = true, hasRecording = true)
        assertEquals(SummaryFeedbackStore.State.Asking, feedback.state)
        assertEquals(com.friend.ios.core.models.ConversationFeedbackKind.Recording, feedback.kind)
        feedback.send(helpful = false, reason = com.friend.ios.core.models.SummaryFeedbackReason.MissingAudio)
        val sent = api.called("sendConversationFeedback").single()
        assertEquals(
            listOf("demo-5", com.friend.ios.core.models.ConversationFeedbackKind.Recording, false, com.friend.ios.core.models.SummaryFeedbackReason.MissingAudio),
            sent.take(4),
        )
        assertEquals("recording_quality", (sent[1] as com.friend.ios.core.models.ConversationFeedbackKind).rawValue)
        assertEquals("recording_missing_audio", (sent[3] as com.friend.ios.core.models.SummaryFeedbackReason).rawValue)
        // One budget for both questions: another sampled conversation the same week does not ask.
        val other = SummaryFeedbackStore(api.client, preferences, "05f95229-5ae7-40c8-9ee3-8df3844b6ad1") { now }
        other.start(hasOwnSummary = true)
        assertEquals(SummaryFeedbackStore.State.Hidden, other.state)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class SearchStoreTest {
    private val now = Instant.parse("2026-10-08T15:00:00Z")

    private fun stores(api: com.friend.ios.network.APIClientProtocol, scope: kotlinx.coroutines.CoroutineScope): Triple<ConversationsStore, TasksStore, MemoriesStore> =
        Triple(ConversationsStore(api, scope, ZoneOffset.UTC), TasksStore(api, ZoneOffset.UTC, scope = scope), MemoriesStore(api, scope))

    @Test
    fun localMatchesFirstThenServerHits() = runTest {
        val local = Fixtures.conversation("a", now, title = "Café plans")
        val remote = Fixtures.conversation("b", now.minusSeconds(60), title = "Something said")
        val api = fakeAPI {
            "conversations" returns listOf(local)
            "searchConversations" returns listOf(remote, local)
            "searchRecaps" returns listOf(DailySummary("r", "2026-10-07", "Day", "", null, null, emptyList(), emptyList()))
        }
        val (conversations, tasks, memories) = stores(api.client, backgroundScope)
        conversations.load()
        val search = SearchStore(api.client, conversations, tasks, memories, backgroundScope, debounceMillis = 300)
        search.update("cafe")
        assertEquals(SearchStore.Phase.Searching, search.phase)
        assertEquals(listOf("a"), search.conversations.map { it.id })
        advanceTimeBy(1_000); runCurrent()
        assertEquals(SearchStore.Phase.Done, search.phase)
        assertEquals(listOf("a", "b"), search.conversations.map { it.id })
        assertEquals(1, search.recaps.size)
        assertEquals(1, api.called("searchConversations").size)
    }

    @Test
    fun starredFilterAloneListsStarred() = runTest {
        val api = fakeAPI { "conversations" returns listOf(Fixtures.conversation("s", now, starred = true)) }
        val (conversations, tasks, memories) = stores(api.client, backgroundScope)
        val search = SearchStore(api.client, conversations, tasks, memories, backgroundScope)
        search.filter = SearchStore.Filter(starred = true)
        advanceTimeBy(1_000); runCurrent()
        assertEquals(listOf("s"), search.conversations.map { it.id })
        assertTrue(api.called("searchConversations").isEmpty())
    }

    @Test
    fun recentsAreKeptLikeFlutter() = runTest {
        val api = fakeAPI {}
        val defaults = InMemorySharedPreferences()
        val (conversations, tasks, memories) = stores(api.client, backgroundScope)
        val search = SearchStore(api.client, conversations, tasks, memories, backgroundScope, defaults = defaults)
        (1..8).forEach { search.remember("q$it") }
        search.remember("Q3")
        assertEquals(listOf("Q3", "q8", "q7", "q6", "q5", "q4"), search.recents)
        assertTrue(defaults.getString(SearchStore.recentsKey, null)!!.startsWith(Preferences.LIST_PREFIX))
        // A new store reads them back.
        assertEquals(search.recents, SearchStore(api.client, conversations, tasks, memories, backgroundScope, defaults = defaults).recents)
        search.clearRecents()
        assertTrue(search.recents.isEmpty())
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class TasksStoreExtrasTest {
    private val zone = ZoneOffset.UTC
    private val now = Instant.parse("2026-10-08T15:00:00Z")

    @Test
    fun deleteWithUndoRestoresOrSends() = runTest {
        val api = fakeAPI {
            "actionItems" returns listOf(Fixtures.task("a", "A"), Fixtures.task("b", "B"), Fixtures.task("c", "C"))
            "deleteActionItems" returns listOf("a")
        }
        val store = TasksStore(api.client, zone, scope = backgroundScope)
        store.load()
        store.deleteWithUndo(listOf("b"))
        assertEquals(listOf("a", "c"), store.tasks.map { it.id })
        store.undoDelete()
        assertEquals(listOf("a", "b", "c"), store.tasks.map { it.id })
        store.deleteWithUndo(listOf("a", "c"))
        store.commitDeletion()
        // The backend deleted only "a": "c" comes back.
        assertEquals(listOf("b", "c"), store.tasks.map { it.id })
        assertTrue(store.lastError != null)
    }

    @Test
    fun indentNeedsARowAboveAndStoresTheLayout() = runTest {
        val due = now.plusSeconds(3600)
        val api = fakeAPI {
            "actionItems" returns listOf(Fixtures.task("a", "A", due = due), Fixtures.task("b", "B", due = due.plusSeconds(60)))
            "setTaskLayout" returns Unit
        }
        val store = TasksStore(api.client, zone, scope = backgroundScope)
        store.load()
        assertFalse(store.canIndent("a", now))
        assertTrue(store.canIndent("b", now))
        store.indent("b", now)
        assertEquals(1, store.tasks.first { it.id == "b" }.indentLevel)
        assertEquals(listOf("b"), store.descendants("a", now))
        assertFalse(store.canIndent("b", now))
        assertTrue(store.canOutdent("b"))
    }

    @Test
    fun dayListsDueThenAdded() = runTest {
        val day = LocalDate.parse("2026-10-08")
        val api = fakeAPI {
            "actionItems" returns listOf(
                Fixtures.task("due", "Due", due = now),
                Fixtures.task("added", "Added", created = now),
                Fixtures.task("other", "Other", due = now.plusSeconds(86_400 * 3)),
            )
        }
        val store = TasksStore(api.client, zone, scope = backgroundScope)
        store.load()
        val tasks = store.day(day)
        assertEquals(listOf("due"), tasks.due.map { it.id })
        assertEquals(listOf("added"), tasks.added.map { it.id })
    }

    @Test
    fun exportSkipsExportedAndReports() = runTest {
        val api = fakeAPI {
            "actionItems" returns listOf(Fixtures.task("a", "A"), Fixtures.task("b", "B").copy(exportPlatform = "todoist"))
            "createIntegrationTask" returns Unit
            "markActionItemExported" returns Unit
        }
        val store = TasksStore(api.client, zone, scope = backgroundScope)
        store.load()
        assertEquals(TaskNotice.Kind.Exported("todoist", 1, 0), store.export(listOf("a", "b"), "todoist"))
        assertEquals("todoist", store.tasks.first { it.id == "a" }.exportPlatform)
        assertEquals(TaskNotice.Kind.AlreadyExported, store.export(listOf("b"), "todoist"))
    }

    @Test
    fun acceptShareAddsAndReloads() = runTest {
        val api = fakeAPI {
            "sharedActionItems" returns com.friend.ios.core.models.SharedTasks("t", "Anna", listOf(com.friend.ios.core.models.SharedTasks.Item("X", null)))
            "acceptSharedActionItems" returns 1
            "actionItems" returns listOf(Fixtures.task("x", "X"))
        }
        val store = TasksStore(api.client, zone, scope = backgroundScope)
        store.openShare("t")
        assertEquals("Anna", store.incomingShare!!.senderName)
        assertTrue(store.acceptShare())
        assertNull(store.incomingShare)
        assertEquals(TaskNotice.Kind.SharedAdded(1), store.notice!!.kind)
        assertEquals(listOf("x"), store.tasks.map { it.id })
    }
}
