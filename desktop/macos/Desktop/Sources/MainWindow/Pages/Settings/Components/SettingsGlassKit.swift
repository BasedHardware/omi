//
//  SettingsGlassKit.swift — the shared chrome every Settings, Apps and Permissions surface wears.
//
//  Settings is the largest literal-driven surface in the app: thirty-odd files, a thousand colour
//  call sites, and until now a card shape spelled out longhand wherever one was wanted. The glass
//  design system (`Ink`, `InkType`, `InkGlass`) supplies the *vocabulary* — colour, type, motion —
//  but not the two composites this surface repeats on every pane: a titled group of rows on a card,
//  and the row itself. Those live here, once, so thirty files cannot drift into thirty layouts.
//
//  The metrics are the ones the source app's settings kit was measured at, and they are stated as
//  values rather than as literals inside a view for the same reason `InkGlass` states the glass that
//  way: a number that appears in one place can be changed; a number that appears in forty cannot.
//
//  **Two rungs, not three.** These surfaces are hosted on glass, and `Ink.tertiary` may never go on
//  glass (see its doc comment — it is arithmetic, not taste). Every secondary run here is
//  `Ink.secondary`, including the ones a three-rung ladder would have set fainter.
//
//  Brand: system semantics and neutrals only (INV-UI-1). The single accent is `Ink.accent`, and it is
//  spent on selection state — never on a filled button, which inverts the label ladder instead.
//

import AppKit
import OmiTheme
import SwiftUI

// MARK: - Metrics

/// The metrics every Settings pane shares.
///
/// A separate namespace from `InkLayout`, which describes the *onboarding card* — a reading column
/// centred on a 560 pt panel with 34 pt margins. A settings pane is a list, not a reading column, and
/// it is denser than anything `InkLayout` sizes: these values come from the measured settings kit and
/// they would be wrong for a hero card, which is exactly why they are not mixed in with it.
enum SettingsGlassMetrics {
  /// Pane gutters. The horizontal value is the one rows are inset by; the vertical pair is
  /// deliberately asymmetric — a pane scrolls, so the foot needs more room than the head.
  static let paneHorizontalPadding: CGFloat = 16
  static let paneTopPadding: CGFloat = 12
  static let paneBottomPadding: CGFloat = 18

  /// Between two sections. The one vertical gap on a pane that is allowed to be large.
  static let sectionSpacing: CGFloat = 14
  /// Between a section's title and its card.
  static let sectionTitleSpacing: CGFloat = 6
  /// Between two rows *inside* a card. Nearly nothing: the hairline separates them, not the gap.
  static let rowSpacing: CGFloat = 2

  static let rowVerticalPadding: CGFloat = 7
  static let rowHorizontalPadding: CGFloat = 10
  /// Between the icon tile and the copy beside it.
  static let rowContentSpacing: CGFloat = 11

  /// The rounded square an icon sits in, and its corner.
  static let iconTile: CGFloat = 26
  static let iconTileRadius: CGFloat = 7

  /// A card inside a pane. **Not** `InkGlass.cornerRadius` (22): that is the corner of the *panel*,
  /// the glass itself, and a card drawn inside it at the same radius reads as a second pane rather
  /// than as content. One value for the glass, one for what sits on it.
  static let cardRadius: CGFloat = 10
  /// A control inside a row: a field, a small button, a badge.
  static let controlRadius: CGFloat = 7
  /// A pill: a key hint, a status chip.
  static let pillRadius: CGFloat = 4

  /// The leading inset of the hairline between two rows, so it starts where the copy does rather
  /// than running under the icon tile. Derived, not typed twice.
  static var rowDividerInset: CGFloat { rowHorizontalPadding + iconTile + rowContentSpacing }
}

// MARK: - The one colour the glass palette does not carry

/// The states these surfaces need that `Ink` has no name for.
///
/// `Ink` is deliberately small: one accent, one error, one live indicator. Settings has a fourth
/// state those three cannot express — *attention, but nothing is broken*: a trial with an hour left,
/// a permission the user has not answered yet, a plan about to lapse. Colouring it `Ink.errorRed`
/// cries wolf, and colouring it `Ink.secondary` says nothing at all.
///
/// It follows the same construction rule as every colour in `Ink`, which is what makes it part of the
/// same palette rather than a literal smuggled in beside one: a **named system colour**, so it tracks
/// the appearance and brightens under Increase Contrast, and never a hand-mixed hue. It lives here
/// rather than in `Ink` because it is a Settings vocabulary word — nothing on the onboarding glass
/// has a caution state — and `Ink` earns its authority by staying the smaller list.
enum SettingsInk {
  /// Attention without failure. Distinct from `Ink.errorRed`, which is reserved for the thing that
  /// actually went wrong.
  static let notice = Color(nsColor: .systemOrange)
}

// MARK: - Row furniture

/// The rounded tile an icon sits in at the head of a row.
///
/// A tile rather than a bare glyph: rows carry SF Symbols of wildly different optical weight
/// (`bell`, `creditcard`, `wrench.and.screwdriver`), and a fixed 26 pt ground is what makes a column
/// of them line up instead of shimmering.
struct SettingsIconTile: View {
  let symbol: String
  var tint: Color = Ink.primary

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: SettingsGlassMetrics.iconTileRadius, style: .continuous)
  }

  var body: some View {
    shape
      .fill(Ink.rowFill)
      .overlay(shape.strokeBorder(Ink.separator, lineWidth: 1))
      .overlay(
        Image(systemName: symbol)
          .font(.system(size: 12, weight: .medium))
          .foregroundStyle(tint)
      )
      .frame(width: SettingsGlassMetrics.iconTile, height: SettingsGlassMetrics.iconTile)
  }
}

/// A printed keyboard chord: monospaced, in a faint pill, and never a control.
///
/// It is `accessibilityLabel`led rather than left as bare glyphs because "⌘ ⇧ O" read aloud
/// character by character is noise.
struct SettingsKeyHint: View {
  let text: String

  var body: some View {
    Text(text)
      .font(.system(size: 10, weight: .semibold, design: .monospaced))
      .foregroundStyle(Ink.secondary)
      .padding(.horizontal, 5)
      .padding(.vertical, 2)
      .background(
        RoundedRectangle(cornerRadius: SettingsGlassMetrics.pillRadius, style: .continuous)
          .fill(Ink.wash)
      )
      .fixedSize()
      .accessibilityLabel(Text("Keyboard shortcut \(text)"))
  }
}

/// The hairline between two rows in a card, inset so it starts where the copy does rather than
/// running under the icon tile.
///
/// It is `GlassSeparator` (`GlassContentChrome.swift`) with an inset, and **not** a `Divider`,
/// because a `Divider` in this design system cannot be given the system's colour: the twenty-eight
/// rules that used to be spelled `Divider().background(Ink.hairline)` were all silently drawing the
/// untinted system separator. `.background` paints *behind* the line a `Divider` draws rather than
/// through it, so the tint never reached a pixel while the call site read, at a glance, like a
/// deliberate choice. A `Rectangle` filled with `Ink.separator` has no such gap between what it says
/// and what it draws, which is the whole reason to have one shared word for a rule.
struct SettingsRowDivider: View {
  var body: some View {
    GlassSeparator()
      .padding(.leading, SettingsGlassMetrics.rowDividerInset)
  }
}

// MARK: - The one row shape

/// An icon tile, a title, a smaller secondary subtitle, an optional printed chord, and a control.
///
/// Everything a pane needs to vary is a parameter rather than a second row type. The row draws **no
/// background of its own** — `SettingsGlassSection` owns the card, and a row that also filled would
/// be a second ground stacked on the first.
struct SettingsGlassRow<Control: View>: View {
  let icon: String
  let title: String
  var subtitle: String?
  /// A chord printed just before the control, e.g. `⌘ ⇧ O`.
  var shortcutHint: String?
  var isEnabled: Bool = true
  @ViewBuilder var control: () -> Control

  var body: some View {
    HStack(alignment: .center, spacing: SettingsGlassMetrics.rowContentSpacing) {
      SettingsIconTile(symbol: icon)
      VStack(alignment: .leading, spacing: 2) {
        Text(title)
          .font(.system(size: 13, weight: .medium))
          .foregroundStyle(Ink.primary)
        if let subtitle, !subtitle.isEmpty {
          Text(subtitle)
            .font(.system(size: 11))
            .foregroundStyle(Ink.secondary)
            // The row wraps; it never truncates. A `Text` given less height than it needs ends in an
            // ellipsis, which is copy disappearing rather than a layout failing.
            .fixedSize(horizontal: false, vertical: true)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)

      if let shortcutHint {
        SettingsKeyHint(text: shortcutHint)
      }
      control()
    }
    .padding(.vertical, SettingsGlassMetrics.rowVerticalPadding)
    .padding(.horizontal, SettingsGlassMetrics.rowHorizontalPadding)
    .opacity(isEnabled ? 1 : 0.55)
    .disabled(!isEnabled)
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}

extension SettingsGlassRow where Control == EmptyView {
  init(
    icon: String, title: String, subtitle: String? = nil, shortcutHint: String? = nil,
    isEnabled: Bool = true
  ) {
    self.init(
      icon: icon, title: title, subtitle: subtitle, shortcutHint: shortcutHint,
      isEnabled: isEnabled, control: { EmptyView() })
  }
}

// MARK: - Grouping

/// A titled group on a card: an 11 pt semibold heading over an `Ink.rowFill` card with a
/// `Ink.separator` hairline, and an optional footnote under it.
///
/// This is the shape a macOS settings pane uses, and it is the reason the rows themselves draw no
/// background: the card is the ground, once, for however many rows sit on it.
struct SettingsGlassSection<Content: View>: View {
  var title: String?
  var footnote: String?
  @ViewBuilder var content: () -> Content

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
  }

  var body: some View {
    VStack(alignment: .leading, spacing: SettingsGlassMetrics.sectionTitleSpacing) {
      if let title {
        Text(title)
          .font(.system(size: 11, weight: .semibold))
          // `secondary` and not the glance rung: this is on glass, which carries two rungs.
          .foregroundStyle(Ink.secondary)
          .textCase(nil)
          .padding(.horizontal, 4)
      }
      VStack(spacing: 0) { content() }
        .background(shape.fill(Ink.rowFill))
        .overlay(shape.strokeBorder(Ink.separator, lineWidth: 1))
      if let footnote {
        Text(footnote)
          .font(.system(size: 11))
          .foregroundStyle(Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.horizontal, 4)
          .padding(.top, 2)
      }
    }
  }
}

// MARK: - Surfaces

extension View {
  /// The card a settings block sits on: `Ink.rowFill` behind a `Ink.separator` hairline, cut to the
  /// card corner.
  ///
  /// Distinct from `inkGlassPanel(…)`, which is *the glass* — the material, the scrim and the 22 pt
  /// corner. Nothing inside a pane may wear that: the window already does, and a second piece of
  /// glass inside the first is the "two grounds" failure `InkGlass` exists to prevent.
  func settingsGlassCard(radius: CGFloat = SettingsGlassMetrics.cardRadius) -> some View {
    let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
    return
      background(shape.fill(Ink.rowFill))
      .overlay(shape.strokeBorder(Ink.separator, lineWidth: 1))
  }

  /// A control's own ground inside a row — a text field, a stepper, a small well.
  ///
  /// Fainter than a card and outlined in `Ink.hairline` rather than `Ink.separator`, because this is
  /// the edge of something the user is meant to press or type into: a rule between blocks and the
  /// outline of a control are different jobs and `Ink` keeps two values for them.
  func settingsGlassWell(radius: CGFloat = SettingsGlassMetrics.controlRadius) -> some View {
    let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
    return
      background(shape.fill(Ink.wash))
      .overlay(shape.strokeBorder(Ink.hairline, lineWidth: 1))
  }
}

/// The scroll container a pane's content sits in, so paddings cannot drift between panes.
struct SettingsGlassPaneScroll<Content: View>: View {
  @ViewBuilder var content: () -> Content

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: SettingsGlassMetrics.sectionSpacing) {
        content()
      }
      .padding(.horizontal, SettingsGlassMetrics.paneHorizontalPadding)
      .padding(.top, SettingsGlassMetrics.paneTopPadding)
      .padding(.bottom, SettingsGlassMetrics.paneBottomPadding)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }
}

// MARK: - Status

/// A one-word state chip: `Granted`, `Beta`, `Connected`.
///
/// Its tint is the whole message, so it takes a colour rather than a boolean — but it composes the
/// ground from that colour instead of taking a second one, because a chip whose fill and label were
/// chosen independently is a contrast pair nobody keeps true.
///
/// **The tint is the dot, not the word.** Setting the *label* in the tint over a wash of the same
/// tint was the obvious reading of "compose the ground from the colour", and on this light panel it
/// does not survive a measurement: `systemGreen` is a light hue (relative luminance ≈ 0.45), so
/// `Granted` in green over 14% green measures about **1.6:1** — the word was there and could not be
/// read, which is the whole job of a status chip. `systemOrange` lands at ≈2.2:1 and `systemRed` at
/// ≈3.5:1, so every state this chip has was under AA and the healthy one was the worst.
///
/// Darkening the hue is not available: these are *named system colours* on purpose (see `Ink`), and
/// a hand-mixed dark green is exactly the hand-mixed hue this palette exists to keep out. So the
/// colour moves to a 6 pt disc — a graphical object, which WCAG asks 3:1 of and which `systemGreen`
/// clears against this ground — and the word takes `Ink.primary`. The state still reads as colour at
/// a glance, and it also reads as words, which it did not before.
struct SettingsStatusChip: View {
  let text: String
  var tint: Color = Ink.secondary

  var body: some View {
    HStack(spacing: 5) {
      Circle()
        .fill(tint)
        .frame(width: 6, height: 6)
      Text(text)
        .font(.system(size: 11, weight: .medium))
        .foregroundStyle(Ink.primary)
    }
    .padding(.horizontal, 8)
    .padding(.vertical, 3)
    .background(
      Capsule(style: .continuous).fill(tint.opacity(0.16))
    )
    .fixedSize()
    .accessibilityElement(children: .combine)
    .accessibilityLabel(Text(text))
  }
}
