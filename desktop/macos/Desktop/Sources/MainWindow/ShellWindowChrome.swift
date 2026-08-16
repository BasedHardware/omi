//
//  ShellWindowChrome.swift — what the main window is, now that it has no ground and is summoned.
//
//  This file replaces `ShellGlassGround`, and the reason it replaces it rather than extends it is the
//  whole shape of the shell.
//
//  The ground was an `InkGlassView` installed as the window's `contentView`, so the entire window was
//  one full-bleed slab of glass and every panel floated *on that slab*. It was the right answer to the
//  bug it was written for — a SwiftUI `.background { … }` is laid out inside the hosting view's safe
//  area, and `.hiddenTitleBar` reports `safeAreaInsets.top == 32`, so a SwiftUI ground starts 32 pt down
//  and the top strip shows the backdrop straight through. AppKit ownership fixed that. But it answered
//  the wrong question: the product wants **no ground at all**. What is behind a panel is the user's
//  wallpaper, the way it is behind the surfaces this design system was ported from.
//
//  So the window is now genuinely transparent (`WindowGlass.wear`, which is `isOpaque = false` plus a
//  clear `backgroundColor`) and every surface positions and grounds itself: the top bar, Home's two
//  panels, and `PageGlassLane` for every other destination. **Do not reintroduce a full-bleed SwiftUI
//  background here** — that is the 32 pt seam, drawn again.
//
//  ## The chrome that had to go with it
//
//  A window with no ground still had three coloured circles hanging on the wallpaper at its top-left:
//  the traffic lights, drawn by AppKit over whatever happened to be behind the window, attached to
//  nothing. They read as a rendering fault rather than as controls. So they are hidden, and the two
//  things they were the only visible affordance for are guaranteed another way:
//
//  - **Closing and minimising are style-mask facts, not button facts.** `⌘W` and `⌘M` are routed by
//    AppKit from `.closable` / `.miniaturizable`; hiding `standardWindowButton(_:)` hides a view and
//    changes no behaviour. `dress` re-asserts both bits so a future window-construction change cannot
//    strand a user in a window with no visible close control *and* no keyboard one.
//  - **Moving has one handle.** The hidden title bar is occupied by the visible
//    top bar (`GlassShell.titlebarClearance` is 0), so there is no empty band to
//    drag from above the glass. The visible top bar still drags (`ShellWindowDragHandle`).
//    The native `isMovableByWindowBackground` switch cannot do that safely: AppKit sees a
//    SwiftUI `Button` as its transparent `NSHostingView`, classifies it as background, and
//    steals its click. A root SwiftUI gesture also competes with every Button, Menu, search
//    field, and filter in the shell. The top-bar-only simultaneous gesture preserves those
//    child controls.
//
//  ## It is still an ordinary application window
//
//  Chrome-less is a *drawing* decision. It is not permission to leave AppKit's application-window
//  contract, and the shell did leave it: `.floating` level plus `hidesOnDeactivate` made it a panel
//  that vanished the moment another app took focus. That is unreachable, not transient. A window
//  AppKit has ordered out is in no switcher's list — not ⌘-Tab's window cycling, not AltTab, not
//  Mission Control — so the only ways back to a shell holding the user's chat history were the chord
//  and the menu bar icon, while every other window on the machine was an ⌥-Tab away. A `.floating`
//  shell that stayed up would have been the opposite failure: permanently on top of the app you
//  switched to.
//
//  So both presentations are `.normal` and neither auto-hides. The shell stays where you left it,
//  every switcher can offer it, and putting it away is something the user asks for: ⌘O toggles,
//  Escape and ⌘W dismiss.
//
//  ## The two presentations, and why there are still two
//
//  What separates them is how they join Spaces, and that is behavioural rather than cosmetic.
//  `.summoned` is `.fullScreenAuxiliary` — the chord must be able to bring the shell up *over* a
//  full-screen app, which is the whole point of a global summon. `.anchored` is the same window before
//  the user has an account and a completed setup: a first run sends people to System Settings for
//  microphone, screen recording and accessibility, so onboarding takes a Space of its own
//  (`.fullScreenPrimary`) rather than riding along on someone else's. `ShellSummon` decides which one
//  applies and owns where the window lands — with `dress` idempotent so the switch is a re-dress, not
//  a rebuild.
//
//  Brand: nothing here picks a colour at all (INV-UI-1).
//

import AppKit
import OmiTheme
import SwiftUI

/// The main window's chrome: transparent, light-pinned, and without the system's window buttons.
@MainActor
enum ShellWindowChrome {
  /// Whether the shell is a thing you summon onto whatever Space you are on, or a window that owns a
  /// Space of its own.
  ///
  /// Behavioural, not cosmetic — the two differ only in how the window joins Spaces. Both stay put
  /// when focus moves elsewhere. See this file's header for why a first run needs the second.
  enum Presentation: Equatable, CaseIterable, Sendable {
    /// Steady state: the chord can bring it up over a full-screen app.
    case summoned
    /// Onboarding, sign-in and permission-granting: takes a Space of its own.
    case anchored
  }

  /// The style-mask bits `⌘W` and `⌘M` are routed by.
  ///
  /// Named rather than written inline because the whole safety argument for hiding the buttons is that
  /// these two survive, and a claim a test can read is worth more than a comment saying so.
  static let keyboardWindowCommands: NSWindow.StyleMask = [.closable, .miniaturizable]

  /// The buttons that stop being drawn. All three: a lone close button on a chrome-less window reads
  /// as a stray more strongly than three do.
  static let hiddenStandardButtons: [NSWindow.ButtonType] = [
    .closeButton, .miniaturizeButton, .zoomButton,
  ]

  /// The glass this window wears — **one kind, in both presentations.**
  ///
  /// It used to be `.titled` when anchored, and that was right for exactly as long as
  /// `ShellGlassGround` made the whole window one slab of glass: a titled window's frame *is* the
  /// panel's edge, so AppKit's window shadow is the correct one and the only one.
  ///
  /// The ground is gone. In **both** presentations the window is now a transparent rectangle
  /// the size of the glass (`DesktopWindowLayoutPolicy.windowInset` is 0). AppKit's shadow
  /// would still trace the rectangular frame, including the squircle's leftover corner
  /// triangles, so it stays off. The panels draw their own ambient lift.
  ///
  /// A constant rather than a function of the presentation, because that parameter had one job and no
  /// longer has it. `Presentation` is behavioural — level, Spaces, whether the window survives losing
  /// focus — and what a window's frame draws is not one of those.
  static let glassKind: WindowGlass.Kind = .summoned

  /// How the window joins Spaces.
  ///
  /// A summoned surface is `.fullScreenAuxiliary` — it comes up *over* whatever app is full-screen,
  /// which is the whole point of summoning it. An anchored one is `.fullScreenPrimary` so onboarding
  /// can take a Space of its own. The two are mutually exclusive, so a re-dress must subtract the
  /// other rather than only add its own; a window that accumulated both loses full-screen entirely.
  static func collectionBehavior(
    for presentation: Presentation,
    current: NSWindow.CollectionBehavior
  ) -> NSWindow.CollectionBehavior {
    var behavior = current
    behavior.insert(.moveToActiveSpace)
    if presentation == .summoned {
      behavior.remove(.fullScreenPrimary)
      behavior.insert(.fullScreenAuxiliary)
    } else {
      behavior.remove(.fullScreenAuxiliary)
      behavior.insert(.fullScreenPrimary)
    }
    return behavior
  }

  /// Puts the window into the state the shell needs, and nothing else.
  ///
  /// Idempotent, because all three call sites run more than once: launch applies it, a summon
  /// re-applies it to a window that may have outlived the launch pass, and completing onboarding
  /// re-applies it to switch presentations. Every step here is a property assignment, so a second pass
  /// re-asserts rather than accumulating.
  static func dress(_ window: NSWindow, as presentation: Presentation = .summoned) {
    WindowGlass.wear(window, as: glassKind)
    // Before hiding the buttons, never after: a window that lost the bits would otherwise spend the
    // window between the two calls with no way to be closed at all.
    window.styleMask.formUnion(keyboardWindowCommands)
    hideStandardButtons(in: window)
    // AppKit cannot see SwiftUI controls inside an NSHostingView. The hosting view reports that a
    // mouse-down may move the window even when the point is a Button, so this native switch turns
    // ordinary clicks into window drags. `ShellWindowDragHandle` keeps the explicit top-bar handle in SwiftUI.
    window.isMovableByWindowBackground = false
    // The two properties that decide whether this window exists for the rest of the system. A window
    // switcher can only offer a window that is on screen, and `.normal` is the level an application
    // window is expected to cycle at — assert both in every presentation, so no path can leave the
    // shell as an overlay only its own chord can reach. See this file's header.
    window.level = .normal
    window.hidesOnDeactivate = false
    window.collectionBehavior = collectionBehavior(for: presentation, current: window.collectionBehavior)
  }

  /// Split from `dress` so a test can drive it against a real `NSWindow` and read the buttons back.
  static func hideStandardButtons(in window: NSWindow) {
    for button in hiddenStandardButtons {
      window.standardWindowButton(button)?.isHidden = true
    }
  }

  /// Whether the live window still satisfies the shell contract.
  ///
  /// SwiftUI is allowed to rebuild a scene's title-bar views after launch. Reading the contract before
  /// re-applying it keeps that ordinary update path cheap while still repairing a window whose system
  /// chrome has been recreated underneath us.
  static func isDressed(_ window: NSWindow, as presentation: Presentation) -> Bool {
    let hasExpectedSpaceBehavior: Bool
    switch presentation {
    case .summoned:
      hasExpectedSpaceBehavior =
        window.collectionBehavior.contains(.fullScreenAuxiliary)
        && !window.collectionBehavior.contains(.fullScreenPrimary)
    case .anchored:
      hasExpectedSpaceBehavior =
        window.collectionBehavior.contains(.fullScreenPrimary)
        && !window.collectionBehavior.contains(.fullScreenAuxiliary)
    }

    let buttonsAreHidden = hiddenStandardButtons.allSatisfy { button in
      window.standardWindowButton(button)?.isHidden != false
    }

    return !window.isOpaque
      && window.backgroundColor == .clear
      && !window.hasShadow
      && window.styleMask.contains(.fullSizeContentView)
      && window.styleMask.isSuperset(of: keyboardWindowCommands)
      && window.titlebarAppearsTransparent
      && window.titleVisibility == .hidden
      && window.titlebarSeparatorStyle == .none
      && buttonsAreHidden
      && !window.isMovableByWindowBackground
      && window.level == .normal
      && !window.hidesOnDeactivate
      && window.collectionBehavior.contains(.moveToActiveSpace)
      && hasExpectedSpaceBehavior
  }

  static func draggedOrigin(windowOrigin: NSPoint, translation: CGSize) -> NSPoint {
    NSPoint(
      x: windowOrigin.x + translation.width,
      y: windowOrigin.y - translation.height)
  }
}

/// A drag handle for the visible top bar. It is intentionally not attached to the shell root: a root
/// gesture can participate in every Button, Menu, and TextField event sequence. Simultaneous
/// recognition keeps top-bar controls clickable while preserving drag-to-move on the bar's empty area.
@MainActor
struct ShellWindowDragHandle: ViewModifier {
  @State private var windowOrigin: NSPoint?

  @ViewBuilder
  func body(content: Content) -> some View {
    if #available(macOS 15.0, *) {
      content.simultaneousGesture(WindowDragGesture())
    } else {
      // `WindowDragGesture` was introduced in macOS 15. Keep the macOS 14 deployment floor usable
      // with a lower-precedence gesture: child controls keep their own clicks and drags, while the
      // shell's non-control surfaces remain window handles.
      content.simultaneousGesture(
        DragGesture(minimumDistance: 3)
          .onChanged { value in
            guard let window = ShellSummon.shellWindow() else { return }
            let origin = windowOrigin ?? window.frame.origin
            windowOrigin = origin
            window.setFrameOrigin(
              ShellWindowChrome.draggedOrigin(windowOrigin: origin, translation: value.translation))
          }
          .onEnded { _ in windowOrigin = nil })
    }
  }
}

extension View {
  func shellWindowDragHandle() -> some View {
    modifier(ShellWindowDragHandle())
  }
}

/// Binds the SwiftUI shell to the exact `NSWindow` that contains it.
///
/// The launch delegate used to search `NSApp.windows` once after a fixed 200 ms delay. On a cold or
/// newly patched bundle the scene can mount later than that, leaving the shell in AppKit's default
/// titled, opaque state for the whole session. This zero-sized view receives `viewDidMoveToWindow`
/// from AppKit, so there is no title lookup and no timing assumption. The update observer only writes
/// when SwiftUI has recreated enough title-bar state for the contract to drift.
@MainActor
final class ShellWindowAttachmentView: NSView {
  private weak var attachedWindow: NSWindow?
  private var updateObserver: NSObjectProtocol?
  private var mouseInterceptionSync: ShellMouseInterceptionSync?

  override func viewWillMove(toWindow newWindow: NSWindow?) {
    super.viewWillMove(toWindow: newWindow)
    guard newWindow !== attachedWindow else { return }
    stopObserving()
  }

  override func viewDidMoveToWindow() {
    super.viewDidMoveToWindow()
    guard let window else { return }
    attachedWindow = window
    reassertIfNeeded(force: true)
    // The transparent shell must pass clicks on its dead margins through to whatever is behind
    // the window — see `ShellClickThrough.swift`.
    mouseInterceptionSync = ShellMouseInterceptionSync(window: window)
    updateObserver = NotificationCenter.default.addObserver(
      forName: NSWindow.didUpdateNotification,
      object: window,
      queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated {
        self?.reassertIfNeeded()
      }
    }
  }

  func reassertIfNeeded(force: Bool = false) {
    guard let window = attachedWindow ?? self.window else { return }
    let presentation = ShellSummon.presentation()
    guard force || !ShellWindowChrome.isDressed(window, as: presentation) else { return }
    ShellSummon.applyPresentation(to: window)
  }

  private func stopObserving() {
    if let updateObserver {
      NotificationCenter.default.removeObserver(updateObserver)
      self.updateObserver = nil
    }
    mouseInterceptionSync?.detach()
    mouseInterceptionSync = nil
    attachedWindow = nil
  }
}

struct ShellWindowAttachment: NSViewRepresentable {
  func makeNSView(context: Context) -> ShellWindowAttachmentView {
    ShellWindowAttachmentView(frame: .zero)
  }

  func updateNSView(_ nsView: ShellWindowAttachmentView, context: Context) {
    nsView.reassertIfNeeded()
  }
}
