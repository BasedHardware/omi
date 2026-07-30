import Foundation

// MARK: - Models

struct CalendarEvent: Identifiable {
  let id: String
  let summary: String
  let startTime: String
  let endTime: String
  let attendees: [String]
  let location: String
  let description: String
  let isAllDay: Bool
}

/// Result of a functional connection probe (philosophy §3/§4). Distinct from a
/// stored "connected" flag: it reflects what is true *right now*.
enum CalendarConnectionStatus: Equatable {
  case connected(verifiedAt: Date)
  case needsSignIn(message: String)
  case error(message: String)

  var isConnected: Bool {
    if case .connected = self { return true }
    return false
  }
}

struct CalendarFetchParameters: Equatable {
  let daysBack: Int
  let daysForward: Int
  let maxResults: Int

  static func normalized(daysBack: Int, daysForward: Int, maxResults: Int) -> CalendarFetchParameters {
    CalendarFetchParameters(
      daysBack: min(max(daysBack, 0), 3650),
      daysForward: min(max(daysForward, 0), 3650),
      maxResults: min(max(maxResults, 1), 2500)
    )
  }
}

enum CalendarReaderError: LocalizedError, Equatable {
  case noBrowserFound
  case notSignedIn
  case sessionExpired
  case cookieDecryptionFailed(String)
  case networkError(String)
  case configurationError(String)
  case pythonNotFound

  var errorDescription: String? {
    switch self {
    case .noBrowserFound:
      return "No supported browser found. Open Google Calendar in Chrome, Arc, Brave, or Edge, then try again."
    case .notSignedIn:
      return
        "Not signed into Google in any browser. Open calendar.google.com in Chrome, Arc, Brave, or Edge, sign in, then try again."
    case .sessionExpired:
      return "Your Google session expired. Reload calendar.google.com in your browser to refresh it, then try again."
    case .cookieDecryptionFailed(let msg):
      return "Couldn't read your browser session: \(msg)"
    case .networkError(let msg):
      return "Couldn't reach Google Calendar: \(msg)"
    case .configurationError(let msg):
      return "Couldn't use Google Calendar: \(msg)"
    case .pythonNotFound:
      return "Python 3 not found. Install it via Homebrew: brew install python3"
    }
  }
}

// MARK: - Fetch outcome (pure, testable layer)

/// The classified outcome of a fetch attempt across all browsers/profiles.
///
/// Per `docs/integrations-philosophy.md` §2 (observe → recover, never a script)
/// and §3 (the UI must reflect reality): we aggregate every browser/profile
/// attempt instead of surfacing whichever one happened to be tried last, then
/// classify the failure into an actionable error — never the catch-all
/// "Network error" that a login problem used to render as.
enum CalendarFetchOutcome: Equatable {
  case success(events: [[String: Any]], browser: String)
  case failure(CalendarFailureClass, summary: String, attempts: [CalendarAttempt])

  static func == (lhs: CalendarFetchOutcome, rhs: CalendarFetchOutcome) -> Bool {
    switch (lhs, rhs) {
    case (.success(_, let lb), .success(_, let rb)):
      return lb == rb
    case (.failure(let lc, let ls, let la), .failure(let rc, let rs, let ra)):
      return lc == rc && ls == rs && la == ra
    default:
      return false
    }
  }
}

/// One browser/profile attempt, carrying only non-sensitive diagnostics — names,
/// stages, and reasons, never cookie values (philosophy §7: sanitized traces).
struct CalendarAttempt: Equatable {
  let browser: String
  let stage: String  // "decrypt" | "auth" | "fetch" | "ok"
  let reason: String
  let hadAuthCookies: Bool
}

enum CalendarFailureClass: String, Equatable {
  case noBrowser = "no_browser"
  case notSignedIn = "not_signed_in"
  case sessionExpired = "session_expired"
  case decryptFailed = "decrypt_failed"
  case configuration = "configuration"
  case network = "network"
  case unknown = "unknown"

  var plainFallbackSummary: String {
    switch self {
    case .noBrowser:
      return "No supported browser with a readable session was found."
    case .notSignedIn:
      return "No browser is signed into Google. Sign into calendar.google.com and try again."
    case .sessionExpired:
      return "Your Google session expired. Reload calendar.google.com to refresh it."
    case .decryptFailed:
      return "browser session could not be decrypted"
    case .configuration:
      return "Calendar API key is invalid or unavailable"
    case .network:
      return "please check your connection and try again"
    case .unknown:
      return "unexpected error"
    }
  }

  var asError: CalendarReaderError {
    asError(summary: nil)
  }

  func detailFragment(from summary: String?) -> String? {
    guard let raw = summary?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
      return nil
    }

    switch self {
    case .network:
      let prefix = "Could not reach Google Calendar"
      if raw.hasPrefix(prefix) {
        let tail = String(raw.dropFirst(prefix.count)).trimmingCharacters(in: .whitespaces)
        return tail.isEmpty ? nil : tail
      }
      return raw
    case .decryptFailed:
      if raw == "Your browser session could not be read." {
        return nil
      }
      return raw
    case .noBrowser, .notSignedIn, .sessionExpired:
      return nil
    case .configuration, .unknown:
      return raw
    }
  }

  func asError(summary: String? = nil) -> CalendarReaderError {
    func detailOr(_ fallback: String) -> String {
      detailFragment(from: summary) ?? fallback
    }

    switch self {
    case .noBrowser: return .noBrowserFound
    case .notSignedIn: return .notSignedIn
    case .sessionExpired: return .sessionExpired
    case .decryptFailed:
      return .cookieDecryptionFailed(detailOr("browser session could not be decrypted"))
    case .configuration:
      return .configurationError(detailOr("Calendar API key is invalid or unavailable"))
    case .network:
      return .networkError(detailOr("please check your connection and try again"))
    case .unknown:
      return .networkError(detailOr("unexpected error"))
    }
  }
}

/// Parses the structured JSON the Python helper writes into a classified
/// outcome. Pure and side-effect free so it can be unit-tested against captured
/// payloads without a browser or Python (philosophy §7: make the surface
/// testable).
enum CalendarOutcomeParser {
  static func parse(_ json: [String: Any]) -> CalendarFetchOutcome {
    let attempts = (json["attempts"] as? [[String: Any]] ?? []).map { dict in
      CalendarAttempt(
        browser: dict["browser"] as? String ?? "unknown",
        stage: dict["stage"] as? String ?? "unknown",
        reason: dict["reason"] as? String ?? "",
        hadAuthCookies: dict["had_auth"] as? Bool ?? false
      )
    }

    if json["ok"] as? Bool == true {
      let events = json["events"] as? [[String: Any]] ?? []
      let browser = json["browser"] as? String ?? "unknown"
      return .success(events: events, browser: browser)
    }

    let cls = CalendarFailureClass(rawValue: json["error_class"] as? String ?? "") ?? .unknown
    let summary =
      (json["summary"] as? String).flatMap { $0.isEmpty ? nil : $0 }
      ?? cls.plainFallbackSummary
    return .failure(cls, summary: summary, attempts: attempts)
  }

  /// Human-readable, non-sensitive one-liner for logs and the eval corpus.
  static func diagnosticsLine(_ attempts: [CalendarAttempt]) -> String {
    guard !attempts.isEmpty else { return "no browsers scanned" }
    return attempts.map { "\($0.browser)[\($0.stage):\($0.reason)]" }.joined(separator: ", ")
  }
}

// MARK: - CalendarReaderService

actor CalendarReaderService {
  static let shared = CalendarReaderService()

  /// Read calendar events using browser cookies + SAPISID auth.
  /// Tries Arc, Chrome, Brave, and Edge across all Chromium profiles.
  /// Fetches events from `daysBack` days ago to `daysForward` days from now.
  func readEvents(daysBack: Int = 90, daysForward: Int = 14, maxResults: Int = 200) async throws
    -> [CalendarEvent]
  {
    await APIKeyService.shared.waitForKeys()
    let events = try fetchCalendarViaCookies(
      daysBack: daysBack, daysForward: daysForward, maxResults: maxResults)
    return events.sorted { $0.startTime > $1.startTime }
  }

  /// Lightweight functional probe — does the integration actually work right now?
  ///
  /// Per `docs/integrations-philosophy.md` §3/§4, "connected" must mean "verified
  /// recently against the real surface," never a stored latch. Callers use this
  /// to render honest status and to drive self-healing, rather than trusting a
  /// one-time success. It runs the same real fetch path over a tiny window so a
  /// green result guarantees the whole chain (cookies → auth → API) works.
  func verifyConnection() async -> CalendarConnectionStatus {
    do {
      await APIKeyService.shared.waitForKeys()
      _ = try fetchCalendarViaCookies(daysBack: 1, daysForward: 1, maxResults: 1)
      return .connected(verifiedAt: Date())
    } catch let error as CalendarReaderError {
      switch error {
      case .notSignedIn, .noBrowserFound:
        return .needsSignIn(message: error.errorDescription ?? "Sign into Google to connect.")
      case .sessionExpired:
        return .needsSignIn(message: error.errorDescription ?? "Your Google session expired.")
      default:
        return .error(message: error.errorDescription ?? "Couldn't verify the connection.")
      }
    } catch {
      return .error(message: error.localizedDescription)
    }
  }

  /// Synthesize profile memories and tasks from calendar events.
  /// Uses local LLM (AgentBridge) to extract ~10 memories and 2-3 tasks.
  func synthesizeFromEvents(events: [CalendarEvent]) async -> (
    memories: Int, tasks: Int, profileSummary: String
  ) {
    guard !events.isEmpty else { return (0, 0, "") }

    // Format events compactly for the LLM
    var eventLines: [String] = []
    for event in events {
      var parts = ["[\(event.startTime)] \(event.summary)"]
      if !event.attendees.isEmpty {
        parts.append("With: \(event.attendees.prefix(5).joined(separator: ", "))")
      }
      if !event.location.isEmpty {
        parts.append("Location: \(event.location)")
      }
      if !event.description.isEmpty {
        let desc = String(event.description.prefix(150))
        parts.append("Notes: \(desc)")
      }
      eventLines.append(parts.joined(separator: " | "))
    }
    let eventsText = eventLines.joined(separator: "\n")

    let today = ISO8601DateFormatter().string(from: Date()).prefix(10)
    let synthesisPrompt = """
      Analyze these \(events.count) Google Calendar events and extract profile information about the user.

      CALENDAR EVENTS:
      \(eventsText)

      Today's date: \(today)

      Respond ONLY with valid JSON (no markdown, no code fences):
      {
        "memories": [
          "factual statement about the user based on calendar patterns"
        ],
        "tasks": [
          {"description": "actionable item based on upcoming events", "priority": "high", "due_at": "2026-03-20T09:00:00Z"}
        ],
        "profile": "2-3 sentence summary of who this user is based on their calendar"
      }

      RULES:
      - Extract 10-15 memories (facts about their role, recurring meetings, relationships, routines, interests, work schedule, hobbies, social life). Memories generalize PATTERNS (weekly standups, regular gym, recurring 1-on-1s), not one-off events, in third person ("The user...").
      - Extract 0-3 tasks. A task is a SPECIFIC preparation the user still owes for a real upcoming event: name the event and what's owed ("Prep the demo for Thursday's call with Daniel"), with an ISO date in due_at. Never a vague "follow up" or a task for a past event.
      - Prefer 0 tasks over a weak or generic one. An empty tasks array is correct when nothing genuine is owed.
      - Task priorities: "high", "medium", or "low"
      - Profile should summarize professional identity and schedule patterns
      - Do NOT include sensitive medical, financial, or religious details in tasks
      """

    // Retry the synthesis on transient failure instead of silently dropping the import.
    let maxAttempts = 2
    for attempt in 1...maxAttempts {
      do {
        if ProcessInfo.processInfo.environment["OMI_FORCE_SYNTHESIS_FAIL"] == "1"
          || UserDefaults.standard.bool(forKey: "forceSynthesisFail")
        {
          throw NSError(
            domain: "Synthesis", code: -1, userInfo: [NSLocalizedDescriptionKey: "forced synthesis failure"])
        }
        let result = try await AgentClient.run(
          surface: .service("calendar_reader"),
          prompt: synthesisPrompt,
          model: ModelQoS.Claude.synthesis,
          systemPrompt:
            "You are a profile extraction assistant. Analyze calendar events and output structured JSON. Be concise and factual.",
          onTextDelta: { @Sendable _ in },
          onToolCall: { @Sendable _, _, _ in return "" },
          onToolActivity: { @Sendable _, _, _, _ in }
        )

        var responseText = result.text
        log(
          "CalendarReaderService: Synthesis raw response (\(responseText.count) chars): \(responseText.prefix(300))"
        )

        // Extract JSON from response — handle markdown code fences and leading text
        if let jsonStart = responseText.range(of: "```json") {
          responseText = String(responseText[jsonStart.upperBound...])
          if let jsonEnd = responseText.range(of: "```") {
            responseText = String(responseText[..<jsonEnd.lowerBound])
          }
        } else if let jsonStart = responseText.range(of: "```") {
          responseText = String(responseText[jsonStart.upperBound...])
          if let jsonEnd = responseText.range(of: "```") {
            responseText = String(responseText[..<jsonEnd.lowerBound])
          }
        }
        // Also try finding raw JSON object if there's leading text
        if let braceStart = responseText.firstIndex(of: "{") {
          responseText = String(responseText[braceStart...])
        }
        responseText = responseText.trimmingCharacters(in: .whitespacesAndNewlines)

        guard let jsonData = responseText.data(using: .utf8),
          let parsed = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any]
        else {
          log(
            "CalendarReaderService: Failed to parse synthesis response: \(responseText.prefix(200))")
          return (0, 0, "")
        }

        let memoryStrings = parsed["memories"] as? [String] ?? []
        let taskDicts = parsed["tasks"] as? [[String: Any]] ?? []
        let profileSummary = parsed["profile"] as? String ?? ""

        let artifacts = memoryStrings.map { memory in
          ImportEvidenceBatchItem(
            title: "Calendar Profile Insight",
            snippet: memory,
            content: memory,
            metadata: ["import_kind": "profile"]
          )
        }
        let legacyMemories = memoryStrings.map { memory in
          MemoryBatchItem(
            content: memory,
            tags: ["calendar", "onboarding"],
            headline: "Calendar Profile Insight",
            source: "google_calendar"
          )
        }
        let saveResult = await OnboardingImportEvidenceService.save(
          artifacts,
          sourceType: "google_calendar",
          logPrefix: "CalendarReaderService",
          legacyMemories: legacyMemories
        )

        // Save tasks
        var tasksSaved = 0
        for taskDict in taskDicts {
          guard let description = taskDict["description"] as? String else { continue }
          let priority = taskDict["priority"] as? String ?? "medium"
          let dueAtStr = taskDict["due_at"] as? String
          var dueAt: Date? = nil
          if let dueAtStr = dueAtStr {
            dueAt = ISO8601DateFormatter().date(from: dueAtStr)
          }
          let task = await TasksStore.shared.createTask(
            description: description,
            dueAt: dueAt,
            priority: priority,
            tags: ["calendar", "onboarding"]
          )
          if task != nil { tasksSaved += 1 }
        }

        log(
          "CalendarReaderService: Synthesis complete — \(saveResult.saved) memories, \(tasksSaved) tasks, profile: \(profileSummary.prefix(80))"
        )
        return (saveResult.saved, tasksSaved, profileSummary)

      } catch {
        if attempt < maxAttempts {
          log("CalendarReaderService: Synthesis attempt \(attempt) failed, retrying: \(error)")
          try? await Task.sleep(nanoseconds: 800_000_000)
          continue
        }
        log("CalendarReaderService: Synthesis failed after \(attempt) attempts: \(error)")
        return (0, 0, "")
      }
    }
    return (0, 0, "")
  }

  func saveAsMemories(events: [CalendarEvent], limit: Int? = nil) async -> (saved: Int, failed: Int) {
    let eventsToSave = limit.map { Array(events.prefix($0)) } ?? events
    guard !eventsToSave.isEmpty else { return (0, 0) }

    let artifacts = eventsToSave.map { event in
      var parts = ["Calendar event — \(event.summary)"]
      if !event.startTime.isEmpty {
        parts.append("Starts: \(event.startTime)")
      }
      if !event.location.isEmpty {
        parts.append("Location: \(event.location)")
      }
      if !event.attendees.isEmpty {
        parts.append("With: \(event.attendees.prefix(5).joined(separator: ", "))")
      }

      return ImportEvidenceBatchItem(
        externalId: "google_calendar:\(event.id)",
        title: event.summary,
        snippet: parts.joined(separator: " | "),
        content: parts.joined(separator: " | "),
        metadata: [
          "import_kind": "event",
          "start_time": event.startTime,
          "location": event.location,
        ]
      )
    }
    let legacyMemories = eventsToSave.map { event in
      var parts = ["Calendar event — \(event.summary)"]
      if !event.startTime.isEmpty {
        parts.append("Starts: \(event.startTime)")
      }
      if !event.location.isEmpty {
        parts.append("Location: \(event.location)")
      }
      if !event.attendees.isEmpty {
        parts.append("With: \(event.attendees.prefix(5).joined(separator: ", "))")
      }
      return MemoryBatchItem(
        content: parts.joined(separator: " | "),
        tags: ["calendar", "onboarding", "event"],
        headline: event.summary,
        source: "google_calendar"
      )
    }

    let result = await OnboardingImportEvidenceService.save(
      artifacts,
      sourceType: "google_calendar",
      logPrefix: "CalendarReaderService",
      legacyMemories: legacyMemories
    )
    log("CalendarReaderService: Saved \(result.saved) events as import evidence (\(result.failed) failed)")
    return result
  }

  // MARK: - Python: decrypt cookies + fetch Calendar events via SAPISID auth

  private func fetchCalendarViaCookies(daysBack: Int, daysForward: Int, maxResults: Int) throws
    -> [CalendarEvent]
  {
    let parameters = CalendarFetchParameters.normalized(
      daysBack: daysBack,
      daysForward: daysForward,
      maxResults: maxResults
    )
    guard let calendarKey = getenv("GOOGLE_CALENDAR_API_KEY").flatMap({ String(validatingCString: $0) }),
      !calendarKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      throw CalendarReaderError.configurationError("Calendar API key is unavailable; try again after startup finishes.")
    }

    // Build browser configs as JSON for Python
    // Pass the ORIGINAL db path — Python opens it read-only to avoid WAL/journal corruption from file copy
    let browserConfigs = BrowserGoogleSession.configsForPython(logPrefix: "CalendarReaderService")

    guard !browserConfigs.isEmpty else {
      throw CalendarReaderError.noBrowserFound
    }

    let configJSON: String
    do {
      let data = try JSONSerialization.data(withJSONObject: browserConfigs)
      configJSON = String(data: data, encoding: .utf8) ?? "[]"
    } catch {
      throw CalendarReaderError.networkError("Failed to serialize browser configs")
    }

    // No temp file cleanup needed — we read the original DB directly in read-only mode

    let pythonScript = """
      \(BrowserGoogleSession.chromiumCookiePythonSupport)
      import urllib.request, urllib.error, urllib.parse
      from datetime import datetime, timedelta, timezone

      browsers = json.loads(sys.stdin.read())
      days_back = int(sys.argv[1]) if len(sys.argv) > 1 else 30
      days_forward = int(sys.argv[2]) if len(sys.argv) > 2 else 14
      max_results = int(sys.argv[3]) if len(sys.argv) > 3 else 100

      def get_sapisidhash(sapisid, origin):
          timestamp = str(int(time.time()))
          raw = timestamp + " " + sapisid + " " + origin
          hash_val = hashlib.sha1(raw.encode('utf-8')).hexdigest()
          return "SAPISIDHASH " + timestamp + "_" + hash_val

      def google_error_detail(raw_body):
          try:
              payload = json.loads(raw_body.decode('utf-8', errors='replace'))
              error = payload.get('error', {})
              message = error.get('message') or ''
              status = error.get('status') or ''
              reasons = [
                  e.get('reason', '')
                  for e in error.get('errors', [])
                  if isinstance(e, dict)
              ]
              parts = [p for p in [status, message, ','.join([r for r in reasons if r])] if p]
              return ': '.join(parts) if parts else None
          except Exception:
              return None

      def fetch_calendar_events(jar, days_back, days_forward, max_results):
          # Returns (events, error, http_status). http_status lets the caller
          # distinguish an expired session (401/403) from a transient network
          # failure so the user gets the right recovery step (philosophy §3).
          origin = "https://calendar.google.com"

          now = datetime.now(timezone.utc)
          time_min = (now - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%SZ')
          time_max = (now + timedelta(days=days_forward)).strftime('%Y-%m-%dT%H:%M:%SZ')

          opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
          all_items = []
          page_token = None

          while len(all_items) < max_results:
              page_size = min(2500, max_results - len(all_items))
              url = (
                  f"https://clients6.google.com/calendar/v3/calendars/primary/events"
                  f"?timeMin={time_min}&timeMax={time_max}"
                  f"&singleEvents=true&orderBy=startTime&maxResults={page_size}"
                  f"&key={os.environ.get('GOOGLE_CALENDAR_API_KEY', '')}"
              )
              if page_token:
                  url += f"&pageToken={urllib.parse.quote(page_token)}"

              req = urllib.request.Request(url)
              # The SAPISIDHASH must use the same host-scoped cookie Chrome
              # would send to clients6.google.com. Selecting the first
              # same-named cookie from SQLite can hash a cookie from a
              # different Google host and make a live browser session look
              # expired.
              sapisid = cookie_value_for_request(
                  jar, url, ('SAPISID', '__Secure-3PAPISID'))
              if not sapisid:
                  return None, "No SAPISID cookie applicable to Calendar found", None
              auth_header = get_sapisidhash(sapisid, origin)
              req.add_header('Authorization', auth_header)
              req.add_header('Origin', origin)
              req.add_header('Referer', 'https://calendar.google.com/')
              req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36')
              req.add_header('X-Goog-AuthUser', '0')

              try:
                  resp = opener.open(req, timeout=30)
                  status = resp.getcode()
                  body = resp.read()
                  if status != 200:
                      return None, f"HTTP {status}", status
                  data = json.loads(body)
              except urllib.error.HTTPError as e:
                  detail = google_error_detail(e.read())
                  return None, f"HTTP {e.code}" + (f": {detail}" if detail else ""), e.code
              except Exception as e:
                  return None, str(e), None

              items = data.get('items', [])
              all_items.extend(items)
              page_token = data.get('nextPageToken')
              if not page_token or not items:
                  break

          return all_items[:max_results], None, 200

      # Aggregate every browser/profile attempt instead of last-writer-wins, so
      # we can classify the *most actionable* failure rather than surfacing
      # whichever profile happened to be tried last (philosophy §2, §3, §7).
      attempts = []

      def classify(attempts):
          # No browser produced any readable cookies at all.
          if not attempts:
              return 'no_browser', 'No supported browser with a readable session was found.'
          # API-key/config failures are not user sign-in problems. Google uses
          # 400 for invalid keys and 403 for missing/unregistered callers.
          config_markers = (
              'API key not valid',
              'API key expired',
              'API key is invalid',
              'unregistered callers',
              'API key',
          )
          for a in attempts:
              reason = a.get('reason') or ''
              if a['stage'] == 'fetch' and any(marker in reason for marker in config_markers):
                  return 'configuration', 'Calendar API key is invalid or unavailable.'
          # Session expired beats "not signed in": if any profile HAD auth
          # cookies but Google rejected them, telling the user to re-login is the
          # actionable next step.
          if any(a['stage'] == 'fetch' and a.get('http') in (401, 403) for a in attempts):
              return 'session_expired', 'Your Google session expired. Reload calendar.google.com to refresh it.'
          # Some profile had auth cookies but the fetch failed for another reason.
          if any(a['stage'] == 'fetch' for a in attempts):
              detail = next(a['reason'] for a in attempts if a['stage'] == 'fetch')
              return 'network', f'Could not reach Google Calendar ({detail}).'
          # Cookies decrypted but no profile was signed into Google.
          if any(a['stage'] == 'auth' for a in attempts):
              return 'not_signed_in', 'No browser is signed into Google. Sign into calendar.google.com and try again.'
          # Everything failed at the decrypt stage.
          return 'decrypt_failed', 'Your browser session could not be read.'

      # Try each browser/profile
      for browser in browsers:
          cookies, err = decrypt_google_cookies(browser['db_path'], browser['password'])
          if err or not cookies:
              attempts.append({'browser': browser['name'], 'stage': 'decrypt',
                               'reason': (err or 'no cookies'), 'had_auth': False})
              continue

          # Check for auth cookies
          found_auth = [c for c in cookies if c['name'] in GOOGLE_AUTH_COOKIE_NAMES]
          if not found_auth:
              attempts.append({'browser': browser['name'], 'stage': 'auth',
                               'reason': 'no Google auth cookies', 'had_auth': False})
              continue

          jar = make_cookie_jar(cookies)
          events, fetch_err, http_status = fetch_calendar_events(jar, days_back, days_forward, max_results)
          if fetch_err or events is None:
              attempts.append({'browser': browser['name'], 'stage': 'fetch',
                               'reason': (fetch_err or 'unknown fetch error'),
                               'had_auth': True, 'http': http_status})
              continue

          # Format events for output
          result_events = []
          for ev in events:
              start = ev.get('start', {})
              end = ev.get('end', {})
              attendees = []
              for a in ev.get('attendees', []):
                  if not a.get('self', False):
                      attendees.append(a.get('email', a.get('displayName', '')))

              result_events.append({
                  'id': ev.get('id', ''),
                  'summary': ev.get('summary', 'Untitled'),
                  'start_time': start.get('dateTime', start.get('date', '')),
                  'end_time': end.get('dateTime', end.get('date', '')),
                  'attendees': attendees,
                  'location': ev.get('location', ''),
                  'description': (ev.get('description', '') or '')[:300],
                  'is_all_day': 'date' in start and 'dateTime' not in start,
              })

          attempts.append({'browser': browser['name'], 'stage': 'ok', 'reason': 'ok', 'had_auth': True})
          # Write to temp file to avoid pipe buffer truncation with large event lists
          write_json_result('omi_cal_', {'ok': True, 'browser': browser['name'], 'events': result_events,
                                         'count': len(result_events), 'attempts': attempts})
          sys.exit(0)

      error_class, summary = classify(attempts)
      write_json_result('omi_cal_', {'ok': False, 'error_class': error_class, 'summary': summary,
                                     'attempts': attempts})
      sys.exit(0)
      """

    let result: BrowserPythonRunner.Result
    do {
      result = try BrowserPythonRunner.run(
        script: pythonScript,
        arguments: [
          String(parameters.daysBack), String(parameters.daysForward), String(parameters.maxResults),
        ],
        stdinData: Data(configJSON.utf8)
      )
    } catch BrowserPythonRunnerError.pythonNotFound {
      throw CalendarReaderError.pythonNotFound
    } catch {
      throw CalendarReaderError.networkError(error.localizedDescription)
    }

    let errOutput = String(data: result.stderr, encoding: .utf8) ?? ""
    if !errOutput.isEmpty {
      log("CalendarReaderService: Python stderr: \(errOutput.prefix(500))")
    }

    // Python writes JSON to a temp file and prints the path to stdout
    let outputPath =
      String(data: result.stdout, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
      ?? ""
    guard !outputPath.isEmpty, FileManager.default.fileExists(atPath: outputPath) else {
      throw CalendarReaderError.networkError(
        "Python did not produce output file (stdout: \(outputPath.prefix(200)))")
    }
    defer { try? FileManager.default.removeItem(atPath: outputPath) }

    let output = try Data(contentsOf: URL(fileURLWithPath: outputPath))
    guard let json = try? JSONSerialization.jsonObject(with: output) as? [String: Any] else {
      let raw = String(data: output, encoding: .utf8) ?? "(empty)"
      throw CalendarReaderError.networkError("Python returned invalid JSON: \(raw.prefix(200))")
    }

    let outcome = CalendarOutcomeParser.parse(json)
    switch outcome {
    case .failure(let cls, let summary, let attempts):
      // Structured, non-sensitive diagnostics for the eval corpus (philosophy §7).
      log(
        "CalendarReaderService: fetch failed [\(cls.rawValue)] — \(summary) | "
          + "attempts: \(CalendarOutcomeParser.diagnosticsLine(attempts))")
      throw cls.asError(summary: summary)

    case .success(let eventDicts, let browserName):
      log("CalendarReaderService: Got \(eventDicts.count) events from \(browserName)")
      return eventDicts.compactMap { dict -> CalendarEvent? in
        guard let id = dict["id"] as? String,
          let summary = dict["summary"] as? String
        else { return nil }

        return CalendarEvent(
          id: id,
          summary: summary,
          startTime: dict["start_time"] as? String ?? "",
          endTime: dict["end_time"] as? String ?? "",
          attendees: dict["attendees"] as? [String] ?? [],
          location: dict["location"] as? String ?? "",
          description: dict["description"] as? String ?? "",
          isAllDay: dict["is_all_day"] as? Bool ?? false
        )
      }
    }
  }

}
