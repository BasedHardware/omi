import SwiftUI
import Combine
import CoreText

// MARK: - Inter Font Registration

/// Registers the Inter variable font from the app bundle at launch.
/// Call `InterFont.register()` once from app startup.
enum InterFont {
    static var isRegistered = false

    static func register() {
        guard !isRegistered else { return }
        isRegistered = true

        let fontNames = ["InterVariable", "InterVariable-Italic"]
        for name in fontNames {
            guard let url = Bundle.resourceBundle.url(forResource: name, withExtension: "ttf") else {
                print("[Font] \(name).ttf not found in resource bundle")
                continue
            }
            var error: Unmanaged<CFError>?
            if CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error) {
                print("[Font] Registered \(name)")
            } else {
                print("[Font] Failed to register \(name): \(error?.takeRetainedValue().localizedDescription ?? "unknown")")
            }
        }
    }

    /// Create an Inter font with the given size and weight.
    /// Falls back to system font if Inter is not available.
    static func font(size: CGFloat, weight: Font.Weight = .regular) -> Font {
        let nsFont = nsFont(size: size, weight: weight)
        return Font(nsFont)
    }

    /// NSFont variant for AppKit contexts (NootoTextEditor, etc.)
    static func nsFont(size: CGFloat, weight: Font.Weight = .regular) -> NSFont {
        // Inter variable font uses weight axis
        let traits: [NSFontDescriptor.TraitKey: Any] = [
            .weight: nsFontWeight(from: weight)
        ]
        let descriptor = NSFontDescriptor(fontAttributes: [
            .family: "Inter",
            .traits: traits
        ])
        return NSFont(descriptor: descriptor, size: size) ?? NSFont.systemFont(ofSize: size, weight: nsFontWeight(from: weight))
    }

    private static func nsFontWeight(from weight: Font.Weight) -> NSFont.Weight {
        switch weight {
        case .ultraLight: return .ultraLight
        case .thin: return .thin
        case .light: return .light
        case .regular: return .regular
        case .medium: return .medium
        case .semibold: return .semibold
        case .bold: return .bold
        case .heavy: return .heavy
        case .black: return .black
        default: return .regular
        }
    }
}

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

// MARK: - Scaled Font Modifier (uses Inter)

struct ScaledFontModifier: ViewModifier {
    @Environment(\.fontScale) private var fontScale
    let size: CGFloat
    var weight: Font.Weight = .regular
    var design: Font.Design = .default

    func body(content: Content) -> some View {
        let scaledSize = round(size * fontScale)
        if design == .monospaced {
            content.font(.system(size: scaledSize, weight: weight, design: .monospaced))
        } else {
            content.font(InterFont.font(size: scaledSize, weight: weight))
        }
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
        content.font(InterFont.font(size: round(size * fontScale), weight: weight))
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
    guard let window = NSApp.keyWindow ?? NSApp.windows.first(where: { $0.title.contains("nooto") || $0.title.contains("Nooto") }) else { return }
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
