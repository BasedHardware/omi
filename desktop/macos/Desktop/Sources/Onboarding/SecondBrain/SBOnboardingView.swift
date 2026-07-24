import AppKit
import OmiTheme
import SwiftUI

enum SBOnboardingRepository {
  static let url = URL(string: "https://github.com/BasedHardware/omi")!
}

/// The Second Brain conversational onboarding — a chat with Omi that streams
/// word-by-word and performs real side-effects. Replaces the legacy wizard.
struct SBOnboardingView: View {
  @Environment(\.sbTheme) private var sb
  @StateObject private var model: SBOnboardingModel
  @ObservedObject private var importConnectorStatusStore: ImportConnectorStatusStore
  @State private var selectedImportConnector: ImportConnector?
  /// Language step: false shows the detected default + Continue; true reveals the picker.
  @State private var languageChanging = false

  /// Same dune background as sign-in, for a continuous entry experience.
  private static let backgroundImage: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "signin_bg", withExtension: "png") else { return nil }
    return NSImage(contentsOf: url)
  }()

  init(
    appState: AppState,
    chatProvider: ChatProvider,
    importConnectorStatusStore: ImportConnectorStatusStore,
    onComplete: (() -> Void)?
  ) {
    _model = StateObject(
      wrappedValue: SBOnboardingModel(appState: appState, chatProvider: chatProvider, onComplete: onComplete))
    _importConnectorStatusStore = ObservedObject(wrappedValue: importConnectorStatusStore)
  }

  var body: some View {
    ZStack {
      if let bg = Self.backgroundImage {
        Image(nsImage: bg)
          .resizable()
          .scaledToFill()
          .overlay(
            LinearGradient(
              colors: [.black.opacity(0.4), .black.opacity(0.5), .black.opacity(0.72)],
              startPoint: .top, endPoint: .bottom)
          )
          .frame(maxWidth: .infinity, maxHeight: .infinity)
          .clipped()
          .ignoresSafeArea()
      } else {
        SBWallpaper()
      }
      panel
        .frame(width: 540, height: min(640, 900))
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .overlay(alignment: .topTrailing) {
      Button(action: { model.skip() }) {
        Text("Skip")
          .geist(size: 13).foregroundStyle(sb.ink(.w45))
          .padding(.horizontal, 14).padding(.vertical, 7)
          .background(
            Capsule().fill(Color.white.opacity(0.06))
              .background(.ultraThinMaterial, in: Capsule())
          )
          .overlay(Capsule().stroke(Color.white.opacity(0.12), lineWidth: 1))
      }
      .buttonStyle(.plain)
      .help("Skip onboarding and go to your second brain")
      .padding(.top, 20).padding(.trailing, 24)
    }
    .onAppear { model.begin() }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      if model.step == .context { refreshContextStates() }
    }
    .onChange(of: model.step) { _, step in
      if step == .context { refreshContextStates() }
    }
    .onReceive(importConnectorStatusStore.connectorDidSync) { connectorID in
      model.markContextImportConnected(connectorID)
    }
    .dismissableSheet(item: $selectedImportConnector) { connector in
      ImportConnectorSheet(
        connector: connector,
        appState: nil,
        statusStore: importConnectorStatusStore,
        onDismiss: { selectedImportConnector = nil }
      )
      .frame(width: 520, height: 620)
    }
    // Safety net: the `.shortcut` step suspends global hotkeys and nulls the main
    // menu (restored only via the advance/skip/complete buttons). If the view is
    // removed by any other path (e.g. auth flips to signed-out), restore them here
    // so hotkeys/menu aren't left disabled until relaunch. Idempotent when unarmed.
    .onDisappear { model.disarmShortcutSummon() }
  }

  private var panel: some View {
    VStack(spacing: 0) {
      ScrollViewReader { proxy in
        ScrollView {
          VStack(alignment: .leading, spacing: 14) {
            ForEach(model.thread) { msg in
              messageRow(msg)
            }
            if let streaming = model.streamingText {
              omiRow(streaming)
            }
            if model.typing {
              HStack(spacing: 10) {
                SBLogo(size: 16, spinning: true)
                Text("omi is typing…").geist(size: 12.5).foregroundStyle(sb.ink(.w4))
              }
            }
            if model.showWidget {
              widget.padding(.leading, 26).padding(.top, 2)
                .id("widget")
            }
            Color.clear.frame(height: 4).id("bottom")
          }
          .padding(.horizontal, 28).padding(.top, 26).padding(.bottom, 10)
        }
        .onChange(of: model.thread.count) { _, _ in scrollDown(proxy) }
        .onChange(of: model.showWidget) { _, _ in scrollDown(proxy) }
        .onChange(of: model.streamingText) { _, _ in scrollDown(proxy) }
        .onChange(of: model.shortcutPicked) { _, _ in scrollDown(proxy) }
        .onChange(of: model.shortcutPressed) { _, _ in scrollDown(proxy) }
      }
      // No progress dots — the user shouldn't count steps or feel a finish line.
      Color.clear.frame(height: 14)
    }
    .background(
      RoundedRectangle(cornerRadius: 18, style: .continuous)
        .fill(Color.white.opacity(0.05))
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    )
    .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(Color.white.opacity(0.12), lineWidth: 1))
    .shadow(color: .black.opacity(0.5), radius: 60, y: 30)
  }

  private func scrollDown(_ proxy: ScrollViewProxy) {
    withAnimation(.easeOut(duration: 0.25)) { proxy.scrollTo("bottom", anchor: .bottom) }
  }

  @ViewBuilder private func messageRow(_ msg: SBOnboardingModel.Msg) -> some View {
    if msg.isOmi { omiRow(msg.text) } else { meRow(msg.text) }
  }

  private func omiRow(_ text: String) -> some View {
    HStack(alignment: .top, spacing: 10) {
      SBLogo(size: 16, opacity: 0.9)
      Text(text).geist(size: 15.5).foregroundStyle(sb.ink(.w88)).lineSpacing(3)
        .frame(maxWidth: 380, alignment: .leading)
      Spacer(minLength: 0)
    }
  }

  private func meRow(_ text: String) -> some View {
    HStack {
      Spacer(minLength: 40)
      Text(text).geist(size: 15).foregroundStyle(sb.ink)
        .padding(.horizontal, 13).padding(.vertical, 8)
        .background(RoundedRectangle(cornerRadius: 13, style: .continuous).fill(sb.ink(.w1)))
        .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous).stroke(sb.ink(.w14), lineWidth: 1))
    }
  }

  // MARK: - Widgets per step

  @ViewBuilder private var widget: some View {
    switch model.step {
    case .promise: promiseWidget
    case .name: nameWidget
    case .howHeard: howHeardWidget
    case .language: languageWidget
    case .role: roleWidget
    case .mic: permStepWidget("microphone", "Microphone", "hears your side of conversations") { model.answerMic() }
    case .systemAudio:
      permStepWidget("system_audio", "System audio", "the other side — Zoom, Meet, calls") { model.answerSystemAudio() }
    case .screen:
      permStepWidget("screen_recording", "Screen Recording", "so I can see what you're looking at") {
        model.answerScreen()
      }
    case .files:
      permStepWidget("full_disk_access", "Full Disk Access", "cite your files · read-only, stays on this Mac") {
        model.answerFiles()
      }
    case .accessibility:
      permStepWidget("accessibility", "Accessibility", "catch your shortcut + click/type for you") {
        model.answerAccessibility()
      }
    case .automation:
      permStepWidget("automation", "Automation", "help with tasks in the apps you choose") {
        model.answerAutomation()
      }
    case .shortcutOpen: shortcutWidget(isTalk: false)
    case .shortcutTalk: shortcutWidget(isTalk: true)
    case .screenDemo: screenDemoWidget
    case .agents: agentsWidget
    case .context: contextWidget
    case .capture: captureWidget
    }
  }

  private var promiseWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      VStack(spacing: 0) {
        trustRow("OPEN") {
          HStack(spacing: 0) {
            Text("Every line of me is on ")
            Link("GitHub", destination: SBOnboardingRepository.url)
              .underline()
            Text(".")
          }
        }
        Divider().overlay(sb.ink(.w08))
        trustRow("PRIVATE") { Text("Your data is encrypted, and only yours.") }
        Divider().overlay(sb.ink(.w08))
        trustRow("YOURS") { Text("Pause me anytime. Delete anything, forever.") }
      }
      .overlay(RoundedRectangle(cornerRadius: 13).stroke(sb.ink(.w1), lineWidth: 1))
      SBInkButton(title: "Set up Omi →") { model.answerPromise() }
    }
  }

  private func trustRow<Content: View>(_ tag: String, @ViewBuilder content: () -> Content) -> some View {
    HStack(alignment: .top, spacing: 12) {
      Text(tag).geistMono(size: 11.5, weight: .medium).foregroundStyle(sb.ink(.w4)).frame(
        width: 52, alignment: .leading)
      content().geist(size: 14).foregroundStyle(sb.ink(.w85))
      Spacer(minLength: 0)
    }
    .padding(.horizontal, 14).padding(.vertical, 12)
  }

  private var nameWidget: some View {
    HStack(spacing: 8) {
      TextField("your name", text: $model.nameDraft)
        .textFieldStyle(.plain).geist(size: 15, weight: .medium).foregroundStyle(sb.ink)
        .padding(.horizontal, 13).padding(.vertical, 9)
        .background(RoundedRectangle(cornerRadius: 10).fill(sb.ink(.w06)))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(sb.ink(.w12), lineWidth: 1))
        .onSubmit { model.answerName() }
      SBInkButton(title: "→", horizontalPadding: 15, verticalPadding: 9) { model.answerName() }
    }
    .frame(maxWidth: 360, alignment: .leading)
  }

  private var howHeardWidget: some View {
    FlowChips(items: SBOnboardingModel.howHeardSources) { source in
      model.pickHowHeard(source)
    }
  }

  private var languageWidget: some View {
    let all = AssistantSettings.supportedLanguages
    let draft = model.languageDraft.trimmingCharacters(in: .whitespaces)
    return VStack(alignment: .leading, spacing: 12) {
      if !languageChanging, !draft.isEmpty {
        // Auto-detected default: accept with one tap, or reveal the picker.
        HStack(spacing: 8) {
          Text(draft).geist(size: 17, weight: .medium).foregroundStyle(sb.ink)
          Text("· detected").geist(size: 12.5).foregroundStyle(sb.ink(.w4))
        }
        SBInkButton(title: "Continue") {
          if let m = all.first(where: { $0.name.lowercased() == draft.lowercased() }) {
            model.pickLanguage(code: m.code, name: m.name)
          } else {
            model.answerLanguageText()
          }
        }
        Button {
          languageChanging = true
        } label: {
          Text("Change language").geist(size: 13).foregroundStyle(sb.ink(.w45))
        }
        .buttonStyle(.plain)
      } else {
        let filter = draft.lowercased()
        let matches: [(code: String, name: String)] =
          filter.isEmpty
          ? Array(all.prefix(6))
          : Array(
            all.filter { $0.name.lowercased().contains(filter) || $0.code.lowercased().hasPrefix(filter) }.prefix(6))
        TextField("Type a language…", text: $model.languageDraft)
          .textFieldStyle(.plain).geist(size: 15).foregroundStyle(sb.ink)
          .padding(.horizontal, 13).padding(.vertical, 10)
          .background(RoundedRectangle(cornerRadius: 10).fill(sb.ink(.w06)))
          .overlay(RoundedRectangle(cornerRadius: 10).stroke(sb.ink(.w12), lineWidth: 1))
          .onSubmit { if let first = matches.first { model.pickLanguage(code: first.code, name: first.name) } }
        if !matches.isEmpty {
          VStack(spacing: 0) {
            ForEach(matches, id: \.code) { lang in
              Button {
                model.pickLanguage(code: lang.code, name: lang.name)
              } label: {
                HStack {
                  Text(lang.name).geist(size: 14).foregroundStyle(sb.ink(.w85))
                  Spacer()
                  Text(lang.code).geistMono(size: 11).foregroundStyle(sb.ink(.w35))
                }
                .padding(.horizontal, 13).padding(.vertical, 9)
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
              }
              .buttonStyle(.plain)
              if lang.code != matches.last?.code { Divider().overlay(sb.ink(.w06)) }
            }
          }
          .overlay(RoundedRectangle(cornerRadius: 11).stroke(sb.ink(.w1), lineWidth: 1))
        }
      }
    }
    .frame(maxWidth: 340, alignment: .leading)
  }

  private var roleWidget: some View {
    VStack(alignment: .leading, spacing: 10) {
      FlowChips(items: ["Student", "Sales", "Consultant", "Founder", "Engineer", "Analyst", "Creator", "Other"]) { r in
        model.pickRole(r)
      }
      HStack(spacing: 8) {
        TextField("or just say it in your own words…", text: $model.roleDraft)
          .textFieldStyle(.plain).geist(size: 14).foregroundStyle(sb.ink)
          .padding(.horizontal, 13).padding(.vertical, 9)
          .background(RoundedRectangle(cornerRadius: 10).fill(sb.ink(.w06)))
          .overlay(RoundedRectangle(cornerRadius: 10).stroke(sb.ink(.w12), lineWidth: 1))
          .onSubmit { model.answerRoleText() }
        SBInkButton(title: "→", horizontalPadding: 15, verticalPadding: 9) { model.answerRoleText() }
      }
      .frame(maxWidth: 360)
    }
  }

  // MARK: permissions (one at a time)

  private func permStepWidget(
    _ key: String, _ name: String, _ why: String, onContinue: @escaping () -> Void
  ) -> some View {
    let state = model.permState(key)
    return VStack(alignment: .leading, spacing: 10) {
      VStack(alignment: .leading, spacing: 3) {
        Text(name).geist(size: 14, weight: .medium).foregroundStyle(sb.ink)
        Text(why).geist(size: 12.5).foregroundStyle(sb.ink(.w45))
      }
      if state == .on {
        Button {
          onContinue()
        } label: {
          HStack(spacing: 6) {
            Text("✓  \(name) on").geist(size: 14, weight: .semibold)
            Spacer()
            Text("Continue →").geist(size: 14, weight: .semibold)
          }
          .foregroundStyle(sb.inkInverted)
          .padding(.horizontal, 14).padding(.vertical, 11)
          .frame(maxWidth: .infinity)
          .background(RoundedRectangle(cornerRadius: 11).fill(sb.ink))
          .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
      } else {
        Button {
          if state == .ask { model.requestPerm(key) }
        } label: {
          Text(state == .waiting ? "Waiting for macOS…" : "Allow \(name)")
            .geist(size: 14, weight: .semibold).foregroundStyle(sb.inkInverted)
            .frame(maxWidth: .infinity).padding(.vertical, 11)
            .background(RoundedRectangle(cornerRadius: 11).fill(state == .waiting ? sb.ink(.w4) : sb.ink))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(state == .waiting)
        Button {
          onContinue()
        } label: {
          Text("Skip for now").geist(size: 13).foregroundStyle(sb.ink(.w35))
        }
        .buttonStyle(.plain)
      }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  /// A physical-looking keycap (symbol + key name for modifiers, centered glyph
  /// otherwise), mirroring the legacy OnboardingKeyCapView. Lights up when `active`.
  private static let keyNames: [String: String] = [
    "⌘": "command", "⇧": "shift", "⌥": "option", "⌃": "control", "↩": "return", "⏎": "return",
  ]

  @ViewBuilder
  private func keycap(_ text: String, active: Bool = false) -> some View {
    let name = Self.keyNames[text]
    Group {
      if let name {
        VStack(spacing: 1) {
          Text(text).font(.system(size: 14, weight: .semibold)).frame(maxWidth: .infinity, alignment: .leading)
          Text(name).font(.system(size: 8, weight: .medium)).lineLimit(1).fixedSize()
            .frame(maxWidth: .infinity, alignment: .center)
        }
      } else {
        Text(text).font(.system(size: 15, weight: .semibold))
      }
    }
    .foregroundStyle(active ? sb.inkInverted : sb.ink(.w9))
    .frame(minWidth: 34, minHeight: 34)
    .padding(.horizontal, 7).padding(.vertical, 5)
    .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(active ? sb.ink : sb.ink(.w06)))
    .overlay(
      RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(active ? sb.ink : sb.ink(.w18), lineWidth: 1.5)
    )
    .shadow(color: .black.opacity(0.28), radius: 1, y: 1)
    .fixedSize()
  }

  // MARK: summon shortcut

  private func shortcutWidget(isTalk: Bool) -> some View {
    let options = isTalk ? model.talkShortcutOptions : model.openShortcutOptions
    return VStack(alignment: .leading, spacing: 9) {
      ForEach(options, id: \.id) { opt in
        Button {
          model.pickShortcut(opt.shortcut, isTalk: isTalk)
        } label: {
          HStack(spacing: 8) {
            HStack(spacing: 5) {
              ForEach(opt.shortcut.displayTokens, id: \.self) { tok in keycap(tok) }
            }
            Text(opt.sub).geist(size: 13).foregroundStyle(sb.ink(.w45))
            Spacer()
            if model.chosenShortcut == opt.shortcut {
              Text("✓").geist(size: 14).foregroundStyle(sb.ink(.w7))
            }
          }
          .padding(.horizontal, 14).padding(.vertical, 11)
          .frame(maxWidth: .infinity, alignment: .leading)
          .contentShape(Rectangle())
          .overlay(
            RoundedRectangle(cornerRadius: 11)
              .stroke(model.chosenShortcut == opt.shortcut ? sb.ink(.w3) : sb.ink(.w14), lineWidth: 1))
        }
        .buttonStyle(.plain)
      }
      if model.shortcutPicked {
        VStack(alignment: .leading, spacing: 10) {
          HStack(spacing: 6) {
            ForEach(model.shortcutTokens, id: \.self) { tok in keycap(tok, active: model.shortcutPressed) }
          }
          Text(
            model.shortcutPressed
              ? "Perfect, that works."
              : (isTalk ? "Now hold it and say something." : "Now give it a tap.")
          )
          .geist(size: 15, weight: .medium)
          .foregroundStyle(model.shortcutPressed ? sb.ink(.w85) : sb.ink(.w6))
        }
        .padding(.top, 6)
      }
      // Continue only appears once the key has actually been pressed; before that,
      // just a quiet Skip so the user is never stuck.
      Group {
        if model.shortcutPressed {
          SBInkButton(title: "Continue") { isTalk ? model.answerShortcutTalk() : model.answerShortcutOpen() }
        } else {
          Button {
            isTalk ? model.answerShortcutTalk() : model.answerShortcutOpen()
          } label: {
            Text("Skip for now").geist(size: 13).foregroundStyle(sb.ink(.w35))
          }
          .buttonStyle(.plain)
        }
      }
      .padding(.top, 6)
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  // MARK: screen + voice demo

  private var screenDemoWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      VStack(alignment: .leading, spacing: 6) {
        HStack(spacing: 5) {
          Text("Hold").geist(size: 14).foregroundStyle(sb.ink(.w85))
          ForEach(model.voiceChordTokens, id: \.self) { tok in keycap(tok) }
          Text("and ask me about it, out loud.").geist(size: 14).foregroundStyle(sb.ink(.w85))
        }
        Text("Try \u{201c}what's on my screen right now?\u{201d} I can see it, and I answer at the top of your screen.")
          .geist(size: 12.5).foregroundStyle(sb.ink(.w45))
          .fixedSize(horizontal: false, vertical: true)
      }
      // Continue appears once Omi has actually answered — before that, an always-
      // tappable, clearly-visible "Skip for now" so the user is never stuck if the
      // demo doesn't fire (it used to be a tiny, easily-missed text link).
      Group {
        if model.screenDemoDone {
          SBInkButton(title: "Continue") { model.answerScreenDemo() }
        } else {
          Button {
            model.answerScreenDemo()
          } label: {
            Text("Skip for now").geist(size: 14, weight: .medium).foregroundStyle(sb.ink(.w85))
              .frame(maxWidth: .infinity).padding(.vertical, 11)
              .overlay(RoundedRectangle(cornerRadius: 11).stroke(sb.ink(.w18), lineWidth: 1))
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
        }
      }
      .padding(.top, 6)
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  // MARK: agents + context connectors

  private var agentsWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      VStack(spacing: 0) {
        ForEach(Array(model.agentRows.enumerated()), id: \.element.id) { i, row in
          connectRow(id: row.id, row.name, row.detail, state: model.agentStates[row.id] ?? "idle") {
            model.connectAgent(row.id)
          }
          if i < model.agentRows.count - 1 { Divider().overlay(sb.ink(.w08)) }
        }
      }
      .padding(.horizontal, 14)
      .overlay(RoundedRectangle(cornerRadius: 13).stroke(sb.ink(.w1), lineWidth: 1))
      SBInkButton(title: "Continue") { model.answerAgents() }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  private var contextWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      VStack(spacing: 0) {
        ForEach(Array(model.contextRows.enumerated()), id: \.element.id) { i, row in
          connectRow(
            id: row.id,
            row.name,
            model.contextDetails[row.id] ?? row.detail,
            state: model.contextStates[row.id] ?? "idle"
          ) {
            connectContext(row.id)
          }
          if i < model.contextRows.count - 1 { Divider().overlay(sb.ink(.w08)) }
        }
      }
      .padding(.horizontal, 14)
      .overlay(RoundedRectangle(cornerRadius: 13).stroke(sb.ink(.w1), lineWidth: 1))
      SBInkButton(title: "Continue") { model.answerContext() }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  private func connectContext(_ id: String) {
    switch SBOnboardingModel.contextConnectionRoute(for: id) {
    case .importConnector(let connectorID):
      selectedImportConnector = ImportConnector.all.first { $0.id == connectorID }
    case .direct:
      model.connectContext(id)
    }
  }

  private func refreshContextStates() {
    model.refreshContextStates()
    importConnectorStatusStore.refreshPersistedManualImportMetrics()
    for connectorID in ["chatgpt", "claude"] {
      guard
        let connector = ImportConnector.all.first(where: { $0.id == connectorID }),
        importConnectorStatusStore.snapshot(for: connector).isConnected
      else { continue }
      model.markContextImportConnected(connectorID)
    }
  }

  private func connectRow(id: String, _ name: String, _ detail: String, state: String, action: @escaping () -> Void)
    -> some View
  {
    VStack(alignment: .leading, spacing: 8) {
      HStack(spacing: 12) {
        ConnectorBrandIcon(brand: model.connectorBrand(id), size: 26, cornerRadius: 7)
        VStack(alignment: .leading, spacing: 1) {
          Text(name).geist(size: 14, weight: .medium).foregroundStyle(sb.ink)
          Text(detail).geist(size: 12).foregroundStyle(sb.ink(.w4))
        }
        Spacer(minLength: 8)
        connectTrailing(state, action: action)
      }
      // Once Claude Code is connected, surface the restart prompt/button so its
      // running sessions actually reload the new MCP config (#10205).
      if id == "claudeCode", state == "on" {
        ClaudeCodeRestartSubtitle()
      }
    }
    .padding(.vertical, 10)
  }

  @ViewBuilder
  private func connectTrailing(_ state: String, action: @escaping () -> Void) -> some View {
    switch state {
    case "on": Text("✓ on").geistMono(size: 12).foregroundStyle(sb.ink(.w6))
    case "connecting": Text("…").geistMono(size: 13).foregroundStyle(sb.ink(.w4))
    case "checking": Text("checking…").geist(size: 12).foregroundStyle(sb.ink(.w35))
    case "unavailable": Text("not installed").geist(size: 12).foregroundStyle(sb.ink(.w35))
    case "error":
      Button(action: action) {
        Text("Retry").geist(size: 13, weight: .semibold).foregroundStyle(sb.inkInverted)
          .padding(.horizontal, 12).padding(.vertical, 4)
          .background(RoundedRectangle(cornerRadius: 7).fill(sb.ink))
      }
      .buttonStyle(.plain)
    default:
      Button(action: action) {
        Text(state == "needsSignIn" ? "Retry" : "Connect").geist(size: 13, weight: .semibold).foregroundStyle(
          sb.inkInverted
        )
        .padding(.horizontal, 12).padding(.vertical, 4)
        .background(RoundedRectangle(cornerRadius: 7).fill(sb.ink))
      }
      .buttonStyle(.plain)
    }
  }

  // MARK: capture

  private var captureWidget: some View {
    VStack(spacing: 8) {
      // The chosen open-Omi chord as keycap chips (e.g. ⌘ O), matching the ⌥ keycap
      // on the demo step — instead of plain "⌘O" glyphs buried in the message copy.
      if !model.summonTokens.isEmpty {
        HStack(spacing: 5) {
          ForEach(model.summonTokens, id: \.self) { tok in keycap(tok) }
          Text("reaches me anytime").geist(size: 14).foregroundStyle(sb.ink(.w85))
          Spacer(minLength: 0)
        }
        .padding(.bottom, 2)
      }
      Button {
        model.captureContinuous()
      } label: {
        Text("● Start listening — continuously").geist(size: 14, weight: .semibold).foregroundStyle(sb.inkInverted)
          .frame(maxWidth: .infinity).padding(.vertical, 11)
          .background(RoundedRectangle(cornerRadius: 11).fill(sb.ink))
      }
      .buttonStyle(.plain)
      Button {
        model.captureMeetingsOnly()
      } label: {
        HStack(spacing: 4) {
          Text("Only during meetings").geist(size: 14).foregroundStyle(sb.ink(.w85))
          Text("· from my calendar").geist(size: 12).foregroundStyle(sb.ink(.w4))
        }
        .frame(maxWidth: .infinity).padding(.vertical, 11)
        .overlay(RoundedRectangle(cornerRadius: 11).stroke(sb.ink(.w18), lineWidth: 1))
      }
      .buttonStyle(.plain)
    }
    .frame(maxWidth: 340, alignment: .leading)
  }
}

/// Wrapping chip row where each chip hugs its content (no wide grid cells that
/// push short chips far apart).
private struct FlowChips: View {
  @Environment(\.sbTheme) private var sb
  let items: [String]
  let onPick: (String) -> Void
  var body: some View {
    ChipFlowLayout(spacing: 8, lineSpacing: 8) {
      ForEach(items, id: \.self) { item in
        Button {
          onPick(item)
        } label: {
          Text(item).geist(size: 14).foregroundStyle(sb.ink(.w85))
            .padding(.horizontal, 15).padding(.vertical, 8)
            .overlay(Capsule().stroke(sb.ink(.w14), lineWidth: 1))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
      }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }
}

/// Minimal left-to-right wrapping flow layout (content-hugging).
private struct ChipFlowLayout: Layout {
  var spacing: CGFloat = 8
  var lineSpacing: CGFloat = 8

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
    let maxWidth = proposal.width ?? 380
    var x: CGFloat = 0
    var y: CGFloat = 0
    var rowHeight: CGFloat = 0
    for sub in subviews {
      let size = sub.sizeThatFits(.unspecified)
      if x + size.width > maxWidth, x > 0 {
        x = 0
        y += rowHeight + lineSpacing
        rowHeight = 0
      }
      x += size.width + spacing
      rowHeight = max(rowHeight, size.height)
    }
    return CGSize(width: maxWidth, height: y + rowHeight)
  }

  func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
    var x: CGFloat = bounds.minX
    var y: CGFloat = bounds.minY
    var rowHeight: CGFloat = 0
    for sub in subviews {
      let size = sub.sizeThatFits(.unspecified)
      if x + size.width > bounds.minX + bounds.width, x > bounds.minX {
        x = bounds.minX
        y += rowHeight + lineSpacing
        rowHeight = 0
      }
      sub.place(at: CGPoint(x: x, y: y), anchor: .topLeading, proposal: ProposedViewSize(size))
      x += size.width + spacing
      rowHeight = max(rowHeight, size.height)
    }
  }
}
