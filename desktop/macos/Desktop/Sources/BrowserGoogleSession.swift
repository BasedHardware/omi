import Darwin
import Foundation
import GRDB
import Security

struct BrowserGoogleSession: Equatable {
  let browserName: String
  let keychainService: String
  let keychainAccount: String
  let cookiePath: String

  private static let recentBrowserMaxAge: TimeInterval = 30 * 24 * 60 * 60

  static let chromiumCookiePythonSupport = """
    import sys, json, os, sqlite3, hashlib, time
    from http.cookiejar import MozillaCookieJar, Cookie

    try:
        from Crypto.Cipher import AES
    except ImportError:
        try:
            from Cryptodome.Cipher import AES
        except ImportError:
            import subprocess
            def decrypt_aes_cbc(key, iv, data):
                p = subprocess.run(['openssl', 'enc', '-aes-128-cbc', '-d', '-K', key.hex(), '-iv', iv.hex(), '-nopad'],
                                   input=data, capture_output=True)
                return p.stdout
            USE_OPENSSL = True
        else:
            USE_OPENSSL = False
    else:
        USE_OPENSSL = False

    GOOGLE_AUTH_COOKIE_NAMES = {'SID', 'HSID', 'SSID', 'APISID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID'}

    def decrypt_google_cookies(db_path, password, include_gmail_hosts=False):
        key = hashlib.pbkdf2_hmac('sha1', password.encode('utf-8'), b'saltysalt', 1003, dklen=16)
        iv = b' ' * 16
        try:
            conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, timeout=5)
            c = conn.cursor()
            c.execute('SELECT value FROM meta WHERE key="version"')
            row = c.fetchone()
            db_version = int(row[0]) if row else 0
            host_filter = "host_key LIKE '%google.com%' OR host_key LIKE '%gmail.com%'" if include_gmail_hosts else "host_key LIKE '%google.com%'"
            c.execute(f"SELECT host_key, name, encrypted_value, path, is_secure, expires_utc FROM cookies WHERE {host_filter}")
            rows = c.fetchall()
            conn.close()
        except Exception as e:
            return None, str(e)

        cookies = []
        for host_key, name, enc, path, is_secure, expires_utc in rows:
            if not enc:
                continue
            enc = bytes(enc) if not isinstance(enc, bytes) else enc
            value = None
            # Cookie values are octet strings and are sent back verbatim in the
            # Latin-1 HTTP Cookie header. Decode them as Latin-1 (a 1:1 byte<->char
            # map, so value.encode('latin-1') reproduces the exact bytes). Using
            # utf-8 with errors='replace' corrupted non-utf-8 values into U+FFFD,
            # which then failed to encode into the Latin-1 request header.
            if enc[:3] in (b'v10', b'v11'):
                ciphertext = enc[3:]
                try:
                    if USE_OPENSSL:
                        decrypted = decrypt_aes_cbc(key, iv, ciphertext)
                    else:
                        cipher = AES.new(key, AES.MODE_CBC, IV=iv)
                        decrypted = cipher.decrypt(ciphertext)
                    pad_len = decrypted[-1] if decrypted else 0
                    if 1 <= pad_len <= 16:
                        decrypted = decrypted[:-pad_len]
                    if db_version >= 24 and len(decrypted) > 32:
                        decrypted = decrypted[32:]
                    value = decrypted.decode('latin-1')
                except Exception:
                    continue
            elif enc[:1] == b'v' and enc[1:3].isdigit():
                # Versioned but not v10/v11 (e.g. v20 app-bound, or a newer macOS
                # scheme whose key lives in iCloud Keychain). We can't decrypt it, so
                # skip it — never fall through to the plaintext branch below, which
                # would emit the raw ciphertext as a garbage "cookie" value.
                # ponytail: deliberately no v20/app-bound decoder (YAGNI on macOS
                # today). Ceiling: these browsers silently contribute no cookies;
                # upgrade path is Google OAuth, not a per-version scraper.
                continue
            elif enc:
                try:
                    value = enc.decode('latin-1')
                except Exception:
                    continue
            if value:
                cookies.append({
                    'domain': host_key,
                    'name': name,
                    'value': value,
                    'path': path or '/',
                    'secure': bool(is_secure),
                })
        return cookies, None

    def make_cookie_jar(cookie_list):
        jar = MozillaCookieJar()
        for c in cookie_list:
            cookie = Cookie(
                version=0, name=c['name'], value=c['value'],
                port=None, port_specified=False,
                domain=c['domain'], domain_specified=True,
                domain_initial_dot=c['domain'].startswith('.'),
                path=c['path'], path_specified=True,
                secure=c['secure'], expires=int(time.time()) + 86400,
                discard=False, comment=None, comment_url=None,
                rest={}, rfc2109=False
            )
            jar.set_cookie(cookie)
        return jar

    def write_json_result(prefix, payload):
        import tempfile
        fd, outfile = tempfile.mkstemp(suffix='.json', prefix=prefix)
        with os.fdopen(fd, 'w') as f:
            json.dump(payload, f)
        print(outfile)
    """

  private static func recent(
    targets: [BrowserAutomationTarget] = BrowserAutomationTargetResolver.installedTargets(),
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser,
    now: Date = Date(),
    maxAge: TimeInterval = recentBrowserMaxAge
  ) -> [BrowserGoogleSession] {
    return targets.flatMap { target in
      guard let keychainIdentity = keychainIdentity(for: target) else {
        return [BrowserGoogleSession]()
      }
      let userDataRoot = target.profileRoot(homeDirectory: homeDirectory)
      guard
        let profile = mainProfile(in: userDataRoot, now: now),
        browserIsRunning(at: userDataRoot)
          || profile.activity >= now.addingTimeInterval(-maxAge),
        profile.hasGoogleAccount || hasGoogleAuthCookie(at: profile.cookieURL)
      else { return [] }

      let browserName = profile.name == "Default" ? target.name : "\(target.name) (\(profile.name))"
      return [
        BrowserGoogleSession(
          browserName: browserName,
          keychainService: keychainIdentity.service,
          keychainAccount: keychainIdentity.account,
          cookiePath: profile.cookieURL.path
        )
      ]
    }
  }

  static func configsForPython(
    logPrefix: String,
    targets: [BrowserAutomationTarget] = BrowserAutomationTargetResolver.installedTargets(),
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser,
    now: Date = Date(),
    passwordLoader: (String, String) -> String? = {
      BrowserKeychainCache.shared.password(for: $0, account: $1)
    }
  ) -> [[String: String]] {
    recent(targets: targets, homeDirectory: homeDirectory, now: now).compactMap { session in
      guard
        let password = passwordLoader(session.keychainService, session.keychainAccount)
      else {
        log("\(logPrefix): No keychain password for \(session.browserName)")
        return nil
      }
      return [
        "name": session.browserName,
        "db_path": session.cookiePath,
        "password": password,
      ]
    }
  }

  private static func mainProfile(in userDataRoot: URL, now: Date) -> (
    name: String, cookieURL: URL, activity: Date, hasGoogleAccount: Bool
  )? {
    let localState = localState(in: userDataRoot)
    let profileState = localState?["profile"] as? [String: Any]
    let infoCache = profileState?["info_cache"] as? [String: Any] ?? [:]
    let cookieProfiles = cookiePaths(in: userDataRoot.path).compactMap { path -> (String, URL)? in
      let cookieURL = URL(fileURLWithPath: path)
      let profileURL =
        cookieURL.deletingLastPathComponent().lastPathComponent == "Network"
        ? cookieURL.deletingLastPathComponent().deletingLastPathComponent()
        : cookieURL.deletingLastPathComponent()
      return (profileURL.lastPathComponent, cookieURL)
    }
    guard !cookieProfiles.isEmpty else { return nil }

    let preferredNames =
      [profileState?["last_used"] as? String]
      + (profileState?["last_active_profiles"] as? [String] ?? []).map(Optional.some)
    let preferred = preferredNames.compactMap { $0 }.first { name in
      cookieProfiles.contains { $0.0 == name }
    }
    let selected =
      preferred.flatMap { name in cookieProfiles.first { $0.0 == name } }
      ?? cookieProfiles.max { lhs, rhs in
        profileActivity(
          profileName: lhs.0, cookieURL: lhs.1, infoCache: infoCache, now: now)
          < profileActivity(
            profileName: rhs.0, cookieURL: rhs.1, infoCache: infoCache, now: now)
      }
    guard let selected else { return nil }

    let info = infoCache[selected.0] as? [String: Any]
    return (
      selected.0,
      selected.1,
      profileActivity(profileName: selected.0, cookieURL: selected.1, infoCache: infoCache, now: now),
      !(info?["gaia_id"] as? String ?? "").isEmpty
    )
  }

  private static func localState(in userDataRoot: URL) -> [String: Any]? {
    let url = userDataRoot.appendingPathComponent("Local State")
    guard let data = try? Data(contentsOf: url) else { return nil }
    return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
  }

  private static func profileActivity(
    profileName: String,
    cookieURL: URL,
    infoCache: [String: Any],
    now: Date
  ) -> Date {
    if let info = infoCache[profileName] as? [String: Any],
      let activeTime = chromiumDate(info["active_time"], now: now)
    {
      return activeTime
    }
    let historyURL =
      cookieURL.deletingLastPathComponent().lastPathComponent == "Network"
      ? cookieURL.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("History")
      : cookieURL.deletingLastPathComponent().appendingPathComponent("History")
    return [cookieURL, historyURL]
      .compactMap { try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate }
      .max() ?? .distantPast
  }

  private static func chromiumDate(_ value: Any?, now: Date) -> Date? {
    let raw: Double?
    if let number = value as? NSNumber {
      raw = number.doubleValue
    } else if let string = value as? String {
      raw = Double(string)
    } else {
      raw = nil
    }
    guard let raw else { return nil }

    let unixSeconds =
      raw > 1_000_000_000_000
      ? raw / 1_000_000 - 11_644_473_600
      : raw > 10_000_000_000 ? raw - 11_644_473_600 : raw
    let date = Date(timeIntervalSince1970: unixSeconds)
    guard date >= Date(timeIntervalSince1970: 946_684_800),
      date <= now.addingTimeInterval(24 * 60 * 60)
    else { return nil }
    return date
  }

  private static func hasGoogleAuthCookie(at cookieURL: URL) -> Bool {
    var configuration = Configuration()
    configuration.readonly = true
    guard let database = try? DatabaseQueue(path: cookieURL.path, configuration: configuration)
    else { return false }
    return
      (try? database.read { db in
        try Bool.fetchOne(
          db,
          sql: """
            SELECT EXISTS(
              SELECT 1 FROM cookies
              WHERE (host_key LIKE '%google.com%' OR host_key LIKE '%gmail.com%')
                AND name IN ('SID', 'HSID', 'SSID', 'APISID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID')
            )
            """) ?? false
      }) ?? false
  }

  private static func browserIsRunning(at userDataRoot: URL) -> Bool {
    ["SingletonLock", "SingletonSocket", "SingletonCookie"].contains { name in
      (try? FileManager.default.destinationOfSymbolicLink(
        atPath: userDataRoot.appendingPathComponent(name).path)) != nil
    }
  }

  static func cookiePaths(in userDataPath: String) -> [String] {
    let fm = FileManager.default
    guard let entries = try? fm.contentsOfDirectory(atPath: userDataPath) else { return [] }

    return
      entries
      .compactMap { entry -> (name: String, path: String)? in
        var isDirectory: ObjCBool = false
        let profilePath = "\(userDataPath)/\(entry)"
        guard fm.fileExists(atPath: profilePath, isDirectory: &isDirectory), isDirectory.boolValue
        else {
          return nil
        }
        let networkCookies = "\(profilePath)/Network/Cookies"
        if fm.fileExists(atPath: networkCookies) {
          return (entry, networkCookies)
        }
        let legacyCookies = "\(profilePath)/Cookies"
        if fm.fileExists(atPath: legacyCookies) {
          return (entry, legacyCookies)
        }
        return nil
      }
      .sorted { lhs, rhs in
        if lhs.name == "Default" { return true }
        if rhs.name == "Default" { return false }
        let lhsIsProfile = lhs.name.hasPrefix("Profile ")
        let rhsIsProfile = rhs.name.hasPrefix("Profile ")
        if lhsIsProfile != rhsIsProfile { return lhsIsProfile }
        return lhs.name.localizedStandardCompare(rhs.name) == .orderedAscending
      }
      .map(\.path)
      .filter { fm.fileExists(atPath: $0) }
  }

  static func keychainIdentity(for target: BrowserAutomationTarget) -> (
    service: String, account: String
  )? {
    switch target.bundleIdentifier {
    case "company.thebrowser.Browser":
      return ("Arc Safe Storage", "Arc")
    case "com.google.Chrome", "com.google.Chrome.beta", "com.google.Chrome.canary",
      "com.openai.atlas":
      return ("Chrome Safe Storage", "Chrome")
    case "com.brave.Browser", "com.brave.Browser.beta", "com.brave.Browser.nightly":
      return ("Brave Safe Storage", "Brave")
    case "com.microsoft.edgemac", "com.microsoft.edgemac.Beta", "com.microsoft.edgemac.Dev",
      "com.microsoft.edgemac.Canary":
      return ("Microsoft Edge Safe Storage", "Microsoft Edge")
    case "com.operasoftware.Opera", "com.operasoftware.OperaGX":
      return ("Opera Safe Storage", "Opera")
    case "org.chromium.Chromium":
      return ("Chromium Safe Storage", "Chromium")
    case "com.vivaldi.Vivaldi":
      return ("Vivaldi Safe Storage", "Vivaldi")
    default:
      return nil
    }
  }
}

/// Browser Safe Storage strategy for Chromium cookie scraping.
///
/// Primary path: read the browser-created generic-password item in-process via
/// `SecItemCopyMatching`. macOS attributes the keychain prompt to the *requesting
/// process*, so the in-process read shows "<this app> wants to access …" — the app
/// identity the user must recognize before granting — instead of "security wants to
/// access …" (which is what shelling out to `/usr/bin/security` produced).
///
/// A first cross-app read requires user approval. For a stably signed app, choosing
/// "Always Allow" lets macOS add this app's code-signing identity and partition ID to
/// the item's ACL, so later reads can proceed without another prompt. We intentionally
/// do not retry through `/usr/bin/security`: that would attribute any second prompt to
/// the CLI and persist access for the wrong requester.
///
/// The in-memory cache below coalesces concurrent reads within a single app run; we do
/// not duplicate browser Safe Storage secrets into app preferences.
final class BrowserKeychainCache: @unchecked Sendable {
  static let shared = BrowserKeychainCache()

  private enum CacheEntry {
    case found(String)
    case missing
  }

  private var cache: [String: CacheEntry] = [:]
  private var inFlight: [String: DispatchGroup] = [:]
  private let lock = NSLock()

  private init() {
    UserDefaults.standard.removeObject(forKey: "cachedBrowserKeychainPasswords")
  }

  func password(for service: String, account: String) -> String? {
    password(for: "\(service)\u{0}\(account)") {
      Self.nativeSafeStoragePassword(for: service, account: account)
    }
  }

  static func safeStorageQuery(service: String, account: String) -> [String: Any] {
    [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]
  }

  /// Reads the browser Safe Storage key in-process so the prompt and any durable
  /// "Always Allow" grant belong to this app rather than `/usr/bin/security`.
  private static func nativeSafeStoragePassword(for service: String, account: String) -> String? {
    var item: CFTypeRef?
    let status = SecItemCopyMatching(
      safeStorageQuery(service: service, account: account) as CFDictionary,
      &item
    )
    guard status == errSecSuccess,
      let data = item as? Data,
      let password = String(data: data, encoding: .utf8),
      !password.isEmpty
    else {
      return nil
    }
    return password
  }

  func password(for cacheKey: String, loader: () -> String?) -> String? {
    loop: while true {
      lock.lock()

      if let cached = cache[cacheKey] {
        lock.unlock()
        switch cached {
        case .found(let password): return password
        case .missing: return nil
        }
      }

      if let group = inFlight[cacheKey] {
        lock.unlock()
        group.wait()
        continue loop
      }

      let group = DispatchGroup()
      group.enter()
      inFlight[cacheKey] = group
      lock.unlock()

      let password = loader()

      lock.lock()
      if let password {
        cache[cacheKey] = .found(password)
      } else {
        cache[cacheKey] = .missing
      }
      let completedGroup = inFlight.removeValue(forKey: cacheKey)
      lock.unlock()

      completedGroup?.leave()
      return password
    }
  }

  func invalidate(cacheKey: String) {
    lock.lock()
    cache.removeValue(forKey: cacheKey)
    lock.unlock()
  }
}

struct BrowserPythonRunner {
  typealias Result = PipeProcessResult

  static func run(
    script: String,
    arguments: [String],
    stdinData: Data? = nil,
    timeoutSeconds: Int = 60
  ) throws -> Result {
    let pythonPaths = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
    guard let pythonPath = pythonPaths.first(where: { FileManager.default.fileExists(atPath: $0) })
    else {
      throw BrowserPythonRunnerError.pythonNotFound
    }

    do {
      return try PipeProcessRunner.run(
        executableURL: URL(fileURLWithPath: pythonPath),
        arguments: ["-c", script] + arguments,
        stdinData: stdinData,
        timeoutSeconds: TimeInterval(timeoutSeconds)
      )
    } catch PipeProcessRunnerError.timedOut {
      throw BrowserPythonRunnerError.timedOut
    } catch {
      throw BrowserPythonRunnerError.launchFailed(error.localizedDescription)
    }
  }
}

enum BrowserPythonRunnerError: LocalizedError {
  case pythonNotFound
  case launchFailed(String)
  case timedOut

  var errorDescription: String? {
    switch self {
    case .pythonNotFound:
      return "Python 3 not found. Install it via Homebrew: brew install python3"
    case .launchFailed(let message):
      return "Failed to run Python: \(message)"
    case .timedOut:
      return "Python helper timed out"
    }
  }
}
