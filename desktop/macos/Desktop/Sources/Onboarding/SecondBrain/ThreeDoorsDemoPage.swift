import Foundation

/// The onboarding ask-demo page: three riddle doors bundled as `Resources/three-doors.html`.
///
/// The step opens it in the user's default browser so the real floating bar, push-to-talk, and
/// screen capture see it exactly like any other page. The page's "Stuck? Hold ⌥ and say…" hint
/// must show the push-to-talk chord the user actually chose, so the bundled template is rendered
/// with that chord into a per-user cache file and *that* file is opened. (A URL fragment is not
/// reliable here: Launch Services drops fragments when handing a `file:` URL to a browser.)
enum ThreeDoorsDemoPage {
  static let fileName = "three-doors.html"
  /// Exact markup of the default key in the bundled template; replaced per user.
  static let templateKeyMarkup = #"<span id="keys"><span class="key">⌥</span></span>"#

  /// Render the bundled template with the user's push-to-talk chord and return the file to open.
  /// `nil` when the resource is missing from the bundle; the step then opens nothing and logs.
  static func url(
    locator: OmiSoundAssetLocator = .bundled,
    pttTokens: [String],
    outputDirectory: URL = FileManager.default.temporaryDirectory
  ) -> URL? {
    guard let template = locator.url(forFileName: fileName),
      let html = try? String(contentsOf: template, encoding: .utf8)
    else { return nil }
    let rendered = html.replacingOccurrences(of: templateKeyMarkup, with: keyMarkup(for: pttTokens))
    let dir = outputDirectory.appendingPathComponent("omi-onboarding", isDirectory: true)
    let out = dir.appendingPathComponent(fileName)
    do {
      try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
      try rendered.write(to: out, atomically: true, encoding: .utf8)
      return out
    } catch {
      // Fall back to the untouched template rather than opening nothing.
      return template
    }
  }

  static func keyMarkup(for tokens: [String]) -> String {
    let keys = tokens.isEmpty ? ["⌥"] : tokens
    let spans = keys.map { #"<span class="key">\#(escape($0))</span>"# }.joined(separator: " ")
    return #"<span id="keys">\#(spans)</span>"#
  }

  private static func escape(_ s: String) -> String {
    s.replacingOccurrences(of: "&", with: "&amp;")
      .replacingOccurrences(of: "<", with: "&lt;")
      .replacingOccurrences(of: ">", with: "&gt;")
  }
}
