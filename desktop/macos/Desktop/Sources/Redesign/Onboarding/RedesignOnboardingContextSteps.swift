import SwiftUI

// MARK: - Step 14 · Data sources (mockup: ob-import "Here's what I already know")

struct RedesignDataSourcesStepView: View {
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let onContinue: () -> Void
  let onSkip: (() -> Void)?
  let onForceComplete: (() -> Void)?

  @State private var activeImportSource: OnboardingMemoryLogSource?
  @State private var chatGPTMemoryLog = ""
  @State private var claudeMemoryLog = ""

  var body: some View {
    RedesignOnboardingScaffold(
      beat: RedesignOnboarding.beat(forStep: stepIndex),
      eyebrow: "Your second brain is live",
      title: "Here's what I\nalready know.",
      subtitle: "Connect more of your context — the more you give me, the sharper I get.",
      showsSkip: onSkip != nil,
      onSkip: onSkip,
      onForceComplete: onForceComplete,
      maxWidth: 580
    ) {
      VStack(alignment: .leading, spacing: 18) {
        connectionsCard

        if let error = coordinator.lastActionError {
          RedesignOnboardingError(message: error)
        }

        if coordinator.isResearchComplete {
          InkButton(title: "Keep going", kind: .primary, size: .lg) { onContinue() }
        } else {
          HStack(spacing: 8) {
            ProgressView().controlSize(.small).tint(Ink.faint)
            Text("Scanning your data sources…").font(InkFont.sans(13)).foregroundColor(Ink.faint)
          }
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .task {
        await graphViewModel.addGraphFromStorage()
        if !coordinator.isResearchComplete {
          await coordinator.startBackgroundInsightsIfNeeded()
        }
      }
    }
  }

  private var connectionsCard: some View {
    InkCard(padding: 0, radius: 16) {
      VStack(spacing: 0) {
        sourceRow(
          brand: .calendar, title: "Calendar",
          metrics: metricsText(coordinator.calendarInsightCount, "event", "events", coordinator.calendarMemoriesSaved),
          trailing: .connected)
        divider
        sourceRow(
          brand: .gmail, title: "Email",
          metrics: metricsText(coordinator.gmailInsightCount, "email", "emails", coordinator.gmailMemoriesSaved),
          trailing: .connected)
        divider
        sourceRow(
          brand: .localFiles, title: "Local files",
          metrics: metricsText(coordinator.scanSnapshot?.fileCount ?? 0, "file", "files", coordinator.localFileMemoriesSaved),
          trailing: .connected)
        divider
        sourceRow(
          brand: .appleNotes, title: "Apple Notes",
          metrics: metricsText(coordinator.appleNotesInsightCount, "note", "notes", coordinator.appleNotesMemoriesSaved),
          trailing: coordinator.appleNotesInsightCount > 0
            ? .connected
            : .action("Select Folder", { Task { await coordinator.selectAppleNotesFolderAndSync() } }))
        divider
        memoryLogRow(source: .chatgpt, text: $chatGPTMemoryLog)
        divider
        memoryLogRow(source: .claude, text: $claudeMemoryLog)
      }
    }
  }

  private var divider: some View {
    Rectangle().fill(Ink.hair).frame(height: 1).padding(.leading, 66)
  }

  private enum Trailing {
    case connected
    case action(String, () -> Void)
    case importToggle(OnboardingMemoryLogSource)
  }

  private func sourceRow(brand: ConnectorBrand, title: String, metrics: String, trailing: Trailing)
    -> some View
  {
    HStack(spacing: 12) {
      ConnectorBrandIcon(brand: brand, size: 38, cornerRadius: 11)

      VStack(alignment: .leading, spacing: 3) {
        Text(title).inkH3()
        Text(metrics).font(InkFont.mono(12)).foregroundColor(Ink.faint).lineLimit(1)
      }
      .frame(minWidth: 130, alignment: .leading)

      Spacer(minLength: 8)

      switch trailing {
      case .connected:
        InkBadge(text: "Connected", kind: .sent)
      case .action(let label, let act):
        InkButton(title: label, kind: .plain, size: .sm, action: act)
      case .importToggle(let source):
        let expanded = activeImportSource == source
        InkButton(title: expanded ? "Close" : "Import", kind: .plain, size: .sm) {
          activeImportSource = expanded ? nil : source
        }
      }
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 13)
  }

  @ViewBuilder
  private func memoryLogRow(source: OnboardingMemoryLogSource, text: Binding<String>) -> some View {
    let importedCount = coordinator.importedMemoryCount(for: source)
    let isConnected = importedCount > 0

    sourceRow(
      brand: source == .chatgpt ? .chatgpt : .claude,
      title: source.displayName,
      metrics: isConnected ? countLabel(importedCount, "memory", "memories") : "0 memories",
      trailing: isConnected ? .connected : .importToggle(source))

    if activeImportSource == source, !isConnected {
      memoryLogPanel(source: source, text: text)
        .padding(.horizontal, 16)
        .padding(.bottom, 16)
    }
  }

  private func memoryLogPanel(source: OnboardingMemoryLogSource, text: Binding<String>)
    -> some View
  {
    VStack(alignment: .leading, spacing: 12) {
      Text("Open \(source.displayName), paste the copied prompt, then drop the full response here.")
        .font(InkFont.sans(13)).foregroundColor(Ink.body)
        .fixedSize(horizontal: false, vertical: true)

      InkButton(title: "Open \(source.displayName) & copy prompt", kind: .plain, size: .sm) {
        coordinator.copyPromptAndOpenMemoryLogSource(source)
      }

      ZStack(alignment: .topLeading) {
        RoundedRectangle(cornerRadius: 12, style: .continuous)
          .fill(Ink.surface2)
          .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
              .strokeBorder(Ink.hair, lineWidth: 1))

        if text.wrappedValue.isEmpty {
          Text("Paste the full \(source.displayName) response here…")
            .font(InkFont.sans(13)).foregroundColor(Ink.faint)
            .padding(.horizontal, 14).padding(.vertical, 14)
        }
        TextEditor(text: text)
          .scrollContentBackground(.hidden)
          .font(InkFont.sans(13))
          .foregroundColor(Ink.ink)
          .frame(minHeight: 130)
          .padding(8)
      }

      HStack(spacing: 12) {
        InkButton(
          title: coordinator.isImportingMemoryLog(for: source) ? "Importing…" : "Import \(source.displayName)",
          kind: .primary, size: .sm
        ) {
          Task {
            await coordinator.importMemoryLog(text.wrappedValue, source: source)
            if coordinator.importedMemoryCount(for: source) > 0 {
              text.wrappedValue = ""
              activeImportSource = nil
            }
          }
        }
        Button("Cancel") { activeImportSource = nil }
          .buttonStyle(.plain).font(InkFont.sans(13, .medium)).foregroundColor(Ink.muted)
      }
    }
    .padding(16)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(Ink.surface2))
  }

  private func metricsText(_ count: Int, _ singular: String, _ plural: String, _ memories: Int)
    -> String
  {
    "\(countLabel(count, singular, plural)) • \(countLabel(memories, "memory", "memories"))"
  }

  private func countLabel(_ count: Int, _ singular: String, _ plural: String) -> String {
    count == 1 ? "1 \(singular)" : "\(count.formatted()) \(plural)"
  }
}

// MARK: - Step 15 · Exports

struct RedesignExportsStepView: View {
  @ObservedObject var graphViewModel: MemoryGraphViewModel
  let stepIndex: Int
  let summaryText: String
  let onContinue: () -> Void
  let onSkip: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var statuses: [MemoryExportDestination: MemoryExportStatus] = [:]
  @State private var activeDestination: MemoryExportDestination?

  var body: some View {
    RedesignOnboardingScaffold(
      beat: RedesignOnboarding.beat(forStep: stepIndex),
      eyebrow: "Take me with you",
      title: "Put your memories\nwhere you work.",
      subtitle: "Connect the tools where you want omi's context to live.",
      showsSkip: true,
      onSkip: onSkip,
      onForceComplete: onForceComplete,
      maxWidth: 580
    ) {
      VStack(alignment: .leading, spacing: 18) {
        InkCard(padding: 0, radius: 16) {
          VStack(spacing: 0) {
            ForEach(Array(onboardingDestinations.enumerated()), id: \.element.id) { index, dest in
              exportRow(dest)
              if index < onboardingDestinations.count - 1 {
                Rectangle().fill(Ink.hair).frame(height: 1).padding(.leading, 66)
              }
            }
          }
        }

        if let activeDestination {
          RedesignInlineExportPanel(
            destination: activeDestination, statuses: $statuses,
            onClose: { self.activeDestination = nil })
        }

        InkButton(title: "Continue", kind: .primary, size: .lg) { onContinue() }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .task {
        await graphViewModel.addGraphFromStorage()
        statuses = await MemoryExportService.shared.allStatuses()
      }
    }
  }

  private var onboardingDestinations: [MemoryExportDestination] {
    MemoryExportDestination.allCases.filter { $0.supportsMemoryPack || $0.supportsAgentSetup }
  }

  private func exportRow(_ destination: MemoryExportDestination) -> some View {
    let status =
      statuses[destination]
      ?? MemoryExportStatus(exportedCount: 0, lastExportedAt: nil, detailText: nil, isConfigured: false)

    return HStack(spacing: 12) {
      ConnectorBrandIcon(brand: destination.brand, size: 38, cornerRadius: 11)

      VStack(alignment: .leading, spacing: 3) {
        Text(destination.title).inkH3()
        Text(exportMetrics(for: destination, status: status))
          .font(InkFont.sans(12)).foregroundColor(Ink.faint)
      }

      Spacer(minLength: 12)

      InkButton(
        title: activeDestination == destination ? "Close" : "Connect",
        kind: .plain, size: .sm
      ) {
        activeDestination = activeDestination == destination ? nil : destination
      }
    }
    .padding(.horizontal, 16)
    .padding(.vertical, 14)
  }

  private func exportMetrics(for destination: MemoryExportDestination, status: MemoryExportStatus)
    -> String
  {
    if status.exportedCount > 0 { return "\(status.exportedCount.formatted()) memories exported" }
    if destination.isAutomated { return "Automatic export" }
    if destination == .notion { return "Copy-ready page" }
    if destination.supportsAgentSetup {
      return status.isConfigured ? "Agent prompt ready" : "Connect an agent"
    }
    return "Prompt + memory pack"
  }
}

private struct RedesignInlineExportPanel: View {
  let destination: MemoryExportDestination
  @Binding var statuses: [MemoryExportDestination: MemoryExportStatus]
  let onClose: () -> Void

  @StateObject private var model = MemoryExportDestinationSheetModel()

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text(destination.description)
        .font(InkFont.sans(13)).foregroundColor(Ink.body)
        .fixedSize(horizontal: false, vertical: true)

      infoCard(infoText)

      if destination == .obsidian {
        InkButton(
          title: model.obsidianVaultPath.isEmpty ? "Choose vault" : "Change vault",
          kind: .plain, size: .sm
        ) { model.pickObsidianVault() }
      }

      HStack(spacing: 12) {
        InkButton(title: model.isRunning ? runningLabel : idleLabel, kind: .primary, size: .sm) {
          Task {
            if destination.supportsAgentSetup, let updated = await model.copyAgentSetupPrompt() {
              statuses[destination] = updated
            } else if let updated = await model.run(destination: destination) {
              statuses[destination] = updated
            }
          }
        }
        .disabled(model.isRunning || model.isLoadingMCPKey)

        Button("Cancel") { onClose() }
          .buttonStyle(.plain).font(InkFont.sans(13, .medium)).foregroundColor(Ink.muted)
      }

      if let statusMessage = model.statusMessage {
        Text(statusMessage).font(InkFont.sans(12, .medium)).foregroundColor(Ink.sentText)
      }
      if let errorMessage = model.errorMessage {
        RedesignOnboardingError(message: errorMessage)
      }
    }
    .padding(16)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.surface).overlay(
          RoundedRectangle(cornerRadius: 14).strokeBorder(Ink.hair, lineWidth: 1)))
    .task { await model.loadConfiguration() }
  }

  private var infoText: String {
    switch destination {
    case .notion:
      return "omi copies a ready-to-paste memory page, saves a backup in Downloads, and opens Notion."
    case .obsidian:
      return model.obsidianVaultPath.isEmpty
        ? "Pick your Obsidian vault once. omi will keep refreshing Omi/Memories.md there."
        : model.obsidianVaultPath
    case .chatgpt, .claude, .gemini:
      return "omi copies the prompt and memory pack together, saves a Markdown backup, and opens \(destination.title)."
    case .agents:
      return "omi copies one setup prompt for your agent, including the connection keys and a short guide."
    case .claudeCode, .codex, .openclaw, .hermes:
      return "Connect \(destination.title) over MCP from Apps after onboarding."
    }
  }

  private var runningLabel: String {
    destination == .obsidian ? "Exporting…" : "Preparing…"
  }

  private var idleLabel: String {
    switch destination {
    case .notion: return "Copy & open"
    case .obsidian: return model.obsidianVaultPath.isEmpty ? "Choose vault" : "Export"
    case .agents: return "Copy prompt"
    case .chatgpt, .claude, .gemini, .claudeCode, .codex, .openclaw, .hermes: return "Copy & open"
    }
  }

  private func infoCard(_ text: String) -> some View {
    Text(text)
      .font(InkFont.sans(12)).foregroundColor(Ink.muted)
      .padding(14)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        RoundedRectangle(cornerRadius: 12, style: .continuous)
          .fill(Ink.surface2).overlay(
            RoundedRectangle(cornerRadius: 12).strokeBorder(Ink.hair, lineWidth: 1)))
  }
}

// MARK: - Step 16 · Goal (mockup: ob-goal)

struct RedesignGoalStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var coordinator: OnboardingPagedIntroCoordinator
  let stepIndex: Int
  let onContinue: () -> Void
  let onSkip: () -> Void
  let onForceComplete: (() -> Void)?

  @State private var customGoalSelected = false

  private static let customGoalOption = "Type my own"
  private static let starterQuestions = [
    ("sparkles", "What did I miss while I was heads-down today?"),
    ("person.2", "Who am I overdue to reply to?"),
    ("calendar", "What's the one thing to finish before 5pm?"),
  ]

  var body: some View {
    RedesignOnboardingScaffold(
      beat: RedesignOnboarding.beat(forStep: stepIndex),
      eyebrow: "Last thing",
      title: "Pick one thing to\nget better at.",
      subtitle: "I'll bias everything I do toward it. Add a number so we can measure progress.",
      centeredText: false,
      showsSkip: true,
      onSkip: onSkip,
      onForceComplete: onForceComplete,
      maxWidth: 560
    ) {
      VStack(alignment: .leading, spacing: 18) {
        FlowLayout(spacing: 10) {
          ForEach(suggestionItems, id: \.self) { item in
            RedesignOnboardingChip(title: item, selected: selectedSuggestion == item) {
              if item == Self.customGoalOption {
                customGoalSelected = true
                coordinator.goalDraft = ""
              } else {
                customGoalSelected = false
                coordinator.goalDraft = item
                coordinator.clearLastActionError()
              }
            }
          }
        }

        if customGoalSelected {
          RedesignOnboardingField(
            placeholder: "Type your goal", text: $coordinator.goalDraft, maxWidth: 520)
        }

        Text("What do you want to ask me first?").inkH3().padding(.top, 8)
        VStack(spacing: 9) {
          ForEach(Self.starterQuestions, id: \.1) { icon, q in
            HStack(spacing: 12) {
              Image(systemName: icon).font(.system(size: 15)).foregroundColor(Ink.faint)
              Text(q).inkBody()
              Spacer()
            }
            .padding(.horizontal, 16).padding(.vertical, 14)
            .background(
              RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Ink.surface).overlay(
                  RoundedRectangle(cornerRadius: 12).strokeBorder(Ink.hair, lineWidth: 1)))
          }
        }

        if let error = coordinator.lastActionError {
          RedesignOnboardingError(message: error)
        }

        if !trimmedGoal.isEmpty {
          InkButton(
            title: coordinator.isSavingGoal ? "Saving…" : "Let's go", kind: .primary, size: .lg
          ) {
            Task {
              coordinator.goalSaved = false
              await coordinator.saveGoalIfNeeded()
              guard coordinator.goalSaved else { return }
              let completed = await coordinator.completeIntro(appState: appState)
              if completed { onContinue() }
            }
          }
          .disabled(coordinator.isSavingGoal)
        }
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .onAppear {
        customGoalSelected =
          !coordinator.goalDraft.isEmpty && !baseSuggestions.contains(coordinator.goalDraft)
      }
    }
  }

  private var baseSuggestions: [String] {
    coordinator.goalSuggestionCards().filter { $0 != "I’ll type my own" }
  }
  private var suggestionItems: [String] {
    Array(baseSuggestions.prefix(4)) + [Self.customGoalOption]
  }
  private var selectedSuggestion: String? {
    if customGoalSelected { return Self.customGoalOption }
    return suggestionItems.contains(coordinator.goalDraft) ? coordinator.goalDraft : nil
  }
  private var trimmedGoal: String {
    coordinator.goalDraft.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
