import OmiTheme
import SwiftUI

/// Page states for a memories list read the server stopped early (#24722).
/// A truncated page is an unfinished read, not an empty account, so neither
/// state may read as "No Memories Yet" or as the end of the history.

/// The page body for an empty truncated read: the server stopped before it
/// reached this account's history. One shared error state, because this is a
/// recoverable pause with a "Try Again", not a fact about the account.
struct MemoriesUnfinishedReadState: View {
  let retry: () -> Void

  var body: some View {
    GlassErrorState(
      title: "Memories Didn't Finish Loading",
      message: "The server stopped before it reached your history. This does not mean you have none.",
      retryAccessibilityIdentifier: "memories-unfinished-read-retry",
      retry: retry
    )
    .accessibilityIdentifier("memories-unfinished-read")
  }
}

/// The list footer for a truncated read that did return rows: the history on
/// screen stops early, so the end of the list must not read as the end of it.
struct MemoriesUnfinishedReadFooter: View {
  let retry: () -> Void

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: GlassPageState.errorSymbol)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
      Text("Some memories were not loaded. This is not the complete history.")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
      Button(GlassPageState.retryTitle, action: retry)
        .buttonStyle(GlassPageState.retryStyle)
        .accessibilityIdentifier("memories-unfinished-read-footer-retry")
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, OmiSpacing.lg)
    .accessibilityIdentifier("memories-unfinished-read-footer")
  }
}
