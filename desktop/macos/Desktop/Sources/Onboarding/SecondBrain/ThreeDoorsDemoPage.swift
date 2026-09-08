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
  /// Exact return-link attribute in the template; replaced with this bundle's registered URL scheme so
  /// "Back to Omi" reaches this app and not a sibling bundle.
  static let templateReturnMarkup = #"data-return="omi-computer-dev://onboarding/doors-complete""#
  static let returnPath = "onboarding/doors-complete"

  /// Render the bundled template with the user's push-to-talk chord and return the file to open.
  /// `nil` when the resource is missing from the bundle; the step then opens nothing and logs.
  static func url(
    locator: OmiSoundAssetLocator = .bundled,
    pttTokens: [String],
    urlScheme: String = bundleURLScheme(),
    outputDirectory: URL = FileManager.default.temporaryDirectory
  ) -> URL? {
    guard let template = locator.url(forFileName: fileName),
      let html = try? String(contentsOf: template, encoding: .utf8)
    else { return nil }
    let rendered =
      html
      .replacingOccurrences(of: templateKeyMarkup, with: keyMarkup(for: pttTokens))
      .replacingOccurrences(of: templateReturnMarkup, with: returnMarkup(scheme: urlScheme))
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

  /// Handed to the kernel while the demo step is active (see `ChatProvider.onboardingDemoContext`).
  /// Mirrors the bundled page exactly; update both together.
  static let modelNote = """
    Onboarding demo in progress: the user is solving three riddle doors on a web page Omi opened. \
    Door 1 riddle: "I have keys but open no locks. I have space but no room. You can enter, but never go inside." (answer: keyboard). \
    Door 2: "Which planet has a day longer than its year?" (answer: Venus). \
    Door 3 asks for the last word of the first riddle (answer: inside). \
    The doors appear one at a time, in order. When the user asks about "this riddle" or "the answer", first call the \
    screenshot tool to see which door is on screen now (the page says "Door N of 3"), then answer THAT door from this note. \
    Never assume it is door 1 because door 1 was answered earlier. \
    If the user asks about any of these doors or riddles, answer directly and briefly from this note. \
    Never say you don't remember the riddle or that it was never mentioned.
    """

  static func returnMarkup(scheme: String) -> String {
    #"data-return="\#(scheme)://\#(returnPath)""#
  }

  /// The URL scheme this bundle registered (run.sh rewrites it per named bundle).
  static func bundleURLScheme() -> String {
    if let urlTypes = Bundle.main.infoDictionary?["CFBundleURLTypes"] as? [[String: Any]],
      let schemes = urlTypes.first?["CFBundleURLSchemes"] as? [String],
      let scheme = schemes.first, !scheme.isEmpty
    {
      return scheme
    }
    return "omi-computer-dev"
  }

  /// True for the URL the finished page opens to hand the user back to Omi.
  static func isReturnURL(_ url: URL) -> Bool {
    (url.host ?? "") + url.path == "onboarding/doors-complete"
  }

  /// Handles the return URL (posts `.onboardingDoorsCompleted`); false for any other URL.
  @MainActor static func handleReturnURL(_ url: URL) -> Bool {
    guard isReturnURL(url) else { return false }
    NotificationCenter.default.post(name: .onboardingDoorsCompleted, object: nil)
    return true
  }

  /// Set while the onboarding screen-demo step is active. Both the typed-chat kernel context and
  /// the voice system instruction read it, so the demo's riddles are answerable even before any
  /// screen frame is OCR'd or embedded (capture just started at this step).
  @MainActor static var activeModelNote: String?

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
