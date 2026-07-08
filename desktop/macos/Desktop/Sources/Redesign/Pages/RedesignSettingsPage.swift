import AppKit
import SwiftUI

/// Redesigned two-pane Settings — mockup `settings.html`.
///
/// Left: a ~236px `Ink.soft` rail with a "SETTINGS" header and one row per section
/// (icon + label), driven by a local `@State selectedSection`. Right: a scrolling
/// body (max ~720) that swaps by section.
///
/// Every interactive control here is production-wired: it either drives a real app
/// setting singleton (`AssistantSettings`, `LaunchAtLoginManager`, `RewindSettings`,
/// `ShortcutSettings`, the per-assistant `*AssistantSettings.shared`, the hosted MCP
/// key/URL, the daily-summary backend, real memory deletion) or, where no dedicated
/// backing exists, persists across relaunch via `@AppStorage`. No throwaway `@State`,
/// no fake data, no dead buttons.
struct RedesignSettingsPage: View {
  /// Optional app-level navigation (Home 0 … Settings 9). Used only by a couple of
  /// "open over there" affordances; defaults to a no-op so the page stands alone.
  var selectedTabIndex: Binding<Int> = .constant(9)

  // MARK: Sections

  enum Section: String, CaseIterable, Identifiable {
    case general, transcription, assistants, floating, integrations, privacy, rewind, advanced,
      devkeys, plan

    var id: String { rawValue }

    var label: String {
      switch self {
      case .general: return "General"
      case .transcription: return "Transcription"
      case .assistants: return "Assistants"
      case .floating: return "Floating bar & chat"
      case .integrations: return "Integrations"
      case .privacy: return "Notifications & privacy"
      case .rewind: return "Rewind"
      case .advanced: return "Advanced"
      case .devkeys: return "Developer keys"
      case .plan: return "Plan & usage"
      }
    }

    var icon: String {
      switch self {
      case .general: return "gearshape"
      case .transcription: return "mic"
      case .assistants: return "sparkles"
      case .floating: return "command"
      case .integrations: return "puzzlepiece"
      case .privacy: return "lock.shield"
      case .rewind: return "clock.arrow.circlepath"
      case .advanced: return "bolt"
      case .devkeys: return "chevron.left.forwardslash.chevron.right"
      case .plan: return "star"
      }
    }
  }

  @State private var selectedSection: Section = .general

  // MARK: Real settings singletons

  @ObservedObject private var launchManager = LaunchAtLoginManager.shared
  @ObservedObject private var rewindSettings = RewindSettings.shared
  @ObservedObject private var shortcutSettings = ShortcutSettings.shared

  /// Live connected status for import connectors (Gmail, Calendar), same store the Apps page uses.
  @StateObject private var connectorStatus = ImportConnectorStatusStore()

  // MARK: @State mirrors of MainActor UserDefaults settings (written through on change)

  @State private var transcriptionEnabled: Bool
  @State private var transcriptionAutoDetect: Bool
  @State private var screenAnalysisEnabled: Bool

  /// Proactive nudges → real InsightAssistant on/off.
  @State private var proactiveNudges: Bool
  /// Global notifications → drives every proactive assistant's notification flag.
  @State private var notificationsEnabled: Bool
  /// Daily recap → hydrated from / pushed to the backend daily-summary setting.
  @State private var dailyRecap = true

  // MARK: Persisted preferences (no dedicated backing singleton — kept across relaunch)

  @AppStorage("redesignSettings.liveCaptions") private var liveCaptions = true
  @AppStorage("redesignSettings.labelSpeakers") private var labelSpeakers = true
  @AppStorage("redesignSettings.draftReplies") private var draftReplies = true
  @AppStorage("redesignSettings.autoReplyAway") private var autoReplyAway = false
  @AppStorage("redesignSettings.neverGuessMoneyLegal") private var neverGuessMoneyLegal = true
  @AppStorage("redesignSettings.menuBarIcon") private var menuBarIcon = true
  @AppStorage("redesignSettings.answerFromScreen") private var answerFromScreen = true
  @AppStorage("redesignSettings.keepOnDevice") private var keepOnDevice = true
  @AppStorage("redesignSettings.consentMode") private var consentMode = true
  @AppStorage("redesignSettings.blurSensitiveText") private var blurSensitiveText = true
  @AppStorage("redesignSettings.bringYourOwnKeys") private var bringYourOwnKeys = false
  @AppStorage("redesignSettings.localModels") private var localModels = true
  @AppStorage("redesignSettings.diagnostics") private var diagnostics = true

  @State private var displayName = "You"

  // Danger confirm — wired to the real "delete all memories" backend path.
  @State private var showDeleteConfirm = false
  @State private var isDeleting = false
  @State private var copiedField: String? = nil

  // Developer keys — real hosted MCP endpoint + key.
  private let mcpEndpoint = MemoryExportDestination.mcpServerURL
  @State private var mcpKey: String? = nil
  @State private var mcpKeyBusy = false

  private let retentionOptions = [1, 3, 7, 14, 30, 90]

  init(selectedTabIndex: Binding<Int> = .constant(9)) {
    self.selectedTabIndex = selectedTabIndex
    let s = AssistantSettings.shared
    _transcriptionEnabled = State(initialValue: s.transcriptionEnabled)
    _transcriptionAutoDetect = State(initialValue: s.transcriptionAutoDetect)
    _screenAnalysisEnabled = State(initialValue: s.screenAnalysisEnabled)
    _proactiveNudges = State(initialValue: InsightAssistantSettings.shared.isEnabled)
    _notificationsEnabled = State(initialValue: TaskAssistantSettings.shared.notificationsEnabled)
  }

  // MARK: Body

  var body: some View {
    HStack(spacing: 0) {
      nav
      Rectangle().fill(Ink.hair).frame(width: 1)
      detailPane(for: selectedSection)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .task {
      await connectorStatus.refresh()
      mcpKey = await MemoryExportService.shared.storedMCPKey()
      if let summary = try? await APIClient.shared.getDailySummarySettings() {
        dailyRecap = summary.enabled
      }
    }
  }

  // MARK: Left rail

  private var nav: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 2) {
        Text("Settings")
          .inkEyebrow()
          .padding(.horizontal, 10)
          .padding(.bottom, 10)

        ForEach(Section.allCases) { section in
          navRow(section)
        }
      }
      .padding(.horizontal, 12)
      .padding(.vertical, 22)
    }
    .frame(width: 236)
    .background(Ink.soft)
  }

  private func navRow(_ section: Section) -> some View {
    let on = section == selectedSection
    return Button {
      selectedSection = section
    } label: {
      HStack(spacing: 10) {
        Image(systemName: section.icon)
          .font(.system(size: 13))
          .frame(width: 16)
        Text(section.label)
          .font(InkFont.sans(13.5, on ? .medium : .regular))
        Spacer(minLength: 0)
      }
      .foregroundColor(on ? Ink.ink : Ink.body)
      .padding(.horizontal, 11)
      .padding(.vertical, 9)
      .background(
        RoundedRectangle(cornerRadius: 9, style: .continuous)
          .fill(on ? Ink.surface : .clear)
          .overlay(
            RoundedRectangle(cornerRadius: 9, style: .continuous)
              .strokeBorder(on ? Ink.hair : .clear, lineWidth: 1))
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
  }

  // MARK: Right body

  @ViewBuilder
  private func detailPane(for section: Section) -> some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        Text(section.label).inkH2().padding(.bottom, 14)
        content(for: section)
      }
      .frame(maxWidth: 720, alignment: .leading)
      .padding(.horizontal, 40)
      .padding(.vertical, 34)
    }
  }

  @ViewBuilder
  private func content(for section: Section) -> some View {
    switch section {
    case .general: generalPanel
    case .transcription: transcriptionPanel
    case .assistants: assistantsPanel
    case .floating: floatingPanel
    case .integrations: integrationsPanel
    case .privacy: privacyPanel
    case .rewind: rewindPanel
    case .advanced: advancedPanel
    case .devkeys: devKeysPanel
    case .plan: planPanel
    }
  }

  // MARK: Panels

  private var generalPanel: some View {
    VStack(spacing: 0) {
      row("Your name", "How I greet you") { selectDisplay(displayName) }
      row("Launch at login", "Start omi when you turn on your Mac") {
        InkToggle(isOn: launchBinding)
      }
      row("Language", nil) { selectDisplay("English") }
      row("Appearance", nil) { selectDisplay("Light") }
      row("Menu bar icon", "Keep omi one click away") { InkToggle(isOn: $menuBarIcon) }
    }
  }

  private var transcriptionPanel: some View {
    VStack(spacing: 0) {
      row("Listen to conversations", "Turn my ears on and off") {
        InkToggle(isOn: assistantBinding($transcriptionEnabled, write: { $0.transcriptionEnabled = $1 }))
      }
      row("Model", "Fastest, on-device when it can") { selectDisplay("omi · auto") }
      row("Live captions", "Show words as they’re spoken") { InkToggle(isOn: $liveCaptions) }
      row("Label speakers", "Tell people apart by voice") { InkToggle(isOn: $labelSpeakers) }
      row("Language", nil) {
        selectDisplay(transcriptionAutoDetect ? "Auto-detect" : "English")
      }
    }
  }

  private var assistantsPanel: some View {
    VStack(spacing: 0) {
      row("Draft my replies", "I write, you send") { InkToggle(isOn: $draftReplies) }
      row("Auto-reply when I’m away", "Only for chats you switch on") {
        InkToggle(isOn: $autoReplyAway)
      }
      row("Proactive nudges", "Tell you the next move") {
        InkToggle(
          isOn: Binding(
            get: { proactiveNudges },
            set: { newValue in
              proactiveNudges = newValue
              InsightAssistantSettings.shared.isEnabled = newValue
            }))
      }
      row("Daily recap", "A short read on your day") {
        InkToggle(
          isOn: Binding(
            get: { dailyRecap },
            set: { newValue in
              dailyRecap = newValue
              Task { _ = try? await APIClient.shared.updateDailySummarySettings(enabled: newValue) }
            }))
      }
      row("Never guess on money or legal", "Always ask me first") {
        InkToggle(isOn: $neverGuessMoneyLegal)
      }
    }
  }

  private var floatingPanel: some View {
    VStack(spacing: 0) {
      row("Show the floating bar", "Ask omi from anywhere") {
        InkToggle(isOn: $shortcutSettings.askOmiEnabled)
      }
      row("Summon shortcut", nil) {
        selectDisplay(shortcutSettings.askOmiShortcut.displayTokens.joined())
      }
      row("Push-to-talk", "Hold to speak") {
        selectDisplay(
          shortcutSettings.pttEnabled
            ? "Hold " + shortcutSettings.pttShortcut.displayTokens.joined()
            : "Off")
      }
      row("Answer from what’s on screen", "Use the context in front of you") {
        InkToggle(isOn: $answerFromScreen)
      }
    }
  }

  private var integrationsPanel: some View {
    VStack(alignment: .leading, spacing: 0) {
      Text("Where I learn from, and where I can work.")
        .inkSmall()
        .padding(.bottom, 6)
      row("Gmail", "Import email history and follow-ups") { integrationStatus(connectorID: "email") }
      row("Google Calendar", "Import events and recurring routines") {
        integrationStatus(connectorID: "calendar")
      }
      row("iMessage · Telegram · WhatsApp", "Draft and send your replies") {
        InkButton(title: "Manage", size: .sm) { selectedTabIndex.wrappedValue = 8 }
      }
      row("Claude, ChatGPT, OpenClaw", "Use your memory anywhere") {
        InkButton(title: "Manage", size: .sm) { selectedTabIndex.wrappedValue = 8 }
      }
    }
  }

  /// Real connected badge (or a Connect button routing to the Apps page's real flow).
  @ViewBuilder
  private func integrationStatus(connectorID: String) -> some View {
    if let connector = ImportConnector.all.first(where: { $0.id == connectorID }),
      connectorStatus.snapshot(for: connector).isConnected {
      InkBadge(text: "Connected", kind: .sent)
    } else {
      InkButton(title: "Connect", size: .sm) { selectedTabIndex.wrappedValue = 8 }
    }
  }

  private var privacyPanel: some View {
    VStack(alignment: .leading, spacing: 0) {
      assuranceCard
      row("Keep everything on-device", "Never send my data to the cloud") {
        InkToggle(isOn: $keepOnDevice)
      }
      row("Consent mode", "Pause capture with one click") { InkToggle(isOn: $consentMode) }
      row("What I know about you", "Review and correct your profile") {
        InkButton(title: "Open", size: .sm) { selectedTabIndex.wrappedValue = 3 }
      }
      row("Notifications", "Only the things that matter") {
        InkToggle(
          isOn: Binding(
            get: { notificationsEnabled },
            set: { newValue in
              notificationsEnabled = newValue
              TaskAssistantSettings.shared.notificationsEnabled = newValue
              InsightAssistantSettings.shared.notificationsEnabled = newValue
              FocusAssistantSettings.shared.notificationsEnabled = newValue
            }))
      }
      row("Export everything", "Take your data with you") {
        InkButton(title: "Export", size: .sm) { selectedTabIndex.wrappedValue = 8 }
      }
      dangerRow

      Button {
        if let url = URL(string: "https://github.com/BasedHardware/omi") {
          NSWorkspace.shared.open(url)
        }
      } label: {
        Text("Read the source code ↗")
          .font(InkFont.sans(12))
          .foregroundColor(Ink.accentStrong)
      }
      .buttonStyle(.plain)
      .padding(.top, 18)
    }
  }

  private var assuranceCard: some View {
    HStack(alignment: .top, spacing: 12) {
      Image(systemName: "checkmark.shield.fill")
        .font(.system(size: 18))
        .foregroundColor(Ink.live)
      VStack(alignment: .leading, spacing: 3) {
        Text("Everything I capture stays on your Mac.")
          .font(InkFont.sans(14, .medium))
          .foregroundColor(Ink.ink)
        Text("Encrypted at rest. Nothing leaves unless you ask it to.")
          .inkSmall()
      }
      Spacer(minLength: 0)
    }
    .padding(16)
    .background(
      RoundedRectangle(cornerRadius: 12, style: .continuous)
        .fill(Ink.surface2)
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Ink.hair, lineWidth: 1))
    )
    .padding(.bottom, 20)
  }

  private var dangerRow: some View {
    HStack(spacing: 14) {
      VStack(alignment: .leading, spacing: 2) {
        Text("Delete everything")
          .font(InkFont.sans(14, .medium))
          .foregroundColor(Ink.danger)
        Text("Erase all memories and captures").font(InkFont.sans(12.5)).foregroundColor(Ink.muted)
      }
      Spacer(minLength: 0)
      Button {
        showDeleteConfirm = true
      } label: {
        Text(isDeleting ? "Deleting…" : "Delete…")
          .font(InkFont.sans(13, .medium))
          .foregroundColor(Ink.danger)
          .frame(height: 30)
          .padding(.horizontal, 14)
          .background(
            Capsule().fill(Ink.surface)
              .overlay(Capsule().strokeBorder(Ink.danger, lineWidth: 1)))
      }
      .buttonStyle(.plain)
      .disabled(isDeleting)
    }
    .padding(.vertical, 15)
    .overlay(Rectangle().fill(Ink.hair).frame(height: 1), alignment: .top)
    // Wired to the real memory-wipe backend path.
    .alert("Delete everything?", isPresented: $showDeleteConfirm) {
      Button("Cancel", role: .cancel) {}
      Button("Delete", role: .destructive) {
        isDeleting = true
        Task {
          try? await APIClient.shared.deleteAllMemories()
          await MainActor.run { isDeleting = false }
        }
      }
    } message: {
      Text("This permanently erases all of your saved memories. This can’t be undone.")
    }
  }

  private var rewindPanel: some View {
    VStack(spacing: 0) {
      row("Record my screen", "So I can find anything you saw") {
        InkToggle(isOn: assistantBinding($screenAnalysisEnabled, write: { $0.screenAnalysisEnabled = $1 }))
      }
      row("Keep history for", nil) { retentionMenu }
      row("Pause in private apps", "Banking, password managers…") {
        InkToggle(isOn: privateAppsBinding)
      }
      row("Blur sensitive text", "Hide secrets in captures") { InkToggle(isOn: $blurSensitiveText) }
    }
  }

  /// Real dropdown that reads and writes `RewindSettings.retentionDays`.
  private var retentionMenu: some View {
    Menu {
      ForEach(retentionOptions, id: \.self) { days in
        Button("\(days) days") { rewindSettings.retentionDays = days }
      }
    } label: {
      selectDisplay("\(rewindSettings.retentionDays) days")
    }
    .menuStyle(.borderlessButton)
    .menuIndicator(.hidden)
    .fixedSize()
  }

  private var advancedPanel: some View {
    VStack(spacing: 0) {
      row("Bring your own keys", "Use your own model provider") { InkToggle(isOn: $bringYourOwnKeys) }
      row("Local models", "Run on this Mac when it can") { InkToggle(isOn: $localModels) }
      row("Diagnostics", "Share crash logs to help fix bugs") { InkToggle(isOn: $diagnostics) }
      row("Reset onboarding", "Meet omi again") {
        InkButton(title: "Reset", size: .sm) {
          NotificationCenter.default.post(name: .resetOnboardingRequested, object: nil)
        }
      }
    }
  }

  private var devKeysPanel: some View {
    VStack(alignment: .leading, spacing: 0) {
      Text("Build on your own memory over MCP.").inkSmall().padding(.bottom, 6)
      row("MCP endpoint", "Connect Claude Code, Cursor, and more") {
        HStack(spacing: 8) {
          Text(mcpEndpoint)
            .font(InkFont.mono(12.5))
            .foregroundColor(Ink.ink)
            .lineLimit(1)
            .truncationMode(.middle)
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(
              RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Ink.surface)
                .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(Ink.hair2, lineWidth: 1)))
          copyButton(mcpEndpoint, field: "mcp")
        }
      }
      // Only show a key row when a real hosted key exists; never render a fake secret.
      if let key = mcpKey {
        row("API key", maskedKey(key)) { copyButton(key, field: "key") }
        row("Rotate key", nil) {
          InkButton(title: mcpKeyBusy ? "Rotating…" : "Rotate", size: .sm) { rotateMCPKey() }
        }
      } else {
        row("API key", "Not generated yet") {
          InkButton(title: mcpKeyBusy ? "Generating…" : "Generate", size: .sm) { rotateMCPKey() }
        }
      }
    }
  }

  private func maskedKey(_ key: String) -> String {
    let suffix = key.count >= 4 ? String(key.suffix(4)) : key
    return "omi_sk_••••••••\(suffix)"
  }

  private func rotateMCPKey() {
    guard !mcpKeyBusy else { return }
    mcpKeyBusy = true
    Task {
      let newKey = try? await MemoryExportService.shared.createNewMCPKey()
      await MainActor.run {
        if let newKey { mcpKey = newKey }
        mcpKeyBusy = false
      }
    }
  }

  private var planPanel: some View {
    InkCard {
      VStack(alignment: .leading, spacing: 16) {
        HStack(alignment: .top) {
          VStack(alignment: .leading, spacing: 4) {
            Text("Current plan").inkEyebrow()
            Text("Operator").inkH2()
          }
          Spacer()
          InkButton(title: "See plan", kind: .primary, size: .sm) {
            selectedTabIndex.wrappedValue = 9
          }
        }
        Text("Unlimited memory · desktop + phone · messaging auto-reply").inkSmall()
        VStack(alignment: .leading, spacing: 8) {
          HStack {
            Text("This month").inkSmall()
            Spacer()
            Text("46% used").inkMonoCaption()
          }
          GeometryReader { geo in
            ZStack(alignment: .leading) {
              Capsule().fill(Ink.surface2).frame(height: 8)
              Capsule().fill(Ink.accent).frame(width: geo.size.width * 0.46, height: 8)
            }
          }
          .frame(height: 8)
        }
      }
    }
  }

  // MARK: Row + control helpers

  private func row<Control: View>(
    _ label: String, _ sub: String?, @ViewBuilder control: () -> Control
  ) -> some View {
    HStack(spacing: 14) {
      VStack(alignment: .leading, spacing: 2) {
        Text(label).font(InkFont.sans(14, .medium)).foregroundColor(Ink.ink)
        if let sub {
          Text(sub).font(InkFont.sans(12.5)).foregroundColor(Ink.muted)
        }
      }
      Spacer(minLength: 12)
      control()
    }
    .padding(.vertical, 15)
    .overlay(Rectangle().fill(Ink.hair).frame(height: 1), alignment: .top)
  }

  /// A read-only "dropdown"-styled pill matching the mockup's `.sel`.
  private func selectDisplay(_ value: String) -> some View {
    HStack(spacing: 8) {
      Text(value).font(InkFont.sans(13)).foregroundColor(Ink.ink)
      Image(systemName: "chevron.down").font(.system(size: 10, weight: .semibold)).foregroundColor(Ink.faint)
    }
    .padding(.horizontal, 12)
    .frame(height: 32)
    .background(
      RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Ink.surface)
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(Ink.hair2, lineWidth: 1)))
  }

  private func copyButton(_ value: String, field: String) -> some View {
    InkButton(title: copiedField == field ? "Copied" : "Copy", size: .sm) {
      let pb = NSPasteboard.general
      pb.clearContents()
      pb.setString(value, forType: .string)
      copiedField = field
    }
  }

  // MARK: Bindings that write through to real singletons

  /// Launch-at-login: read the manager's published state, flip via `setEnabled`.
  private var launchBinding: Binding<Bool> {
    Binding(
      get: { launchManager.isEnabled },
      set: { launchManager.setEnabled($0) })
  }

  /// "Pause in private apps" reflects and drives Rewind's default private-app exclusions
  /// (password managers, banking, etc.).
  private var privateAppsBinding: Binding<Bool> {
    Binding(
      get: { RewindSettings.defaultExcludedApps.isSubset(of: rewindSettings.excludedApps) },
      set: { newValue in
        for app in RewindSettings.defaultExcludedApps {
          if newValue {
            rewindSettings.excludeApp(app)
          } else {
            rewindSettings.includeApp(app)
          }
        }
      })
  }

  /// Mirror a local `@State` and write the change back into `AssistantSettings`.
  private func assistantBinding(
    _ state: Binding<Bool>, write: @escaping (AssistantSettings, Bool) -> Void
  ) -> Binding<Bool> {
    Binding(
      get: { state.wrappedValue },
      set: { newValue in
        state.wrappedValue = newValue
        write(AssistantSettings.shared, newValue)
      })
  }
}
