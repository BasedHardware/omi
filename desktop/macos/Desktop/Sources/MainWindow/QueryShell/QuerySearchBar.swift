import OmiTheme
import SwiftUI

/// The always-visible search face — "Search what you've seen and heard…" — shared by Home and the
/// Memory hub's Activity tab. Pure search: the surface below narrows live from every keystroke, so
/// there is no submit and no chat controls. The one chat composer stays inside the answer panel
/// (INV-6); this field never sends.
struct QuerySearchBar: View {
  @Binding var text: String
  var accessibilityID: String = "query-search-field"
  var placeholder: String = RewindSearchMetrics.placeholder
  var focus: FocusState<Bool>.Binding? = nil

  var body: some View {
    searchRow
      .frame(minHeight: QueryShellLayout.barMinHeight)
      .inkGlassPanel(cornerRadius: QueryShellLayout.panelCornerRadius, shadow: .ambient)
  }

  private var searchRow: some View {
    HStack(spacing: QueryShellLayout.heroRowSpacing) {
      Image(systemName: "magnifyingglass")
        .scaledFont(size: QueryShellLayout.heroGlyphSize, weight: .regular)
        .foregroundStyle(Ink.secondary)
      searchField
      if !text.isEmpty {
        Button {
          text = ""
        } label: {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: QueryShellLayout.heroGlyphSize, weight: .regular)
            .foregroundStyle(Ink.secondary)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Clear search")
        .help("Clear the search")
      }
    }
    .padding(.horizontal, QueryShellLayout.barPaddingHorizontal)
  }

  @ViewBuilder
  private var searchField: some View {
    if let focus {
      TextField(placeholder, text: $text)
        .textFieldStyle(.plain)
        .scaledFont(size: QueryShellLayout.queryFontSize, weight: .regular)
        .foregroundStyle(Ink.primary)
        .focused(focus)
        .accessibilityIdentifier(accessibilityID)
    } else {
      TextField(placeholder, text: $text)
        .textFieldStyle(.plain)
        .scaledFont(size: QueryShellLayout.queryFontSize, weight: .regular)
        .foregroundStyle(Ink.primary)
        .accessibilityIdentifier(accessibilityID)
    }
  }
}
