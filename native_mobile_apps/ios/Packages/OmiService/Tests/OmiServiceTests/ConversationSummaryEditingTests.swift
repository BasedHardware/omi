import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// Editing the saved summary in place (`PATCH v1/conversations/{id}/summary`): the new text shows
/// at once, the old one comes back when the backend refuses, and every refusal says what happened.
@MainActor
struct ConversationSummaryEditingTests {
    private func detailStore(_ api: FakeAPIClient) async -> ConversationDetailStore {
        let store = ConversationDetailStore(preview: Fixtures.conversations[0], api: api)
        await store.load()
        return store
    }

    /// A conversation whose summary is an app's result, the way the backend sends it.
    private func appSummary(
        _ api: FakeAPIClient, appID: String? = "app-notes", content: String = "Decisions and owners.",
        gist: String? = nil
    ) {
        api.conversationExtras.details["c1"] = ConversationDetail(
            conversation: Fixtures.conversations[0], summaryActionItems: [], transcript: [],
            summary: content, gist: gist, summaryAppID: appID, summaryIsOmiOwn: appID == nil
        )
    }

    @Test func savesEditedSummaryInPlace() async {
        let api = FakeAPIClient()
        let store = await detailStore(api)
        #expect(store.canEditSummary)
        let before = store.detail?.summary

        #expect(await store.editSummary("  Q4: ship the beta.  ") == .saved)
        // Trimmed, and on screen before the backend answered.
        #expect(store.detail?.summary == "Q4: ship the beta.")
        #expect(store.detail?.summary != before)
        #expect(api.conversationExtras.log.contains("summary:c1@own=Q4: ship the beta."))
        #expect(api.conversationExtras.savedSummaries["c1"] == "Q4: ship the beta.")
    }

    @Test func editingOmiOwnSummaryDropsTheGist() async {
        let api = FakeAPIClient()
        api.conversationExtras.details["c1"] = ConversationDetail(
            conversation: Fixtures.conversations[0], summaryActionItems: [], transcript: [],
            summary: "Overview of q4 roadmap with anna.", gist: "Three decisions, one owner."
        )
        let store = await detailStore(api)
        #expect(store.detail?.gist != nil)

        #expect(await store.editSummary("Rewritten by hand.") == .saved)
        // The generated sections, and the gist that came with them, are gone on the backend.
        #expect(store.detail?.gist == nil)
    }

    @Test func editingAnAppsResultKeepsTheGistAndNamesTheApp() async {
        let api = FakeAPIClient()
        appSummary(api, gist: "Kept.")
        let store = await detailStore(api)
        #expect(store.canEditSummary)

        #expect(await store.editSummary("Notes, tightened.") == .saved)
        #expect(api.conversationExtras.log.contains("summary:c1@app-notes=Notes, tightened."))
        // An app's result carries no generated sections, so nothing else changes.
        #expect(store.detail?.gist == "Kept.")
    }

    @Test func sendsNothingWhenTheTextIsEmptyOrUnchanged() async {
        let api = FakeAPIClient()
        let store = await detailStore(api)
        let before = store.detail?.summary

        #expect(await store.editSummary("   \n ") == .unchanged)
        #expect(await store.editSummary(before ?? "") == .unchanged)
        #expect(api.conversationExtras.log.isEmpty)
        #expect(store.detail?.summary == before)
    }

    @Test func aResultWithoutAnAppIDStaysReadOnly() async {
        let api = FakeAPIClient()
        // An app result without its id, which the PATCH cannot address.
        api.conversationExtras.details["c1"] = ConversationDetail(
            conversation: Fixtures.conversations[0], summaryActionItems: [], transcript: [],
            summary: "Written by an app that sent no id.", summaryAppID: nil, summaryIsOmiOwn: false
        )
        let store = await detailStore(api)
        #expect(await !store.canEditSummary)

        #expect(await store.editSummary("Trying anyway.") == .unchanged)
        #expect(api.conversationExtras.log.isEmpty)
        #expect(store.detail?.summary == "Written by an app that sent no id.")
    }

    @Test func aRefusedEditRollsBackAndSaysWhatFailed() async {
        let api = FakeAPIClient()
        let store = await detailStore(api)
        let before = store.detail?.summary
        api.conversationExtras.failing = ["summary"]

        let outcome = await store.editSummary("Never saved.")
        #expect(outcome == .failed(.refused(status: 500)))
        #expect(store.detail?.summary == before)
    }

    @Test func aRollbackBringsTheGistBackToo() async {
        let api = FakeAPIClient()
        api.conversationExtras.details["c1"] = ConversationDetail(
            conversation: Fixtures.conversations[0], summaryActionItems: [], transcript: [],
            summary: "Overview of q4 roadmap with anna.", gist: "Three decisions, one owner."
        )
        let store = await detailStore(api)
        api.conversationExtras.failing = ["summary"]

        #expect(await store.editSummary("Never saved.") == .failed(.refused(status: 500)))
        #expect(store.detail?.summary == "Overview of q4 roadmap with anna.")
        #expect(store.detail?.gist == "Three decisions, one owner.")
    }

    @Test func aVanishedAppResultSaysSo() async {
        let api = FakeAPIClient()
        appSummary(api, appID: "app-gone")
        let store = await detailStore(api)
        let before = store.detail?.summary

        #expect(await store.editSummary("Notes, v2.") == .failed(.appResultGone))
        #expect(store.detail?.summary == before)
    }

    /// The backend answers 404 both for a vanished app result and for a vanished conversation; only
    /// the second one is about the conversation itself.
    @Test func aVanishedConversationIsNotBlamedOnAnApp() async {
        let api = FakeAPIClient()
        let store = await detailStore(api)
        let before = store.detail?.summary
        api.conversationExtras.summaryConversationGone = true

        #expect(await store.editSummary("Edited after it was deleted.") == .failed(.conversationGone))
        #expect(store.detail?.summary == before)
    }

    @Test func twoResultsFromTheSameAppAreRefused() async {
        let api = FakeAPIClient()
        appSummary(api)
        api.conversationExtras.duplicateSummaryApps = true
        let store = await detailStore(api)

        #expect(await store.editSummary("Notes, v2.") == .failed(.appResultAmbiguous))
        #expect(store.detail?.summary == "Decisions and owners.")
    }

    @Test func anUnreachableBackendAndASignedOutDeviceAreToldApart() async {
        let api = FakeAPIClient()
        let store = await detailStore(api)

        api.fail(with: .transport("no route to the backend"))
        #expect(await store.editSummary("Offline edit.") == .failed(.offline))
        api.fail(with: .notSignedIn)
        #expect(await store.editSummary("Signed out edit.") == .failed(.signedOut))
        api.fail(with: nil)
        #expect(await store.editSummary("Back online.") == .saved)
    }
}
