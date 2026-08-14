import Foundation

struct GmailAccountOption: Identifiable, Equatable {
  let id: String
  let browserName: String
  let email: String?
}

enum GmailSelectionStore {
  private static let selectedPathKey = DefaultsKey.gmailSelectedCookiePath.rawValue
  private static let selectedLabelKey = DefaultsKey.gmailSelectedAccountLabel.rawValue

  static var selectedCookiePath: String? {
    get { UserDefaults.standard.string(forKey: selectedPathKey) }
    set { UserDefaults.standard.set(newValue, forKey: selectedPathKey) }
  }

  static var selectedAccountLabel: String {
    UserDefaults.standard.string(forKey: selectedLabelKey) ?? ""
  }

  static var hasMadeChoice: Bool {
    selectedCookiePath != nil || !selectedAccountLabel.isEmpty
  }

  static func persist(cookiePath: String?, label: String) {
    selectedCookiePath = cookiePath
    UserDefaults.standard.set(label, forKey: selectedLabelKey)
  }

  static func resetForTesting() {
    UserDefaults.standard.removeObject(forKey: selectedPathKey)
    UserDefaults.standard.removeObject(forKey: selectedLabelKey)
  }

  static func filter(_ configs: [[String: String]]) -> [[String: String]] {
    filter(configs, selectedCookiePath: selectedCookiePath)
  }

  /// Filter with an explicit snapshot of the selected profile. Callers that
  /// run several fetches for one logical read pass the snapshot captured at
  /// read entry, so a picker change mid-read cannot mix two accounts' mail.
  static func filter(_ configs: [[String: String]], selectedCookiePath: String?) -> [[String: String]] {
    guard let selected = selectedCookiePath, !selected.isEmpty else { return configs }
    let narrowed = configs.filter { $0["db_path"] == selected }
    guard narrowed.isEmpty else { return narrowed }
    // The stored selection no longer matches any configured profile (cookies
    // deleted, profile removed, path changed). Widening back to every profile
    // silently changes which inbox is read while Settings still shows the old
    // label — record the fail-open so it is not invisible.
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "gmail_account_selection",
      from: "selected_account",
      to: "first_readable_profile",
      reason: "selected_profile_missing",
      outcome: .recovered)
    return configs
  }
}

enum GmailAccountProbe {
  static func availableAccounts() async throws -> [GmailAccountOption] {
    let configs = BrowserGoogleSession.configsForPython(logPrefix: "GmailAccountProbe")
    guard !configs.isEmpty else { return [] }

    let configJSON: String
    do {
      let data = try JSONSerialization.data(withJSONObject: configs)
      configJSON = String(data: data, encoding: .utf8) ?? "[]"
    } catch {
      throw error
    }

    let pythonScript = """
      \(BrowserGoogleSession.chromiumCookiePythonSupport)
      import re
      from urllib.request import Request, build_opener, HTTPCookieProcessor

      browsers = json.loads(sys.stdin.read())
      accounts = []
      for browser in browsers:
          cookies, err = decrypt_google_cookies(browser['db_path'], browser['password'], include_gmail_hosts=True)
          if err or not cookies:
              continue
          if not [c for c in cookies if c['name'] in GOOGLE_AUTH_COOKIE_NAMES]:
              continue
          jar = make_cookie_jar(cookies)
          email = None
          for url in ('https://accounts.google.com/AccountInfo', 'https://www.google.com/accounts/AccountInfo'):
              try:
                  opener = build_opener(HTTPCookieProcessor(jar))
                  req = Request(url)
                  req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36')
                  resp = opener.open(req, timeout=15)
                  body = resp.read().decode('utf-8', errors='replace')
                  match = re.search(r'<email>([^<]+)</email>', body)
                  if match:
                      email = match.group(1)
                      break
              except Exception:
                  continue
          accounts.append({'name': browser['name'], 'db_path': browser['db_path'], 'email': email})
      write_json_result('omi_gmail_accounts_', {'ok': True, 'accounts': accounts})
      """

    do {
      let result = try BrowserPythonRunner.run(
        script: pythonScript,
        arguments: [],
        stdinData: Data(configJSON.utf8),
        // Two sequential AccountInfo probes per profile with a 15s request
        // timeout; give the process budget for every configured profile so a
        // slow Google endpoint cannot zero out all discovered accounts.
        timeoutSeconds: 45 + 30 * max(configs.count, 1)
      )
      let outputPath =
        String(data: result.stdout, encoding: .utf8)?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      guard !outputPath.isEmpty, FileManager.default.fileExists(atPath: outputPath) else {
        throw GmailAccountProbeError.noOutput
      }
      defer { try? FileManager.default.removeItem(atPath: outputPath) }
      let data = try Data(contentsOf: URL(fileURLWithPath: outputPath))
      guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        throw GmailAccountProbeError.invalidOutput
      }
      return Self.parseAccounts(json)
    }
  }

  enum GmailAccountProbeError: LocalizedError {
    case noOutput
    case invalidOutput

    var errorDescription: String? {
      switch self {
      case .noOutput:
        return "Gmail account probe produced no output."
      case .invalidOutput:
        return "Gmail account probe returned unreadable output."
      }
    }
  }

  static func parseAccounts(_ json: [String: Any]) -> [GmailAccountOption] {
    let raw = (json["accounts"] as? [[String: Any]] ?? []).sorted { lhs, rhs in
      let lhsName = lhs["name"] as? String ?? ""
      let rhsName = rhs["name"] as? String ?? ""
      return lhsName.localizedStandardCompare(rhsName) == .orderedAscending
    }
    return raw.compactMap { dict in
      guard let path = dict["db_path"] as? String, !path.isEmpty else { return nil }
      let email = (dict["email"] as? String).flatMap { $0.isEmpty ? nil : $0 }
      return GmailAccountOption(
        id: path,
        browserName: dict["name"] as? String ?? "Browser",
        email: email
      )
    }
  }
}
