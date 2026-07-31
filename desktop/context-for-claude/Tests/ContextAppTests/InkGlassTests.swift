import AppKit
import SwiftUI
import XCTest

@testable import ContextApp

/// The app's one piece of glass — the surface the onboarding card, the timeline, settings, the menu
/// bar popover, the search panels and the tutorial's coach marks are all built on.
///
/// Every claim here is about what the *type* ends up sitting on, because that is the only thing a
/// translucent surface can get wrong in a way that matters. The material's own blur is not asserted
/// and cannot be: an `NSVisualEffectView` set to `.behindWindow` samples the desktop, and in a test
/// process there is no desktop behind it. What is asserted is the part this code owns — the pinned
/// appearance, the scrim, the ladder on the resulting ground, the shadow, and what the accessibility
/// setting does to all of it.
final class InkGlassTests: XCTestCase {

    // MARK: - The pin

    /// **The panel is light, and it is light because it says so — not because the machine is.**
    ///
    /// This is the whole mechanism. `NSVisualEffectView` renders a *different, dark* material in
    /// `.darkAqua`, and `controlBackgroundColor` resolves near-black there, which is how this surface
    /// shipped as a black slab. A test host runs in whatever appearance it happens to be in, so the
    /// claim is asserted the hard way: the panel is put inside a view hierarchy explicitly pinned to
    /// Dark, and it still has to come out Aqua.
    @MainActor
    func testTheGlassStaysLightInsideADarkHost() {
        let host = NSView(frame: NSRect(x: 0, y: 0, width: 400, height: 300))
        host.appearance = NSAppearance(named: .darkAqua)
        let glass = InkGlassView(frame: host.bounds)
        host.addSubview(glass)

        XCTAssertEqual(
            glass.panel.effectiveAppearance.name, .aqua,
            "the glass resolved \(glass.panel.effectiveAppearance.name.rawValue) inside a Dark host — "
                + "the pin is what makes this surface light, and it is not holding")
    }

    /// **…and the type on it flips dark with it.**
    ///
    /// The failure this guards against is not subtle-looking, it is invisible: `Ink`'s whole ladder
    /// is an alpha on `labelColor`, which is near-*white* in Dark. A panel forced light whose text
    /// did not follow is white-on-white — nothing on screen at all. Asserted as luminance rather than
    /// as a colour value so it keeps meaning something if the palette is ever re-based.
    @MainActor
    func testTheTypeResolvesDarkOnTheLightGlass() {
        for (name, step) in [("primary", Ink.primary), ("secondary", Ink.secondary), ("tertiary", Ink.tertiary)] {
            XCTAssertLessThan(
                InkContrastProbe.glassLuminance(step), 0.2,
                "\(name) resolves light on the light glass, which is text nobody can see")
        }
        XCTAssertGreaterThan(
            InkContrastProbe.glassLuminance(Ink.surface), 0.8,
            "the scrim colour has to be near-white on the light glass, or the panel is not light")
    }

    // MARK: - Contrast

    /// The label ladder still clears WCAG AA **on the glass**, in both system appearances, over both
    /// of the two desktops that can be behind it.
    ///
    /// Four combinations, and all four have to hold. `Ink`'s alphas were tuned against an opaque
    /// `surface`, and `MenuBarPresentationTests` still asserts them there; that assertion does not
    /// cover any of these windows any more, because the ground is now `surface` at `InkGlass.scrim`,
    /// over the material, over whatever the user has on screen. So the same ladder is measured again
    /// against *that* ground, at both extremes — a solid black desktop and a solid white one.
    ///
    /// The system appearance is varied and is expected to make no difference at all. That is the
    /// point: it is the assertion that the pin, and not the machine, decides what this surface is.
    @MainActor
    func testTheLadderClearsWCAGAAOnTheGlassOnEveryDesktopAndEverySystemAppearance() {
        var readings: [Double] = []
        for system in [NSAppearance.Name.aqua, .darkAqua] {
            for (desktop, label) in [(Color.black, "black desktop"), (Color.white, "white desktop")] {
                let ladder = InkContrastProbe.glassLadder(system: system, over: desktop)
                let where_ = "\(label), system \(system.rawValue)"

                // Every step here carries text under 18 pt, so the bar is AA's 4.5:1 for normal text
                // and not the 3:1 large-text allowance. `tertiary` is included and is the binding
                // one: the search results panel sets dense small copy on this glass, so a floor that
                // only held for headlines would be no floor at all.
                XCTAssertGreaterThanOrEqual(
                    ladder.primary, 4.5, "primary is \(ladder.primary):1 on the glass — \(where_)")
                XCTAssertGreaterThanOrEqual(
                    ladder.secondary, 4.5, "secondary is \(ladder.secondary):1 on the glass — \(where_)")
                XCTAssertGreaterThanOrEqual(
                    ladder.tertiary, 4.5, "tertiary is \(ladder.tertiary):1 on the glass — \(where_)")

                // …and it is still a ladder on glass, not one colour three times.
                XCTAssertGreaterThan(ladder.primary, ladder.secondary, where_)
                XCTAssertGreaterThan(ladder.secondary, ladder.tertiary, where_)

                readings.append(ladder.tertiary)
            }
        }

        // The two system appearances must produce *identical* readings, not merely passing ones. A
        // difference here means something in the chain is still reading the machine's appearance.
        XCTAssertEqual(readings[0], readings[2], accuracy: 1e-9, "system appearance changed the glass")
        XCTAssertEqual(readings[1], readings[3], accuracy: 1e-9, "system appearance changed the glass")
    }

    /// The scrim is a **floor**, and this is the measurement that sets it.
    ///
    /// The pressure on this number is entirely one way: the surface is meant to look like glass, so
    /// every future pass will want it thinner. What stops that from silently walking `Ink.tertiary`
    /// under AA is showing that the shipped value is *already* near the edge — the same model, run a
    /// few points lower, has to fail.
    ///
    /// Stated against the model rather than as `scrim >= 0.36` so it survives a change of material:
    /// swap the material and this test still says "thin it until the ladder breaks, then back off".
    @MainActor
    func testTheScrimIsTheThinnestTheLadderCanBeReadOn() {
        let shipped = InkContrastProbe.glassLadder(system: .aqua, over: .black)
        XCTAssertGreaterThanOrEqual(shipped.tertiary, 4.5)

        // The floor really is a floor: taking a fifth off the scrim puts the bottom rung under AA.
        let thinned = InkGlassTests.tertiaryOnGlass(scrim: InkGlass.scrim * 0.8)
        XCTAssertLessThan(
            thinned, 4.5,
            "at \(InkGlass.scrim * 0.8) the ladder still clears AA, so \(InkGlass.scrim) is not the "
                + "floor it is documented as — re-derive it or thin the scrim")
    }

    /// The same model as `InkContrastProbe.glassLadder`, at an arbitrary scrim, so the floor above can
    /// be shown to be one. Only `tertiary` — it is the binding rung and the only one worth modelling
    /// twice.
    @MainActor
    private static func tertiaryOnGlass(scrim: CGFloat) -> Double {
        var value = 0.0
        NSAppearance(named: InkGlass.appearanceName)!.performAsCurrentDrawingAppearance {
            func linear(_ c: Double) -> Double {
                c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
            }
            // Grey throughout: the material measures neutral and both extreme desktops are neutral.
            let material = Double(InkGlass.measuredMaterialOpacity)
            let tint = Double(InkGlass.measuredMaterialTint)
            let frosted = tint * material  // over a black desktop
            let ground = 1.0 * Double(scrim) + frosted * (1 - Double(scrim))
            let alpha = Double(NSColor(Ink.tertiary).usingColorSpace(.sRGB)!.alphaComponent)
            let text = ground * (1 - alpha)
            value = (linear(ground) + 0.05) / (linear(text) + 0.05)
        }
        return value
    }

    // MARK: - Reduce Transparency

    /// **Reduce Transparency really produces an opaque background.**
    ///
    /// The whole promise of the setting, in the two values that carry it. A user who has asked macOS
    /// to stop making surfaces see-through gets a solid sheet and no material at all — not a thicker
    /// scrim, not a slower blur. Shipping glass that ignores this is an accessibility defect and not
    /// a rough edge, which is why it is a value a test can hold rather than an `if` inside a view.
    func testReduceTransparencyGivesAnOpaqueGroundAndNoMaterial() {
        XCTAssertEqual(
            InkGlass.groundAlpha(reduceTransparency: true), 1,
            "the ground has to be fully opaque when the user has asked for reduced transparency")
        XCTAssertFalse(
            InkGlass.showsMaterial(reduceTransparency: true),
            "and the blurred material has to be gone, not merely covered")
    }

    /// …and with the setting off it is genuinely glass, so the test above cannot pass by the
    /// translucency having quietly been dropped everywhere.
    func testTheDefaultGroundIsTranslucentAndKeepsItsMaterial() {
        let alpha = InkGlass.groundAlpha(reduceTransparency: false)
        XCTAssertEqual(alpha, InkGlass.scrim)
        XCTAssertLessThan(alpha, 1, "the default ground has to let the desktop through")
        XCTAssertTrue(InkGlass.showsMaterial(reduceTransparency: false))

        // And it has to be *substantially* translucent, not a token 0.95. This is the number the
        // surface was reported on — it shipped at 0.80 and read as an opaque slab.
        XCTAssertLessThanOrEqual(
            alpha, 0.5, "a scrim this thick is a sheet with a blur behind it, not glass")
    }

    /// …and the panel the app actually installs really does what those two values say, in **every**
    /// style it is used in.
    ///
    /// The values above are a policy; this is the wiring. Asserted on the real `NSView` because the
    /// defect being guarded against is not "the policy is wrong", it is "the policy is right and
    /// nothing reads it", which is what shipping a glass window that ignores the setting looks like
    /// from the inside. Both styles, because they are used by different windows and a branch that
    /// only fires for one of them is the shape this defect takes next time.
    @MainActor
    func testEveryStyleOfPanelGoesOpaqueWhenTransparencyIsReduced() throws {
        for (name, style) in [
            ("floating", InkGlassStyle.floating),
            ("fullBleed", InkGlassStyle.fullBleed),
            ("panel", InkGlassStyle.panel()),
        ] {
            let glass = InkGlassView(frame: NSRect(x: 0, y: 0, width: 720, height: 520), style: style)
            glass.layoutSubtreeIfNeeded()

            glass.apply(reduceTransparency: true)
            XCTAssertTrue(glass.material.isHidden, "\(name): the blurred material is still being drawn")
            let opaque = try XCTUnwrap(glass.ground.layer?.backgroundColor)
            XCTAssertEqual(
                opaque.alpha, 1, accuracy: 1e-9, "\(name): the ground is still letting the desktop in")

            glass.apply(reduceTransparency: false)
            XCTAssertFalse(glass.material.isHidden, "\(name): the material never came back")
            let glassy = try XCTUnwrap(glass.ground.layer?.backgroundColor)
            XCTAssertEqual(glassy.alpha, InkGlass.scrim, accuracy: 1e-6, name)
        }
    }

    // MARK: - The shape and the shadow

    /// One corner for every panel, and it is the rounder one.
    ///
    /// Two things floating over the same desktop rounded to two different radii is the tell that
    /// neither was decided. The floor is the part worth holding: at 16 — where this app was — a large
    /// panel reads as a dialog rather than as a floating object.
    func testEveryFloatingPanelIsCutToOneGenerousCorner() {
        XCTAssertEqual(InkGlass.cornerRadius, 22)
        XCTAssertGreaterThanOrEqual(
            InkGlass.cornerRadius, 20, "a panel cut tighter than this reads as a dialog, not as glass")
        XCTAssertEqual(InkGlassStyle.floating.cornerRadius, InkGlass.cornerRadius)
        XCTAssertEqual(InkGlassStyle.panel().cornerRadius, InkGlass.cornerRadius)
        // The inside of an ordinary titled window is the one surface that is not rounded: the window
        // frame already is, and rounding twice draws a corner inside a corner.
        XCTAssertEqual(InkGlassStyle.fullBleed.cornerRadius, 0)
    }

    /// The shadow is **broad and faint**, which is the whole of why a panel reads as floating.
    ///
    /// The wrong shadow here is not a missing one, it is a tight dark one: an 18 pt radius at 0.22 —
    /// what the tutorial card shipped with — reads as a sticker rather than as an object with air
    /// under it. Held as a shape (wide, low-opacity, offset downward) rather than as three numbers,
    /// so it can be retuned but not turned back into a drop shadow.
    func testTheAmbientShadowIsWideAndFaintRatherThanATightDrop() {
        let shadow = InkGlassShadow.ambient
        XCTAssertGreaterThanOrEqual(shadow.radius, 24, "a \(shadow.radius) pt shadow is a drop shadow")
        XCTAssertLessThanOrEqual(shadow.opacity, 0.35, "a shadow this dark reads as a border")
        XCTAssertGreaterThan(shadow.opacity, 0, "no shadow at all is not the design either")
        XCTAssertLessThan(shadow.offsetY, 0, "the light is above; the shadow falls below the panel")

        // And the window has to leave it somewhere to fall. A borderless window clips at its own
        // bounds, so a panel drawn edge to edge simply has no shadow — which is the same bug as not
        // having one, arrived at from the other direction.
        XCTAssertGreaterThan(shadow.padding, shadow.radius, "the margin cannot be narrower than the blur")
        XCTAssertEqual(InkGlassStyle.floating.inset, shadow.padding)
        XCTAssertEqual(InkGlassStyle.fullBleed.inset, 0, "a window-filling surface must not be inset")
    }

    /// The panel really is inset inside its host, at every size — a 56 pt bar and a 760 pt panel both
    /// have to leave the same room, because the shadow is one value for all of them.
    @MainActor
    func testThePanelLeavesRoomForItsShadowAtEverySize() {
        for size in [NSSize(width: 660, height: 56), NSSize(width: 1180, height: 760)] {
            let outer = NSSize(
                width: size.width + InkGlassStyle.floating.inset * 2,
                height: size.height + InkGlassStyle.floating.inset * 2)
            let glass = InkGlassView(frame: NSRect(origin: .zero, size: outer), style: .floating)
            glass.layoutSubtreeIfNeeded()

            XCTAssertEqual(glass.panel.frame.width, size.width, accuracy: 0.5, "\(size)")
            XCTAssertEqual(glass.panel.frame.height, size.height, accuracy: 0.5, "\(size)")
            XCTAssertEqual(glass.panel.layer?.cornerRadius, InkGlass.cornerRadius, "\(size)")
        }
    }

    /// Content handed to the panel fills the *panel*, not the host — otherwise the card's copy is
    /// drawn out in the transparent shadow margin, which looks exactly like a layout bug because it
    /// is one.
    @MainActor
    func testContentIsLaidOutInsideTheGlassAndNotInTheShadowMargin() {
        let glass = InkGlassView(frame: NSRect(x: 0, y: 0, width: 832, height: 632), style: .floating)
        glass.layoutSubtreeIfNeeded()
        let content = NSView()
        glass.setContent(content)

        XCTAssertTrue(content.isDescendant(of: glass.panel), "content was not hosted inside the glass")
        XCTAssertEqual(content.frame.size, glass.panel.bounds.size)
    }

    // MARK: - The onboarding window

    /// The onboarding window is sized to the card *plus* the shadow's margin, and the card keeps the
    /// size it always had.
    ///
    /// The failure this catches is the one that makes the whole component look broken: sizing the
    /// window to the card, so the panel is inset inside it and the card silently shrinks by 112 pt.
    @MainActor
    func testTheOnboardingWindowIsTheCardPlusTheRoomItsShadowNeeds() {
        let pad = InkGlassStyle.floating.inset
        let card = OnboardingWindow.cardSize
        let window = OnboardingWindow.windowSize
        XCTAssertEqual(card.width, 720, "the reading column plus both gutters")
        // The height is not a free choice and is no longer 520: it is what the permissions card's
        // tallest state measures, plus the page margins and the band the progress dots are
        // reserved. `PermissionsCardLayoutTests` derives and enforces it; restated here only so a
        // change to the pane is a deliberate one rather than a side effect.
        XCTAssertEqual(card.height, 640)
        XCTAssertEqual(
            card.height,
            OnboardingWindow.cardContentHeight + 2 * InkLayout.pagePaddingVertical
                + InkLayout.progressBandHeight,
            "the budget the card is laid out against has to describe the card")
        XCTAssertEqual(window.width, card.width + pad * 2)
        XCTAssertEqual(window.height, card.height + pad * 2)
    }

    // MARK: - Yielding the screen

    /// A show that arrives while the card is still fading out must cancel the `orderOut`.
    ///
    /// The card yields the screen whenever the next thing to click belongs to another app, and on the
    /// permissions run that is three times per grant — so a hide and a show overlapping is the normal
    /// case, not the edge one. The fade made it possible for the two to cross: `orderOut` now runs in
    /// a completion handler, and a completion handler that fires after the user has been sent back to
    /// the card takes the window off screen behind them.
    ///
    /// There is no recovering from that. The app is `LSUIElement` — no Dock icon, no window menu,
    /// nothing to click — so a first-run window ordered out with no path back is a dead install. The
    /// rule is a value precisely so it can be asserted rather than reasoned about in a closure.
    func testAShowArrivingMidFadeCancelsTheHide() {
        // The ordinary case: a hide runs to completion undisturbed.
        XCTAssertTrue(
            OnboardingWindow.hideMayComplete(startedAt: 4, current: 4, stillHidden: true))

        // A show landed while the fade was running — the intent is no longer "hidden".
        XCTAssertFalse(
            OnboardingWindow.hideMayComplete(startedAt: 4, current: 5, stillHidden: false),
            "a fade that has been overtaken by a show must not order the window out")
        // …and even a hide → show → hide round trip must not let the *first* fade do the ordering:
        // the second one owns it, and the first one's completion is stale.
        XCTAssertFalse(
            OnboardingWindow.hideMayComplete(startedAt: 4, current: 6, stillHidden: true),
            "a stale fade must not order the window out on a newer request's behalf")
    }
}
