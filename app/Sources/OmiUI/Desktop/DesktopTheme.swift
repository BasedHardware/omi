import SwiftUI

// Port of `react-native/src/desktop/tokens.ts` + `DesktopTheme.tsx`: the
// dark glass palette and the light paper palette, radius/space/type scales,
// and the theme environment. Dark rides the native behind-window vibrancy
// (transparent app content); light paints an opaque paper background because
// a light native glass film reads milky under translucent surfaces.

public enum DesktopThemeName: String, Sendable {
    case dark
    case light
}

public struct DesktopTokens: Sendable {
    public var ink: Color
    public var inkMuted: Color
    public var inkFaint: Color
    public var glass: Color
    public var glassStrong: Color
    public var glassQuiet: Color
    public var glassSelected: Color
    public var line: Color
    public var lineStrong: Color
    /// Historical name: the opaque surface the light theme paints behind all
    /// content (dark ink in dark mode, paper in light mode).
    public var surfaceInk: Color
    public var white: Color
    public var blue: Color
    public var red: Color
    /// Window/panel/control/chip radii.
    public var radiusWindow: CGFloat
    public var radiusPanel: CGFloat
    public var radiusControl: CGFloat
    public var radiusChip: CGFloat
    public var isLight: Bool

    public init(
        ink: Color, inkMuted: Color, inkFaint: Color, glass: Color,
        glassStrong: Color, glassQuiet: Color, glassSelected: Color,
        line: Color, lineStrong: Color, surfaceInk: Color, white: Color,
        blue: Color, red: Color, isLight: Bool
    ) {
        self.ink = ink
        self.inkMuted = inkMuted
        self.inkFaint = inkFaint
        self.glass = glass
        self.glassStrong = glassStrong
        self.glassQuiet = glassQuiet
        self.glassSelected = glassSelected
        self.line = line
        self.lineStrong = lineStrong
        self.surfaceInk = surfaceInk
        self.white = white
        self.blue = blue
        self.red = red
        // tokens.ts keeps one radius scale across both palettes.
        self.radiusWindow = 24
        self.radiusPanel = 22
        self.radiusControl = 18
        self.radiusChip = 14
        self.isLight = isLight
    }
}

public enum DesktopPalettes {
    // Color construction mirrors OmiColor.hex in ../Tokens.swift; duplicated
    // privately because Desktop may not edit shared files.
    static func hex(_ value: UInt32, _ opacity: Double = 1) -> Color {
        Color(
            red: Double((value >> 16) & 0xFF) / 255.0,
            green: Double((value >> 8) & 0xFF) / 255.0,
            blue: Double(value & 0xFF) / 255.0,
            opacity: opacity
        )
    }

    public nonisolated(unsafe) static let dark = DesktopTokens(
        ink: hex(0xF2F4EF),
        inkMuted: hex(0xF2F4EF, 0.62),
        inkFaint: hex(0xF2F4EF, 0.45),
        glass: .clear,
        glassStrong: Color.white.opacity(0.14),
        glassQuiet: Color.white.opacity(0.05),
        glassSelected: Color.white.opacity(0.16),
        line: Color.white.opacity(0.10),
        lineStrong: Color.white.opacity(0.24),
        surfaceInk: hex(0x242622),
        white: .white,
        blue: hex(0x0A84FF),
        red: hex(0xFF453A),
        isLight: false
    )

    public nonisolated(unsafe) static let light = DesktopTokens(
        ink: hex(0x1D1F1B),
        inkMuted: hex(0x1D1F1B, 0.62),
        inkFaint: hex(0x1D1F1B, 0.45),
        glass: .clear,
        glassStrong: hex(0x1D1F1B, 0.08),
        glassQuiet: hex(0x1D1F1B, 0.04),
        glassSelected: hex(0x1D1F1B, 0.10),
        line: hex(0x1D1F1B, 0.12),
        lineStrong: hex(0x1D1F1B, 0.26),
        surfaceInk: hex(0xF4F5F1),
        white: .white,
        blue: hex(0x0066D6),
        red: hex(0xD70015),
        isLight: true
    )

    public static func tokens(_ name: DesktopThemeName) -> DesktopTokens {
        name == DesktopThemeName.light ? light : dark
    }
}

// MARK: - Theme environment

public struct DesktopThemeKey: EnvironmentKey {
    public nonisolated(unsafe) static let defaultValue: DesktopTokens =
        DesktopPalettes.dark
}

extension EnvironmentValues {
    public var desktopTokens: DesktopTokens {
        get { self[DesktopThemeKey.self] }
        set { self[DesktopThemeKey.self] = newValue }
    }
}

/// Applies the palette to a desktop subtree: transparent content over the
/// native glass in dark mode, an opaque paper background in light mode
/// (DesktopApp.tsx `DesktopRoot`).
public struct DesktopRootSurface<Content: View>: View {
    let tokens: DesktopTokens
    let content: Content

    public init(tokens: DesktopTokens, @ViewBuilder content: () -> Content) {
        self.tokens = tokens
        self.content = content()
    }

    public var body: some View {
        content
            .environment(\.desktopTokens, tokens)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(
                tokens.isLight ? tokens.surfaceInk : Color.clear
            )
    }
}
