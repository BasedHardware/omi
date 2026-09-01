import Foundation

/// The onboarding ask-demo page: three riddle doors bundled as `Resources/three-doors.html`.
///
/// The step opens it in the user's default browser so the real floating bar, push-to-talk, and
/// screen capture see it exactly like any other page. The push-to-talk chord is passed in the URL
/// fragment so the page's "Stuck? Hold ⌥ and say…" hint shows the key the user actually chose.
enum ThreeDoorsDemoPage {
  static let fileName = "three-doors.html"

  /// `nil` when the resource is missing from the bundle; the step then shows no open button
  /// instead of opening nothing.
  static func url(locator: OmiSoundAssetLocator = .bundled, pttTokens: [String]) -> URL? {
    guard let file = locator.url(forFileName: fileName) else { return nil }
    guard var components = URLComponents(url: file, resolvingAgainstBaseURL: false) else { return file }
    let joined = pttTokens.joined(separator: ",")
    if !joined.isEmpty {
      // URLComponents percent-encodes the fragment itself; hand it the raw text.
      components.fragment = "key=" + joined
    }
    return components.url ?? file
  }
}
