import Foundation
import GRDB

struct AppleNoteRecord: Identifiable, Sendable {
  let id: Int64
  let title: String
  let summary: String
  let modifiedAt: Date
}

enum AppleNotesReaderError: LocalizedError {
  case storeNotFound
  case authorizationDenied(path: String)
  case invalidSelectedFolder(path: String)
  case schemaUnavailable(path: String)
  case storeReadFailed(path: String, reason: String)

  var errorDescription: String? {
    switch self {
    case .storeNotFound:
      return "Apple Notes data store not found."
    case .authorizationDenied:
      return
        "Omi needs permission to read Apple Notes. Select the Apple Notes folder or grant Full Disk Access, then try again."
    case .invalidSelectedFolder:
      return "Choose the Apple Notes folder named group.com.apple.notes."
    case .schemaUnavailable:
      return "Apple Notes data store could not be read because its database format was not recognized."
    case .storeReadFailed(_, let reason):
      return "Apple Notes data store could not be read: \(reason)"
    }
  }

  var reasonCode: String {
    switch self {
    case .storeNotFound:
      return "store_not_found"
    case .authorizationDenied:
      return "authorization_denied"
    case .invalidSelectedFolder:
      return "invalid_selected_folder"
    case .schemaUnavailable:
      return "schema_unavailable"
    case .storeReadFailed:
      return "store_read_failed"
    }
  }

  var shouldPromptForFolderSelection: Bool {
    switch self {
    case .storeNotFound, .authorizationDenied, .invalidSelectedFolder:
      return true
    case .schemaUnavailable, .storeReadFailed:
      return false
    }
  }
}

enum AppleNotesConnectionStatus: Equatable {
  case connected(noteCount: Int, verifiedAt: Date)
  case needsAccess(message: String, reasonCode: String)
  case error(message: String, reasonCode: String)

  var isConnected: Bool {
    if case .connected = self { return true }
    return false
  }
}

enum AppleNotesReadOutcome: Equatable {
  case readable(noteCount: Int)
  case needsAccess(message: String, reasonCode: String)
  case error(message: String, reasonCode: String)

  static func classify(noteCount: Int?, error: AppleNotesReaderError?) -> AppleNotesReadOutcome {
    if let noteCount {
      return .readable(noteCount: noteCount)
    }

    guard let error else {
      return .error(message: "Apple Notes data store could not be read.", reasonCode: "unknown")
    }

    let message = error.localizedDescription
    if error.shouldPromptForFolderSelection {
      return .needsAccess(message: message, reasonCode: error.reasonCode)
    }
    return .error(message: message, reasonCode: error.reasonCode)
  }
}

actor AppleNotesReaderService {
  static let shared = AppleNotesReaderService()
  private static let classifierNoise = [
    "Document Documents Papers Written Document Written Documents",
    "Chart Charts Graph Graphs",
    "Machine Apparatus Machines",
    "Consumer Electronics Electronic Device Electronic Devices Electronics",
    "Computer Computers Computing Device Computing Devices Computing Machine Computing Machines",
    "Electronic Computer Electronic Computers",
  ]

  private let selectedFolderDefaultsKey = "onboardingAppleNotesFolderPath"

  func readRecentNotes(maxResults: Int = 40, selectedFolderPath: String? = nil) async throws -> [AppleNoteRecord] {
    let boundedMaxResults = min(max(maxResults, 0), 1_000)
    let storeURL = try locateNotesStoreURL(selectedFolderPath: selectedFolderPath)

    do {
      let dbQueue = try openReadOnlyStore(at: storeURL)
      return try await fetchRecentNotes(from: dbQueue, maxResults: boundedMaxResults)
    } catch let error as AppleNotesReaderError {
      log("AppleNotesReaderService: Notes read failed code=\(error.reasonCode) path=\(storeURL.path)")
      throw error
    } catch {
      let classified = Self.classifyReadError(error, path: storeURL.path)
      log("AppleNotesReaderService: Notes read failed code=\(classified.reasonCode) path=\(storeURL.path): \(error)")
      throw classified
    }
  }

  func connectionStatus(maxResults: Int = 1, selectedFolderPath: String? = nil) async -> AppleNotesConnectionStatus {
    do {
      let notes = try await readRecentNotes(maxResults: maxResults, selectedFolderPath: selectedFolderPath)
      return .connected(noteCount: notes.count, verifiedAt: Date())
    } catch let error as AppleNotesReaderError {
      let outcome = Self.classifyReadOutcome(noteCount: nil, error: error)
      switch outcome {
      case .readable(let noteCount):
        return .connected(noteCount: noteCount, verifiedAt: Date())
      case .needsAccess(let message, let reasonCode):
        return .needsAccess(message: message, reasonCode: reasonCode)
      case .error(let message, let reasonCode):
        return .error(message: message, reasonCode: reasonCode)
      }
    } catch {
      let classified = Self.classifyReadError(error, path: selectedFolderPath ?? "")
      return .error(message: classified.localizedDescription, reasonCode: classified.reasonCode)
    }
  }

  func validateSelectedFolder(path: String, remember: Bool = true) async throws -> URL {
    let folderURL = URL(fileURLWithPath: path)
    let resolvedFolder = try Self.resolveSelectedFolder(folderURL)
    let storeURL = try locateNotesStoreURL(selectedFolderPath: resolvedFolder.path)

    do {
      let dbQueue = try openReadOnlyStore(at: storeURL)
      _ = try await countReadableNotes(from: dbQueue)
      if remember {
        rememberSelectedFolder(path: resolvedFolder.path)
      }
      log("AppleNotesReaderService: Validated selected Notes folder at \(resolvedFolder.path)")
      return resolvedFolder
    } catch let error as AppleNotesReaderError {
      log("AppleNotesReaderService: Selected folder validation failed code=\(error.reasonCode) path=\(storeURL.path)")
      throw error
    } catch {
      let classified = Self.classifyReadError(error, path: storeURL.path)
      log(
        "AppleNotesReaderService: Selected folder validation failed code=\(classified.reasonCode) path=\(storeURL.path): \(error)"
      )
      throw classified
    }
  }

  nonisolated static func resolveSelectedFolder(
    _ selectedURL: URL,
    fileManager: FileManager = .default,
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
  ) throws -> URL {
    let groupContainersURL =
      homeDirectory
      .appendingPathComponent("Library/Group Containers", isDirectory: true)

    if selectedURL.path == groupContainersURL.path {
      let inferredURL = groupContainersURL.appendingPathComponent("group.com.apple.notes", isDirectory: true)
      guard fileManager.fileExists(atPath: inferredURL.path) else {
        throw AppleNotesReaderError.invalidSelectedFolder(path: selectedURL.path)
      }
      return inferredURL
    }

    if selectedURL.lastPathComponent == "group.com.apple.notes" {
      guard fileManager.fileExists(atPath: selectedURL.path) else {
        throw AppleNotesReaderError.invalidSelectedFolder(path: selectedURL.path)
      }
      return selectedURL
    }

    let nestedURL = selectedURL.appendingPathComponent("group.com.apple.notes", isDirectory: true)
    guard fileManager.fileExists(atPath: nestedURL.path) else {
      throw AppleNotesReaderError.invalidSelectedFolder(path: selectedURL.path)
    }
    return nestedURL
  }

  nonisolated static func classifyReadError(_ error: Error, path: String) -> AppleNotesReaderError {
    if let notesError = error as? AppleNotesReaderError {
      return notesError
    }

    let message = String(describing: error)
    let localized = error.localizedDescription
    let combined = "\(message) \(localized)".lowercased()

    if combined.contains("sqlite error 23")
      || combined.contains("authorization denied")
      || combined.contains("not authorized")
      || combined.contains("operation not permitted")
      || combined.contains("permission denied")
    {
      return .authorizationDenied(path: path)
    }

    if combined.contains("no such table")
      || combined.contains("no such column")
      || combined.contains("database disk image is malformed")
    {
      return .schemaUnavailable(path: path)
    }

    return .storeReadFailed(path: path, reason: localized)
  }

  nonisolated static func classifyReadOutcome(noteCount: Int?, error: AppleNotesReaderError?) -> AppleNotesReadOutcome {
    AppleNotesReadOutcome.classify(noteCount: noteCount, error: error)
  }

  private func openReadOnlyStore(at storeURL: URL) throws -> DatabaseQueue {
    var configuration = Configuration()
    configuration.readonly = true
    return try DatabaseQueue(path: storeURL.path, configuration: configuration)
  }

  private func fetchRecentNotes(from dbQueue: DatabaseQueue, maxResults: Int) async throws -> [AppleNoteRecord] {
    try await dbQueue.read { db in
      let rows = try Row.fetchAll(
        db,
        sql: """
            SELECT
              Z_PK,
              ZTITLE,
              ZSUMMARY,
              ZMODIFICATIONDATE
            FROM ZICCLOUDSYNCINGOBJECT
            WHERE ZNOTE IS NOT NULL
              AND ZMARKEDFORDELETION = 0
              AND ZTITLE IS NOT NULL
            ORDER BY ZMODIFICATIONDATE DESC
            LIMIT ?
          """,
        arguments: [maxResults * 3]
      )

      let notes = rows.compactMap { row -> AppleNoteRecord? in
        guard let rawTitle = row["ZTITLE"] as? String else {
          return nil
        }

        let id = (row["Z_PK"] as? Int64) ?? Int64(row["Z_PK"] as? Int ?? 0)
        let modifiedAtValue =
          (row["ZMODIFICATIONDATE"] as? Double)
          ?? Double(row["ZMODIFICATIONDATE"] as? Int64 ?? 0)

        let title = Self.normalizeNoteField(rawTitle)
        let summary = Self.normalizeNoteField(row["ZSUMMARY"] as? String ?? "")

        guard !title.isEmpty, !Self.isLikelyAttachment(title: title, summary: summary) else {
          return nil
        }

        return AppleNoteRecord(
          id: id,
          title: title,
          summary: summary,
          modifiedAt: Date(timeIntervalSinceReferenceDate: modifiedAtValue)
        )
      }

      return Array(notes.prefix(maxResults))
    }
  }

  private func countReadableNotes(from dbQueue: DatabaseQueue) async throws -> Int {
    try await dbQueue.read { db in
      try Int.fetchOne(
        db,
        sql: """
            SELECT COUNT(*)
            FROM ZICCLOUDSYNCINGOBJECT
            WHERE ZNOTE IS NOT NULL
              AND ZMARKEDFORDELETION = 0
              AND ZTITLE IS NOT NULL
          """
      ) ?? 0
    }
  }

  func synthesizeFromNotes(notes: [AppleNoteRecord]) async -> (
    memories: Int, profileSummary: String
  ) {
    guard !notes.isEmpty else { return (0, "") }

    let formatter = DateFormatter()
    formatter.dateFormat = "MMM d"
    let noteLines = notes.map { note in
      let date = formatter.string(from: note.modifiedAt)
      let detail = note.summary.isEmpty ? "" : " | \(note.summary)"
      return "[\(date)] \(note.title)\(detail)"
    }
    let noteText = noteLines.joined(separator: "\n")

    let synthesisPrompt = """
      Analyze these \(notes.count) recent Apple Notes entries and extract profile information about the user.

      APPLE NOTES:
      \(noteText)

      Respond ONLY with valid JSON (no markdown, no code fences):
      {
        "memories": [
          "clear factual statement about the user"
        ],
        "profile": "2-3 sentence summary of what these notes say about the user"
      }

      RULES:
      - Extract 8-12 memories grounded in the note titles and summaries
      - Focus on plans, projects, interests, shopping intent, relationships, routines, and recurring ideas
      - Ignore screenshot noise, OCR garbage, duplicate lines, and generic UI text
      - Each memory should be one concise third-person factual statement
      - Do not invent details not supported by the notes
      """

    // Retry the synthesis (bridge/LLM call) on transient failure instead of silently
    // dropping the whole import. Each attempt uses a fresh bridge.
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
          surface: .service("apple_notes_reader"),
          prompt: synthesisPrompt,
          model: ModelQoS.Claude.synthesis,
          systemPrompt:
            "You extract high-signal user facts from Apple Notes. Output only valid JSON.",
          onTextDelta: { @Sendable _ in },
          onToolCall: { @Sendable _, _, _ in "" },
          onToolActivity: { @Sendable _, _, _, _ in }
        )

        let responseText = Self.extractJSONObject(from: result.text)
        guard
          let jsonData = responseText.data(using: .utf8),
          let parsed = try JSONSerialization.jsonObject(with: jsonData) as? [String: Any]
        else {
          log("AppleNotesReaderService: Failed to parse synthesis response")
          return (0, "")
        }

        let memoryStrings = (parsed["memories"] as? [String] ?? []).filter {
          !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        let profileSummary = parsed["profile"] as? String ?? ""

        let artifacts = memoryStrings.map { memory in
          ImportEvidenceBatchItem(
            title: "Apple Notes Insight",
            snippet: memory,
            content: memory,
            metadata: ["import_kind": "profile"]
          )
        }
        let legacyMemories = memoryStrings.map { memory in
          MemoryBatchItem(
            content: memory,
            tags: ["apple_notes", "onboarding"],
            headline: "Apple Notes Insight",
            source: "apple_notes"
          )
        }
        let saveResult = await OnboardingImportEvidenceService.save(
          artifacts,
          sourceType: "apple_notes",
          logPrefix: "AppleNotesReaderService",
          legacyMemories: legacyMemories
        )

        return (saveResult.saved, profileSummary)
      } catch {
        if attempt < maxAttempts {
          log("AppleNotesReaderService: Synthesis attempt \(attempt) failed, retrying: \(error)")
          try? await Task.sleep(nanoseconds: 800_000_000)
          continue
        }
        log("AppleNotesReaderService: Synthesis failed after \(attempt) attempts: \(error)")
        return (0, "")
      }
    }
    return (0, "")
  }

  func saveAsMemories(notes: [AppleNoteRecord], limit: Int? = nil) async -> (saved: Int, failed: Int) {
    let notesToSave = limit.map { Array(notes.prefix($0)) } ?? notes
    guard !notesToSave.isEmpty else { return (0, 0) }

    let dateFormatter = DateFormatter()
    dateFormatter.dateFormat = "MMM d, yyyy"
    let artifacts = notesToSave.map { note in
      var content = note.title
      if !note.summary.isEmpty {
        content += "\n\n" + note.summary
      }

      return ImportEvidenceBatchItem(
        externalId: "apple_notes:\(note.id)",
        occurredAt: note.modifiedAt,
        title: note.title,
        snippet: note.summary,
        content: content,
        metadata: [
          "import_kind": "note",
          "window_title": "Apple Notes — \(dateFormatter.string(from: note.modifiedAt))",
        ]
      )
    }
    let legacyMemories = notesToSave.map { note in
      var content = note.title
      if !note.summary.isEmpty {
        content += "\n\n" + note.summary
      }
      return MemoryBatchItem(
        content: content,
        tags: ["apple_notes", "onboarding", "note"],
        headline: note.title,
        source: "apple_notes",
        windowTitle: "Apple Notes — \(dateFormatter.string(from: note.modifiedAt))"
      )
    }

    let result = await OnboardingImportEvidenceService.save(
      artifacts,
      sourceType: "apple_notes",
      logPrefix: "AppleNotesReaderService",
      legacyMemories: legacyMemories
    )
    log("AppleNotesReaderService: Saved \(result.saved) notes as import evidence (\(result.failed) failed)")
    return result
  }

  func rememberSelectedFolder(path: String) {
    UserDefaults.standard.set(path, forKey: selectedFolderDefaultsKey)
  }

  private func locateNotesStoreURL(selectedFolderPath: String? = nil) throws -> URL {
    let fm = FileManager.default
    let home = fm.homeDirectoryForCurrentUser

    var candidates: [URL] = []

    if let selectedFolderPath = selectedFolderPath ?? UserDefaults.standard.string(forKey: selectedFolderDefaultsKey),
      !selectedFolderPath.isEmpty
    {
      let selectedFolderURL = URL(fileURLWithPath: selectedFolderPath)
      if selectedFolderURL.lastPathComponent == "NoteStore.sqlite" {
        candidates.append(selectedFolderURL)
      } else if let resolvedFolder = try? Self.resolveSelectedFolder(
        selectedFolderURL, fileManager: fm, homeDirectory: home)
      {
        candidates.append(
          resolvedFolder.appendingPathComponent("NoteStore.sqlite", isDirectory: false)
        )
        candidates.append(
          resolvedFolder
            .appendingPathComponent("Accounts", isDirectory: true)
            .appendingPathComponent("LocalAccount", isDirectory: true)
            .appendingPathComponent("NoteStore.sqlite", isDirectory: false)
        )
      }
      candidates.append(
        selectedFolderURL.appendingPathComponent("NoteStore.sqlite", isDirectory: false)
      )
      candidates.append(
        selectedFolderURL
          .appendingPathComponent("Accounts", isDirectory: true)
          .appendingPathComponent("LocalAccount", isDirectory: true)
          .appendingPathComponent("NoteStore.sqlite", isDirectory: false)
      )

      guard let storeURL = candidates.first(where: { fm.fileExists(atPath: $0.path) }) else {
        throw AppleNotesReaderError.invalidSelectedFolder(path: selectedFolderPath)
      }
      return storeURL
    }

    candidates.append(
      home.appendingPathComponent("Library/Group Containers/group.com.apple.notes/NoteStore.sqlite")
    )
    candidates.append(
      home
        .appendingPathComponent("Library/Group Containers/group.com.apple.notes", isDirectory: true)
        .appendingPathComponent("NoteStore.sqlite", isDirectory: false)
    )
    candidates.append(
      home
        .appendingPathComponent(
          "Library/Group Containers/group.com.apple.notes/Accounts/LocalAccount",
          isDirectory: true
        )
        .appendingPathComponent("NoteStore.sqlite", isDirectory: false)
    )

    guard let storeURL = candidates.first(where: { fm.fileExists(atPath: $0.path) }) else {
      throw AppleNotesReaderError.storeNotFound
    }
    return storeURL
  }

  private static func normalizeNoteField(_ value: String) -> String {
    var normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
    for noise in Self.classifierNoise {
      normalized = normalized.replacingOccurrences(of: noise, with: "")
    }
    normalized = normalized.replacingOccurrences(
      of: #"\s+"#,
      with: " ",
      options: .regularExpression
    )
    return normalized.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  nonisolated static func isLikelyAttachment(title: String, summary: String) -> Bool {
    let combined = "\(title) \(summary)".trimmingCharacters(in: .whitespacesAndNewlines)
    guard !combined.isEmpty else { return true }

    // "SOLITE" / "kMDItem" are distinctive metadata/artifact tokens safe to match as
    // substrings. "exec" must match only as a whole word — as a raw substring it wrongly
    // dropped ordinary notes whose title/summary merely *contained* it ("Q3 execution
    // plan", "Executive summary", "executed tasks").
    let hasExecToken = combined.range(of: #"\bexec\b"#, options: [.regularExpression, .caseInsensitive]) != nil
    if combined.contains("SOLITE") || combined.contains("kMDItem") || hasExecToken {
      return true
    }

    let lowerTitle = title.lowercased()
    let attachmentExtensions = [".png", ".jpg", ".jpeg", ".heic", ".pdf", ".mov", ".mp4"]
    if attachmentExtensions.contains(where: { lowerTitle.hasSuffix($0) }) {
      return true
    }

    if lowerTitle.hasPrefix("cleanshot ") || lowerTitle.hasPrefix("image ") {
      return true
    }

    if lowerTitle.contains("scan") && lowerTitle.contains("document") {
      return true
    }

    return title.count < 3 && summary.count < 12
  }

  private static func extractJSONObject(from text: String) -> String {
    var responseText = text.trimmingCharacters(in: .whitespacesAndNewlines)

    if responseText.hasPrefix("```") {
      if let firstNewline = responseText.firstIndex(of: "\n") {
        responseText = String(responseText[responseText.index(after: firstNewline)...])
      }
      if responseText.hasSuffix("```") {
        responseText = String(responseText.dropLast(3)).trimmingCharacters(
          in: .whitespacesAndNewlines)
      }
    }

    if let braceIndex = responseText.firstIndex(of: "{") {
      responseText = String(responseText[braceIndex...])
    }

    return responseText.trimmingCharacters(in: .whitespacesAndNewlines)
  }

}
