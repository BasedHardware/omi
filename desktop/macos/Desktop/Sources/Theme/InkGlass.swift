//
//  InkGlass.swift — the app's one piece of glass.
//
//  Ported from Context for Claude's `InkGlass.swift`. Every translucent surface built on this system
//  is this component: not a shared *style* that each window re-implements, but one
//  `NSVisualEffectView`, one scrim, one corner, one shadow, built here and hosted there. A translucent
//  surface has four numbers that have to agree (material, scrim, corner, shadow) and six windows
//  copy-pasting them is six chances to disagree.
//
//  **It is pinned to a light appearance, deliberately.** `NSVisualEffectView` renders a *different*
//  material in Dark, and the Dark variants are dark: over a `controlBackgroundColor` scrim that
//  resolves to near-black in Dark, the panel reads as a black slab pasted over the desktop rather than
//  as glass. Pinning to `.aqua` gets the light material, a white scrim, and — the part that matters and
//  the part that is easy to get wrong — `labelColor` resolving *dark*, so the type on the panel is
//  near-black rather than white-on-white. This is a product decision, not a default: the panel does not
//  follow the system appearance.
//
//  **The material is `.hudWindow`, and the number that decides that is the material's own opacity —
//  not the scrim.** Re-sampled on real hardware (`.behindWindow`, `.active`, pinned `.aqua`, over solid
//  black / mid / white full-screen backdrops, solving `composite = tint·a + backdrop·(1−a)`) at **scrim
//  zero** — which is each material at its most transparent, the honest way to rank them:
//
//      material              ground/black  pass     material               ground/black  pass
//      hudWindow                136.2/255  41.2%    menu                      188.4/255  18.8%
//      fullScreenUI             136.2/255  41.2%    titlebar                  208.0/255  15.4%
//      popover                  163.7/255  29.4%    headerView                212.9/255  16.2%
//      selection                193.4/255   8.5%    sidebar / underWindow     213.9/255   7.9%
//      contentBackground / sheet / windowBackground: opaque in `.aqua`.
//
//  Ranking materials at a *fixed ground* asks the wrong question, because the floor is not a ground
//  someone picked — it is whatever ground still lets the *faintest rung anyone sets on the panel* clear
//  WCAG AA over a solid black desktop. `.headerView` is ~84% opaque white on its own, so its ground
//  bottoms out at 212.9 and the scrim is worth four points of ground in total; that is why two separate
//  attempts to make these panels see-through changed nothing anybody could perceive.
//
//  **But the material was never the binding constraint either — the bottom rung of the type ladder
//  was.** Dark type needs a light ground, so the ground can only fall as far as the *faintest* thing
//  anyone sets on it survives:
//
//      ladder on glass       ground over black   passthrough   bottom rung there
//      three rungs                 205.5/255        17.0%      tertiary  4.56:1
//      two rungs (this)            154.1/255        34.8%      secondary 4.58:1
//
//  Twice the desktop for the same legibility. The rule itself lives on `Ink.tertiary` — it is a rule
//  about the *type*, not about the glass.
//
//  Two cues cost no contrast at all and are therefore spent: the broad ambient shadow
//  (`InkGlassShadow`) and the specular top edge (`sheenAlpha`). Both are worth more at a ground of 154
//  than they were at 205, because there is real desktop moving under them.
//
//  Brand: neutrals and system semantics only (INV-UI-1). Nothing here reaches for `Ink.accent` at all —
//  glass is defined by its brightness and its shadow, not by a hue.
//
//  **What the glass costs to composite — measured, so it is not guessed at again.** "The blur is
//  expensive" is the obvious hypothesis when this design system is blamed for a slow window, and it is
//  wrong. Measured by pairing: one process alternating between two configurations every 2 s, so both
//  arms see the same machine load, and only the paired difference is read.
//
//      configuration                                       per frame        verdict
//      the ground's `.behindWindow` blur, on vs off        +0.065 ms (+0.9%)  free
//      3 further `.behindWindow` panels nested in it       +0.13 ms  (+1.8%)  free
//      `glassScrollFade`'s mask, on a real NSScrollView    +0.002 ms (+2.3%)  free
//      3 × SwiftUI `.shadow(radius: 17)` (alpha-derived)   +0.03 ms  (+0.5%)  free
//
//  The window server caches a blurred backdrop and re-derives it when the *backdrop* moves, not when
//  the window's own content redraws — so scrolling and navigating cost the blur nothing. On the same
//  run the window server's CPU went 78.9% → 78.0% when the ground's material was hidden, i.e. the
//  ground is not distinguishable from noise.
//
//  The one cost that is real is **mounting**, not drawing: each `.behindWindow` view registers a
//  sampling region with the window server as it enters a window, which measures ≈0.9 ms. A navigation
//  that mounts five of them pays +3.6–4.9 ms (+14% median, reproduced over three runs) on a page mount
//  that costs 27–50 ms in total — so the glass is a few percent of a navigation and the rest is the
//  view tree being built. Pooling the views to dodge the allocation recovers ~1%: the cost is the
//  registration, not the `alloc`. Before optimising anything here, check that number is still small
//  against the total; it was never the reason a window felt slow.
//

import AppKit
import SwiftUI

// MARK: - The values

/// Everything the glass is made of, as values rather than as statements inside a view.
///
/// A value because the claims worth asserting are *"Reduce Transparency really produces an opaque
/// ground"* and *"the ladder still clears AA on this ground"*, and
/// `NSWorkspace.accessibilityDisplayShouldReduceTransparency` is a machine setting a hermetic test
/// cannot flip. Reducing the decision to functions of one `Bool` puts it inside reach; the view then
/// has a single branch and no judgement of its own.
package enum InkGlass {
  /// The appearance every glass surface is pinned to. See the file header — this is what makes the
  /// panel light *and* what makes the type on it dark. Pinned exactly, never system-following.
  package static let appearanceName: NSAppearance.Name = .aqua

  /// Resolved, for the places that need the object rather than the name.
  ///
  /// `.aqua` is a system-guaranteed appearance name, so the lookup cannot fail; a computed property
  /// rather than a stored one because `NSAppearance` is a reference type and not `Sendable`.
  package static var appearance: NSAppearance {
    guard let appearance = NSAppearance(named: appearanceName) else {
      preconditionFailure("NSAppearance(named: .aqua) is guaranteed by AppKit")
    }
    return appearance
  }

  /// `.hudWindow` — measured, not picked. See the file header for the table and the argument.
  package static let material: NSVisualEffectView.Material = .hudWindow

  /// The material's own opacity over an arbitrary backdrop, before the scrim goes on.
  ///
  /// A **measurement**: a material's opacity is not published and cannot be derived. Sampled by putting
  /// one window per candidate over a full-screen solid backdrop and solving the composite on two
  /// backdrops (`composite = tint·a + backdrop·(1−a)`; black gives `tint·a`, white gives
  /// `tint·a + (1−a)`). Re-take it, do not adjust it.
  ///
  /// It exists so a contrast guard can be arithmetic instead of a screenshot: a test process has no
  /// desktop behind its windows, so the only way to assert the ladder on glass is to model the ground.
  /// Checked against the real thing at seven scrim values on three backdrops, the model reproduces the
  /// sampled composite to under 3/255.
  package static let measuredMaterialOpacity: CGFloat = 0.588

  /// …and the tone it contributes, as a fraction of white. `.hudWindow` measures 232/255 — near white
  /// but not white, which costs a little passthrough per point of ground and is paid for many times
  /// over by the material being 25 points less opaque than `.headerView`. Modelled as white × this so a
  /// material with a different tint can be swapped in without rewriting the guard.
  package static let measuredMaterialTint: CGFloat = 0.909

  /// `Ink.surface` at 0.14, painted over the material and under the content.
  ///
  /// **This number is meaningless on its own and comparing it across materials is how this surface was
  /// mistuned three times.** The quantity to reason about is the **ground**, and the quantity to judge
  /// the design by is the **passthrough** — never this alpha.
  ///
  /// Measured on the real material over real backdrops (`.aqua`, `.behindWindow`, `.active`, a
  /// full-screen banded desktop, sampled out of a `screencapture`):
  ///
  /// | material / scrim | ground over black | passthrough | bottom rung on glass |
  /// |---|---|---|---|
  /// | `headerView` 0.10 (three-rung) | 217.0/255 | 14.5% | `tertiary` 4.74:1 |
  /// | `hudWindow` 0.56 (three-rung) | 205.5/255 | 17.0% | `tertiary` 4.56:1 |
  /// | `hudWindow` 0.115 | 151.2/255 | 35.9% | `secondary` 4.48:1 — **under AA** |
  /// | **`hudWindow` 0.14** | **154.1/255** | **34.8%** | **`secondary` 4.58:1** |
  /// | `hudWindow` 0.00 — *the material's own ceiling* | 136.2/255 | 41.2% | `secondary` 3.96:1 ✗ |
  ///
  /// **The floor is the faintest rung the panel is allowed to carry, and on glass that is
  /// `Ink.secondary`.** The remaining budget is under three points of ground: at 0.115 the panel is
  /// illegible over a black desktop. This value sits a point above that boundary because the two-layer
  /// model reproduces the sampled composite to about 3/255, so a scrim tuned to the last tenth would be
  /// tuned to noise.
  ///
  /// Deliberately flat and full-bleed. A scrim only under the copy is a grey slab, drawn again.
  package static let scrim: CGFloat = 0.14

  /// The corner every panel is cut to.
  ///
  /// One value for every panel on purpose — a 56 pt search bar and a 760 pt timeline rounded
  /// differently read as two products.
  package static let cornerRadius: CGFloat = 22

  /// The alpha of the panel's edge, on `labelColor`.
  ///
  /// Much fainter than `Ink.hairline` (0.22), which is the outline of a *control*. A panel that needs a
  /// drawn border is a panel whose brightness and shadow are not doing their job; this is barely there,
  /// and it exists only to keep the top edge from dissolving into a light desktop.
  package static let edgeAlpha: CGFloat = 0.06

  /// The specular highlight along the panel's **top edge only**, on white.
  ///
  /// The one part of "reads as glass" that costs no legibility at all, which is why it is here: the
  /// ground is pinned to the contrast floor and cannot be thinned, so everything left has to come from
  /// cues that are not the ground. A bright line along the top edge is how a real pane of glass catches
  /// a light source above it, and it is the difference between a rectangle of pale grey and an object
  /// with a surface.
  ///
  /// Top edge only, and not a border: a bright line all the way round is a stroked box, which is the
  /// opposite of the reading wanted. It is white rather than `Ink.primary` for the reason `Ink.glow`
  /// is — a highlight is light, and INV-UI-1 wants that light neutral.
  package static let sheenAlpha: CGFloat = 0.5

  /// The alpha of the `Ink.surface` ground, given the user's Reduce Transparency setting.
  ///
  /// Opaque when the setting is on, and the material goes with it — glass that ignores the setting is
  /// not a softer version of honouring it, it is the defect the setting exists for.
  package static func groundAlpha(reduceTransparency: Bool) -> CGFloat {
    reduceTransparency ? 1 : scrim
  }

  /// Whether the blurred material is drawn at all. False under Reduce Transparency: with an opaque
  /// ground over it the blur is invisible, and a hidden `NSVisualEffectView` stops sampling the desktop
  /// every frame.
  package static func showsMaterial(reduceTransparency: Bool) -> Bool {
    !reduceTransparency
  }

  /// Pins a whole window to the glass appearance.
  ///
  /// For windows that have real chrome, where pinning only the content view would leave the title bar
  /// and the traffic lights in the system's appearance and the window visibly half-converted.
  @MainActor
  package static func pin(_ window: NSWindow) {
    window.appearance = appearance
  }
}

// MARK: - The shadow

/// The broad ambient shadow under a floating panel.
///
/// Not a drop shadow. The floating quality comes almost entirely from a wide, diffuse, low-opacity
/// shadow — a tight 1 pt one reads as a sticker. It is one value for every panel size for the same
/// reason the corner is: two floating objects on the same desktop with different shadows read as two
/// different materials.
package struct InkGlassShadow: Equatable, Sendable {
  package var radius: CGFloat
  package var opacity: Float
  package var offsetY: CGFloat

  package init(radius: CGFloat, opacity: Float, offsetY: CGFloat) {
    self.radius = radius
    self.opacity = opacity
    self.offsetY = offsetY
  }

  /// How much clear margin the panel needs *inside its window* for this shadow to render.
  ///
  /// A borderless window clips at its own bounds, so a panel drawn edge to edge has nowhere to cast
  /// into. Callers size their window to the panel plus twice this.
  package var padding: CGFloat { radius + abs(offsetY) + 12 }

  /// The one shadow.
  package static let ambient = InkGlassShadow(radius: 34, opacity: 0.24, offsetY: -10)
}

// MARK: - The style

/// How a particular surface wears the glass. Three cases, and they are not variations on a theme — one
/// is a free-floating object over the desktop, one is the inside of a window that already has its own
/// frame and shadow from AppKit, one fills a host something else already positions.
package struct InkGlassStyle: Equatable, Sendable {
  package var cornerRadius: CGFloat
  /// `nil` for a surface whose shadow is drawn by someone else — an ordinary window frame, or a SwiftUI
  /// `.shadow` further out.
  package var shadow: InkGlassShadow?
  /// Whether to draw the faint edge. Off for a full-bleed surface, where the window's own frame is the
  /// edge.
  package var drawsEdge: Bool
  /// The margin the panel is inset by inside its host view, so the shadow has somewhere to fall.
  package var inset: CGFloat

  package init(cornerRadius: CGFloat, shadow: InkGlassShadow?, drawsEdge: Bool, inset: CGFloat) {
    self.cornerRadius = cornerRadius
    self.shadow = shadow
    self.drawsEdge = drawsEdge
    self.inset = inset
  }

  /// A free-floating panel over the desktop: rounded, edged, and casting the ambient shadow. The window
  /// hosting it must be borderless, transparent, and `hasShadow = false` — see `WindowGlass`.
  package static let floating = InkGlassStyle(
    cornerRadius: InkGlass.cornerRadius, shadow: .ambient, drawsEdge: true,
    inset: InkGlassShadow.ambient.padding)

  /// The inside of an ordinary titled window. Square and shadowless because the window frame already
  /// owns both.
  package static let fullBleed = InkGlassStyle(
    cornerRadius: 0, shadow: nil, drawsEdge: false, inset: 0)

  /// A panel filling its host exactly, with no shadow of its own. For a surface embedded in a view tree
  /// that already positions and shadows it — a SwiftUI `.background`, a coach mark.
  package static func panel(cornerRadius: CGFloat = InkGlass.cornerRadius) -> InkGlassStyle {
    InkGlassStyle(cornerRadius: cornerRadius, shadow: nil, drawsEdge: true, inset: 0)
  }
}

// MARK: - The view

/// Holds the Reduce Transparency observer token so the panel can drop it without a `deinit` that
/// reaches into `@MainActor` state.
///
/// `NSView` is `@MainActor` (AppKit annotates `NSResponder` with the UI actor), its `deinit` is not,
/// and under `-strict-concurrency=complete` a nonisolated `deinit` may not touch a non-`Sendable`
/// isolated stored property. Handing the token to a plain reference type moves the teardown to a
/// `deinit` that is allowed to run it, at exactly the same moment. `@unchecked` because the token is
/// only ever written on the main thread, from `InkGlassView.init`.
private final class InkGlassObserverToken: @unchecked Sendable {
  var token: (any NSObjectProtocol)?

  deinit {
    guard let token else { return }
    NSWorkspace.shared.notificationCenter.removeObserver(token)
  }
}

/// The panel: ambient shadow, material, scrim, corner and edge, with the caller's content on top.
///
/// The ground is AppKit's and not SwiftUI's, all of it, so there is exactly one owner of "what is under
/// the type" and the hosted SwiftUI stays entirely transparent. Two grounds is how a translucent
/// surface ends up opaque in one appearance and muddy in the other.
///
/// `apply(reduceTransparency:)` takes the setting rather than reading it for one reason:
/// `NSWorkspace.accessibilityDisplayShouldReduceTransparency` is a machine setting a hermetic test
/// cannot flip — on a modern macOS not even `defaults write` can, the domain is protected — so a view
/// that reads it directly has an accessibility path nothing can ever assert. Passing it in makes "the
/// setting really produces an opaque panel" a test rather than a promise.
package final class InkGlassView: NSView {
  /// The glass itself: clipped to the corner, pinned to the light appearance. Content goes in here.
  package let panel = NSView()
  package let material = NSVisualEffectView()
  /// The scrim. A view rather than a sublayer so it sits in the same ordering as the hosted content and
  /// cannot end up drawn over it by a later `addSubview`.
  package let ground = NSView()
  /// The specular top edge. See `InkGlass.sheenAlpha` — the glassiness that costs no contrast.
  package let sheen = NSView()

  package private(set) var style: InkGlassStyle

  /// The corner, settable after construction so a panel whose radius is driven by its content (a
  /// SwiftUI caller) does not have to rebuild the view to change it.
  package var cornerRadius: CGFloat {
    get { style.cornerRadius }
    set {
      guard newValue != style.cornerRadius else { return }
      style.cornerRadius = newValue
      panel.layer?.cornerRadius = newValue
      needsLayout = true
    }
  }

  /// Draws nothing itself; it exists to own a `shadowPath` and a mask that keeps the shadow from
  /// falling *under* the panel. It would otherwise: Core Animation renders a `shadowPath` as a filled,
  /// blurred shape behind the layer's content, and behind a panel that passes 35% of what is behind it
  /// a filled black rounded rect is not subtle — this cut-out gets more load-bearing every time the
  /// ground gets thinner, not less.
  private let shadowHost = NSView()
  private let observer = InkGlassObserverToken()

  package init(frame: NSRect, style: InkGlassStyle = .floating) {
    self.style = style
    super.init(frame: frame)
    wantsLayer = true

    shadowHost.wantsLayer = true
    addSubview(shadowHost)

    panel.wantsLayer = true
    panel.layer?.cornerRadius = style.cornerRadius
    // `.continuous` is the squircle every card in this system is cut with; `masksToBounds` is what
    // makes the material respect the corner at all — an `NSVisualEffectView` draws its own rectangle
    // otherwise, which is the straight edge that keeps windows off glass. It is also what clips the
    // sheen, so the highlight cannot square off the top corners on this path.
    panel.layer?.cornerCurve = .continuous
    panel.layer?.masksToBounds = true
    panel.layer?.borderWidth = style.drawsEdge ? 1 : 0
    // The pin. Everything inside the panel — including a hosted `NSHostingView` and therefore SwiftUI's
    // `colorScheme` — resolves in this appearance.
    panel.appearance = InkGlass.appearance
    addSubview(panel)

    material.material = InkGlass.material
    // `.behindWindow`, so the blur is of the desktop rather than of this window's own content —
    // `.withinWindow` would frost the panel's own type.
    material.blendingMode = .behindWindow
    // `.active` and not `.followsWindowActiveState`: these windows spend much of their life inactive (a
    // browser during sign-in, a TCC prompt), and a panel that goes flat grey whenever the user answers
    // a system dialog reads as broken.
    material.state = .active
    material.autoresizingMask = [.width, .height]
    panel.addSubview(material)

    ground.wantsLayer = true
    ground.autoresizingMask = [.width, .height]
    panel.addSubview(ground)

    // Above the ground so it is a highlight *on* the surface, and pinned to the top edge by `layout()`
    // rather than by an autoresizing mask — `.maxYMargin` would keep its distance from the top on a
    // resize, which on a window that resizes leaves the highlight floating in the middle of the card.
    sheen.wantsLayer = true
    panel.addSubview(sheen)

    applyCurrentSettings()
    // The user can flip Reduce Transparency while a window is up — someone struggling to read a
    // first-run card is exactly who reaches for the setting — so the panel watches for it rather than
    // sampling once at construction.
    observer.token = NSWorkspace.shared.notificationCenter.addObserver(
      forName: InkReduceTransparency.didChangeNotification,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      MainActor.assumeIsolated { self?.applyCurrentSettings() }
    }
  }

  @available(*, unavailable)
  required init?(coder: NSCoder) { nil }

  /// Accepted for the reason every view in these windows accepts it: an `.accessory` app is never
  /// frontmost when a panel appears, and AppKit otherwise spends the user's first click activating the
  /// window instead of delivering it to the control underneath.
  package override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

  /// Hosts a content view inside the panel, filling it.
  ///
  /// The seam every window uses: build your `NSHostingView`, hand it here, and the glass owns
  /// everything under it. Autoresizing rather than constraints, because these panels are resized by
  /// their windows and a constraint-based child of a borderless window is the shape that crashes in
  /// `_postWindowNeedsUpdateConstraints`.
  package func setContent(_ view: NSView) {
    view.frame = panel.bounds
    view.autoresizingMask = [.width, .height]
    panel.addSubview(view)
  }

  /// Where the glass actually is inside this view. A caller that has to position something against the
  /// panel — a pointer, a tail — reads it from here rather than re-deriving the inset.
  package var panelFrame: NSRect { bounds.insetBy(dx: style.inset, dy: style.inset) }

  /// A frame-based view does not always get a `layout()` pass from a resize on its own, and this one is
  /// autoresized by every window that hosts it. Without this, a resized window leaves the panel at its
  /// old size.
  package override func setFrameSize(_ newSize: NSSize) {
    super.setFrameSize(newSize)
    needsLayout = true
  }

  package override func layout() {
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

  /// The palette is dynamic and the panel is pinned, so the pin has to be re-asserted and the resolved
  /// colours re-read whenever the appearance changes. AppKit calls this for the latter.
  package override func viewDidChangeEffectiveAppearance() {
    super.viewDidChangeEffectiveAppearance()
    applyCurrentSettings()
  }

  private func applyCurrentSettings() {
    apply(reduceTransparency: InkReduceTransparency.isEnabled)
  }

  /// One point. A highlight is a *line*, not a gradient band — a band reads as a second, lighter panel
  /// stacked on the first, which is the "two grounds" failure this component exists to stop.
  ///
  /// `nonisolated` because it is a number, not a view: `NSView` is `@MainActor`, so without this the
  /// constant is only readable from the main actor and the SwiftUI modifier below — plus any hermetic
  /// layout check — would have to hop an actor to read a `1`.
  nonisolated package static let sheenHeight: CGFloat = 1

  /// The panel's whole appearance, from one `Bool`. The only branch in this file.
  package func apply(reduceTransparency reduced: Bool) {
    material.isHidden = !InkGlass.showsMaterial(reduceTransparency: reduced)
    // A specular highlight is a property of *glass*. Under Reduce Transparency this is an opaque sheet
    // and there is no glass for the light to catch, so the highlight goes with the blur — the same rule
    // the material follows, for the same reason.
    sheen.isHidden = reduced

    let alpha = InkGlass.groundAlpha(reduceTransparency: reduced)
    // Resolved inside the panel's own (pinned) appearance, not read at file scope: a dynamic `NSColor`
    // converted to a `CGColor` anywhere else freezes whichever appearance happened to be current, which
    // on a Dark machine is exactly the near-black ground this replaces.
    panel.effectiveAppearance.performAsCurrentDrawingAppearance {
      ground.layer?.backgroundColor = Ink.nsSurface.withAlphaComponent(alpha).cgColor
      // Fixed white rather than a semantic colour: this is a light source reflecting off the panel's
      // face, not a surface tone, so it must not follow the palette into anything.
      sheen.layer?.backgroundColor = NSColor.white.withAlphaComponent(InkGlass.sheenAlpha).cgColor
      panel.layer?.borderColor =
        style.drawsEdge
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
    // Under Reduce Transparency the panel is opaque, but it is still a floating object over the desktop
    // and still needs to read as one, so the shadow stays.
    layer.shadowOpacity = shadow.opacity
    layer.shadowRadius = shadow.radius
    layer.shadowOffset = CGSize(width: 0, height: shadow.offsetY)
    layer.shadowPath = CGPath(
      roundedRect: frame, cornerWidth: radius, cornerHeight: radius, transform: nil)

    // Everything except the panel's own footprint. Inset by a point so the cut-out is always smaller
    // than the panel drawn over it and no seam can show at the corners, where a continuous squircle and
    // `CGPath`'s circular corner do not quite agree.
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

/// The same glass, for a panel drawn *inside* SwiftUI rather than being a window root — a coach mark, a
/// card floating in a shared full-screen overlay window that cannot each own an `NSWindow`.
///
/// It is the same material, scrim, corner and shadow, reached a different way, because there is no
/// third option: SwiftUI's own `Material` is within-window vibrancy and blurs the app's content rather
/// than the desktop, so a SwiftUI-only card over the desktop is not glass at all.
///
/// **Nesting one of these inside a window that already has a glass ground does not stack two
/// materials — it replaces one with the other.** `.behindWindow` samples what is behind the *window*,
/// so a panel drawn this way ignores the ground beneath it and takes its own, second copy of the
/// desktop, then puts the scrim on that. The result is a surface with the ground's passthrough but a
/// doubled scrim, which is the "two grounds" reading `SettingsGlassKit` forbids inside a pane — and it
/// is why a bar over a busy wallpaper can read muddier than the glass around it. It is nearly free to
/// draw (see the cost table in this file's header) and ≈0.9 ms to mount, so this is a question about
/// how the surface *looks*, not about frame rate; `glassFloatingBar` is the one caller that wants it,
/// because a bar floating over scrolling content does need a material of its own.
package struct InkGlassBackdrop: NSViewRepresentable {
  package init() {}

  package func makeNSView(context: Context) -> NSVisualEffectView {
    let view = NSVisualEffectView()
    view.material = InkGlass.material
    view.blendingMode = .behindWindow
    view.state = .active
    view.appearance = InkGlass.appearance
    return view
  }

  package func updateNSView(_ view: NSVisualEffectView, context: Context) {}
}

/// The whole panel — material, scrim, corner, edge — as one SwiftUI view, for a caller that wants to
/// place and shadow it itself.
///
/// `inkGlassPanel(…)` is the modifier most callers want; this is the same glass for a view tree that
/// needs the surface as a value rather than as a background, and it is the AppKit `InkGlassView` rather
/// than a second stack of layers, so there is still only one glass.
package struct InkGlassSurface: NSViewRepresentable {
  package var cornerRadius: CGFloat

  package init(cornerRadius: CGFloat = InkGlass.cornerRadius) {
    self.cornerRadius = cornerRadius
  }

  package func makeNSView(context: Context) -> InkGlassView {
    InkGlassView(frame: .zero, style: .panel(cornerRadius: cornerRadius))
  }

  package func updateNSView(_ view: InkGlassView, context: Context) {
    view.cornerRadius = cornerRadius
  }
}

extension View {
  /// Wears the glass: material, scrim, corner, faint edge, ambient shadow — and the light appearance,
  /// forced into the environment so `Ink`'s dynamic colours resolve dark on it.
  ///
  /// - Parameter reduceTransparency: passed in rather than read, for the same reason
  ///   `InkGlassView.apply(reduceTransparency:)` takes it — see that method.
  @ViewBuilder
  package func inkGlassPanel(
    cornerRadius: CGFloat = InkGlass.cornerRadius,
    shadow: InkGlassShadow? = .ambient,
    reduceTransparency: Bool = InkReduceTransparency.isEnabled
  ) -> some View {
    let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
    self
      .environment(\.colorScheme, .light)
      .background {
        ZStack(alignment: .top) {
          if InkGlass.showsMaterial(reduceTransparency: reduceTransparency) {
            InkGlassBackdrop()
          }
          Ink.surface.opacity(InkGlass.groundAlpha(reduceTransparency: reduceTransparency))
          // Hidden under Reduce Transparency for the same reason the material is: there is no glass to
          // catch the light.
          //
          // **Deliberate divergence from the source.** Upstream the highlight is a plain child of this
          // stack and relies entirely on the stack's own `.clipShape` below to round it. That clip does
          // not reach every call site — a child that renders into its own layer (the representable
          // material beside it, a panel mid-animation) can escape it, and when it does the 1 pt band
          // runs the full width and squares off both top corners, which is the exact complaint the
          // upstream fix was written for. So the highlight carries the panel's shape itself: the outer
          // `maxHeight` frame first, so the band's *own* frame is the whole panel, and only then the
          // clip — a `clipShape` evaluated inside a 1 pt box degenerates to a straight bar and is what
          // squared the corners in the first place. Order is the whole fix.
          if InkGlass.showsMaterial(reduceTransparency: reduceTransparency) {
            Color.white.opacity(InkGlass.sheenAlpha)
              .frame(height: InkGlassView.sheenHeight)
              .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
              .clipShape(shape)
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
