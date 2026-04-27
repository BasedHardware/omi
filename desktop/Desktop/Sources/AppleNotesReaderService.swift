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
  case storeUnavailable

  var errorDescription: String? {
    switch self {
    case .storeNotFound:
      return "Apple Notes data store not found."
    case .storeUnavailable:
      return "Apple Notes data store is unavailable."
    }
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

  func readRecentNotes(maxResults: Int = 40) async throws -> [AppleNoteRecord] {
    guard let storeURL = locateNotesStoreURL() else {
      throw AppleNotesReaderError.storeNotFound
    }

    var configuration = Configuration()
    configuration.readonly = true

    do {
      let dbQueue = try DatabaseQueue(path: storeURL.path, configuration: configuration)
      return try await dbQueue.read { db in
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
    } catch {
      log("AppleNotesReaderService: Failed reading Notes store at \(storeURL.path): \(error)")
      throw AppleNotesReaderError.storeUnavailable
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

    do {
      let bridge = AgentBridge(harnessMode: "piMono")
      try await bridge.start()
      defer { Task { await bridge.stop() } }

      let result = try await bridge.query(
        prompt: synthesisPrompt,
        systemPrompt:
          "You extract high-signal user facts from Apple Notes. Output only valid JSON.",
        model: ModelQoS.Claude.synthesis,
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

      var memoriesSaved = 0
      for memory in memoryStrings {
        do {
          _ = try await APIClient.shared.createMemory(
            content: memory,
            visibility: "private",
            tags: ["apple_notes", "import", "profile"],
            source: "apple_notes",
            headline: "Apple Notes Insight"
          )
          memoriesSaved += 1
        } catch {
          log("AppleNotesReaderService: Failed to save memory: \(error)")
        }
      }

      return (memoriesSaved, profileSummary)
    } catch {
      log("AppleNotesReaderService: Synthesis failed: \(error)")
      return (0, "")
    }
  }

  func saveAsMemories(notes: [AppleNoteRecord], limit: Int? = nil) async -> (saved: Int, failed: Int) {
    let notesToSave = limit.map { Array(notes.prefix($0)) } ?? notes
    guard !notesToSave.isEmpty else { return (0, 0) }

    let concurrency = min(8, notesToSave.count)
    var nextIndex = 0

    return await withTaskGroup(of: Bool.self) { group in
      func enqueueNext() {
        guard nextIndex < notesToSave.count else { return }
        let note = notesToSave[nextIndex]
        nextIndex += 1
        group.addTask {
          await Self.saveMemory(for: note)
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

      log("AppleNotesReaderService: Saved \(saved) notes as memories (\(failed) failed)")
      return (saved, failed)
    }
  }

  func rememberSelectedFolder(path: String) {
    UserDefaults.standard.set(path, forKey: selectedFolderDefaultsKey)
  }

  private func locateNotesStoreURL() -> URL? {
    let fm = FileManager.default
    let home = fm.homeDirectoryForCurrentUser

    var candidates: [URL] = []

    if let selectedFolderPath = UserDefaults.standard.string(forKey: selectedFolderDefaultsKey),
      !selectedFolderPath.isEmpty
    {
      let selectedFolderURL = URL(fileURLWithPath: selectedFolderPath)
      if selectedFolderURL.lastPathComponent == "NoteStore.sqlite" {
        candidates.append(selectedFolderURL)
      }
      candidates.append(
        selectedFolderURL.appendingPathComponent("NoteStore.sqlite", isDirectory: false)
      )
      candidates.append(
        selectedFolderURL.appendingPathComponent(
          "NoteStore.sqlite-wal",
          isDirectory: false
        ).deletingLastPathComponent().appendingPathComponent("NoteStore.sqlite")
      )
      candidates.append(
        selectedFolderURL
          .appendingPathComponent("Accounts", isDirectory: true)
          .appendingPathComponent("LocalAccount", isDirectory: true)
          .appendingPathComponent("NoteStore.sqlite", isDirectory: false)
      )
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

    return candidates.first(where: { fm.fileExists(atPath: $0.path) })
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

  private static func isLikelyAttachment(title: String, summary: String) -> Bool {
    let combined = "\(title) \(summary)".trimmingCharacters(in: .whitespacesAndNewlines)
    guard !combined.isEmpty else { return true }

    if combined.contains("SOLITE") || combined.contains("exec") || combined.contains("kMDItem") {
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

  nonisolated private static func saveMemory(for note: AppleNoteRecord) async -> Bool {
    let dateFormatter = DateFormatter()
    dateFormatter.dateFormat = "MMM d, yyyy"

    var content = note.title
    if !note.summary.isEmpty {
      content += "\n\n" + note.summary
    }

    do {
      _ = try await APIClient.shared.createMemory(
        content: content,
        visibility: "private",
        tags: ["apple_notes", "import", "note"],
        source: "apple_notes",
        windowTitle: "Apple Notes — \(dateFormatter.string(from: note.modifiedAt))",
        headline: note.title
      )
      return true
    } catch {
      log("AppleNotesReaderService: Failed to save raw note memory \(note.id): \(error)")
      return false
    }
  }
}
