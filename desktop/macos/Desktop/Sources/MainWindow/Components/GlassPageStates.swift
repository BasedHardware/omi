import OmiTheme
import SwiftUI

// MARK: - Page states

/// The three states a page body is in before it has rows to show: loading, failed, and empty.
///
/// Each used to be drawn per page, and the pages disagreed about everything a reader compares across
/// them: glyph sizes of 28, 32, 36, 40 and 48; a heading-weight title on one page and a medium one on
/// the next; three different error glyphs; and seven styles of "Try Again". These are the one
/// version. A page that needs a state picks one of these and a `placement`; it does not draw its own.
enum GlassPageState {
  /// One glyph size for every empty and error state.
  static let glyphSize: CGFloat = OmiType.title
  /// The one error glyph. An outline, not the filled triangle: a failed load is not an alarm.
  static let errorSymbol = "exclamationmark.triangle"
  /// The one retry label (see ux-contract.md §8, Words).
  static let retryTitle = "Try Again"
  /// The one retry style: an error state is a recoverable pause, so its action is secondary.
  @MainActor static var retryStyle: OmiButtonStyle { OmiButtonStyle(.secondary, size: .compact) }
}

/// Where a state sits, which decides how much room it claims.
enum GlassPageStatePlacement: Equatable {
  /// The whole page body or a sidebar column: fill what is offered and centre in it.
  case page
  /// Inside a `ScrollView`, which offers no height to fill: fill the width and keep a floor so the
  /// state does not collapse to its text.
  case scrolling
  /// Inside a panel that sizes itself (`TransparentWindowStatusPanel`): take only the intrinsic size,
  /// or the panel grows to the window.
  case panel

  /// The minimum height the state keeps, or nil when it takes its intrinsic height.
  var minHeight: CGFloat? {
    self == .scrolling ? QueryShellLayout.minimumBodyHeight : nil
  }

  /// Whether the state expands to fill the height it is offered.
  var fillsHeight: Bool { self == .page }

  /// The breathing room around the state. A panel already pads its content.
  var padding: CGFloat { self == .panel ? 0 : OmiSpacing.xxl }
}

private struct GlassPageStatePlacementModifier: ViewModifier {
  let placement: GlassPageStatePlacement

  func body(content: Content) -> some View {
    content
      .padding(placement.padding)
      .frame(
        maxWidth: placement == .panel ? nil : .infinity,
        minHeight: placement.minHeight,
        maxHeight: placement.fillsHeight ? .infinity : nil
      )
  }
}

/// The glyph, title and sentence every state shares, so the three states cannot drift apart.
private struct GlassPageStateText: View {
  let systemImage: String
  let title: String
  let message: String?

  var body: some View {
    Image(systemName: systemImage)
      .scaledFont(size: GlassPageState.glyphSize, weight: .light)
      // `secondary`, not a fainter step: on glass there is no third rung to spend here.
      .foregroundStyle(Ink.secondary)
      .accessibilityHidden(true)
    Text(title)
      .scaledFont(size: OmiType.subheading, weight: .semibold)
      .foregroundStyle(Ink.primary)
      .multilineTextAlignment(.center)
    if let message {
      Text(message)
        .scaledFont(size: OmiType.body)
        .foregroundStyle(Ink.secondary)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)
    }
  }
}

/// "There is nothing here yet", or "nothing matches". Actions, when there are any, are
/// `OmiButtonStyle(.secondary, size: .compact)` buttons ("Clear Search") or one `.primary` when the
/// action is how the page gets its first row ("New Memory").
struct GlassEmptyState<Actions: View>: View {
  let systemImage: String
  let title: String
  var message: String?
  var placement: GlassPageStatePlacement = .page
  @ViewBuilder var actions: () -> Actions

  var body: some View {
    VStack(spacing: OmiSpacing.md) {
      GlassPageStateText(systemImage: systemImage, title: title, message: message)
      HStack(spacing: OmiSpacing.sm) {
        actions()
      }
      .padding(.top, OmiSpacing.xs)
    }
    .modifier(GlassPageStatePlacementModifier(placement: placement))
  }
}

extension GlassEmptyState where Actions == EmptyView {
  init(
    systemImage: String,
    title: String,
    message: String? = nil,
    placement: GlassPageStatePlacement = .page
  ) {
    self.init(
      systemImage: systemImage, title: title, message: message, placement: placement,
      actions: { EmptyView() })
  }
}

/// A load that failed and can be tried again. One glyph, one title rung, one "Try Again".
struct GlassErrorState: View {
  let title: String
  var message: String?
  var placement: GlassPageStatePlacement = .page
  /// Carried onto the retry button for automation and UI tests.
  var retryAccessibilityIdentifier: String?
  let retry: () -> Void

  var body: some View {
    VStack(spacing: OmiSpacing.md) {
      GlassPageStateText(systemImage: GlassPageState.errorSymbol, title: title, message: message)
      Button(GlassPageState.retryTitle, action: retry)
        .buttonStyle(GlassPageState.retryStyle)
        .accessibilityIdentifier(retryAccessibilityIdentifier ?? "glass-error-retry")
        .padding(.top, OmiSpacing.xs)
    }
    .modifier(GlassPageStatePlacementModifier(placement: placement))
  }
}

/// A page's first load. One spinner size and one text style.
///
/// Spinner sizes across the app follow one convention: a page-state spinner is this view at the
/// regular control size; every inline spinner (in a button, row, toolbar or field) is
/// `ProgressView().controlSize(.small)`. Never `.scaleEffect` a `ProgressView` — it blurs the
/// rasterised arcs and leaves the layout frame at the unscaled size. A skeleton is allowed where
/// the page already draws one (Apps' shimmer grid), since it previews the layout that will land.
struct GlassLoadingState: View {
  let label: String
  var placement: GlassPageStatePlacement = .page

  var body: some View {
    VStack(spacing: OmiSpacing.md) {
      ProgressView()
        .controlSize(.regular)
      Text(label)
        .scaledFont(size: OmiType.body)
        .foregroundStyle(Ink.secondary)
        .multilineTextAlignment(.center)
    }
    .accessibilityElement(children: .combine)
    .modifier(GlassPageStatePlacementModifier(placement: placement))
  }
}
