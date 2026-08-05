import CoreText
import Foundation

/// Registers the bundled display and UI faces with CoreText at launch so the design
/// systems resolve them by family name: Geist / Geist Mono (`Font.geist` /
/// `Font.geistMono`) and Open Runde (`Font.openRunde` — the glass system's display face
/// at and above `Font.inkDisplayThreshold`). The fonts ship in the executable target's
/// resource bundle (`Resources/Fonts/*.ttf` and `*.otf`), so registration must happen
/// here — `OmiTheme`'s own `Bundle.module` cannot see them.
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
    // Geist ships as `.ttf`, Open Runde as `.otf`; both extensions must be swept or the
    // missing family silently falls back to the system font at every call site.
    var urls = Set<URL>()
    for ext in ["ttf", "otf"] {
      if let root = Bundle.resourceBundle.urls(forResourcesWithExtension: ext, subdirectory: nil) {
        urls.formUnion(root)
      }
      if let sub = Bundle.resourceBundle.urls(forResourcesWithExtension: ext, subdirectory: "Fonts") {
        urls.formUnion(sub)
      }
    }

    guard !urls.isEmpty else {
      NSLog("OmiFontRegistration: no bundled fonts found — Geist and Open Runde fall back to the system font")
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
