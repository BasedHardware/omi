package com.friend.ios.service.stores

import com.friend.ios.core.models.IgnoredVoice
import com.friend.ios.core.models.ImportJob
import com.friend.ios.core.models.KnowledgeGraph
import com.friend.ios.core.models.Person
import com.friend.ios.core.models.VoiceProfileSettings
import com.friend.ios.network.APIError
import com.friend.ios.persistence.Preferences
import com.friend.ios.persistence.Preferences.Key
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.fakeAPI
import com.friend.ios.service.freshPreferences
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Ports of the people, voices, transcription, import and graph store tests
 * (`AccountAndSettingsTests.swift`, `VoicesStoreTests.swift`, `ImportStoreTests.swift`,
 * `KnowledgeGraphTests.swift`), for the Voices & people, Listening and Memory screens.
 */
class PeopleMemoryStoresTest {
    private fun store(api: FakeAPI, prefs: Preferences = freshPreferences()) =
        SettingsStore(api.client, prefs, CoroutineScope(Dispatchers.Unconfined), File(System.getProperty("java.io.tmpdir")))

    private fun person(id: String, name: String, pinned: Boolean = false, confidence: Person.Confidence = Person.Confidence.Unknown, samples: Int = 0) =
        Person(id, name, samples, List(samples) { "https://x/$id/$it.wav" }, pinned, confidence)

    @Test
    fun peopleSearchIgnoresCaseAndAccents() = runTest {
        val api = fakeAPI { "peopleWithStats" returns listOf(person("2", "Zoë"), person("1", "Anna"), person("3", "José")) }
        val settings = store(api)
        settings.loadPeopleWithStats()
        assertEquals(listOf("Anna", "José", "Zoë"), settings.people.map { it.name })
        assertEquals(listOf("José"), settings.people("jose").map { it.name })
        assertEquals(listOf("Zoë"), settings.people(" ZOE ").map { it.name })
        assertEquals(3, settings.people("").size)
    }

    /** Clean up offers only unsure, unpinned people; a refused delete brings that person back. */
    @Test
    fun cleanUpSkipsPinnedAndRestoresRefusedDeletes() = runTest {
        val api = fakeAPI {
            "peopleWithStats" returns listOf(
                person("a", "Ann", confidence = Person.Confidence.Unverified),
                person("b", "Ben", pinned = true, confidence = Person.Confidence.Unverified),
                person("c", "Cy", confidence = Person.Confidence.Confirmed),
                person("d", "Di", confidence = Person.Confidence.Unverified),
            )
            "deletePerson" does { args -> if (args[0] == "d") throw APIError.Http(500, "") }
        }
        val settings = store(api)
        settings.loadPeopleWithStats()
        assertEquals(listOf("a", "d"), settings.cleanUpCandidates.map { it.id })
        settings.deletePeople(setOf("a", "d"))
        assertEquals(listOf("Ben", "Cy", "Di"), settings.people.map { it.name })
        assertEquals("1 not deleted", settings.lastError)
    }

    @Test
    fun pinRollsBackWhenRefused() = runTest {
        val api = fakeAPI {
            "peopleWithStats" returns listOf(person("a", "Ann"))
            "setPersonPinned" throws APIError.Http(500, "")
        }
        val settings = store(api)
        settings.loadPeopleWithStats()
        settings.setPinned("a", true)
        assertFalse(settings.person("a")!!.isPinned)
        assertTrue(settings.lastError != null)
    }

    @Test
    fun deletingASampleDropsItsURLAndCount() = runTest {
        val api = fakeAPI {
            "peopleWithStats" returns listOf(person("a", "Ann", samples = 3))
            "deleteSpeechSample" returns Unit
        }
        val settings = store(api)
        settings.loadPeopleWithStats()
        settings.deleteSample("a", 1)
        val ann = settings.person("a")!!
        assertEquals(2, ann.sampleCount)
        assertEquals(listOf("https://x/a/0.wav", "https://x/a/2.wav"), ann.sampleURLs)
        assertEquals(listOf<Any?>("a", 1), api.called("deleteSpeechSample").single())
    }

    /** Detect languages is the inverse of the backend's `single_language_mode`, cached for the next launch. */
    @Test
    fun languageDetectionMirrorsSingleLanguageMode() = runTest {
        val prefs = freshPreferences()
        val api = fakeAPI {
            "singleLanguageMode" returns true
            "setSingleLanguageMode" returns Unit
        }
        val settings = store(api, prefs)
        assertTrue(settings.detectsLanguages)
        assertFalse(settings.loadLanguageDetection())
        assertTrue(prefs.bool(Key.CachedSingleLanguageMode))
        assertTrue(settings.setLanguageDetection(true))
        assertEquals(listOf<Any?>(false), api.called("setSingleLanguageMode").single())
        assertTrue(settings.detectsLanguages)
        with(api) { "setSingleLanguageMode" throws APIError.Transport("offline") }
        assertFalse(settings.setLanguageDetection(false))
        assertTrue(settings.detectsLanguages)
    }

    @Test
    fun voiceSwitchesApplyAndRollBack() = runTest {
        val api = fakeAPI {
            "voiceProfileSettings" returns VoiceProfileSettings(asksToTag = true, savesOtherVoices = true)
            "updateVoiceProfileSettings" returns VoiceProfileSettings(asksToTag = false, savesOtherVoices = true)
        }
        val voices = VoicesStore(api.client)
        voices.loadSettings()
        voices.setAsksToTag(false)
        assertFalse(voices.settings!!.asksToTag)
        assertEquals(listOf<Any?>(false, null), api.called("updateVoiceProfileSettings").single())
        with(api) { "updateVoiceProfileSettings" throws APIError.Http(500, "") }
        voices.setSavesOtherVoices(false)
        assertTrue(voices.settings!!.savesOtherVoices)
        assertTrue(voices.lastError != null)
    }

    @Test
    fun restoringAnIgnoredVoiceComesBackWhenRefused() = runTest {
        val voice = IgnoredVoice("c1", 2, "Standup", null)
        val api = fakeAPI {
            "ignoredVoices" returns listOf(voice)
            "restoreIgnoredVoice" throws APIError.Http(500, "")
        }
        val voices = VoicesStore(api.client)
        voices.loadIgnored()
        assertTrue(voices.ignoredLoaded)
        voices.restore(voice)
        assertEquals(listOf(voice), voices.ignored)
    }

    @Test
    fun importRefusesNonZipAndTooLargeFiles() = runTest {
        val api = fakeAPI { "importLimitless" returns ImportJob("j1", ImportJob.Status.Completed) }
        val store = ImportStore(api.client, CoroutineScope(Dispatchers.Unconfined))
        assertFalse(store.importZip(ByteArray(4), "notes.txt", "en"))
        assertEquals("unreadable", store.lastError)
        assertFalse(store.importZip(ByteArray(ImportStore.MAX_BYTES + 1), "big.zip", "en"))
        assertEquals("tooLarge", store.lastError)
        assertTrue(store.importZip(ByteArray(4), "export.zip", "de"))
        assertNull(store.lastError)
        assertEquals(listOf("j1"), store.jobs.map { it.id })
        assertEquals("de", api.called("importLimitless").single()[2])
    }

    @Test
    fun deletingAnImportComesBackWhenRefused() = runTest {
        val jobs = listOf(ImportJob("a", ImportJob.Status.Completed), ImportJob("b", ImportJob.Status.Failed))
        val api = fakeAPI {
            "importJobs" returns jobs
            "deleteImportJob" throws APIError.Http(409, "")
        }
        val store = ImportStore(api.client, CoroutineScope(Dispatchers.Unconfined))
        store.load()
        assertEquals(ImportStore.Phase.Loaded, store.phase)
        store.delete("b")
        assertEquals(listOf("a", "b"), store.jobs.map { it.id })
    }

    @Test
    fun importProgressIsTheShareOfFilesDone() {
        assertEquals(0.25, ImportJob("j", ImportJob.Status.Processing, totalFiles = 8, processedFiles = 2).progress!!, 1e-9)
        assertNull(ImportJob("j", ImportJob.Status.Processing, totalFiles = 0, processedFiles = 0).progress)
        assertTrue(ImportJob("j", ImportJob.Status.Pending).isRunning)
        assertFalse(ImportJob("j", ImportJob.Status.Cancelled).isRunning)
    }

    /** Every node that stands for the user becomes the one center node; its edges follow. */
    @Test
    fun graphCentersOnTheUser() {
        val graph = KnowledgeGraph(
            nodes = listOf(
                KnowledgeGraph.Node("u1", "Me", "person"),
                KnowledgeGraph.Node("u2", "Alice", "user"),
                KnowledgeGraph.Node("p", "Bob", "person"),
                KnowledgeGraph.Node("q", "Berlin", "place"),
            ),
            edges = listOf(
                KnowledgeGraph.Edge("u1", "p", "knows"),
                KnowledgeGraph.Edge("u2", "p", "knows"),
                KnowledgeGraph.Edge("p", "q", "lives in"),
                KnowledgeGraph.Edge("u1", "u2", "is"),
            ),
        )
        val centered = GraphLayout.centered("Alice", graph)
        assertEquals(listOf(GraphLayout.USER_ID, "p", "q"), centered.nodes.map { it.id })
        assertEquals("Me", centered.nodes.first().label)
        assertEquals(2, centered.edges.size)
        val positions = GraphLayout.positions(centered, GraphLayout.USER_ID)
        assertEquals(0.0 to 0.0, positions[GraphLayout.USER_ID])
        positions.values.forEach { (x, y) -> assertTrue(x in -1.0..1.0 && y in -1.0..1.0) }
    }

    @Test
    fun graphStoreLoadsAndCounts() = runTest {
        val api = fakeAPI {
            "knowledgeGraph" returns KnowledgeGraph(listOf(KnowledgeGraph.Node("p", "Bob", "person")), emptyList())
        }
        val graph = KnowledgeGraphStore(api.client, "Alice")
        graph.load()
        assertEquals(KnowledgeGraphStore.Phase.Loaded, graph.phase)
        assertFalse(graph.isEmpty)
        assertEquals(1, graph.nodes.count { it.node.kind == "person" })
    }
}
