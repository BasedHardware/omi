import AppKit
import CoreText
import SwiftUI

/// Type-size registers for the desktop app. Use with `scaledFont(size:weight:)`
/// (`.scaledFont(size: OmiType.body)`) instead of numeric literals so the
/// hierarchy stays trimodal and intentional. Off-register sizes (9, 12, 14,
/// 17, 18) round to the nearest register.
package enum OmiType {
  /// Single swap point for the product typeface. Geist is bundled under the
  /// SIL Open Font License 1.1 in `Resources/Licenses/Geist-OFL.txt`.
  package static let familyName = "Geist"

  /// Display: onboarding hero titles.
  package static let hero: CGFloat = 40
  /// Page/section headers.
  package static let title: CGFloat = 28
  /// Card titles, prominent labels.
  package static let heading: CGFloat = 20
  /// Subheads, emphasized rows, primary buttons.
  package static let subheading: CGFloat = 15
  /// Default body text (macOS system body).
  package static let body: CGFloat = 13
  /// Secondary labels, captions.
  package static let caption: CGFloat = 11
  /// Micro badges, counters.
  package static let micro: CGFloat = 10

  /// Register the bundled variable font once for the current process. Calling
  /// this during app launch keeps every `scaledFont` call on the same family.
  @discardableResult
  package static func registerBundledTypeface() -> Bool {
    OmiBundledTypeface.isRegistered
  }

  package static func font(
    size: CGFloat,
    weight: Font.Weight = .regular,
    design: Font.Design = .default
  ) -> Font {
    guard design == .default else {
      return .system(size: size, weight: weight, design: design)
    }
    guard registerBundledTypeface() else {
      return .system(size: size, weight: weight)
    }
    return .custom(familyName, size: size).weight(weight)
  }

  package static func appKitFont(size: CGFloat) -> NSFont {
    _ = registerBundledTypeface()
    return NSFont(name: familyName, size: size) ?? .systemFont(ofSize: size)
  }
}

private enum OmiBundledTypeface {
  static let isRegistered: Bool = {
    guard let url = Bundle.module.url(
      forResource: "Geist",
      withExtension: "ttf",
      subdirectory: "Fonts"
    ) else {
      NSLog("OmiType: bundled Geist font is missing")
      return false
    }

    var registrationError: Unmanaged<CFError>?
    let registered = CTFontManagerRegisterFontsForURL(url as CFURL, .process, &registrationError)
    if !registered, let error = registrationError?.takeRetainedValue() {
      NSLog("OmiType: could not register Geist: %@", error.localizedDescription)
    }
    return registered
  }()
}
