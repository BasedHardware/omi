import AppKit
import SwiftUI
import XCTest

@testable import ContextApp

/// Renders the onboarding card **over a synthetic desktop** and writes the frames out for a person to
/// look at, then samples its own render to say how much of that desktop survived.
///
/// **Skipped unless `CONTEXT_GLASS_RENDER=1`.** It writes files, and it exists to be run by hand while
/// tuning the glass; the claims that have to hold every time are in `InkGlassTests`, which is pure.
///
/// **Why this exists at all.** The glass was retuned three times, and each retune was verified
/// against a number that was not what anybody was looking at — the scrim's alpha, then a modelled
/// passthrough derived from a stale material sample, then a ground genuinely on its floor but with
/// the wrong rung setting that floor. All three moved convincingly while the card on screen did not.
/// A render over a *dark* desktop is the one check that could not have passed while the panel was a
/// white slab, because a white slab and a piece of glass look identical over a light desktop and
/// nothing alike over a dark one.
///
/// The pair it renders is now the two *ladders* on the same material — three-rung at scrim 0.56
/// (17.0% passthrough) against two-rung at the shipped scrim (34.8%) — because that is the change,
/// and putting the two dark-desktop frames beside each other is the whole argument in one look.
///
/// **What it can and cannot show.** `ImageRenderer` has no window server behind it, so a real
/// `NSVisualEffectView` would render as nothing at all; the material is therefore reproduced from the
/// sampled constants (`InkGlass.measuredMaterialOpacity` / `measuredMaterialTint`) exactly as
/// `InkContrastProbe` reproduces it for the contrast guard. That model is checked against the real
/// composite on a real desktop — see the table in `InkGlass.swift`'s header — and reproduces it to
/// about 3/255. What this harness is authoritative about is therefore the *composite*: the ground,
/// the type on it, and how far the desktop moves the card body. What it is not authoritative about is
/// the blur, which no offscreen renderer can produce.
final class GlassRenderHarness: XCTestCase {

    private var outputDirectory: URL {
        URL(
            fileURLWithPath: ProcessInfo.processInfo.environment["CONTEXT_GLASS_RENDER_DIR"]
                ?? NSTemporaryDirectory() + "glass-renders")
    }

    @MainActor
    func testRenderTheOnboardingCardOverADarkDesktop() throws {
        try XCTSkipUnless(
            ProcessInfo.processInfo.environment["CONTEXT_GLASS_RENDER"] == "1",
            "render harness; set CONTEXT_GLASS_RENDER=1 to run it")
        XCTAssertTrue(InkTestFonts.registered, "the bundled faces have to be registered to render type")

        let directory = outputDirectory
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        // The recipe reported as an opaque slab the third time: the same `.hudWindow` material, but
        // scrimmed up to the ground a *three-rung* ladder needs. Kept as a fixture so the two renders
        // can be put side by side, and kept at this material on purpose — it isolates the one thing
        // that changed, which is the ladder and not the glass.
        let previous = GlassRecipe(
            name: "before-threeRung",
            materialOpacity: InkGlass.measuredMaterialOpacity,
            materialTint: InkGlass.measuredMaterialTint,
            scrim: 0.56)
        let shipped = GlassRecipe(
            name: "after-shipped",
            materialOpacity: InkGlass.measuredMaterialOpacity,
            materialTint: InkGlass.measuredMaterialTint,
            scrim: InkGlass.scrim)

        for recipe in [previous, shipped] {
            for desktop in GlassDesktop.allCases {
                let view = GlassProof(recipe: recipe, desktop: desktop)
                let image = try render(view, named: "\(recipe.name)-\(desktop.rawValue)", to: directory)
                if desktop == .bands { report(recipe, image: image) }
            }
        }

        print("[glass] frames written to \(directory.path)")
    }

    // MARK: Measuring the render

    /// Samples the card body over each band and prints the slope — the share of the desktop's own
    /// luminance that reaches the eye. Printed rather than asserted here: the assertion belongs to
    /// `InkGlassTests`, which does not need a file written to make it.
    @MainActor
    private func report(_ recipe: GlassRecipe, image: CGImage) {
        let bands = GlassDesktop.bandLevels
        let samples = bands.enumerated().compactMap { index, level -> (Double, Double)? in
            // The centre of each band, well inside the card and far enough from the band boundary
            // that no blur could mix one reading into the next.
            let y = GlassProof.size.height * (CGFloat(index) + 0.5) / CGFloat(bands.count)
            guard let body = sample(image, x: GlassProof.size.width / 2, y: y) else { return nil }
            return (level * 255, body)
        }
        guard samples.count > 1 else { return XCTFail("the render could not be sampled") }

        let n = Double(samples.count)
        let sx = samples.reduce(0) { $0 + $1.0 }
        let sy = samples.reduce(0) { $0 + $1.1 }
        let sxy = samples.reduce(0) { $0 + $1.0 * $1.1 }
        let sxx = samples.reduce(0) { $0 + $1.0 * $1.0 }
        let slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
        let intercept = (sy - slope * sx) / n

        print(
            String(
                format: "[glass] %@: passthrough %.1f%%  card body %.1f..%.1f /255 over every desktop",
                recipe.name, slope * 100, intercept, intercept + slope * 255))
        for (desktop, body) in samples {
            print(String(format: "[glass]     desktop %5.1f -> card body %5.1f", desktop, body))
        }
    }

    private func sample(_ image: CGImage, x: CGFloat, y: CGFloat) -> Double? {
        let rep = NSBitmapImageRep(cgImage: image)
        guard let colour = rep.colorAt(x: Int(x), y: Int(y))?.usingColorSpace(.sRGB) else { return nil }
        return Double(colour.redComponent) * 255
    }

    @MainActor
    private func render(_ view: some View, named name: String, to directory: URL) throws -> CGImage {
        let renderer = ImageRenderer(content: view)
        renderer.scale = 1
        let image = try XCTUnwrap(renderer.cgImage, "\(name) did not render")
        let bitmap = NSBitmapImageRep(cgImage: image)
        let data = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
        try data.write(to: directory.appendingPathComponent("\(name).png"))
        return image
    }
}

// MARK: - The recipe under test

/// One glass recipe, as the three numbers that decide what is under the type.
///
/// A value so the harness can render the recipe that shipped and the recipe that replaced it from the
/// same code — the comparison is the whole point, and two hand-built views would drift.
struct GlassRecipe {
    var name: String
    /// The material's own opacity, sampled off the real thing. See `InkGlass.measuredMaterialOpacity`.
    var materialOpacity: CGFloat
    /// …and its tone, as a fraction of white.
    var materialTint: CGFloat
    var scrim: CGFloat
}

// MARK: - The desktop underneath

/// The synthetic desktops the card is rendered over. Synthetic and never real: nothing here
/// screenshots the machine, so nothing of the user's can end up in a frame.
enum GlassDesktop: String, CaseIterable {
    /// Three flat bands — the measuring surface. Flat because the slope of composite against desktop
    /// is what passthrough *is*, and a photograph has no known luminance to regress against.
    case bands
    /// A dark desktop with structure in it, which is the case the complaint was made about and the
    /// only one where a white slab and a piece of glass look different.
    case dark
    /// The other extreme, so a change that fixes the dark case by breaking the light one is visible.
    case light

    static let bandLevels: [Double] = [0.0, 0.5, 1.0]

    @ViewBuilder
    var view: some View {
        switch self {
        case .bands:
            VStack(spacing: 0) {
                ForEach(Array(Self.bandLevels.enumerated()), id: \.offset) { _, level in
                    Color(white: level)
                }
            }
        case .dark:
            ZStack {
                Color(white: 0.06)
                // Something to see *through* the glass. If these are not visible in the render, the
                // panel is not glass, whatever the arithmetic says.
                Canvas { context, size in
                    for index in 0..<7 {
                        let t = CGFloat(index) / 6
                        context.fill(
                            Path(
                                ellipseIn: CGRect(
                                    x: size.width * (0.05 + t * 0.8) - 90,
                                    y: size.height * (0.12 + (index % 3 == 0 ? 0.5 : 0.1)) - 90,
                                    width: 180, height: 180)),
                            with: .color(Color(white: 0.06 + t * 0.34)))
                    }
                }
                .blur(radius: 30)
            }
        case .light:
            Color(white: 0.94)
        }
    }
}

// MARK: - The composite

/// The onboarding card as the compositor assembles it: desktop, material, scrim, specular edge, type.
///
/// Layered in the shipping order, and with the shipping tokens, so the picture is the app's rather
/// than a reconstruction of it. The one substitution is the material, which is reproduced from its
/// sampled constants because an `NSVisualEffectView` cannot render offscreen — see the harness's
/// documentation.
struct GlassProof: View {
    var recipe: GlassRecipe
    var desktop: GlassDesktop

    static let size = CGSize(
        width: OnboardingWindow.cardSize.width, height: OnboardingWindow.cardSize.height)

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: InkGlass.cornerRadius, style: .continuous)
    }

    var body: some View {
        ZStack {
            desktop.view

            ZStack {
                // The ground, in two layers and in order: the material's own tone at its own opacity,
                // then the scrim over it. Kept as two rather than pre-multiplied into one so a change
                // to either token shows up here as the compositor would apply it.
                Color(white: Double(recipe.materialTint)).opacity(Double(recipe.materialOpacity))
                Ink.surface.opacity(Double(recipe.scrim))
            }
            .clipShape(shape)
            .overlay(alignment: .top) {
                Color.white.opacity(InkGlass.sheenAlpha)
                    .frame(height: InkGlassView.sheenHeight)
                    .clipShape(shape)
            }
            .overlay(shape.strokeBorder(Ink.glassEdge, lineWidth: 1))
            .shadow(
                color: .black.opacity(Double(InkGlassShadow.ambient.opacity)),
                radius: InkGlassShadow.ambient.radius / 2,
                y: -InkGlassShadow.ambient.offsetY)
            .overlay {
                PermissionsCard(
                    title: "First…",
                    preamble: """
                        macOS asks separately for each of these, and I won’t ask for any of them \
                        until you tell me to. Read them, then click the one you’re ready for — I \
                        take them one at a time.
                        """,
                    rows: [
                        PermissionsCardRow(capability: .microphone, granted: true, status: "Granted"),
                        PermissionsCardRow(capability: .systemAudio, granted: false, status: "Allow"),
                        PermissionsCardRow(capability: .screen, granted: false, status: "Open Settings"),
                        PermissionsCardRow(capability: .accessibility, granted: false, status: "Allow"),
                    ],
                    phraseStart: Date().addingTimeInterval(-30)
                )
                .frame(width: InkLayout.permissionsMaxWidth)
                .padding(.horizontal, InkLayout.pagePaddingHorizontal)
                .padding(.vertical, InkLayout.pagePaddingVertical)
            }
            // The pin. Everything on the panel resolves in the glass's own appearance, which is what
            // makes the type dark on it — the same environment `inkGlassPanel` forces.
            .environment(\.colorScheme, .light)
            .frame(width: Self.size.width, height: Self.size.height)
        }
        .frame(width: Self.size.width, height: Self.size.height)
    }
}
