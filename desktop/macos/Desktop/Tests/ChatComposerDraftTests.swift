import Combine
import XCTest

@testable import Omi_Computer

/// The composer draft is the highest-frequency mutation in the app — one write
/// per character typed. It is deliberately *not* published on `ChatProvider`:
/// when it was, Home's whole page body and the chat transcript's body were
/// re-evaluated on every keystroke, and SwiftUI's own change dumper attributed
/// the shell's dominant invalidation to `_chatProvider changed`.
///
/// These tests pin both halves of that contract: the text still round-trips and
/// persists through the provider's accessor, and mutating it must not wake
/// observers of the provider.
@MainActor
final class ChatComposerDraftTests: XCTestCase {
  private var rootURL: URL!

  override func setUp() async throws {
    rootURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("ChatComposerDraftTests-\(UUID().uuidString)", isDirectory: true)
  }

  override func tearDown() async throws {
    try? FileManager.default.removeItem(at: rootURL)
    rootURL = nil
  }

  func testEditsPublishOnTheDraftAndPersistThroughTheStore() {
    let store = makeStore(ownerID: "user-a")
    let draft = ChatComposerDraft(key: .mainChat(contextID: "omi:default"), store: store)

    var published: [String] = []
    let cancellable = draft.$text.dropFirst().sink { published.append($0) }
    defer { cancellable.cancel() }

    draft.setText("hel")
    draft.setText("hello")
    store.flush()

    XCTAssertEqual(published, ["hel", "hello"])
    XCTAssertEqual(draft.text, "hello")
    XCTAssertEqual(
      makeStore(ownerID: "user-a").text(for: .mainChat(contextID: "omi:default")),
      "hello"
    )
  }

  func testEveryEditAdvancesTheRevisionSoALateSendCannotClearNewerText() {
    let draft = ChatComposerDraft(key: .floatingMain, store: makeStore(ownerID: "user-a"))
    let start = draft.revision

    draft.setText("a")
    draft.setText("ab")

    XCTAssertEqual(draft.revision, start &+ 2)
  }

  func testRestoringSavedTextIsNotAnEditAndIsNotWrittenBack() {
    let store = makeStore(ownerID: "user-a")
    store.setText("saved", for: .floatingMain)
    store.flush()

    let draft = ChatComposerDraft(key: .floatingMain, store: store)
    let start = draft.revision
    draft.restore()

    XCTAssertEqual(draft.text, "saved")
    XCTAssertEqual(draft.revision, start, "a restore must not count as a reader edit")
  }

  func testActivatingAnotherContextLoadsThatContextsDraft() {
    let store = makeStore(ownerID: "user-a")
    store.setText("main text", for: .mainChat(contextID: "omi:default"))
    store.setText("other text", for: .mainChat(contextID: "app:other"))
    store.flush()

    let draft = ChatComposerDraft(key: .mainChat(contextID: "omi:default"), store: store)
    draft.restore()
    XCTAssertEqual(draft.text, "main text")

    draft.activate(key: .mainChat(contextID: "app:other"))
    XCTAssertEqual(draft.text, "other text")
  }

  func testReactivatingTheSameContextKeepsUnsentText() {
    let store = makeStore(ownerID: "user-a")
    let draft = ChatComposerDraft(key: .mainChat(contextID: "omi:default"), store: store)
    draft.setText("half-written thought")

    draft.activate(key: .mainChat(contextID: "omi:default"))

    XCTAssertEqual(
      draft.text,
      "half-written thought",
      "a re-entrant context sync must never discard a live draft"
    )
  }

  func testResetDropsTheDraftWithoutPersistingTheClearedValue() {
    let store = makeStore(ownerID: "user-a")
    let draft = ChatComposerDraft(key: .floatingMain, store: store)
    draft.setText("signed-in text")
    let revisionBeforeReset = draft.revision

    draft.reset(to: .mainChat(contextID: "omi:default"))

    XCTAssertEqual(draft.text, "")
    XCTAssertEqual(draft.key, .mainChat(contextID: "omi:default"))
    XCTAssertEqual(draft.revision, revisionBeforeReset, "a reset is not a reader edit")
  }

  /// The regression this whole split exists for: a keystroke must not publish on
  /// the provider, because every page and the transcript observe it.
  func testTypingDoesNotNotifyObserversOfTheProvider() {
    let provider = ChatProvider()
    var providerNotifications = 0
    let cancellable = provider.objectWillChange.sink { _ in providerNotifications += 1 }
    defer { cancellable.cancel() }

    provider.draftText = "t"
    provider.draftText = "ty"
    provider.draftText = "typ"

    XCTAssertEqual(
      providerNotifications,
      0,
      "publishing the draft on ChatProvider re-renders every view observing it, once per character"
    )
    XCTAssertEqual(provider.draftText, "typ", "the provider is still the accessor for composer text")
    XCTAssertEqual(provider.composerDraft.text, "typ")
  }

  private func makeStore(ownerID: String) -> ChatDraftStore {
    ChatDraftStore(
      rootURL: rootURL,
      writeDelay: 60,
      ownerIDProvider: { ownerID }
    )
  }
}
