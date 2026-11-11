import OmiTheme
import SwiftUI

/// Server attention items share Activity's existing conversation navigation.
/// Unknown kinds have no retry control; notes retries never use general reprocess.
struct AttentionLedgerSection: View {
  @ObservedObject var store: AttentionLedgerStore
  let onOpen: (String) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text("Needs attention").font(.headline).foregroundStyle(Ink.primary)
      if store.loadFailed {
        Text("Attention items couldn’t load. Try again.").font(.caption).foregroundStyle(Ink.secondary)
      }
      ForEach(store.rows) { item in
        HStack(spacing: 12) {
          Image(systemName: "exclamationmark.triangle").foregroundStyle(Ink.secondary)
          Button {
            onOpen(item.conversationId)
          } label: {
            VStack(alignment: .leading, spacing: 4) {
              Text(item.title ?? "Conversation needs attention").font(.body).foregroundStyle(Ink.primary)
              if item.notesOnly {
                Text("Notes couldn’t be completed. Saved tasks and events are kept.")
                  .font(.caption).foregroundStyle(Ink.secondary)
              }
              if store.errors.contains(item.id) {
                Text("Couldn’t retry. Try again.").font(.caption).foregroundStyle(Ink.primary)
              }
            }.frame(maxWidth: .infinity, alignment: .leading)
          }.buttonStyle(.plain)
          if item.canRetry || store.retrying.contains(item.id) {
            Button(store.retrying.contains(item.id) ? "Retrying…" : item.notesOnly ? "Re-run notes" : "Try Again") {
              Task { await store.retry(item) }
            }
            .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
            .disabled(store.retrying.contains(item.id))
            .accessibilityIdentifier("attention-retry-\(item.id)")
          }
        }.padding(14).accessibilityIdentifier("attention-item-\(item.id)")
      }
    }.accessibilityIdentifier("activity-attention-ledger")
  }
}
