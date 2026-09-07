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
    case .imported(let memories, let failed, _):
      let message =
        failed > 0
        ? "Imported \(memories.formatted()) memories from \(source.displayName); \(failed.formatted()) couldn't be saved. Import again to retry them."
        : "Imported \(memories.formatted()) memories from \(source.displayName)."
      return .success(
        SyncResult(sourceCount: nil, memoryCount: memories, newItems: memories),
        message: message
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
    case .failed(let failure):
      return memoryLogFailureOutcome(failure)
    }
  }

  private static func memoryLogFailureOutcome(
    _ failure: OnboardingMemoryLogImportService.ImportFailure
  ) -> Outcome {
    switch failure {
    case .authentication:
      return .failure(
        message: "Your session expired. Sign in again, then retry the import.",
        failureClass: .authentication)
    case .planRequired:
      return .failure(
        message: "Memory extraction isn't available on your current plan.",
        failureClass: .authorizationDenied)
    case .rateLimited:
      return .failure(
        message: "Too many memory imports are running. Wait a minute, then try again.",
        failureClass: .rateLimit)
    case .network:
      return .failure(
        message: "Omi couldn't reach the memory service. Check your connection, then try again.",
        failureClass: .network)
    case .timeout:
      return .failure(
        message: "Memory extraction took too long. Try the import again.",
        failureClass: .timeout)
    case .server:
      return .failure(
        message: "Omi's memory service is temporarily unavailable. Try again shortly.",
        failureClass: .server)
    case .invalidResponse:
      return .failure(
        message: "Omi couldn't read the extracted memories. Try the import again.",
        failureClass: .invalidResponse)
    case .requestRejected:
      return .failure(
        message: "The memory service rejected this import. Check the pasted text, then try again.",
        failureClass: .invalidResponse)
    case .saveFailed:
      return .failure(
        message: "Memories were extracted, but Omi couldn't save them. Check your connection, then try again.",
        failureClass: .unknown)
    case .fixtureUnavailable:
      return .failure(
        message: "This import test is only available in development builds.",
        failureClass: .configuration)
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

  @MainActor
  static func importCalendar(progress: ConnectorImportRunner.ProgressSink) async -> Outcome {
    do {
      let events = try await CalendarReaderService.shared.readEvents(
        daysBack: 365,
        daysForward: 30,
        maxResults: 500,
        userInitiated: true
      )
      return await saveCalendarEvents(events, progress: progress)
    } catch let error as CalendarReaderError {
      // Every `CalendarReaderError` means the browser-cookie reader found no
      // usable Google session on this machine, and `readEvents` only reaches it
      // when the account has no OAuth grant either. Both sources are exhausted,
      // so "try again" is not advice — nothing about the machine has changed.
      // Google's own consent screen is the one path that does not depend on
      // which browser is installed or whether its cookies can be decrypted.
      return await connectCalendarViaOAuth(progress: progress, cookieFailure: error)
    } catch {
      return .failure(
        message: error.localizedDescription,
        failureClass: IntegrationConnectTelemetry.ErrorClass.fromMessage(error.localizedDescription))
    }
  }

  /// Backend-mediated Google OAuth, same shape as `connectX`: open the consent
  /// URL, poll until the grant lands, then read through it.
  @MainActor
  private static func connectCalendarViaOAuth(
    progress: ConnectorImportRunner.ProgressSink,
    cookieFailure: CalendarReaderError
  ) async -> Outcome {
    let authURL: URL
    do {
      authURL = try await APIClient.shared.googleCalendarOAuthURL()
    } catch {
      // Server-side OAuth is unavailable, so the cookie reader's own diagnosis
      // is still the most actionable thing the user can be told.
      return .failure(
        message: cookieFailure.localizedDescription,
        failureClass: Self.failureClass(for: cookieFailure))
    }

    guard NSWorkspace.shared.open(authURL) else {
      return .failure(
        message: "Couldn't open the Google sign-in page. Check your default browser, then try again.",
        failureClass: .noBrowser)
    }

    progress.update(
      title: "Waiting for Google sign-in",
      detail: "Approve calendar access in your browser. This window updates automatically."
    )

    for _ in 0..<60 {
      try? await Task.sleep(for: .seconds(2))
      guard await CalendarReaderService.shared.hasGoogleGrant() else { continue }
      progress.update(
        title: "Importing calendar events",
        detail: "Reading past events and upcoming commitments for memory extraction."
      )
      do {
        let events =
          try await CalendarReaderService.shared.readEventsViaGrant(
            daysBack: 365,
            daysForward: 30,
            maxResults: 500
          ) ?? []
        return await saveCalendarEvents(events, progress: progress)
      } catch {
        return .failure(
          message: "Connected to Google, but reading your calendar failed. Try Sync now.",
          failureClass: IntegrationConnectTelemetry.ErrorClass.fromMessage(error.localizedDescription))
      }
    }

    return .failure(
      message: "Didn't hear back from Google. If you approved access, try again.",
      failureClass: .notSignedIn)
  }

  @MainActor
  private static func saveCalendarEvents(
    _ events: [CalendarEvent],
    progress: ConnectorImportRunner.ProgressSink
  ) async -> Outcome {
    progress.update(
      title: "Importing calendar events",
      detail: "Saving events as memories and generating action-oriented summaries."
    )
    let rawImport = await CalendarReaderService.shared.saveAsMemories(events: events, limit: 200)
    let synthesis = await CalendarReaderService.shared.synthesizeFromEvents(events: events)
    let memoryCount = rawImport.saved + synthesis.memories
    return .success(
      SyncResult(sourceCount: events.count, memoryCount: memoryCount, newItems: events.count),
      message: "Read \(events.count.formatted()) calendar events and saved \(memoryCount.formatted()) memories."
    )
  }

  @MainActor
  static func importAppleNotes(progress: ConnectorImportRunner.ProgressSink) async -> Outcome {
    do {
      return try await runAppleNotesImport(progress: progress)
    } catch let error as AppleNotesReaderError {
      guard error.shouldPromptForFolderSelection else {
        return .failure(message: error.localizedDescription)
      }
      switch await selectAppleNotesFolder() {
      case .denied(let message):
        return .failure(message: message ?? error.localizedDescription)
      case .granted:
        do {
          return try await runAppleNotesImport(progress: progress)
        } catch {
          return .failure(message: error.localizedDescription)
        }
      }
    } catch {
      return .failure(message: error.localizedDescription)
    }
  }

  @MainActor
  private static func runAppleNotesImport(progress: ConnectorImportRunner.ProgressSink) async throws -> Outcome {
    progress.update(
      title: "Importing Apple Notes",
      detail: "Reading recent notes and turning useful content into memories."
    )
    let notes = try await AppleNotesReaderService.shared.readRecentNotes(
      maxResults: 250,
      userInitiated: true
    )
    let rawImport = await AppleNotesReaderService.shared.saveAsMemories(notes: notes, limit: 200)
    let synthesis = await AppleNotesReaderService.shared.synthesizeFromNotes(notes: notes)
    let memoryCount = rawImport.saved + synthesis.memories
    return .success(
      SyncResult(sourceCount: notes.count, memoryCount: memoryCount, newItems: notes.count),
      message: "Imported \(notes.count.formatted()) notes and saved \(memoryCount.formatted()) memories."
    )
  }

  @MainActor
  static func rescanLocalFiles() async -> Outcome {
    let previousCount = await currentIndexedFileCount()
    AnalyticsManager.shared.onboardingChatToolUsed(
      tool: "scan_files",
      properties: ["surface": "import_connector_sheet"]
    )
    let result = await ChatToolExecutor.scanLocalFiles()

    guard result.didCompleteSuccessfully, result.hasReadableUserFileTarget else {
      return .failure(message: localFilesFailureLine(for: result))
    }

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

  private enum FolderSelection {
    case granted
    /// nil message means the user cancelled the panel; the caller falls
    /// back to the error that prompted the selection.
    case denied(message: String?)
  }

  @MainActor
  private static func selectAppleNotesFolder() async -> FolderSelection {
    let fileManager = FileManager.default
    let home = fileManager.homeDirectoryForCurrentUser
    let notesContainerURL =
      home
      .appendingPathComponent("Library/Group Containers/group.com.apple.notes", isDirectory: true)
    let groupContainersURL =
      home
      .appendingPathComponent("Library/Group Containers", isDirectory: true)

    let panel = NSOpenPanel()
    panel.message = "Select your Apple Notes data folder to grant access."
    panel.prompt = "Open"
    panel.canChooseFiles = false
    panel.canChooseDirectories = true
    panel.allowsMultipleSelection = false
    panel.directoryURL =
      fileManager.fileExists(atPath: notesContainerURL.path)
      ? notesContainerURL
      : groupContainersURL

    guard panel.runModal() == .OK, let selectedURL = panel.url else {
      return .denied(message: nil)
    }

    do {
      _ = try await AppleNotesReaderService.shared.validateSelectedFolder(path: selectedURL.path)
      return .granted
    } catch {
      return .denied(message: error.localizedDescription)
    }
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
