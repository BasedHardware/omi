import Foundation

/// One Apple Note as Omi imports it.
///
/// `id` is the stable note key (`AppleNotesSyncState.noteKey(fromAppleScriptID:)`),
/// not the raw AppleScript id, so an external id survives a CoreData store
/// rebuild. `body` is the real note text — the previous store-scraping reader
/// carried only a `summary`, which is why imported notes read as titles with no
/// content.
struct AppleNoteRecord: Identifiable, Sendable, Equatable {
  let id: String
  let title: String
  let body: String
  let bodyTruncated: Bool
  let folder: String?
  let createdAt: Date
  let modifiedAt: Date

  /// First 200 characters of the body with runs of whitespace collapsed.
  var snippet: String {
    let collapsed = body.replacingOccurrences(
      of: #"\s+"#,
      with: " ",
      options: .regularExpression
    ).trimmingCharacters(in: .whitespacesAndNewlines)
    return String(collapsed.prefix(200))
  }
}

enum AppleNotesReaderError: LocalizedError, Equatable {
  /// A passive (non user-initiated) read refused to proceed. The reason code is
  /// intentionally the legacy `user_initiated_read_required` string so existing
  /// telemetry queries and status surfaces keep working.
  case passiveReadDeclined
  case automationPermissionDenied
  case automationPermissionUndetermined
  case notesAppUnavailable
  case readTimedOut(seconds: TimeInterval)
  case readFailed(reason: String)
  case malformedResponse(reason: String)

  var errorDescription: String? {
    switch self {
    case .passiveReadDeclined:
      return "Apple Notes stays disconnected until you choose Connect or Import."
    case .automationPermissionDenied:
      return
        "Omi needs permission to control Apple Notes. Allow Omi under System Settings › Privacy & Security › Automation, then try again."
    case .automationPermissionUndetermined:
      return "Choose Connect or Import so macOS can ask for permission to read Apple Notes."
    case .notesAppUnavailable:
      return "Apple Notes could not be started, so Omi could not read your notes."
    case .readTimedOut(let seconds):
      return "Reading Apple Notes timed out after \(Int(seconds)) seconds."
    case .readFailed(let reason):
      return "Apple Notes could not be read: \(reason)"
    case .malformedResponse(let reason):
      return "Apple Notes returned unreadable data: \(reason)"
    }
  }

  var reasonCode: String {
    switch self {
    case .passiveReadDeclined:
      return "user_initiated_read_required"
    case .automationPermissionDenied:
      return "automation_permission_denied"
    case .automationPermissionUndetermined:
      return "automation_permission_undetermined"
    case .notesAppUnavailable:
      return "notes_app_unavailable"
    case .readTimedOut:
      return "notes_read_timed_out"
    case .readFailed:
      return "notes_read_failed"
    case .malformedResponse:
      return "malformed_response"
    }
  }

  /// True only for the two states the user can resolve by granting automation
  /// access. Everything else is a plain error, not an access prompt.
  var shouldPromptForAutomationPermission: Bool {
    switch self {
    case .automationPermissionDenied, .automationPermissionUndetermined:
      return true
    case .passiveReadDeclined, .notesAppUnavailable, .readTimedOut, .readFailed, .malformedResponse:
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
      return .error(message: "Apple Notes could not be read.", reasonCode: "unknown")
    }

    let message = error.localizedDescription
    if error.shouldPromptForAutomationPermission {
      return .needsAccess(message: message, reasonCode: error.reasonCode)
    }
    return .error(message: message, reasonCode: error.reasonCode)
  }
}

/// Result of one incremental sync pass.
///
/// `deletedKeys` reports notes that disappeared from Apple Notes since the last
/// pass. Omi records the disappearance locally and stops tracking them, but does
/// **not** delete the corresponding remote import evidence: remote deletion is a
/// separate, destructive capability that needs its own authorization path and is
/// out of scope for the reader.
struct AppleNotesSyncResult: Sendable, Equatable {
  let changed: [AppleNoteRecord]
  let totalNotes: Int
  let deletedKeys: [String]
  let lockedSkipped: Int
  let folderMode: AppleNotesSnapshot.FolderMode
}

/// Reads Apple Notes through the scriptable Notes app.
///
/// The previous implementation opened `NoteStore.sqlite` with GRDB and asked for
/// a "select the group container" folder grant. That path returned title +
/// summary only, dropped most of the library to attachment heuristics, and broke
/// whenever Apple changed the private schema. This one asks Notes itself, in two
/// bulk passes, and keeps a content-hashed manifest so repeat syncs stay cheap.
actor AppleNotesReaderService {
  static let shared = AppleNotesReaderService()

  /// Manifest is small and cheap; the body export walks the whole library.
  private static let manifestTimeoutSeconds: TimeInterval = 20
  private static let fullExportTimeoutSeconds: TimeInterval = 90
  private static let maxBodyCharsCeiling = 100_000
  private static let maxResultsCeiling = 20_000
  private static let defaultMaxFolders = 200

  /// Bounds for the LLM synthesis digest. 120 notes × 300 characters keeps the
  /// prompt around 50KB; the unbounded version built a ~1MB prompt from a real
  /// library and was rejected by the provider.
  private static let synthesisNoteLimit = 120
  private static let synthesisExcerptLimit = 300
  private static let synthesisEntrySeparator = "\n---\n"

  private let runner: AppleNotesScriptRunning
  private let gate: AppleNotesAutomationGate
  private let syncState: AppleNotesSyncStateStoring
  private let diagnostics: AppleNotesDiagnosticsRecording
  private let now: @Sendable () -> Date

  init(
    runner: AppleNotesScriptRunning = OSAScriptRunner(),
    gate: AppleNotesAutomationGate = SystemAppleNotesAutomationGate(),
    syncState: AppleNotesSyncStateStoring = FileAppleNotesSyncStateStore(),
    diagnostics: AppleNotesDiagnosticsRecording = DesktopAppleNotesDiagnostics(),
    now: @escaping @Sendable () -> Date = { Date() }
  ) {
    self.runner = runner
    self.gate = gate
    self.syncState = syncState
    self.diagnostics = diagnostics
    self.now = now
  }

  // MARK: - Reads

  /// Full library read. Every note in the export is returned — no attachment
  /// heuristics, no folder filter.
  func readAllNotes(
    maxResults: Int = 5_000,
    maxBodyChars: Int = 8_000,
    userInitiated: Bool
  ) async throws -> [AppleNoteRecord] {
    let boundedMaxResults = min(max(maxResults, 0), Self.maxResultsCeiling)
    guard boundedMaxResults > 0 else { return [] }

    try await prepareAutomation(userInitiated: userInitiated)
    let snapshot = try await runFullExport(maxBodyChars: maxBodyChars)
    return Array(snapshot.notes.prefix(boundedMaxResults))
  }

  /// Incremental sync. Runs the cheap manifest first and only pays for the body
  /// export when the manifest says something actually moved.
  func syncChangedNotes(
    maxBodyChars: Int = 8_000,
    userInitiated: Bool
  ) async throws -> AppleNotesSyncResult {
    try await prepareAutomation(userInitiated: userInitiated)

    let manifest = try await runManifest()
    let manifestByKey = Dictionary(manifest.map { ($0.key, $0) }, uniquingKeysWith: { _, latest in latest })

    var entries: [String: AppleNotesSyncState.Entry]
    if let priorState = await syncState.load() {
      entries = priorState.entries
    } else {
      // Missing, unreadable, or schema-mismatched state. Re-importing the whole
      // library is correct-but-expensive, so it is a recorded fallback rather
      // than a silent behavior change.
      entries = [:]
      await diagnostics.recordFallback(
        area: "connector_sync",
        from: "incremental",
        to: "full_resync",
        reason: "sync_state_unreadable",
        outcome: .recovered
      )
    }

    let deletedKeys = entries.keys.filter { manifestByKey[$0] == nil }.sorted()
    for key in deletedKeys {
      entries.removeValue(forKey: key)
    }

    let changedKeys = manifest.filter { entry in
      guard let stored = entries[entry.key] else { return true }
      return stored.modifiedAt != entry.modifiedAt
    }.map(\.key)

    guard !changedKeys.isEmpty else {
      await syncState.save(AppleNotesSyncState(lastSyncedAt: now(), entries: entries))
      log("AppleNotesReaderService: manifest unchanged (notes=\(manifest.count)); skipped body export")
      return AppleNotesSyncResult(
        changed: [],
        totalNotes: manifest.count,
        deletedKeys: deletedKeys,
        lockedSkipped: 0,
        folderMode: .skipped
      )
    }

    let snapshot = try await runFullExport(maxBodyChars: maxBodyChars)
    let changedSet = Set(changedKeys)
    let exportedKeys = Set(snapshot.notes.map(\.id))

    var changed: [AppleNoteRecord] = []
    for note in snapshot.notes where changedSet.contains(note.id) {
      let contentHash = AppleNotesSyncState.contentHash(title: note.title, body: note.body)
      let alreadyImported = entries[note.id]?.contentHash == contentHash
      entries[note.id] = AppleNotesSyncState.Entry(modifiedAt: note.modifiedAt, contentHash: contentHash)
      // Notes bumps the modification date for folder moves and other metadata
      // edits. Identical content means there is nothing new to import.
      guard !alreadyImported else { continue }
      changed.append(note)
    }

    // Password-protected notes appear in the manifest but never in the export.
    // Without an entry they would look "changed" on every future pass and force
    // the expensive body export forever.
    for key in changedKeys where !exportedKeys.contains(key) {
      guard let manifestEntry = manifestByKey[key] else { continue }
      entries[key] = AppleNotesSyncState.Entry(modifiedAt: manifestEntry.modifiedAt, contentHash: "")
    }

    await syncState.save(AppleNotesSyncState(lastSyncedAt: now(), entries: entries))
    log(
      "AppleNotesReaderService: sync changed=\(changed.count) deleted=\(deletedKeys.count) "
        + AppleNotesOutcomeParser.diagnosticsLine(snapshot)
    )

    return AppleNotesSyncResult(
      changed: changed,
      totalNotes: manifest.count,
      deletedKeys: deletedKeys,
      lockedSkipped: snapshot.lockedSkipped,
      folderMode: snapshot.folderMode
    )
  }

  /// Functional probe: does the connector actually work right now? Uses the
  /// cheap manifest, so an empty library answers `connected(noteCount: 0)`
  /// rather than looking like a broken connector.
  func connectionStatus(userInitiated: Bool) async -> AppleNotesConnectionStatus {
    do {
      try await prepareAutomation(userInitiated: userInitiated)
      let manifest = try await runManifest()
      return .connected(noteCount: manifest.count, verifiedAt: now())
    } catch let error as AppleNotesReaderError {
      switch Self.classifyReadOutcome(noteCount: nil, error: error) {
      case .readable(let noteCount):
        return .connected(noteCount: noteCount, verifiedAt: now())
      case .needsAccess(let message, let reasonCode):
        return .needsAccess(message: message, reasonCode: reasonCode)
      case .error(let message, let reasonCode):
        return .error(message: message, reasonCode: reasonCode)
      }
    } catch {
      return .error(message: error.localizedDescription, reasonCode: "notes_read_failed")
    }
  }

  nonisolated static func classifyReadOutcome(noteCount: Int?, error: AppleNotesReaderError?) -> AppleNotesReadOutcome {
    AppleNotesReadOutcome.classify(noteCount: noteCount, error: error)
  }

  // MARK: - Import

  func saveAsMemories(notes: [AppleNoteRecord]) async -> (saved: Int, failed: Int) {
    guard !notes.isEmpty else { return (0, 0) }

    let dateFormatter = DateFormatter()
    dateFormatter.dateFormat = "MMM d, yyyy"

    let artifacts = notes.map { note -> ImportEvidenceBatchItem in
      var metadata: [String: String] = [
        "import_kind": "note",
        "truncated": note.bodyTruncated ? "true" : "false",
        "window_title": "Apple Notes — \(dateFormatter.string(from: note.modifiedAt))",
      ]
      // Only attach a folder when the export actually mapped folders; a missing
      // folder in skipped mode means "unknown", not "no folder".
      if let folder = note.folder, !folder.isEmpty {
        metadata["folder"] = folder
      }
      return ImportEvidenceBatchItem(
        externalId: "apple_notes:\(note.id)",
        occurredAt: note.modifiedAt,
        title: note.title,
        snippet: note.snippet,
        content: note.title + "\n\n" + note.body,
        contentHash: AppleNotesSyncState.contentHash(title: note.title, body: note.body),
        metadata: metadata
      )
    }

    let legacyMemories = notes.map { note in
      MemoryBatchItem(
        content: note.title + "\n\n" + note.body,
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

  func synthesizeFromNotes(notes: [AppleNoteRecord]) async -> (memories: Int, profileSummary: String) {
    guard !notes.isEmpty else { return (0, "") }

    let digest = Self.synthesisDigest(notes)
    let synthesisPrompt = """
      Analyze these Apple Notes entries and extract profile information about the user.

      APPLE NOTES:
      \(digest)

      Respond ONLY with valid JSON (no markdown, no code fences):
      {
        "memories": [
          "clear factual statement about the user"
        ],
        "profile": "2-3 sentence summary of what these notes say about the user"
      }

      RULES:
      - Extract 8-12 memories grounded in the note titles and bodies
      - Focus on plans, projects, interests, shopping intent, relationships, routines, and recurring ideas
      - Ignore screenshot noise, OCR garbage, duplicate lines, and generic UI text
      - Each memory should be one concise third-person factual statement
      - Do not invent details not supported by the notes
      """

    // Retry the synthesis (bridge/LLM call) on transient failure instead of
    // silently dropping the whole import. Each attempt uses a fresh bridge.
    let maxAttempts = 2
    for attempt in 1...maxAttempts {
      do {
        // Fault-injection hook for the retry path. The companion
        // `forceSynthesisFail` UserDefaults literal was dropped with the move:
        // typed keys live in `DefaultsKey`, and the environment variable already
        // covers every way this switch is actually used.
        if ProcessInfo.processInfo.environment["OMI_FORCE_SYNTHESIS_FAIL"] == "1" {
          throw NSError(
            domain: "Synthesis", code: -1, userInfo: [NSLocalizedDescriptionKey: "forced synthesis failure"])
        }
        let result = try await AgentClient.run(
          surface: .service("apple_notes_reader"),
          prompt: synthesisPrompt,
          model: ModelQoS.Claude.synthesis,
          systemPrompt: "You extract high-signal user facts from Apple Notes. Output only valid JSON.",
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

  /// Bounded prompt input: at most 120 notes, at most a 300-character excerpt
  /// each. A real library is ~840 notes × 8,000 characters, which becomes a
  /// ~1MB prompt if fed in whole.
  nonisolated static func synthesisDigest(_ notes: [AppleNoteRecord]) -> String {
    notes.prefix(synthesisNoteLimit)
      .map { note in
        let excerpt =
          note.body
          .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
          .trimmingCharacters(in: .whitespacesAndNewlines)
        return note.title + "\n" + String(excerpt.prefix(synthesisExcerptLimit))
      }
      .joined(separator: synthesisEntrySeparator)
  }

  // MARK: - Private

  /// Permission and lifecycle preconditions for addressing Apple Events at Notes.
  ///
  /// A passive caller must never trigger a TCC dialog, so it requires an
  /// already-granted status — sending the event *is* what prompts. Denied is
  /// terminal for passive and user-initiated callers alike.
  private func prepareAutomation(userInitiated: Bool) async throws {
    let status = await gate.permissionStatus()
    if status == -1743 {
      throw AppleNotesReaderError.automationPermissionDenied
    }
    if status != noErr {
      guard userInitiated else {
        await diagnostics.recordFallback(
          area: "connector_sync",
          from: "live_probe",
          to: "cached_status",
          reason: "policy",
          outcome: .degraded
        )
        throw status == -1744
          ? AppleNotesReaderError.automationPermissionUndetermined
          : AppleNotesReaderError.passiveReadDeclined
      }
    }

    if await gate.isNotesRunning() == false {
      guard await gate.launchNotesInBackground() else {
        throw AppleNotesReaderError.notesAppUnavailable
      }
    }
  }

  private func runManifest() async throws -> [AppleNotesManifestEntry] {
    let result = try await execute(
      source: AppleNotesScript.manifest,
      environment: [:],
      timeoutSeconds: Self.manifestTimeoutSeconds
    )
    switch AppleNotesOutcomeParser.parseManifest(result.stdout) {
    case .success(let entries):
      return entries
    case .failure(let error):
      throw error
    }
  }

  private func runFullExport(maxBodyChars: Int) async throws -> AppleNotesSnapshot {
    // Clamp before the value crosses the process boundary: the script reads this
    // from the environment, and a zero or negative cap would export either
    // nothing or an unbounded body.
    let boundedBodyChars = min(max(maxBodyChars, 1), Self.maxBodyCharsCeiling)
    let result = try await execute(
      source: AppleNotesScript.fullExport,
      environment: [
        AppleNotesScript.maxBodyCharsEnvironmentKey: String(boundedBodyChars),
        AppleNotesScript.maxFoldersEnvironmentKey: String(Self.defaultMaxFolders),
      ],
      timeoutSeconds: Self.fullExportTimeoutSeconds
    )
    switch AppleNotesOutcomeParser.parse(result.stdout, maxBodyChars: boundedBodyChars) {
    case .failure(let error):
      throw error
    case .success(let snapshot):
      if snapshot.folderMode == .skipped {
        // Folder attribution costs a per-folder note-id loop (~1.4s for 75
        // folders). Above the cap the import continues without folder names.
        await diagnostics.recordFallback(
          area: "connector_sync",
          from: "folders_mapped",
          to: "folders_skipped",
          reason: "policy",
          outcome: .degraded
        )
      }
      return snapshot
    }
  }

  /// Runs a script and turns a transport failure or a non-zero exit into a
  /// classified reader error. Timeouts and non-zero exits are hard failures:
  /// there is no degraded Apple Notes read to fall back to, so neither records
  /// fallback telemetry.
  private func execute(
    source: String,
    environment: [String: String],
    timeoutSeconds: TimeInterval
  ) async throws -> AppleNotesScriptResult {
    let result: AppleNotesScriptResult
    do {
      result = try await runner.run(
        source: source,
        environment: environment,
        timeoutSeconds: timeoutSeconds
      )
    } catch let error as AppleNotesScriptRunnerError {
      switch error {
      case .timedOut(let seconds):
        throw AppleNotesReaderError.readTimedOut(seconds: seconds)
      case .launchFailed(let reason):
        throw AppleNotesReaderError.readFailed(reason: reason)
      }
    }

    guard result.terminationStatus == 0 else {
      throw AppleNotesOutcomeParser.classify(
        stderr: result.stderr,
        terminationStatus: result.terminationStatus
      )
    }
    return result
  }

  private static func extractJSONObject(from text: String) -> String {
    var responseText = text.trimmingCharacters(in: .whitespacesAndNewlines)

    if responseText.hasPrefix("```") {
      if let firstNewline = responseText.firstIndex(of: "\n") {
        responseText = String(responseText[responseText.index(after: firstNewline)...])
      }
      if responseText.hasSuffix("```") {
        responseText = String(responseText.dropLast(3)).trimmingCharacters(in: .whitespacesAndNewlines)
      }
    }

    if let braceIndex = responseText.firstIndex(of: "{") {
      responseText = String(responseText[braceIndex...])
    }

    return responseText.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
