import AppKit
import SwiftUI

/// Redesigned two-pane Settings — mockup `settings.html`.
///
/// Left: a ~236px `Ink.soft` rail with a "SETTINGS" header and one row per section
/// (icon + label), driven by a local `@State selectedSection`. Right: a scrolling
/// body (max ~720) that swaps by section. Real settings are wired where they exist
/// (`AssistantSettings`, `LaunchAtLoginManager`, `RewindSettings`); everything else
/// falls back to local `@State` so the page is self-contained and compiles alone.
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

  // MARK: Real settings (mirrored into @State; written through on change)

  @ObservedObject private var launchManager = LaunchAtLoginManager.shared
  @ObservedObject private var rewindSettings = RewindSettings.shared

  @State private var transcriptionEnabled: Bool
  @State private var screenAnalysisEnabled: Bool
  @State private var transcriptionAutoDetect: Bool

  // MARK: Local-only mirrors (no dedicated single property today — kept honest as UI state)

  @State private var liveCaptions = true
  @State private var labelSpeakers = true

  @State private var draftReplies = true
  @State private var autoReplyAway = false
  @State private var proactiveNudges = true
  @State private var dailyRecap = true
  @State private var neverGuessMoneyLegal = true

  @State private var showFloatingBar = true
  @State private var menuBarIcon = true
  @State private var answerFromScreen = true

  @State private var keepOnDevice = true
  @State private var consentMode = true
  @State private var notificationsEnabled = true

  @State private var pauseInPrivateApps = true
  @State private var blurSensitiveText = true

  @State private var bringYourOwnKeys = false
  @State private var localModels = true
  @State private var diagnostics = true

  @State private var displayName = "You"

  // Danger confirm (confirm-only placeholder — no destructive action)
  @State private var showDeleteConfirm = false
  @State private var copiedField: String? = nil

  private let mcpEndpoint = "/v1/mcp/sse"
  private let maskedApiKey = "omi_sk_••••••••4120"

  init(selectedTabIndex: Binding<Int> = .constant(9)) {
    self.selectedTabIndex = selectedTabIndex
    let s = AssistantSettings.shared
    _transcriptionEnabled = State(initialValue: s.transcriptionEnabled)
    _screenAnalysisEnabled = State(initialValue: s.screenAnalysisEnabled)
    _transcriptionAutoDetect = State(initialValue: s.transcriptionAutoDetect)
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
      row("Proactive nudges", "Tell you the next move") { InkToggle(isOn: $proactiveNudges) }
      row("Daily recap", "A short read on your day") { InkToggle(isOn: $dailyRecap) }
      row("Never guess on money or legal", "Always ask me first") {
        InkToggle(isOn: $neverGuessMoneyLegal)
      }
    }
  }

  private var floatingPanel: some View {
    VStack(spacing: 0) {
      row("Show the floating bar", "Ask omi from anywhere") { InkToggle(isOn: $showFloatingBar) }
      row("Summon shortcut", nil) { selectDisplay("⌘⇧Space") }
      row("Push-to-talk", "Hold to speak") { selectDisplay("Hold ⌥") }
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
      row("Gmail", "Connected inbox") { InkBadge(text: "Connected", kind: .sent) }
      row("Google Calendar", "12 events this week") { InkBadge(text: "Connected", kind: .sent) }
      row("iMessage · Telegram · WhatsApp", "Draft and send your replies") {
        InkBadge(text: "Connected", kind: .sent)
      }
      row("Claude, ChatGPT, OpenClaw", "Use your memory anywhere") {
        InkButton(title: "Manage", size: .sm) { selectedTabIndex.wrappedValue = 8 }
      }
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
        InkToggle(isOn: $notificationsEnabled)
      }
      row("Export everything", "Take your data with you") {
        InkButton(title: "Export", size: .sm) {}
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
        Text("Delete…")
          .font(InkFont.sans(13, .medium))
          .foregroundColor(Ink.danger)
          .frame(height: 30)
          .padding(.horizontal, 14)
          .background(
            Capsule().fill(Ink.surface)
              .overlay(Capsule().strokeBorder(Ink.danger, lineWidth: 1)))
      }
      .buttonStyle(.plain)
    }
    .padding(.vertical, 15)
    .overlay(Rectangle().fill(Ink.hair).frame(height: 1), alignment: .top)
    // Confirm-only placeholder: no destructive action is performed.
    .alert("Delete everything?", isPresented: $showDeleteConfirm) {
      Button("Cancel", role: .cancel) {}
      Button("Delete", role: .destructive) {}
    } message: {
      Text("This is a confirmation placeholder. Nothing is deleted in this build.")
    }
  }

  private var rewindPanel: some View {
    VStack(spacing: 0) {
      row("Record my screen", "So I can find anything you saw") {
        InkToggle(isOn: assistantBinding($screenAnalysisEnabled, write: { $0.screenAnalysisEnabled = $1 }))
      }
      row("Keep history for", nil) { selectDisplay("\(rewindSettings.retentionDays) days") }
      row("Pause in private apps", "Banking, password managers…") {
        InkToggle(isOn: $pauseInPrivateApps)
      }
      row("Blur sensitive text", "Hide secrets in captures") { InkToggle(isOn: $blurSensitiveText) }
    }
  }

  private var advancedPanel: some View {
    VStack(spacing: 0) {
      row("Bring your own keys", "Use your own model provider") { InkToggle(isOn: $bringYourOwnKeys) }
      row("Local models", "Run on this Mac when it can") { InkToggle(isOn: $localModels) }
      row("Diagnostics", "Share crash logs to help fix bugs") { InkToggle(isOn: $diagnostics) }
      row("Reset onboarding", "Meet omi again") {
        InkButton(title: "Reset", size: .sm) {}
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
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(
              RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Ink.surface)
                .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(Ink.hair2, lineWidth: 1)))
          copyButton(mcpEndpoint, field: "mcp")
        }
      }
      row("API key", maskedApiKey) { copyButton(maskedApiKey, field: "key") }
      row("Rotate key", nil) { InkButton(title: "Rotate", size: .sm) {} }
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
