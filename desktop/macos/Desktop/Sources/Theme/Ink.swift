//
//  Ink.swift — the glass design system's shared visual vocabulary.
//
//  Ported from Context for Claude's `Ink.swift`. Every colour here is a macOS semantic colour or a
//  fixed alpha on one, and the single accent is `NSColor.systemBlue` — a *named* system colour,
//  chosen here rather than read off the machine. No hue is hand-mixed, so there is exactly one
//  palette in this system and it composites correctly on any ground.
//
//  Roles are exposed as whole styles rather than loose numbers because the character of the type
//  lives in the tracking as much as the point size — a caller that hand-assembles
//  `.font(.openRunde(34, .semiBold))` and forgets `.tracking(-1.19)` has quietly shipped a different
//  product. `Text.inkStyle(_:)` (see `InkType.swift`) makes both mistakes unavailable.
//
//  Brand: system semantics and neutrals only, and INV-UI-1's banned hue nowhere — note that the
//  accent is a value *this file picks*, not the one the machine reports. See `Ink.accent`.
//
//  Companion files: `InkType.swift` (faces, roles, tracking), `InkGlass.swift` (the panel itself),
//  `WindowGlass.swift` (the `NSWindow` properties the panel needs to reach the screen).
//

import AppKit
import SwiftUI

// MARK: - Colour

/// The whole palette. Every role is a system semantic colour or a fixed alpha on one — a colour
/// literal at a call site that means to be part of this system is a bug.
package enum Ink {
  // Surfaces.

  /// Every surface this system draws: the glass panel's scrim, an opaque sheet's ground.
  ///
  /// `controlBackgroundColor` rather than `windowBackgroundColor`: this is the ground *content* sits
  /// on, which is white in Light and near-black in Dark — a sheet, in both appearances. On glass it
  /// is always resolved inside the pinned light appearance (see `InkGlass`).
  package static let surface = Color(nsColor: .controlBackgroundColor)

  // Type, in three steps and no fourth. Which step a run gets is decided by what the reader has to
  // do with it, not by how deep it sits in a stack.
  //
  // The lower two steps are an alpha on `labelColor` and *not* `secondaryLabelColor` /
  // `tertiaryLabelColor`, which is a legibility decision with measurements behind it. The system's
  // own steps are 50% and 26% black in Light, tuned for dense system chrome — an inspector row, a
  // table cell, a menu — where the reader glances at a word beside its subject. Composited over
  // `surface` they measure **3.95:1** and **1.88:1**, so the step that carries whole sentences fails
  // WCAG AA for body text (4.5:1) and the glance step is barely a shade of grey.
  //
  // Alpha on `labelColor` keeps every property this system relies on: `labelColor` is near-black in
  // Light and near-white in Dark, so one value darkens a light sheet and lightens a dark one — no
  // hardcoded grey, no second set of values for Dark, and it still composites correctly over a
  // vibrant material.
  //
  // **There are three rungs, but glass only gets two.** `primary` and `secondary` may go on any
  // surface; `tertiary` may only go on an *opaque* one. This is not a style preference — it is
  // arithmetic, and it is the single thing that decides how see-through every panel is. See
  // `tertiary`.

  /// Headlines, row copy, the primary button's fill, the granted checkbox — and any state with
  /// something to do about it.
  package static let primary = Color(nsColor: .labelColor)

  /// A sentence someone reads: prose, a status line, an upload note — **and, on glass, everything
  /// that is not `primary`.**
  ///
  /// `labelColor` at 0.80 — 7.8:1 over `surface` in Light and 8.3:1 in Dark. AAA (7:1), which is the
  /// right target for the only step that carries whole sentences.
  ///
  /// On glass `surface` is no longer the whole ground: it is `InkGlass.scrim` of `surface` over a
  /// light-pinned blurred desktop. Because the glass pins its appearance, that ground does not depend
  /// on the machine's. **This is the bottom rung on glass, so it is the rung every bound on that
  /// ground is evaluated at**, and it is therefore measured rather than assumed: through the real
  /// material over the two desktops that can exist, it lands at **5.89:1 over a solid black desktop
  /// and 7.66:1 over a solid white one**, in both system appearances.
  ///
  /// **AA is no longer what holds the ground up, though.** This rung cleared 4.5:1 at a much thinner
  /// scrim — it did, at 4.58:1, on the panel that shipped unreadable over a browser window. A contrast
  /// ratio is defined against a *uniform* background, and the ground under this panel is a blurred
  /// picture of another app. What sets the scrim now is `InkGlass.interferenceRatio`, evaluated at this
  /// rung because it is the faintest one here.
  ///
  /// It still cannot be thinned, and the reason is sharper than it was: thinning it does not spend
  /// margin this rung has, it pushes the *ground* up for every surface, because the ground is solved
  /// for whatever sits at the bottom. It is deliberately not *thickened* either — contrast this rung
  /// does not need is contrast the panel paid for in opacity, which is exactly what an opaque-looking
  /// panel is made of.
  package static let secondary = Color(nsColor: .labelColor).opacity(0.80)

  /// A word someone glances at: `Granted`, `Quit`, `Sign out`. Never a whole sentence — **and never
  /// on glass.**
  ///
  /// `labelColor` at 0.68 — 5.2:1 over `surface` in Light, 6.3:1 in Dark, which is a comfortable
  /// glance step on an *opaque* sheet.
  ///
  /// **The rule "never on glass" was arrived at the hard way, and the arithmetic behind it has since
  /// moved.** The ground under dark type has to stay light enough for the *faintest* rung set on it, so
  /// whichever rung is at the bottom is what decides the ground. With this rung on the panel the floor
  /// was a ground of ≈203/255 and 17% passthrough — pale paper — and three separate retunes of the
  /// material and the scrim moved it by fourteen levels out of 255, correctly reported each time as no
  /// change at all. Dropping it bought twice the desktop at the same 4.5:1.
  ///
  /// **That bargain is smaller now, and the rule has to stand on something else.** The scrim is no
  /// longer set by AA on the bottom rung but by `InkGlass.interferenceRatio` — how strongly the panel
  /// shows the app behind it against how strongly it shows its own words — so "this rung costs half the
  /// desktop" is no longer the argument. What holds the rule is the plainer pair of facts: at today's
  /// ground this rung measures **4.34:1**, under AA, so as written it may not carry type here at all;
  /// and darkening it to the **0.694** that would just clear AA puts it **7.5 L\*** from `secondary` on
  /// this ground, inside the 8 L\* the rungs are held apart by. A third step that close to the second is
  /// not a ladder, it is the same colour twice with an extra token to keep true.
  ///
  /// If the ladder is ever revisited, revisit it deliberately and with the interference bound in hand —
  /// do not reintroduce this rung by noticing that the panel got lighter.
  ///
  /// So on a glass surface, promote to `secondary`. A run that was `tertiary` because it is a sentence
  /// rather than a glance word was on the wrong rung anyway; one that was genuinely a glance word
  /// loses a step of hierarchy, which is the price of the panel, paid deliberately.
  package static let tertiary = Color(nsColor: .labelColor).opacity(0.68)

  // Edges.

  /// A rule between blocks. A menu surface uses `Divider()` instead, which draws this itself.
  package static let separator = Color(nsColor: .separatorColor)

  /// The edge of something you are meant to press: the secondary button, the empty checkbox.
  /// `separator` is right for a rule and too faint for a control's outline.
  package static let hairline = Color(nsColor: .labelColor).opacity(0.22)

  /// The edge of a *panel*, which is a different job and a much fainter one.
  ///
  /// `hairline` outlines a control, where the border is the affordance. A floating glass panel is
  /// defined by its brightness and its shadow; at 0.22 the outline is the loudest thing on the surface
  /// and the panel reads as a drawn box rather than as a piece of glass. The value lives beside its
  /// sibling so the two cannot be confused at a call site. See `InkGlass.edgeAlpha`, which is this
  /// value.
  package static let glassEdge = Color(nsColor: .labelColor).opacity(InkGlass.edgeAlpha)

  /// The one accent, spent on the one thing that is actionable and is not already a button.
  ///
  /// `systemBlue`, and deliberately **not** `NSColor.controlAccentColor`. The accent the user picked
  /// in System Settings was the obvious choice and it is the wrong one: macOS offers the one hue
  /// INV-UI-1 bans as a system accent, so on such a machine every selection ring, checkbox, toggle and
  /// link in this app renders off-brand (`product/invariants/brand-ui.md`). Nothing here can fix
  /// that at the call site, because the hue is not knowable here; the only fix is to stop reading it.
  /// A colour that is on brand on most machines and off brand on the rest is not a palette, it is a
  /// coin flip — and a rendered-pixel check cannot catch it either, because every machine this is
  /// developed on reports blue.
  ///
  /// It stays a *named system colour* rather than a literal, so it still tracks the appearance and
  /// still brightens under Increase Contrast — everything `controlAccentColor` was picked for except
  /// the one property that made it unshippable.
  package static let accent = Color(nsColor: .systemBlue)

  /// The error colour: the only place the app ever raises its voice.
  package static let errorRed = Color(nsColor: .systemRed)

  /// The live indicator. "On" has to read as on at 7 pt, and green is the only colour that says it
  /// without a label.
  package static let listeningGreen = Color(nsColor: .systemGreen)

  // Fills. Alpha on `labelColor` rather than a named fill colour, because these have to composite
  // correctly over both an opaque sheet and a vibrant material: a wash that darkens in Light and
  // lightens in Dark does, and a fixed grey does not.

  /// Row fill on a card surface. A menu surface has no row fill at all — a real macOS menu does not
  /// fill its rows.
  package static let rowFill = Color(nsColor: .labelColor).opacity(0.045)

  /// The same row under the pointer. A tappable row has to say so, and macOS has no other affordance
  /// for it.
  package static let rowFillHover = Color(nsColor: .labelColor).opacity(0.085)

  /// A *menu* row under the pointer. Fainter than `rowFillHover` and over nothing at rest: a popover's
  /// material is already separating the panel from the window, so anything heavier reads as a second,
  /// competing background.
  ///
  /// Deliberately still `tertiaryLabelColor` and not the ladder's `tertiary`: this is a fill, it is
  /// meant to be barely there, and the legibility reason the type ladder moved does not apply to
  /// something nobody reads.
  package static let rowHover = Color(nsColor: .tertiaryLabelColor).opacity(0.12)

  /// The pressed state of anything with no fill of its own.
  package static let wash = Color(nsColor: .labelColor).opacity(0.06)

  /// An overexposure composited in `plusLighter`.
  ///
  /// Plain white and not `surface`: `plusLighter` only ever adds, so the exit has to be the brightest
  /// thing available or there is nothing to burn out to — over a dark sheet, adding a dark grey is
  /// invisible. White is also the neutral INV-UI-1 asks for.
  package static let glow = Color.white

  // AppKit twins, for the layers SwiftUI cannot reach. `NSColor` is `Sendable`, so these are plain
  // static values.

  package static let nsSurface = NSColor.controlBackgroundColor
  package static let nsPrimary = NSColor.labelColor

  /// `nsPrimary` resolved against the glass's own pinned appearance.
  ///
  /// The composers embed an `NSTextView`, which paints its `textColor` against the *view's*
  /// `effectiveAppearance` — not the SwiftUI `colorScheme` the glass pins. `WindowGlass.wear` pins the
  /// window for exactly this reason, but `DesktopHomeView.enforceMainWindowMinimumSize` still stamps
  /// `.darkAqua` back onto every window whose title starts with "omi", so a composer cannot rely on
  /// winning that race. Handing the dynamic `labelColor` straight to the text view is how one ends up
  /// drawing white type on the light panel: unreadable, and the reader's own words are the last run of
  /// text in the app that can afford to disappear. Resolved up front, the caret and the typed text
  /// stay near-black on the light well either way.
  package static var nsPrimaryOnGlass: NSColor {
    var resolved = nsPrimary
    InkGlass.appearance.performAsCurrentDrawingAppearance {
      resolved = nsPrimary.usingColorSpace(.sRGB) ?? resolved
    }
    return resolved
  }
  // There is deliberately no `nsAccent`. An AppKit twin nothing uses is a second definition of the
  // accent waiting to drift from the first, and the accent is exactly the token a design system is
  // most often bitten by having two opinions about. AppKit callers that genuinely need it can say
  // `NSColor(Ink.accent)`.
}

// MARK: - Layout

package enum InkLayout {
  /// The reading column: a headline and the sentences under it, centred on the card.
  ///
  /// 488 pt is the width left inside a 560 pt card after the page padding, and it is also the measure
  /// `prose` was sized against — at 17 pt that is a little under 80 characters a line, which is the top
  /// of the range a paragraph stays readable across. Wider is not more generous here; it is a longer
  /// distance for the eye to travel back along.
  package static let contentMaxWidth: CGFloat = 488

  /// The list column: a left-aligned card of rows.
  ///
  /// Wider than the reading column, and this is what pays for the larger type. A row is not a
  /// paragraph — it is a sentence with a checkbox before it and a status word after it, and those two
  /// fixtures take ~116 pt out of the row before the sentence starts. Nothing about the measure
  /// argument applies to a list, so the list takes the width the reading column deliberately does not.
  ///
  /// 560 is the card's own width — the reading column plus both gutters — and it is also as wide as
  /// the column should go: 560 plus its padding leaves 80 pt of glass either side, and content that
  /// runs closer than that to a rounded edge reads as content that did not fit.
  package static let permissionsMaxWidth: CGFloat = 560

  package static let pagePaddingHorizontal: CGFloat = 36

  /// The margin between the copy and the top and bottom edges of the glass. Deliberately *not* a place
  /// to find height for bigger type: it is the only thing keeping a 34 pt headline off a rounded
  /// corner.
  package static let pagePaddingVertical: CGFloat = 34

  /// The vertical rhythm. Pick from this ladder rather than inventing a gap.
  package static let rhythm: [CGFloat] = [28, 22, 18, 14, 12, 10, 8, 6]

  /// A reserved strip at the foot of a card that progress dots occupy.
  ///
  /// Reserved rather than drawn over. Subtracting a band is the version of "clear of the content" that
  /// a longer sentence cannot invalidate.
  package static let progressBandHeight: CGFloat = 44

  /// Between a headline block, its rows, and whichever panel sits under them.
  package static let permissionsBlockSpacing: CGFloat = 18

  /// Between two rows.
  package static let permissionsRowSpacing: CGFloat = 8
}

// MARK: - Motion

/// Durations from the motion table, in seconds. Pass them through `InkReduceMotion` before use.
package enum InkMotion {
  package static let stepTransition: Double = 0.240
  package static let wordReveal: Double = 1.200
  package static let settle: Double = 0.280
  package static let checkbox: Double = 0.180
  package static let finaleGlow: Double = 0.550
  /// Button press feedback, fast enough to read as pressure rather than as animation.
  package static let press: Double = 0.090
}

/// Reduce Transparency in one place, for the same reason `InkReduceMotion` exists: the setting is
/// honoured by a call, not by a discipline nobody keeps.
package enum InkReduceTransparency {
  package static var isEnabled: Bool {
    NSWorkspace.shared.accessibilityDisplayShouldReduceTransparency
  }

  /// Fires when the user flips the setting. The same notification `InkReduceMotion` watches — macOS
  /// posts one for the whole accessibility display group — so an observer has to re-read the setting
  /// it cares about rather than assume which one changed.
  package static let didChangeNotification = NSWorkspace.accessibilityDisplayOptionsDidChangeNotification
}

/// Reduce Motion in one place. Every animation in this system goes through this, so honouring the
/// setting is a call rather than a discipline nobody keeps.
package enum InkReduceMotion {
  package static var isEnabled: Bool {
    NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
  }

  /// Fires when the user flips the setting; posted on `NSWorkspace.shared.notificationCenter`.
  package static let didChangeNotification = NSWorkspace.accessibilityDisplayOptionsDidChangeNotification

  /// `nil` under Reduce Motion, which is how SwiftUI spells "apply the change instantly".
  package static func animation(_ animation: Animation) -> Animation? {
    isEnabled ? nil : animation
  }

  /// Zero under Reduce Motion. For hand-rolled interpolation where a zero duration means "jump to the
  /// end state".
  package static func duration(_ seconds: Double) -> Double {
    isEnabled ? 0 : seconds
  }

  /// `withAnimation`, or a straight mutation under Reduce Motion.
  package static func perform(_ animation: Animation, _ body: () -> Void) {
    if isEnabled {
      body()
    } else {
      withAnimation(animation) { body() }
    }
  }
}

// MARK: - Button

/// The only action shape in this system: a full stadium, never a rounded rectangle.
package struct InkButton: View {
  package enum Kind: Sendable {
    /// `Ink.primary` fill, `Ink.surface` label — the label ladder inverted.
    case primary
    /// Clear fill, `Ink.primary` label, 1 pt `Ink.hairline`.
    case secondary
  }

  private let title: String
  private let kind: Kind
  private let action: () -> Void

  package init(_ title: String, kind: Kind = .primary, action: @escaping () -> Void) {
    self.title = title
    self.kind = kind
    self.action = action
  }

  package var body: some View {
    Button(action: action) {
      Text(title).inkFont(InkType.buttonLabel)
    }
    .buttonStyle(InkButtonStyle(kind: kind))
  }
}

/// Exposed so a caller with a richer label (an icon, a progress ring) still gets the exact metrics.
package struct InkButtonStyle: ButtonStyle {
  package var kind: InkButton.Kind

  // `nonisolated` for the same reason `InkPermissionRow.menuRowHeight` is: `ButtonStyle` is
  // `@MainActor`, and these are metrics a caller may want to read while measuring, not draw with.
  nonisolated package static let minHeight: CGFloat = 42
  nonisolated package static let horizontalPadding: CGFloat = 24

  package init(kind: InkButton.Kind = .primary) {
    self.kind = kind
  }

  package func makeBody(configuration: Configuration) -> some View {
    // A nested view, not an inline body: `@Environment` only tracks changes inside a `View`.
    StyledLabel(kind: kind, configuration: configuration)
  }

  private struct StyledLabel: View {
    let kind: InkButton.Kind
    let configuration: Configuration
    @Environment(\.isEnabled) private var isEnabled

    private var pressed: Bool { configuration.isPressed }

    /// The primary button is deliberately *not* accent-filled. The accent is already spent on the one
    /// link that needs it, and a filled accent button owes a label colour legible on it in both
    /// appearances — one more contrast pair to keep true. Inverting the label ladder instead is
    /// high-contrast in both appearances by construction.
    private var fill: Color {
      switch kind {
      // Pressed drops opacity rather than darkening: letting the surface through is the only
      // direction that reads as give in both appearances.
      case .primary: return pressed ? Ink.primary.opacity(0.82) : Ink.primary
      case .secondary: return pressed ? Ink.wash : Color.clear
      }
    }

    private var label: Color {
      kind == .primary ? Ink.surface : Ink.primary
    }

    var body: some View {
      configuration.label
        // A caller-supplied label keeps its own font; `InkButton` has already set it.
        .font(InkType.buttonLabel.font)
        .foregroundStyle(label)
        .padding(.horizontal, InkButtonStyle.horizontalPadding)
        .frame(minHeight: InkButtonStyle.minHeight)
        .background(Capsule(style: .continuous).fill(fill))
        .overlay {
          if kind == .secondary {
            Capsule(style: .continuous).strokeBorder(Ink.hairline, lineWidth: 1)
          }
        }
        .contentShape(Capsule(style: .continuous))
        .opacity(isEnabled ? 1 : 0.45)
        // Colour only, no scale: a pill this size bouncing reads as a toy.
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: pressed)
    }
  }
}

// MARK: - Permission row

/// One capability, asked for in the app's own voice. The whole row is the target — the state readout
/// is not a separate control.
///
/// The same row appears on two surfaces that must not look alike, which is what `native` selects
/// between:
///
/// - **A card (`native: false`)**, and it is *glass*: a wash, a hairline, a drawn checkbox, the
///   capability introduced as a first-person sentence, and the status word in `secondary` — glass
///   carries a two-rung ladder (see `Ink.tertiary`).
/// - **A menu item (`native: true`)** on a system surface sitting beside every other menu bar extra on
///   the machine: 22 pt tall, one system-size label, the status trailing in `tertiary` (that surface is
///   opaque chrome, so it keeps all three rungs), no fill of its own, no tracking, no border. A filled
///   capsule with letter-spaced type is the single clearest tell that a panel was drawn by a website
///   rather than by macOS.
package struct InkPermissionRow: View {
  private let title: String
  private let granted: Bool
  private let status: String
  private let native: Bool
  private let action: () -> Void

  @State private var isHovering = false

  /// - Parameters:
  ///   - title: the first-person sentence, e.g. "I would like to hear you"; the plain noun on the
  ///     native surface, where the user has already been introduced.
  ///   - granted: drives the state readout.
  ///   - status: one word — `Granted` / `Open` / `Checking` / `Action required`.
  ///   - native: renders the row as a macOS menu item instead of a card.
  package init(title: String, granted: Bool, status: String, native: Bool = false, action: @escaping () -> Void) {
    self.native = native
    self.title = title
    self.granted = granted
    self.status = status
    self.action = action
  }

  package var body: some View {
    Button(action: action) {
      if native {
        menuRow
      } else {
        card
      }
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isHovering)
    .accessibilityLabel(Text("\(title). \(status)"))
  }

  // MARK: - The menu bar

  /// Menu metrics, not card metrics: `NSFont.systemFontSize` is the size AppKit sets a menu item in,
  /// and 22 pt is the height it gives one. No `.inkStyle` anywhere in here — the tracking that gives a
  /// card its character is exactly what makes a menu look counterfeit.
  private var menuRow: some View {
    HStack(spacing: 6) {
      // The checkmark column, held open whether or not it is filled, so the titles of a granted and an
      // ungranted row line up the way a menu's do.
      Image(systemName: "checkmark")
        .font(.system(size: 10, weight: .semibold))
        .foregroundStyle(Ink.primary)
        .opacity(granted ? 1 : 0)
        .frame(width: 12, alignment: .leading)

      Text(title)
        .font(.system(size: NSFont.systemFontSize))
        .foregroundStyle(Ink.primary)
        .lineLimit(1)

      Spacer(minLength: 8)

      // The one `Ink.tertiary` in this file, and it is on the *opaque* surface: this branch only ever
      // renders inside a menu bar popover, which is AppKit's own chrome rather than `InkGlassView`. The
      // card branch below sets the same word in `secondary`, because glass carries a two-rung ladder.
      Text(status)
        .font(.system(size: NSFont.systemFontSize))
        .foregroundStyle(Ink.tertiary)
        .fixedSize()
    }
    .padding(.horizontal, 4)
    .frame(height: InkPermissionRow.menuRowHeight)
    .frame(maxWidth: .infinity, alignment: .leading)
    // Nothing at rest. A popover already has a vibrant material doing the work of separating itself
    // from the window behind it, and a menu row that is filled when it is not under the pointer is not
    // a menu row.
    .background(
      RoundedRectangle(cornerRadius: 4, style: .continuous)
        .fill(isHovering ? Ink.rowHover : Color.clear)
    )
    .contentShape(Rectangle())
  }

  /// The height AppKit gives a menu item set at `NSFont.systemFontSize`.
  ///
  /// `nonisolated` because it is a metric, not a view. `View` is `@MainActor`, so a constant declared
  /// inside a view is main-actor-isolated by default and a menu that lays itself out off the main
  /// actor could not read it.
  nonisolated package static let menuRowHeight: CGFloat = 22

  // MARK: - The card

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: 13, style: .continuous)
  }

  private var card: some View {
    HStack(spacing: 11) {
      InkCheckbox(granted: granted)
      Text(title)
        .inkStyle(InkType.rowCopy, color: Ink.primary)
        .multilineTextAlignment(.leading)
        // **The row wraps; it never truncates.** Without this the sentence is compressible, and a
        // `VStack` of rows in a card that is a little too short pays for the shortfall by squeezing
        // them — which is not a squeeze, it is a `Text` given less height than it needs, and a `Text`
        // given less height than it needs ends in "…". Fixed vertically, the row can only get taller,
        // so too little room becomes a layout that fails a measurement instead of copy that quietly
        // disappears.
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
      // `secondary` and not the glance-word rung: this row is on glass, which carries two rungs. The
      // status still reads as subordinate to the sentence beside it, which is `primary`.
      Text(status)
        .inkStyle(InkType.statusLabel, color: Ink.secondary)
        .fixedSize()
    }
    .padding(.horizontal, 14)
    .padding(.vertical, 11)
    .frame(maxWidth: .infinity, alignment: .leading)
    // A half-step of shading plus a hairline. A fill strong enough to read on its own would box three
    // sentences into three grey slabs.
    .background(shape.fill(isHovering ? Ink.rowFillHover : Ink.rowFill))
    .overlay(shape.strokeBorder(Ink.separator, lineWidth: 1))
    .contentShape(shape)
  }
}

/// 18 × 18, corner radius 6, `Ink.hairline`; fills `Ink.primary` with an `Ink.surface` checkmark when
/// granted. The card surface only — a menu uses a plain menu checkmark.
package struct InkCheckbox: View {
  package let granted: Bool

  package init(granted: Bool) {
    self.granted = granted
  }

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: 6, style: .continuous)
  }

  package var body: some View {
    shape
      .fill(granted ? Ink.primary : Color.clear)
      .overlay(shape.strokeBorder(granted ? Color.clear : Ink.hairline, lineWidth: 1))
      .overlay(
        Image(systemName: "checkmark")
          .font(.system(size: 11, weight: .bold))
          .foregroundStyle(Ink.surface)
          .opacity(granted ? 1 : 0)
      )
      .frame(width: 18, height: 18)
      .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.checkbox)), value: granted)
  }
}
