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
  var searchSurface: SearchSurface? = nil
  @FocusState private var internalFocus: Bool
  @State private var isClearHovered = false

  private var isFocused: Bool {
    focus?.wrappedValue ?? internalFocus
  }

  var body: some View {
    searchRow
      .frame(minHeight: QueryShellLayout.barMinHeight)
      .inkGlassPanel(cornerRadius: QueryShellLayout.panelCornerRadius, shadow: .ambient)
      .overlay {
        RoundedRectangle(cornerRadius: QueryShellLayout.panelCornerRadius, style: .continuous)
          .stroke(isFocused ? Ink.primary.opacity(0.28) : Color.clear, lineWidth: 1)
          .allowsHitTesting(false)
      }
      .onChange(of: internalFocus) { _, focused in
        guard focus == nil else { return }
        reportFocus(focused)
      }
      // Typing on the page with nothing focused starts a search here. The bar is not focused ahead
      // of time — no caret, no stroke — until the first key arrives (`StrayTypingRouter`).
      .straysTypingHere(focus ?? $internalFocus)
  }

  private func reportFocus(_ focused: Bool) {
    guard focused, let searchSurface else { return }
    SearchAnalytics.barFocused(surface: searchSurface)
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
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundStyle(Ink.secondary)
            .frame(width: 28, height: 28)
            .background(isClearHovered ? Ink.rowFillHover : Color.clear)
            .clipShape(Circle())
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { isClearHovered = $0 }
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
        .onChange(of: focus.wrappedValue) { _, focused in
          reportFocus(focused)
        }
    } else {
      TextField(placeholder, text: $text)
        .textFieldStyle(.plain)
        .scaledFont(size: QueryShellLayout.queryFontSize, weight: .regular)
        .foregroundStyle(Ink.primary)
        .focused($internalFocus)
        .accessibilityIdentifier(accessibilityID)
    }
  }
}
