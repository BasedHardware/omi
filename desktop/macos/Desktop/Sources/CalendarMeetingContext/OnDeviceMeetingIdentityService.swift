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
  private static let uiTitles: Set<String> = [
    "audio", "camera", "chat", "leave", "meeting", "microphone", "more", "mute", "participants", "reactions",
    "record", "screen", "share", "stop video", "unmute",
  ]

  static func payload(
    from snapshots: [MeetingScreenActivitySnapshot],
    overlapping interval: DateInterval
  ) -> DesktopMeetingPayload? {
    let selected = selectConferencingRows(snapshots)
    guard !selected.isEmpty else { return nil }
    var participants = participants(from: selected.map(\.combinedText))
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

  static func participants(from texts: [String]) -> [DesktopMeetingParticipant] {
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

  private static func rosterNames(in text: String) -> [String] {
    text.components(separatedBy: .newlines).flatMap { rawLine -> [String] in
      let line = cleanLine(rawLine)
      guard
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

  private let provider: any MeetingScreenActivityProviding
  private let uploader: any DesktopMeetingUploading
  private var uploadedEventIDs = Set<String>()

  init(
    provider: any MeetingScreenActivityProviding = RewindMeetingScreenActivityProvider(),
    uploader: any DesktopMeetingUploading = BackendDesktopMeetingUploader()
  ) {
    self.provider = provider
    self.uploader = uploader
  }

  func syncIdentity(overlapping interval: DateInterval) async {
    let snapshots = await provider.snapshots(overlapping: interval)
    guard let payload = OnDeviceMeetingIdentityExtractor.payload(from: snapshots, overlapping: interval) else { return }
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
