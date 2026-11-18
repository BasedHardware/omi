import CoreGraphics
import XCTest

@testable import Omi_Computer

/// System Settings: a pane is read only when it is positively identified as
/// ordinary, in any language; everything else is refused.
final class SettingsPaneGuardTests: XCTestCase {
  private static let general = "com.apple.systempreferences.GeneralSettings"

  private static func key(_ name: String) -> String {
    SettingsPaneCatalog.stringsKey(general, "Localizable", name)
  }

  /// What the installed extensions answer, in English, German, French and Finnish.
  private let paneGuard = SettingsPaneGuard(
    catalog: SettingsPaneCatalog(
      displayNames: [
        "com.apple.settings.PrivacySecurity.extension": [
          "Privacy & Security", "Datenschutz & Sicherheit", "Confidentialité et sécurité", "Tietosuoja ja turvallisuus",
        ],
        general: ["General", "Allgemein", "Général", "Yleiset"],
        "com.apple.Sound-Settings.extension": ["Sound", "Ton", "Son", "Ääni"],
        "com.apple.Sharing-Settings.extension": ["Sharing", "Teilen", "Partage"],
        "com.apple.wifi-settings-extension": ["Wi‑Fi", "WLAN"],
        "com.apple.Accessibility-Settings.extension": ["Accessibility", "Bedienungshilfen"],
      ],
      settingsPaneExtensionIDs: [
        "com.apple.settings.PrivacySecurity.extension", general, "com.apple.Sound-Settings.extension",
        "com.apple.Sharing-Settings.extension", "com.apple.wifi-settings-extension",
        "com.apple.Accessibility-Settings.extension",
      ],
      strings: [
        key("General"): ["General", "Allgemein", "Général", "Yleiset"],
        key("About"): ["About", "Info", "À propos", "Tietoja"],
        key("Sharing"): ["Sharing", "Teilen", "Partage", "Jakaminen"],
        key("Login Items & Extensions"): [
          "Login Items & Extensions", "Anmeldeobjekte & Erweiterungen", "Ouverture et extensions",
        ],
        key("AutoFill & Passwords"): ["AutoFill & Passwords", "Automatisch ausfüllen & Passwörter"],
        SettingsPaneCatalog.stringsKey("com.apple.settings.PrivacySecurity.extension", "Localizable", "ALL_FILES"): [
          "Full Disk Access", "Festplattenvollzugriff",
        ],
      ]))

  /// System Settings' shape: a sidebar outline of rows, a content group with
  /// its own table whose selected row must never pose as the sidebar.
  private func settingsWindow(
    title: String, selected: String?, sidebar: [String]? = nil, sheet: Bool = false, search: String = ""
  ) -> FixtureAXNode {
    let names =
      sidebar ?? [
        "Wi‑Fi", "General", "Allgemein", "Général", "Yleiset", "Sound", "Ton", "Privacy & Security",
        "Datenschutz & Sicherheit", "Full Disk Access", "Neue Funktion", "Accessibility", "Bedienungshilfen",
      ]
    let rows = names.map { name in
      axNode(
        "AXRow", selected: name == selected,
        children: [axNode("AXCell", children: [axNode("AXStaticText", value: .string(name))])])
    }
    var children = [
      axNode(
        "AXSplitGroup",
        children: [
          axNode("AXSearchField", description: "Search", value: .string(search)),
          axNode(
            "AXScrollArea",
            children: [
              axNode(
                "AXOutline", description: "Sidebar", frame: CGRect(x: 0, y: 50, width: 200, height: 500), children: rows
              )
            ]),
          axNode(
            "AXGroup",
            children: [
              axNode(
                "AXTable", frame: CGRect(x: 250, y: 50, width: 600, height: 300),
                children: [axNode("AXRow", selected: true, children: [axNode("AXStaticText", value: .string("Sound"))])]
              )
            ]),
        ])
    ]
    if sheet { children.append(axNode("AXSheet", "Enter password")) }
    return axNode("AXWindow", title, frame: CGRect(x: 0, y: 0, width: 900, height: 600), children: children)
  }

  private func verdict(_ window: FixtureAXNode) -> SettingsPaneGuard.Verdict {
    let source = FixtureAccessibilitySource(windows: [window])
    return paneGuard.evaluate(window: 1, title: window.attributes[AXName.title]?.string ?? "", source: source)
  }

  func testAnOrdinaryPaneIsAllowedInAnyLanguage() {
    XCTAssertEqual(verdict(settingsWindow(title: "Sound", selected: "Sound")), .allowed)
    XCTAssertEqual(verdict(settingsWindow(title: "Ton", selected: "Ton")), .allowed)
    XCTAssertEqual(verdict(settingsWindow(title: "Info", selected: "Allgemein")), .allowed, "General > About in German")
  }

  func testAPaneUnderPrivacyIsRefusedByTheSelectedSidebarRow() {
    XCTAssertEqual(
      verdict(settingsWindow(title: "Location Services", selected: "Privacy & Security")),
      .sensitive(pane: "Privacy & Security"))
    XCTAssertEqual(
      verdict(settingsWindow(title: "Ortungsdienste", selected: "Datenschutz & Sicherheit")),
      .sensitive(pane: "Privacy & Security"))
  }

  func testSensitiveGeneralSubpagesAreRefusedInEveryLanguage() {
    XCTAssertEqual(verdict(settingsWindow(title: "Sharing", selected: "General")), .sensitive(pane: "Sharing"))
    XCTAssertEqual(verdict(settingsWindow(title: "Jakaminen", selected: "Yleiset")), .sensitive(pane: "Sharing"))
    XCTAssertEqual(
      verdict(settingsWindow(title: "Anmeldeobjekte & Erweiterungen", selected: "Allgemein")),
      .sensitive(pane: "Login Items & Extensions"))
    XCTAssertEqual(
      verdict(settingsWindow(title: "Ouverture et extensions", selected: "Général")),
      .sensitive(pane: "Login Items & Extensions"))
    XCTAssertEqual(
      verdict(settingsWindow(title: "AutoFill & Passwords", selected: "General")), .sensitive(pane: "Passwords"))
  }

  func testAPrivacyPageIsRefusedByItsTitleWhateverTheSidebarSelects() {
    XCTAssertEqual(
      verdict(settingsWindow(title: "Full Disk Access", selected: "Sound")), .sensitive(pane: "Privacy & Security"))
    XCTAssertEqual(
      verdict(settingsWindow(title: "Festplattenvollzugriff", selected: "Ton")), .sensitive(pane: "Privacy & Security"))
    XCTAssertEqual(
      verdict(settingsWindow(title: "Bedienungshilfen", selected: "Ton")), .sensitive(pane: "Privacy & Security"),
      "Accessibility under Privacy, reached while the sidebar stays on Sound")
    XCTAssertEqual(
      verdict(settingsWindow(title: "Accessibility", selected: "Accessibility")), .allowed,
      "the top-level Accessibility pane shares the name and stays readable")
    XCTAssertEqual(verdict(settingsWindow(title: "Bedienungshilfen", selected: "Bedienungshilfen")), .allowed)
  }

  func testASidebarThatCannotBePlacedIsRefused() {
    var window = settingsWindow(title: "Sound", selected: "Sound")
    // Remove the outline's position: a content table could then pose as the sidebar.
    func strip(_ node: inout FixtureAXNode) {
      if node.attributes[AXName.role] == .string("AXOutline") { node.attributes[AXName.position] = nil }
      for index in node.children.indices { strip(&node.children[index]) }
    }
    strip(&window)
    XCTAssertEqual(verdict(window), .undetermined)
  }

  func testAnythingNotPositivelyIdentifiedIsRefused() {
    // A General subpage nobody listed, as after an Apple rename.
    XCTAssertEqual(verdict(settingsWindow(title: "Something New", selected: "General")), .undetermined)
    // A search result selected in the sidebar.
    XCTAssertEqual(verdict(settingsWindow(title: "Full Disk Access", selected: "Full Disk Access")), .undetermined)
    // An ordinary-looking row while a sidebar search is active (a Privacy subpage can share its name).
    XCTAssertEqual(
      verdict(settingsWindow(title: "Accessibility", selected: "Sound", search: "access")), .undetermined)
    // A top-level row the installed extensions do not name.
    XCTAssertEqual(verdict(settingsWindow(title: "Neue Funktion", selected: "Neue Funktion")), .undetermined)
    // No selection, no sidebar, or a sheet over an ordinary pane.
    XCTAssertEqual(verdict(settingsWindow(title: "Sound", selected: nil)), .undetermined)
    XCTAssertEqual(
      verdict(axNode("AXWindow", "Sound", children: [axNode("AXButton", "Done", actions: ["AXPress"])])), .undetermined)
    XCTAssertEqual(verdict(settingsWindow(title: "Sound", selected: "Sound", sheet: true)), .undetermined)
    XCTAssertEqual(SettingsPaneGuard.Verdict.undetermined.failure?.reason, "refused_settings_pane_unknown")
  }

  func testTheWalkerChecksEverySettingsWindowBeforeReadingAnything() throws {
    var request = WindowSnapshotRequest()
    request.paneGuard = paneGuard
    let readable = FixtureAccessibilitySource(windows: [settingsWindow(title: "Sound", selected: "Sound")])
    XCTAssertNoThrow(try WindowSnapshotWalker(fixture: readable).snapshot(request).get())

    let recorder = FixtureAXRecorder()
    let sensitive = FixtureAccessibilitySource(
      windows: [settingsWindow(title: "Users & Groups", selected: "General")], recorder: recorder)
    guard case .failure(let refused) = WindowSnapshotWalker(fixture: sensitive).snapshot(request) else {
      return XCTFail("a sensitive pane was read")
    }
    XCTAssertEqual(refused.reason, "refused_settings_pane")
    XCTAssertFalse(recorder.attributeReads.contains { $0.names.contains(AXName.numberOfCharacters) }, "it walked")

    // The window asked for is fine, but a second Settings window cannot be identified.
    let twoWindows = FixtureAccessibilitySource(
      windows: [settingsWindow(title: "Sound", selected: "Sound"), axNode("AXWindow", "Untitled")])
    guard case .failure(let unknown) = WindowSnapshotWalker(fixture: twoWindows).snapshot(request) else {
      return XCTFail("an unidentified second Settings window was ignored")
    }
    XCTAssertEqual(unknown.reason, "refused_settings_pane_unknown")
  }

  func testTheCatalogReadsDisplayNamesAndTableStringsFromTheExtensions() throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent("settings-ext-\(UUID().uuidString)")
    defer { try? FileManager.default.removeItem(at: root) }
    let contents = root.appendingPathComponent("GeneralSettings.appex/Contents")
    try FileManager.default.createDirectory(
      at: contents.appendingPathComponent("Resources/fi.lproj"), withIntermediateDirectories: true)
    try
      ([
        "CFBundleIdentifier": Self.general, "CFBundleDisplayName": "General",
        "EXAppExtensionAttributes": ["EXExtensionPointIdentifier": "com.apple.Settings.extension.ui"],
      ] as NSDictionary).write(to: contents.appendingPathComponent("Info.plist"))
    try (["de": ["CFBundleDisplayName": "Allgemein"]] as NSDictionary)
      .write(to: contents.appendingPathComponent("Resources/InfoPlist.loctable"))
    try
      ([
        "de": ["Login Items & Extensions": "Anmeldeobjekte & Erweiterungen", "Sharing": "Teilen"],
        "fr": ["Login Items & Extensions": "Ouverture et extensions"],
      ] as NSDictionary).write(to: contents.appendingPathComponent("Resources/Localizable.loctable"))
    try (["Sharing": "Jakaminen"] as NSDictionary)
      .write(to: contents.appendingPathComponent("Resources/fi.lproj/Localizable.strings"))

    let catalog = SettingsPaneCatalog(directory: root)

    XCTAssertEqual(catalog.settingsPaneExtensionIDs, [Self.general.lowercased()])
    XCTAssertEqual(Set(catalog.displayNames[Self.general.lowercased()] ?? []), ["General", "Allgemein"])
    XCTAssertEqual(
      Set(catalog.strings[Self.key("Login Items & Extensions")] ?? []),
      ["Anmeldeobjekte & Erweiterungen", "Ouverture et extensions"])
    XCTAssertEqual(Set(catalog.strings[Self.key("Sharing")] ?? []), ["Teilen", "Jakaminen"])
  }

  /// Against this Mac's own System Settings extensions, when they are there.
  func testTheInstalledExtensionsNameLocalizedGeneralSubpages() throws {
    let general = URL(fileURLWithPath: "/System/Library/ExtensionKit/Extensions/GeneralSettings.appex")
    guard
      FileManager.default.fileExists(
        atPath: general.appendingPathComponent("Contents/Resources/Localizable.loctable").path)
    else { throw XCTSkip("no General settings string table on this system") }

    let live = SettingsPaneGuard(catalog: .installed)

    XCTAssertEqual(
      live.sensitiveNames[SettingsPaneGuard.normalize("Anmeldeobjekte & Erweiterungen")], "Login Items & Extensions")
    XCTAssertEqual(live.sensitiveNames[SettingsPaneGuard.normalize("Jakaminen")], "Sharing")
    XCTAssertEqual(
      live.sensitiveNames[SettingsPaneGuard.normalize("Ouverture et extensions")], "Login Items & Extensions")
    XCTAssertTrue(live.generalNames.contains(SettingsPaneGuard.normalize("Allgemein")))
    XCTAssertTrue(live.allowedPaneNames.contains(SettingsPaneGuard.normalize("Sound")))
    XCTAssertFalse(live.allowedPaneNames.contains(SettingsPaneGuard.normalize("Privacy & Security")))
  }
}
