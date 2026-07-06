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
  case provider(GmailFailureClass, message: String)
  case helper(message: String)
  case pythonNotFound

  var errorDescription: String? {
    switch self {
    case .provider(_, let message), .helper(let message):
      return message
    case .pythonNotFound:
      return "Python 3 not found. Install it via Homebrew: brew install python3"
    }
  }

  var failureClass: GmailFailureClass? {
    if case .provider(let cls, _) = self { return cls }
    return nil
  }

  var needsSignIn: Bool {
    failureClass?.needsSignIn == true
  }

  var classification: String {
    switch self {
    case .provider(let cls, _):
      return cls.rawValue
    case .helper:
      return "helper_failed"
    case .pythonNotFound:
      return "python_not_found"
    }
  }
}

enum GmailConnectionStatus: Equatable {
  case connected(verifiedAt: Date)
  case needsSignIn(message: String)
  case error(message: String)

  var isConnected: Bool {
    if case .connected = self { return true }
    return false
  }
}

enum GmailFetchOutcome: Equatable {
  case success(emails: [[String: Any]], browser: String, source: String)
  case failure(GmailFailureClass, summary: String, attempts: [GmailAttempt])

  static func == (lhs: GmailFetchOutcome, rhs: GmailFetchOutcome) -> Bool {
    switch (lhs, rhs) {
    case let (.success(_, lb, ls), .success(_, rb, rs)):
      return lb == rb && ls == rs
    case let (.failure(lc, ls, la), .failure(rc, rs, ra)):
      return lc == rc && ls == rs && la == ra
    default:
      return false
    }
  }
}

struct GmailAttempt: Equatable {
  let browser: String
  let stage: String
  let reason: String
  let hadAuthCookies: Bool
}

enum GmailFailureClass: String, Equatable {
  case noBrowser = "no_browser"
  case notSignedIn = "not_signed_in"
  case sessionExpired = "session_expired"
  case decryptFailed = "decrypt_failed"
  case network = "network"
  case unknown = "unknown"

  var needsSignIn: Bool {
    switch self {
    case .noBrowser, .notSignedIn, .sessionExpired:
      return true
    case .decryptFailed, .network, .unknown:
      return false
    }
  }

  var defaultMessage: String {
    switch self {
    case .noBrowser:
      return "Open Gmail in Chrome, Arc, Brave, or Edge and sign in, then try again."
    case .notSignedIn:
      return "This account isn't signed into Gmail. Sign in through your browser, then try again."
    case .sessionExpired:
      return "This account's Gmail sign-in has expired. Reload Gmail in your browser, then try again."
    case .decryptFailed:
      return "Could not connect this account. Make sure it is signed in and reload Gmail in your browser, then try again."
    case .network:
      return "Couldn't reach Gmail. Check your connection and try again."
    case .unknown:
      return "Couldn't read Gmail. Try again."
    }
  }
}

enum GmailOutcomeParser {
  static func parse(_ json: [String: Any]) -> GmailFetchOutcome {
    let attempts = (json["attempts"] as? [[String: Any]] ?? []).map { dict in
      GmailAttempt(
        browser: dict["browser"] as? String ?? "unknown",
        stage: dict["stage"] as? String ?? "unknown",
        reason: dict["reason"] as? String ?? "",
        hadAuthCookies: dict["had_auth"] as? Bool ?? false
      )
    }

    if json["ok"] as? Bool == true {
      let emails = json["emails"] as? [[String: Any]] ?? []
      let browser = json["browser"] as? String ?? "unknown"
      let source = json["source"] as? String ?? "unknown"
      return .success(emails: emails, browser: browser, source: source)
    }

    let cls = GmailFailureClass(rawValue: json["error_class"] as? String ?? "") ?? .unknown
    let summary =
      (json["summary"] as? String).flatMap { $0.isEmpty ? nil : $0 }
      ?? cls.defaultMessage
    return .failure(cls, summary: summary, attempts: attempts)
  }

  static func diagnosticsLine(_ attempts: [GmailAttempt]) -> String {
    guard !attempts.isEmpty else { return "no browsers scanned" }
    return attempts.map { "\($0.browser)[\($0.stage):\($0.reason)]" }.joined(separator: ", ")
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
      let queryEmails = try fetchGmailViaAtomFeedSingle(
        maxResults: maxResults,
        query: query,
        feedPath: nil,
        allowBootstrap: false
      )
      let labelEmails = try fetchGmailViaLabelFeeds(maxResults: maxResults, query: query)
      var merged: [String: GmailEmail] = [:]
      for email in queryEmails + labelEmails {
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

  func verifyConnection() async -> GmailConnectionStatus {
    do {
      _ = try fetchGmailViaAtomFeedSingle(
        maxResults: 1,
        query: "newer_than:1d",
        feedPath: "atom/inbox",
        allowBootstrap: false
      )
      return .connected(verifiedAt: Date())
    } catch let error as GmailReaderError {
      let message = error.errorDescription ?? "Couldn't verify the connection."
      if error.needsSignIn {
        return .needsSignIn(message: message)
      }
      return .error(message: message)
    } catch {
      return .error(message: error.localizedDescription)
    }
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

    // Retry the synthesis on transient failure instead of silently dropping the import.
    let maxAttempts = 2
    for attempt in 1...maxAttempts {
    do {
      if ProcessInfo.processInfo.environment["OMI_FORCE_SYNTHESIS_FAIL"] == "1"
        || UserDefaults.standard.bool(forKey: "forceSynthesisFail") {
        throw NSError(domain: "Synthesis", code: -1, userInfo: [NSLocalizedDescriptionKey: "forced synthesis failure"])
      }
      let result = try await AgentClient.run(
        surface: .service("gmail_reader"),
        prompt: synthesisPrompt,
        model: ModelQoS.Claude.synthesis,
        systemPrompt:
          "You are a profile extraction assistant. Output ONLY valid JSON. No markdown, no code fences, no explanation.",
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

      let artifacts = memoryStrings.map { memory in
        ImportEvidenceBatchItem(
            title: "Email Profile Insight",
            snippet: memory,
            content: memory,
            metadata: ["import_kind": "profile"]
        )
      }
      let legacyMemories = memoryStrings.map { memory in
        MemoryBatchItem(
          content: memory,
          tags: ["gmail", "onboarding"],
          headline: "Email Profile Insight",
          source: "gmail"
        )
      }
      let saveResult = await OnboardingImportEvidenceService.save(
        artifacts,
        sourceType: "gmail",
        logPrefix: "GmailReaderService",
        legacyMemories: legacyMemories
      )

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
        "GmailReaderService: Synthesis complete — \(saveResult.saved) memories, \(tasksSaved) tasks"
      )
      return (saveResult.saved, tasksSaved, profileSummary)

    } catch {
      if attempt < maxAttempts {
        log("GmailReaderService: Synthesis attempt \(attempt) failed, retrying: \(error)")
        try? await Task.sleep(nanoseconds: 800_000_000)
        continue
      }
      log("GmailReaderService: Synthesis failed after \(attempt) attempts: \(error)")
      return (0, 0, "")
    }
    }
    return (0, 0, "")
  }

  /// Save fetched emails as memories via the OMI backend API.
  func saveAsMemories(emails: [GmailEmail]) async -> (saved: Int, failed: Int) {
    guard !emails.isEmpty else { return (0, 0) }

    let artifacts = emails.map { email in
      let dateStr = email.date.formatted(date: .abbreviated, time: .shortened)
      let senderName =
        email.from.components(separatedBy: "<").first?.trimmingCharacters(in: .whitespaces)
        ?? email.from
      let content = "Email from \(senderName) — \"\(email.subject)\": \(email.snippet)"

      return ImportEvidenceBatchItem(
        externalId: "gmail:\(email.id)",
        occurredAt: email.date,
        title: email.subject,
        snippet: email.snippet,
        content: content,
        metadata: [
          "import_kind": "email",
          "from": email.from,
          "window_title": "Gmail — \(dateStr)",
        ]
      )
    }
    let legacyMemories = emails.map { email in
      let dateStr = email.date.formatted(date: .abbreviated, time: .shortened)
      let senderName =
        email.from.components(separatedBy: "<").first?.trimmingCharacters(in: .whitespaces)
        ?? email.from
      let content = "Email from \(senderName) — \"\(email.subject)\": \(email.snippet)"
      return MemoryBatchItem(
        content: content,
        tags: ["gmail", "onboarding", "email"],
        headline: email.subject,
        source: "gmail",
        windowTitle: "Gmail — \(dateStr)"
      )
    }

    let result = await OnboardingImportEvidenceService.save(
      artifacts,
      sourceType: "gmail",
      logPrefix: "GmailReaderService",
      legacyMemories: legacyMemories
    )
    log("GmailReaderService: Saved \(result.saved) emails as import evidence (\(result.failed) failed)")
    return result
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

    let browserConfigs = BrowserGoogleSession.configsForPython(logPrefix: "GmailReaderService")

    guard !browserConfigs.isEmpty else {
      throw GmailReaderError.provider(.noBrowser, message: GmailFailureClass.noBrowser.defaultMessage)
    }

    let configJSON: String
    do {
      let data = try JSONSerialization.data(withJSONObject: browserConfigs)
      configJSON = String(data: data, encoding: .utf8) ?? "[]"
    } catch {
      throw GmailReaderError.helper(message: "Couldn't prepare Gmail import. Try again.")
    }

    let pythonScript = """
      \(BrowserGoogleSession.chromiumCookiePythonSupport)
      import xml.etree.ElementTree as ET
      from urllib.parse import quote, urlparse
      from urllib.request import Request, build_opener, HTTPCookieProcessor
      from urllib.error import HTTPError

      browsers = json.loads(sys.stdin.read())
      max_results = int(sys.argv[1]) if len(sys.argv) > 1 else 50
      query = sys.argv[2] if len(sys.argv) > 2 else 'newer_than:1d'
      use_bootstrap = (sys.argv[3] if len(sys.argv) > 3 else '1') == '1'
      feed_path = sys.argv[4] if len(sys.argv) > 4 else ''

      def http_get(opener, url):
          # Returns (status, final_url, body). opener.open raises HTTPError for
          # non-2xx (e.g. 401/403 on an expired session); we catch it and keep the
          # real status + body so auth failures are not mislabeled as network
          # errors. Only a genuine connectivity failure (URLError: DNS, timeout,
          # refused) yields a None status.
          req = Request(url)
          req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36')
          try:
              resp = opener.open(req, timeout=30)
              return resp.getcode(), resp.geturl(), resp.read()
          except HTTPError as e:
              try:
                  body = e.read()
              except Exception:
                  body = b''
              final = e.geturl() if hasattr(e, 'geturl') else url
              return e.code, final, body
          except Exception as e:
              return None, None, str(e).encode('utf-8', 'replace')

      def fetch_home_page(jar):
          opener = build_opener(HTTPCookieProcessor(jar))
          return http_get(opener, 'https://mail.google.com/mail/u/0/')

      def is_mail_google_url(url):
          try:
              host = (urlparse(url).hostname or '').lower()
          except Exception:
              return False
          return host == 'mail.google.com' or host.endswith('.mail.google.com')

      def is_login_redirect(final_url):
          if not final_url:
              return False
          return not is_mail_google_url(final_url)

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
              if query:
                  separator = '&' if '?' in url else '?'
                  url = f'{url}{separator}q={quote(query)}'
          else:
              url = f'https://mail.google.com/mail/feed/atom?q={quote(query)}'
          return http_get(opener, url)

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

      attempts = []

      def classify(attempts):
          if not attempts:
              return 'no_browser', 'No supported browser with a readable Gmail session was found.'
          fetches = [a for a in attempts if a['stage'] == 'fetch']
          if fetches:
              # Only a confirmed auth failure — an explicit 401/403, or Gmail
              # bouncing us to a sign-in page — means the sign-in expired.
              if any(a.get('http') in (401, 403) or a.get('login_redirect') for a in fetches):
                  return 'session_expired', 'This account is signed out of Gmail or its session expired. Reload Gmail in the browser, then try again.'
              # Anything else (no response, 429, 5xx, or an unexpected body) is not
              # an auth problem — we can't confirm the sign-in expired, so treat it
              # as a transient reach/read failure the user can just retry rather
              # than telling them to sign in again.
              return 'network', 'Could not reach Gmail. Check your connection and try again.'
          if any(a['stage'] == 'auth' for a in attempts):
              return 'not_signed_in', 'This account is not signed into Gmail in the browser. Sign in, then try again.'
          # decrypt-stage failures collapse several distinct causes — split them
          # by the recorded reason so the message is accurate, not a catch-all.
          decrypt_reasons = ' '.join((a.get('reason') or '').lower() for a in attempts if a['stage'] == 'decrypt')
          if 'locked' in decrypt_reasons or 'busy' in decrypt_reasons:
              return 'decrypt_failed', 'Your browser is busy right now. Wait a moment, then try again.'
          if 'no cookies' in decrypt_reasons:
              return 'not_signed_in', 'This account is not signed into Gmail. Sign in through your browser, then try again.'
          return 'decrypt_failed', 'Could not connect this account. Make sure it is signed in and reload Gmail in your browser, then try again.'

      # Try each browser/profile and keep every non-sensitive attempt.
      for browser in browsers:
          cookies, err = decrypt_google_cookies(browser['db_path'], browser['password'], include_gmail_hosts=True)
          if err or not cookies:
              attempts.append({'browser': browser['name'], 'stage': 'decrypt',
                               'reason': (err or 'no cookies'), 'had_auth': False})
              continue

          found_auth = [c for c in cookies if c['name'] in GOOGLE_AUTH_COOKIE_NAMES]
          if not found_auth:
              attempts.append({'browser': browser['name'], 'stage': 'auth',
                               'reason': 'no Google auth cookies', 'had_auth': False})
              continue

          jar = make_cookie_jar(cookies)

          # Atom feed first: ~16 KB, returns recent messages in ~0.4 s, and a
          # valid session (even an empty inbox) counts as success. This is the
          # fast path. The ~3 MB Gmail home page is only fetched as a fallback
          # below, so a normal Connect no longer waits several seconds on it.
          status, final, body = fetch_atom_feed(jar)
          if status == 200:
              emails, parse_err = parse_atom(body, max_results)
              if not parse_err and emails is not None:
                  attempts.append({'browser': browser['name'], 'stage': 'ok', 'reason': 'ok', 'had_auth': True})
                  write_json_result('omi_gmail_', {'ok': True, 'browser': browser['name'], 'source': 'atom',
                                                   'emails': emails, 'count': len(emails), 'attempts': attempts})
                  sys.exit(0)
          # A redirect off the mail.google.com host means Gmail bounced us to sign-in.
          login_redirect = is_login_redirect(final)
          reason = f'HTTP {status}' if status else 'no HTTP response'
          attempts.append({'browser': browser['name'], 'stage': 'fetch',
                           'reason': reason, 'had_auth': True,
                           'http': status, 'login_redirect': login_redirect})

          # Fallback to the richer bootstrap home page only when the atom result
          # was ambiguous. A definitive 401/403 is already an auth failure, so we
          # skip the heavy download in that case and fail fast.
          if use_bootstrap and status not in (401, 403):
              status, final, body = fetch_home_page(jar)
              if status == 200:
                  emails, parse_err = parse_bootstrap_page(body, max_results)
                  if not parse_err and emails:
                      attempts.append({'browser': browser['name'], 'stage': 'ok', 'reason': 'ok', 'had_auth': True})
                      write_json_result('omi_gmail_', {'ok': True, 'browser': browser['name'], 'source': 'bootstrap',
                                                       'emails': emails, 'count': len(emails), 'attempts': attempts})
                      sys.exit(0)
              login_redirect = is_login_redirect(final)
              reason = f'HTTP {status}' if status else 'no HTTP response'
              attempts.append({'browser': browser['name'], 'stage': 'fetch',
                               'reason': reason, 'had_auth': True,
                               'http': status, 'login_redirect': login_redirect})

      error_class, summary = classify(attempts)
      write_json_result('omi_gmail_', {'ok': False, 'error_class': error_class, 'summary': summary,
                                       'attempts': attempts})
      sys.exit(0)
      """

    let result: BrowserPythonRunner.Result
    do {
      result = try BrowserPythonRunner.run(
        script: pythonScript,
        arguments: [
          String(maxResults), query,
          shouldUseBootstrapPage ? "1" : "0",
          feedPath ?? "",
        ],
        stdinData: Data(configJSON.utf8)
      )
    } catch BrowserPythonRunnerError.pythonNotFound {
      throw GmailReaderError.pythonNotFound
    } catch {
      throw GmailReaderError.helper(message: "Couldn't read Gmail. Try again.")
    }

    let errOutput = String(data: result.stderr, encoding: .utf8) ?? ""
    if !errOutput.isEmpty {
      log("GmailReaderService: Python stderr: \(errOutput.prefix(500))")
    }

    let outputPath =
      String(data: result.stdout, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
      ?? ""
    guard !outputPath.isEmpty, FileManager.default.fileExists(atPath: outputPath) else {
      throw GmailReaderError.helper(message: "Couldn't read Gmail. Try again.")
    }
    defer { try? FileManager.default.removeItem(atPath: outputPath) }

    let output = try Data(contentsOf: URL(fileURLWithPath: outputPath))
    guard let json = try? JSONSerialization.jsonObject(with: output) as? [String: Any] else {
      throw GmailReaderError.helper(message: "Couldn't read Gmail. Try again.")
    }

    let outcome = GmailOutcomeParser.parse(json)
    let emailDicts: [[String: Any]]
    switch outcome {
    case let .failure(cls, summary, attempts):
      log(
        "GmailReaderService: fetch failed [\(cls.rawValue)] — \(summary) | "
          + "attempts: \(GmailOutcomeParser.diagnosticsLine(attempts))")
      throw GmailReaderError.provider(cls, message: summary)
    case let .success(emails, browserName, sourceName):
      log("GmailReaderService: Got \(emails.count) emails from \(browserName) via \(sourceName)")
      emailDicts = emails
    }

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

  private func fetchGmailViaLabelFeeds(maxResults: Int, query: String) throws -> [GmailEmail] {
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
        query: query,
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

}
