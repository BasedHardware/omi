//
//  WindowGlass.swift — the window *around* the glass.
//
//  `InkGlass` owns what the surface is made of: the material, the scrim, the 22 pt corner, the
//  ambient shadow, the light pin. Those numbers and the argument behind them live in that file's
//  header and are **deliberately not restated here** — this line carried `.headerView` and a 0.10
//  scrim for a release after the surface had moved to `.hudWindow` at 0.14, which is what a second
//  copy of somebody else's constants is always worth.
//
//  This owns the other half — the handful of `NSWindow` properties that have to be true for any of
//  that to reach the screen. They are a genuinely separate concern, and they are the half that
//  drifts, because nothing in the file that draws a panel says anything at all about them.
//
//  **The failure this exists to prevent is two grounds.** An `NSVisualEffectView` blending
//  `.behindWindow` samples what is behind the *window*, so a window that still paints its own
//  `backgroundColor` has slipped an opaque sheet between the desktop and the blur. The panel then
//  reads as a flat slab over one desktop and as a muddy one over another, and nothing in the drawing
//  code looks wrong — which is exactly how a surface documented as glass ships opaque.
//
//  It is a function of one `Kind` rather than the same four statements written out in every window,
//  for the same reason `InkGlass` reduced the surface itself to functions of one `Bool`: it puts "a
//  glass window really is transparent" inside reach of a hermetic test (`WindowGlassTests`) and
//  leaves each window with no chrome judgement of its own. The timeline, settings and the search
//  surface each restated the properties by hand, which was three chances per property to disagree —
//  and one of them, the shadow, is genuinely *not* the same answer for all three.
//
//  `OnboardingWindow` is the fourth such window and is deliberately not converted here: it is the
//  reference implementation the rest of the app's glass was read off, and it is being worked on
//  elsewhere. It states the same four properties by hand and agrees with `.floating` exactly;
//  folding it in is the one migration this component still owes.
//

import AppKit

/// How a window carries the app's one piece of glass.
///
/// Only `wear` touches AppKit and only it is `@MainActor`; the two decisions are plain functions of
/// `Kind` so the pairing with `InkGlassStyle` can be asserted without a window at all.
enum WindowGlass {

    /// Which kind of window is carrying it.
    ///
    /// Not a style knob — the two are structurally different objects, and what separates them is who
    /// draws the shadow and whether there is a title bar in the way.
    enum Kind: Equatable, CaseIterable {
        /// The window *is* the panel: borderless and transparent right to its edges, with the glass
        /// inset inside it so the ambient shadow has somewhere to fall (`InkGlassStyle.floating`).
        /// The onboarding card and the search surface.
        case floating
        /// An ordinary titled window whose *inside* is glass (`InkGlassStyle.fullBleed`) — the
        /// timeline and settings. The window frame already owns the corner and the shadow.
        case titled
    }

    /// **Whether AppKit draws the window's own shadow**, which is the one property the two kinds
    /// disagree about and the one that is wrong in a way people can see.
    ///
    /// A floating panel draws a broad, diffuse ambient shadow *inside* its own bounds
    /// (`InkGlassShadow`), and the window is deliberately larger than the panel so it has room to.
    /// AppKit's window shadow traces the window's *frame* — which on such a window is a transparent
    /// rectangle several dozen points bigger than the panel — so leaving it on draws a second,
    /// tighter, rectangular shadow around nothing. On a titled window the frame *is* the panel's
    /// edge and AppKit's shadow is the only correct one.
    ///
    /// Pure, and stated here rather than inside `wear`, so the pairing with `InkGlassStyle` — exactly
    /// one shadow per window, never zero and never two — is a claim a test can hold.
    static func drawsSystemShadow(_ kind: Kind) -> Bool { kind == .titled }

    /// Whether the window has a title bar that has to be got out of the glass's way.
    static func hasTitlebar(_ kind: Kind) -> Bool { kind == .titled }

    /// Puts a window into the state the glass needs, and nothing else.
    ///
    /// Deliberately narrow. Level, collection behaviour, movability, minimum size and first-mouse are
    /// policy each window owns for its own reasons; folding them in here would make this a window
    /// factory rather than the one ground rule, and a caller would then have to fight it.
    @MainActor
    static func wear(_ window: NSWindow, as kind: Kind) {
        // The pin goes on the *window*, not on the content view. `InkGlass` is light in both system
        // appearances, and the parts of a window this app does not draw itself read the window's
        // appearance rather than SwiftUI's environment: the title bar, the traffic lights, the
        // scrollers, and an `NSTextField`'s own resolved `labelColor`. Pinning only the content
        // leaves those in the system's appearance, which on a Dark Mac is a dark title bar on a
        // white sheet, and near-white type on near-white glass in the search field.
        InkGlass.pin(window)

        // The two properties that carry the whole thing. `isOpaque = false` is what lets AppKit
        // composite the window at all; the clear `backgroundColor` is what stops it painting a
        // ground of its own underneath the panel. Either one alone is not enough, which is why they
        // are never written apart.
        window.isOpaque = false
        window.backgroundColor = .clear

        window.hasShadow = drawsSystemShadow(kind)

        guard hasTitlebar(kind) else { return }
        // `.fullSizeContentView` — which the caller sets, because it is part of what the window *is*
        // — plus a transparent title bar is what lets the glass run edge to edge underneath it. The
        // separator is a hairline drawn straight across the panel and belongs to a window with a
        // toolbar; none of these have one, and on glass it reads as a crack.
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.titlebarSeparatorStyle = .none
    }
}
