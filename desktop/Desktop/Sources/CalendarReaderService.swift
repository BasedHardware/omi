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

enum CalendarReaderError: LocalizedError {
    case noBrowserFound
    case noGoogleCookies
    case cookieDecryptionFailed(String)
    case networkError(String)
    case authFailed
    case pythonNotFound

    var errorDescription: String? {
        switch self {
        case .noBrowserFound:
            return "No browser with Google session found. Log into Google in Chrome, Arc, Brave, or Edge."
        case .noGoogleCookies:
            return "No Google session cookies found. Make sure you're logged into Google."
        case .cookieDecryptionFailed(let msg):
            return "Cookie decryption failed: \(msg)"
        case .networkError(let msg):
            return "Network error: \(msg)"
        case .authFailed:
            return "Google Calendar authentication failed. Try refreshing your Google session in the browser."
        case .pythonNotFound:
            return "Python 3 not found. Install it via Homebrew: brew install python3"
        }
    }
}

// MARK: - Browser Config (same as Gmail)

private struct CalBrowserConfig {
    let name: String
    let keychainService: String
    let cookiePath: String

    static func allBrowsers() -> [CalBrowserConfig] {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return [
            CalBrowserConfig(
                name: "Arc",
                keychainService: "Arc Safe Storage",
                cookiePath: "\(home)/Library/Application Support/Arc/User Data/Default/Cookies"
            ),
            CalBrowserConfig(
                name: "Chrome",
                keychainService: "Chrome Safe Storage",
                cookiePath: "\(home)/Library/Application Support/Google/Chrome/Default/Cookies"
            ),
            CalBrowserConfig(
                name: "Brave",
                keychainService: "Brave Safe Storage",
                cookiePath: "\(home)/Library/Application Support/BraveSoftware/Brave-Browser/Default/Cookies"
            ),
            CalBrowserConfig(
                name: "Edge",
                keychainService: "Microsoft Edge Safe Storage",
                cookiePath: "\(home)/Library/Application Support/Microsoft Edge/Default/Cookies"
            ),
            CalBrowserConfig(
                name: "Vivaldi",
                keychainService: "Vivaldi Safe Storage",
                cookiePath: "\(home)/Library/Application Support/Vivaldi/Default/Cookies"
            ),
        ]
    }
}

// MARK: - CalendarReaderService

actor CalendarReaderService {
    static let shared = CalendarReaderService()

    /// Read calendar events using browser cookies + SAPISID auth.
    /// Tries Arc, Chrome, Brave, Edge, Vivaldi in order.
    /// Fetches events from `daysBack` days ago to `daysForward` days from now.
    func readEvents(daysBack: Int = 90, daysForward: Int = 14, maxResults: Int = 200) async throws -> [CalendarEvent] {
        let events = try fetchCalendarViaCookies(daysBack: daysBack, daysForward: daysForward, maxResults: maxResults)
        return events.sorted { $0.startTime > $1.startTime }
    }

    /// Synthesize profile memories and tasks from calendar events.
    /// Uses local LLM (ACPBridge) to extract ~10 memories and 2-3 tasks.
    func synthesizeFromEvents(events: [CalendarEvent]) async -> (memories: Int, tasks: Int, profileSummary: String) {
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
        - Extract 10-15 memories (facts about their role, recurring meetings, relationships, routines, interests, work schedule, hobbies, social life)
        - Extract 3-5 tasks (upcoming preparation, follow-ups, deadlines from future events)
        - Focus on PATTERNS (weekly standups, regular gym, recurring 1-on-1s) not one-off events
        - Each memory should be a single clear factual statement in third person ("The user...")
        - Tasks should only reference FUTURE events with ISO date in due_at
        - Task priorities: "high", "medium", or "low"
        - Profile should summarize professional identity and schedule patterns
        - Do NOT include raw event details — synthesize and generalize
        - Do NOT include sensitive medical or financial details
        """

        do {
            let bridge = ACPBridge(passApiKey: true)
            try await bridge.start()
            defer { Task { await bridge.stop() } }

            let result = try await bridge.query(
                prompt: synthesisPrompt,
                systemPrompt:
                    "You are a profile extraction assistant. Analyze calendar events and output structured JSON. Be concise and factual.",
                model: "claude-opus-4-6",
                onTextDelta: { @Sendable _ in },
                onToolCall: { @Sendable _, _, _ in return "" },
                onToolActivity: { @Sendable _, _, _, _ in }
            )

            var responseText = result.text
            log("CalendarReaderService: Synthesis raw response (\(responseText.count) chars): \(responseText.prefix(300))")

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
                log("CalendarReaderService: Failed to parse synthesis response: \(responseText.prefix(200))")
                return (0, 0, "")
            }

            let memoryStrings = parsed["memories"] as? [String] ?? []
            let taskDicts = parsed["tasks"] as? [[String: Any]] ?? []
            let profileSummary = parsed["profile"] as? String ?? ""

            // Save memories
            var memoriesSaved = 0
            for memory in memoryStrings {
                do {
                    _ = try await APIClient.shared.createMemory(
                        content: memory,
                        visibility: "private",
                        tags: ["calendar", "onboarding", "profile"],
                        source: "google_calendar",
                        headline: "Calendar Profile Insight"
                    )
                    memoriesSaved += 1
                } catch {
                    log("CalendarReaderService: Failed to save memory: \(error)")
                }
            }

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
                "CalendarReaderService: Synthesis complete — \(memoriesSaved) memories, \(tasksSaved) tasks, profile: \(profileSummary.prefix(80))"
            )
            return (memoriesSaved, tasksSaved, profileSummary)

        } catch {
            log("CalendarReaderService: Synthesis failed: \(error)")
            return (0, 0, "")
        }
    }

    // MARK: - Python: decrypt cookies + fetch Calendar events via SAPISID auth

    private func fetchCalendarViaCookies(daysBack: Int, daysForward: Int, maxResults: Int) throws -> [CalendarEvent] {
        // Build browser configs as JSON for Python
        // Pass the ORIGINAL db path — Python opens it read-only to avoid WAL/journal corruption from file copy
        var browserConfigs: [[String: String]] = []
        for browser in CalBrowserConfig.allBrowsers() {
            guard FileManager.default.fileExists(atPath: browser.cookiePath) else { continue }
            guard let password = getKeychainPassword(service: browser.keychainService) else { continue }

            browserConfigs.append([
                "name": browser.name,
                "db_path": browser.cookiePath,
                "password": password,
            ])
        }

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
import sys, json, os, sqlite3, hashlib, time, urllib.request, urllib.error
from http.cookiejar import MozillaCookieJar, Cookie
from datetime import datetime, timedelta, timezone

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
days_back = int(sys.argv[2]) if len(sys.argv) > 2 else 30
days_forward = int(sys.argv[3]) if len(sys.argv) > 3 else 14
max_results = int(sys.argv[4]) if len(sys.argv) > 4 else 100

def decrypt_cookies(db_path, password):
    key = hashlib.pbkdf2_hmac('sha1', password.encode('utf-8'), b'saltysalt', 1003, dklen=16)
    iv = b' ' * 16
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro&immutable=1', uri=True, timeout=5)
        c = conn.cursor()
        c.execute('SELECT value FROM meta WHERE key="version"')
        row = c.fetchone()
        db_version = int(row[0]) if row else 0
        c.execute("SELECT host_key, name, encrypted_value, path, is_secure, expires_utc FROM cookies WHERE host_key LIKE '%google.com%'")
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

def get_sapisidhash(sapisid, origin):
    timestamp = str(int(time.time()))
    raw = timestamp + " " + sapisid + " " + origin
    hash_val = hashlib.sha1(raw.encode('utf-8')).hexdigest()
    return "SAPISIDHASH " + timestamp + "_" + hash_val

def fetch_calendar_events(jar, cookies_list, days_back, days_forward, max_results):
    # Find SAPISID cookie
    sapisid = None
    for c in cookies_list:
        if c['name'] == 'SAPISID':
            sapisid = c['value']
            break
    if not sapisid:
        # Try __Secure-3PAPISID
        for c in cookies_list:
            if c['name'] == '__Secure-3PAPISID':
                sapisid = c['value']
                break
    if not sapisid:
        return None, "No SAPISID cookie found"

    origin = "https://calendar.google.com"
    auth_header = get_sapisidhash(sapisid, origin)

    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%SZ')
    time_max = (now + timedelta(days=days_forward)).strftime('%Y-%m-%dT%H:%M:%SZ')

    url = (
        f"https://clients6.google.com/calendar/v3/calendars/primary/events"
        f"?timeMin={time_min}&timeMax={time_max}"
        f"&singleEvents=true&orderBy=startTime&maxResults={max_results}"
        f"&key={os.environ.get('GOOGLE_CALENDAR_API_KEY', '')}"
    )

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    req = urllib.request.Request(url)
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
            return None, f"HTTP {status}"
        data = json.loads(body)
        return data.get('items', []), None
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')[:200] if e.fp else ''
        return None, f"HTTP {e.code}: {body}"
    except Exception as e:
        return None, str(e)

# Try each browser
for browser in browsers:
    cookies, err = decrypt_cookies(browser['db_path'], browser['password'])
    if err or not cookies:
        continue

    # Check for auth cookies
    auth_names = {'SID', 'HSID', 'SSID', 'APISID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID'}
    found_auth = [c for c in cookies if c['name'] in auth_names]
    if not found_auth:
        continue

    jar = make_cookie_jar(cookies)
    events, fetch_err = fetch_calendar_events(jar, cookies, days_back, days_forward, max_results)
    if fetch_err or events is None:
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

    # Write to temp file to avoid pipe buffer truncation with large event lists
    import tempfile
    outfile = tempfile.mktemp(suffix='.json', prefix='omi_cal_')
    with open(outfile, 'w') as f:
        json.dump({'ok': True, 'browser': browser['name'], 'events': result_events, 'count': len(result_events)}, f)
    print(outfile)
    sys.exit(0)

import tempfile
outfile = tempfile.mktemp(suffix='.json', prefix='omi_cal_')
with open(outfile, 'w') as f:
    json.dump({'ok': False, 'error': 'No browser with valid Google session found'}, f)
print(outfile)
sys.exit(0)
"""

        // Find Python
        let pythonPaths = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
        guard let pythonPath = pythonPaths.first(where: { FileManager.default.fileExists(atPath: $0) })
        else {
            throw CalendarReaderError.pythonNotFound
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = [
            "-c", pythonScript, configJSON,
            String(daysBack), String(daysForward), String(maxResults),
        ]
        let pipe = Pipe()
        let errPipe = Pipe()
        process.standardOutput = pipe
        process.standardError = errPipe

        // Read pipe data asynchronously to avoid deadlock
        // (waitUntilExit blocks if pipe buffers are full)
        var outputData = Data()
        var errData = Data()
        let outputSem = DispatchSemaphore(value: 0)
        let errSem = DispatchSemaphore(value: 0)
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let d = handle.availableData
            if d.isEmpty {
                pipe.fileHandleForReading.readabilityHandler = nil
                outputSem.signal()
            } else {
                outputData.append(d)
            }
        }
        errPipe.fileHandleForReading.readabilityHandler = { handle in
            let d = handle.availableData
            if d.isEmpty {
                errPipe.fileHandleForReading.readabilityHandler = nil
                errSem.signal()
            } else {
                errData.append(d)
            }
        }

        do {
            try process.run()
            // Timeout after 60 seconds
            DispatchQueue.global().asyncAfter(deadline: .now() + .seconds(60)) {
                if process.isRunning { process.terminate() }
            }
            process.waitUntilExit()
        } catch {
            throw CalendarReaderError.networkError("Failed to run Python: \(error.localizedDescription)")
        }

        // Wait for pipe reads to finish (max 5s after process exit)
        _ = outputSem.wait(timeout: .now() + .seconds(5))
        _ = errSem.wait(timeout: .now() + .seconds(5))

        let errOutput = String(data: errData, encoding: .utf8) ?? ""
        if !errOutput.isEmpty {
            log("CalendarReaderService: Python stderr: \(errOutput.prefix(500))")
        }

        // Python writes JSON to a temp file and prints the path to stdout
        let outputPath = String(data: outputData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !outputPath.isEmpty, FileManager.default.fileExists(atPath: outputPath) else {
            throw CalendarReaderError.networkError("Python did not produce output file (stdout: \(outputPath.prefix(200)))")
        }
        defer { try? FileManager.default.removeItem(atPath: outputPath) }

        let output = try Data(contentsOf: URL(fileURLWithPath: outputPath))
        guard let json = try? JSONSerialization.jsonObject(with: output) as? [String: Any] else {
            let raw = String(data: output, encoding: .utf8) ?? "(empty)"
            throw CalendarReaderError.networkError("Python returned invalid JSON: \(raw.prefix(200))")
        }

        guard json["ok"] as? Bool == true else {
            let errMsg = json["error"] as? String ?? "Unknown error"
            throw CalendarReaderError.networkError(errMsg)
        }

        guard let eventDicts = json["events"] as? [[String: Any]] else {
            return []
        }

        let browserName = json["browser"] as? String ?? "unknown"
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

    // MARK: - Keychain

    private func getKeychainPassword(service: String) -> String? {
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
