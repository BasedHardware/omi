import AppKit
import Combine
import CoreText
import SwiftUI

// MARK: - Geist / Geist Mono (Second Brain design system)
//
// The design uses Geist for UI and Geist Mono for meta/labels/time — never
// Inter/Roboto/system. The bundled files are single VARIABLE fonts; we build an
// exact weight by applying the `wght` variation axis via CoreText, so 400/500/600/700
// are real, not synthesized. Fonts are registered at launch by the executable target
// (`OmiFontRegistration`); these helpers resolve them by family name once registered,
// and fall back to the system font if registration hasn't happened yet (e.g. previews).

private enum GeistFamily {
  static let sans = "Geist"
  static let mono = "Geist Mono"
}

/// FourCC for the standard weight axis ('wght').
private let kGeistWeightAxis: Int = 0x7767_6874

private func geistWeightValue(_ weight: Font.Weight) -> CGFloat {
  switch weight {
  case .ultraLight: return 100
  case .thin: return 200
  case .light: return 300
  case .regular: return 400
  case .medium: return 500
  case .semibold: return 600
  case .bold: return 700
  case .heavy: return 800
  case .black: return 900
  default: return 400
  }
}

private func makeGeist(_ family: String, size: CGFloat, weight: Font.Weight) -> Font {
  let variation: [NSNumber: NSNumber] = [
    NSNumber(value: kGeistWeightAxis): NSNumber(value: Double(geistWeightValue(weight)))
  ]
  let attrs: [CFString: Any] = [
    kCTFontFamilyNameAttribute: family,
    kCTFontVariationAttribute: variation,
  ]
  let descriptor = CTFontDescriptorCreateWithAttributes(attrs as CFDictionary)
  let ctFont = CTFontCreateWithFontDescriptor(descriptor, size, nil)
  // If Geist isn't registered, CoreText falls back to a system font — detect and
  // return an explicit system font so layout stays stable before registration.
  let resolvedFamily = CTFontCopyFamilyName(ctFont) as String
  if resolvedFamily == family {
    return Font(ctFont)
  }
  return .system(size: size, weight: weight, design: family == GeistFamily.mono ? .monospaced : .default)
}

extension Font {
  /// Geist (UI). Unscaled — prefer the `.geist(...)` view modifier for a11y font scaling.
  package static func geist(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
    makeGeist(GeistFamily.sans, size: size, weight: weight)
  }

  /// Geist Mono (meta / labels / time).
  package static func geistMono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
    makeGeist(GeistFamily.mono, size: size, weight: weight)
  }
}

// MARK: - Scaled Geist view modifiers (respect FontScaleSettings)

package struct GeistFontModifier: ViewModifier {
  @Environment(\.fontScale) private var fontScale
  let mono: Bool
  let size: CGFloat
  let weight: Font.Weight
  let tracking: CGFloat?

  package func body(content: Content) -> some View {
    let s = round(size * fontScale)
    return
      content
      .font(mono ? .geistMono(s, weight) : .geist(s, weight))
      .tracking(tracking ?? 0)
  }
}

extension View {
  /// Geist UI text. `tracking` is in points; for the design's em values pass `size * em`
  /// (e.g. a 26px title at -0.02em → `tracking: 26 * -0.02`).
  package func geist(size: CGFloat, weight: Font.Weight = .regular, tracking: CGFloat? = nil) -> some View {
    modifier(GeistFontModifier(mono: false, size: size, weight: weight, tracking: tracking))
  }

  /// Geist Mono meta/label text. Section labels use letter-spacing ~.08–.1em.
  package func geistMono(size: CGFloat, weight: Font.Weight = .regular, tracking: CGFloat? = nil) -> some View {
    modifier(GeistFontModifier(mono: true, size: size, weight: weight, tracking: tracking))
  }
}

// MARK: - Font Scale Settings

@MainActor package class FontScaleSettings: ObservableObject {
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

extension EnvironmentValues {
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

extension View {
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

extension View {
  package func scaledMonospacedDigitFont(size: CGFloat, weight: Font.Weight = .regular) -> some View {
    modifier(ScaledMonospacedDigitFontModifier(size: size, weight: weight))
  }

  package func scaledMonospacedFont(size: CGFloat, weight: Font.Weight = .regular) -> some View {
    modifier(ScaledMonospacedFontModifier(size: size, weight: weight))
  }
}

// MARK: - Window Size Reset

@MainActor package func resetWindowToDefaultSize() {
  guard
    let window = NSApp.keyWindow ?? NSApp.windows.first(where: { $0.title.contains("omi") || $0.title.contains("Omi") })
  else { return }
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

extension View {
  package func withFontScaling() -> some View {
    modifier(FontScaleEnvironmentModifier())
  }
}
