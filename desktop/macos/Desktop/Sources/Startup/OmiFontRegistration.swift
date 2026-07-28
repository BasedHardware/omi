import CoreText
import Foundation

/// Registers the bundled Geist / Geist Mono variable fonts with CoreText at launch so
/// the Second Brain design system (`Font.geist` / `Font.geistMono`) resolves them by
/// family name. The fonts ship in the executable target's resource bundle
/// (`Resources/Fonts/*.ttf`), so registration must happen here — `OmiTheme`'s own
/// `Bundle.module` cannot see them.
enum OmiFontRegistration {
  // Touched only on the main thread from `applicationWillFinishLaunching`.
  nonisolated(unsafe) private static var didRegister = false

  static func registerAll() {
    guard !didRegister else { return }
    didRegister = true

    // `.process("Resources")` may or may not preserve the `Fonts/` subdirectory in the
    // built bundle, so look in both the root and the subdirectory and de-duplicate.
    // MUST be `Bundle.resourceBundle`, never SwiftPM's generated `Bundle.module`:
    // the generated accessor only checks the app ROOT and a baked-in absolute
    // `.build` path from the build machine, so it fatalErrors on every real user
    // install (v0.12.110 launch crash) while passing on any machine that has the
    // repo checked out.
    var urls = Set<URL>()
    if let root = Bundle.resourceBundle.urls(forResourcesWithExtension: "ttf", subdirectory: nil) {
      urls.formUnion(root)
    }
    if let sub = Bundle.resourceBundle.urls(forResourcesWithExtension: "ttf", subdirectory: "Fonts") {
      urls.formUnion(sub)
    }

    guard !urls.isEmpty else {
      NSLog("OmiFontRegistration: no bundled .ttf fonts found — Geist will fall back to system font")
      return
    }

    for url in urls {
      var error: Unmanaged<CFError>?
      if !CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error) {
        // A benign failure (e.g. already registered) is fine; the Font helpers fall back.
        let message = error?.takeRetainedValue().localizedDescription ?? "unknown"
        NSLog("OmiFontRegistration: \(url.lastPathComponent) not registered (\(message))")
      }
    }
  }
}
