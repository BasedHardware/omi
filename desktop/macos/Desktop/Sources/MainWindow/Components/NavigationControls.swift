//
//  NavigationControls.swift — the only two ways out of a surface.
//
//  The app used to have about eleven back controls (glass chip, bare chevron, chevron in a circle,
//  sidebar row, grey text, a `chevron.up` "Back to Rewind") and six close buttons (18–32 pt, four
//  fills). A reader could not tell from the control whether leaving would pop one level, close an
//  overlay, or change tabs. The contract is now two controls with two meanings:
//
//  - `BackChip` — leading edge, names its destination ("‹ Conversations"). For anything that
//    *replaced* the page you were on: a drill-in, a detail, a transcript.
//  - `DismissButton` — trailing edge, an xmark. For anything that *floats over* the page: a side
//    panel, a sheet, a toast, a card.
//
//  Both advertise Esc, and every surface that shows one must consume Esc for the same action at
//  `.content` priority or higher. See `docs/ux-contract.md` and `INV-UI-2`.
//
//  Brand: `Ink` semantics only (INV-UI-1).
//

import AppKit
import OmiTheme
import SwiftUI

// MARK: - Back

/// The drill-in way out: a glass chip on the leading edge naming where it goes.
///
/// A bare "Back" is allowed only when the destination genuinely has no name the reader would
/// recognise; prefer the destination ("Conversations", "Summary", "Rewind").
struct BackChip: View {
  let title: String
  let action: () -> Void
  var accessibilityIdentifier: String?

  @State private var isHovering = false

  init(_ title: String = "Back", accessibilityIdentifier: String? = nil, action: @escaping () -> Void) {
    self.title = title
    self.accessibilityIdentifier = accessibilityIdentifier
    self.action = action
  }

  /// The chip's height. One number for every back control so a drill-in two levels deep does not
  /// shift the header by two points.
  static let height: CGFloat = QueryShellLayout.chipHeight + 2

  var body: some View {
    Button(action: action) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: "chevron.left")
          .scaledFont(size: OmiType.caption, weight: .semibold)
        Text(title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .lineLimit(1)
          .truncationMode(.tail)
      }
      .foregroundStyle(GlassShell.controlLabel(isProminent: true))
      .padding(.horizontal, OmiSpacing.md)
      .frame(height: Self.height)
      .frame(maxWidth: 220, alignment: .leading)
      .fixedSize(horizontal: true, vertical: false)
      .glassChip(isActive: isHovering)
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .help(Self.helpText(for: title))
    .accessibilityLabel(Self.helpText(for: title))
    .accessibilityIdentifier(accessibilityIdentifier ?? "back-chip")
  }

  nonisolated static func helpText(for title: String) -> String {
    title == "Back" ? "Back (Esc)" : "Back to \(title) (Esc)"
  }
}

// MARK: - Dismiss

/// The overlay way out: an xmark on the trailing edge.
///
/// A real `Button` (not a tap gesture) so accessibility exposes it as a labeled "Close" control and
/// keyboard users can reach it.
struct DismissButton: View {
  let action: () -> Void
  var icon: String = "xmark"
  var showBackground: Bool = true
  var accessibilityLabel: String = "Close"
  var size: Size = .regular

  enum Size {
    /// 28 pt — sheets, side panels, page-level overlays.
    case regular
    /// 22 pt — inline cards and toasts, where a 28 pt circle outweighs the content.
    case compact

    var diameter: CGFloat { self == .regular ? 28 : 22 }
    var glyph: CGFloat { self == .regular ? OmiType.body : OmiType.caption }
  }

  var body: some View {
    Button {
      log("DISMISS_BUTTON: Activated")

      // Commit any in-progress field editing before tearing the sheet down.
      NSApp.keyWindow?.makeFirstResponder(nil)

      OmiMotion.withGated(.easeOut(duration: 0.2)) {
        action()
      }
    } label: {
      Image(systemName: icon)
        .scaledFont(size: size.glyph, weight: .medium)
    }
    .buttonStyle(
      GlassIconButtonStyle(diameter: size.diameter, restsFilled: showBackground)
    )
    .help("\(accessibilityLabel) (Esc)")
    .accessibilityLabel(accessibilityLabel)
  }
}

// MARK: - Safe Dismiss

/// A dismiss button for `DismissAction`-driven sheets that prevents click-through to underlying
/// views on macOS. Uses a tap gesture with an async delay so the click is fully consumed before the
/// sheet tears down. Looks exactly like `DismissButton`.
struct SafeDismissButton: View {
  let dismiss: DismissAction
  var icon: String = "xmark"
  var showBackground: Bool = true

  @State private var isPressed = false

  var body: some View {
    Image(systemName: icon)
      .scaledFont(size: OmiType.body, weight: .medium)
      .foregroundColor(Ink.secondary)
      .frame(width: 28, height: 28)
      .background(showBackground ? Ink.wash : Color.clear)
      .clipShape(Circle())
      .contentShape(Circle())
      .opacity(isPressed ? 0.7 : 1.0)
      .help("Close (Esc)")
      .accessibilityElement()
      .accessibilityLabel("Close")
      .accessibilityAddTraits(.isButton)
      .onTapGesture {
        guard !isPressed else { return }  // Prevent double-tap
        isPressed = true

        // Consume the click by resigning first responder
        NSApp.keyWindow?.makeFirstResponder(nil)

        // Post a mouse-up event to ensure any pending click is consumed
        if let window = NSApp.keyWindow,
          let event = NSEvent.mouseEvent(
            with: .leftMouseUp,
            location: window.mouseLocationOutsideOfEventStream,
            modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime,
            windowNumber: window.windowNumber,
            context: nil,
            eventNumber: 0,
            clickCount: 1,
            pressure: 0
          )
        {
          window.sendEvent(event)
        }

        Task { @MainActor in
          // omi-ux: click-through guard — the mouse-up must finish before the sheet tears down.
          try? await Task.sleep(nanoseconds: 250_000_000)
          dismiss()
        }
      }
  }
}

// MARK: - Clear field

/// The clear control inside a search or text field: a filled circle-x at the field's trailing edge.
/// It clears the field; it never closes anything, which is why it is not a `DismissButton`.
struct ClearFieldButton: View {
  var help: String = "Clear Search"
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Image(systemName: "xmark.circle.fill")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .contentShape(Circle())
    }
    .buttonStyle(.plain)
    .help(help)
    .accessibilityLabel(help)
  }
}
