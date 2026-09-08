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

  func testBackgroundSafeStorageReadDisallowsInteraction() {
    let backgroundQuery = BrowserKeychainCache.safeStorageQuery(
      service: "Chrome Safe Storage",
      account: "Chrome",
      userInitiated: false
    )
    let userInitiatedQuery = BrowserKeychainCache.safeStorageQuery(
      service: "Chrome Safe Storage",
      account: "Chrome",
      userInitiated: true
    )

    XCTAssertNotNil(backgroundQuery[kSecUseAuthenticationContext as String])
    XCTAssertTrue(
      CFEqual(
        backgroundQuery[kSecUseAuthenticationUI as String] as CFTypeRef,
        kSecUseAuthenticationUISkip
      )
    )
    XCTAssertNil(userInitiatedQuery[kSecUseAuthenticationContext as String])
    XCTAssertNil(userInitiatedQuery[kSecUseAuthenticationUI as String])
  }

  func testSuccessfulSharedSafeStorageGrantIsReadOnceAcrossExplicitGoogleConsumers() {
    // This is the exact shared Chrome Safe Storage identity Calendar and Gmail
    // derive through `BrowserKeychainCache.password(for:account:)`; prefix it
    // only to keep the test isolated from a real user credential.
    let cacheKey = "BrowserGoogleSessionTests.\(UUID().uuidString)\u{0}Chrome Safe Storage\u{0}Chrome"
    var keychainReads = 0

    let calendarPassword = BrowserKeychainCache.shared.password(for: cacheKey, userInitiated: true) {
      keychainReads += 1
      return "granted"
    }
    let gmailPassword = BrowserKeychainCache.shared.password(for: cacheKey, userInitiated: true) {
      keychainReads += 1
      return "granted"
    }

    XCTAssertEqual(calendarPassword, "granted")
    XCTAssertEqual(gmailPassword, "granted")
    // A second loader would be a second Keychain authorization request. Both
    // consumers must reuse the original successful grant and exact secret.
    XCTAssertEqual(keychainReads, 1)
    BrowserKeychainCache.shared.invalidate(cacheKey: cacheKey)
  }

  func testPassiveSafeStorageReadCannotReuseExplicitGrant() {
    let cacheKey = "BrowserGoogleSessionTests.passive.\(UUID().uuidString)"
    var passiveLoaderCalled = false

    BrowserKeychainCache.shared.beginUserInitiatedOperation()
    XCTAssertEqual(
      BrowserKeychainCache.shared.password(for: cacheKey, userInitiated: true) { "granted" },
      "granted"
    )

    XCTAssertNil(
      BrowserKeychainCache.shared.password(for: cacheKey) {
        passiveLoaderCalled = true
        return "should-not-be-read"
      })
    XCTAssertFalse(passiveLoaderCalled)
    BrowserKeychainCache.shared.invalidate(cacheKey: cacheKey)
  }

  func testDeniedSafeStorageReadIsScopedToOneExplicitOperation() {
    let cacheKey = "BrowserGoogleSessionTests.denied.\(UUID().uuidString)"
    var keychainReads = 0

    BrowserKeychainCache.shared.beginUserInitiatedOperation()
    XCTAssertNil(
      BrowserKeychainCache.shared.password(for: cacheKey, userInitiated: true) {
        keychainReads += 1
        return nil
      })
    XCTAssertNil(
      BrowserKeychainCache.shared.password(for: cacheKey, userInitiated: true) {
        keychainReads += 1
        return nil
      })
    XCTAssertEqual(keychainReads, 1)

    BrowserKeychainCache.shared.beginUserInitiatedOperation()
    XCTAssertNil(
      BrowserKeychainCache.shared.password(for: cacheKey, userInitiated: true) {
        keychainReads += 1
        return nil
      })
    XCTAssertEqual(keychainReads, 2)
    BrowserKeychainCache.shared.invalidate(cacheKey: cacheKey)
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

  func testRequestCookieValueUsesOnlyCookiesApplicableToTheTargetHost() throws {
    let script =
      BrowserGoogleSession.chromiumCookiePythonSupport + """

        cookies = [
            {
                'domain': 'accounts.google.com',
                'name': 'SAPISID',
                'value': 'wrong-host-cookie',
                'path': '/',
                'secure': True,
            },
            {
                'domain': '.google.com',
                'name': 'SAPISID',
                'value': 'calendar-cookie',
                'path': '/',
                'secure': True,
            },
        ]
        jar = make_cookie_jar(cookies)
        value = cookie_value_for_request(
            jar,
            'https://clients6.google.com/calendar/v3/calendars/primary/events',
            ('SAPISID', '__Secure-3PAPISID'),
        )
        assert value == 'calendar-cookie', value
        """

    let result = try BrowserPythonRunner.run(script: script, arguments: [])
    XCTAssertEqual(
      result.terminationStatus,
      0,
      String(data: result.stderr, encoding: .utf8) ?? "Python cookie selection check failed"
    )
  }
}
