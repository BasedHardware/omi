import Foundation

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

  private struct BrowserFamily {
    let name: String
    let keychainService: String
    let userDataPath: String
  }

  private static func cookiePaths(in userDataPath: String) -> [String] {
    let fm = FileManager.default
    guard let entries = try? fm.contentsOfDirectory(atPath: userDataPath) else { return [] }

    return
      entries
      .filter { $0 == "Default" || $0.hasPrefix("Profile ") }
      .sorted { lhs, rhs in
        if lhs == "Default" { return true }
        if rhs == "Default" { return false }
        return lhs.localizedStandardCompare(rhs) == .orderedAscending
      }
      .map { "\(userDataPath)/\($0)/Cookies" }
      .filter { fm.fileExists(atPath: $0) }
  }

  static func allBrowsers() -> [BrowserConfig] {
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let families = [
      BrowserFamily(
        name: "Arc",
        keychainService: "Arc Safe Storage",
        userDataPath: "\(home)/Library/Application Support/Arc/User Data"
      ),
      BrowserFamily(
        name: "Chrome",
        keychainService: "Chrome Safe Storage",
        userDataPath: "\(home)/Library/Application Support/Google/Chrome"
      ),
      BrowserFamily(
        name: "Brave",
        keychainService: "Brave Safe Storage",
        userDataPath: "\(home)/Library/Application Support/BraveSoftware/Brave-Browser"
      ),
      BrowserFamily(
        name: "Edge",
        keychainService: "Microsoft Edge Safe Storage",
        userDataPath: "\(home)/Library/Application Support/Microsoft Edge"
      ),
    ]

    return families.flatMap { family in
      cookiePaths(in: family.userDataPath).map { cookiePath in
        let profileName = URL(fileURLWithPath: cookiePath).deletingLastPathComponent()
          .lastPathComponent
        let browserName = profileName == "Default" ? family.name : "\(family.name) (\(profileName))"
        return BrowserConfig(
          name: browserName,
          keychainService: family.keychainService,
          cookiePath: cookiePath
        )
      }
    }
  }
}

// MARK: - Shared Keychain Cache

/// Shared cache for browser keychain passwords so we only prompt once per session.
/// Used by both GmailReaderService and CalendarReaderService.
final class BrowserKeychainCache: @unchecked Sendable {
  static let shared = BrowserKeychainCache()
  private var cache: [String: String] = [:]
  private var inFlight: [String: DispatchGroup] = [:]
  private let lock = NSLock()
  private let persistKey = "cachedBrowserKeychainPasswords"

  private init() {
    // Restore persisted passwords so we never re-prompt after the first "Always Allow"
    if let persisted = UserDefaults.standard.dictionary(forKey: persistKey) as? [String: String] {
      cache = persisted
    }
  }

  /// Ensures only one keychain lookup runs per browser service at a time.
  /// Persists successful lookups so the keychain prompt only appears once ever.
  func password(for service: String, loader: () -> String?) -> String? {
    loop: while true {
      lock.lock()

      if let cached = cache[service] {
        lock.unlock()
        return cached.isEmpty ? nil : cached
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
      cache[service] = password ?? ""
      // Persist non-empty passwords across app launches
      if password != nil {
        let toSave = cache.filter { !$0.value.isEmpty }
        UserDefaults.standard.set(toSave, forKey: persistKey)
      }
      let completedGroup = inFlight.removeValue(forKey: service)
      lock.unlock()

      completedGroup?.leave()
      return password
    }
  }

  /// Invalidate a cached password (e.g. if cookie decryption fails, Chrome may have rotated the key).
  func invalidate(service: String) {
    lock.lock()
    cache.removeValue(forKey: service)
    let toSave = cache.filter { !$0.value.isEmpty }
    UserDefaults.standard.set(toSave, forKey: persistKey)
    lock.unlock()
  }
}

// MARK: - GmailReaderService

actor GmailReaderService {
  static let shared = GmailReaderService()

  /// Read emails using browser cookies + Gmail Atom feed.
  /// - Parameters:
  ///   - maxResults: Maximum number of emails to return
  ///   - query: Gmail search query (default: "newer_than:1d"). For onboarding use "newer_than:30d".
  func readRecentEmails(maxResults: Int = 50, query: String = "newer_than:1d") async throws
    -> [GmailEmail]
  {
    let emails: [GmailEmail]
    if let days = Self.parseNewerThanDays(query), days > 20 {
      let bootstrapEmails = try fetchGmailViaAtomFeedSingle(
        maxResults: maxResults,
        query: query,
        feedPath: nil,
        allowBootstrap: true
      )
      let labelEmails = try fetchGmailViaLabelFeeds(maxResults: maxResults)
      var merged: [String: GmailEmail] = [:]
      for email in bootstrapEmails + labelEmails {
        let existing = merged[email.id]
        if existing == nil || existing!.date < email.date {
          merged[email.id] = email
        }
      }
      emails = Array(merged.values)
        .sorted { $0.date > $1.date }
        .prefix(maxResults)
        .map(\.self)
    } else {
      emails = try fetchGmailViaAtomFeedSingle(maxResults: maxResults, query: query)
    }
    return emails.sorted { $0.date > $1.date }
  }

  /// Synthesize profile memories and tasks from a batch of emails.
  /// Uses an LLM call to extract ~10 memories and 2-3 tasks.
  func synthesizeFromEmails(emails: [GmailEmail]) async -> (
    memories: Int, tasks: Int, profileSummary: String
  ) {
    guard !emails.isEmpty else { return (0, 0, "") }

    // Format emails compactly for the LLM
    var emailLines: [String] = []
    let dateFormatter = DateFormatter()
    dateFormatter.dateFormat = "MMM d"
    for email in emails {
      let date = dateFormatter.string(from: email.date)
      let sender =
        email.from.components(separatedBy: "<").first?.trimmingCharacters(in: .whitespaces)
        ?? email.from
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
      let bridge = AgentBridge(harnessMode: "piMono")
      try await bridge.start()
      defer { Task { await bridge.stop() } }

      let result = try await bridge.query(
        prompt: synthesisPrompt,
        systemPrompt:
          "You are a profile extraction assistant. Output ONLY valid JSON. No markdown, no code fences, no explanation.",
        model: ModelQoS.Claude.synthesis,
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
          responseText = String(responseText.dropLast(3)).trimmingCharacters(
            in: .whitespacesAndNewlines)
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
    guard !emails.isEmpty else { return (0, 0) }

    let concurrency = min(8, emails.count)
    var nextIndex = 0

    return await withTaskGroup(of: Bool.self) { group in
      func enqueueNext() {
        guard nextIndex < emails.count else { return }
        let email = emails[nextIndex]
        nextIndex += 1
        group.addTask {
          await Self.saveMemory(for: email)
        }
      }

      for _ in 0..<concurrency {
        enqueueNext()
      }

      var saved = 0
      var failed = 0

      while let success = await group.next() {
        if success {
          saved += 1
        } else {
          failed += 1
        }
        enqueueNext()
      }

      log("GmailReaderService: Saved \(saved) emails as memories (\(failed) failed)")
      return (saved, failed)
    }
  }

  // MARK: - All-in-one Python: decrypt cookies + fetch Gmail session HTML + return JSON

  private func fetchGmailViaAtomFeedSingle(
    maxResults: Int,
    query: String = "newer_than:1d",
    feedPath: String? = nil,
    allowBootstrap: Bool? = nil
  ) throws
    -> [GmailEmail]
  {
    let shouldUseBootstrapPage =
      allowBootstrap ?? (feedPath == nil && Self.parseNewerThanDays(query) != nil)

    // Build browser configs as JSON for Python.
    // Pass the original cookie DB path and open it read-only in Python so we do not miss
    // live Chromium cookie rows from WAL/journal state while the browser is running.
    var browserConfigs: [[String: String]] = []
    for browser in BrowserConfig.allBrowsers() {
      guard FileManager.default.fileExists(atPath: browser.cookiePath) else { continue }
      guard let password = getKeychainPassword(service: browser.keychainService) else { continue }

      browserConfigs.append([
        "name": browser.name,
        "db_path": browser.cookiePath,
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

    let pythonScript = """
      import sys, json, sqlite3, hashlib, xml.etree.ElementTree as ET
      from http.cookiejar import MozillaCookieJar, Cookie
      from urllib.parse import quote
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
      use_bootstrap = (sys.argv[4] if len(sys.argv) > 4 else '1') == '1'
      feed_path = sys.argv[5] if len(sys.argv) > 5 else ''

      def decrypt_cookies_with_domains(db_path, password):
          key = hashlib.pbkdf2_hmac('sha1', password.encode('utf-8'), b'saltysalt', 1003, dklen=16)
          iv = b' ' * 16
          try:
              conn = sqlite3.connect(f'file:{db_path}?mode=ro&immutable=1', uri=True, timeout=5)
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

      def fetch_home_page(jar):
          opener = build_opener(HTTPCookieProcessor(jar))
          req = Request('https://mail.google.com/mail/u/0/')
          req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36')
          try:
              resp = opener.open(req, timeout=30)
              status = resp.getcode()
              body = resp.read()
              return status, body
          except Exception as e:
              return None, str(e)

      def parse_bootstrap_page(html_bytes, max_results):
          try:
              body = html_bytes.decode('utf-8', errors='replace')
          except Exception as e:
              return None, f'HTML decode error: {e}'

          needle = '"a6jdv":[["sils",null,"'
          start = body.find(needle)
          if start < 0:
              return None, 'Bootstrap inbox snapshot not found'

          i = start + len(needle)
          escaped = False
          encoded_chars = []
          while i < len(body):
              ch = body[i]
              if escaped:
                  encoded_chars.append(ch)
                  escaped = False
              elif ch == '\\\\':
                  encoded_chars.append(ch)
                  escaped = True
              elif ch == '"':
                  break
              else:
                  encoded_chars.append(ch)
              i += 1

          try:
              encoded = '"' + ''.join(encoded_chars) + '"'
              decoded = json.loads(encoded)
              parsed = json.loads(decoded)
          except Exception as e:
              return None, f'Bootstrap JSON parse error: {e}'

          if not parsed or not isinstance(parsed, list) or not parsed[0] or not isinstance(parsed[0], list):
              return None, 'Bootstrap inbox snapshot malformed'

          rows = parsed[0][0] if len(parsed[0]) > 0 and isinstance(parsed[0][0], list) else []
          emails = []
          seen_ids = set()

          for row in rows:
              if not isinstance(row, list) or len(row) < 5:
                  continue

              thread_id = row[1] if len(row) > 1 and isinstance(row[1], str) else ''
              subject = row[3] if len(row) > 3 and isinstance(row[3], str) else '(no subject)'
              row_meta = row[4] if isinstance(row[4], list) else []
              row_snippet = row_meta[1] if len(row_meta) > 1 and isinstance(row_meta[1], str) else ''
              row_timestamp = row_meta[2] if len(row_meta) > 2 and isinstance(row_meta[2], (int, float)) else None
              message_rows = row_meta[4] if len(row_meta) > 4 and isinstance(row_meta[4], list) else []

              if not message_rows:
                  if thread_id and thread_id not in seen_ids:
                      seen_ids.add(thread_id)
                      emails.append({
                          'id': thread_id,
                          'from': '',
                          'subject': subject,
                          'snippet': row_snippet,
                          'date': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime((row_timestamp or time.time() * 1000) / 1000.0)),
                          'isUnread': False,
                      })
                  continue

              for message in message_rows:
                  if not isinstance(message, list) or not message:
                      continue

                  msg_id = message[0] if isinstance(message[0], str) else thread_id
                  if not msg_id or msg_id in seen_ids:
                      continue
                  seen_ids.add(msg_id)

                  sender = ''
                  if len(message) > 1 and isinstance(message[1], list):
                      sender_name = message[1][2] if len(message[1]) > 2 and isinstance(message[1][2], str) else ''
                      sender_email = message[1][1] if len(message[1]) > 1 and isinstance(message[1][1], str) else ''
                      sender = f'{sender_name} <{sender_email}>' if sender_name and sender_email else sender_name or sender_email

                  msg_timestamp = message[6] if len(message) > 6 and isinstance(message[6], (int, float)) else row_timestamp
                  snippet = message[9] if len(message) > 9 and isinstance(message[9], str) else row_snippet
                  labels = message[10] if len(message) > 10 and isinstance(message[10], list) else []
                  is_unread = '^u' in labels

                  iso_date = time.strftime(
                      '%Y-%m-%dT%H:%M:%SZ',
                      time.gmtime((msg_timestamp or time.time() * 1000) / 1000.0)
                  )

                  emails.append({
                      'id': msg_id,
                      'from': sender,
                      'subject': subject or '(no subject)',
                      'snippet': snippet or '',
                      'date': iso_date,
                      'isUnread': is_unread,
                  })

                  if len(emails) >= max_results:
                      return emails, None

          return emails[:max_results], None

      def fetch_atom_feed(jar):
          opener = build_opener(HTTPCookieProcessor(jar))
          if feed_path:
              url = f'https://mail.google.com/mail/feed/{feed_path.lstrip("/")}'
          else:
              url = f'https://mail.google.com/mail/feed/atom?q={quote(query)}'
          req = Request(url)
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
                      dedupe_parts = [
                          href,
                          title or '',
                          summary or '',
                          author_name or '',
                          author_email_addr or '',
                          issued or '',
                      ]
                      msg_id = 'atom_' + hashlib.sha1(chr(31).join(dedupe_parts).encode('utf-8')).hexdigest()
              else:
                  dedupe_parts = [
                      title or '',
                      summary or '',
                      author_name or '',
                      author_email_addr or '',
                      issued or '',
                  ]
                  msg_id = 'atom_' + hashlib.sha1(chr(31).join(dedupe_parts).encode('utf-8')).hexdigest()

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
          status, body = fetch_home_page(jar)
          if use_bootstrap and status == 200:
              emails, parse_err = parse_bootstrap_page(body, max_results)
              if not parse_err and emails:
                  print(json.dumps({'ok': True, 'browser': browser['name'], 'source': 'bootstrap', 'emails': emails, 'count': len(emails)}))
                  sys.exit(0)

          status, body = fetch_atom_feed(jar)
          if status == 200:
              emails, parse_err = parse_atom(body, max_results)
              if not parse_err and emails is not None:
                  print(json.dumps({'ok': True, 'browser': browser['name'], 'source': 'atom', 'emails': emails, 'count': len(emails)}))
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
    process.arguments = [
      "-c", pythonScript, configJSON, String(maxResults), query,
      shouldUseBootstrapPage ? "1" : "0",
      feedPath ?? "",
    ]
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
    let errOutput =
      String(data: errPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
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
    let sourceName = json["source"] as? String ?? "atom"
    log("GmailReaderService: Got \(emailDicts.count) emails from \(browserName) via \(sourceName)")

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

  private func fetchGmailViaLabelFeeds(maxResults: Int) throws -> [GmailEmail] {
    guard maxResults > 0 else { return [] }

    let feedPaths = [
      "atom/all",
      "atom/inbox",
      "atom/sent",
      "atom/starred",
      "atom/important",
      "atom/trash",
      "atom/spam",
      "atom/unread",
      "atom/social",
      "atom/promotions",
      "atom/updates",
      "atom/forums",
      "atom/personal",
    ]

    var merged: [String: GmailEmail] = [:]
    for feedPath in feedPaths {
      let feedEmails = try fetchGmailViaAtomFeedSingle(
        maxResults: min(20, maxResults),
        query: "newer_than:1d",
        feedPath: feedPath,
        allowBootstrap: false
      )
      for email in feedEmails {
        let existing = merged[email.id]
        if existing == nil || existing!.date < email.date {
          merged[email.id] = email
        }
      }
    }

    log(
      "GmailReaderService: Collected \(merged.count) unique emails across \(feedPaths.count) label feeds"
    )

    return Array(merged.values)
      .sorted { $0.date > $1.date }
      .prefix(maxResults)
      .map(\.self)
  }

  private func fetchGmailViaDateWindows(daysBack: Int, maxResults: Int) throws -> [GmailEmail] {
    guard maxResults > 0 else { return [] }

    let calendar = Calendar(identifier: .gregorian)
    let now = Date()
    guard
      let tomorrow = calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: now))
    else {
      return try fetchGmailViaAtomFeedSingle(
        maxResults: maxResults, query: "newer_than:\(daysBack)d")
    }

    var collected: [String: GmailEmail] = [:]
    var inspectedWindows = 0
    let windowSpanDays = daysBack > 120 ? 3 : 2
    var remainingDays = max(daysBack, 1)
    var windowEnd = tomorrow

    while remainingDays > 0 && collected.count < maxResults {
      let span = min(windowSpanDays, remainingDays)
      guard let windowStart = calendar.date(byAdding: .day, value: -span, to: windowEnd) else {
        break
      }
      inspectedWindows += 1

      let query = Self.atomDateRangeQuery(start: windowStart, end: windowEnd)
      let slice = try fetchGmailViaAtomFeedSingle(maxResults: min(20, maxResults), query: query)
      for email in slice {
        collected[email.id] = email
      }

      windowEnd = windowStart
      remainingDays -= span
    }

    log(
      "GmailReaderService: Collected \(collected.count) unique emails across \(inspectedWindows) windows"
    )

    return Array(collected.values)
      .sorted { $0.date > $1.date }
      .prefix(maxResults)
      .map(\.self)
  }

  // MARK: - Keychain

  private func getKeychainPassword(service: String) -> String? {
    BrowserKeychainCache.shared.password(for: service) {
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
    let formats = [
      "EEE, dd MMM yyyy HH:mm:ss Z", "dd MMM yyyy HH:mm:ss Z", "yyyy-MM-dd'T'HH:mm:ssZ",
    ]
    for fmt in formats {
      let f = DateFormatter()
      f.dateFormat = fmt
      f.locale = Locale(identifier: "en_US_POSIX")
      if let d = f.date(from: str) { return d }
    }
    return nil
  }

  nonisolated private static func parseNewerThanDays(_ query: String) -> Int? {
    guard let regex = try? NSRegularExpression(pattern: #"newer_than:(\d+)d"#, options: []) else {
      return nil
    }
    let range = NSRange(query.startIndex..., in: query)
    guard let match = regex.firstMatch(in: query, options: [], range: range),
      let daysRange = Range(match.range(at: 1), in: query)
    else {
      return nil
    }
    return Int(query[daysRange])
  }

  nonisolated private static func atomDateRangeQuery(start: Date, end: Date) -> String {
    let formatter = DateFormatter()
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy/MM/dd"
    return "after:\(formatter.string(from: start)) before:\(formatter.string(from: end))"
  }

  nonisolated private static func saveMemory(for email: GmailEmail) async -> Bool {
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
      return true
    } catch {
      log("GmailReaderService: Failed to save memory for email \(email.id): \(error)")
      return false
    }
  }
}
