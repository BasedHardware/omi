package com.friend.ios.service.stores

import com.friend.ios.core.models.ConversationDetail
import com.friend.ios.network.APIError
import com.friend.ios.service.FakeAPI
import com.friend.ios.service.fakeAPI
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

/**
 * Port of `ConversationSummaryEditingTests`: editing the saved summary in place
 * (`PATCH v1/conversations/{id}/summary`). The new text shows at once, the old one comes back when
 * the backend refuses, and every refusal says what happened.
 */
class ConversationSummaryEditingTest {
    private val now = Instant.parse("2026-10-08T15:00:00Z")
    private val conversation = Fixtures.conversation("c1", now)

    /** A conversation whose summary is Omi's own, or (with [appID]) an app's result. */
    private fun detail(
        summary: String = "Decisions and owners.",
        gist: String? = null,
        appID: String? = null,
        omiOwn: Boolean = appID == null,
    ) = ConversationDetail(
        conversation = conversation,
        summaryActionItems = emptyList(),
        transcript = emptyList(),
        summary = summary,
        gist = gist,
        summaryAppID = appID,
        summaryIsOmiOwn = omiOwn,
    )

    /** The loaded store, with whatever the PATCH should answer ([stub]) already wired up. */
    private suspend fun loaded(detail: ConversationDetail, stub: FakeAPI.() -> Unit = {}): Pair<FakeAPI, ConversationDetailStore> {
        val api = fakeAPI {
            "conversationDetail" returns detail
            // The backend stores an edit unless the test says otherwise.
            "updateConversationSummary" returns Unit
            stub()
        }
        val store = ConversationDetailStore(conversation, api.client)
        store.load()
        return api to store
    }

    @Test
    fun savesEditedSummaryInPlace() = runTest {
        val (api, store) = loaded(detail())
        val before = store.detail?.summary
        assertTrue(store.canEditSummary)

        assertEquals(SummaryEditOutcome.Saved, store.editSummary("  Q4: ship the beta.  "))
        // Trimmed, and on screen before the backend answered.
        assertEquals("Q4: ship the beta.", store.detail?.summary)
        assertTrue(store.detail?.summary != before)
        assertEquals(listOf(listOf<Any?>("c1", null, "Q4: ship the beta.")), api.called("updateConversationSummary"))
    }

    @Test
    fun editingOmiOwnSummaryDropsTheGist() = runTest {
        val (_, store) = loaded(detail(summary = "Overview of q4 roadmap with anna.", gist = "Three decisions, one owner."))
        assertEquals("Three decisions, one owner.", store.detail?.gist)

        assertEquals(SummaryEditOutcome.Saved, store.editSummary("Rewritten by hand."))
        // The generated sections, and the gist that came with them, are gone on the backend.
        assertNull(store.detail?.gist)
    }

    @Test
    fun editingAnAppsResultKeepsTheGistAndNamesTheApp() = runTest {
        val (api, store) = loaded(detail(gist = "Kept.", appID = "app-notes"))
        assertTrue(store.canEditSummary)

        assertEquals(SummaryEditOutcome.Saved, store.editSummary("Notes, tightened."))
        assertEquals(listOf(listOf<Any?>("c1", "app-notes", "Notes, tightened.")), api.called("updateConversationSummary"))
        // An app's result carries no generated sections, so nothing else changes.
        assertEquals("Kept.", store.detail?.gist)
    }

    @Test
    fun sendsNothingWhenTheTextIsEmptyOrUnchanged() = runTest {
        val (api, store) = loaded(detail())
        val before = store.detail?.summary

        assertEquals(SummaryEditOutcome.Unchanged, store.editSummary("   \n "))
        assertEquals(SummaryEditOutcome.Unchanged, store.editSummary(before ?: ""))
        assertTrue(api.called("updateConversationSummary").isEmpty())
        assertEquals(before, store.detail?.summary)
    }

    @Test
    fun aResultWithoutAnAppIDStaysReadOnly() = runTest {
        // An app result without its id, which the PATCH cannot address.
        val (api, store) = loaded(detail(summary = "Written by an app that sent no id.", appID = null, omiOwn = false))
        assertFalse(store.canEditSummary)

        assertEquals(SummaryEditOutcome.Unchanged, store.editSummary("Trying anyway."))
        assertTrue(api.called("updateConversationSummary").isEmpty())
        assertEquals("Written by an app that sent no id.", store.detail?.summary)
    }

    @Test
    fun aRefusedEditRollsBackAndSaysWhatFailed() = runTest {
        val (_, store) = loaded(detail()) { "updateConversationSummary" throws APIError.Http(500, "") }
        val before = store.detail?.summary

        assertEquals(SummaryEditOutcome.Failed(SummaryEditFailure.Refused(500)), store.editSummary("Never saved."))
        assertEquals(before, store.detail?.summary)
    }

    @Test
    fun aRollbackBringsTheGistBackToo() = runTest {
        val (_, store) = loaded(detail(summary = "Overview of q4 roadmap with anna.", gist = "Three decisions, one owner.")) {
            "updateConversationSummary" throws APIError.Http(500, "")
        }

        assertEquals(SummaryEditOutcome.Failed(SummaryEditFailure.Refused(500)), store.editSummary("Never saved."))
        assertEquals("Overview of q4 roadmap with anna.", store.detail?.summary)
        assertEquals("Three decisions, one owner.", store.detail?.gist)
    }

    @Test
    fun aVanishedAppResultSaysSo() = runTest {
        val (_, store) = loaded(detail(appID = "app-gone")) { "updateConversationSummary" throws APIError.Http(404, "") }
        val before = store.detail?.summary

        assertEquals(SummaryEditOutcome.Failed(SummaryEditFailure.AppResultGone), store.editSummary("Notes, v2."))
        assertEquals(before, store.detail?.summary)
    }

    /**
     * The backend answers 404 both for a vanished app result and for a vanished conversation; only
     * the second one is about the conversation itself.
     */
    @Test
    fun aVanishedConversationIsNotBlamedOnAnApp() = runTest {
        val (_, store) = loaded(detail()) { "updateConversationSummary" throws APIError.Http(404, "") }
        val before = store.detail?.summary

        assertEquals(SummaryEditOutcome.Failed(SummaryEditFailure.ConversationGone), store.editSummary("Edited after it was deleted."))
        assertEquals(before, store.detail?.summary)
    }

    @Test
    fun twoResultsFromTheSameAppAreRefused() = runTest {
        val (_, store) = loaded(detail(appID = "app-notes")) { "updateConversationSummary" throws APIError.Http(409, "") }

        assertEquals(SummaryEditOutcome.Failed(SummaryEditFailure.AppResultAmbiguous), store.editSummary("Notes, v2."))
        assertEquals("Decisions and owners.", store.detail?.summary)
    }

    @Test
    fun anUnreachableBackendAndASignedOutDeviceAreToldApart() = runTest {
        var failure: Throwable? = null
        val (_, store) = loaded(detail()) { "updateConversationSummary" does { failure?.let { throw it } } }

        failure = APIError.Transport("no route to the backend")
        assertEquals(SummaryEditOutcome.Failed(SummaryEditFailure.Offline), store.editSummary("Offline edit."))
        failure = APIError.NotSignedIn
        assertEquals(SummaryEditOutcome.Failed(SummaryEditFailure.SignedOut), store.editSummary("Signed out edit."))
        failure = null
        assertEquals(SummaryEditOutcome.Saved, store.editSummary("Back online."))
    }
}
