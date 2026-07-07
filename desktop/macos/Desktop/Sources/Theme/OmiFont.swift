import AppKit
import SwiftUI
import Combine

// MARK: - Font Scale Settings

package class FontScaleSettings: ObservableObject {
    package static let shared = FontScaleSettings()
    private let defaults = UserDefaults.standard

    @Published package var scale: CGFloat {
        didSet {
            defaults.set(scale, forKey: "fontScale")
        }
    }

    private init() {
        self.scale = defaults.object(forKey: "fontScale") as? CGFloat ?? 1.0
    }

    package func resetToDefault() {
        scale = 1.0
    }
}

// MARK: - Environment Key

private struct FontScaleKey: EnvironmentKey {
    static let defaultValue: CGFloat = 1.0
}

package extension EnvironmentValues {
    package var fontScale: CGFloat {
        get { self[FontScaleKey.self] }
        set { self[FontScaleKey.self] = newValue }
    }
}

// MARK: - Scaled Font Modifier

package struct ScaledFontModifier: ViewModifier {
    @Environment(\.fontScale) private var fontScale
    let size: CGFloat
    var weight: Font.Weight = .regular
    var design: Font.Design = .default

    package func body(content: Content) -> some View {
        content.font(.system(size: round(size * fontScale), weight: weight, design: design))
    }
}

package extension View {
package func scaledFont(size: CGFloat, weight: Font.Weight = .regular, design: Font.Design = .default) -> some View {
        modifier(ScaledFontModifier(size: size, weight: weight, design: design))
    }
}

// MARK: - Monospaced Digit Variant

package struct ScaledMonospacedDigitFontModifier: ViewModifier {
    @Environment(\.fontScale) private var fontScale
    let size: CGFloat
    var weight: Font.Weight = .regular

    package func body(content: Content) -> some View {
        content.font(.system(size: round(size * fontScale), weight: weight).monospacedDigit())
    }
}

package struct ScaledMonospacedFontModifier: ViewModifier {
    @Environment(\.fontScale) private var fontScale
    let size: CGFloat
    var weight: Font.Weight = .regular

    package func body(content: Content) -> some View {
        content.font(.system(size: round(size * fontScale), weight: weight).monospaced())
    }
}

package extension View {
package func scaledMonospacedDigitFont(size: CGFloat, weight: Font.Weight = .regular) -> some View {
        modifier(ScaledMonospacedDigitFontModifier(size: size, weight: weight))
    }

package func scaledMonospacedFont(size: CGFloat, weight: Font.Weight = .regular) -> some View {
        modifier(ScaledMonospacedFontModifier(size: size, weight: weight))
    }
}

// MARK: - Window Size Reset

package func resetWindowToDefaultSize() {
    guard let window = NSApp.keyWindow ?? NSApp.windows.first(where: { $0.title.contains("omi") || $0.title.contains("Omi") }) else { return }
    let defaultSize = NSSize(width: 1200, height: 800)
    let frame = window.frame
    let newOrigin = NSPoint(
        x: frame.midX - defaultSize.width / 2,
        y: frame.midY - defaultSize.height / 2
    )
    window.setFrame(NSRect(origin: newOrigin, size: defaultSize), display: true, animate: true)
}

// MARK: - Font Scale Environment Injection

package struct FontScaleEnvironmentModifier: ViewModifier {
    @ObservedObject private var settings = FontScaleSettings.shared

    package func body(content: Content) -> some View {
        content.environment(\.fontScale, settings.scale)
    }
}

package extension View {
package func withFontScaling() -> some View {
        modifier(FontScaleEnvironmentModifier())
    }
}
