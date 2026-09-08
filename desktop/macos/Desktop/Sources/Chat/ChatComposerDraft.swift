import Foundation

/// Owns the unsent composer text for the main chat, plus the draft key it
/// belongs to and its persistence.
///
/// This is deliberately a separate observable from `ChatProvider`. The draft
/// used to be a `@Published` property on the provider, so a single keystroke
/// published on an object that the whole shell observes: Home re-evaluated its
/// entire page body and the transcript's body on every character typed
/// (measured: 21 `DashboardPage.body` + 21 `ChatMessagesView.body` evaluations
/// for 20 keystrokes). Views that must track the text live subscribe here —
/// see `ChatDraftScope` — and everything else keeps observing the provider
/// without being woken by typing.
///
/// `ChatProvider.draftText` still reads and writes through this object, so the
/// provider remains the single owner of composer state and the persistence path
/// is unchanged.
@MainActor
final class ChatComposerDraft: ObservableObject {
  /// The live composer text. Only this property is published.
  @Published var text: String = ""

  /// The draft record this text belongs to. Switching contexts swaps the key
  /// and reloads that context's saved text.
  private(set) var key: ChatDraftKey

  /// Monotonic edit counter. A send captures it so a late acceptance only
  /// clears the composer when the reader has not typed since.
  private(set) var revision: UInt64 = 0

  /// True while text is being loaded from storage, so a restore never counts as
  /// an edit and never writes the value straight back.
  private var isRestoring = false

  private let store: ChatDraftStore

  init(key: ChatDraftKey = .mainChat(contextID: "omi:default"), store: ChatDraftStore? = nil) {
    self.key = key
    self.store = store ?? ChatDraftStore.shared
  }

  /// Applies a reader edit: publishes the new text, advances the revision, and
  /// schedules the coalesced write. Restores bypass both side effects.
  func setText(_ newValue: String) {
    text = newValue
    guard !isRestoring else { return }
    revision &+= 1
    store.setText(newValue, for: key)
  }

  /// Loads the current key's saved text without counting it as an edit.
  func restore() {
    isRestoring = true
    text = store.text(for: key)
    isRestoring = false
  }

  /// Switches to another draft context and loads its saved text. A no-op when
  /// the key is unchanged, so re-entrant context syncs never clear a live draft.
  func activate(key nextKey: ChatDraftKey) {
    guard nextKey != key else { return }
    key = nextKey
    restore()
  }

  /// Drops the in-memory draft and rebinds to `nextKey` without persisting the
  /// cleared value — used when the signed-in owner goes away.
  func reset(to nextKey: ChatDraftKey) {
    key = nextKey
    isRestoring = true
    text = ""
    isRestoring = false
  }
}
