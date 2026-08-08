//
//  ShellConfirmationDialog.swift — "are you sure?", drawn by the shell, because the system draws it
//  on the wallpaper.
//
//  A SwiftUI `.alert` is presented *by AppKit against the host window*, and the backdrop it puts up
//  while it is open is sized to that window. On an ordinary titled window that is exactly right — the
//  window's frame is the app's edge, so dimming to it dims the app. On this one it is the defect
//  `ShellModalScrim` was written for, arriving through a door that file could not close:
//  `ShellWindowChrome` took the shell's ground away, so the window is a transparent rectangle
//  noticeably larger than the panels inside it, and a backdrop at window scale is a hard-edged
//  rounded rectangle — window shadow and all — stamped onto the user's wallpaper.
//
//  Measured on a live build, opening Settings → Advanced → Reset Onboarding: every pixel inside the
//  window frame changed, including the wallpaper showing through between the panels and the drag band
//  above the top bar, out to the window's own shadow. Nothing outside the frame changed. That is the
//  window, drawn.
//
//  ## So the shell draws its own
//
//  The dim has to survive — a confirmation with a live app behind it does not read as a confirmation,
//  and this one guards a destructive action. What changes is who paints it: `ShellModalScrim`, which
//  keeps modality at host scale (an invisible barrier that swallows clicks and carries the dismiss
//  gesture) and puts the *paint* on the enclosing surface, cut to the one corner every panel in this
//  product is cut to. Which surface that is comes from the environment `PageGlassLane` publishes, so
//  this dialog inherits correct bounds wherever it is mounted and no call site is asked to choose.
//
//  Escape and a click outside both cancel, which is what `.alert`'s `.cancel` role bought and is the
//  only behaviour of it worth reproducing by hand.
//
//  It is deliberately a *confirmation* and not a general alert: a title, a sentence, one action and a
//  way out. Anything that needs a text field, a list, or three verbs is a sheet
//  (`dismissableSheet`), which already draws its dim the same way.
//
//  Brand: `Ink` semantics only — `OmiButtonStyle(.destructive)` for a destructive verb, the shared
//  neutral dim for everything else. No hue is introduced here (INV-UI-1).
//

import OmiTheme
import SwiftUI

/// A confirmation card over a bounded dim: a title, a sentence, the verb, and the way out.
///
/// Presented with `View.shellConfirmation(...)` rather than constructed directly, so the presented
/// state and the accessibility gate on the content behind it stay in one place.
struct ShellConfirmationDialog: View {
  /// The question. Phrased as one — "Reset Onboarding?" — because the buttons are the answers.
  let title: String
  /// What confirming actually does, in a sentence. This is the part a system alert routinely gets
  /// skimmed past, so it says consequences rather than restating the title.
  let message: String
  /// The verb on the confirming button. Never "OK": a confirmation whose button does not name the
  /// action is a confirmation the reader has to scroll back up to understand.
  let confirmTitle: String
  /// Whether confirming destroys something. Drives the one place this product is allowed to raise its
  /// voice (`OmiButtonStyle.Kind.destructive`).
  var isDestructive: Bool = true
  let onConfirm: () -> Void
  let onCancel: () -> Void

  /// The card's width — the shell's other modal card (`UsageLimitPopupView`) already picked this, and
  /// two modals on one window at two widths read as two products.
  static let cardWidth: CGFloat = 380

  var body: some View {
    ZStack {
      // The dim, on the shell's own surface rather than on the window. This is the whole fix; see
      // `ShellModalScrim`.
      ShellModalScrim(onTap: onCancel)

      card
        .frame(width: Self.cardWidth)
        // The card paints no ground of its own; the glass owns it, and brings the corner, the edge
        // and the one ambient shadow with it.
        .inkGlassPanel()
        .accessibilityAddTraits(.isModal)
        // The Escape route, on the card rather than as a full-host sibling. It is a key monitor,
        // not a surface: `EscapeKeyHandlerView` registers against the *window* the moment it has
        // one and returns `nil` from `hitTest`, so its own extent buys nothing — and on this window
        // handing anything the host's extent is how the defect above starts.
        .overlay { OverlayModalEscapeCatcher(action: onCancel) }
    }
    .transition(.opacity.animation(OmiMotion.gated(.easeInOut(duration: 0.2))))
  }

  private var card: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      Text(title)
        .inkStyle(.rowCopy, color: Ink.primary)
        .fixedSize(horizontal: false, vertical: true)

      Text(message)
        .inkStyle(.prose, color: Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)

      HStack(spacing: OmiSpacing.sm) {
        Spacer(minLength: 0)

        Button(action: onCancel) {
          Text("Cancel")
        }
        .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        .keyboardShortcut(.cancelAction)

        Button(action: onConfirm) {
          Text(confirmTitle)
        }
        .buttonStyle(OmiButtonStyle(isDestructive ? .destructive : .primary, size: .compact))
      }
    }
    .padding(OmiSpacing.xxl)
  }
}

extension View {
  /// Presents a confirmation over this surface: a bounded dim, a card, and a way out.
  ///
  /// **Mount it on the surface you want dimmed, not on the control that raises it.** The dim is an
  /// overlay, so its extent is this view's — attached to a row inside a scroll view it would darken
  /// that row. Every other modal in the shell is mounted at page or shell root for the same reason.
  ///
  /// The replacement for `.alert(_:isPresented:)` on any surface inside the main window. See this
  /// file's header for why that modifier cannot be used here.
  func shellConfirmation(
    isPresented: Binding<Bool>,
    title: String,
    message: String,
    confirmTitle: String,
    isDestructive: Bool = true,
    onConfirm: @escaping () -> Void
  ) -> some View {
    // The dialog is modal: while it is up, what is under it must not be reachable by VoiceOver or
    // Full Keyboard Access either. Same gate `dismissableSheet` applies.
    self.accessibilityHidden(isPresented.wrappedValue)
      .overlay {
        if isPresented.wrappedValue {
          ShellConfirmationDialog(
            title: title,
            message: message,
            confirmTitle: confirmTitle,
            isDestructive: isDestructive,
            onConfirm: {
              isPresented.wrappedValue = false
              onConfirm()
            },
            onCancel: { isPresented.wrappedValue = false }
          )
        }
      }
      .omiAnimation(.easeOut(duration: 0.2), value: isPresented.wrappedValue)
  }
}
