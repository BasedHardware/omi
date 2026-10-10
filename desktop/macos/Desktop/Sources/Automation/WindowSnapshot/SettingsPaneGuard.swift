import CoreGraphics
import Foundation

/// Decides, before anything is read, whether the open System Settings pane may
/// be read at all. It is an allow-list: a pane is read only when it is
/// positively identified as an ordinary one.
///
/// The open pane is told by the selected row of the window's sidebar and by
/// the window title. A sensitive name in either refuses. Otherwise the sidebar
/// selection must name an ordinary top-level pane, in any language the
/// installed System Settings extensions ship; a search result, a row it does
/// not know, no selection, an active sidebar search (whose results can name
/// a Privacy subpage after an ordinary pane), or a sheet over the window is
/// refused. General
/// hosts sensitive subpages (Sharing, Login Items, AutoFill & Passwords), so
/// with General selected the window title must also be one of General's
/// ordinary subpages. A window titled with a page of Privacy & Security
/// (Full Disk Access, Location Services and the rest) is refused unless the
/// sidebar selects that same name, since a link or history can open such a
/// page while the sidebar stays on an ordinary pane. A sidebar it cannot
/// place on screen is refused too, so a content table cannot pose as it. It
/// runs on every read and for every Settings window,
/// because the person can switch panes after approving System Settings.
///
/// Window and sidebar text is the other app's content. It is compared against
/// the fixed lists and never decides anything beyond that comparison.
struct SettingsPaneGuard: Equatable, Sendable {
  typealias Floor = GeneratedUIAutomationSafetyFloor

  enum Verdict: Equatable, Sendable {
    case allowed
    case sensitive(pane: String)
    case undetermined

    var failure: WindowSnapshotFailure? {
      switch self {
      case .allowed:
        return nil
      case .sensitive(let pane):
        return WindowSnapshotFailure(
          reason: "refused_settings_pane",
          message: "Omi never reads the \(pane) settings. Other System Settings panes can be read.")
      case .undetermined:
        return WindowSnapshotFailure(
          reason: "refused_settings_pane_unknown",
          message: "Omi could not identify the open System Settings pane, so it did not read it.")
      }
    }
  }

  /// Normalized sensitive name → the pane's English name, for the refusal message.
  let sensitiveNames: [String: String]
  /// Ordinary top-level panes, as the sidebar names them.
  let allowedPaneNames: Set<String>
  /// The General pane, as the sidebar names it.
  let generalNames: Set<String>
  /// Ordinary subpages of General, as the window title names them.
  let generalSubpageNames: Set<String>
  /// Pages inside Privacy & Security, as the window title names them.
  let privacySubpageNames: Set<String>

  init(catalog: SettingsPaneCatalog) {
    var sensitive: [String: String] = [:]
    for pane in Floor.sensitiveSettingsPanes {
      let displayName = pane.names.titles.first ?? pane.name
      for name in catalog.names(pane.names) {
        let key = Self.normalize(name)
        if !key.isEmpty, sensitive[key] == nil { sensitive[key] = displayName }
      }
    }
    let sensitiveExtensions = Set(
      Floor.sensitiveSettingsPanes.flatMap(\.names.extensionBundleIDs).map { $0.lowercased() })
    let general = Floor.generalExtensionBundleID.lowercased()
    var allowed = catalog.names(Floor.allowedSettingsPanes)
    for id in catalog.settingsPaneExtensionIDs where !sensitiveExtensions.contains(id) && id != general {
      allowed += catalog.displayNames[id] ?? []
    }
    let generalNames =
      ["General"] + (catalog.displayNames[general] ?? [])
      + catalog.tableStrings(.init(extensionBundleID: general, table: "Localizable", keys: ["General"]))
    let keep: (String) -> Bool = { !$0.isEmpty && sensitive[$0] == nil }
    let generalSet = Set(generalNames.map(Self.normalize).filter(keep))
    sensitiveNames = sensitive
    self.generalNames = generalSet
    allowedPaneNames = Set(allowed.map(Self.normalize).filter(keep)).subtracting(generalSet)
    generalSubpageNames = Set(catalog.names(Floor.generalAllowedSubpages).map(Self.normalize).filter(keep))
    privacySubpageNames = Set(catalog.names(Floor.privacySubpages).map(Self.normalize).filter { !$0.isEmpty })
  }

  /// The floor's panes, named in every language the installed extensions
  /// ship. Built once per process.
  static let live = SettingsPaneGuard(catalog: .installed)

  /// Case-folded, compatibility-normalized, with every dash shape made `-`
  /// and whitespace collapsed: the Wi-Fi pane spells itself with U+2011 and
  /// some languages put a no-break space inside a name.
  static func normalize(_ title: String) -> String {
    let folded = WindowSnapshotText.sanitize(title.precomposedStringWithCompatibilityMapping).lowercased()
    let dashes: Set<UInt32> = [0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212, 0xFE63, 0xFF0D]
    let scalars = folded.unicodeScalars.map { dashes.contains($0.value) ? "-" : $0 }
    return String(String.UnicodeScalarView(scalars)).trimmingCharacters(in: .whitespaces)
  }

  func evaluate<Source: AccessibilityElementSource>(
    window: Source.Element, title: String, source: Source, isExpired: () -> Bool = { false }
  ) -> Verdict {
    let normalizedTitle = Self.normalize(title)
    if let pane = sensitiveNames[normalizedTitle] { return .sensitive(pane: pane) }
    guard let probe = try? probeSidebar(in: window, source: source, isExpired: isExpired), !probe.hasSheet,
      !probe.isSearching, !probe.hasUnplacedList, !probe.selectedTexts.isEmpty
    else { return .undetermined }
    let selected = probe.selectedTexts.map(Self.normalize)
    for text in selected {
      if let pane = sensitiveNames[text] { return .sensitive(pane: pane) }
    }
    if privacySubpageNames.contains(normalizedTitle), !selected.contains(normalizedTitle) {
      return .sensitive(pane: "Privacy & Security")
    }
    if selected.contains(where: generalNames.contains) {
      return generalSubpageNames.contains(normalizedTitle) ? .allowed : .undetermined
    }
    return selected.contains(where: allowedPaneNames.contains) ? .allowed : .undetermined
  }

  // MARK: - Reading the sidebar

  private struct SidebarProbe {
    var hasSheet = false
    var isSearching = false
    /// A list in the window has no position, so the sidebar cannot be told apart.
    var hasUnplacedList = false
    var selectedTexts: [String] = []
  }

  private struct Expired: Error {}

  private static let listRoles: Set<String> = ["AXOutline", "AXTable", "AXList"]

  /// The texts of the selected row of the leftmost list in the window: the
  /// sidebar. Bounded in elements and time so a large pane cannot make the
  /// check expensive.
  private func probeSidebar<Source: AccessibilityElementSource>(
    in window: Source.Element, source: Source, isExpired: () -> Bool
  ) throws -> SidebarProbe {
    var probe = SidebarProbe()
    var queue: [(element: Source.Element, depth: Int)] = [(window, 0)]
    var index = 0
    var sidebar: (element: Source.Element, x: CGFloat)?
    while index < queue.count, index < 400 {
      if isExpired() { throw Expired() }
      let (element, depth) = queue[index]
      index += 1
      if depth > 0 {
        let attributes = try source.attributes([AXName.role, AXName.subrole, AXName.position], of: element)
        let role = attributes[AXName.role]?.string
        if depth == 1, role == "AXSheet" {
          probe.hasSheet = true
          return probe
        }
        if role == "AXSearchField" || attributes[AXName.subrole]?.string == "AXSearchField" {
          let query = try source.attributes([AXName.value], of: element)[AXName.value]?.string ?? ""
          if !WindowSnapshotText.sanitize(query).isEmpty {
            probe.isSearching = true
            return probe
          }
          continue
        }
        if let role, Self.listRoles.contains(role) {
          guard case .point(let origin)? = attributes[AXName.position] else {
            probe.hasUnplacedList = true
            return probe
          }
          if origin.x < (sidebar?.x ?? .infinity) { sidebar = (element, origin.x) }
          continue
        }
      }
      guard depth < 8 else { continue }
      for child in try source.children(of: element, preferVisible: false, head: 50, tail: 0).elements {
        queue.append((child.element, depth + 1))
      }
    }
    guard let sidebar else { return probe }
    for row in try source.selectedRows(of: sidebar.element).prefix(3) {
      var rowQueue: [(element: Source.Element, depth: Int)] = [(row, 0)]
      var rowIndex = 0
      while rowIndex < rowQueue.count, rowIndex < 30 {
        if isExpired() { throw Expired() }
        let (element, depth) = rowQueue[rowIndex]
        rowIndex += 1
        let attributes = try source.attributes([AXName.title, AXName.description, AXName.value], of: element)
        for name in [AXName.title, AXName.description, AXName.value] {
          if let text = attributes[name]?.string.map(WindowSnapshotText.sanitize), !text.isEmpty {
            probe.selectedTexts.append(text)
          }
        }
        guard depth < 4 else { continue }
        for child in try source.children(of: element, preferVisible: false, head: 10, tail: 0).elements {
          rowQueue.append((child.element, depth + 1))
        }
      }
    }
    return probe
  }
}
