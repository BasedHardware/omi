import Foundation
import Security

// MARK: - Models

struct GmailEmail: Identifiable {
  let id: String
  let from: String
  let subject: String
  let snippet: String
  let date: Date
  let isUnread: Bool
}

enum GmailReaderError: LocalizedError {
  case noBrowserFound
  case noGmailCookies
  case cookieDecryptionFailed(String)
  case networkError(String)
  case authFailed
  case pythonNotFound

  var errorDescription: String? {
    switch self {
    case .noBrowserFound:
      return "No browser with Gmail session found. Log into Gmail in Chrome, Arc, Brave, or Edge."
    case .noGmailCookies:
      return "No Gmail session cookies found. Make sure you're logged into Gmail."
    case .cookieDecryptionFailed(let msg):
      return "Cookie decryption failed: \(msg)"
    case .networkError(let msg):
      return "Network error: \(msg)"
    case .authFailed:
      return "Gmail authentication failed. Try refreshing your Gmail session in the browser."
    case .pythonNotFound:
      return "Python 3 not found. Install it via Homebrew: brew install python3"
    }
  }
}

// MARK: - Browser Config

private struct BrowserConfig {
  let name: String
  let keychainService: String
  let cookiePath: String

  static func allBrowsers() -> [BrowserConfig] {
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    return [
      BrowserConfig(
        name: "Arc",
        keychainService: "Arc Safe Storage",
        cookiePath: "\(home)/Library/Application Support/Arc/User Data/Default/Cookies"
      ),
      BrowserConfig(
        name: "Chrome",
        keychainService: "Chrome Safe Storage",
        cookiePath: "\(home)/Library/Application Support/Google/Chrome/Default/Cookies"
      ),
    ]
  }
}

// MARK: - GmailReaderService

actor GmailReaderService {
  static let shared = GmailReaderService()

  /// Read emails using browser cookies + Gmail Atom feed.
  /// - Parameters:
  ///   - maxResults: Maximum number of emails to return
  ///   - query: Gmail search query (default: "newer_than:1d"). For onboarding use "newer_than:30d".
  func readRecentEmails(maxResults: Int = 50, query: String = "newer_than:1d") async throws -> [GmailEmail] {
    let emails = try fetchGmailViaAtomFeed(maxResults: maxResults, query: query)
    return emails.sorted { $0.date > $1.date }
  }

  /// Synthesize profile memories and tasks from a batch of emails.
  /// Uses an LLM call to extract ~10 memories and 2-3 tasks.
  func synthesizeFromEmails(emails: [GmailEmail]) async -> (memories: Int, tasks: Int, profileSummary: String) {
    guard !emails.isEmpty else { return (0, 0, "") }

    // Format emails compactly for the LLM
    var emailLines: [String] = []
    let dateFormatter = DateFormatter()
    dateFormatter.dateFormat = "MMM d"
    for email in emails {
      let date = dateFormatter.string(from: email.date)
      let sender =
        email.from.components(separatedBy: "<").first?.trimmingCharacters(in: .whitespaces) ?? email.from
      emailLines.append("[\(date)] From: \(sender) | Subject: \(email.subject) | \(email.snippet)")
    }
    let emailText = emailLines.joined(separator: "\n")

    let synthesisPrompt = """
    Analyze these \(emails.count) recent emails and extract profile information about the user.

    EMAILS:
    \(emailText)

    Respond ONLY with valid JSON (no markdown, no code fences, no backticks):
    {
      "memories": [
        "factual statement about the user based on email patterns"
      ],
      "tasks": [
        {"description": "actionable follow-up item", "priority": "high"}
      ],
      "profile": "2-3 sentence summary of who this user is"
    }

    RULES:
    - Extract exactly 10 memories (facts about their role, company, projects, relationships, interests, tools, communication patterns)
    - Extract 2-3 tasks (pending replies, upcoming deadlines, things to follow up on)
    - Each memory should be a single clear factual statement
    - Task priorities: "high", "medium", or "low"
    - Profile should summarize professional identity and key interests
    - Do NOT include raw email content — synthesize and generalize
    - Output ONLY the JSON object, nothing else
    """

    do {
      let bridge = ACPBridge(passApiKey: true)
      try await bridge.start()
      defer { Task { await bridge.stop() } }

      let result = try await bridge.query(
        prompt: synthesisPrompt,
        systemPrompt:
          "You are a profile extraction assistant. Output ONLY valid JSON. No markdown, no code fences, no explanation.",
        model: "claude-opus-4-6",
        onTextDelta: { @Sendable _ in },
        onToolCall: { @Sendable _, _, _ in return "" },
        onToolActivity: { @Sendable _, _, _, _ in }
      )

      var responseText = result.text.trimmingCharacters(in: .whitespacesAndNewlines)
      log("GmailReaderService: Synthesis response length: \(responseText.count) chars")

      // Strip markdown code fences if present (```json ... ``` or ``` ... ```)
      if responseText.hasPrefix("```") {
        // Remove opening fence (```json or ```)
        if let firstNewline = responseText.firstIndex(of: "\n") {
          responseText = String(responseText[responseText.index(after: firstNewline)...])
        }
        // Remove closing fence
        if responseText.hasSuffix("```") {
          responseText = String(responseText.dropLast(3)).trimmingCharacters(in: .whitespacesAndNewlines)
        }
      }

      // Parse the JSON response
      guard let jsonData = responseText.data(using: .utf8),
        let parsed = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any]
      else {
        log("GmailReaderService: Failed to parse synthesis response: \(responseText.prefix(500))")
        return (0, 0, "")
      }

      let memoryStrings = parsed["memories"] as? [String] ?? []
      let taskDicts = parsed["tasks"] as? [[String: Any]] ?? []
      let profileSummary = parsed["profile"] as? String ?? ""

      log("GmailReaderService: Parsed \(memoryStrings.count) memories, \(taskDicts.count) tasks")

      // Save memories
      var memoriesSaved = 0
      for memory in memoryStrings {
        do {
          _ = try await APIClient.shared.createMemory(
            content: memory,
            visibility: "private",
            tags: ["gmail", "onboarding", "profile"],
            source: "gmail",
            headline: "Email Profile Insight"
          )
          memoriesSaved += 1
        } catch {
          log("GmailReaderService: Failed to save synthesized memory: \(error)")
        }
      }

      // Save tasks
      var tasksSaved = 0
      for taskDict in taskDicts {
        guard let description = taskDict["description"] as? String else { continue }
        let priority = taskDict["priority"] as? String ?? "medium"
        let task = await TasksStore.shared.createTask(
          description: description,
          dueAt: nil,
          priority: priority,
          tags: ["gmail", "onboarding"]
        )
        if task != nil { tasksSaved += 1 }
      }

      log(
        "GmailReaderService: Synthesis complete — \(memoriesSaved) memories, \(tasksSaved) tasks"
      )
      return (memoriesSaved, tasksSaved, profileSummary)

    } catch {
      log("GmailReaderService: Synthesis failed: \(error)")
      return (0, 0, "")
    }
  }

  /// Save fetched emails as memories via the OMI backend API.
  func saveAsMemories(emails: [GmailEmail]) async -> (saved: Int, failed: Int) {
    var saved = 0
    var failed = 0
    for email in emails {
      let dateStr = email.date.formatted(date: .abbreviated, time: .shortened)
      let senderName =
        email.from.components(separatedBy: "<").first?.trimmingCharacters(in: .whitespaces)
        ?? email.from
      let content = "Email from \(senderName) — \"\(email.subject)\": \(email.snippet)"
      do {
        _ = try await APIClient.shared.createMemory(
          content: content,
          visibility: "private",
          tags: ["gmail", "email"],
          source: "gmail",
          windowTitle: "Gmail — \(dateStr)",
          headline: email.subject
        )
        saved += 1
      } catch {
        log("GmailReaderService: Failed to save memory for email \(email.id): \(error)")
        failed += 1
      }
    }
    log("GmailReaderService: Saved \(saved) emails as memories (\(failed) failed)")
    return (saved, failed)
  }

  // MARK: - All-in-one Python: decrypt cookies + fetch Atom feed + return JSON

  private func fetchGmailViaAtomFeed(maxResults: Int, query: String = "newer_than:1d") throws -> [GmailEmail] {
    // Build browser configs as JSON for Python
    var browserConfigs: [[String: String]] = []
    for browser in BrowserConfig.allBrowsers() {
      guard FileManager.default.fileExists(atPath: browser.cookiePath) else { continue }
      guard let password = getKeychainPassword(service: browser.keychainService) else { continue }

      let tmpPath = "/tmp/omi_cookies_\(browser.name)_\(Int(Date().timeIntervalSince1970)).db"
      do {
        try FileManager.default.copyItem(atPath: browser.cookiePath, toPath: tmpPath)
      } catch {
        log("GmailReaderService: Failed to copy \(browser.name) cookies: \(error)")
        continue
      }

      browserConfigs.append([
        "name": browser.name,
        "db_path": tmpPath,
        "password": password,
      ])
    }

    guard !browserConfigs.isEmpty else {
      throw GmailReaderError.noBrowserFound
    }

    let configJSON: String
    do {
      let data = try JSONSerialization.data(withJSONObject: browserConfigs)
      configJSON = String(data: data, encoding: .utf8) ?? "[]"
    } catch {
      throw GmailReaderError.networkError("Failed to serialize browser configs")
    }

    defer {
      // Clean up temp DB files
      for config in browserConfigs {
        if let path = config["db_path"] {
          try? FileManager.default.removeItem(atPath: path)
        }
      }
    }

    let pythonScript = """
      import sys, json, sqlite3, hashlib, xml.etree.ElementTree as ET
      from http.cookiejar import MozillaCookieJar, Cookie
      from urllib.request import Request, build_opener, HTTPCookieProcessor
      import time

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

      browsers = json.loads(sys.argv[1])
      max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 50
      query = sys.argv[3] if len(sys.argv) > 3 else 'newer_than:1d'

      def decrypt_cookies_with_domains(db_path, password):
          key = hashlib.pbkdf2_hmac('sha1', password.encode('utf-8'), b'saltysalt', 1003, dklen=16)
          iv = b' ' * 16
          try:
              conn = sqlite3.connect(db_path)
              c = conn.cursor()
              c.execute('SELECT value FROM meta WHERE key="version"')
              row = c.fetchone()
              db_version = int(row[0]) if row else 0
              c.execute("SELECT host_key, name, encrypted_value, path, is_secure, expires_utc FROM cookies WHERE host_key LIKE '%google.com%' OR host_key LIKE '%gmail.com%'")
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
                      value = decrypted.decode('utf-8', errors='replace')
                  except Exception:
                      continue
              elif enc:
                  try:
                      value = enc.decode('utf-8', errors='replace')
                  except Exception:
                      continue
              if value:
                  domain = host_key.lstrip('.')
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

      def fetch_atom_feed(jar):
          opener = build_opener(HTTPCookieProcessor(jar))
          req = Request(f'https://mail.google.com/mail/feed/atom?q={query}')
          req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36')
          try:
              resp = opener.open(req, timeout=30)
              status = resp.getcode()
              body = resp.read()
              return status, body
          except Exception as e:
              return None, str(e)

      def parse_atom(xml_bytes, max_results):
          ns = {'atom': 'http://purl.org/atom/ns#'}
          try:
              root = ET.fromstring(xml_bytes)
          except ET.ParseError as e:
              return None, f'XML parse error: {e}'

          entries = root.findall('atom:entry', ns)
          emails = []
          for i, entry in enumerate(entries[:max_results]):
              title = entry.findtext('atom:title', '', ns)
              summary = entry.findtext('atom:summary', '', ns)
              author_name = ''
              author_email_addr = ''
              author_el = entry.find('atom:author', ns)
              if author_el is not None:
                  author_name = author_el.findtext('atom:name', '', ns)
                  author_email_addr = author_el.findtext('atom:email', '', ns)
              issued = entry.findtext('atom:issued', '', ns)
              link_el = entry.find('atom:link', ns)
              msg_id = ''
              if link_el is not None:
                  href = link_el.get('href', '')
                  if '/message_id=' in href:
                      msg_id = href.split('/message_id=')[-1]
                  else:
                      msg_id = f'atom_{i}'
              else:
                  msg_id = f'atom_{i}'

              from_str = f'{author_name} <{author_email_addr}>' if author_email_addr else author_name
              emails.append({
                  'id': msg_id,
                  'from': from_str,
                  'subject': title or '(no subject)',
                  'snippet': summary or '',
                  'date': issued or '',
                  'isUnread': True,
              })
          return emails, None

      # Try each browser
      for browser in browsers:
          cookies, err = decrypt_cookies_with_domains(browser['db_path'], browser['password'])
          if err or not cookies:
              continue

          auth_names = {'SID', 'HSID', 'SSID', 'APISID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID'}
          found_auth = [c for c in cookies if c['name'] in auth_names]
          if not found_auth:
              continue

          jar = make_cookie_jar(cookies)
          status, body = fetch_atom_feed(jar)
          if status != 200:
              continue

          emails, parse_err = parse_atom(body, max_results)
          if parse_err or emails is None:
              continue

          print(json.dumps({'ok': True, 'browser': browser['name'], 'emails': emails, 'count': len(emails)}))
          sys.exit(0)

      print(json.dumps({'ok': False, 'error': 'No browser with valid Gmail session found'}))
      sys.exit(0)
      """

    // Find Python
    let pythonPaths = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
    guard let pythonPath = pythonPaths.first(where: { FileManager.default.fileExists(atPath: $0) })
    else {
      throw GmailReaderError.pythonNotFound
    }

    let process = Process()
    process.executableURL = URL(fileURLWithPath: pythonPath)
    process.arguments = ["-c", pythonScript, configJSON, String(maxResults), query]
    let pipe = Pipe()
    let errPipe = Pipe()
    process.standardOutput = pipe
    process.standardError = errPipe

    do {
      try process.run()
      process.waitUntilExit()
    } catch {
      throw GmailReaderError.networkError("Failed to run Python: \(error.localizedDescription)")
    }

    let output = pipe.fileHandleForReading.readDataToEndOfFile()
    let errOutput = String(data: errPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    if !errOutput.isEmpty {
      log("GmailReaderService: Python stderr: \(errOutput.prefix(500))")
    }

    guard let json = try? JSONSerialization.jsonObject(with: output) as? [String: Any] else {
      let raw = String(data: output, encoding: .utf8) ?? "(empty)"
      throw GmailReaderError.networkError("Python returned invalid JSON: \(raw.prefix(200))")
    }

    guard json["ok"] as? Bool == true else {
      let errMsg = json["error"] as? String ?? "Unknown error"
      throw GmailReaderError.networkError(errMsg)
    }

    guard let emailDicts = json["emails"] as? [[String: Any]] else {
      return []
    }

    let browserName = json["browser"] as? String ?? "unknown"
    log("GmailReaderService: Got \(emailDicts.count) emails from \(browserName) via Atom feed")

    return emailDicts.compactMap { dict -> GmailEmail? in
      guard let id = dict["id"] as? String,
        let from = dict["from"] as? String,
        let subject = dict["subject"] as? String
      else { return nil }

      let snippet = dict["snippet"] as? String ?? ""
      let dateStr = dict["date"] as? String ?? ""
      let isUnread = dict["isUnread"] as? Bool ?? true

      return GmailEmail(
        id: id,
        from: from,
        subject: subject,
        snippet: snippet,
        date: parseISO8601Date(dateStr) ?? Date(),
        isUnread: isUnread
      )
    }
  }

  // MARK: - Keychain

  private func getKeychainPassword(service: String) -> String? {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]
    var result: AnyObject?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess, let data = result as? Data,
      let password = String(data: data, encoding: .utf8)
    else {
      if status != errSecItemNotFound {
        log("GmailReaderService: Keychain lookup for '\(service)' failed with status \(status)")
      }
      return nil
    }
    return password.isEmpty ? nil : password
  }

  // MARK: - Date Parsing

  private func parseISO8601Date(_ str: String) -> Date? {
    // Gmail Atom feed uses ISO 8601: 2026-03-15T10:30:00Z
    let iso = ISO8601DateFormatter()
    if let d = iso.date(from: str) { return d }
    // Try with fractional seconds
    iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let d = iso.date(from: str) { return d }
    // Fallback: RFC 2822
    let formats = ["EEE, dd MMM yyyy HH:mm:ss Z", "dd MMM yyyy HH:mm:ss Z", "yyyy-MM-dd'T'HH:mm:ssZ"]
    for fmt in formats {
      let f = DateFormatter()
      f.dateFormat = fmt
      f.locale = Locale(identifier: "en_US_POSIX")
      if let d = f.date(from: str) { return d }
    }
    return nil
  }
}
