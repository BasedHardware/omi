//
//  OmiIconButton.swift — every icon-only control in the main window.
//
//  An icon button used to be whatever its call site drew: 18, 20, 24, 26, 28, 32 and 36 pt, circles and
//  rounded squares, four different fills, almost none with a hover state, and about forty of them with
//  neither a tooltip nor an accessibility label. The conversation header alone mixed four treatments in
//  one row.
//
//  `OmiIconButton` makes the tooltip and label *required arguments*: an icon without words is only a
//  control for people who already know what it does. It draws through `GlassIconButtonStyle`, so hover
//  and press come for free and the diameter is one of three rungs.
//
//  `OmiIconMenu` is the same control opening a menu, with the menu indicator hidden — the stray
//  chevron beside the folder button was `.borderlessButton`'s default indicator.
//
//  `CopyButton` is the icon button that copies, and the only place copy feedback is decided: the glyph
//  becomes a checkmark for `OmiFeedbackTiming.confirmation`.
//
//  See `docs/ux-contract.md` (INV-UI-2).
//

import AppKit
import OmiTheme
import SwiftUI

/// How long transient feedback stays on screen. One table instead of 1.4 / 1.5 / 1.8 / 2 / 4 / 6 / 12 s
/// picked per call site.
enum OmiFeedbackTiming {
  /// A confirmation of something the user just did ("Copied", "Saved"). Long enough to see, short
  /// enough not to still be there when they look for the next thing.
  static let confirmation: TimeInterval = 1.5
  /// A toast that carries an Undo. Long enough to read the item name and reach the button.
  static let undo: TimeInterval = 5
  /// Informational cards the user did not ask for. Paused while hovered.
  static let informational: TimeInterval = 8
}

enum OmiIconButtonSize {
  /// 22 pt — inline in a row or a card.
  case compact
  /// 28 pt — page and panel headers. The default.
  case regular
  /// 32 pt — the shell's top bar.
  case large

  var diameter: CGFloat {
    switch self {
    case .compact: return 22
    case .regular: return 28
    case .large: return 32
    }
  }

  var glyph: CGFloat {
    switch self {
    case .compact: return OmiType.caption
    case .regular, .large: return OmiType.body
    }
  }
}

/// An icon-only button. `help` is both the tooltip and the accessibility label.
struct OmiIconButton: View {
  let systemName: String
  let help: String
  var size: OmiIconButtonSize = .regular
  var isDestructive: Bool = false
  var isActive: Bool = false
  let action: () -> Void

  init(
    _ systemName: String,
    help: String,
    size: OmiIconButtonSize = .regular,
    isDestructive: Bool = false,
    isActive: Bool = false,
    action: @escaping () -> Void
  ) {
    self.systemName = systemName
    self.help = help
    self.size = size
    self.isDestructive = isDestructive
    self.isActive = isActive
    self.action = action
  }

  var body: some View {
    Button(action: action) {
      Image(systemName: systemName)
        .scaledFont(size: size.glyph, weight: .medium)
        .foregroundStyle(isDestructive ? AnyShapeStyle(Ink.errorRed) : AnyShapeStyle(.foreground))
    }
    .buttonStyle(GlassIconButtonStyle(isActive: isActive, diameter: size.diameter, restsFilled: true))
    .help(help)
    .accessibilityLabel(help)
  }
}

/// An icon-only button that opens a menu. Looks exactly like `OmiIconButton`; no indicator chevron.
struct OmiIconMenu<Content: View>: View {
  let systemName: String
  let help: String
  var size: OmiIconButtonSize = .regular
  var isActive: Bool = false
  @ViewBuilder let content: () -> Content

  @State private var isHovering = false

  var body: some View {
    Menu(content: content) {
      Image(systemName: systemName)
        .scaledFont(size: size.glyph, weight: .medium)
    }
    .menuStyle(.button)
    .buttonStyle(GlassIconButtonStyle(isActive: isActive, diameter: size.diameter, restsFilled: true))
    .menuIndicator(.hidden)
    .fixedSize()
    .help(help)
    .accessibilityLabel(help)
  }
}

// MARK: - Copy

/// The one clipboard write path for user-initiated copies, so every copy can report whether it
/// happened.
enum OmiClipboard {
  /// Copies `text`. Returns `false` (and copies nothing) for empty text, so a caller never shows
  /// "Copied" over an empty clipboard.
  @discardableResult
  @MainActor
  static func copy(_ text: String) -> Bool {
    guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
    let pasteboard = NSPasteboard.general
    pasteboard.clearContents()
    return pasteboard.setString(text, forType: .string)
  }
}

/// An icon button that copies and confirms with a checkmark.
///
/// `text` is evaluated on click, so a caller can build an expensive string lazily. Returning `nil`
/// or empty text shows nothing — the button never claims a copy it did not make.
struct CopyButton: View {
  let help: String
  var size: OmiIconButtonSize = .regular
  let text: () -> String?

  @State private var confirmed = false
  @State private var resetTask: Task<Void, Never>?

  init(help: String = "Copy", size: OmiIconButtonSize = .regular, text: @escaping () -> String?) {
    self.help = help
    self.size = size
    self.text = text
  }

  var body: some View {
    Button {
      guard let value = text(), OmiClipboard.copy(value) else { return }
      resetTask?.cancel()
      confirmed = true
      resetTask = Task { @MainActor in
        try? await Task.sleep(nanoseconds: UInt64(OmiFeedbackTiming.confirmation * 1_000_000_000))
        guard !Task.isCancelled else { return }
        confirmed = false
      }
    } label: {
      Image(systemName: confirmed ? "checkmark" : "doc.on.doc")
        .scaledFont(size: size.glyph, weight: .medium)
        .contentTransition(.symbolEffect(.replace))
    }
    .buttonStyle(GlassIconButtonStyle(diameter: size.diameter, restsFilled: true))
    .help(confirmed ? "Copied" : help)
    .accessibilityLabel(confirmed ? "Copied" : help)
  }
}
