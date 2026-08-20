import OmiTheme
import SwiftUI

/// The always-visible search face — "Search what you've seen and heard…" — shared by Home and the
/// Memory hub's Activity tab. Pure search: the surface below narrows live from every keystroke, so
/// there is no submit and no chat controls. The one chat composer stays inside the answer panel
/// (INV-6); this field never sends.
struct QuerySearchBar: View {
  @Binding var text: String
  var accessibilityID: String = "query-search-field"
  var focusClaim: Int = 0

  @FocusState private var isFocused: Bool

  var body: some View {
    HStack(spacing: QueryShellLayout.heroRowSpacing) {
      Image(systemName: "magnifyingglass")
        .scaledFont(size: QueryShellLayout.heroGlyphSize, weight: .regular)
        .foregroundStyle(Ink.secondary)
      TextField(RewindSearchMetrics.placeholder, text: $text)
        .textFieldStyle(.plain)
        .scaledFont(size: QueryShellLayout.queryFontSize, weight: .regular)
        .foregroundStyle(Ink.primary)
        .focused($isFocused)
        .accessibilityIdentifier(accessibilityID)
      if !text.isEmpty {
        Button {
          text = ""
        } label: {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: QueryShellLayout.heroGlyphSize, weight: .regular)
            .foregroundStyle(Ink.secondary)
        }
        .buttonStyle(.plain)
        .help("Clear the search")
      }
    }
    .padding(.horizontal, QueryShellLayout.barPaddingHorizontal)
    .frame(minHeight: QueryShellLayout.barMinHeight)
    .inkGlassPanel(cornerRadius: QueryShellLayout.panelCornerRadius, shadow: .ambient)
    .onAppear {
      if focusClaim > 0 { isFocused = true }
    }
    .onChange(of: focusClaim) { _, _ in isFocused = true }
  }
}
