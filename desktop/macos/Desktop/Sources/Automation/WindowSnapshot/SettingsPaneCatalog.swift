import Foundation
import OmiSupport

/// The names System Settings gives its panes, read from the installed
/// System Settings extensions in every language they ship.
///
/// Each extension carries its display name in `InfoPlist.loctable` (or a
/// `*.lproj/InfoPlist.strings` on older systems), and some names live in an
/// extension's own string table: General's subpages, for one, are keys of
/// General's `Localizable` table. Bundle ids are lowercased throughout.
struct SettingsPaneCatalog: Equatable, Sendable {
  typealias Floor = GeneratedUIAutomationSafetyFloor

  /// Every localized display name, per extension.
  let displayNames: [String: [String]]
  /// The installed extensions that are System Settings panes.
  let settingsPaneExtensionIDs: Set<String>
  /// Localized values of the string-table keys the floor names, keyed by `id|table|key`.
  let strings: [String: [String]]

  init(displayNames: [String: [String]], settingsPaneExtensionIDs: Set<String>, strings: [String: [String]] = [:]) {
    self.displayNames = Dictionary(lastWriteWins: displayNames.map { ($0.key.lowercased(), $0.value) })
    self.settingsPaneExtensionIDs = Set(settingsPaneExtensionIDs.map { $0.lowercased() })
    self.strings = Dictionary(lastWriteWins: strings.map { ($0.key.lowercased(), $0.value) })
  }

  static func stringsKey(_ extensionBundleID: String, _ table: String, _ key: String) -> String {
    "\(extensionBundleID)|\(table)|\(key)".lowercased()
  }

  func tableStrings(_ reference: Floor.SettingsStrings) -> [String] {
    reference.keys.flatMap { strings[Self.stringsKey(reference.extensionBundleID, reference.table, $0)] ?? [] }
  }

  /// English titles, plus every installed name of the extensions and table strings listed.
  func names(_ names: Floor.SettingsNames) -> [String] {
    names.titles + names.extensionBundleIDs.flatMap { displayNames[$0.lowercased()] ?? [] }
      + names.strings.flatMap(tableStrings)
  }

  static let installed = SettingsPaneCatalog(
    directory: URL(fileURLWithPath: "/System/Library/ExtensionKit/Extensions", isDirectory: true))

  private static let settingsExtensionPoint = "com.apple.Settings.extension.ui"

  /// Every string table key any list in the floor names.
  private static var referencedStrings: [Floor.SettingsStrings] {
    Floor.sensitiveSettingsPanes.flatMap(\.names.strings) + Floor.allowedSettingsPanes.strings
      + Floor.generalAllowedSubpages.strings + Floor.privacySubpages.strings
      + [.init(extensionBundleID: Floor.generalExtensionBundleID, table: "Localizable", keys: ["General"])]
  }

  init(directory: URL, references: [Floor.SettingsStrings]? = nil) {
    let references = references ?? Self.referencedStrings
    var displayNames: [String: [String]] = [:]
    var paneIDs: Set<String> = []
    var strings: [String: [String]] = [:]
    let fileManager = FileManager.default
    let appexes = (try? fileManager.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? []
    for appex in appexes where appex.pathExtension == "appex" {
      let contents = appex.appendingPathComponent("Contents", isDirectory: true)
      guard
        let info = NSDictionary(contentsOf: contents.appendingPathComponent("Info.plist")),
        let bundleID = (info["CFBundleIdentifier"] as? String)?.lowercased()
      else { continue }
      let attributes = info["EXAppExtensionAttributes"] as? NSDictionary
      let isPane = attributes?["EXExtensionPointIdentifier"] as? String == Self.settingsExtensionPoint
      let wanted = references.filter { $0.extensionBundleID.lowercased() == bundleID }
      guard isPane || !wanted.isEmpty else { continue }
      if isPane { paneIDs.insert(bundleID) }
      let resources = contents.appendingPathComponent("Resources", isDirectory: true)
      var names: [String] = (info["CFBundleDisplayName"] as? String).map { [$0] } ?? []
      names += Self.localizedValues(table: "InfoPlist", keys: ["CFBundleDisplayName"], in: resources).flatMap(\.value)
      displayNames[bundleID] = names
      for reference in wanted {
        for (key, values) in Self.localizedValues(table: reference.table, keys: reference.keys, in: resources) {
          strings[Self.stringsKey(bundleID, reference.table, key), default: []].append(contentsOf: values)
        }
      }
    }
    self.init(displayNames: displayNames, settingsPaneExtensionIDs: paneIDs, strings: strings)
  }

  /// The values of `keys` in `table`, in every language: `<table>.loctable`
  /// (macOS 14 and later) and any `*.lproj/<table>.strings`.
  private static func localizedValues(table: String, keys: [String], in resources: URL) -> [String: [String]] {
    var found: [String: [String]] = [:]
    let wanted = Set(keys)
    func collect(_ strings: NSDictionary?) {
      guard let strings else { return }
      for key in wanted {
        if let value = strings[key] as? String, !value.isEmpty { found[key, default: []].append(value) }
      }
    }
    if let loctable = NSDictionary(contentsOf: resources.appendingPathComponent("\(table).loctable")) {
      for case let languageTable as NSDictionary in loctable.allValues { collect(languageTable) }
    }
    let lprojs = (try? FileManager.default.contentsOfDirectory(at: resources, includingPropertiesForKeys: nil)) ?? []
    for lproj in lprojs where lproj.pathExtension == "lproj" {
      collect(NSDictionary(contentsOf: lproj.appendingPathComponent("\(table).strings")))
    }
    return found
  }
}
