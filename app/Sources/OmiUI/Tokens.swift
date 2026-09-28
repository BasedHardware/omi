import Foundation
import SwiftUI

// Shared design tokens, ported from `react-native/src/ui/tokens.ts`.
// Static dark by design — mobile renders without a theme provider; desktop
// environments remap via their own theme layer (as DesktopTheme did).

/// Token color construction. SkipUI cannot merge constructors into SwiftUI
/// types from other modules, so this is a namespace function, not an
/// extension on `Color`.
public enum OmiColor {
    /// Builds a color from a packed 0xRRGGBB token value.
    public static func hex(_ value: UInt32) -> Color {
        Color(
            red: Double((value >> 16) & 0xFF) / 255.0,
            green: Double((value >> 8) & 0xFF) / 255.0,
            blue: Double(value & 0xFF) / 255.0
        )
    }
}

public enum Palette {
    public nonisolated(unsafe) static let canvas = OmiColor.hex(0x141414)
    public nonisolated(unsafe) static let chrome = OmiColor.hex(0x121413)
    public nonisolated(unsafe) static let chromeText = OmiColor.hex(0xC8CBC6)
    public nonisolated(unsafe) static let danger = OmiColor.hex(0xD9826F)
    public nonisolated(unsafe) static let focus = OmiColor.hex(0x78BDA5)
    public nonisolated(unsafe) static let input = Color.white.opacity(0.1)
    public nonisolated(unsafe) static let inputPressed = Color.white.opacity(0.14)
    public nonisolated(unsafe) static let menu = Color(
        red: 31.0 / 255.0, green: 35.0 / 255.0, blue: 33.0 / 255.0,
        opacity: 0.98
    )
    public nonisolated(unsafe) static let menuText = OmiColor.hex( 0xD7DAD5)
    public nonisolated(unsafe) static let menuTextStrong = OmiColor.hex( 0xDFE2DD)
    public nonisolated(unsafe) static let line = OmiColor.hex( 0x303030)
    public nonisolated(unsafe) static let lineStrong = OmiColor.hex( 0x555555)
    public nonisolated(unsafe) static let primary = Color.white
    public nonisolated(unsafe) static let primaryPressed = OmiColor.hex( 0xE4EEE6)
    public nonisolated(unsafe) static let surface = OmiColor.hex( 0x1A1A1A)
    public nonisolated(unsafe) static let surfaceRaised = OmiColor.hex( 0x202020)
    public nonisolated(unsafe) static let text = OmiColor.hex( 0xF2F4F1)
    public nonisolated(unsafe) static let textInverse = OmiColor.hex( 0x141414)
    public nonisolated(unsafe) static let textMuted = OmiColor.hex( 0xB0B0B0)
    public nonisolated(unsafe) static let textSubtle = OmiColor.hex( 0x888888)
}

public enum Radius {
    public nonisolated(unsafe) static let none: CGFloat = 0
    public nonisolated(unsafe) static let sm: CGFloat = 6
    public nonisolated(unsafe) static let md: CGFloat = 10
    public nonisolated(unsafe) static let lg: CGFloat = 14
    public nonisolated(unsafe) static let xl: CGFloat = 26
    public nonisolated(unsafe) static let pill: CGFloat = 18
}

public enum Space {
    public nonisolated(unsafe) static let none: CGFloat = 0
    public nonisolated(unsafe) static let xxs: CGFloat = 2
    public nonisolated(unsafe) static let xs: CGFloat = 4
    public nonisolated(unsafe) static let sm: CGFloat = 8
    public nonisolated(unsafe) static let md: CGFloat = 12
    public nonisolated(unsafe) static let lg: CGFloat = 16
    public nonisolated(unsafe) static let xl: CGFloat = 24
    public nonisolated(unsafe) static let xxl: CGFloat = 32
    public nonisolated(unsafe) static let xxxl: CGFloat = 48
}

public struct TypeStyle: Hashable {
    public let size: CGFloat
    public let lineHeight: CGFloat
    public let weight: Font.Weight

    public init(size: CGFloat, lineHeight: CGFloat, weight: Font.Weight) {
        self.size = size
        self.lineHeight = lineHeight
        self.weight = weight
    }

    public var font: Font {
        Font.system(size: size, weight: weight)
    }
}

public enum Typography {
    public nonisolated(unsafe) static let caption = TypeStyle(
        size: 12, lineHeight: 16, weight: .medium
    )
    public nonisolated(unsafe) static let label = TypeStyle(size: 13, lineHeight: 18, weight: .semibold)
    public nonisolated(unsafe) static let body = TypeStyle(size: 14, lineHeight: 20, weight: .regular)
    public nonisolated(unsafe) static let title = TypeStyle(size: 18, lineHeight: 24, weight: .bold)
    public nonisolated(unsafe) static let display = TypeStyle(size: 28, lineHeight: 34, weight: .bold)
}

public enum Borders {
    public nonisolated(unsafe) static let width: CGFloat = 1
}

public enum IconWeight {
    public nonisolated(unsafe) static let strokeWidth: CGFloat = 2
}

public enum Opacity {
    public nonisolated(unsafe) static let disabled: Double = 0.48
    public nonisolated(unsafe) static let pressed: Double = 0.78
}

public enum Size {
    public nonisolated(unsafe) static let ask: CGFloat = 38
    public nonisolated(unsafe) static let askCompact: CGFloat = 26
    public nonisolated(unsafe) static let content: CGFloat = 560
    public nonisolated(unsafe) static let controlCompact: CGFloat = 30
    public nonisolated(unsafe) static let control: CGFloat = 36
    public nonisolated(unsafe) static let controlLarge: CGFloat = 44
    public nonisolated(unsafe) static let iconSmall: CGFloat = 14
    public nonisolated(unsafe) static let icon: CGFloat = 18
    public nonisolated(unsafe) static let iconLarge: CGFloat = 20
    public nonisolated(unsafe) static let iconChrome: CGFloat = 17
    public nonisolated(unsafe) static let searchDock: CGFloat = 52
    public nonisolated(unsafe) static let searchDockCompact: CGFloat = 60
    public nonisolated(unsafe) static let searchMax: CGFloat = 680
    public nonisolated(unsafe) static let sheet: CGFloat = 224
    public nonisolated(unsafe) static let sheetTop: CGFloat = 60
    public nonisolated(unsafe) static let toolbar: CGFloat = 38
}
