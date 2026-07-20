import GRDB
import XCTest

@testable import Omi_Computer

final class BrowserGoogleSessionTests: XCTestCase {
  private var tempRoot: URL!

  override func setUpWithError() throws {
    try super.setUpWithError()
    tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("browser-google-session-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
  }

  override func tearDownWithError() throws {
    if let tempRoot {
      try? FileManager.default.removeItem(at: tempRoot)
    }
    try super.tearDownWithError()
  }

  func testCookiePathsPreferChromiumNetworkCookieStore() throws {
    let defaultProfile = tempRoot.appendingPathComponent("Default", isDirectory: true)
    let networkDir = defaultProfile.appendingPathComponent("Network", isDirectory: true)
    try FileManager.default.createDirectory(at: networkDir, withIntermediateDirectories: true)
    try Data().write(to: defaultProfile.appendingPathComponent("Cookies"))
    try Data().write(to: networkDir.appendingPathComponent("Cookies"))

    let profile2 = tempRoot.appendingPathComponent("Profile 2", isDirectory: true)
    try FileManager.default.createDirectory(at: profile2, withIntermediateDirectories: true)
    try Data().write(to: profile2.appendingPathComponent("Cookies"))

    XCTAssertEqual(
      BrowserGoogleSession.cookiePaths(in: tempRoot.path),
      [
        networkDir.appendingPathComponent("Cookies").path,
        profile2.appendingPathComponent("Cookies").path,
      ])
  }

  func testConfigsPrioritizeRecentProfilesAndFallbackToNewestStaleSession() throws {
    let now = Date(timeIntervalSince1970: 1_784_563_200)
    let chrome = try target("com.google.Chrome")
    let chromeRoot = chrome.profileRoot(homeDirectory: tempRoot)
    let chromeDefault = try makeCookieDatabase(
      in: chromeRoot, profile: "Default", host: ".google.com", name: "SID")
    let chromeMain = try makeCookieDatabase(
      in: chromeRoot, profile: "Profile 2", host: ".google.com", name: "SID")
    try writeLocalState(
      to: chromeRoot,
      profile: [
        "last_used": "Profile 2",
        "info_cache": [
          "Default": [
            "active_time": now.addingTimeInterval(-120).timeIntervalSince1970,
            "gaia_id": "default-account",
          ],
          "Profile 2": [
            "active_time": (now.timeIntervalSince1970 + 11_644_473_600) * 1_000_000,
            "gaia_id": "main-account",
          ],
        ],
      ])

    let brave = try target("com.brave.Browser")
    let braveRoot = brave.profileRoot(homeDirectory: tempRoot)
    _ = try makeCookieDatabase(in: braveRoot, profile: "Default", host: ".example.com", name: "SID")
    try writeLocalState(
      to: braveRoot,
      profile: [
        "last_active_profiles": ["Default"],
        "info_cache": ["Default": ["active_time": now.timeIntervalSince1970]],
      ])

    let arc = try target("company.thebrowser.Browser")
    let arcRoot = arc.profileRoot(homeDirectory: tempRoot)
    _ = try makeCookieDatabase(in: arcRoot, profile: "Default", host: ".google.com", name: "SID")
    try writeLocalState(
      to: arcRoot,
      profile: [
        "info_cache": ["Default": ["active_time": now.addingTimeInterval(-31 * 86_400).timeIntervalSince1970]]
      ])

    let vivaldi = try target("com.vivaldi.Vivaldi")
    let vivaldiRoot = vivaldi.profileRoot(homeDirectory: tempRoot)
    let vivaldiCookie = try makeCookieDatabase(
      in: vivaldiRoot, profile: "Default", host: "mail.gmail.com", name: "__Secure-1PSID")
    try FileManager.default.setAttributes(
      [.modificationDate: now.addingTimeInterval(-60)], ofItemAtPath: vivaldiCookie.path)
    try FileManager.default.createSymbolicLink(
      atPath: vivaldiRoot.appendingPathComponent("SingletonLock").path,
      withDestinationPath: "host-1234")

    var keychainReads: [String] = []
    let configs = BrowserGoogleSession.configsForPython(
      logPrefix: "test",
      targets: [chrome, brave, arc, vivaldi],
      homeDirectory: tempRoot,
      now: now
    ) { service, _ in
      keychainReads.append(service)
      return "password"
    }

    XCTAssertEqual(
      keychainReads,
      ["Vivaldi Safe Storage", "Chrome Safe Storage", "Chrome Safe Storage"])
    XCTAssertEqual(
      configs.map { $0["db_path"] },
      [vivaldiCookie.path, chromeMain.path, chromeDefault.path])

    let fallbackConfigs = BrowserGoogleSession.configsForPython(
      logPrefix: "test",
      targets: [chrome, brave, arc, vivaldi],
      homeDirectory: tempRoot,
      now: now.addingTimeInterval(31 * 86_400)
    ) { _, _ in "password" }
    XCTAssertEqual(fallbackConfigs.map { $0["db_path"] }, [chromeMain.path])
  }

  func testSafeStorageIdentitiesMatchBrowserItems() throws {
    let expected: [String: (service: String, account: String)] = [
      "com.openai.atlas": ("Chrome Safe Storage", "Chrome"),
      "com.google.Chrome": ("Chrome Safe Storage", "Chrome"),
      "com.google.Chrome.beta": ("Chrome Safe Storage", "Chrome"),
      "com.google.Chrome.canary": ("Chrome Safe Storage", "Chrome"),
      "com.brave.Browser": ("Brave Safe Storage", "Brave"),
      "com.brave.Browser.beta": ("Brave Safe Storage", "Brave"),
      "com.brave.Browser.nightly": ("Brave Safe Storage", "Brave"),
      "com.microsoft.edgemac": ("Microsoft Edge Safe Storage", "Microsoft Edge"),
      "com.microsoft.edgemac.Beta": ("Microsoft Edge Safe Storage", "Microsoft Edge"),
      "com.microsoft.edgemac.Dev": ("Microsoft Edge Safe Storage", "Microsoft Edge"),
      "com.microsoft.edgemac.Canary": ("Microsoft Edge Safe Storage", "Microsoft Edge"),
      "company.thebrowser.Browser": ("Arc Safe Storage", "Arc"),
      "com.operasoftware.Opera": ("Opera Safe Storage", "Opera"),
      "com.operasoftware.OperaGX": ("Opera Safe Storage", "Opera"),
      "org.chromium.Chromium": ("Chromium Safe Storage", "Chromium"),
      "com.vivaldi.Vivaldi": ("Vivaldi Safe Storage", "Vivaldi"),
    ]

    for target in BrowserAutomationTargetResolver.knownTargets {
      let expectedIdentity = try XCTUnwrap(expected[target.bundleIdentifier])
      let actual = try XCTUnwrap(BrowserGoogleSession.keychainIdentity(for: target))
      XCTAssertEqual(actual.service, expectedIdentity.service, target.bundleIdentifier)
      XCTAssertEqual(actual.account, expectedIdentity.account, target.bundleIdentifier)
    }
  }

  func testSafeStorageQueryMatchesTheFullGenericPasswordIdentity() {
    let query = BrowserKeychainCache.safeStorageQuery(
      service: "Chrome Safe Storage",
      account: "Chrome"
    )

    XCTAssertEqual(query[kSecAttrService as String] as? String, "Chrome Safe Storage")
    XCTAssertEqual(query[kSecAttrAccount as String] as? String, "Chrome")
    XCTAssertEqual(query[kSecReturnData as String] as? Bool, true)
  }

  func testUnknownVersionCookieBlobIsSkippedInsteadOfEmittedAsPlaintext() throws {
    let databasePath = tempRoot.appendingPathComponent("Cookies").path
    let script =
      BrowserGoogleSession.chromiumCookiePythonSupport + """

        db_path = sys.argv[1]
        conn = sqlite3.connect(db_path)
        conn.execute('CREATE TABLE meta (key TEXT, value TEXT)')
        conn.execute('INSERT INTO meta VALUES ("version", "24")')
        conn.execute('''CREATE TABLE cookies (
            host_key TEXT, name TEXT, encrypted_value BLOB, path TEXT,
            is_secure INTEGER, expires_utc INTEGER
        )''')
        conn.execute(
            'INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?)',
            ('.google.com', 'VERSIONED', sqlite3.Binary(b'v20ciphertext'), '/', 1, 0)
        )
        conn.execute(
            'INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?)',
            ('.google.com', 'PLAINTEXT', sqlite3.Binary(b'plain-cookie'), '/', 1, 0)
        )
        conn.commit()
        conn.close()

        cookies, error = decrypt_google_cookies(db_path, 'unused')
        assert error is None, error
        assert [cookie['name'] for cookie in cookies] == ['PLAINTEXT'], cookies
        """

    let result = try BrowserPythonRunner.run(script: script, arguments: [databasePath])
    XCTAssertEqual(
      result.terminationStatus,
      0,
      String(data: result.stderr, encoding: .utf8) ?? "Python cookie check failed"
    )
  }

  private func target(_ bundleIdentifier: String) throws -> BrowserAutomationTarget {
    try XCTUnwrap(
      BrowserAutomationTargetResolver.knownTargets.first { $0.bundleIdentifier == bundleIdentifier })
  }

  private func writeLocalState(to root: URL, profile: [String: Any]) throws {
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    let data = try JSONSerialization.data(withJSONObject: ["profile": profile])
    try data.write(to: root.appendingPathComponent("Local State"))
  }

  private func makeCookieDatabase(
    in root: URL,
    profile: String,
    host: String,
    name: String
  ) throws -> URL {
    let network = root.appendingPathComponent(profile).appendingPathComponent("Network")
    try FileManager.default.createDirectory(at: network, withIntermediateDirectories: true)
    let url = network.appendingPathComponent("Cookies")
    let database = try DatabaseQueue(path: url.path)
    try database.write { db in
      try db.create(table: "cookies") { table in
        table.column("host_key", .text).notNull()
        table.column("name", .text).notNull()
      }
      try db.execute(sql: "INSERT INTO cookies (host_key, name) VALUES (?, ?)", arguments: [host, name])
    }
    return url
  }
}
