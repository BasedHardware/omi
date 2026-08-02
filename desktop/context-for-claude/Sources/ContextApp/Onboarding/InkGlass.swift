//
//  InkGlass.swift — the app's one piece of glass.
//
//  Every translucent surface in this app is this component: the onboarding card, the timeline, the
//  settings window, the menu bar popover, the tutorial coach marks, the search bar. Not a shared
//  *style* that each window re-implements — one `NSVisualEffectView`, one scrim, one corner, one
//  shadow, built here and hosted there. A translucent surface has four numbers that have to agree
//  (material, scrim, corner, shadow) and six windows copy-pasting them is six chances to disagree.
//
//  **It is pinned to a light appearance.** `NSVisualEffectView` renders a *different material* in
//  Dark, and the Dark variants are dark: over a `controlBackgroundColor` scrim that resolves to
//  near-black in Dark, the onboarding card read as a black slab pasted over the desktop rather than
//  as glass. Pinning the panel to `.aqua` gets the light material, a white scrim, and — the part
//  that matters and the part that is easy to get wrong — `labelColor` resolving *dark*, so the type
//  on the panel is near-black rather than white-on-white. `InkGlassTests` asserts that flip rather
//  than trusting it.
//
//  **The material is `.headerView`, and it was measured rather than picked.** Fourteen candidate
//  materials were put over a solid black and a solid white full-screen backdrop, pinned to `.aqua`,
//  and sampled (macOS 15.5, `.behindWindow`, `.active`; run under both a Light and a Dark system,
//  which produced identical readings — the pin is what decides). Solving each one's composite for
//  its own opacity and tint:
//
//      material                opacity   tint          material                opacity   tint
//      headerView               0.800    (255,255,255) hudWindow                0.525    (221,221,221)
//      titlebar                 0.809    (246,246,247) fullScreenUI             0.525    (221,221,219)
//      sidebar                  0.903    (228,228,228) popover                  0.651    (229,229,229)
//      menu                     0.776    (227,227,227) underWindowBackground     0.906    (222,222,222)
//      toolTip                  0.902    (222,222,222) selection                0.902    (200,200,200)
//      sheet / windowBackground / contentBackground / underPageBackground: opaque in `.aqua`.
//
//  The choice is not "which is most translucent" — it is "which passes the most desktop through *at
//  a fixed legibility floor*", which is a different question and has a different answer. The floor
//  is `Ink.tertiary` clearing WCAG AA over a solid black desktop (see `scrim`). Writing the ground
//  over black as `255·s + tint·a·(1−s)` and the desktop's share as `(1−a)(1−s)`, a **pure white tint
//  is optimal**: it is the only tint for which brightening the panel costs nothing in passthrough,
//  because the material *is* the brightest thing available. `.headerView` is the only translucent
//  candidate that measures pure white. Solving each candidate for the scrim that lands it on the
//  ground this app now ships (209.1/255): `.headerView` passes **18.0%** of the desktop, `titlebar`
//  and `hudWindow` 15.7%, `popover` 15.1%, `menu` 13.0%, `sidebar` 9.1%. Rendered side by side over
//  a colour wallpaper at equal legibility, they confirm the arithmetic — `.headerView` shows the
//  most of what is behind it, and its lead widens as the ground gets thinner, because the others
//  have to spend scrim making up for a tint that is not white.
//
//  Brand: neutrals and system semantics only, never purple (INV-UI-1). Nothing here reaches for
//  `Ink.accent` at all — glass is defined by its brightness and its shadow, not by a hue.
//

import AppKit
import SwiftUI

// MARK: - The values

/// Everything the glass is made of, as values rather than as statements inside a view.
///
/// A value for the same reason `OnboardingSurface` was one before it: the claims worth asserting are
/// *"Reduce Transparency really produces an opaque ground"* and *"the ladder still clears AA on this
/// ground"*, and `NSWorkspace.accessibilityDisplayShouldReduceTransparency` is a machine setting a
/// hermetic test cannot flip. Reducing the decision to functions of one `Bool` puts it inside reach;
/// the view then has a single branch and no judgement of its own.
enum InkGlass {

    /// The appearance every glass surface is pinned to. See the file header — this is what makes the
    /// panel light *and* what makes the type on it dark.
    static let appearanceName: NSAppearance.Name = .aqua

    /// Resolved, for the places that need the object rather than the name.
    static var appearance: NSAppearance { NSAppearance(named: appearanceName)! }

    /// `.headerView` — measured, not picked. See the file header for the table and the argument.
    static let material: NSVisualEffectView.Material = .headerView

    /// The material's own opacity over an arbitrary backdrop, before the scrim goes on.
    ///
    /// A **measurement**: a material's opacity is not published and cannot be derived. Sampled by
    /// putting one window per candidate over a full-screen solid backdrop and solving the composite
    /// on two backdrops (`composite = tint·a + backdrop·(1−a)`; black gives `tint·a`, white gives
    /// `tint·a + (1−a)`). Re-take it, do not adjust it.
    ///
    /// It exists so the contrast guard can be arithmetic instead of a screenshot: a test process has
    /// no desktop behind its windows, so the only way to assert the ladder on glass is to model the
    /// ground. Checked against the real thing at four scrim values on both backdrops, the model
    /// reproduces the sampled composite to under 1/255.
    static let measuredMaterialOpacity: CGFloat = 0.80

    /// …and the tone it contributes, as a fraction of white. `.headerView` measures pure white on
    /// this machine, which is the property that made it the best material at a fixed legibility
    /// floor. Modelled as white × this so a future material with a tint can be swapped in without
    /// rewriting the guard.
    static let measuredMaterialTint: CGFloat = 1.0

    /// `Ink.surface` at 0.10, painted over the material and under the content. It shipped at 0.80,
    /// then at 0.36, and is now a tenth — the panel was still reported as reading more like paper
    /// than like glass.
    ///
    /// **The whiteness is what matters, not where it comes from.** Both the material's tint and this
    /// scrim are pure white, so over a black desktop the ground is `255·s + 255·a·(1−s)` and the
    /// desktop's surviving share is exactly `1 − ground`: passthrough is a function of the *final*
    /// ground alone, and it makes no difference whether the whiteness was contributed by the
    /// material or by the scrim. That is why the material's own alpha is never touched — dimming an
    /// `NSVisualEffectView` does not thin the ground, it lets a *sharp*, unblurred desktop past the
    /// blur, which is the one thing legibility on glass cannot survive.
    ///
    /// So there are only two numbers: this one and `Ink.tertiary`, the bottom rung of the label
    /// ladder and the rung that binds. The ceiling is `1 − 0.800 = 20%` — the material is the
    /// brightest thing macOS offers and no scrim can pass more of the desktop than it already does.
    ///
    /// | scrim | ground over black | passthrough | `tertiary` there |
    /// |---|---|---|---|
    /// | 0.36 (was) | 222.4/255 | 12.8% | 4.55:1 at alpha 0.66 |
    /// | **0.10** | **209.1/255** | **18.0%** | **4.62:1 at alpha 0.68** |
    /// | 0.00 | 204.0/255 | 20.0% | 4.54:1 at alpha 0.68 |
    ///
    /// **The scrim is no longer the floor — `Ink.tertiary` is.** At the old 0.66 this rung needed a
    /// ground of 219/255 just to clear AA, which is what capped every panel in the app at 14.1%; two
    /// points of alpha on that one token clear AA on *no* scrim at all, so the panel now spends 18.0
    /// of the 20.0 points available instead of 12.8. The last two are kept as the model's margin:
    /// the arithmetic here reproduces the sampled composite to under 1/255, but a surface with
    /// nothing of its own left is a hole rather than a panel, and it is this alpha — not the
    /// material — that goes to 1 under Reduce Transparency.
    ///
    /// Thinning it further is nearly free and nearly pointless (2 points), and *thickening* it is
    /// the change to be suspicious of: it is the direction that quietly walks the surface back
    /// towards paper. The value that must not move without re-deriving both is `Ink.tertiary`.
    ///
    /// Deliberately flat and full-bleed. A scrim only under the copy is a grey slab, drawn again.
    static let scrim: CGFloat = 0.10

    /// The corner every panel is cut to.
    ///
    /// 22 and not the 16 this app used: at 16 a large panel reads as a dialog, and the floating
    /// glass this is modelled on is noticeably rounder. It is one value for every panel on purpose —
    /// a 56 pt search bar and a 760 pt timeline rounded differently read as two products.
    static let cornerRadius: CGFloat = 22

    /// The alpha of the panel's edge, on `labelColor`.
    ///
    /// Much fainter than `Ink.hairline` (0.22), which is the outline of a *control*. A panel that
    /// needs a drawn border is a panel whose brightness and shadow are not doing their job; this is
    /// barely there, and it exists only to keep the top edge from dissolving into a light desktop.
    static let edgeAlpha: CGFloat = 0.06

    /// The alpha of the `Ink.surface` ground, given the user's Reduce Transparency setting.
    ///
    /// Opaque when the setting is on, and the material goes with it — glass that ignores the setting
    /// is not a softer version of honouring it, it is the defect the setting exists for.
    static func groundAlpha(reduceTransparency: Bool) -> CGFloat {
        reduceTransparency ? 1 : scrim
    }

    /// Whether the blurred material is drawn at all. False under Reduce Transparency: with an opaque
    /// ground over it the blur is invisible, and a hidden `NSVisualEffectView` stops sampling the
    /// desktop every frame.
    static func showsMaterial(reduceTransparency: Bool) -> Bool {
        !reduceTransparency
    }

    /// Pins a whole window to the glass appearance.
    ///
    /// For the two windows that have real chrome — the timeline and settings — where pinning only
    /// the content view would leave the title bar and the traffic lights in the system's appearance
    /// and the window visibly half-converted.
    static func pin(_ window: NSWindow) {
        window.appearance = appearance
    }
}

// MARK: - The shadow

/// The broad ambient shadow under a floating panel.
///
/// Not a drop shadow. The floating quality in the reference comes almost entirely from a wide,
/// diffuse, low-opacity shadow — a tight 1 pt one reads as a sticker. It is one value for every
/// panel size for the same reason the corner is: two floating objects on the same desktop with
/// different shadows read as two different materials.
struct InkGlassShadow: Equatable {
    var radius: CGFloat
    var opacity: Float
    var offsetY: CGFloat

    /// How much clear margin the panel needs *inside its window* for this shadow to render.
    ///
    /// A borderless window clips at its own bounds, so a panel drawn edge to edge has nowhere to
    /// cast into. Callers size their window to the panel plus twice this.
    var padding: CGFloat { radius + abs(offsetY) + 12 }

    /// The one shadow.
    static let ambient = InkGlassShadow(radius: 34, opacity: 0.24, offsetY: -10)
}

// MARK: - The style

/// How a particular surface wears the glass. Two cases in practice, and they are not variations on
/// a theme — one is a free-floating object over the desktop, the other is the inside of a window
/// that already has its own frame and shadow from AppKit.
struct InkGlassStyle: Equatable {
    var cornerRadius: CGFloat
    /// `nil` for a surface whose shadow is drawn by someone else — an ordinary window frame, or a
    /// SwiftUI `.shadow` further out.
    var shadow: InkGlassShadow?
    /// Whether to draw the faint edge. Off for a full-bleed surface, where the window's own frame is
    /// the edge.
    var drawsEdge: Bool
    /// The margin the panel is inset by inside its host view, so the shadow has somewhere to fall.
    var inset: CGFloat

    /// A free-floating panel over the desktop: rounded, edged, and casting the ambient shadow. The
    /// window hosting it must be borderless, transparent, and `hasShadow = false`.
    static let floating = InkGlassStyle(
        cornerRadius: InkGlass.cornerRadius, shadow: .ambient, drawsEdge: true,
        inset: InkGlassShadow.ambient.padding)

    /// The inside of an ordinary titled window — the timeline, settings. Square and shadowless
    /// because the window frame already owns both.
    static let fullBleed = InkGlassStyle(
        cornerRadius: 0, shadow: nil, drawsEdge: false, inset: 0)

    /// A panel filling its host exactly, with no shadow of its own. For a surface embedded in a view
    /// tree that already positions and shadows it — a SwiftUI `.background`, a coach mark.
    static func panel(cornerRadius: CGFloat = InkGlass.cornerRadius) -> InkGlassStyle {
        InkGlassStyle(cornerRadius: cornerRadius, shadow: nil, drawsEdge: true, inset: 0)
    }
}

// MARK: - The view

/// The panel: ambient shadow, material, scrim, corner and edge, with the caller's content on top.
///
/// The ground is AppKit's and not SwiftUI's, all of it, so there is exactly one owner of "what is
/// under the type" and the hosted SwiftUI stays entirely transparent. Two grounds is how a
/// translucent surface ends up opaque in one appearance and muddy in the other.
///
/// `apply(reduceTransparency:)` takes the setting rather than reading it for one reason:
/// `NSWorkspace.accessibilityDisplayShouldReduceTransparency` is a machine setting a hermetic test
/// cannot flip — on a modern macOS not even `defaults write` can, the domain is protected — so a
/// view that reads it directly has an accessibility path nothing can ever assert. Passing it in
/// makes "the setting really produces an opaque panel" a test rather than a promise.
final class InkGlassView: NSView {

    /// The glass itself: clipped to the corner, pinned to the light appearance. Content goes in here.
    let panel = NSView()
    let material = NSVisualEffectView()
    /// The scrim. A view rather than a sublayer so it sits in the same ordering as the hosted
    /// content and cannot end up drawn over it by a later `addSubview`.
    let ground = NSView()

    private(set) var style: InkGlassStyle

    /// The corner, settable after construction so a panel whose radius is driven by its content
    /// (a SwiftUI caller) does not have to rebuild the view to change it.
    var cornerRadius: CGFloat {
        get { style.cornerRadius }
        set {
            guard newValue != style.cornerRadius else { return }
            style.cornerRadius = newValue
            panel.layer?.cornerRadius = newValue
            needsLayout = true
        }
    }

    /// Draws nothing itself; it exists to own a `shadowPath` and a mask that keeps the shadow from
    /// falling *under* the panel. It would otherwise: Core Animation renders a `shadowPath` as a
    /// filled, blurred shape behind the layer's content, and behind an 18%-transparent panel a
    /// filled black rounded rect is very much visible — more so now than when the scrim was 0.36,
    /// which is the half of this component that a thinner ground makes *more* load-bearing.
    private let shadowHost = NSView()
    private var observer: (any NSObjectProtocol)?

    init(frame: NSRect, style: InkGlassStyle = .floating) {
        self.style = style
        super.init(frame: frame)
        wantsLayer = true

        shadowHost.wantsLayer = true
        addSubview(shadowHost)

        panel.wantsLayer = true
        panel.layer?.cornerRadius = style.cornerRadius
        // `.continuous` is the squircle every card in this app is cut with; `masksToBounds` is what
        // makes the material respect the corner at all — an `NSVisualEffectView` draws its own
        // rectangle otherwise, which is the straight edge that kept these windows off glass before.
        panel.layer?.cornerCurve = .continuous
        panel.layer?.masksToBounds = true
        panel.layer?.borderWidth = style.drawsEdge ? 1 : 0
        // The pin. Everything inside the panel — including a hosted `NSHostingView` and therefore
        // SwiftUI's `colorScheme` — resolves in this appearance.
        panel.appearance = InkGlass.appearance
        addSubview(panel)

        material.material = InkGlass.material
        // `.behindWindow`, so the blur is of the desktop rather than of this window's own content —
        // `.withinWindow` would frost the panel's own type.
        material.blendingMode = .behindWindow
        // `.active` and not `.followsWindowActiveState`: these windows are presented by an
        // `.accessory` app and spend much of their life inactive (the browser during sign-in, a TCC
        // prompt), and a panel that goes flat grey whenever the user answers a system dialog reads
        // as broken.
        material.state = .active
        material.autoresizingMask = [.width, .height]
        panel.addSubview(material)

        ground.wantsLayer = true
        ground.autoresizingMask = [.width, .height]
        panel.addSubview(ground)

        applyCurrentSettings()
        // The user can flip Reduce Transparency while a window is up — someone struggling to read a
        // first-run card is exactly who reaches for the setting — so the panel watches for it rather
        // than sampling once at construction.
        observer = NSWorkspace.shared.notificationCenter.addObserver(
            forName: InkReduceTransparency.didChangeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.applyCurrentSettings() }
        }
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { nil }

    deinit {
        if let observer { NSWorkspace.shared.notificationCenter.removeObserver(observer) }
    }

    /// Accepted for the reason every view in these windows accepts it: the app is an `.accessory`, so
    /// it is never frontmost when a panel appears, and AppKit otherwise spends the user's first click
    /// activating the window instead of delivering it to the control underneath.
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    /// Hosts a content view inside the panel, filling it.
    ///
    /// The seam every window uses: build your `NSHostingView`, hand it here, and the glass owns
    /// everything under it. Autoresizing rather than constraints, because these panels are resized by
    /// their windows (`OnboardingWindow`'s cinematic lands by resizing one) and a constraint-based
    /// child of a borderless window is the shape that crashes in `_postWindowNeedsUpdateConstraints`.
    func setContent(_ view: NSView) {
        view.frame = panel.bounds
        view.autoresizingMask = [.width, .height]
        panel.addSubview(view)
    }

    /// Where the glass actually is inside this view. A caller that has to position something against
    /// the panel — a pointer, a tail — reads it from here rather than re-deriving the inset.
    var panelFrame: NSRect { bounds.insetBy(dx: style.inset, dy: style.inset) }

    /// A frame-based view does not always get a `layout()` pass from a resize on its own, and this
    /// one is autoresized by every window that hosts it. Without this, a resized window leaves the
    /// panel at its old size — which on the onboarding card is the cinematic landing on a glass
    /// rectangle the size of the whole display.
    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        needsLayout = true
    }

    override func layout() {
        super.layout()
        let frame = panelFrame
        panel.frame = frame
        material.frame = panel.bounds
        ground.frame = panel.bounds
        shadowHost.frame = bounds
        applyShadow()
    }

    /// The palette is dynamic and the panel is pinned, so the pin has to be re-asserted and the
    /// resolved colours re-read whenever the appearance changes. AppKit calls this for the latter.
    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        applyCurrentSettings()
    }

    private func applyCurrentSettings() {
        apply(reduceTransparency: InkReduceTransparency.isEnabled)
    }

    /// The panel's whole appearance, from one `Bool`. The only branch in this file.
    func apply(reduceTransparency reduced: Bool) {
        material.isHidden = !InkGlass.showsMaterial(reduceTransparency: reduced)

        let alpha = InkGlass.groundAlpha(reduceTransparency: reduced)
        // Resolved inside the panel's own (pinned) appearance, not read at file scope: a dynamic
        // `NSColor` converted to a `CGColor` anywhere else freezes whichever appearance happened to
        // be current, which on a Dark machine is exactly the near-black ground this replaces.
        panel.effectiveAppearance.performAsCurrentDrawingAppearance {
            ground.layer?.backgroundColor = Ink.nsSurface.withAlphaComponent(alpha).cgColor
            panel.layer?.borderColor = style.drawsEdge
                ? Ink.nsPrimary.withAlphaComponent(InkGlass.edgeAlpha).cgColor
                : NSColor.clear.cgColor
        }
        applyShadow()
    }

    private func applyShadow() {
        guard let shadow = style.shadow, let layer = shadowHost.layer else {
            shadowHost.layer?.shadowOpacity = 0
            return
        }
        let frame = panelFrame
        guard frame.width > 0, frame.height > 0 else { return }
        let radius = style.cornerRadius
        layer.shadowColor = NSColor.black.cgColor
        // Under Reduce Transparency the panel is opaque, but it is still a floating object over the
        // desktop and still needs to read as one, so the shadow stays.
        layer.shadowOpacity = shadow.opacity
        layer.shadowRadius = shadow.radius
        layer.shadowOffset = CGSize(width: 0, height: shadow.offsetY)
        layer.shadowPath = CGPath(
            roundedRect: frame, cornerWidth: radius, cornerHeight: radius, transform: nil)

        // Everything except the panel's own footprint. Inset by a point so the cut-out is always
        // smaller than the panel drawn over it and no seam can show at the corners, where a
        // continuous squircle and `CGPath`'s circular corner do not quite agree.
        let cut = CAShapeLayer()
        cut.fillRule = .evenOdd
        let path = CGMutablePath()
        path.addRect(bounds.insetBy(dx: -shadow.radius * 4, dy: -shadow.radius * 4))
        path.addPath(
            CGPath(
                roundedRect: frame.insetBy(dx: 1, dy: 1),
                cornerWidth: radius, cornerHeight: radius, transform: nil))
        cut.path = path
        layer.mask = cut
    }
}

// MARK: - SwiftUI

/// The same glass, for a panel that is drawn *inside* SwiftUI rather than being a window root — the
/// tutorial's coach marks, which float in a shared full-screen overlay window and cannot each own an
/// `NSWindow`.
///
/// It is the same material, scrim, corner and shadow, reached a different way, because there is no
/// third option: SwiftUI's own `Material` is within-window vibrancy and blurs the app's content
/// rather than the desktop, so a SwiftUI-only card over the desktop is not glass at all.
struct InkGlassBackdrop: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = InkGlass.material
        view.blendingMode = .behindWindow
        view.state = .active
        view.appearance = InkGlass.appearance
        return view
    }

    func updateNSView(_ view: NSVisualEffectView, context: Context) {}
}

/// The whole panel — material, scrim, corner, edge — as one SwiftUI view, for a caller that wants to
/// place and shadow it itself.
///
/// `inkGlassPanel(…)` is the modifier most callers want; this is the same glass for a view tree that
/// needs the surface as a value rather than as a background, and it is the AppKit `InkGlassView`
/// rather than a second stack of layers, so there is still only one glass in the app.
struct InkGlassSurface: NSViewRepresentable {
    var cornerRadius: CGFloat = InkGlass.cornerRadius

    func makeNSView(context: Context) -> InkGlassView {
        InkGlassView(frame: .zero, style: .panel(cornerRadius: cornerRadius))
    }

    func updateNSView(_ view: InkGlassView, context: Context) {
        view.cornerRadius = cornerRadius
    }
}

extension View {
    /// Wears the glass: material, scrim, corner, faint edge, ambient shadow — and the light
    /// appearance, forced into the environment so `Ink`'s dynamic colours resolve dark on it.
    ///
    /// - Parameter reduceTransparency: passed in rather than read, for the same reason
    ///   `InkGlassView.apply(reduceTransparency:)` takes it — see that method.
    @ViewBuilder
    func inkGlassPanel(
        cornerRadius: CGFloat = InkGlass.cornerRadius,
        shadow: InkGlassShadow? = .ambient,
        reduceTransparency: Bool = InkReduceTransparency.isEnabled
    ) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        self
            .environment(\.colorScheme, .light)
            .background {
                ZStack {
                    if InkGlass.showsMaterial(reduceTransparency: reduceTransparency) {
                        InkGlassBackdrop()
                    }
                    Ink.surface.opacity(InkGlass.groundAlpha(reduceTransparency: reduceTransparency))
                }
                .environment(\.colorScheme, .light)
                .clipShape(shape)
                .overlay(shape.strokeBorder(Ink.glassEdge, lineWidth: 1))
                .shadow(
                    color: .black.opacity(shadow.map { Double($0.opacity) } ?? 0),
                    // SwiftUI's blur radius is half Core Animation's for the same visual spread.
                    radius: (shadow?.radius ?? 0) / 2,
                    y: -(shadow?.offsetY ?? 0))
            }
    }
}
