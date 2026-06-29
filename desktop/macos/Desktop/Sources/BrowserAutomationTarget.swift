import AppKit
import Foundation

struct BrowserAutomationTarget: Equatable, Hashable, Identifiable, Sendable {
  static let extensionId = "mmlmfjhmonkocbjadbfplnigmagldckm"
  static let chromeWebStoreURL =
    "https://chromewebstore.google.com/detail/playwright-mcp-bridge/\(extensionId)"

  let name: String
  let bundleIdentifier: String
  let appPath: String
  let profileDirectoryRelativePath: String
  let installURL: URL?
  let supportsChromeWebStore: Bool

  var id: String { bundleIdentifier }
  var appURL: URL { URL(fileURLWithPath: appPath) }

  func profileRoot(homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser) -> URL {
    homeDirectory.appendingPathComponent(profileDirectoryRelativePath)
  }

  func extensionStatusURL() -> URL? {
    URL(string: "chrome-extension://\(Self.extensionId)/status.html")
  }

  func extensionInstallURL() -> URL? {
    supportsChromeWebStore ? URL(string: Self.chromeWebStoreURL) : installURL
  }

  func extensionSetupURL() -> URL? {
    extensionInstallURL()
  }
}

enum BrowserAutomationTargetStore {
  private static let selectedBundleIdentifierKey = "playwrightBrowserBundleIdentifier"
  private static let userSelectedBundleIdentifierKey = "playwrightBrowserBundleIdentifierUserSelected"
  private static let extensionTokenKey = "playwrightExtensionToken"

  static var selectedBundleIdentifier: String? {
    get {
      guard UserDefaults.standard.bool(forKey: userSelectedBundleIdentifierKey) else { return nil }
      let value = UserDefaults.standard.string(forKey: selectedBundleIdentifierKey) ?? ""
      return value.isEmpty ? nil : value
    }
    set {
      UserDefaults.standard.set(newValue ?? "", forKey: selectedBundleIdentifierKey)
      UserDefaults.standard.set(newValue != nil, forKey: userSelectedBundleIdentifierKey)
    }
  }

  static func select(_ target: BrowserAutomationTarget) {
    if selectedBundleIdentifier != target.bundleIdentifier {
      UserDefaults.standard.removeObject(forKey: extensionTokenKey)
    }
    selectedBundleIdentifier = target.bundleIdentifier
  }
}

enum BrowserAutomationTargetResolver {
  static let knownTargets: [BrowserAutomationTarget] = [
    BrowserAutomationTarget(
      name: "ChatGPT Atlas",
      bundleIdentifier: "com.openai.atlas",
      appPath: "/Applications/ChatGPT Atlas.app",
      profileDirectoryRelativePath: "Library/Application Support/com.openai.atlas/browser-data/host",
      installURL: URL(string: "https://chatgpt.com/atlas"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Google Chrome",
      bundleIdentifier: "com.google.Chrome",
      appPath: "/Applications/Google Chrome.app",
      profileDirectoryRelativePath: "Library/Application Support/Google/Chrome",
      installURL: URL(string: "https://www.google.com/chrome/"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Google Chrome Beta",
      bundleIdentifier: "com.google.Chrome.beta",
      appPath: "/Applications/Google Chrome Beta.app",
      profileDirectoryRelativePath: "Library/Application Support/Google/Chrome Beta",
      installURL: URL(string: "https://www.google.com/chrome/beta/"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Google Chrome Canary",
      bundleIdentifier: "com.google.Chrome.canary",
      appPath: "/Applications/Google Chrome Canary.app",
      profileDirectoryRelativePath: "Library/Application Support/Google/Chrome Canary",
      installURL: URL(string: "https://www.google.com/chrome/canary/"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Brave Browser",
      bundleIdentifier: "com.brave.Browser",
      appPath: "/Applications/Brave Browser.app",
      profileDirectoryRelativePath: "Library/Application Support/BraveSoftware/Brave-Browser",
      installURL: URL(string: "https://brave.com/download/"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Brave Browser Beta",
      bundleIdentifier: "com.brave.Browser.beta",
      appPath: "/Applications/Brave Browser Beta.app",
      profileDirectoryRelativePath: "Library/Application Support/BraveSoftware/Brave-Browser-Beta",
      installURL: URL(string: "https://brave.com/download-beta/"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Brave Browser Nightly",
      bundleIdentifier: "com.brave.Browser.nightly",
      appPath: "/Applications/Brave Browser Nightly.app",
      profileDirectoryRelativePath: "Library/Application Support/BraveSoftware/Brave-Browser-Nightly",
      installURL: URL(string: "https://brave.com/download-nightly/"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Microsoft Edge",
      bundleIdentifier: "com.microsoft.edgemac",
      appPath: "/Applications/Microsoft Edge.app",
      profileDirectoryRelativePath: "Library/Application Support/Microsoft Edge",
      installURL: URL(string: "https://www.microsoft.com/edge/download"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Microsoft Edge Beta",
      bundleIdentifier: "com.microsoft.edgemac.Beta",
      appPath: "/Applications/Microsoft Edge Beta.app",
      profileDirectoryRelativePath: "Library/Application Support/Microsoft Edge Beta",
      installURL: URL(string: "https://www.microsoft.com/edge/download/insider"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Microsoft Edge Dev",
      bundleIdentifier: "com.microsoft.edgemac.Dev",
      appPath: "/Applications/Microsoft Edge Dev.app",
      profileDirectoryRelativePath: "Library/Application Support/Microsoft Edge Dev",
      installURL: URL(string: "https://www.microsoft.com/edge/download/insider"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Microsoft Edge Canary",
      bundleIdentifier: "com.microsoft.edgemac.Canary",
      appPath: "/Applications/Microsoft Edge Canary.app",
      profileDirectoryRelativePath: "Library/Application Support/Microsoft Edge Canary",
      installURL: URL(string: "https://www.microsoft.com/edge/download/insider"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Arc",
      bundleIdentifier: "company.thebrowser.Browser",
      appPath: "/Applications/Arc.app",
      profileDirectoryRelativePath: "Library/Application Support/Arc/User Data",
      installURL: URL(string: "https://arc.net/"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Opera",
      bundleIdentifier: "com.operasoftware.Opera",
      appPath: "/Applications/Opera.app",
      profileDirectoryRelativePath: "Library/Application Support/com.operasoftware.Opera",
      installURL: URL(string: "https://www.opera.com/download"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Opera GX",
      bundleIdentifier: "com.operasoftware.OperaGX",
      appPath: "/Applications/Opera GX.app",
      profileDirectoryRelativePath: "Library/Application Support/com.operasoftware.OperaGX",
      installURL: URL(string: "https://www.opera.com/gx"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Chromium",
      bundleIdentifier: "org.chromium.Chromium",
      appPath: "/Applications/Chromium.app",
      profileDirectoryRelativePath: "Library/Application Support/Chromium",
      installURL: URL(string: "https://www.chromium.org/getting-involved/download-chromium/"),
      supportsChromeWebStore: true
    ),
    BrowserAutomationTarget(
      name: "Vivaldi",
      bundleIdentifier: "com.vivaldi.Vivaldi",
      appPath: "/Applications/Vivaldi.app",
      profileDirectoryRelativePath: "Library/Application Support/Vivaldi",
      installURL: URL(string: "https://vivaldi.com/download/"),
      supportsChromeWebStore: true
    ),
  ]

  static func installedTargets(
    fileManager: FileManager = .default,
    workspace: NSWorkspace = .shared
  ) -> [BrowserAutomationTarget] {
    knownTargets.filter { target in
      fileManager.fileExists(atPath: target.appPath)
        || workspace.urlForApplication(withBundleIdentifier: target.bundleIdentifier) != nil
    }
  }

  static func target(
    for bundleIdentifier: String?,
    fileManager: FileManager = .default,
    workspace: NSWorkspace = .shared
  ) -> BrowserAutomationTarget? {
    guard let bundleIdentifier else { return nil }
    return installedTargets(fileManager: fileManager, workspace: workspace)
      .first { $0.bundleIdentifier == bundleIdentifier }
  }

  static func defaultTarget(
    for url: URL = URL(string: "https://chatgpt.com/")!,
    fileManager: FileManager = .default,
    workspace: NSWorkspace = .shared
  ) -> BrowserAutomationTarget? {
    guard let appURL = workspace.urlForApplication(toOpen: url) else { return nil }
    let installed = installedTargets(fileManager: fileManager, workspace: workspace)
    return installed.first { $0.appURL.standardizedFileURL == appURL.standardizedFileURL }
      ?? installed.first {
        workspace.urlForApplication(withBundleIdentifier: $0.bundleIdentifier)?
          .standardizedFileURL == appURL.standardizedFileURL
      }
  }

  static func preferredTarget(
    for url: URL = URL(string: "https://chatgpt.com/")!,
    fileManager: FileManager = .default,
    workspace: NSWorkspace = .shared
  ) -> BrowserAutomationTarget? {
    if let selected = target(
      for: BrowserAutomationTargetStore.selectedBundleIdentifier,
      fileManager: fileManager,
      workspace: workspace)
    {
      return selected
    }
    if let target = defaultTarget(for: url, fileManager: fileManager, workspace: workspace) {
      return target
    }
    let installed = installedTargets(fileManager: fileManager, workspace: workspace)
    if let target = installed.first {
      return target
    }
    return knownTargets.first
  }

  static func isInstalled(
    _ target: BrowserAutomationTarget,
    fileManager: FileManager = .default,
    workspace: NSWorkspace = .shared
  ) -> Bool {
    fileManager.fileExists(atPath: target.appPath)
      || workspace.urlForApplication(withBundleIdentifier: target.bundleIdentifier) != nil
  }

  static func isExtensionInstalled(
    in target: BrowserAutomationTarget,
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser,
    fileManager: FileManager = .default
  ) -> Bool {
    let root = target.profileRoot(homeDirectory: homeDirectory)
    guard
      let profiles = try? fileManager.contentsOfDirectory(
        at: root, includingPropertiesForKeys: nil)
    else { return false }

    for profile in profiles {
      let extDir = profile.appendingPathComponent("Extensions/\(BrowserAutomationTarget.extensionId)")
      if fileManager.fileExists(atPath: extDir.path) {
        return true
      }
    }
    return false
  }

  static func open(_ url: URL, in target: BrowserAutomationTarget, workspace: NSWorkspace = .shared) {
    let configuration = NSWorkspace.OpenConfiguration()
    configuration.activates = true

    if let appURL = workspace.urlForApplication(withBundleIdentifier: target.bundleIdentifier) {
      workspace.open([url], withApplicationAt: appURL, configuration: configuration) { _, error in
        if let error {
          log("BrowserAutomationTargetResolver: Failed opening \(url) in \(target.name): \(error)")
          workspace.open(url)
        }
      }
      return
    }

    if FileManager.default.fileExists(atPath: target.appPath) {
      workspace.open([url], withApplicationAt: target.appURL, configuration: configuration) { _, error in
        if let error {
          log("BrowserAutomationTargetResolver: Failed opening \(url) at \(target.appPath): \(error)")
          workspace.open(url)
        }
      }
      return
    }

    workspace.open(url)
  }
}
