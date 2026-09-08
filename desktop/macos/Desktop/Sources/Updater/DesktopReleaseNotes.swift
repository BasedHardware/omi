import Foundation

/// One shipped desktop release and the user-facing notes that came with it.
///
/// Decoded from the changelog the repo already maintains (`changelog/releases/<version>.json`,
/// consolidated into `CHANGELOG.json`), a trimmed copy of which is bundled with the app as
/// `changelog.json` so the Updates settings section can show release notes offline instead of
/// sending the user to a GitHub release page.
struct DesktopReleaseNote: Identifiable, Equatable, Sendable {
  /// Short version string as published, e.g. "0.12.322".
  let version: String
  /// Publication day in `yyyy-MM-dd` form, or `nil` when the entry omitted it.
  let date: Date?
  /// User-facing notes, in the order the changelog listed them.
  let changes: [String]

  var id: String { version }
}

/// The bundled release-notes list, newest release first.
struct DesktopReleaseNotesCatalog: Equatable, Sendable {
  let releases: [DesktopReleaseNote]

  static let empty = DesktopReleaseNotesCatalog(releases: [])

  /// Decode the changelog document shape (`{"releases": [{version, date, changes}]}`).
  ///
  /// Malformed or partial entries are dropped rather than failing the whole catalog: a single bad
  /// release document must not blank the section for every other release. Entries are re-sorted
  /// newest-first by version so a hand-edited file cannot present them out of order.
  static func decode(from data: Data) throws -> DesktopReleaseNotesCatalog {
    let document = try JSONDecoder().decode(ChangelogDocument.self, from: data)
    let releases =
      document.releases
      .compactMap(DesktopReleaseNote.init(entry:))
      .sorted { DesktopReleaseVersion.isDescending($0.version, $1.version) }
    return DesktopReleaseNotesCatalog(releases: releases)
  }

  /// Notes for the running build, when the bundled changelog covers it.
  func note(forVersion version: String) -> DesktopReleaseNote? {
    releases.first { $0.version == version }
  }

  /// Releases published after `version` — what the user would gain by updating.
  func notes(newerThan version: String) -> [DesktopReleaseNote] {
    releases.filter { DesktopReleaseVersion.isDescending($0.version, version) }
  }

  /// The catalog shipped inside the app bundle. Loaded once; an absent or unreadable resource
  /// yields an empty catalog so the Updates section degrades to its links instead of failing.
  static let bundled: DesktopReleaseNotesCatalog = loadBundled()

  /// `OmiSoundAssetLocator` rather than `Bundle.resourceBundle.url(forResource:)`: SwiftPM writes
  /// `.process("Resources")` files flat at the resource bundle's root, but that bundle also carries
  /// a `Contents/Resources/` (the staged agent Node runtime), so `Bundle.resourcePath` resolves
  /// there and the flat root — where `changelog.json` actually lands — is never searched. The
  /// locator checks every container an installed app, a local build, or a test host can be using.
  static func loadBundled() -> DesktopReleaseNotesCatalog {
    guard
      let url = OmiSoundAssetLocator.bundled.url(forFileName: "changelog.json"),
      let data = try? Data(contentsOf: url),
      let catalog = try? decode(from: data)
    else {
      return .empty
    }
    return catalog
  }
}

// MARK: - Version ordering

enum DesktopReleaseVersion {
  /// Dot-separated numeric components, ignoring any build/suffix noise ("0.12.322" -> [0, 12, 322]).
  static func components(_ version: String) -> [Int] {
    version
      .split(separator: ".")
      .map { part in
        Int(part.prefix { $0.isNumber }) ?? 0
      }
  }

  /// True when `lhs` is a strictly newer version than `rhs`.
  static func isDescending(_ lhs: String, _ rhs: String) -> Bool {
    let left = components(lhs)
    let right = components(rhs)
    for index in 0..<max(left.count, right.count) {
      let l = index < left.count ? left[index] : 0
      let r = index < right.count ? right[index] : 0
      if l != r { return l > r }
    }
    return false
  }
}

// MARK: - Decoding

extension DesktopReleaseNote {
  fileprivate init?(entry: ChangelogDocument.Entry) {
    let version = entry.version.trimmingCharacters(in: .whitespacesAndNewlines)
    let changes =
      entry.changes?
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty } ?? []
    guard !version.isEmpty, !changes.isEmpty else { return nil }
    self.init(
      version: version,
      date: entry.date.flatMap(DesktopReleaseNote.day(from:)),
      changes: changes)
  }

  /// `yyyy-MM-dd` — the form the changelog generator writes.
  ///
  /// Read in the reader's own time zone, not UTC: this is a calendar day, and a UTC midnight
  /// formatted west of Greenwich renders as the day before ("2026-09-08" showing as September 7).
  static func day(from raw: String) -> Date? {
    dayFormatter.date(from: raw.trimmingCharacters(in: .whitespacesAndNewlines))
  }

  private static let dayFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = .current
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter
  }()
}

private struct ChangelogDocument: Decodable {
  struct Entry: Decodable {
    let version: String
    let date: String?
    let changes: [String]?
  }

  let releases: [Entry]
}
