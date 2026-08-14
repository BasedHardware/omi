import AppKit
import ApplicationServices
import Foundation

enum WorkHistoryHandleExtractor {
  private static let browserApps: Set<String> = [
    "Google Chrome",
    "Arc",
    "Safari",
    "Firefox",
    "Microsoft Edge",
    "Brave Browser",
    "Opera",
    "Chromium",
    "Vivaldi",
    "Orion",
    "Dia",
    "Comet",
  ]

  static func handles(from snapshot: WorkHistoryFrontmostSnapshot) -> [WorkHistoryHandle] {
    var result: [WorkHistoryHandle] = []
    if isBrowser(snapshot),
      let url = httpURL(from: snapshot.documentURL) ?? snapshot.browserURL,
      let handle = WorkHistoryHandle.url(url.absoluteString)
    {
      result.append(handle)
    } else if let fileHandle = fileHandle(from: snapshot.documentURL) {
      result.append(fileHandle)
    } else if let url = snapshot.browserURL, let handle = WorkHistoryHandle.url(url.absoluteString) {
      result.append(handle)
    }

    if let windowHandle = WorkHistoryHandle.appWindow(
      appName: snapshot.appName,
      title: ContextTitleNormalizer.normalize(snapshot.windowTitle, appName: snapshot.appName)
        ?? snapshot.windowTitle ?? "")
    {
      result.append(windowHandle)
    }
    return uniqued(result)
  }

  static func liveSnapshot(appName: String, windowTitle: String?, expectedBundleID: String? = nil)
    -> WorkHistoryFrontmostSnapshot
  {
    var snapshot = WorkHistoryFrontmostSnapshot(
      appName: appName,
      windowTitle: windowTitle,
      bundleID: expectedBundleID ?? NSWorkspace.shared.frontmostApplication?.bundleIdentifier
    )
    guard AXIsProcessTrusted() else { return snapshot }
    guard let front = NSWorkspace.shared.frontmostApplication else { return snapshot }
    let nameMatches = front.localizedName == appName
    let bundleMatches = expectedBundleID.map { $0 == front.bundleIdentifier } ?? false
    guard nameMatches || bundleMatches else { return snapshot }
    snapshot.bundleID = front.bundleIdentifier
    let app = AXUIElementCreateApplication(front.processIdentifier)
    guard let window = copyElement(app, attribute: kAXFocusedWindowAttribute) else { return snapshot }

    if let document = copyString(window, attribute: kAXDocumentAttribute) {
      snapshot.documentURL = URL(string: document) ?? URL(fileURLWithPath: document)
    }
    if httpURL(from: snapshot.documentURL) == nil, let url = firstURL(in: window, remaining: 24) {
      snapshot.browserURL = url
    }
    return snapshot
  }

  static func isBrowser(_ snapshot: WorkHistoryFrontmostSnapshot) -> Bool {
    isBrowser(appName: snapshot.appName, bundleID: snapshot.bundleID)
  }

  static func isBrowser(appName: String, bundleID: String? = nil) -> Bool {
    if browserApps.contains(appName) { return true }
    guard let bundleID else { return false }
    return browserBundles.contains(bundleID)
  }

  private static let browserBundles: Set<String> = [
    "com.google.Chrome",
    "com.google.Chrome.canary",
    "company.thebrowser.Browser",
    "com.apple.Safari",
    "org.mozilla.firefox",
    "com.microsoft.edgemac",
    "com.brave.Browser",
    "com.operasoftware.Opera",
    "org.chromium.Chromium",
    "com.vivaldi.Vivaldi",
    "com.kagi.kagimacOS",
  ]

  private static func fileHandle(from url: URL?) -> WorkHistoryHandle? {
    guard let url else { return nil }
    if url.isFileURL {
      return WorkHistoryHandle.file(url.path)
    }
    if url.scheme == nil {
      return WorkHistoryHandle.file(url.path)
    }
    return nil
  }

  private static func httpURL(from url: URL?) -> URL? {
    guard let url, let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https" else {
      return nil
    }
    return url
  }

  private static func uniqued(_ handles: [WorkHistoryHandle]) -> [WorkHistoryHandle] {
    var seen = Set<WorkHistoryHandle>()
    return handles.filter { seen.insert($0).inserted }
  }

  private static func copyElement(_ element: AXUIElement, attribute: String) -> AXUIElement? {
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success,
      let value,
      CFGetTypeID(value) == AXUIElementGetTypeID()
    else { return nil }
    return unsafeDowncast(value, to: AXUIElement.self)
  }

  private static func copyString(_ element: AXUIElement, attribute: String) -> String? {
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, attribute as CFString, &value) == .success else { return nil }
    if let string = value as? String { return string }
    if let url = value as? URL { return url.absoluteString }
    return nil
  }

  private static func firstURL(in element: AXUIElement, remaining: Int) -> URL? {
    guard remaining > 0 else { return nil }
    if let raw = copyString(element, attribute: "AXURL"),
      let url = URL(string: raw),
      let scheme = url.scheme?.lowercased(),
      scheme == "http" || scheme == "https"
    {
      return url
    }
    var children: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, kAXChildrenAttribute as CFString, &children) == .success,
      let list = children as? [AXUIElement]
    else { return nil }
    var budget = remaining - 1
    for child in list.prefix(8) {
      if let url = firstURL(in: child, remaining: budget) { return url }
      budget -= 1
      if budget <= 0 { break }
    }
    return nil
  }
}
