import AppKit
import CoreServices
import Foundation
import GRDB
import SwiftUI

@MainActor
final class OnboardingPagedIntroCoordinator: ObservableObject {
  struct ScanSnapshot: Equatable {
    let fileCount: Int
    let projectNames: [String]
    let applications: [String]
    let technologies: [String]
    let folders: [String]
    let recentFiles: [String]
  }

  enum ScanState: Equatable {
    case idle
    case scanning
    case complete
    case failed(String)
  }

  private struct EnrichmentEntity {
    let label: String
    let nodeType: String
    let relation: String
  }

  private struct EnrichmentAnalysis {
    let summary: String
    let entities: [EnrichmentEntity]
    let goals: [String]
  }

  private struct MemoryDraft: Hashable {
    let content: String
    let tags: [String]
    let source: String
    let headline: String
  }

  @Published var preferredName: String
  @Published var draftName: String
  @Published var selectedLanguageCode: String
  @Published var selectedLanguageLabel: String
  @Published var customLanguage: String = ""
  @Published var scanState: ScanState = .idle
  @Published var scanStatusText: String = "Ready to scan your files."
  @Published var scanSnapshot: ScanSnapshot?
  @Published var localFileMemoriesSaved: Int = 0
  @Published var emailSummary: String = ""
  @Published var gmailInsightCount: Int = 0
  @Published var gmailMemoriesSaved: Int = 0
  @Published var calendarSummary: String = ""
  @Published var calendarInsightCount: Int = 0
  @Published var calendarMemoriesSaved: Int = 0
  @Published var appleNotesSummary: String = ""
  @Published var appleNotesInsightCount: Int = 0
  @Published var appleNotesMemoriesSaved: Int = 0
  @Published var webResearchSummary: String = ""
  @Published var isLoadingInsights = false
  @Published var insightStatusText: String = ""
  @Published var isResearchComplete = false
  @Published var goalDraft: String = ""
  @Published var suggestedGoals: [String] = []
  @Published var goalSaved = OnboardingChatPersistence.isGoalCompleted
  @Published var isSavingGoal = false
  @Published var lastActionError: String?
  @Published var chatGPTImportedMemoriesCount: Int
  @Published var claudeImportedMemoriesCount: Int
  @Published var chatGPTImportSummary: String
  @Published var claudeImportSummary: String
  @Published var importingMemoryLogSource: OnboardingMemoryLogSource?
  @Published var isSyncingAppleNotes = false

  private var insightsStarted = false
  private var gmailInsightsFinished = false
  private var calendarInsightsFinished = false
  private var appleNotesInsightsFinished = false
  private var gmailTask: Task<Void, Never>?
  private var calendarTask: Task<Void, Never>?
  private var appleNotesTask: Task<Void, Never>?
  private var webResearchTask: Task<Void, Never>?
  private var localFileMemoryImportTask: Task<Int, Never>?

  private let chatGPTImportedMemoriesKey = "onboardingChatGPTImportedMemoriesCount"
  private let chatGPTImportSummaryKey = "onboardingChatGPTImportSummary"
  private let claudeImportedMemoriesKey = "onboardingClaudeImportedMemoriesCount"
  private let claudeImportSummaryKey = "onboardingClaudeImportSummary"

  init() {
    let givenName = AuthService.shared.givenName.trimmingCharacters(in: .whitespacesAndNewlines)
    let displayName = AuthService.shared.displayName.trimmingCharacters(in: .whitespacesAndNewlines)
    let initialName = givenName.isEmpty ? (displayName.isEmpty ? "there" : displayName) : givenName

    preferredName = initialName
    draftName = initialName

    let languageCode = AssistantSettings.shared.transcriptionLanguage
    selectedLanguageCode = languageCode
    selectedLanguageLabel = Self.displayName(forLanguageCode: languageCode)

    let defaults = UserDefaults.standard
    chatGPTImportedMemoriesCount = defaults.integer(forKey: chatGPTImportedMemoriesKey)
    claudeImportedMemoriesCount = defaults.integer(forKey: claudeImportedMemoriesKey)
    chatGPTImportSummary = defaults.string(forKey: chatGPTImportSummaryKey) ?? ""
    claudeImportSummary = defaults.string(forKey: claudeImportSummaryKey) ?? ""
  }

  deinit {
    gmailTask?.cancel()
    calendarTask?.cancel()
    appleNotesTask?.cancel()
    webResearchTask?.cancel()
  }

  func prepare(appState: AppState) {
    ChatToolExecutor.onboardingAppState = appState
    appState.checkAllPermissions()

    // Clear graph only on first onboarding start, not mid-onboarding restarts.
    let isResuming = OnboardingChatPersistence.isMidOnboarding
    OnboardingChatPersistence.saveMidOnboarding()
    if !isResuming {
      Task { await KnowledgeGraphStorage.shared.clearAll() }
    }

    if scanSnapshot == nil {
      Task { await refreshSnapshotIfAvailable() }
    }
  }

  func refreshPermissions(appState: AppState) {
    ChatToolExecutor.onboardingAppState = appState
    appState.checkAllPermissions()
  }

  func clearLastActionError() {
    lastActionError = nil
  }

  func userEmail() -> String? {
    AuthState.shared.userEmail
  }

  var connectedContextSummary: String {
    let candidateSummaries = [
      condensedProfileSentence(from: webResearchSummary),
      condensedProfileSentence(from: emailSummary),
      condensedProfileSentence(from: calendarSummary),
      condensedProfileSentence(from: appleNotesSummary),
      condensedProfileSentence(from: chatGPTImportSummary),
      condensedProfileSentence(from: claudeImportSummary),
    ].compactMap { $0 }

    if !candidateSummaries.isEmpty {
      return candidateSummaries.prefix(2).joined(separator: " ")
    }

    if let snapshot = scanSnapshot, snapshot.fileCount > 0 {
      let name = preferredName == "there" ? "This person" : preferredName
      let projects = snapshot.projectNames.prefix(2)
      let technologies = snapshot.technologies.prefix(2)

      if !projects.isEmpty && !technologies.isEmpty {
        return
          "\(name) appears to be building around \(projects.joined(separator: " and ")), with daily work in \(technologies.joined(separator: " and "))."
      }

      if !projects.isEmpty {
        return "\(name) appears focused on \(projects.joined(separator: " and "))."
      }
    }

    return "Omi is still building a clearer picture from the sources connected so far."
  }

  func importedMemoryCount(for source: OnboardingMemoryLogSource) -> Int {
    switch source {
    case .chatgpt:
      chatGPTImportedMemoriesCount
    case .claude:
      claudeImportedMemoriesCount
    }
  }

  func isImportingMemoryLog(for source: OnboardingMemoryLogSource) -> Bool {
    importingMemoryLogSource == source
  }

  func copyPromptAndOpenMemoryLogSource(_ source: OnboardingMemoryLogSource) {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(source.prompt, forType: .string)
    openURLInDefaultBrowser(source.prefilledBrowserURL)
  }

  func importMemoryLog(_ rawText: String, source: OnboardingMemoryLogSource) async {
    lastActionError = nil
    importingMemoryLogSource = source
    defer { importingMemoryLogSource = nil }

    let result = await OnboardingMemoryLogImportService.shared.importMemoryLog(
      rawText, source: source)
    guard result.memories > 0 else {
      lastActionError =
        "Couldn’t extract durable memories from the pasted \(source.displayName) log."
      return
    }

    let defaults = UserDefaults.standard
    switch source {
    case .chatgpt:
      chatGPTImportedMemoriesCount = result.memories
      chatGPTImportSummary = result.profileSummary
      defaults.set(result.memories, forKey: chatGPTImportedMemoriesKey)
      defaults.set(result.profileSummary, forKey: chatGPTImportSummaryKey)
    case .claude:
      claudeImportedMemoriesCount = result.memories
      claudeImportSummary = result.profileSummary
      defaults.set(result.memories, forKey: claudeImportedMemoriesKey)
      defaults.set(result.profileSummary, forKey: claudeImportSummaryKey)
    }

    await saveGraph(
      nodes: [
        [
          "id": "integration_\(source.rawValue)", "label": source.displayName, "node_type": "thing",
          "aliases": [],
        ]
      ],
      edges: [
        [
          "source_id": "user", "target_id": "integration_\(source.rawValue)",
          "label": "shared_context_from",
        ]
      ]
    )
  }

  func selectAppleNotesFolderAndSync() async {
    lastActionError = nil

    let panel = NSOpenPanel()
    panel.title = "Select your Apple Notes data folder"
    panel.message = "Choose the Apple Notes group container so Omi can sync your notes."
    panel.prompt = "Select Folder"
    panel.canChooseFiles = false
    panel.canChooseDirectories = true
    panel.allowsMultipleSelection = false
    panel.canCreateDirectories = false

    let home = FileManager.default.homeDirectoryForCurrentUser
    let suggestedURL = home.appendingPathComponent("Library/Group Containers/group.com.apple.notes")
    if FileManager.default.fileExists(atPath: suggestedURL.path) {
      panel.directoryURL = suggestedURL
    }

    guard panel.runModal() == .OK, let selectedURL = panel.url else { return }

    await AppleNotesReaderService.shared.rememberSelectedFolder(path: selectedURL.path)
    await refreshAppleNotesInsights()
  }

  func refreshAppleNotesInsights() async {
    lastActionError = nil
    isSyncingAppleNotes = true
    defer { isSyncingAppleNotes = false }

    do {
      let notes = try await AppleNotesReaderService.shared.readRecentNotes(maxResults: 250)
      if notes.isEmpty {
        appleNotesInsightCount = 0
        appleNotesSummary = ""
        appleNotesMemoriesSaved = 0
        return
      }

      let rawImport = await AppleNotesReaderService.shared.saveAsMemories(notes: notes, limit: 200)
      let result = await AppleNotesReaderService.shared.synthesizeFromNotes(
        notes: Array(notes.prefix(120))
      )
      appleNotesInsightCount = notes.count
      appleNotesMemoriesSaved = rawImport.saved + result.memories
      appleNotesSummary =
        result.profileSummary.isEmpty
        ? "Your notes already reflect active ideas, plans, and recurring interests."
        : result.profileSummary

      if appleNotesMemoriesSaved > 0 {
        await saveGraph(
          nodes: [
            [
              "id": "integration_apple_notes", "label": "Apple Notes", "node_type": "thing",
              "aliases": [],
            ]
          ],
          edges: [
            ["source_id": "user", "target_id": "integration_apple_notes", "label": "captures_in"]
          ]
        )
      }
    } catch {
      lastActionError = error.localizedDescription
    }
  }

  func confirmPreferredName() async {
    lastActionError = nil
    let trimmed = draftName.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
      lastActionError = "Pick a name first."
      return
    }

    if trimmed != AuthService.shared.givenName, trimmed != AuthService.shared.displayName {
      let result = await executeTool(name: "set_user_preferences", arguments: ["name": trimmed])
      if result.lowercased().contains("error") {
        lastActionError = result
        return
      }
    }

    preferredName = trimmed
    await saveGraph(
      nodes: [
        [
          "id": "user", "label": trimmed, "node_type": "person",
          "aliases": [AuthService.shared.displayName],
        ]
      ],
      edges: []
    )
  }

  func selectEnglish() async {
    await setLanguage(code: "en", label: "English")
  }

  func setCustomLanguage() async {
    let trimmed = customLanguage.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
      lastActionError = "Add a language first."
      return
    }

    let normalizedCode =
      Locale.availableIdentifiers
      .compactMap { Locale(identifier: $0) }
      .first(where: { locale in
        locale.localizedString(forIdentifier: locale.identifier)?
          .localizedCaseInsensitiveContains(trimmed) == true
          || locale.localizedString(
            forLanguageCode: locale.language.languageCode?.identifier ?? "")?
            .localizedCaseInsensitiveContains(trimmed) == true
      })?
      .language
      .languageCode?
      .identifier ?? trimmed.lowercased()

    await setLanguage(code: normalizedCode, label: trimmed.capitalized)
  }

  private func setLanguage(code: String, label: String) async {
    lastActionError = nil
    let result = await executeTool(name: "set_user_preferences", arguments: ["language": code])
    if result.lowercased().contains("error") {
      lastActionError = result
      return
    }

    selectedLanguageCode = code
    selectedLanguageLabel = label

    await saveGraph(
      nodes: [
        ["id": "language_\(code)", "label": label, "node_type": "concept", "aliases": [code]]
      ],
      edges: [
        ["source_id": "user", "target_id": "language_\(code)", "label": "prefers"]
      ]
    )
  }

  private func openURLInDefaultBrowser(_ url: URL) {
    let configuration = NSWorkspace.OpenConfiguration()
    configuration.activates = true

    if let browserBundleId = LSCopyDefaultHandlerForURLScheme("https" as CFString)?
      .takeRetainedValue() as String?,
      let browserURL = NSWorkspace.shared.urlForApplication(withBundleIdentifier: browserBundleId)
    {
      NSWorkspace.shared.open([url], withApplicationAt: browserURL, configuration: configuration) {
        _, error in
        if let error {
          log(
            "OnboardingPagedIntroCoordinator: Failed opening browser URL \(url.absoluteString): \(error.localizedDescription)"
          )
          NSWorkspace.shared.open(url)
        }
      }
      return
    }

    NSWorkspace.shared.open(url)
  }

  func requestPermission(_ type: String, appState: AppState) async -> Bool {
    lastActionError = nil
    ChatToolExecutor.onboardingAppState = appState

    let result = await executeTool(name: "request_permission", arguments: ["type": type])
    refreshPermissions(appState: appState)

    if result.contains("move omi to /Applications first") {
      lastActionError = result
    }

    return isPermissionGranted(type, appState: appState)
  }

  func isPermissionGranted(_ type: String, appState: AppState) -> Bool {
    switch type {
    case "full_disk_access":
      return appState.hasFullDiskAccess
    case "microphone":
      return appState.hasMicrophonePermission
    case "accessibility":
      return appState.hasAccessibilityPermission && !appState.isAccessibilityBroken
    case "automation":
      return appState.hasAutomationPermission
    case "screen_recording":
      return appState.hasScreenRecordingPermission
    default:
      return false
    }
  }

  func startFileScanIfNeeded(appState: AppState) async {
    guard case .idle = scanState else { return }
    lastActionError = nil
    ChatToolExecutor.onboardingAppState = appState
    scanState = .scanning
    scanStatusText = "Scanning your projects and apps..."

    // Start Gmail/Calendar/web research in parallel with the file scan
    // so insights are ready by the time the user reaches the research step.
    // Must use Task.detached to avoid @MainActor serialization with the scan.
    Task.detached { await self.startBackgroundInsightsIfNeeded() }

    let result = await executeTool(name: "scan_files", arguments: [:])
    if result.lowercased().hasPrefix("error") {
      scanState = .failed(result)
      lastActionError = result
      return
    }

    await refreshSnapshotIfAvailable()
    scanState = .complete
    scanStatusText = "Your workspace is mapped."
  }

  func refreshSnapshotIfAvailable() async {
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else { return }

    do {
      let snapshot = try await dbQueue.read { db in
        let total = try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM indexed_files") ?? 0
        guard total > 0 else { return ScanSnapshot?(nil) }

        let projectIndicators = try Row.fetchAll(
          db,
          sql: """
              SELECT path
              FROM indexed_files
              WHERE filename IN ('package.json', 'Cargo.toml', 'Podfile', 'go.mod',
                'requirements.txt', 'Pipfile', 'setup.py', 'pyproject.toml',
                'build.gradle', 'pom.xml', 'CMakeLists.txt', 'Makefile',
                'Package.swift', 'Gemfile', 'composer.json', 'mix.exs', 'pubspec.yaml')
              LIMIT 12
            """)

        let apps = try Row.fetchAll(
          db,
          sql: """
              SELECT filename
              FROM indexed_files
              WHERE folder = 'Applications' AND fileExtension = 'app'
              ORDER BY filename
              LIMIT 12
            """)

        let recentFiles = try Row.fetchAll(
          db,
          sql: """
              SELECT filename
              FROM indexed_files
              WHERE filename NOT LIKE 'CleanShot %'
                AND filename NOT LIKE '.DS_Store'
              ORDER BY modifiedAt DESC
              LIMIT 10
            """)

        let extensions = try Row.fetchAll(
          db,
          sql: """
              SELECT fileExtension, COUNT(*) as count
              FROM indexed_files
              WHERE fileExtension IS NOT NULL AND fileExtension != ''
              GROUP BY fileExtension
              ORDER BY count DESC
              LIMIT 16
            """)

        let folderCounts = try Row.fetchAll(
          db,
          sql: """
              SELECT folder, COUNT(*) as count
              FROM indexed_files
              GROUP BY folder
              ORDER BY count DESC
              LIMIT 8
            """)

        let projectCandidates = try Row.fetchAll(
          db,
          sql: """
              SELECT path, folder
              FROM indexed_files
              WHERE folder IN ('Projects', 'Documents')
                AND path NOT LIKE '%/node_modules/%'
                AND path NOT LIKE '%/.git/%'
                AND path NOT LIKE '%/.build/%'
                AND path NOT LIKE '%/build/%'
                AND path NOT LIKE '%/DerivedData/%'
                AND path NOT LIKE '%/Pods/%'
              LIMIT 6000
            """)

        let indicatorProjects = projectIndicators.compactMap { row -> String? in
          guard let path = row["path"] as? String else { return nil }
          let directory = (path as NSString).deletingLastPathComponent
          let projectName = (directory as NSString).lastPathComponent
          return projectName.isEmpty ? nil : projectName
        }

        var projectScores: [String: Int] = [:]
        for project in indicatorProjects {
          projectScores[project, default: 0] += 500
        }
        for row in projectCandidates {
          guard
            let path = row["path"] as? String,
            let folder = row["folder"] as? String,
            let project = Self.projectLabel(from: path, folder: folder)
          else { continue }
          projectScores[project, default: 0] += 1
        }

        let projects =
          projectScores
          .sorted {
            if $0.value == $1.value {
              return $0.key.localizedCaseInsensitiveCompare($1.key) == .orderedAscending
            }
            return $0.value > $1.value
          }
          .map(\.key)

        let technologies =
          extensions
          .compactMap { row -> String? in
            guard let raw = row["fileExtension"] as? String else { return nil }
            return Self.technologyName(forFileExtension: raw)
          }

        let folders =
          folderCounts
          .compactMap { row -> String? in
            guard let folder = row["folder"] as? String else { return nil }
            return Self.displayFolderName(folder)
          }

        return ScanSnapshot(
          fileCount: total,
          projectNames: Array(projects.prefix(12)),
          applications: apps.compactMap {
            ($0["filename"] as? String)?.replacingOccurrences(of: ".app", with: "")
          },
          technologies: Array(Set(technologies)).sorted().prefix(10).map(\.self),
          folders: Array(folders.prefix(5)),
          recentFiles: recentFiles.compactMap { $0["filename"] as? String }
        )
      }

      guard let snapshot else { return }
      let previousSnapshot = scanSnapshot
      scanSnapshot = snapshot
      suggestedGoals = buildSuggestedGoals(from: snapshot)

      guard previousSnapshot != snapshot else { return }

      var nodes: [[String: Any]] = []
      var edges: [[String: Any]] = []

      for project in snapshot.projectNames.prefix(10) {
        let id = "project_\(slug(project))"
        nodes.append(["id": id, "label": project, "node_type": "thing", "aliases": []])
        edges.append(["source_id": "user", "target_id": id, "label": "works_on"])
      }

      for tech in snapshot.technologies.prefix(8) {
        let id = "tech_\(slug(tech))"
        nodes.append(["id": id, "label": tech, "node_type": "thing", "aliases": []])
        edges.append(["source_id": "user", "target_id": id, "label": "uses"])
      }

      for application in snapshot.applications.prefix(6) {
        let id = "app_\(slug(application))"
        nodes.append(["id": id, "label": application, "node_type": "thing", "aliases": []])
        edges.append(["source_id": "user", "target_id": id, "label": "opens"])
      }

      for folder in snapshot.folders.prefix(4) {
        let id = "folder_\(slug(folder))"
        nodes.append(["id": id, "label": folder, "node_type": "thing", "aliases": []])
        edges.append(["source_id": "user", "target_id": id, "label": "stores_work_in"])
      }

      if !nodes.isEmpty {
        await saveGraph(nodes: nodes, edges: edges)
      }

      localFileMemoriesSaved = await importLocalFileMemories(from: snapshot)
    } catch {
      logError("OnboardingPagedIntroCoordinator: Failed to load scan snapshot", error: error)
    }
  }

  func startBackgroundInsightsIfNeeded() async {
    guard !insightsStarted else { return }
    insightsStarted = true
    isLoadingInsights = true
    isResearchComplete = false
    insightStatusText = "Reading Gmail, calendar, and Apple Notes..."
    gmailInsightsFinished = false
    calendarInsightsFinished = false
    appleNotesInsightsFinished = false
    webResearchSummary = ""

    gmailTask = Task {
      do {
        let emails = try await GmailReaderService.shared.readRecentEmails(
          maxResults: 300,
          query: "newer_than:365d"
        )
        guard !Task.isCancelled else { return }

        if emails.isEmpty {
          await MainActor.run {
            self.emailSummary = ""
            self.gmailInsightCount = 0
            self.gmailMemoriesSaved = 0
            ChatToolExecutor.emailInsightsText = nil
          }
          await self.markInsightFinished(.gmail)
          return
        }

        let rawImport = await GmailReaderService.shared.saveAsMemories(emails: emails)
        let result = await GmailReaderService.shared.synthesizeFromEmails(
          emails: Array(emails.prefix(120))
        )
        guard !Task.isCancelled else { return }

        let summary =
          result.profileSummary.isEmpty
          ? "Your email suggests active follow-ups and recurring projects."
          : result.profileSummary

        await self.saveGraph(
          nodes: [
            ["id": "integration_gmail", "label": "Gmail", "node_type": "thing", "aliases": []]
          ],
          edges: [
            ["source_id": "user", "target_id": "integration_gmail", "label": "checks"]
          ]
        )

        await MainActor.run {
          self.gmailInsightCount = emails.count
          self.gmailMemoriesSaved = rawImport.saved + result.memories
          self.emailSummary = summary
          ChatToolExecutor.emailInsightsText = summary
          self.suggestedGoals = self.buildSuggestedGoals(
            from: self.scanSnapshot, email: summary, calendar: self.calendarSummary)
        }
        await self.markInsightFinished(.gmail)
      } catch {
        log(
          "OnboardingPagedIntroCoordinator: Gmail insights unavailable: \(error.localizedDescription)"
        )
        await self.markInsightFinished(.gmail)
      }
    }

    calendarTask = Task {
      do {
        let events = try await CalendarReaderService.shared.readEvents(
          daysBack: 365,
          daysForward: 90,
          maxResults: 1000
        )
        guard !Task.isCancelled else { return }

        if events.isEmpty {
          await MainActor.run {
            self.calendarSummary = ""
            self.calendarInsightCount = 0
            self.calendarMemoriesSaved = 0
            ChatToolExecutor.calendarInsightsText = nil
          }
          await self.markInsightFinished(.calendar)
          return
        }

        let rawImport = await CalendarReaderService.shared.saveAsMemories(
          events: events,
          limit: 500
        )
        let result = await CalendarReaderService.shared.synthesizeFromEvents(
          events: Array(events.prefix(150))
        )
        guard !Task.isCancelled else { return }

        let summary =
          result.profileSummary.isEmpty
          ? "Your calendar is busy enough that Omi can start surfacing deadlines and prep work."
          : result.profileSummary

        await self.saveGraph(
          nodes: [
            [
              "id": "integration_calendar", "label": "Calendar", "node_type": "thing",
              "aliases": [],
            ]
          ],
          edges: [
            ["source_id": "user", "target_id": "integration_calendar", "label": "plans_with"]
          ]
        )

        await MainActor.run {
          self.calendarInsightCount = events.count
          self.calendarMemoriesSaved = rawImport.saved + result.memories
          self.calendarSummary = summary
          ChatToolExecutor.calendarInsightsText = summary
          self.suggestedGoals = self.buildSuggestedGoals(
            from: self.scanSnapshot, email: self.emailSummary, calendar: summary)
        }
        await self.markInsightFinished(.calendar)
      } catch {
        log(
          "OnboardingPagedIntroCoordinator: Calendar insights unavailable: \(error.localizedDescription)"
        )
        await self.markInsightFinished(.calendar)
      }
    }

    appleNotesTask = Task {
      await MainActor.run {
        self.isSyncingAppleNotes = true
      }

      defer {
        Task { @MainActor in
          self.isSyncingAppleNotes = false
        }
      }

      do {
        let notes = try await AppleNotesReaderService.shared.readRecentNotes(maxResults: 250)
        guard !Task.isCancelled else { return }

        if notes.isEmpty {
          await MainActor.run {
            self.appleNotesInsightCount = 0
            self.appleNotesSummary = ""
            self.appleNotesMemoriesSaved = 0
          }
          await self.markInsightFinished(.appleNotes)
          return
        }

        let rawImport = await AppleNotesReaderService.shared.saveAsMemories(
          notes: notes,
          limit: 200
        )
        let result = await AppleNotesReaderService.shared.synthesizeFromNotes(
          notes: Array(notes.prefix(120))
        )
        guard !Task.isCancelled else { return }

        if rawImport.saved + result.memories > 0 {
          await self.saveGraph(
            nodes: [
              [
                "id": "integration_apple_notes", "label": "Apple Notes", "node_type": "thing",
                "aliases": [],
              ]
            ],
            edges: [
              ["source_id": "user", "target_id": "integration_apple_notes", "label": "captures_in"]
            ]
          )
        }

        let summary =
          result.profileSummary.isEmpty
          ? "Your notes already reflect active ideas, plans, and recurring interests."
          : result.profileSummary

        await MainActor.run {
          self.appleNotesInsightCount = notes.count
          self.appleNotesMemoriesSaved = rawImport.saved + result.memories
          self.appleNotesSummary = summary
        }
        await self.markInsightFinished(.appleNotes)
      } catch {
        log(
          "OnboardingPagedIntroCoordinator: Apple Notes insights unavailable: \(error.localizedDescription)"
        )
        await MainActor.run {
          self.appleNotesInsightCount = 0
          self.appleNotesSummary = ""
          self.appleNotesMemoriesSaved = 0
        }
        await self.markInsightFinished(.appleNotes)
      }
    }
  }

  private enum InsightSource {
    case gmail
    case calendar
    case appleNotes
  }

  private func markInsightFinished(_ source: InsightSource) async {
    switch source {
    case .gmail:
      gmailInsightsFinished = true
    case .calendar:
      calendarInsightsFinished = true
    case .appleNotes:
      appleNotesInsightsFinished = true
    }

    await maybeStartWebResearch()
  }

  private func maybeStartWebResearch() async {
    guard gmailInsightsFinished && calendarInsightsFinished && appleNotesInsightsFinished else {
      return
    }
    guard webResearchTask == nil && !isResearchComplete else { return }

    insightStatusText = "Searching the web..."

    webResearchTask = Task {
      let results = await OnboardingWebResearchService.shared.search(queries: buildWebQueries())
      guard !Task.isCancelled else { return }

      let analysis = await analyzeEnrichment(webResults: results)
      guard !Task.isCancelled else { return }

      if !analysis.entities.isEmpty {
        let nodes = analysis.entities.map { entity in
          [
            "id": "insight_\(slug(entity.label))",
            "label": entity.label,
            "node_type": entity.nodeType,
            "aliases": [],
          ] as [String: Any]
        }
        let edges = analysis.entities.map { entity in
          [
            "source_id": "user",
            "target_id": "insight_\(slug(entity.label))",
            "label": entity.relation,
          ] as [String: Any]
        }
        await saveGraph(nodes: nodes, edges: edges)
      }

      if !analysis.summary.isEmpty {
        webResearchSummary = analysis.summary
      }

      log(
        "OnboardingPagedIntroCoordinator: Enrichment goals: \(analysis.goals), summary: \(analysis.summary.prefix(100))"
      )

      if !analysis.goals.isEmpty {
        suggestedGoals = Array(
          NSOrderedSet(
            array: analysis.goals + suggestedGoals.filter { $0 != "I’ll type my own" } + [
              "I’ll type my own"
            ]
          ).array as? [String] ?? suggestedGoals
        )
      }

      isLoadingInsights = false
      isResearchComplete = true
      insightStatusText = ""
      webResearchTask = nil
    }
  }

  private func analyzeEnrichment(
    webResults: [OnboardingWebSearchResult]
  ) async -> EnrichmentAnalysis {
    let scanLines =
      scanSnapshot.map { snapshot in
        [
          "Projects: \(snapshot.projectNames.joined(separator: ", "))",
          "Applications: \(snapshot.applications.joined(separator: ", "))",
          "Technologies: \(snapshot.technologies.joined(separator: ", "))",
          "Folders: \(snapshot.folders.joined(separator: ", "))",
          "Recent files: \(snapshot.recentFiles.joined(separator: ", "))",
        ]
        .filter { !$0.hasSuffix(": ") }
        .joined(separator: "\n")
      } ?? "No file scan context."

    let webLines =
      webResults.isEmpty
      ? "No web search results."
      : webResults.prefix(6).map { result in
        "[\(result.query)] \(result.title) | \(result.snippet) | \(result.url)"
      }.joined(separator: "\n")

    let prompt = """
      You are preparing a Mac app onboarding summary.

      USER:
      Name: \(preferredName)
      Email: \(userEmail() ?? "unknown")

      FILE SCAN:
      \(scanLines)

      EMAIL SUMMARY:
      \(emailSummary.isEmpty ? "None" : emailSummary)

      CALENDAR SUMMARY:
      \(calendarSummary.isEmpty ? "None" : calendarSummary)

      APPLE NOTES SUMMARY:
      \(appleNotesSummary.isEmpty ? "None" : appleNotesSummary)

      WEB RESULTS:
      \(webLines)

      Return ONLY valid JSON:
      {
        "summary": "1-2 sentence summary",
        "entities": [
          {"label": "entity name", "node_type": "organization", "relation": "works_with"}
        ],
        "goals": [
          "specific goal suggestion"
        ]
      }

      RULES:
      - Use only facts grounded in the provided context
      - summary must describe who the user is in 1-2 crisp sentences, not source counts
      - summary should be readable in a small UI footer and must avoid bloated phrasing
      - entities: at most 12
      - node_type must be one of: person, organization, place, thing, concept
      - relation must connect the user to the entity, like works_on, uses, works_with, follows, plans_with, researches
      - goals: at most 6, concrete and specific, not generic
      - Prefer project names, organizations, tools, products, repositories, and recurring commitments
      - Favor labels that will make a graph visually informative, not generic filler
      """

    do {
      let bridge = AgentBridge(harnessMode: "piMono")
      try await bridge.start()
      defer { Task { await bridge.stop() } }

      let result = try await bridge.query(
        prompt: prompt,
        systemPrompt:
          "You are a structured onboarding research assistant. Output only valid JSON.",
        model: ModelQoS.Claude.chat,
        onTextDelta: { @Sendable _ in },
        onToolCall: { @Sendable _, _, _ in return "" },
        onToolActivity: { @Sendable _, _, _, _ in }
      )

      let responseText = sanitizeJSONResponse(result.text)
      guard
        let data = responseText.data(using: .utf8),
        let parsed = try JSONSerialization.jsonObject(with: data) as? [String: Any]
      else {
        return EnrichmentAnalysis(summary: fallbackWebSummary(webResults), entities: [], goals: [])
      }

      let summary = parsed["summary"] as? String ?? fallbackWebSummary(webResults)
      let rawEntities: [[String: Any]] = parsed["entities"] as? [[String: Any]] ?? []
      let entities: [EnrichmentEntity] = rawEntities.compactMap { raw in
        guard
          let label = raw["label"] as? String,
          let nodeType = raw["node_type"] as? String,
          let relation = raw["relation"] as? String
        else {
          return nil
        }
        return EnrichmentEntity(label: label, nodeType: nodeType, relation: relation)
      }
      let goals = (parsed["goals"] as? [String] ?? []).filter {
        !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      }

      return EnrichmentAnalysis(summary: summary, entities: entities, goals: goals)
    } catch {
      log(
        "OnboardingPagedIntroCoordinator: Enrichment analysis failed: \(error.localizedDescription)"
      )
      return EnrichmentAnalysis(summary: fallbackWebSummary(webResults), entities: [], goals: [])
    }
  }

  private func buildWebQueries() -> [String] {
    var queries: [String] = []

    if let organization = searchableOrganizationHint() {
      queries.append("\(preferredName) \(organization)")
    }

    if let project = scanSnapshot?.projectNames.first, !project.isEmpty {
      let projectQuery =
        searchableOrganizationHint().map { "\($0) \(project)" } ?? "\(preferredName) \(project)"
      queries.append(projectQuery)
    }

    if let secondProject = scanSnapshot?.projectNames.dropFirst().first, !secondProject.isEmpty {
      queries.append("\(preferredName) \(secondProject)")
    } else if let technology = scanSnapshot?.technologies.first, !technology.isEmpty {
      queries.append("\(preferredName) \(technology)")
    }

    if let technology = scanSnapshot?.technologies.first, !technology.isEmpty {
      queries.append("\(preferredName) \(technology)")
    }

    return Array(NSOrderedSet(array: queries).array as? [String] ?? queries).prefix(4).map(\.self)
  }

  private func searchableOrganizationHint() -> String? {
    guard let email = userEmail(), let domain = email.split(separator: "@").last?.lowercased()
    else {
      return nil
    }

    let publicDomains: Set<String> = [
      "gmail.com", "googlemail.com", "icloud.com", "me.com", "mac.com", "yahoo.com",
      "outlook.com", "hotmail.com", "live.com", "proton.me", "protonmail.com",
      "privaterelay.appleid.com", "privaterelay.icloud.com",
    ]

    guard !publicDomains.contains(domain) else { return nil }
    return organizationHint()
  }

  private func fallbackWebSummary(_ webResults: [OnboardingWebSearchResult]) -> String {
    guard let firstResult = webResults.first else { return "" }
    if !firstResult.snippet.isEmpty {
      return firstResult.snippet
    }
    return firstResult.title
  }

  private func condensedProfileSentence(from raw: String) -> String? {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return nil }

    let cleaned =
      trimmed
      .replacingOccurrences(of: "\n", with: " ")
      .replacingOccurrences(of: "  ", with: " ")
      .trimmingCharacters(in: .whitespacesAndNewlines)

    let sentence = cleaned.split(whereSeparator: \.isNewline).first.map(String.init) ?? cleaned
    let normalized = sentence.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty else { return nil }

    let capped =
      normalized.count > 170
      ? String(normalized.prefix(167)).trimmingCharacters(in: .whitespacesAndNewlines) + "..."
      : normalized

    return capped.hasSuffix(".") || capped.hasSuffix("!") || capped.hasSuffix("?")
      ? capped
      : capped + "."
  }

  private func sanitizeJSONResponse(_ text: String) -> String {
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

  func saveGoalIfNeeded() async {
    let trimmed = goalDraft.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
      lastActionError = "Add a goal first."
      return
    }

    guard !goalSaved else { return }

    isSavingGoal = true
    defer { isSavingGoal = false }
    lastActionError = nil

    let rawTitle = trimmed
    let aiNormalized = await GoalsAIService.shared.normalizeOnboardingGoalInput(rawTitle)
    let title = aiNormalized?.title ?? heuristicGoalTitle(rawTitle)
    guard !title.isEmpty else {
      lastActionError = "That goal needs a little more detail."
      return
    }

    let config =
      aiNormalized.map { (goalType: $0.goalType, targetValue: $0.targetValue, unit: $0.unit) }
      ?? fallbackGoalConfig(from: title)

    do {
      let goal = try await createGoalWithRetry(
        title: title,
        description: "Added from onboarding",
        goalType: config.goalType,
        targetValue: config.targetValue,
        unit: config.unit
      )
      _ = try? await GoalStorage.shared.syncServerGoal(goal)

      goalDraft = title
      goalSaved = true
      OnboardingChatPersistence.markGoalCompleted()

      await saveGraph(
        nodes: [
          ["id": "goal_\(slug(title))", "label": title, "node_type": "concept", "aliases": []]
        ],
        edges: [
          ["source_id": "user", "target_id": "goal_\(slug(title))", "label": "prioritizes"]
        ]
      )
    } catch APIError.httpError(let statusCode) where statusCode == 429 {
      logError(
        "OnboardingPagedIntroCoordinator: Goal save rate-limited (429)",
        error: APIError.httpError(statusCode: 429))
      lastActionError =
        "Too many requests right now. Skip this step or try again in a moment."
    } catch {
      logError("OnboardingPagedIntroCoordinator: Failed to save onboarding goal", error: error)
      lastActionError = error.localizedDescription
    }
  }

  /// Create a goal with retry/backoff for transient 429s. The onboarding flow can saturate
  /// Cloud Armor's per-Authorization limit through the local-file memory batch import that
  /// runs in parallel; this gives the limiter time to drain before failing the user.
  private func createGoalWithRetry(
    title: String,
    description: String,
    goalType: GoalType,
    targetValue: Double,
    unit: String?
  ) async throws -> Goal {
    let backoffsSec: [UInt64] = [1, 3, 6]
    var lastError: Error?
    for attempt in 0...backoffsSec.count {
      do {
        return try await APIClient.shared.createGoal(
          title: title,
          description: description,
          goalType: goalType,
          targetValue: targetValue,
          currentValue: 0,
          unit: unit,
          source: "onboarding_step_flow"
        )
      } catch APIError.httpError(let statusCode) where statusCode == 429 {
        lastError = APIError.httpError(statusCode: 429)
        guard attempt < backoffsSec.count else { break }
        log(
          "OnboardingPagedIntroCoordinator: createGoal 429, retrying in \(backoffsSec[attempt])s "
            + "(attempt \(attempt + 2)/\(backoffsSec.count + 1))")
        try? await Task.sleep(nanoseconds: backoffsSec[attempt] * 1_000_000_000)
      }
    }
    throw lastError ?? APIError.httpError(statusCode: 429)
  }

  func completeIntro(appState: AppState) async -> Bool {
    ChatToolExecutor.onboardingAppState = appState
    let result = await executeTool(name: "complete_onboarding", arguments: [:])
    if result.lowercased().contains("error") {
      lastActionError = result
      return false
    }
    return true
  }

  func goalSuggestionCards() -> [String] {
    if !suggestedGoals.isEmpty {
      return Array(suggestedGoals.prefix(4))
    }

    return [
      "Finish my main launch",
      "Ship the current desktop milestone",
      "Protect more focus time this week",
      "I’ll type my own",
    ]
  }

  func organizationHint() -> String? {
    guard let email = AuthState.shared.userEmail, let domain = email.split(separator: "@").last
    else {
      return nil
    }
    let cleaned = domain.replacingOccurrences(of: ".com", with: "")
      .replacingOccurrences(of: ".io", with: "")
      .replacingOccurrences(of: ".ai", with: "")
      .replacingOccurrences(of: "-", with: " ")
      .replacingOccurrences(of: ".", with: " ")
      .capitalized
    return cleaned.isEmpty ? nil : cleaned
  }

  private func buildSuggestedGoals(
    from snapshot: ScanSnapshot?,
    email: String = "",
    calendar: String = ""
  ) -> [String] {
    var suggestions: [String] = []

    // Context-aware but user-centered goals (not raw project names)
    if snapshot != nil || !email.isEmpty || !calendar.isEmpty {
      suggestions.append("Be more productive and focused every day")
    }

    if !email.isEmpty {
      suggestions.append("Stay ahead of important follow-ups")
    }

    if !calendar.isEmpty {
      suggestions.append("Create more focus time between meetings")
    }

    if snapshot != nil {
      suggestions.append("Make meaningful progress on my projects")
    }

    suggestions.append("I’ll type my own")
    return Array(NSOrderedSet(array: suggestions).array as? [String] ?? suggestions)
  }

  private func executeTool(name: String, arguments: [String: Any]) async -> String {
    await ChatToolExecutor.execute(
      ToolCall(name: name, arguments: arguments, thoughtSignature: nil)
    )
  }

  private func saveGraph(nodes: [[String: Any]], edges: [[String: Any]]) async {
    guard !nodes.isEmpty else { return }
    _ = await executeTool(
      name: "save_knowledge_graph",
      arguments: ["nodes": nodes, "edges": edges]
    )
  }

  private func importLocalFileMemories(from snapshot: ScanSnapshot) async -> Int {
    if localFileMemoriesSaved > 0 {
      return localFileMemoriesSaved
    }

    if let existingTask = localFileMemoryImportTask {
      return await existingTask.value
    }

    let task = Task<Int, Never> {
      let drafts = await buildLocalFileMemoryDrafts(from: snapshot)
      guard !drafts.isEmpty else { return 0 }

      // Batch the drafts through POST /v3/memories/batch. The previous
      // implementation fanned out 12 concurrent POST /v3/memories calls
      // per draft; with up to ~2800 drafts, that blew through Cloud
      // Armor's 120 req/min per-Authorization limit in seconds and
      // collaterally 429'd unrelated onboarding calls (goals, sync, chat).
      //
      // One batch request = one Firestore write + one embeddings call +
      // one Pinecone upsert on the server, regardless of batch size.
      let chunkSize = APIClient.memoriesBatchMaxSize
      var savedCount = 0
      var index = 0
      while index < drafts.count {
        let end = min(index + chunkSize, drafts.count)
        let chunk = drafts[index..<end].map { draft in
          MemoryBatchItem(
            content: draft.content,
            visibility: "private",
            tags: draft.tags,
            headline: draft.headline
          )
        }
        index = end

        do {
          let response = try await APIClient.shared.createMemoriesBatch(Array(chunk))
          savedCount += response.createdCount
        } catch {
          log(
            "OnboardingPagedIntroCoordinator: Failed to save local file memory batch "
              + "(\(chunk.count) items): \(error)")
        }
      }

      log("OnboardingPagedIntroCoordinator: Saved \(savedCount) local file memories")
      return savedCount
    }

    localFileMemoryImportTask = task
    let saved = await task.value
    localFileMemoryImportTask = nil
    return saved
  }

  private func buildLocalFileMemoryDrafts(from snapshot: ScanSnapshot) async -> [MemoryDraft] {
    var drafts: [MemoryDraft] = [
      MemoryDraft(
        content:
          "The user has \(snapshot.fileCount.formatted()) local files indexed across their machine.",
        tags: ["local_files", "onboarding", "profile"],
        source: "local_files",
        headline: "Local Files Overview"
      )
    ]

    for project in snapshot.projectNames.prefix(12) {
      drafts.append(
        MemoryDraft(
          content: "The user works on a local project named \(project).",
          tags: ["local_files", "onboarding", "project"],
          source: "local_files",
          headline: project
        )
      )
    }

    for technology in snapshot.technologies.prefix(8) {
      drafts.append(
        MemoryDraft(
          content: "The user's local files show active work in \(technology).",
          tags: ["local_files", "onboarding", "technology"],
          source: "local_files",
          headline: technology
        )
      )
    }

    for fileName in snapshot.recentFiles.prefix(8) {
      drafts.append(
        MemoryDraft(
          content: "A recently modified local file is named \(fileName).",
          tags: ["local_files", "onboarding", "recent_file"],
          source: "local_files",
          headline: fileName
        )
      )
    }

    if let dbQueue = await RewindDatabase.shared.getDatabaseQueue() {
      do {
        let projectDrafts = try await dbQueue.read { db -> [MemoryDraft] in
          let sql = """
            SELECT path, filename, fileExtension, folder
            FROM indexed_files
            WHERE folder IN ('Projects', 'Documents', 'Downloads')
              AND filename NOT LIKE 'CleanShot %'
              AND filename NOT LIKE '.DS_Store'
              AND path NOT LIKE '%/node_modules/%'
              AND path NOT LIKE '%/.git/%'
              AND path NOT LIKE '%/.build/%'
              AND path NOT LIKE '%/build/%'
              AND path NOT LIKE '%/DerivedData/%'
              AND path NOT LIKE '%/Pods/%'
              AND (
                fileExtension IN ('swift','dart','py','ts','tsx','js','jsx','md','mdx','json',
                                  'yaml','yml','toml','sh','txt','html','css','scss','sql',
                                  'go','rs','kt','java','cpp','c','h','hpp','ipynb','pdf')
                OR fileExtension IS NULL
              )
            ORDER BY modifiedAt DESC
            LIMIT 2800
            """

          let rows = try Row.fetchAll(db, sql: sql)
          return rows.compactMap { row in
            guard let path: String = row["path"], let filename: String = row["filename"] else {
              return nil
            }

            let folder: String = row["folder"] ?? "Files"
            let fileExtension: String = row["fileExtension"] ?? ""
            let normalizedPath = Self.normalizedLocalFilePath(path)
            let extensionSuffix = fileExtension.isEmpty ? "" : " (\(fileExtension))"

            return MemoryDraft(
              content:
                "The user's local \(folder.lowercased()) include \(normalizedPath)\(extensionSuffix).",
              tags: [
                "local_files", "onboarding", folder.lowercased(), Self.sanitizedTag(fileExtension),
              ],
              source: "local_files",
              headline: filename
            )
          }
        }
        drafts.append(contentsOf: projectDrafts)
      } catch {
        log(
          "OnboardingPagedIntroCoordinator: Failed to build detailed local file memories: \(error)")
      }
    }

    var seen = Set<MemoryDraft>()
    return drafts.filter { seen.insert($0).inserted }
  }

  nonisolated private static func normalizedLocalFilePath(_ path: String) -> String {
    if path.hasPrefix("~/") { return path }

    let home = FileManager.default.homeDirectoryForCurrentUser.path
    if path.hasPrefix(home + "/") {
      return "~/" + path.dropFirst(home.count + 1)
    }
    return path
  }

  nonisolated private static func sanitizedTag(_ tag: String) -> String {
    let trimmed = tag.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return trimmed.isEmpty ? "unknown" : trimmed.replacingOccurrences(of: " ", with: "_")
  }

  private func heuristicGoalTitle(_ text: String) -> String {
    var cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
      .replacingOccurrences(of: "\n", with: " ")
    let lower = cleaned.lowercased()
    let prefixes = [
      "my goal is ",
      "goal is ",
      "my goal: ",
      "goal: ",
      "i want to ",
      "i wanna ",
      "i need to ",
      "i will ",
      "i'm going to ",
    ]
    for prefix in prefixes where lower.hasPrefix(prefix) {
      cleaned = String(cleaned.dropFirst(prefix.count))
      break
    }
    return cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private func fallbackGoalConfig(from title: String) -> (
    goalType: GoalType, targetValue: Double, unit: String?
  ) {
    let lower = title.lowercased()
    let pattern =
      #"\b(\d+(?:\.\d+)?)\s*(k|m|b)?\s*(users?|customers?|clients?|sales?|revenue|downloads?)?\b"#
    if let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive),
      let match = regex.firstMatch(in: lower, range: NSRange(lower.startIndex..., in: lower))
    {
      let numberRange = match.range(at: 1)
      let suffixRange = match.range(at: 2)
      let unitRange = match.range(at: 3)
      if let numberSwiftRange = Range(numberRange, in: lower),
        let baseNumber = Double(lower[numberSwiftRange])
      {
        var multiplier = 1.0
        if let suffixSwiftRange = Range(suffixRange, in: lower) {
          switch lower[suffixSwiftRange] {
          case "k": multiplier = 1_000
          case "m": multiplier = 1_000_000
          case "b": multiplier = 1_000_000_000
          default: break
          }
        }
        let unit: String? = Range(unitRange, in: lower).map { String(lower[$0]) }
        return (.numeric, max(baseNumber * multiplier, 1), unit)
      }
    }

    return (.boolean, 1, nil)
  }

  nonisolated private static func displayName(forLanguageCode code: String) -> String {
    Locale.current.localizedString(forLanguageCode: code)?.capitalized ?? code.uppercased()
  }

  nonisolated private static func technologyName(forFileExtension raw: String) -> String? {
    switch raw.lowercased() {
    case "swift": return "Swift"
    case "dart": return "Flutter"
    case "ts", "tsx": return "TypeScript"
    case "js", "jsx": return "JavaScript"
    case "py": return "Python"
    case "rs": return "Rust"
    case "go": return "Go"
    case "kt": return "Kotlin"
    case "java": return "Java"
    case "rb": return "Ruby"
    case "mdx": return "Mintlify"
    default: return nil
    }
  }

  nonisolated private static func displayFolderName(_ raw: String) -> String? {
    switch raw {
    case "Projects":
      return "Projects"
    case "Documents":
      return "Documents"
    case "Downloads":
      return "Downloads"
    case "Desktop":
      return "Desktop"
    case "Applications":
      return "Apps"
    case "group.com.apple.notes":
      return "Apple Notes Store"
    default:
      return nil
    }
  }

  nonisolated private static func projectLabel(from path: String, folder: String) -> String? {
    let normalized = normalizedLocalFilePath(path)
    let components = normalized.split(separator: "/").map(String.init)

    func component(after name: String) -> String? {
      guard
        let index = components.firstIndex(where: { $0.caseInsensitiveCompare(name) == .orderedSame }
        ),
        index + 1 < components.count
      else {
        return nil
      }
      return components[index + 1]
    }

    let candidate: String?
    switch folder {
    case "Projects":
      candidate = component(after: "projects")
    case "Documents":
      candidate = component(after: "Documents")
    default:
      candidate = nil
    }

    guard let candidate else { return nil }
    let trimmed = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
    let banned = Set(["Users", "nik", "Documents", "Projects", "Downloads", "Desktop", "Library"])
    guard !trimmed.isEmpty, !banned.contains(trimmed) else { return nil }
    return trimmed
  }

  private func slug(_ value: String) -> String {
    value
      .lowercased()
      .replacingOccurrences(of: "[^a-z0-9]+", with: "_", options: .regularExpression)
      .trimmingCharacters(in: CharacterSet(charactersIn: "_"))
  }
}
