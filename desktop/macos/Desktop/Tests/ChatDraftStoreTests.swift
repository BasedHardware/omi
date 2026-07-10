import XCTest
@testable import Omi_Computer

@MainActor
final class ChatDraftStoreTests: XCTestCase {
    private var rootURL: URL!

    override func setUp() async throws {
        rootURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("ChatDraftStoreTests-\(UUID().uuidString)", isDirectory: true)
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: rootURL)
        rootURL = nil
    }

    func testDraftsRoundTripIndependentlyAcrossRelaunch() {
        let first = makeStore(ownerID: "user-a")
        first.setText("main draft\nwith detail", for: .mainChat(contextID: "omi:default"))
        first.setText("notch draft", for: .floatingMain)
        first.setText("task draft", for: .taskChat("task-1"))
        first.flush()

        let relaunched = makeStore(ownerID: "user-a")
        XCTAssertEqual(relaunched.text(for: .mainChat(contextID: "omi:default")), "main draft\nwith detail")
        XCTAssertEqual(relaunched.text(for: .floatingMain), "notch draft")
        XCTAssertEqual(relaunched.text(for: .taskChat("task-1")), "task draft")
        XCTAssertEqual(relaunched.text(for: .taskChat("task-2")), "")
    }

    func testLatestEditWinsWhenWritesAreCoalesced() {
        let store = makeStore(ownerID: "user-a")
        store.setText("first", for: .floatingMain)
        store.setText("second", for: .floatingMain)
        store.setText("latest", for: .floatingMain)
        store.flush()

        XCTAssertEqual(makeStore(ownerID: "user-a").text(for: .floatingMain), "latest")
    }

    func testDraftsAreIsolatedByAccount() {
        let firstUser = makeStore(ownerID: "user-a")
        firstUser.setText("Alice's draft", for: .floatingMain)
        firstUser.flush()

        let secondUser = makeStore(ownerID: "user-b")
        XCTAssertEqual(secondUser.text(for: .floatingMain), "")
        secondUser.setText("Bob's draft", for: .floatingMain)
        secondUser.flush()

        XCTAssertEqual(makeStore(ownerID: "user-a").text(for: .floatingMain), "Alice's draft")
        XCTAssertEqual(makeStore(ownerID: "user-b").text(for: .floatingMain), "Bob's draft")
    }

    func testExplicitSignOutClearsOnlyThatAccountsDrafts() {
        let firstUser = makeStore(ownerID: "user-a")
        firstUser.setText("remove me", for: .floatingMain)
        firstUser.flush()

        let secondUser = makeStore(ownerID: "user-b")
        secondUser.setText("keep me", for: .floatingMain)
        secondUser.flush()

        firstUser.clearAll(ownerID: "user-a")

        XCTAssertEqual(makeStore(ownerID: "user-a").text(for: .floatingMain), "")
        XCTAssertEqual(makeStore(ownerID: "user-b").text(for: .floatingMain), "keep me")
    }

    func testClearingDraftDeletesItsPersistedRecord() {
        let store = makeStore(ownerID: "user-a")
        store.setText("temporary", for: .floatingMain)
        store.flush()
        store.clear(.floatingMain)
        store.flush()

        XCTAssertEqual(makeStore(ownerID: "user-a").text(for: .floatingMain), "")
        XCTAssertTrue(allJSONFiles().isEmpty)
    }

    func testCorruptRecordDoesNotAffectOtherDrafts() throws {
        let store = makeStore(ownerID: "user-a")
        store.setText("main unique value", for: .mainChat(contextID: "omi:default"))
        store.setText("notch survives", for: .floatingMain)
        store.flush()

        let mainFile = try XCTUnwrap(allJSONFiles().first { url in
            (try? String(contentsOf: url, encoding: .utf8))?.contains("main unique value") == true
        })
        try Data("not-json".utf8).write(to: mainFile, options: .atomic)

        let relaunched = makeStore(ownerID: "user-a")
        XCTAssertEqual(relaunched.text(for: .mainChat(contextID: "omi:default")), "")
        XCTAssertEqual(relaunched.text(for: .floatingMain), "notch survives")
    }

    func testDraftPersistenceHarnessActionsAreDiscoverable() {
        let registry = DesktopAutomationActionRegistry.shared
        registry.registerBuiltins()
        let names = Set(registry.descriptors().map(\.name))

        XCTAssertTrue(names.contains("set_chat_drafts"))
        XCTAssertTrue(names.contains("chat_drafts_snapshot"))
    }

    func testAcceptedFloatingDraftClearsWhenUnchanged() {
        let state = FloatingControlBarState()
        state.switchAIDraft(to: .onboardingFloating)
        defer {
            ChatDraftStore.shared.clear(.onboardingFloating)
            ChatDraftStore.shared.flush()
        }

        state.aiInputText = "submitted"
        state.markAIDraftSubmitted("submitted")
        state.clearSubmittedAIDraftIfUnchanged("submitted")

        XCTAssertEqual(state.aiInputText, "")
    }

    func testAcceptedFloatingDraftDoesNotClearNewSameTextRevision() {
        let state = FloatingControlBarState()
        state.switchAIDraft(to: .onboardingFloating)
        defer {
            ChatDraftStore.shared.clear(.onboardingFloating)
            ChatDraftStore.shared.flush()
        }

        state.aiInputText = "submitted"
        state.markAIDraftSubmitted("submitted")
        state.aiInputText = "new draft"
        state.aiInputText = "submitted"
        state.clearSubmittedAIDraftIfUnchanged("submitted")

        XCTAssertEqual(state.aiInputText, "submitted")
    }

    private func makeStore(ownerID: String) -> ChatDraftStore {
        ChatDraftStore(
            rootURL: rootURL,
            writeDelay: 60,
            ownerIDProvider: { ownerID }
        )
    }

    private func allJSONFiles() -> [URL] {
        guard let enumerator = FileManager.default.enumerator(
            at: rootURL,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) else { return [] }
        return enumerator.compactMap { $0 as? URL }.filter { $0.pathExtension == "json" }
    }
}
