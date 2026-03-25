import Foundation
import GRDB
import SwiftUI

@MainActor
final class OnboardingPagedIntroCoordinator: ObservableObject {
  struct ScanSnapshot {
    let fileCount: Int
    let projectNames: [String]
    let applications: [String]
    let technologies: [String]
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

  @Published var preferredName: String
  @Published var draftName: String
  @Published var selectedLanguageCode: String
  @Published var selectedLanguageLabel: String
  @Published var customLanguage: String = ""
  @Published var scanState: ScanState = .idle
  @Published var scanStatusText: String = "Ready to scan your files."
  @Published var scanSnapshot: ScanSnapshot?
  @Published var emailSummary: String = ""
  @Published var calendarSummary: String = ""
  @Published var webResearchSummary: String = ""
  @Published var isLoadingInsights = false
  @Published var insightStatusText: String = ""
  @Published var isResearchComplete = false
  @Published var goalDraft: String = ""
  @Published var suggestedGoals: [String] = []
  @Published var goalSaved = OnboardingChatPersistence.isGoalCompleted
  @Published var isSavingGoal = false
  @Published var lastActionError: String?

  private var insightsStarted = false
  private var gmailInsightsFinished = false
  private var calendarInsightsFinished = false
  private var gmailTask: Task<Void, Never>?
  private var calendarTask: Task<Void, Never>?
  private var webResearchTask: Task<Void, Never>?

  init() {
    let givenName = AuthService.shared.givenName.trimmingCharacters(in: .whitespacesAndNewlines)
    let displayName = AuthService.shared.displayName.trimmingCharacters(in: .whitespacesAndNewlines)
    let initialName = givenName.isEmpty ? (displayName.isEmpty ? "there" : displayName) : givenName

    preferredName = initialName
    draftName = initialName

    let languageCode = AssistantSettings.shared.transcriptionLanguage
    selectedLanguageCode = languageCode
    selectedLanguageLabel = Self.displayName(forLanguageCode: languageCode)
  }

  deinit {
    gmailTask?.cancel()
    calendarTask?.cancel()
    webResearchTask?.cancel()
  }

  func prepare(appState: AppState) {
    ChatToolExecutor.onboardingAppState = appState
    OnboardingChatPersistence.saveMidOnboarding()
    appState.checkAllPermissions()

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
    case "notifications":
      return appState.hasNotificationPermission
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

    let result = await executeTool(name: "scan_files", arguments: [:])
    if result.lowercased().hasPrefix("error") {
      scanState = .failed(result)
      lastActionError = result
      return
    }

    await refreshSnapshotIfAvailable()
    scanState = .complete
    scanStatusText = "Your workspace is mapped."
    await startBackgroundInsightsIfNeeded()
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
              WHERE folder = '/Applications' AND fileExtension = 'app'
              ORDER BY filename
              LIMIT 8
            """)

        let recentFiles = try Row.fetchAll(
          db,
          sql: """
              SELECT filename
              FROM indexed_files
              ORDER BY modifiedAt DESC
              LIMIT 6
            """)

        let extensions = try Row.fetchAll(
          db,
          sql: """
              SELECT fileExtension, COUNT(*) as count
              FROM indexed_files
              WHERE fileExtension IS NOT NULL AND fileExtension != ''
              GROUP BY fileExtension
              ORDER BY count DESC
              LIMIT 12
            """)

        let projects = projectIndicators.compactMap { row -> String? in
          guard let path = row["path"] as? String else { return nil }
          let directory = (path as NSString).deletingLastPathComponent
          let projectName = (directory as NSString).lastPathComponent
          return projectName.isEmpty ? nil : projectName
        }

        let technologies =
          extensions
          .compactMap { row -> String? in
            guard let raw = row["fileExtension"] as? String else { return nil }
            return Self.technologyName(forFileExtension: raw)
          }

        return ScanSnapshot(
          fileCount: total,
          projectNames: Array(Set(projects)).sorted().prefix(6).map(\.self),
          applications: apps.compactMap {
            ($0["filename"] as? String)?.replacingOccurrences(of: ".app", with: "")
          },
          technologies: Array(Set(technologies)).sorted().prefix(6).map(\.self),
          recentFiles: recentFiles.compactMap { $0["filename"] as? String }
        )
      }

      guard let snapshot else { return }
      scanSnapshot = snapshot
      suggestedGoals = buildSuggestedGoals(from: snapshot)

      var nodes: [[String: Any]] = []
      var edges: [[String: Any]] = []

      for project in snapshot.projectNames.prefix(4) {
        let id = "project_\(slug(project))"
        nodes.append(["id": id, "label": project, "node_type": "thing", "aliases": []])
        edges.append(["source_id": "user", "target_id": id, "label": "works_on"])
      }

      for tech in snapshot.technologies.prefix(4) {
        let id = "tech_\(slug(tech))"
        nodes.append(["id": id, "label": tech, "node_type": "thing", "aliases": []])
        edges.append(["source_id": "user", "target_id": id, "label": "uses"])
      }

      for application in snapshot.applications.prefix(3) {
        let id = "app_\(slug(application))"
        nodes.append(["id": id, "label": application, "node_type": "thing", "aliases": []])
        edges.append(["source_id": "user", "target_id": id, "label": "opens"])
      }

      if !nodes.isEmpty {
        await saveGraph(nodes: nodes, edges: edges)
      }
    } catch {
      logError("OnboardingPagedIntroCoordinator: Failed to load scan snapshot", error: error)
    }
  }

  func startBackgroundInsightsIfNeeded() async {
    guard !insightsStarted else { return }
    insightsStarted = true
    isLoadingInsights = true
    isResearchComplete = false
    insightStatusText = "Reading Gmail and calendar..."
    gmailInsightsFinished = false
    calendarInsightsFinished = false
    webResearchSummary = ""

    gmailTask = Task {
      do {
        let emails = try await GmailReaderService.shared.readRecentEmails(
          maxResults: 50,
          query: "newer_than:30d"
        )
        guard !Task.isCancelled else { return }

        if emails.isEmpty {
          await MainActor.run {
            self.emailSummary = ""
            ChatToolExecutor.emailInsightsText = nil
          }
          await self.markInsightFinished(.gmail)
          return
        }

        let result = await GmailReaderService.shared.synthesizeFromEmails(emails: emails)
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
          daysBack: 90,
          daysForward: 14,
          maxResults: 200
        )
        guard !Task.isCancelled else { return }

        if events.isEmpty {
          await MainActor.run {
            self.calendarSummary = ""
            ChatToolExecutor.calendarInsightsText = nil
          }
          await self.markInsightFinished(.calendar)
          return
        }

        let result = await CalendarReaderService.shared.synthesizeFromEvents(events: events)
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
  }

  private enum InsightSource {
    case gmail
    case calendar
  }

  private func markInsightFinished(_ source: InsightSource) async {
    switch source {
    case .gmail:
      gmailInsightsFinished = true
    case .calendar:
      calendarInsightsFinished = true
    }

    await maybeStartWebResearch()
  }

  private func maybeStartWebResearch() async {
    guard gmailInsightsFinished && calendarInsightsFinished else { return }
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
      - entities: at most 6
      - node_type must be one of: person, organization, place, thing, concept
      - relation must connect the user to the entity, like works_on, uses, works_with, follows, plans_with, researches
      - goals: at most 4, concrete and specific, not generic
      - Prefer project names, organizations, tools, and recurring commitments
      """

    do {
      let bridge = ACPBridge(passApiKey: true)
      try await bridge.start()
      defer { Task { await bridge.stop() } }

      let result = try await bridge.query(
        prompt: prompt,
        systemPrompt:
          "You are a structured onboarding research assistant. Output only valid JSON.",
        model: "claude-opus-4-6",
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
    } else if let technology = scanSnapshot?.technologies.first, !technology.isEmpty {
      queries.append("\(preferredName) \(technology)")
    }

    return Array(NSOrderedSet(array: queries).array as? [String] ?? queries).prefix(2).map(\.self)
  }

  private func searchableOrganizationHint() -> String? {
    guard let email = userEmail(), let domain = email.split(separator: "@").last?.lowercased()
    else {
      return nil
    }

    let publicDomains: Set<String> = [
      "gmail.com", "googlemail.com", "icloud.com", "me.com", "mac.com", "yahoo.com",
      "outlook.com", "hotmail.com", "live.com", "proton.me", "protonmail.com",
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
      let goal = try await APIClient.shared.createGoal(
        title: title,
        description: "Added from onboarding",
        goalType: config.goalType,
        targetValue: config.targetValue,
        currentValue: 0,
        unit: config.unit,
        source: "onboarding_step_flow"
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
    } catch {
      logError("OnboardingPagedIntroCoordinator: Failed to save onboarding goal", error: error)
      lastActionError = error.localizedDescription
    }
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

    if let snapshot {
      for project in snapshot.projectNames.prefix(2) {
        suggestions.append("Ship \(project)")
      }
      if let technology = snapshot.technologies.first {
        suggestions.append("Make faster progress in \(technology)")
      }
    }

    if !email.isEmpty {
      suggestions.append("Stay ahead of important follow-ups")
    }

    if !calendar.isEmpty {
      suggestions.append("Create more focus time between meetings")
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

  private func slug(_ value: String) -> String {
    value
      .lowercased()
      .replacingOccurrences(of: "[^a-z0-9]+", with: "_", options: .regularExpression)
      .trimmingCharacters(in: CharacterSet(charactersIn: "_"))
  }
}
