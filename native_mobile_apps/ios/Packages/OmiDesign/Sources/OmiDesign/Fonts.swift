import CoreText
import SwiftUI

/// Omi's bundled display face: Instrument Serif (SIL Open Font License 1.1, `Resources/Fonts/OFL.txt`).
/// Registered for this process the first time a serif font is asked for (or by `register()` at app
/// start); text sizes follow Dynamic Type through `relativeTo`.
public enum OmiFonts {
    public static let serifName = "InstrumentSerif-Regular"

    /// Registers the bundled fonts once. Safe to call any number of times.
    public static func register() {
        _ = registration
    }

    /// A serif font that scales with Dynamic Type like `style`.
    public static func serif(_ size: CGFloat, relativeTo style: Font.TextStyle) -> Font {
        register()
        return .custom(serifName, size: size, relativeTo: style)
    }

    private static let registration: Bool = {
        guard let url = Bundle.module.url(forResource: serifName, withExtension: "ttf", subdirectory: "Fonts") else { return false }
        // Already registered (a second process start in previews) is fine too.
        return CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil)
    }()
}
