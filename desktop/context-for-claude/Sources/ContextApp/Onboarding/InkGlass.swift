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
//  **The material is `.hudWindow`, and the number that decides that is the material's own opacity —
//  not the scrim.** This is the correction of an argument that was stated backwards here for two
//  releases, and it is worth writing down because it is the reason two separate attempts to make
//  these panels see-through did nothing the user could perceive.
//
//  The ground under the type is `scrim` of white over `material` over the desktop. Only the
//  *material* has any real depth to it: every translucent candidate is between 50% and 90% opaque on
//  its own, so it, and not the scrim, is what the desktop has to survive. Re-sampled on this machine
//  (macOS 26, `.behindWindow`, `.active`, pinned `.aqua`, over solid black / mid / white full-screen
//  backdrops, solving `composite = tint·a + backdrop·(1−a)`) at **scrim zero** — which is each
//  material at its most transparent, the honest way to rank them:
//
//      material              ground/black  pass     material               ground/black  pass
//      hudWindow                136.2/255  41.2%    menu                      188.4/255  18.8%
//      fullScreenUI             136.2/255  41.2%    titlebar                  208.0/255  15.4%
//      popover                  163.7/255  29.4%    headerView                212.9/255  16.2%
//      selection                193.4/255   8.5%    sidebar / underWindow     213.9/255   7.9%
//      contentBackground / sheet / windowBackground: opaque in `.aqua`.
//
//  The old ranking here held the *ground* fixed at 209.1/255 and asked which material passed the most
//  desktop at that ground, and concluded a pure white tint was optimal and `.headerView` won. That
//  question has the answer backwards, because **209.1 is not the legibility floor — it is well above
//  it.** The floor is whatever ground still lets the *faintest rung anyone sets on the panel* clear
//  WCAG AA over a solid black desktop: ≈203/255 while that rung was `Ink.tertiary`, and **≈152/255**
//  now that it is `Ink.secondary`. `.headerView` is ~84% opaque white on its own, so its
//  ground *bottoms out at 212.9* — it cannot reach the floor at any scrim, and the scrim is therefore
//  the only knob it has, worth 4 points of ground in total. That is precisely what happened: dropping
//  the scrim 0.36 → 0.10 moved this card from 228.0/255 to 217.0/255, eleven levels out of 255, and
//  was reported — correctly — as no change at all.
//
//  `.hudWindow` is 59% opaque at a near-white tint, so it *can* be scrimmed down a long way, and it
//  arrives with more of the desktop still in it than any other candidate. `.fullScreenUI` measures
//  identically and either would do; `.hudWindow` is the semantic match for a floating panel.
//
//  **But the material was never the binding constraint either — the bottom rung of the type ladder
//  was, and that is the thing that has now changed.** Dark type needs a light ground, so the ground
//  can only fall as far as the *faintest* thing anyone sets on it survives. With `Ink.tertiary`
//  (`labelColor` @ 0.68) on the panel, the floor was a ground of ≈203/255 — 17% passthrough, which is
//  pale paper, and which is why "make these panels glassmorphic" was asked for three times and
//  answered three times with a number nobody could see.
//
//  **So glass carries a two-rung ladder: `primary` and `secondary`, and never `tertiary`.** The floor
//  moves with the faintest rung, and the panel moves with the floor. Measured on the real material
//  over a real desktop, at the same non-negotiable 4.5:1:
//
//      ladder on glass       ground over black   passthrough   bottom rung there
//      three rungs (before)        205.5/255        17.0%      tertiary  4.56:1
//      two rungs (now)             154.1/255        34.8%      secondary 4.58:1
//
//  Twice the desktop for the same legibility. That is the whole change; everything else in this file
//  is unchanged, including the material. The rule itself lives on `Ink.tertiary` — it is a rule about
//  the *type*, not about the glass — and it is enforced from both sides in `InkGlassTests`.
//
//  Two cues still cost no contrast at all and are still spent: the broad ambient shadow
//  (`InkGlassShadow`) and the specular top edge (`sheenAlpha`). Both are worth *more* now than they
//  were, because a ground at 154 has real desktop moving under it for them to sit on.
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

    /// `.hudWindow` — measured, not picked. See the file header for the table and the argument.
    static let material: NSVisualEffectView.Material = .hudWindow

    /// The material's own opacity over an arbitrary backdrop, before the scrim goes on.
    ///
    /// A **measurement**: a material's opacity is not published and cannot be derived. Sampled by
    /// putting one window per candidate over a full-screen solid backdrop and solving the composite
    /// on two backdrops (`composite = tint·a + backdrop·(1−a)`; black gives `tint·a`, white gives
    /// `tint·a + (1−a)`). Re-take it, do not adjust it.
    ///
    /// It exists so the contrast guard can be arithmetic instead of a screenshot: a test process has
    /// no desktop behind its windows, so the only way to assert the ladder on glass is to model the
    /// ground. Checked against the real thing at seven scrim values on three backdrops, the model
    /// reproduces the sampled composite to under 3/255.
    ///
    /// **The previous pair of values was stale and the staleness was not harmless.** They recorded
    /// `.headerView` at 0.800/pure-white, sampled on macOS 15.5; re-sampled here it is 0.835, and the
    /// difference is why this file's documented passthrough (18.0%) never matched the panel anyone
    /// looked at (14.5%). A model that flatters the surface is worse than no model, because it is the
    /// thing the contrast guard trusts.
    static let measuredMaterialOpacity: CGFloat = 0.588

    /// …and the tone it contributes, as a fraction of white. `.hudWindow` measures 232/255 — near
    /// white but not white, which costs a little passthrough per point of ground and is paid for many
    /// times over by the material being 25 points less opaque than `.headerView`. Modelled as
    /// white × this so a material with a different tint can be swapped in without rewriting the guard.
    static let measuredMaterialTint: CGFloat = 0.909

    /// `Ink.surface` at 0.14, painted over the material and under the content.
    ///
    /// **This number is meaningless on its own and comparing it across materials is how this surface
    /// was mistuned three times.** It shipped at 0.80, 0.36, 0.10 and 0.56 — each change read as
    /// "thinner glass" and none of the first three was, because the scrim was riding on
    /// `.headerView`, which is ~84% opaque before the scrim is applied at all. The quantity to reason
    /// about is the **ground**, and the quantity to judge the design by is the **passthrough** —
    /// never this alpha.
    ///
    /// Measured on the real material over real backdrops (`.aqua`, `.behindWindow`, `.active`, a
    /// full-screen banded desktop, sampled out of a `screencapture`):
    ///
    /// | material / scrim | ground over black | passthrough | bottom rung on glass |
    /// |---|---|---|---|
    /// | `headerView` 0.10 (shipped, three-rung) | 217.0/255 | 14.5% | `tertiary` 4.74:1 |
    /// | `hudWindow` 0.56 (shipped, three-rung) | 205.5/255 | 17.0% | `tertiary` 4.56:1 |
    /// | `hudWindow` 0.115 | 151.2/255 | 35.9% | `secondary` 4.48:1 — **under AA** |
    /// | **`hudWindow` 0.14** | **154.1/255** | **34.8%** | **`secondary` 4.58:1** |
    /// | `hudWindow` 0.00 — *the material's own ceiling* | 136.2/255 | 41.2% | `secondary` 3.96:1 ✗ |
    ///
    /// **The floor is the faintest rung the panel is allowed to carry, and on glass that is now
    /// `Ink.secondary`.** Dropping the bottom rung — see `Ink.tertiary`, which states the rule — is
    /// what moved this ground 51 points and doubled the passthrough; no change to the material or to
    /// this alpha could have. The remaining budget is under three points of ground: at 0.115 the
    /// panel is illegible over a black desktop. This value sits a point above that boundary because
    /// the two-layer model the contrast guard uses reproduces the sampled composite to about 3/255,
    /// so a scrim tuned to the last tenth would be tuned to noise. Both edges are asserted in
    /// `InkGlassTests.testTheBottomRungIsWhatPaysForTheGlass`.
    ///
    /// **What is left to buy, and it is not much.** The panel's whole range across every desktop that
    /// can exist is 154.1…242.8 of 255 — an 89-level span, against 43 before. Going further means
    /// spending the *second* rung too, which would leave one type colour and no ladder at all, so
    /// this is the end of the road for a light panel carrying dark type. Dark glass is not a way out
    /// either: the binding case inverts (light type is worst over a *white* desktop) and it measures
    /// worse — see `docs/design-system.md`.
    ///
    /// Deliberately flat and full-bleed. A scrim only under the copy is a grey slab, drawn again.
    static let scrim: CGFloat = 0.14

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

    /// The specular highlight along the panel's **top edge only**, on white.
    ///
    /// The one part of "reads as glass" that costs no legibility at all, which is why it is here at
    /// all: the ground is pinned to the contrast floor and cannot be thinned, so everything left has
    /// to come from cues that are not the ground. A bright line along the top edge is how a real
    /// pane of glass catches a light source above it, and it is the difference between a rectangle of
    /// pale grey and an object with a surface. The ambient shadow is the same trick from the other
    /// side — one says "there is air under this", the other says "there is a face on this".
    ///
    /// Top edge only, and not a border: a bright line all the way round is a stroked box, which is
    /// the opposite of the reading wanted. It is white rather than `Ink.primary` for the reason
    /// `Ink.glow` is — a highlight is light, and INV-UI-1 wants that light neutral.
    ///
    /// It brightens the ground where it lands, so it can only *help* dark type; there is no contrast
    /// case to re-derive. One point tall, clipped by the panel's own corner radius.
    static let sheenAlpha: CGFloat = 0.5

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
    /// The specular top edge. See `InkGlass.sheenAlpha` — the glassiness that costs no contrast.
    let sheen = NSView()

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
    /// filled, blurred shape behind the layer's content, and behind a panel that now passes 35% of
    /// what is behind it a filled black rounded rect is not subtle — this cut-out gets more
    /// load-bearing every time the ground gets thinner, not less.
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

        // Above the ground so it is a highlight *on* the surface, and pinned to the top edge by
        // `layout()` rather than by an autoresizing mask — `.maxYMargin` would keep its distance from
        // the top on a resize, which on a window that resizes (the cinematic's landing) leaves the
        // highlight floating in the middle of the card.
        sheen.wantsLayer = true
        panel.addSubview(sheen)

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
        // The top edge, in a flipped-off (AppKit) coordinate space: maxY is the top.
        sheen.frame = NSRect(
            x: 0, y: panel.bounds.maxY - InkGlassView.sheenHeight,
            width: panel.bounds.width, height: InkGlassView.sheenHeight)
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

    /// One point. A highlight is a *line*, not a gradient band — a band reads as a second, lighter
    /// panel stacked on the first, which is the "two grounds" failure this component exists to stop.
    static let sheenHeight: CGFloat = 1

    /// The panel's whole appearance, from one `Bool`. The only branch in this file.
    func apply(reduceTransparency reduced: Bool) {
        material.isHidden = !InkGlass.showsMaterial(reduceTransparency: reduced)
        // A specular highlight is a property of *glass*. Under Reduce Transparency this is an opaque
        // sheet and there is no glass for the light to catch, so the highlight goes with the blur —
        // the same rule the material follows, for the same reason.
        sheen.isHidden = reduced

        let alpha = InkGlass.groundAlpha(reduceTransparency: reduced)
        // Resolved inside the panel's own (pinned) appearance, not read at file scope: a dynamic
        // `NSColor` converted to a `CGColor` anywhere else freezes whichever appearance happened to
        // be current, which on a Dark machine is exactly the near-black ground this replaces.
        panel.effectiveAppearance.performAsCurrentDrawingAppearance {
            ground.layer?.backgroundColor = Ink.nsSurface.withAlphaComponent(alpha).cgColor
            // Fixed white rather than a semantic colour: this is a light source reflecting off the
            // panel's face, not a surface tone, so it must not follow the palette into anything.
            sheen.layer?.backgroundColor = NSColor.white.withAlphaComponent(InkGlass.sheenAlpha).cgColor
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
                // **The sheen is a layer of the stack, not an overlay sitting on top of the clip.**
                //
                // It used to be an `.overlay(alignment: .top)` carrying a `.clipShape(shape)` of its
                // own, which reads as "clipped to the panel" and is not: a `clipShape` is evaluated
                // in the frame of the view it modifies, and that view is `sheenHeight` tall. A 22 pt
                // corner radius inside a ~1 pt box degenerates to a straight bar, so the highlight
                // ran the full width of the card and carried straight past both corners as the glass
                // curved away from it.
                //
                // Reported as two complaints that were one defect: *"there's a weird line showing
                // up… it's not completely rounded"* and *"I can see like weird like boxy edges and
                // it's not completely rounded."* A single hairline across the top is exactly what
                // squares off a rounded card.
                //
                // Inside the stack there is one clip, applied once, in the panel's own coordinate
                // space — so the corner cuts the material, the ground and the highlight together.
                // `InkGlassView` has always drawn it this way; this is the modifier reaching the same
                // result rather than a second, subtly different implementation of it.
                ZStack(alignment: .top) {
                    if InkGlass.showsMaterial(reduceTransparency: reduceTransparency) {
                        InkGlassBackdrop()
                    }
                    Ink.surface.opacity(InkGlass.groundAlpha(reduceTransparency: reduceTransparency))
                    // Hidden under Reduce Transparency for the same reason the material is: there is
                    // no glass to catch the light. The outer `maxHeight` pins it to the top edge
                    // without letting a 1 pt band stretch the stack.
                    if InkGlass.showsMaterial(reduceTransparency: reduceTransparency) {
                        Color.white.opacity(InkGlass.sheenAlpha)
                            .frame(height: InkGlassView.sheenHeight)
                            .frame(maxHeight: .infinity, alignment: .top)
                    }
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
