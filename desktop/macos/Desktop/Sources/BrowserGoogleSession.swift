import Darwin
import Foundation
import Security

struct BrowserGoogleSession: Equatable {
  let browserName: String
  let keychainService: String
  let cookiePath: String

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

  static func all() -> [BrowserGoogleSession] {
    let homeDirectory = FileManager.default.homeDirectoryForCurrentUser
    return BrowserAutomationTargetResolver.knownTargets.flatMap { target in
      guard let keychainService = keychainService(for: target) else {
        return [BrowserGoogleSession]()
      }
      let userDataPath = target.profileRoot(homeDirectory: homeDirectory).path
      return cookiePaths(in: userDataPath).map { cookiePath in
        let cookieURL = URL(fileURLWithPath: cookiePath)
        let profileURL =
          cookieURL.deletingLastPathComponent().lastPathComponent == "Network"
          ? cookieURL.deletingLastPathComponent().deletingLastPathComponent()
          : cookieURL.deletingLastPathComponent()
        let profileName = profileURL.lastPathComponent
        let browserName = profileName == "Default" ? target.name : "\(target.name) (\(profileName))"
        return BrowserGoogleSession(
          browserName: browserName,
          keychainService: keychainService,
          cookiePath: cookiePath
        )
      }
    }
  }

  static func configsForPython(logPrefix: String) -> [[String: String]] {
    all().compactMap { session in
      guard FileManager.default.fileExists(atPath: session.cookiePath) else { return nil }
      guard let password = BrowserKeychainCache.shared.password(for: session.keychainService) else {
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

  static func cookiePaths(in userDataPath: String) -> [String] {
    let fm = FileManager.default
    guard let entries = try? fm.contentsOfDirectory(atPath: userDataPath) else { return [] }

    return
      entries
      .compactMap { entry -> (name: String, path: String)? in
        var isDirectory: ObjCBool = false
        let profilePath = "\(userDataPath)/\(entry)"
        guard fm.fileExists(atPath: profilePath, isDirectory: &isDirectory), isDirectory.boolValue else {
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

  private static func keychainService(for target: BrowserAutomationTarget) -> String? {
    switch target.bundleIdentifier {
    case "company.thebrowser.Browser":
      return "Arc Safe Storage"
    case "com.google.Chrome", "com.google.Chrome.beta", "com.google.Chrome.canary",
      "com.openai.atlas":
      return "Chrome Safe Storage"
    case "com.brave.Browser", "com.brave.Browser.beta", "com.brave.Browser.nightly":
      return "Brave Safe Storage"
    case "com.microsoft.edgemac", "com.microsoft.edgemac.Beta", "com.microsoft.edgemac.Dev",
      "com.microsoft.edgemac.Canary":
      return "Microsoft Edge Safe Storage"
    case "com.operasoftware.Opera", "com.operasoftware.OperaGX":
      return "Opera Safe Storage"
    case "org.chromium.Chromium":
      return "Chromium Safe Storage"
    case "com.vivaldi.Vivaldi":
      return "Vivaldi Safe Storage"
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
/// Fallback path: the legacy `/usr/bin/security find-generic-password -w` CLI, kept
/// for environments where the in-process read cannot complete for an environmental
/// reason (e.g. no interaction allowed on a background thread). We never fall back
/// after the user actively denies the in-process prompt, so there is no double-prompt.
///
/// NOTE: neither path makes "Always Allow" durably persist. The Safe Storage item is
/// owned by the browser and its ACL partition list is pinned to the browser's Team ID,
/// so macOS may re-prompt a third-party reader on each launch regardless of the API
/// used — this is a browser/OS ACL limitation, not a bug here (see
/// mostlikelee.com "Scripting the macOS Keychain – Partition IDs"). The durable fix is
/// OAuth-backed providers. The in-memory cache below only coalesces concurrent reads
/// within a single app run; we do not duplicate browser Safe Storage secrets into app
/// preferences.
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

  func password(for service: String) -> String? {
    password(for: service) {
      // Primary: in-process read so the OS attributes the prompt to this signed app.
      let (nativePassword, status) = Self.nativeSafeStoragePassword(for: service)
      if let nativePassword { return nativePassword }

      // Only fall back to the legacy `/usr/bin/security` CLI when the in-process read
      // could not complete for an environmental reason (see shouldFallBackToLegacyCLI).
      guard Self.shouldFallBackToLegacyCLI(afterNativeReadStatus: status) else { return nil }
      return Self.securityCLIPassword(for: service)
    }
  }

  /// Whether a nil in-process read should retry through the legacy `/usr/bin/security`
  /// CLI. We fall back ONLY for environmental failures (e.g. `errSecInteractionNotAllowed`
  /// on a background thread, `errSecNotAvailable`). We do NOT fall back when:
  ///   - the read already succeeded (`errSecSuccess`, e.g. empty/undecodable data),
  ///   - the user actively denied the prompt (`errSecUserCanceled`, `errSecAuthFailed`) —
  ///     retrying would surface a second, worse-looking "security wants to access" dialog,
  ///   - the item is absent (`errSecItemNotFound`) — there is no browser session to read.
  ///
  /// Pure and version-agnostic (a switch over `OSStatus`), so the behavior is identical on
  /// every supported macOS version and is unit-testable without touching the real Keychain.
  static func shouldFallBackToLegacyCLI(afterNativeReadStatus status: OSStatus) -> Bool {
    switch status {
    case errSecSuccess, errSecUserCanceled, errSecAuthFailed, errSecItemNotFound:
      return false
    default:
      return true
    }
  }

  /// Reads the browser Safe Storage key in-process via the Security framework.
  /// The keychain prompt is attributed to this app bundle, not `/usr/bin/security`.
  /// Returns the decoded password (if any) and the raw `OSStatus` so the caller can
  /// decide whether an environmental failure warrants the legacy CLI fallback.
  private static func nativeSafeStoragePassword(for service: String) -> (password: String?, status: OSStatus) {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]
    var item: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &item)
    guard status == errSecSuccess,
      let data = item as? Data,
      let password = String(data: data, encoding: .utf8),
      !password.isEmpty
    else {
      return (nil, status)
    }
    return (password, status)
  }

  /// Legacy fallback: shells out to `/usr/bin/security`. Retained for resilience when
  /// the in-process read cannot complete. Note the OS attributes this prompt to
  /// "security", not this app — this is the fallback, not the primary path.
  private static func securityCLIPassword(for service: String) -> String? {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/security")
    process.arguments = ["find-generic-password", "-s", service, "-w"]
    let pipe = Pipe()
    let errPipe = Pipe()
    process.standardOutput = pipe
    process.standardError = errPipe
    do {
      try process.run()
      process.waitUntilExit()
      guard process.terminationStatus == 0 else { return nil }
      let output = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines)
      return output?.isEmpty == false ? output : nil
    } catch {
      return nil
    }
  }

  func password(for service: String, loader: () -> String?) -> String? {
    loop: while true {
      lock.lock()

      if let cached = cache[service] {
        lock.unlock()
        switch cached {
        case .found(let password): return password
        case .missing: return nil
        }
      }

      if let group = inFlight[service] {
        lock.unlock()
        group.wait()
        continue loop
      }

      let group = DispatchGroup()
      group.enter()
      inFlight[service] = group
      lock.unlock()

      let password = loader()

      lock.lock()
      if let password {
        cache[service] = .found(password)
      } else {
        cache[service] = .missing
      }
      let completedGroup = inFlight.removeValue(forKey: service)
      lock.unlock()

      completedGroup?.leave()
      return password
    }
  }

  func invalidate(service: String) {
    lock.lock()
    cache.removeValue(forKey: service)
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
