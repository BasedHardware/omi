import AppKit
import Foundation
@preconcurrency import GRDB

/// Connector-specific import work, extracted from the connector sheet so runs
/// can be owned by `ConnectorImportRunner` and outlive the sheet. Operations
/// report live progress through the sink and return a terminal outcome;
/// status-store side effects happen at the call site.
@MainActor
enum ConnectorImportOperations {
  struct SyncResult {
    let sourceCount: Int?
    let memoryCount: Int?
    let newItems: Int?
  }

  enum Outcome {
    case success(SyncResult, message: String)
    case failure(message: String, failureClass: IntegrationConnectTelemetry.ErrorClass? = nil)
  }

  @MainActor
  static func importMemoryLog(
    text: String,
    source: OnboardingMemoryLogSource,
    extractedFixture: OnboardingMemoryLogImportService.ExtractedMemoryLog? = nil
  ) async -> Outcome {
    let result = await OnboardingMemoryLogImportService.shared.importMemoryLog(
      text,
      source: source,
      extractedFixture: extractedFixture
    )
    return memoryLogOutcome(result, source: source)
  }

  /// Maps a memory-log service result to a connector outcome, with copy
  /// that distinguishes "the pasted text had nothing durable" (fix the
  /// paste) from "the import itself broke" (retry as-is).
  static func memoryLogOutcome(
    _ result: OnboardingMemoryLogImportService.ImportOutcome,
    source: OnboardingMemoryLogSource
  ) -> Outcome {
    switch result {
    case .imported(let memories, _):
      return .success(
        SyncResult(sourceCount: nil, memoryCount: memories, newItems: memories),
        message: "Imported \(memories.formatted()) memories from \(source.displayName)."
      )
    case .noDurableMemories:
      // Not a connect failure — the parse succeeded but produced nothing
      // durable. Surfaces UI guidance as a failure but carries a distinct
      // bounded class so analytics can exclude it from the connect-failure rate.
      return .failure(
        message: "No durable memories found in that text. "
          + "Make sure you pasted \(source.displayName)'s full response, then import again.",
        failureClass: .noContent
      )
    case .failed:
      return .failure(message: "The import couldn't run. Try again.")
    }
  }

  @MainActor
  static func importGmail(progress: ConnectorImportRunner.ProgressSink) async -> Outcome {
    do {
      let emails = try await GmailReaderService.shared.readRecentEmails(
        maxResults: 300,
        query: "newer_than:365d",
        userInitiated: true
      )
      progress.update(
        title: "Importing Gmail history",
        detail: "Saving raw emails as memories and generating follow-up insights."
      )
      let rawImport = await GmailReaderService.shared.saveAsMemories(emails: emails)
      let synthesis = await GmailReaderService.shared.synthesizeFromEmails(emails: emails)
      let memoryCount = rawImport.saved + synthesis.memories
      return .success(
        SyncResult(sourceCount: emails.count, memoryCount: memoryCount, newItems: emails.count),
        message: "Imported \(emails.count.formatted()) emails and saved \(memoryCount.formatted()) memories."
      )
    } catch let error as GmailReaderError {
      return .failure(message: error.localizedDescription, failureClass: Self.failureClass(for: error))
    } catch {
      return .failure(
        message: error.localizedDescription,
        failureClass: IntegrationConnectTelemetry.ErrorClass.fromMessage(error.localizedDescription))
    }
  }

  /// Connect X via backend-mediated OAuth: open the authorize URL in the
  /// browser, then poll the backend until the account is linked. The backend
  /// kicks off the first ingest, so once connected we surface the synced count.
  @MainActor
  static func connectX(progress: ConnectorImportRunner.ProgressSink) async -> Outcome {
    // Deep link back to THIS build (dev vs prod URL schemes differ).
    let scheme = appURLScheme()
    let redirect = "\(scheme)://x/callback"

    do {
      let resp = try await APIClient.shared.xOAuthURL(successRedirectURL: redirect)
      guard resp.success, let authUrl = resp.authUrl, let url = URL(string: authUrl) else {
        return .failure(
          message: resp.error == "x_oauth_not_configured"
            ? "X connector isn't configured on the server yet."
            : "Couldn't start the X connection."
        )
      }
      guard NSWorkspace.shared.open(url) else {
        return .failure(
          message: "Couldn't open the X authorization page. Check your default browser, then try again."
        )
      }
      progress.update(
        title: "Waiting for X authorization",
        detail: "Approve access in your browser. This window updates automatically."
      )

      // Phase 1: wait until the account is linked (callback completed).
      var linked: XConnectionStatus?
      for _ in 0..<60 {
        try? await Task.sleep(for: .seconds(2))
        if let status = try? await APIClient.shared.xConnectionStatus(), status.connected {
          linked = status
          break
        }
      }
      guard let linked else {
        return .failure(message: "Didn't hear back from X. If you approved access, try again.")
      }

      let handle = linked.handle ?? "you"

      // Phase 2: the OAuth callback kicks off the first import in the
      // background. Poll while it runs, surfacing live counts, until the
      // backend marks syncing complete (or counts stop growing).
      var posts = linked.postCount ?? 0
      var memories = linked.memoryCount ?? 0
      var importCompleted = linked.syncing == false
      for _ in 0..<90 {
        let status = try? await APIClient.shared.xConnectionStatus()
        posts = status?.postCount ?? posts
        memories = status?.memoryCount ?? memories
        importCompleted = status?.syncing == false || importCompleted
        progress.update(
          title: "Importing your X data",
          detail: "Saved \(posts.formatted()) posts · \(memories.formatted()) memories so far…"
        )
        // Done once the backend clears the syncing flag, even if the account has no importable posts.
        if importCompleted { break }
        try? await Task.sleep(for: .seconds(2))
      }

      let message = xImportCompletionMessage(
        handle: handle,
        posts: posts,
        memories: memories,
        importCompleted: importCompleted
      )
      return .success(
        SyncResult(sourceCount: posts, memoryCount: memories > 0 ? memories : nil, newItems: posts),
        message: message
      )
    } catch {
      return .failure(message: error.localizedDescription)
    }
  }

  static func xImportCompletionMessage(handle: String, posts: Int, memories: Int, importCompleted: Bool) -> String {
    if posts > 0 {
      let memClause =
        memories > 0
        ? " — \(memories.formatted()) memories added. View them in Memories."
        : ". Extracted memories appear in Memories."
      return "Imported \(posts.formatted()) posts from @\(handle)\(memClause)"
    }
    if importCompleted {
      return "Connected to X as @\(handle). No posts or bookmarks were ready to import."
    }
    return "Connected to X as @\(handle). Import is still running; check back shortly."
  }

  private static func appURLScheme() -> String {
    if let urlTypes = Bundle.main.infoDictionary?["CFBundleURLTypes"] as? [[String: Any]],
      let first = urlTypes.first,
      let schemes = first["CFBundleURLSchemes"] as? [String],
      let scheme = schemes.first
    {
      return scheme
    }
    return "omi-computer"
  }

  /// Maps the connector-native Gmail error to the closed telemetry class.
  /// Pure and bounded — the enum is the sanitized form; no message text leaks.
  private static func failureClass(for error: GmailReaderError) -> IntegrationConnectTelemetry.ErrorClass {
    switch error {
    case .noBrowserFound: return .noBrowser
    case .noGmailCookies, .notSignedIn: return .notSignedIn
    case .sessionExpired, .authFailed: return .sessionExpired
    case .cookieDecryptionFailed: return .decryptFailed
    case .networkError: return .network
    case .pythonNotFound: return .unknown
    }
  }

  /// Maps the connector-native Calendar error to the closed telemetry class.
  /// Includes the `configuration` class (invalid/missing API key) that is
  /// otherwise invisible to telemetry — a real cold-launch ops blind spot.
  private static func failureClass(for error: CalendarReaderError) -> IntegrationConnectTelemetry.ErrorClass {
    switch error {
    case .noBrowserFound: return .noBrowser
    case .notSignedIn: return .notSignedIn
    case .sessionExpired: return .sessionExpired
    case .cookieDecryptionFailed: return .decryptFailed
    case .configurationError: return .configuration
    case .networkError: return .network
    case .pythonNotFound: return .unknown
    }
  }

  /// `userInitiated: false` is the unattended (background refresh) path.
  ///
  /// It performs the raw import only. Raw artifacts are idempotent — the backend
  /// dedupes them on `external_id` + `content_hash`
  /// (`backend/database/memory_imports.py`), so replaying a background pass adds
  /// nothing. LLM synthesis is *not* idempotent: it emits items with no external
  /// id, so drifting model output would mint fresh duplicate artifacts on every
  /// refresh forever. This repo has already paid for that once with a
  /// server-side purge after a mass-duplication incident.
  @MainActor
  static func importCalendar(
    progress: ConnectorImportRunner.ProgressSink,
    userInitiated: Bool = true
  ) async -> Outcome {
    do {
      let events = try await CalendarReaderService.shared.readEvents(
        daysBack: 365,
        daysForward: 30,
        maxResults: 500,
        userInitiated: userInitiated
      )
      progress.update(
        title: "Importing calendar events",
        detail: "Saving events as memories and generating action-oriented summaries."
      )
      let rawImport = await CalendarReaderService.shared.saveAsMemories(events: events, limit: 200)
      var memoryCount = rawImport.saved
      if userInitiated {
        memoryCount += await CalendarReaderService.shared.synthesizeFromEvents(events: events).memories
      }
      return .success(
        SyncResult(sourceCount: events.count, memoryCount: memoryCount, newItems: events.count),
        message: "Read \(events.count.formatted()) calendar events and saved \(memoryCount.formatted()) memories."
      )
    } catch let error as CalendarReaderError {
      return .failure(message: error.localizedDescription, failureClass: Self.failureClass(for: error))
    } catch {
      return .failure(
        message: error.localizedDescription,
        failureClass: IntegrationConnectTelemetry.ErrorClass.fromMessage(error.localizedDescription))
    }
  }

  /// Apple Notes is read through Notes.app over Apple Events, so the only
  /// recoverable access failure is the macOS Automation grant — there is no
  /// folder to pick. See `importCalendar` for why `userInitiated: false` skips
  /// synthesis.
  @MainActor
  static func importAppleNotes(
    progress: ConnectorImportRunner.ProgressSink,
    userInitiated: Bool = true
  ) async -> Outcome {
    do {
      return try await runAppleNotesImport(progress: progress, userInitiated: userInitiated)
    } catch let error as AppleNotesReaderError {
      let failureClass = IntegrationConnectTelemetry.ErrorClass(error)
      guard error.shouldPromptForAutomationPermission else {
        return .failure(message: error.localizedDescription, failureClass: failureClass)
      }
      return .failure(
        message: "Omi needs permission to control Apple Notes. Choose Allow when macOS asks, or "
          + "turn on Notes for Omi in System Settings › Privacy & Security › Automation, then import again.",
        failureClass: failureClass
      )
    } catch {
      return .failure(
        message: error.localizedDescription,
        failureClass: IntegrationConnectTelemetry.ErrorClass.fromMessage(error.localizedDescription))
    }
  }

  @MainActor
  private static func runAppleNotesImport(
    progress: ConnectorImportRunner.ProgressSink,
    userInitiated: Bool
  ) async throws -> Outcome {
    progress.update(
      title: "Importing Apple Notes",
      detail: "Reading your notes and turning useful content into memories."
    )
    let result = try await AppleNotesReaderService.shared.syncChangedNotes(userInitiated: userInitiated)
    let rawImport = await AppleNotesReaderService.shared.saveAsMemories(notes: result.changed)
    var memoryCount = rawImport.saved
    if userInitiated {
      memoryCount += await AppleNotesReaderService.shared.synthesizeFromNotes(notes: result.changed).memories
    }
    return .success(
      SyncResult(sourceCount: result.totalNotes, memoryCount: memoryCount, newItems: result.changed.count),
      message: appleNotesCompletionMessage(
        importedNotes: result.changed.count,
        totalNotes: result.totalNotes,
        memoryCount: memoryCount,
        lockedSkipped: result.lockedSkipped
      )
    )
  }

  /// Names the locked-note shortfall explicitly. Password-protected notes are
  /// invisible to the export, so without this line an under-import reads as a
  /// complete one.
  static func appleNotesCompletionMessage(
    importedNotes: Int,
    totalNotes: Int,
    memoryCount: Int,
    lockedSkipped: Int
  ) -> String {
    var message =
      "Imported \(importedNotes.formatted()) of \(totalNotes.formatted()) notes "
      + "and saved \(memoryCount.formatted()) memories."
    if lockedSkipped > 0 {
      let noun = lockedSkipped == 1 ? "note" : "notes"
      message += " (\(lockedSkipped.formatted()) locked \(noun) skipped)"
    }
    return message
  }

  /// - Parameter analyticsSurface: Who asked for this scan. Defaulted so the
  ///   user-initiated Apps-tab path is unchanged; the background refresh adapter
  ///   passes its own value so timer-driven scans do not inflate the
  ///   `import_connector_sheet` numbers a human is supposed to be behind.
  @MainActor
  static func rescanLocalFiles(analyticsSurface: String = "import_connector_sheet") async -> Outcome {
    let previousCount = await currentIndexedFileCount()
    AnalyticsManager.shared.onboardingChatToolUsed(
      tool: "scan_files",
      properties: ["surface": analyticsSurface]
    )
    let result = await ChatToolExecutor.scanLocalFiles()

    guard result.didCompleteSuccessfully, result.hasReadableUserFileTarget else {
      // A scan that could not complete proves nothing, and a previously proven
      // grant may well be what just went away — revoke it rather than let the
      // scheduler keep believing an unattended rescan is safe.
      recordLocalFilesUnattendedGrant(proven: false)
      return .failure(message: localFilesFailureLine(for: result))
    }

    recordLocalFilesUnattendedGrant(proven: result.deniedUserFolders.isEmpty)
    let updatedCount = await currentIndexedFileCount()
    let newItems = max(updatedCount - previousCount, 0)
    return .success(
      SyncResult(sourceCount: updatedCount, memoryCount: nil, newItems: newItems),
      message: localFilesStatusLine(
        indexedCount: updatedCount,
        newItems: newItems,
        deniedFolders: result.deniedUserFolders
      )
    )
  }

  /// Records whether this user-initiated scan proved a prompt-free grant. This
  /// is the only writer of `ConnectorRefreshState.unattendedGrantProven`, and
  /// therefore the only thing that can ever make local files eligible for
  /// background refresh.
  ///
  /// The scan walks `~/Downloads`, `~/Documents`, and `~/Desktop` with
  /// `FileManager`, and the *first* touch of each raises a macOS TCC dialog. So
  /// an unattended rescan is prompt-free only after a user-initiated scan has
  /// already answered every one of those dialogs — which the scan reports as no
  /// denied user folders. Recording `false` matters just as much: a folder
  /// revoked in System Settings takes the connector straight back out of the
  /// background rotation.
  private static func recordLocalFilesUnattendedGrant(proven: Bool) {
    ConnectorRefreshStateStore().recordUnattendedGrant(
      proven: proven,
      for: LocalFilesBackgroundRefreshAdapter.connectorIdentifier
    )
  }

  /// One-line user-facing summary for a completed scan. The scan outcome's
  /// `summaryText` is agent-facing context and must not be shown in the UI.
  static func localFilesStatusLine(indexedCount: Int, newItems: Int, deniedFolders: [String]) -> String {
    var line = "Indexed \(indexedCount.formatted()) files"
    if newItems > 0 {
      line += " (+\(newItems.formatted()) new)"
    }
    line += "."
    if !deniedFolders.isEmpty {
      line += " Some folders weren't scanned (\(folderList(deniedFolders))) — grant access and reindex."
    }
    return line
  }

  static func localFilesFailureLine(for outcome: ChatToolExecutor.LocalFileScanOutcome) -> String {
    guard outcome.didCompleteSuccessfully else {
      return "Indexing couldn't complete. Try again."
    }
    guard !outcome.deniedUserFolders.isEmpty else {
      return "Omi couldn't access your folders. Click Allow on the macOS permission dialogs, then reindex."
    }
    return "Omi couldn't access your folders (\(folderList(outcome.deniedUserFolders))). "
      + "Click Allow on the macOS permission dialogs, then reindex."
  }

  private static func folderList(_ folders: [String]) -> String {
    folders
      .map { $0.hasPrefix("~/") ? String($0.dropFirst(2)) : $0 }
      .joined(separator: ", ")
  }

  private static func currentIndexedFileCount() async -> Int {
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else { return 0 }
    do {
      return try await dbQueue.read { db in
        try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM indexed_files") ?? 0
      }
    } catch {
      log("ConnectorImportOperations: Failed to read indexed file count: \(error)")
      return 0
    }
  }
}
