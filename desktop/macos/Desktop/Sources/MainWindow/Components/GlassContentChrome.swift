//
//  GlassContentChrome.swift — the chrome the content pages wear on glass.
//
//  `OmiTheme`'s `Ink` / `InkGlass` own the *panel*: the material, the scrim, the corner, the pinned
//  light appearance. This file owns what a **content page hosted inside that panel** is allowed to
//  draw on it — the card, the row, the chip, the field, the scroll fade — so conversations, memories,
//  tasks and rewind cannot each invent their own answer.
//
//  Three rules are load-bearing here, and every one of them was a defect in the dark chrome this
//  replaced:
//
//  1. **Hosted content paints no background.** The glass owns the ground. A page that fills itself
//     opaque is a grey slab pasted over the panel, and the panel is the product. So the surfaces below
//     are *washes* (`Ink.rowFill`, alpha on `labelColor`) rather than fills — they read as a shade of
//     the glass rather than as a second background.
//  2. **Two type rungs, never three.** `Ink.tertiary` is legal only on an opaque sheet; on glass it
//     measures under AA (see `Ink.tertiary`). Anything that was tertiary is `Ink.secondary` here.
//  3. **A scroll fade is a mask, not an overlay.** On glass there is no opaque colour to fade *to* —
//     an overlay gradient painted in the page's old background colour is a grey smear over the
//     desktop. `glassScrollFade` masks the content's alpha instead, and applies unconditionally: a
//     fade that appears only when `canScrollUp` changes the modified view's identity and throws the
//     scroll position away every time it flips.
//
//  Colour decisions live in `PageGlass` as pure functions so they are assertable without a window
//  server; the modifiers below are thin wrappers over them.
//

import AppKit
import OmiTheme
import SwiftUI

// MARK: - Tokens

/// The content pages' half of the glass vocabulary. Radii, the two state colours `Ink` does not
/// carry, and the row/card fills as pure functions of state.
enum PageGlass {
  // Geometry. One card corner, shared with the panel itself so a card on glass and the glass it sits
  // on are cut to the same curve; rows and chips step down from it.

  /// The card corner — `InkGlass.cornerRadius` by construction, never a second opinion about 22.
  static let cardRadius: CGFloat = InkGlass.cornerRadius
  /// A row inside a card. Matches `InkPermissionRow`'s card so a task row and a permission row are
  /// visibly the same object.
  static let rowRadius: CGFloat = 13
  /// A filter chip, a badge, a tag.
  static let chipRadius: CGFloat = 11
  /// A text field or search field.
  static let fieldRadius: CGFloat = 13

  /// Page content starts fully opaque. A permanent top-edge mask fades the first visible row before
  /// the user has scrolled, which makes correctly positioned controls and headings look clipped.
  /// The bottom edge still signals overflow without compromising the page's resting state.
  static let topFade: CGFloat = 0
  /// Deeper than the top, because the bottom of a page is where floating bars sit and the content has
  /// to pass under one legibly.
  static let bottomFade: CGFloat = 30

  /// Foreground for a control filled with `Ink.primary`.
  ///
  /// A primary-on-primary pairing erases the control's label. Keep the inverse ink named once so
  /// custom page actions cannot drift away from the shared button-style contrast contract.
  static let primaryActionLabel = Ink.surface

  // The two states `Ink` deliberately has no token for. `Ink` carries `errorRed` and
  // `listeningGreen` because those are the only two states the *shell* raises its voice for; a
  // content page also has "overdue / needs attention" and "starred", which are one step below an
  // error and must not borrow `errorRed` to say so.
  //
  // A **named system colour**, for the same reason `Ink.accent` is one: it tracks the appearance,
  // brightens under Increase Contrast, and is not a hand-mixed hue. INV-UI-1's banned hue appears
  // nowhere in this file.

  /// Overdue, stale, degraded — a state with something to do about it that is not yet an error.
  static let warning = Color(nsColor: .systemOrange)

  /// A starred conversation, memory, or task. Same hue as `warning` on purpose: an app with a
  /// separate colour per adjective has a mood board, not a palette.
  static let starred = Color(nsColor: .systemOrange)

  /// Speaker tints for transcript bubbles.
  ///
  /// The dark-chrome list was six hand-mixed near-blacks (`0x2D3748`, `0x1E3A5F`, …) that were only
  /// ever distinguishable *because* the page behind them was `0x0F0F0F`. On glass they are six
  /// identical dark slabs. These are named system colours at a wash alpha instead, so a bubble reads
  /// as a tinted piece of the glass and the transcript stays legible in `Ink.primary` on top of it.
  static let speakerTints: [Color] = [
    Color(nsColor: .systemBlue).opacity(0.12),
    Color(nsColor: .systemTeal).opacity(0.12),
    Color(nsColor: .systemGreen).opacity(0.12),
    Color(nsColor: .systemOrange).opacity(0.12),
    Color(nsColor: .systemBrown).opacity(0.12),
    Color(nsColor: .systemGray).opacity(0.14),
  ]

  /// A row's three states. `selected` outranks `hover` — a row under the pointer that is already
  /// selected must not dim back to the hover wash.
  enum RowState: Equatable, Sendable {
    case rest
    case hover
    case selected
  }

  /// The wash behind a row. `rest` is genuinely nothing on a *list* — a list of forty filled slabs is
  /// a wall — so only the states the pointer or the selection put a row into draw anything.
  static func rowFill(_ state: RowState) -> Color {
    switch state {
    case .rest: return .clear
    case .hover: return Ink.rowFill
    case .selected: return Ink.rowFillHover
    }
  }

  /// The row's outline. Only a selected row is outlined: a hover wash is the affordance, and a border
  /// that appears under the pointer reads as the row having moved.
  static func rowStroke(_ state: RowState) -> Color {
    state == .selected ? Ink.separator : .clear
  }

  /// A chip's fill.
  ///
  /// **The active step is deliberately much heavier than the rest step, and that is a fix rather
  /// than a preference.** Active used to be `Ink.rowFillHover` over `Ink.rowFill` — four hundredths
  /// of alpha apart. On the dark chrome those two tokens sat on a near-black page and read as two
  /// steps; on glass they composite onto a ground that is already 35% desktop, and a filter row of
  /// six chips showed no legible difference between the one that was on and the five that were off.
  /// A filter whose state you cannot see is a filter that silently lies about what the list contains.
  ///
  /// `Ink.primary` at 0.14 rather than a heavier `rowFill`: it is the same ink the active chip's
  /// *label* is set in, so "on" reads as one object getting darker rather than as a second colour.
  static func chipFill(isActive: Bool) -> Color {
    isActive ? Color(nsColor: .labelColor).opacity(0.14) : Ink.rowFill
  }

  /// A chip's outline. The active chip carries the control outline (`Ink.hairline`) so its edge is
  /// legible even where the fill lands on an unusually dark patch of desktop.
  static func chipStroke(isActive: Bool) -> Color {
    isActive ? Ink.hairline : Ink.separator
  }
}

// MARK: - Surfaces

/// A card on glass: a wash plus a hairline, and no shadow.
///
/// Deliberately not `omiPanel`'s recipe. That drew an opaque fill and a `black.opacity(0.14)` drop
/// shadow, which on a dark page read as depth and on glass reads as dirt — the panel already carries
/// the one ambient shadow in this system (`InkGlassShadow.ambient`), and a second shadow inside it is
/// a card floating above a card.
private struct GlassCardModifier: ViewModifier {
  let cornerRadius: CGFloat
  let isEmphasized: Bool

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
  }

  func body(content: Content) -> some View {
    content
      .background(shape.fill(isEmphasized ? Ink.rowFillHover : Ink.rowFill))
      .overlay(shape.strokeBorder(Ink.separator, lineWidth: 1))
  }
}

private struct GlassRowModifier: ViewModifier {
  let state: PageGlass.RowState
  let cornerRadius: CGFloat

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
  }

  func body(content: Content) -> some View {
    content
      .background(shape.fill(PageGlass.rowFill(state)))
      .overlay(shape.strokeBorder(PageGlass.rowStroke(state), lineWidth: 1))
      .contentShape(shape)
      // Colour only — a row that scales under the pointer turns a list into a trampoline.
      .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: state)
  }
}

/// The mask that ends a scrolling column.
///
/// Height-agnostic on purpose: a `LinearGradient` given `UnitPoint` stops fades a fixed *fraction* of
/// the column, so the same modifier erases 6 pt of a tall page and 60 pt of a short one. Stacking two
/// fixed-height gradients around an opaque middle makes the fade a constant number of points at both
/// ends whatever the content does.
private struct GlassScrollFadeModifier: ViewModifier {
  let top: CGFloat
  let bottom: CGFloat

  func body(content: Content) -> some View {
    content.mask {
      VStack(spacing: 0) {
        LinearGradient(colors: [.clear, .black], startPoint: .top, endPoint: .bottom)
          .frame(height: top)
        Rectangle().fill(Color.black)
        LinearGradient(colors: [.black, .clear], startPoint: .top, endPoint: .bottom)
          .frame(height: bottom)
      }
    }
  }
}

extension View {
  /// Marks a view as content *hosted on* the glass panel.
  ///
  /// Two jobs, and the second is the one that bites. It paints no background — the glass owns the
  /// ground — and it resolves `Ink`'s dynamic colours in the panel's pinned light appearance. Without
  /// the second, a page on a machine in Dark Mode renders `Ink.primary` as near-*white* onto a
  /// light-pinned panel and the whole page disappears. `inkGlassPanel` pins the same appearance for
  /// the surfaces it draws itself; a page reached through a navigation stack or a sheet does not
  /// always sit inside one, so it says so itself. Idempotent — applying it twice costs nothing.
  func glassContent() -> some View {
    environment(\.colorScheme, .light)
  }

  /// The one dark surface a content page is allowed to draw: a viewport onto rendered media.
  ///
  /// A screen recording is letterboxed against black by every player ever shipped, and the reason is
  /// not taste — a light mat around a screenshot of a light app hides where the frame ends. So the
  /// full-screen Rewind player keeps its mat, and this is the *only* exemption from "hosted content
  /// paints no background".
  ///
  /// It flips the environment to `.dark` rather than hard-coding light-on-black, so `Ink`'s ladder
  /// resolves *up* on the mat: one palette, two grounds, and no second set of colour literals for the
  /// player's transport controls. Anything reading `Ink.primary` inside is white here and near-black
  /// on the glass, which is the correct answer in both places.
  func glassMediaMat(cornerRadius: CGFloat = 0) -> some View {
    environment(\.colorScheme, .dark)
      .background(
        Group {
          if cornerRadius > 0 {
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous).fill(Color.black)
          } else {
            Color.black
          }
        }
      )
  }

  /// A card on glass. See `GlassCardModifier`.
  func glassCard(cornerRadius: CGFloat = PageGlass.cardRadius, emphasized: Bool = false) -> some View {
    modifier(GlassCardModifier(cornerRadius: cornerRadius, isEmphasized: emphasized))
  }

  /// One row of a list on glass.
  func glassRow(_ state: PageGlass.RowState, cornerRadius: CGFloat = PageGlass.rowRadius) -> some View {
    modifier(GlassRowModifier(state: state, cornerRadius: cornerRadius))
  }

  /// A filter chip / badge / tag on glass. Stadium, because every pressable thing in this system is.
  func glassChip(isActive: Bool = false) -> some View {
    background(Capsule(style: .continuous).fill(PageGlass.chipFill(isActive: isActive)))
      .overlay(Capsule(style: .continuous).strokeBorder(PageGlass.chipStroke(isActive: isActive), lineWidth: 1))
      .contentShape(Capsule(style: .continuous))
  }

  /// A text or search field on glass.
  func glassField(cornerRadius: CGFloat = PageGlass.fieldRadius) -> some View {
    let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
    return background(shape.fill(Ink.rowFill))
      .overlay(shape.strokeBorder(Ink.separator, lineWidth: 1))
  }

  /// A bar that floats over the scroll — a merge bar, a load-more, a player transport.
  ///
  /// This one *is* glass rather than a wash: it sits over moving content, so it needs the material
  /// and the ambient shadow to stay readable as the page scrolls under it.
  func glassFloatingBar(cornerRadius: CGFloat = PageGlass.cardRadius) -> some View {
    inkGlassPanel(cornerRadius: cornerRadius, shadow: .ambient)
  }

  /// Fades the ends of a scrolling column by masking its alpha.
  ///
  /// **Always apply this unconditionally.** Wrapping it in `if canScrollUp` changes the view's
  /// identity on every flip, which discards the scroll position — the exact bug a fade is usually
  /// added to paper over.
  func glassScrollFade(
    top: CGFloat = PageGlass.topFade,
    bottom: CGFloat = PageGlass.bottomFade
  ) -> some View {
    modifier(GlassScrollFadeModifier(top: top, bottom: bottom))
  }
}

// MARK: - Components

/// A page's title block: the heading and the sentence under it, in the two rungs glass carries.
struct GlassPageHeader<Trailing: View>: View {
  let title: String
  var subtitle: String?
  @ViewBuilder var trailing: () -> Trailing

  var body: some View {
    HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.md) {
      VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
        Text(title)
          .inkStyle(InkType.firstTitle, color: Ink.primary)
        if let subtitle {
          Text(subtitle)
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
        }
      }
      Spacer(minLength: OmiSpacing.md)
      trailing()
    }
  }
}

extension GlassPageHeader where Trailing == EmptyView {
  init(title: String, subtitle: String? = nil) {
    self.init(title: title, subtitle: subtitle, trailing: { EmptyView() })
  }
}

/// The "there is nothing here yet" state, in one place so nine pages do not each pick a different
/// glyph size and grey.
struct GlassEmptyState: View {
  let systemImage: String
  let title: String
  var message: String?

  var body: some View {
    VStack(spacing: OmiSpacing.md) {
      Image(systemName: systemImage)
        .font(.system(size: 30, weight: .light))
        // `secondary`, not a fainter step: on glass there is no third rung to spend here.
        .foregroundStyle(Ink.secondary)
      Text(title)
        .inkStyle(InkType.rowCopy, color: Ink.primary)
      if let message {
        Text(message)
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .padding(OmiSpacing.xxl)
  }
}

/// A rule between blocks on glass. `Ink.separator` at 1 px, never a `Divider()` inside a card — a
/// `Divider` inherits the host window's appearance rather than the panel's pinned one.
struct GlassSeparator: View {
  var body: some View {
    Rectangle()
      .fill(Ink.separator)
      .frame(height: 1)
  }
}
