import Foundation

struct MeetingScreenActivitySnapshot: Equatable, Sendable {
  let timestamp: Date
  let appName: String
  let windowTitle: String?
  let ocrText: String?
}

protocol MeetingScreenActivityProviding: Sendable {
  func snapshots(overlapping interval: DateInterval) async -> [MeetingScreenActivitySnapshot]
}

actor RewindMeetingScreenActivityProvider: MeetingScreenActivityProviding {
  func snapshots(overlapping interval: DateInterval) async -> [MeetingScreenActivitySnapshot] {
    do {
      return try await RewindDatabase.shared
        .getScreenshots(from: interval.start, to: interval.end, limit: 240)
        .map {
          MeetingScreenActivitySnapshot(
            timestamp: $0.timestamp,
            appName: $0.appName,
            windowTitle: $0.windowTitle,
            ocrText: $0.ocrText)
        }
    } catch {
      // Local OCR context is optional; database availability must never hold finalization open.
      return []
    }
  }
}

enum OnDeviceMeetingIdentityExtractor {
  static let maximumRows = 80
  static let maximumCharacters = 12_000
  static let maximumParticipants = 12

  private static let emailPattern = regex("[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}")
  // Single source for the bare-meeting-code title lives in the shared conferencing catalog.
  private static let meetCodeTitle = regex(ConferencingApps.browserCallTitlePattern)
  private static let rosterPatterns = [
    regex("(?i)^(?<people>.+?)\\s+(?:are|is)\\s+in\\s+this\\s+call\\b"),
    regex("(?i)^(?<people>.+?)\\s+(?:has|have)\\s+joined\\b"),
    regex("(?i)^Meet\\s+with\\s+(?<people>.+?)\\s*$"),
    regex("(?i)^In\\s+call\\s+with\\s+(?<people>.+?)\\s*$"),
  ]
  private static let rosterSeparator = regex("(?i),|\\band\\b|&|\\+")
  private static let nameDecoration = regex("(?i)\\s*(?:\\(.*?\\)|\\d{1,2}:\\d{2}\\s*(?:AM|PM)?|·.*)\\s*$")
  private static let nameWord = regex("^[A-Za-z][A-Za-z.'’\\-]*$")
  private static let nonPersonWords: Set<String> = [
    "account", "admin", "all", "anyone", "call", "everyone", "guest", "guests", "host", "me", "others",
    "participants", "people", "presenting", "you",
  ]
  private static let joinerWords: Set<String> = ["and", "with", "vs", "versus", "or", "et"]
  private static let uiTitles: Set<String> = [
    "audio", "camera", "chat", "leave", "meeting", "microphone", "more", "mute", "participants", "reactions",
    "record", "screen", "share", "stop video", "unmute",
  ]

  static func payload(
    from snapshots: [MeetingScreenActivitySnapshot],
    overlapping interval: DateInterval,
    ownerNames: [String] = [],
    ownerEmails: [String] = []
  ) -> DesktopMeetingPayload? {
    let selected = selectConferencingRows(snapshots)
    guard !selected.isEmpty else { return nil }
    // Tile persistence is judged over every row, not the character-budgeted selection: three
    // full-desktop frames exhaust that budget.
    let tiles = callTileNames(in: snapshots, ownerNames: ownerNames, ownerEmails: ownerEmails)
    var participants = participants(from: selected.map(\.combinedText), tileNames: tiles)
    if participants.isEmpty {
      participants = messagingCallParticipants(from: snapshots)
    }
    guard !participants.isEmpty else { return nil }

    let title = selected.compactMap(meetingTitle).first ?? "Video meeting"
    let platform = selected.compactMap { conferencingPlatform(for: $0) }.first ?? "Video conference"
    let start = interval.start
    let end = max(interval.end, start.addingTimeInterval(1))
    let eventID = "screen-activity:\(Int(start.timeIntervalSince1970)):\(Int(end.timeIntervalSince1970))"

    return DesktopMeetingPayload(
      calendarEventID: eventID,
      source: .derived(
        calendarSource: "screen_activity",
        egress: DerivedDataEgressRequest(
          dataClass: .meetingIdentity,
          route: .calendarMeetings,
          purpose: DerivedDataEgressPolicy.meetingIdentityPurpose)),
      title: title,
      startTime: start,
      endTime: end,
      participants: participants,
      platform: platform,
      meetingLink: nil)
  }

  static func participants(from texts: [String], tileNames: [String] = []) -> [DesktopMeetingParticipant] {
    var roster: [String] = []
    var emails: [String] = []
    var looseNames: [String] = []
    for text in texts where !text.isEmpty {
      appendUnique(rosterNames(in: text), to: &roster)
      appendUnique(
        matches(emailPattern, in: text).map {
          $0.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        },
        to: &emails)
      appendUnique(decoratedNameLines(in: text), to: &looseNames)
    }

    let localTokens = Set(emails.flatMap { emailLocalTokens($0) })
    var names = roster
    for candidate in looseNames where !names.contains(candidate) {
      if !Set(nameTokens(candidate)).isDisjoint(with: localTokens) { names.append(candidate) }
    }
    var known = Set(names.map { $0.lowercased() })
    for tile in tileNames where known.insert(tile.lowercased()).inserted {
      names.append(tile)
    }

    var result: [DesktopMeetingParticipant] = []
    var usedEmails = Set<String>()
    for name in names.prefix(maximumParticipants) {
      let tokens = Set(nameTokens(name))
      let email = emails.first {
        !usedEmails.contains($0) && !Set(emailLocalTokens($0)).isDisjoint(with: tokens)
      }
      if let email { usedEmails.insert(email) }
      result.append(DesktopMeetingParticipant(name: name, email: email))
    }
    for email in emails where !usedEmails.contains(email) && result.count < maximumParticipants {
      result.append(DesktopMeetingParticipant(name: nil, email: email))
    }
    return result
  }

  private static func selectConferencingRows(_ snapshots: [MeetingScreenActivitySnapshot])
    -> [MeetingScreenActivitySnapshot]
  {
    let ranked = snapshots.enumerated().filter { conferencingPlatform(for: $0.element) != nil }.sorted {
      let left = identitySignal($0.element.combinedText)
      let right = identitySignal($1.element.combinedText)
      return left == right ? $0.offset < $1.offset : left > right
    }
    var selected: [MeetingScreenActivitySnapshot] = []
    var characters = 0
    for (_, snapshot) in ranked.prefix(maximumRows) {
      guard characters < maximumCharacters else { break }
      let available = maximumCharacters - characters
      let clipped = String(snapshot.combinedText.prefix(available))
      selected.append(
        MeetingScreenActivitySnapshot(
          timestamp: snapshot.timestamp,
          appName: snapshot.appName,
          windowTitle: snapshot.windowTitle,
          ocrText: clipped))
      characters += clipped.count
    }
    return selected
  }

  private static func conferencingPlatform(for snapshot: MeetingScreenActivitySnapshot) -> String? {
    let metadata = "\(snapshot.appName) \(snapshot.windowTitle ?? "")".lowercased()
    if metadata.contains("google meet") || metadata.contains("meet.google")
      || firstMatch(meetCodeTitle, in: cleanLine(snapshot.windowTitle ?? "")) != nil
      || snapshot.combinedText.lowercased().contains("meet.google.com/")
    {
      return "Google Meet"
    }
    if metadata.contains("zoom") || snapshot.combinedText.lowercased().contains("zoom.us/j/") { return "Zoom" }
    if metadata.contains("microsoft teams") || metadata.contains("teams")
      || snapshot.combinedText.lowercased().contains("teams.microsoft.com/l/meetup")
    {
      return "Teams"
    }
    if metadata.contains("webex") || snapshot.combinedText.lowercased().contains("webex.com/meet") { return "Webex" }
    if metadata.contains("facetime") { return "FaceTime" }
    if ConferencingApps.isMessagingCallApp(appName: snapshot.appName) {
      return ConferencingApps.nativeCallPlatform(forAppName: snapshot.appName)
    }
    return nil
  }

  private static func meetingTitle(for snapshot: MeetingScreenActivitySnapshot) -> String? {
    let title = cleanLine(snapshot.windowTitle ?? "")
    guard !title.isEmpty, !uiTitles.contains(title.lowercased()) else { return nil }
    if firstMatch(meetCodeTitle, in: title) != nil { return title }

    // A native conferencing app owns its window title. A browser row recognized
    // only from OCR does not: its tab/window title might describe any other page.
    if ConferencingApps.nativeCallPlatform(forAppName: snapshot.appName) != nil {
      return title
    }
    let app = snapshot.appName.lowercased()
    let nativeMarkers = ["zoom", "microsoft teams", "webex", "facetime", "google meet"]
    return nativeMarkers.contains(where: app.contains) ? title : nil
  }

  private static let callControlMarkers: [String] = [
    "mute", "unmute", "end call", "hang up", "leave call",
    "stop video", "start video", "screen share", "screenshare",
    "in call", "in-call", "camera off", "camera on",
  ]

  private static func hasCallControlChrome(_ snapshot: MeetingScreenActivitySnapshot) -> Bool {
    let haystack = snapshot.combinedText.lowercased()
    return callControlMarkers.contains { marker in
      let pattern = "\\b\(NSRegularExpression.escapedPattern(for: marker))\\b"
      return haystack.range(of: pattern, options: .regularExpression) != nil
    }
  }

  /// For native messaging-call apps only: a name-shaped window title is a
  /// participation assertion when the row also shows in-call chrome, or when one
  /// stable call window dominates the interval. Unrelated chat titles are ignored.
  private static func messagingCallParticipants(from snapshots: [MeetingScreenActivitySnapshot])
    -> [DesktopMeetingParticipant]
  {
    let messaging = snapshots.filter { ConferencingApps.isMessagingCallApp(appName: $0.appName) }
    guard !messaging.isEmpty else { return [] }
    let callRows = messaging.filter(hasCallControlChrome)
    let source = callRows.isEmpty ? dominatingCallWindows(in: messaging) : callRows
    guard !source.isEmpty else { return [] }

    var names: [String] = []
    for snapshot in source {
      let title = cleanLine(snapshot.windowTitle ?? "")
      guard looksLikePersonName(title), !uiTitles.contains(title.lowercased()) else { continue }
      if title.lowercased() == snapshot.appName.lowercased() { continue }
      if !names.contains(title) { names.append(title) }
    }
    return names.prefix(maximumParticipants).map { DesktopMeetingParticipant(name: $0, email: nil) }
  }

  private static func dominatingCallWindows(in snapshots: [MeetingScreenActivitySnapshot])
    -> [MeetingScreenActivitySnapshot]
  {
    var counts: [String: Int] = [:]
    for snapshot in snapshots {
      let title = cleanLine(snapshot.windowTitle ?? "")
      guard !title.isEmpty else { continue }
      counts[title, default: 0] += 1
    }
    let titledCount = counts.values.reduce(0, +)
    guard titledCount > 0, let (topTitle, topCount) = counts.max(by: { $0.value < $1.value }) else {
      return []
    }
    guard looksLikePersonName(topTitle) else { return [] }
    let runnerUp = counts.filter { $0.key != topTitle }.map(\.value).max() ?? 0
    guard topCount * 2 > titledCount, topCount > runnerUp else { return [] }
    return snapshots.filter { cleanLine($0.windowTitle ?? "") == topTitle }
  }

  // MARK: - Call tiles

  // A video tile labels its person with a bare name and nothing else, so no roster sentence or email
  // ever corroborates it (conversation 449565eb: a 1:1 Meet whose other participant was on screen
  // the whole call but never reached the roster). What corroborates a tile label is persistence: it
  // stays on screen across the call while tab-strip text churns. The backend twin
  // (`utils/conversations/meeting_context.py` `call_tile_names`) implements the same rule; both are
  // pinned by `backend/tests/fixtures/meeting_identity/call_tile_vectors.json`.
  static let minimumTileRows = 3
  static let minimumTileRowShare = 0.25
  static let maximumTileNames = 8
  /// A label that recurs across most non-call rows too is browser chrome (bookmarks bar, profile
  /// button), not a tile. Only judged with enough non-call rows.
  static let minimumNonCallRowsForChromeCheck = 3
  static let maximumNonCallRowShare = 0.5

  private static let tileParticles: Set<String> = [
    "al", "bin", "da", "de", "del", "der", "di", "du", "la", "le", "van", "von",
  ]
  private static let ownerTileMarker = regex("(?i)\\((?:[^)]*[,\\s])?you(?:[,\\s][^)]*)?\\)\\s*$")
  private static let meetCode = regex("(?i)\\b[a-z]{3}-[a-z]{4}-[a-z]{3}\\b")
  private static let titleSeparator = regex("\\s[-\u{2013}\u{2014}|:]\\s")
  /// Words that make a capitalised line app chrome, a meeting title, or a page name, not a person.
  private static let tileChromeWords: Set<String> = Set(
    """
    access account accounts activities admin advisories agenda allow analytics api backgrounds bank \
    banking billing board bookmarks calendar call camera captions channel chat chrome cloud console \
    controls cost dashboard dashboards demo docs document drive edit effects everyone feedback file \
    general github gmail google guest hand help home host inbox intro issues join keys kickoff leave \
    login meet meeting meetings mic microphone monitor more mute new notes notion options overview \
    participants pay people platform portal present presentation presenting profile project pull raise \
    rate reactions record recording registration report requests review roadmap screen search security \
    settings share sharing sheets sign slack slides standup summary sync tab tabs team teams tokens \
    untitled unmute update usage users view webex window workspace you zoom
    """.split(separator: " ").map(String.init))
  /// AI notetakers and assistants join calls as tiles too; they are never human participants.
  /// Whole tokens only: a suffix rule ("ends with bot") also drops people named Talbot or Abbot.
  /// Dotted agent names ("Otter.ai", "Read.ai", "tl;dv") already fail the tile-name shape.
  private static let aiAgentTileWords: Set<String> = [
    "agent", "ai", "assistant", "boardy", "bot", "chatbot", "companion", "fathom", "fireflies", "gemini",
    "granola", "meetbot", "notebot", "notes", "notetaker", "otter", "recorder", "tldv",
  ]

  /// Names shown as call-tile labels, by persistence across the call's rows. A candidate is a line
  /// that is only a 2-4 token capitalised name (tile decorations stripped). It is accepted when it
  /// appears in at least `minimumTileRows` conferencing rows and at least `minimumTileRowShare` of
  /// them, is not the owner (their tile says "(You)", or it matches a supplied owner name or email),
  /// not an AI agent, not part of a conferencing window title, and not chrome that recurs across the
  /// non-call rows as well.
  static func callTileNames(
    in snapshots: [MeetingScreenActivitySnapshot],
    ownerNames: [String] = [],
    ownerEmails: [String] = []
  ) -> [String] {
    let callRows = snapshots.filter { conferencingPlatform(for: $0) != nil }
    guard callRows.count >= minimumTileRows else { return [] }
    var owners = Set(ownerNames.map { cleanLine($0).lowercased() }.filter { !$0.isEmpty })
    let ownerLocals = Set(
      ownerEmails.compactMap { email -> String? in
        let folded = email.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard folded.contains("@") else { return nil }
        return folded.split(separator: "@", maxSplits: 1, omittingEmptySubsequences: false).first.map(String.init)
      })
    var titleParts = Set<String>()
    var counts: [String: Int] = [:]
    var spelling: [String: String] = [:]
    var order: [String] = []
    for row in callRows {
      let title = cleanLine(row.windowTitle ?? "")
      for part in split(titleSeparator, text: title)
      where !part.trimmingCharacters(in: .whitespaces).isEmpty {
        titleParts.insert(cleanLine(part).lowercased())
      }
      var seen = Set<String>()
      for rawLine in (row.ocrText ?? "").components(separatedBy: .newlines) {
        let line = cleanLine(rawLine)
        guard let name = tileName(line) else { continue }
        let key = name.lowercased()
        if firstMatch(ownerTileMarker, in: line) != nil { owners.insert(key) }
        guard seen.insert(key).inserted else { continue }
        if counts[key] == nil {
          counts[key] = 0
          spelling[key] = name
          order.append(key)
        }
        counts[key, default: 0] += 1
      }
    }

    let nonCallRows = snapshots.filter { conferencingPlatform(for: $0) == nil }
    let minimum = max(Double(minimumTileRows), minimumTileRowShare * Double(callRows.count))
    var accepted: [String] = []
    for key in order {
      guard let name = spelling[key], let count = counts[key] else { continue }
      if Double(count) < minimum || titleParts.contains(key) { continue }
      if isOwnerName(name, owners: owners, ownerLocals: ownerLocals) || isAIAgentTileName(name) { continue }
      if nonCallRows.count >= minimumNonCallRowsForChromeCheck {
        let elsewhere = nonCallRows.filter { row in
          row.combinedText.components(separatedBy: .newlines).contains { tileName(cleanLine($0)) == name }
        }.count
        if Double(elsewhere) > maximumNonCallRowShare * Double(nonCallRows.count) { continue }
      }
      accepted.append(name)
    }
    // `accepted` is already in first-appearance order, so a stable sort by count is the full order.
    let ranked = accepted.enumerated().sorted {
      let left = counts[$0.element.lowercased()] ?? 0
      let right = counts[$1.element.lowercased()] ?? 0
      return left == right ? $0.offset < $1.offset : left > right
    }
    accepted = ranked.map(\.element)
    return Array(accepted.prefix(maximumTileNames))
  }

  static func isAIAgentTileName(_ name: String) -> Bool {
    name.split(separator: " ").contains { word in
      let token = word.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: ".'’-"))
      return aiAgentTileWords.contains(token)
    }
  }

  /// The name a call tile shows on this line, if the line is only a name.
  private static func tileName(_ line: String) -> String? {
    if line.contains("@") || line.lowercased().contains("http") || firstMatch(meetCode, in: line) != nil {
      return nil
    }
    let name = cleanLine(replacingMatches(nameDecoration, in: line, with: ""))
    let tokens = name.split(separator: " ").map(String.init)
    guard (2...4).contains(tokens.count), name.count <= 60, tokens.allSatisfy(isTileToken) else { return nil }
    if let first = tokens.first, let last = tokens.last,
      tileParticles.contains(first.lowercased()) || tileParticles.contains(last.lowercased())
    {
      return nil
    }
    let folded = tokens.map(trimmedToken)
    guard
      !folded.contains(where: {
        tileChromeWords.contains($0) || nonPersonWords.contains($0) || joinerWords.contains($0)
      })
    else { return nil }
    return name
  }

  private static func isTileToken(_ token: String) -> Bool {
    if tileParticles.contains(token.lowercased()) { return true }
    guard token.first?.isUppercase == true,
      token.allSatisfy({ $0.isLetter || "-'’".contains($0) })
    else { return false }
    return token.contains { $0.isLowercase }
  }

  private static func isOwnerName(_ name: String, owners: Set<String>, ownerLocals: Set<String>) -> Bool {
    let folded = name.lowercased()
    let tokens = folded.split(separator: " ").map(String.init)
    for owner in owners {
      let ownerTokens = owner.split(separator: " ").map(String.init)
      if folded == owner
        || (ownerTokens.count >= 2 && tokens.first == ownerTokens.first && tokens.last == ownerTokens.last)
      {
        return true
      }
    }
    let joined = tokens.joined()
    return ownerLocals.contains { local in
      joined == local.filter { !"._-+".contains($0) }
    }
  }

  private static func trimmedToken(_ word: String) -> String {
    word.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "'’-"))
  }

  private static func rosterNames(in text: String) -> [String] {
    text.components(separatedBy: .newlines).flatMap { rawLine -> [String] in
      let line = cleanLine(rawLine)
      // Roster sentences are short UI chrome, never a 4k-character OCR smear.
      guard
        line.count <= 200,
        let match = rosterPatterns.compactMap({ firstMatch($0, in: line, group: "people") }).first
      else { return [] }
      return split(rosterSeparator, text: match).map(cleanLine).filter(looksLikePersonName)
    }
  }

  private static func decoratedNameLines(in text: String) -> [String] {
    text.components(separatedBy: .newlines).compactMap { rawLine in
      var line = cleanLine(rawLine)
      guard !line.contains("@"), !line.lowercased().contains("http") else { return nil }
      line = cleanLine(replacingMatches(nameDecoration, in: line, with: ""))
      return looksLikePersonName(line) ? line : nil
    }
  }

  private static func looksLikePersonName(_ value: String) -> Bool {
    guard !value.isEmpty, value.count <= 60 else { return false }
    let words = value.split(separator: " ").map(String.init)
    guard (1...4).contains(words.count), !words.contains(where: { nonPersonWords.contains($0.lowercased()) }) else {
      return false
    }
    // One person is never called "X and Y": such a line is a roster or an event title.
    guard
      !words.contains(where: {
        joinerWords.contains($0.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: ".'’-")))
      })
    else { return false }
    return words.allSatisfy { firstMatch(nameWord, in: $0) != nil }
      && words.contains { $0.first?.isUppercase == true }
  }

  private static func identitySignal(_ text: String) -> Int {
    (rosterNames(in: text).isEmpty ? 0 : 2) + (firstMatch(emailPattern, in: text) == nil ? 0 : 1)
  }

  private static func nameTokens(_ name: String) -> [String] {
    name.split(separator: " ").map { $0.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: ".'’-")) }
  }

  private static func emailLocalTokens(_ email: String) -> [String] {
    guard let local = email.split(separator: "@", maxSplits: 1).first else { return [] }
    return local.split(whereSeparator: { "._-".contains($0) }).map { $0.lowercased() }
  }

  private static func cleanLine(_ value: String) -> String {
    value.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
      .trimmingCharacters(in: CharacterSet(charactersIn: " •|*·-—\t"))
  }

  private static func appendUnique(_ values: [String], to destination: inout [String]) {
    for value in values where !destination.contains(value) { destination.append(value) }
  }

  private static func regex(_ pattern: String) -> NSRegularExpression {
    do {
      return try NSRegularExpression(pattern: pattern)
    } catch {
      preconditionFailure("Invalid static meeting-identity pattern")
    }
  }

  private static func firstMatch(_ regex: NSRegularExpression, in text: String, group: String? = nil) -> String? {
    let range = NSRange(text.startIndex..., in: text)
    guard let match = regex.firstMatch(in: text, range: range) else { return nil }
    let matchRange = group.map { match.range(withName: $0) } ?? match.range
    guard let swiftRange = Range(matchRange, in: text) else { return nil }
    return String(text[swiftRange])
  }

  private static func matches(_ regex: NSRegularExpression, in text: String) -> [String] {
    regex.matches(in: text, range: NSRange(text.startIndex..., in: text)).compactMap {
      Range($0.range, in: text).map { String(text[$0]) }
    }
  }

  private static func replacingMatches(
    _ regex: NSRegularExpression,
    in text: String,
    with replacement: String
  ) -> String {
    regex.stringByReplacingMatches(in: text, range: NSRange(text.startIndex..., in: text), withTemplate: replacement)
  }

  private static func split(_ regex: NSRegularExpression, text: String) -> [String] {
    var pieces: [String] = []
    var cursor = text.startIndex
    for match in regex.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
      guard let range = Range(match.range, in: text) else { continue }
      pieces.append(String(text[cursor..<range.lowerBound]))
      cursor = range.upperBound
    }
    pieces.append(String(text[cursor...]))
    return pieces
  }
}

extension MeetingScreenActivitySnapshot {
  fileprivate var combinedText: String { "\(windowTitle ?? "")\n\(ocrText ?? "")" }
}

actor OnDeviceMeetingIdentityService {
  static let shared = OnDeviceMeetingIdentityService()

  /// The signed-in user's own names and emails, so their tile is never listed as someone else.
  struct OwnerIdentity: Sendable {
    var names: [String]
    var emails: [String]
  }

  private let provider: any MeetingScreenActivityProviding
  private let uploader: any DesktopMeetingUploading
  private let ownerIdentity: @Sendable () async -> OwnerIdentity
  private var uploadedEventIDs = Set<String>()

  init(
    provider: any MeetingScreenActivityProviding = RewindMeetingScreenActivityProvider(),
    uploader: any DesktopMeetingUploading = BackendDesktopMeetingUploader(),
    ownerIdentity: @escaping @Sendable () async -> OwnerIdentity = { @MainActor in
      OnDeviceMeetingIdentityService.signedInOwner()
    }
  ) {
    self.provider = provider
    self.uploader = uploader
    self.ownerIdentity = ownerIdentity
  }

  @MainActor
  static func signedInOwner() -> OwnerIdentity {
    let auth = AuthService.shared
    let names = [auth.displayName].filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
    let emails = [AuthState.shared.userEmail].compactMap { $0 }.filter { $0.contains("@") }
    return OwnerIdentity(names: names, emails: emails)
  }

  func syncIdentity(overlapping interval: DateInterval) async {
    let snapshots = await provider.snapshots(overlapping: interval)
    let owner = await ownerIdentity()
    guard
      let payload = OnDeviceMeetingIdentityExtractor.payload(
        from: snapshots, overlapping: interval, ownerNames: owner.names, ownerEmails: owner.emails)
    else { return }
    guard !uploadedEventIDs.contains(payload.calendarEventID) else { return }
    do {
      _ = try payload.wireBody
      try await uploader.upload(payload)
      uploadedEventIDs.insert(payload.calendarEventID)
      log("OnDeviceMeetingIdentity: stored meeting identity")
    } catch {
      // Metadata-only log: OCR, names, emails, titles, and transport bodies stay out of logs.
      log("OnDeviceMeetingIdentity: upload failed")
    }
  }
}
