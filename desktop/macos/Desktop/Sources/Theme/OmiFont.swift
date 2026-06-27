import SwiftUI
import Combine

// MARK: - Font Scale Settings

class FontScaleSettings: ObservableObject {
    static let shared = FontScaleSettings()
    private let defaults = UserDefaults.standard

    @Published var scale: CGFloat {
        didSet {
            defaults.set(scale, forKey: "fontScale")
        }
    }

    private init() {
        self.scale = defaults.object(forKey: "fontScale") as? CGFloat ?? 1.0
    }

    func resetToDefault() {
        scale = 1.0
    }
}

// MARK: - Environment Key

private struct FontScaleKey: EnvironmentKey {
    static let defaultValue: CGFloat = 1.0
}

extension EnvironmentValues {
    var fontScale: CGFloat {
        get { self[FontScaleKey.self] }
        set { self[FontScaleKey.self] = newValue }
    }
}

// MARK: - Scaled Font Modifier

struct ScaledFontModifier: ViewModifier {
    @Environment(\.fontScale) private var fontScale
    let size: CGFloat
    var weight: Font.Weight = .regular
    var design: Font.Design = .default

    func body(content: Content) -> some View {
        content.font(.system(size: round(size * fontScale), weight: weight, design: design))
    }
}

extension View {
    func scaledFont(size: CGFloat, weight: Font.Weight = .regular, design: Font.Design = .default) -> some View {
        modifier(ScaledFontModifier(size: size, weight: weight, design: design))
    }
}

// MARK: - Monospaced Digit Variant

struct ScaledMonospacedDigitFontModifier: ViewModifier {
    @Environment(\.fontScale) private var fontScale
    let size: CGFloat
    var weight: Font.Weight = .regular

    func body(content: Content) -> some View {
        content.font(.system(size: round(size * fontScale), weight: weight).monospacedDigit())
    }
}

struct ScaledMonospacedFontModifier: ViewModifier {
    @Environment(\.fontScale) private var fontScale
    let size: CGFloat
    var weight: Font.Weight = .regular

    func body(content: Content) -> some View {
        content.font(.system(size: round(size * fontScale), weight: weight).monospaced())
    }
}

extension View {
    func scaledMonospacedDigitFont(size: CGFloat, weight: Font.Weight = .regular) -> some View {
        modifier(ScaledMonospacedDigitFontModifier(size: size, weight: weight))
    }

    func scaledMonospacedFont(size: CGFloat, weight: Font.Weight = .regular) -> some View {
        modifier(ScaledMonospacedFontModifier(size: size, weight: weight))
    }
}

// MARK: - Window Size Reset

func resetWindowToDefaultSize() {
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

struct FontScaleEnvironmentModifier: ViewModifier {
    @ObservedObject private var settings = FontScaleSettings.shared

    func body(content: Content) -> some View {
        content.environment(\.fontScale, settings.scale)
    }
}

extension View {
    func withFontScaling() -> some View {
        modifier(FontScaleEnvironmentModifier())
    }
}
