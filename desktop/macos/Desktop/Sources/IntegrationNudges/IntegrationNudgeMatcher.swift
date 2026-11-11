import Foundation

/// Resolves "which integration is this window about?" from the frontmost app.
///
/// Pure and synchronous so the whole recognition surface — including every
/// false-positive risk in the browser-title heuristics — is unit-testable
/// without a window server.
enum IntegrationNudgeMatcher {
  struct Match: Equatable {
    let entry: IntegrationNudgeCatalogEntry
    let trigger: IntegrationNudgeTrigger
  }

  /// The frontmost window, as much of it as the app can see.
  ///
  /// `windowTitle` is nil when Screen Recording permission has not been granted.
  /// That degrades browser-site recognition to nothing and leaves native-app
  /// recognition working, which is the right failure direction: a missed nudge,
  /// never a wrong one.
  struct Window: Equatable {
    let bundleIdentifier: String?
    let windowTitle: String?

    init(bundleIdentifier: String?, windowTitle: String? = nil) {
      self.bundleIdentifier = bundleIdentifier
      self.windowTitle = windowTitle
    }
  }

  /// Returns the first catalog entry the window matches, or nil.
  ///
  /// Native-app triggers are evaluated before browser-title triggers across the
  /// whole catalog. A bundle identifier is an exact fact; a window title is a
  /// guess, so the fact wins. Without this ordering, ChatGPT.app — whose window
  /// title also contains "ChatGPT" — could be attributed to the browser trigger
  /// and reported under the wrong `trigger_kind`.
  static func match(_ window: Window, in catalog: [IntegrationNudgeCatalogEntry] = IntegrationNudgeCatalog.nudgeable)
    -> Match?
  {
    if let bundleIdentifier = window.bundleIdentifier {
      for entry in catalog {
        for trigger in entry.triggers {
          guard case .application(let identifiers) = trigger.match else { continue }
          if identifiers.contains(bundleIdentifier) {
            return Match(entry: entry, trigger: trigger)
          }
        }
      }
    }

    guard isBrowser(bundleIdentifier: window.bundleIdentifier),
      let title = window.windowTitle,
      !title.isEmpty
    else { return nil }

    let haystack = normalizedTitle(title)
    for entry in catalog {
      for trigger in entry.triggers {
        switch trigger.match {
        case .application:
          continue
        case .browserTitleSite(let names):
          if names.contains(where: { endsWithSiteName(haystack, $0.lowercased()) }) {
            return Match(entry: entry, trigger: trigger)
          }
        case .browserTitleGoogleWorkspaceMailbox:
          if isGoogleWorkspaceMailbox(haystack) {
            return Match(entry: entry, trigger: trigger)
          }
        }
      }
    }

    return nil
  }

  /// Gmail on a Workspace domain titles the mailbox with the organization's
  /// name, not "Gmail" — "Inbox (3,012) - you@company.com - Acme Mail". The
  /// account address in the middle segment is what makes this Gmail rather than
  /// any other webmail, so both halves are required: a trailing " mail" alone
  /// would claim Proton Mail and Yahoo Mail, and an address alone appears in
  /// every mail client on the web.
  static func isGoogleWorkspaceMailbox(_ normalizedTitle: String) -> Bool {
    guard normalizedTitle.hasSuffix(" mail") else { return false }
    return
      normalizedTitle
      .components(separatedBy: " - ")
      .dropLast()
      .contains { segment in
        guard let at = segment.firstIndex(of: "@") else { return false }
        let local = segment[segment.startIndex..<at]
        let domain = segment[segment.index(after: at)...]
        return !local.isEmpty && domain.contains(".") && !domain.hasSuffix(".")
      }
  }

  /// True when the site's own name is the whole title, or is the last segment
  /// behind one of the separators sites actually use.
  ///
  /// The separator is what makes this a site name rather than a word the title
  /// ended on. "home / x" is X; "x marks the spot" is not, and neither is "how
  /// to create studio ghibli style art with chatgpt".
  ///
  /// A one-character name never stands alone. "X" as an entire title carries no
  /// evidence of being x.com — a Stripe checkout page in the measured corpus is
  /// titled exactly that — so X has to arrive with its separator, as it does in
  /// every real x.com title ("Home / X").
  static func endsWithSiteName(_ normalizedTitle: String, _ name: String) -> Bool {
    if name.count > 1, normalizedTitle == name { return true }
    return titleSeparators.contains { normalizedTitle.hasSuffix($0 + name) }
  }

  /// " / ", " - " and " | " are the three observed in front of these sites' own
  /// names in real browser history; the two dashes are the same separator in
  /// typographic form and cost nothing to accept.
  ///
  /// ": " is deliberately absent. Sites lead with it — "ChatGPT: Chat, Work,
  /// Create & Code with AI" — rather than close with it, so as a *suffix* rule
  /// it could only ever fire on prose that happened to end in the name.
  private static let titleSeparators = [" - ", " – ", " — ", " | ", " / "]

  /// Lowercased, trimmed, stripped of the invisible directionality marks sites
  /// emit, and stripped of the browser's own trailing chrome so a site name the
  /// browser appended its product name after still reads as the end of the
  /// title.
  ///
  /// Gemini is why the invisible characters matter: it titles its pages
  /// "\u{200E}Google Gemini", and a leading left-to-right mark is enough to make
  /// an exact comparison against "google gemini" fail.
  ///
  /// On macOS the Chromium browsers do *not* append their name — a Chrome window
  /// showing Gmail is titled exactly "Inbox (12) - you@corp.com - Gmail". The
  /// ones that do are Firefox and its relatives, so those are what this strips.
  /// Chromium suffixes stay in the list only because they cost nothing and some
  /// builds and window managers do add them.
  static func normalizedTitle(_ title: String) -> String {
    var value = String(title.unicodeScalars.filter { !invisibleFormatting.contains($0) })
      .lowercased()
      .trimmingCharacters(in: .whitespacesAndNewlines)
    var didStrip = true
    while didStrip {
      didStrip = false
      for chrome in browserTitleChrome where value.hasSuffix(chrome) {
        value = String(value.dropLast(chrome.count)).trimmingCharacters(in: .whitespaces)
        didStrip = true
        break
      }
    }
    return value
  }

  /// Bidi controls and zero-width characters: invisible, and load-bearing for
  /// nothing a title match should care about.
  private static let invisibleFormatting: CharacterSet = {
    var set = CharacterSet(charactersIn: "\u{200B}"..."\u{200F}")
    set.insert(charactersIn: "\u{202A}"..."\u{202E}")
    set.insert(charactersIn: "\u{2066}"..."\u{2069}")
    set.insert("\u{FEFF}")
    return set
  }()

  private static let browserTitleChrome = [
    " — mozilla firefox", " - mozilla firefox",
    " — firefox developer edition", " - firefox developer edition",
    " — zen browser", " - zen browser",
    " - vivaldi", " — vivaldi",
    " - google chrome", " — google chrome",
    " - brave", " — brave",
    " - microsoft edge", " — microsoft edge",
  ]

  static func isBrowser(bundleIdentifier: String?) -> Bool {
    guard let bundleIdentifier else { return false }
    return IntegrationNudgeCatalog.browserBundleIdentifiers.contains(bundleIdentifier)
  }
}
