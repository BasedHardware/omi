//
//  RewindSearchBar.swift — the first of the search surface's two panels: the place you type.
//
//  The query is drawn the way the reference draws it — a tinted capsule around what has been typed,
//  with the live insertion point sitting after it. The capsule is sized from the text
//  (`RewindSearchMetrics.chipWidth`) rather than filling the bar, which is what makes it read as a
//  *chip*: a fixed-width tinted box would just be a text field with a background. With nothing typed
//  there is no chip at all, only the placeholder and the cursor.
//
//  This is the one element on the surface that carries a hue. Everything else — chips, cards,
//  selection — answers in weight, because a second meaning-bearing colour is one more thing to learn.
//
//  **There is no `↵ Search` key hint, because searching is not a thing you commit to.**
//  `RewindViewModel` subscribes to `$searchQuery` and runs `performSearch` 300 ms after you stop
//  typing, so the results under the bar have already narrowed by the time a hand reaches Return. The
//  hint was a button for a job that finished while you were reaching for it — and, since no call site
//  ever passed `onSubmit`, a button that ran an empty closure. Same removal and the same reason as
//  the home composer's (`QueryHeroBar`, 979a1101e1): a key that means nothing is not a key worth
//  labelling.
//

import OmiTheme
import SwiftUI

/// The query bar: a glyph, the query, and what the keyboard can do about it.
///
/// Used both inside Rewind's own top band and, via `panel`, as a free-standing sheet of glass above
/// the results. The bar's furniture is the same either way; only the ground under it changes.
struct RewindSearchBar: View {
  @Binding var query: String
  var placeholder: String = RewindSearchMetrics.placeholder
  /// Whether a search is in flight, so the bar can say so where the count would otherwise sit.
  var isSearching: Bool = false
  /// What the search found, already phrased. `nil` when nothing has been asked and there is no
  /// verdict to report — "No results" over an untouched bar answers a search nobody ran.
  var countLabel: String?
  /// The bar owns the keyboard focus for the whole surface, so the page hands its own focus state in
  /// rather than keeping a second one that could disagree.
  var focus: FocusState<Bool>.Binding
  var onClear: () -> Void = {}

  private var isTyped: Bool { !query.isEmpty }

  var body: some View {
    HStack(spacing: 12) {
      Image(systemName: "clock.arrow.circlepath")
        .font(.system(size: RewindSearchLayout.glyphSize * 0.82, weight: .regular))
        .foregroundStyle(Ink.primary)
        .frame(width: RewindSearchLayout.glyphSize, height: RewindSearchLayout.glyphSize)
        .accessibilityHidden(true)

      queryField

      Spacer(minLength: 12)

      if isSearching {
        ProgressView()
          .progressViewStyle(.circular)
          .controlSize(.small)
      } else if let countLabel {
        Text(countLabel)
          .inkStyle(.statusLabel, color: Ink.secondary)
          .fixedSize()
      }

      if isTyped {
        Button(action: onClear) {
          Image(systemName: "xmark.circle.fill")
            .font(.system(size: 13, weight: .regular))
            .foregroundStyle(Ink.secondary)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(Self.clearActionName)
        .accessibilityLabel(Text(Self.clearActionName))
      }
    }
    .frame(height: RewindSearchLayout.barHeight)
  }

  /// What clearing is called wherever it is named in words rather than in a glyph.
  static let clearActionName = "Clear the search"

  /// What the action is called wherever it is named in words. It names **both** halves on purpose:
  /// a user who has only ever searched screenshots has no reason to expect this to know what was on
  /// screen *and* what a window was called.
  static let searchActionName = "Search this Mac's screen history"

  // MARK: - The field

  private var queryField: some View {
    ZStack(alignment: .leading) {
      if isTyped {
        Capsule(style: .continuous)
          .fill(RewindSearchInk.queryChipFill)
          .overlay(
            Capsule(style: .continuous)
              .strokeBorder(RewindSearchInk.queryChipStroke, lineWidth: 1)
          )
          .frame(
            width: RewindSearchMetrics.chipWidth(
              for: query, available: RewindSearchLayout.queryFieldWidth),
            height: RewindSearchMetrics.queryLineHeight
          )
      }

      HStack(spacing: 6) {
        if isTyped {
          Image(systemName: "magnifyingglass")
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(RewindSearchInk.queryChipGlyph)
            .accessibilityHidden(true)
        }
        TextField(placeholder, text: $query)
          .textFieldStyle(.plain)
          .font(.system(size: RewindSearchMetrics.queryFontSize, weight: .semibold))
          .foregroundStyle(Ink.primary)
          .focused(focus)
          .straysTypingHere(focus)
          .accessibilityLabel(Text(Self.searchActionName))
          .onChange(of: focus.wrappedValue) { _, focused in
            guard focused else { return }
            SearchAnalytics.barFocused(surface: .rewind)
          }
      }
      .padding(.leading, isTyped ? RewindSearchMetrics.chipPaddingHorizontal : 0)
    }
    // The field's line box, with room over the ascenders. A row shorter than the face it is set in
    // clips the top of the placeholder.
    .frame(height: RewindSearchMetrics.queryLineHeight)
    .omiAnimation(.easeOut(duration: InkMotion.press), value: isTyped)
  }

}

extension RewindSearchBar {
  /// The bar as a free-standing sheet of glass — the first of the surface's two objects.
  ///
  /// The panel is what makes the arrangement read as two things rather than one: it carries its own
  /// corner and its own ambient shadow, and `RewindSearchLayout.panelGap` of real air sits under it.
  var panel: some View {
    self
      .padding(.horizontal, RewindSearchLayout.panelPaddingHorizontal)
      .frame(width: RewindSearchLayout.panelWidth, alignment: .leading)
      .inkGlassPanel(cornerRadius: RewindSearchLayout.panelCornerRadius, shadow: .ambient)
      .contentShape(
        RoundedRectangle(cornerRadius: RewindSearchLayout.panelCornerRadius, style: .continuous))
  }
}

#if canImport(PreviewsMacros)
  private struct RewindSearchBarPreview: View {
    @FocusState private var focused: Bool
    @State private var empty = ""
    @State private var typed = "claude"

    var body: some View {
      VStack(spacing: RewindSearchLayout.panelGap) {
        RewindSearchBar(query: $empty, focus: $focused).panel
        RewindSearchBar(
          query: $typed, isSearching: false, countLabel: "48 results", focus: $focused
        ).panel
      }
      .padding(RewindSearchLayout.shadowMargin)
    }
  }

  #Preview {
    RewindSearchBarPreview()
      .frame(width: RewindSearchLayout.surfaceWidth)
      .background(Ink.surface)
  }
#endif
