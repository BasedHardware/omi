import SwiftUI

/// Subscribes to the composer draft on behalf of exactly the subtree that has
/// to redraw while the reader types, and hands that subtree a binding.
///
/// The composer text is not published on `ChatProvider` (see
/// `ChatComposerDraft`), so a page observing the provider is no longer woken by
/// typing. Any view whose appearance genuinely depends on the live text — the
/// input field itself, and Home's ask bar whose width tracks the typed string —
/// wraps itself in this scope instead, which keeps the per-keystroke
/// invalidation inside the composer.
struct ChatDraftScope<Content: View>: View {
  @ObservedObject var draft: ChatComposerDraft
  @ViewBuilder var content: (Binding<String>) -> Content

  var body: some View {
    content(
      Binding(
        get: { draft.text },
        // Route writes through `setText` so a reader edit still advances the
        // revision and schedules persistence exactly as a provider write does.
        set: { draft.setText($0) }
      )
    )
  }
}
