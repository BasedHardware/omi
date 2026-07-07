import AppKit
import Foundation
import GRDB

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
        case failure(message: String)
    }

    @MainActor
    static func importMemoryLog(text: String, source: OnboardingMemoryLogSource) async -> Outcome {
        let result = await OnboardingMemoryLogImportService.shared.importMemoryLog(text, source: source)
        guard result.memories > 0 else {
            return .failure(message: "No durable memories could be extracted from that import.")
        }
        return .success(
            SyncResult(sourceCount: nil, memoryCount: result.memories, newItems: result.memories),
            message: "Imported \(result.memories.formatted()) memories from \(source.displayName)."
        )
    }

    @MainActor
    static func importGmail(progress: ConnectorImportRunner.ProgressSink) async -> Outcome {
        do {
            let emails = try await GmailReaderService.shared.readRecentEmails(
                maxResults: 300,
                query: "newer_than:365d"
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
        } catch {
            return .failure(message: error.localizedDescription)
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
            NSWorkspace.shared.open(url)
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
            for _ in 0..<90 {
                let status = try? await APIClient.shared.xConnectionStatus()
                posts = status?.postCount ?? posts
                memories = status?.memoryCount ?? memories
                progress.update(
                    title: "Importing your X data",
                    detail: "Saved \(posts.formatted()) posts · \(memories.formatted()) memories so far…"
                )
                // Done once the backend clears the syncing flag and we have data.
                if status?.syncing == false && posts > 0 { break }
                try? await Task.sleep(for: .seconds(2))
            }

            let message: String
            if posts > 0 {
                let memClause = memories > 0
                    ? " — \(memories.formatted()) memories added. View them in Memories."
                    : ". Extracted memories appear in Memories."
                message = "Imported \(posts.formatted()) posts from @\(handle)\(memClause)"
            } else {
                message = "Connected to X as @\(handle). Import is still running; check back shortly."
            }
            return .success(
                SyncResult(sourceCount: posts, memoryCount: memories > 0 ? memories : nil, newItems: posts),
                message: message
            )
        } catch {
            return .failure(message: error.localizedDescription)
        }
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

    @MainActor
    static func importCalendar(progress: ConnectorImportRunner.ProgressSink) async -> Outcome {
        do {
            let events = try await CalendarReaderService.shared.readEvents(
                daysBack: 365,
                daysForward: 30,
                maxResults: 500
            )
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
        } catch {
            return .failure(message: error.localizedDescription)
        }
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
        let notes = try await AppleNotesReaderService.shared.readRecentNotes(maxResults: 250)
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
            return .failure(message: result.summaryText)
        }

        let updatedCount = await currentIndexedFileCount()
        let newItems = max(updatedCount - previousCount, 0)
        return .success(
            SyncResult(sourceCount: updatedCount, memoryCount: nil, newItems: newItems),
            message: result.summaryText
        )
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
        let notesContainerURL = home
            .appendingPathComponent("Library/Group Containers/group.com.apple.notes", isDirectory: true)
        let groupContainersURL = home
            .appendingPathComponent("Library/Group Containers", isDirectory: true)

        let panel = NSOpenPanel()
        panel.message = "Select your Apple Notes data folder to grant access."
        panel.prompt = "Open"
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = fileManager.fileExists(atPath: notesContainerURL.path)
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
