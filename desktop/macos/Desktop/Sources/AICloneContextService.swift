import Foundation

/// Live "world knowledge" for AI Clone reply generation: a compact block of the user's
/// saved Memories (real facts about their life) and — when the incoming message looks
/// scheduling-related — their real upcoming calendar, so the clone answers availability
/// questions from actual data instead of hallucinating.
///
/// Strictly read-only and strictly additive: this service only produces context strings
/// for `AIClonePersonaService.respond()`. It never writes to any calendar, never touches
/// send-mode routing or the pause switch, and a failed/empty fetch yields `nil` so the
/// reply generates exactly as it did without enrichment.
actor AICloneContextService {
  static let shared = AICloneContextService()

  // Bounds — the enrichment must stay a short block, not a data dump.
  static let maxMemories = 12
  static let maxMemoryChars = 160
  static let maxCalendarEvents = 25
  static let calendarDaysForward = 14

  // Both fetches are expensive (network call / cookie-decrypting Python subprocess), so
  // results — including failures — are cached briefly. Caching nil doubles as a failure
  // cooldown: a machine with no Google session doesn't re-spawn Python per message.
  private var memoryCache: (block: String?, fetchedAt: Date)?
  private var calendarCache: (block: String?, fetchedAt: Date)?
  private let memoryTTL: TimeInterval = 15 * 60
  private let calendarTTL: TimeInterval = 10 * 60

  // MARK: - Memories

  /// Compact background-facts block from the user's saved Memories, or nil when
  /// unavailable (fetch failed, signed out, no memories). Never throws.
  func memoryContext() async -> String? {
    if let cache = memoryCache, Date().timeIntervalSince(cache.fetchedAt) < memoryTTL {
      return cache.block
    }
    var block: String?
    if let fixture = Self.loadFixtureStrings(key: "aiCloneMemoriesFixturePath") {
      block = Self.renderMemoryBlock(fixture)
    } else {
      do {
        let memories = try await APIClient.shared.getMemories(limit: 60)
        // Tips are advice ("you should…"), not facts about the user — skip them.
        block = Self.renderMemoryBlock(memories.filter { !$0.isTip }.map(\.content))
      } catch {
        log("AICloneContextService: memory fetch failed (replying without): \(error)")
        block = nil
      }
    }
    memoryCache = (block, Date())
    return block
  }

  /// Pure renderer so bounds/wording are unit-testable. Returns nil for no usable facts.
  static func renderMemoryBlock(_ contents: [String]) -> String? {
    let facts = contents
      .map { $0.replacingOccurrences(of: "\n", with: " ").trimmingCharacters(in: .whitespaces) }
      .filter { !$0.isEmpty }
      .prefix(maxMemories)
      .map { "- \(String($0.prefix(maxMemoryChars)))" }
    guard !facts.isEmpty else { return nil }
    return """
      BACKGROUND FACTS ABOUT YOU (real, from your saved memories):
      \(facts.joined(separator: "\n"))
      These are silent background knowledge, NOT things to bring up. Use one ONLY to answer \
      correctly when the other person's message directly asks about it. NEVER introduce a fact \
      from this list on your own, never turn one into a new topic or agenda to "keep the \
      conversation going", never list or show them off, and never mention "memories", "notes", \
      or where you know something from. If the current message doesn't touch any of these, reply \
      as if this list didn't exist.
      """
  }

  // MARK: - Calendar

  /// Real-availability block for the next `calendarDaysForward` days, or nil when the
  /// calendar can't be read (no browser Google session, fetch error). Never throws.
  /// An empty-but-successful fetch still returns a block — "no commitments" is real data.
  func calendarContext(now: Date = Date()) async -> String? {
    if let cache = calendarCache, now.timeIntervalSince(cache.fetchedAt) < calendarTTL {
      return cache.block
    }
    var block: String?
    if let fixture = Self.loadFixtureEvents() {
      block = Self.renderCalendarBlock(events: fixture, now: now)
    } else {
      // Hard deadline on the whole fetch: cookie decryption can stall on keychain
      // prompts, and a reply must never wait on that. Timeout/failure → no block.
      let events = await Self.withTimeout(seconds: 45) {
        try await CalendarReaderService.shared.readEvents(
          daysBack: 1, daysForward: Self.calendarDaysForward, maxResults: 150)
      }
      if let events {
        block = Self.renderCalendarBlock(events: events, now: now)
      } else {
        log("AICloneContextService: calendar fetch failed or timed out (replying without)")
        block = nil
      }
    }
    calendarCache = (block, now)
    return block
  }

  /// Race `work` against a deadline; nil on timeout or error. The loser is cancelled,
  /// though a fetch blocked in a subprocess only dies when its own process timeout fires.
  private static func withTimeout<T: Sendable>(
    seconds: TimeInterval, _ work: @escaping @Sendable () async throws -> T
  ) async -> T? {
    await withTaskGroup(of: T?.self) { group in
      group.addTask { try? await work() }
      group.addTask {
        try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
        return nil
      }
      let first = await group.next() ?? nil
      group.cancelAll()
      return first
    }
  }

  /// Pure renderer: filters to [now, now+14d], sorts ascending, caps line count, and
  /// carries the hard no-booking rule. Unit-testable with synthetic events.
  static func renderCalendarBlock(
    events: [CalendarEvent], now: Date, calendar: Calendar = .current
  ) -> String? {
    let windowEnd = now.addingTimeInterval(TimeInterval(calendarDaysForward) * 86_400)

    let dayFormatter = DateFormatter()
    dayFormatter.calendar = calendar
    dayFormatter.timeZone = calendar.timeZone
    dayFormatter.dateFormat = "EEE MMM d"
    let timeFormatter = DateFormatter()
    timeFormatter.calendar = calendar
    timeFormatter.timeZone = calendar.timeZone
    timeFormatter.dateFormat = "h:mm a"
    let nowFormatter = DateFormatter()
    nowFormatter.calendar = calendar
    nowFormatter.timeZone = calendar.timeZone
    nowFormatter.dateFormat = "EEEE, MMM d yyyy, h:mm a"

    let upcoming = events
      .compactMap { event -> (start: Date, line: String)? in
        guard let start = parseEventDate(event.startTime) else { return nil }
        let end = event.endTime.isEmpty ? nil : parseEventDate(event.endTime)
        // Keep events still in progress (end in the future) and drop far-future ones.
        guard (end ?? start) >= now, start <= windowEnd else { return nil }
        let title = event.summary.isEmpty ? "Busy" : event.summary
        if event.isAllDay {
          return (start, "- \(dayFormatter.string(from: start)) (all day): \(title)")
        }
        let span = end.map { "–\(timeFormatter.string(from: $0))" } ?? ""
        return (
          start,
          "- \(dayFormatter.string(from: start)) \(timeFormatter.string(from: start))\(span): \(title)"
        )
      }
      .sorted { $0.start < $1.start }

    let shown = upcoming.prefix(maxCalendarEvents).map(\.line)
    let truncationNote =
      upcoming.count > maxCalendarEvents
      ? "\n(+\(upcoming.count - maxCalendarEvents) more events not listed — if a specific day isn't covered above, don't promise availability for it)"
      : ""
    let body =
      shown.isEmpty
      ? "No commitments in the next \(calendarDaysForward) days — genuinely wide open."
      : shown.joined(separator: "\n") + truncationNote

    return """
      YOUR REAL CALENDAR — the ONLY source of truth for your availability.
      Right now it is \(nowFormatter.string(from: now)) (local time).
      Commitments in the next \(calendarDaysForward) days:
      \(body)
      When plans or availability come up, answer ONLY from this calendar — never invent \
      or guess events. Say you're free or propose a time only if it doesn't clash with a \
      commitment above. You are ONLY texting: NEVER claim you booked, scheduled, \
      confirmed, or added anything to a calendar, and never offer to "send an invite".
      """
  }

  /// Parse a Google Calendar API timestamp: RFC3339 dateTime ("2026-07-06T14:00:00-07:00")
  /// or all-day date ("2026-07-06", interpreted in the local timezone).
  static func parseEventDate(_ raw: String, calendar: Calendar = .current) -> Date? {
    let trimmed = raw.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return nil }
    if trimmed.count == 10 {
      let formatter = DateFormatter()
      formatter.calendar = calendar
      formatter.timeZone = calendar.timeZone
      formatter.dateFormat = "yyyy-MM-dd"
      return formatter.date(from: trimmed)
    }
    let iso = ISO8601DateFormatter()
    if let date = iso.date(from: trimmed) { return date }
    iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return iso.date(from: trimmed)
  }

  // MARK: - Scheduling detection

  private static let schedulingPhrases: [String] = [
    "free", "available", "availability", "busy", "schedule", "reschedule", "calendar",
    "meet", "meeting", "meetup", "hang", "hangout", "lunch", "dinner", "brunch", "coffee",
    "drinks", "facetime", "zoom", "plans", "tomorrow", "tonight", "this week", "next week",
    "weekend", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "what time", "when are you", "when r u", "when u", "wanna come", "come over", "down to",
    "down for", "catch up", "swing by", "stop by", "call you", "call me", "give you a call",
  ]

  /// Cheap keyword/time-pattern heuristic: does this message (plus a little recent
  /// context) look like it's about availability, plans, or meeting up? False positives
  /// just attach harmless extra context; false negatives lose enrichment for one reply.
  static func isSchedulingRelated(_ text: String) -> Bool {
    let lowered = " " + text.lowercased() + " "
    for phrase in schedulingPhrases {
      // Poor-man's word boundary: the phrase must not be embedded inside a longer word.
      var searchRange = lowered.startIndex..<lowered.endIndex
      while let range = lowered.range(of: phrase, range: searchRange) {
        let before = lowered[lowered.index(before: range.lowerBound)]
        let afterIndex = range.upperBound
        let after = afterIndex < lowered.endIndex ? lowered[afterIndex] : " "
        if !before.isLetter, !after.isLetter { return true }
        searchRange = range.upperBound..<lowered.endIndex
      }
    }
    // Clock times: "3pm", "3 pm", "10:30", "10.30am"
    let timePattern = #"\b\d{1,2}([:.]\d{2})?\s*(am|pm)\b|\b\d{1,2}:\d{2}\b"#
    return lowered.range(of: timePattern, options: .regularExpression) != nil
  }

  // MARK: - Fixtures (non-production test harnesses only)

  /// JSON `["fact", …]` file override, mirroring the `aiCloneChatDbPathOverride` pattern
  /// so headless lab bundles can test deterministically. Never active in production.
  private static func loadFixtureStrings(key: String) -> [String]? {
    guard AppBuild.isNonProduction,
      let path = UserDefaults.standard.string(forKey: key), !path.isEmpty,
      let data = FileManager.default.contents(atPath: path),
      let parsed = try? JSONSerialization.jsonObject(with: data) as? [String]
    else { return nil }
    return parsed
  }

  /// JSON `[{"summary": …, "start_time": …, "end_time": …, "is_all_day": …}, …]` override.
  private static func loadFixtureEvents() -> [CalendarEvent]? {
    guard AppBuild.isNonProduction,
      let path = UserDefaults.standard.string(forKey: "aiCloneCalendarFixturePath"),
      !path.isEmpty,
      let data = FileManager.default.contents(atPath: path),
      let parsed = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
    else { return nil }
    return parsed.enumerated().map { index, dict in
      CalendarEvent(
        id: dict["id"] as? String ?? "fixture-\(index)",
        summary: dict["summary"] as? String ?? "Untitled",
        startTime: dict["start_time"] as? String ?? "",
        endTime: dict["end_time"] as? String ?? "",
        attendees: dict["attendees"] as? [String] ?? [],
        location: dict["location"] as? String ?? "",
        description: dict["description"] as? String ?? "",
        isAllDay: dict["is_all_day"] as? Bool ?? false
      )
    }
  }

  /// Test/harness hook: drop cached blocks so fixture changes take effect immediately.
  func invalidateCaches() {
    memoryCache = nil
    calendarCache = nil
  }
}
