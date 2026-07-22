import AppKit
import OmiTheme
import SwiftUI

/// The Second Brain conversational onboarding — a chat with Omi that streams
/// word-by-word and performs real side-effects. Replaces the legacy wizard.
struct SBOnboardingView: View {
  @Environment(\.sbTheme) private var sb
  @StateObject private var model: SBOnboardingModel

  /// Same dune background as sign-in, for a continuous entry experience.
  private static let backgroundImage: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "signin_bg", withExtension: "png") else { return nil }
    return NSImage(contentsOf: url)
  }()

  init(appState: AppState, chatProvider: ChatProvider, onComplete: (() -> Void)?) {
    _model = StateObject(
      wrappedValue: SBOnboardingModel(appState: appState, chatProvider: chatProvider, onComplete: onComplete))
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
    case .language: languageWidget
    case .role: roleWidget
    case .mic: permStepWidget("microphone", "Microphone", "hears your side of conversations") { model.answerMic() }
    case .systemAudio:
      permStepWidget("system_audio", "System audio", "the other side — Zoom, Meet, calls") { model.answerSystemAudio() }
    case .screen:
      permStepWidget("screen_recording", "Screen Recording", "so I can see what you're looking at") { model.answerScreen() }
    case .files:
      permStepWidget("full_disk_access", "Full Disk Access", "cite your files · read-only, stays on this Mac") {
        model.answerFiles()
      }
    case .accessibility:
      permStepWidget("accessibility", "Accessibility", "catch your shortcut + click/type for you") {
        model.answerAccessibility()
      }
    case .automation:
      permStepWidget("automation", "Automation", "drive your other apps to get things done") { model.answerAutomation() }
    case .shortcut: shortcutWidget
    case .screenDemo: screenDemoWidget
    case .agents: agentsWidget
    case .context: contextWidget
    case .capture: captureWidget
    }
  }

  private var promiseWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      VStack(spacing: 0) {
        trustRow("OPEN", "Every line of me is on GitHub.")
        Divider().overlay(sb.ink(.w08))
        trustRow("PRIVATE", "Your data is encrypted, and only yours.")
        Divider().overlay(sb.ink(.w08))
        trustRow("YOURS", "Pause me from the notch. Delete anything, forever.")
      }
      .overlay(RoundedRectangle(cornerRadius: 13).stroke(sb.ink(.w1), lineWidth: 1))
      SBInkButton(title: "Set up Omi →") { model.answerPromise() }
    }
  }

  private func trustRow(_ tag: String, _ text: String) -> some View {
    HStack(alignment: .top, spacing: 12) {
      Text(tag).geistMono(size: 11.5, weight: .medium).foregroundStyle(sb.ink(.w4)).frame(width: 52, alignment: .leading)
      Text(text).geist(size: 14).foregroundStyle(sb.ink(.w85))
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

  private var languageWidget: some View {
    let draft = model.languageDraft.trimmingCharacters(in: .whitespaces).lowercased()
    let all = AssistantSettings.supportedLanguages
    let matches: [(code: String, name: String)] =
      draft.isEmpty
      ? Array(all.prefix(6))
      : Array(all.filter { $0.name.lowercased().contains(draft) || $0.code.lowercased().hasPrefix(draft) }.prefix(6))
    return VStack(alignment: .leading, spacing: 8) {
      TextField("Type a language…", text: $model.languageDraft)
        .textFieldStyle(.plain).geist(size: 15).foregroundStyle(sb.ink)
        .padding(.horizontal, 13).padding(.vertical, 10)
        .background(RoundedRectangle(cornerRadius: 10).fill(sb.ink(.w06)))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(sb.ink(.w12), lineWidth: 1))
        .onSubmit { if let first = matches.first { model.pickLanguage(code: first.code, name: first.name) } }
      if !matches.isEmpty {
        VStack(spacing: 0) {
          ForEach(matches, id: \.code) { lang in
            Button { model.pickLanguage(code: lang.code, name: lang.name) } label: {
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
    .frame(maxWidth: 340, alignment: .leading)
  }

  private var roleWidget: some View {
    VStack(alignment: .leading, spacing: 10) {
      FlowChips(items: ["Student", "Sales", "Consultant", "Founder", "Engineer", "Creator"]) { r in
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
        Button { onContinue() } label: {
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
        Button { if state == .ask { model.requestPerm(key) } } label: {
          Text(state == .waiting ? "Waiting for macOS…" : "Allow \(name)")
            .geist(size: 14, weight: .semibold).foregroundStyle(sb.inkInverted)
            .frame(maxWidth: .infinity).padding(.vertical, 11)
            .background(RoundedRectangle(cornerRadius: 11).fill(state == .waiting ? sb.ink(.w4) : sb.ink))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(state == .waiting)
        Button { onContinue() } label: {
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
    .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(active ? sb.ink : sb.ink(.w18), lineWidth: 1.5))
    .shadow(color: .black.opacity(0.28), radius: 1, y: 1)
    .fixedSize()
  }

  // MARK: summon shortcut

  private var shortcutWidget: some View {
    VStack(alignment: .leading, spacing: 9) {
      ForEach(model.shortcutOptions, id: \.id) { opt in
        Button { model.pickShortcut(opt) } label: {
          HStack(spacing: 8) {
            HStack(spacing: 4) {
              ForEach(opt.shortcut.displayTokens, id: \.self) { tok in keycap(tok) }
            }
            Text(opt.sub).geist(size: 12).foregroundStyle(sb.ink(.w45))
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
        VStack(alignment: .leading, spacing: 7) {
          HStack(spacing: 6) {
            ForEach(model.shortcutTokens, id: \.self) { tok in keycap(tok, active: model.shortcutPressed) }
          }
          Text(model.shortcutPressed ? "✓ Nice, that's your key." : "Now press it to test.")
            .geist(size: 13).foregroundStyle(model.shortcutPressed ? sb.ink(.w7) : sb.ink(.w5))
        }
        .padding(.top, 4)
      }
      SBInkButton(title: model.shortcutPicked ? "Continue" : "Skip for now") { model.answerShortcut() }
        .padding(.top, 2)
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  // MARK: screen + voice demo

  private var screenDemoWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      macLineup
        .frame(maxWidth: 380)
      VStack(alignment: .leading, spacing: 6) {
        HStack(spacing: 5) {
          Text("Hold").geist(size: 14).foregroundStyle(sb.ink(.w85))
          ForEach(model.voiceChordTokens, id: \.self) { tok in keycap(tok) }
          Text("and ask me about it, out loud.").geist(size: 14).foregroundStyle(sb.ink(.w85))
        }
        Text("Try \u{201c}what's on my screen right now?\u{201d} I can see it, and I answer up in the notch.")
          .geist(size: 12.5).foregroundStyle(sb.ink(.w45))
          .fixedSize(horizontal: false, vertical: true)
      }
      SBInkButton(title: "Continue") { model.answerScreenDemo() }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  /// The Mac lineup illustration reused from the legacy floating-bar demo step.
  private static let macLineupImage: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "onboarding_mac_lineup", withExtension: "png") else {
      return nil
    }
    return NSImage(contentsOf: url)
  }()

  @ViewBuilder private var macLineup: some View {
    if let img = Self.macLineupImage {
      Image(nsImage: img)
        .resizable()
        .interpolation(.high)
        .scaledToFit()
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(sb.ink(.w1), lineWidth: 1))
    }
  }

  // MARK: agents + context connectors

  private var agentsWidget: some View {
    VStack(alignment: .leading, spacing: 12) {
      VStack(spacing: 0) {
        ForEach(Array(model.agentRows.enumerated()), id: \.element.id) { i, row in
          connectRow(row.name, row.detail, state: model.agentStates[row.id] ?? "idle") { model.connectAgent(row.id) }
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
          connectRow(row.name, row.detail, state: model.contextStates[row.id] ?? "idle") { model.connectContext(row.id) }
          if i < model.contextRows.count - 1 { Divider().overlay(sb.ink(.w08)) }
        }
      }
      .padding(.horizontal, 14)
      .overlay(RoundedRectangle(cornerRadius: 13).stroke(sb.ink(.w1), lineWidth: 1))
      SBInkButton(title: "Continue") { model.answerContext() }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  private func connectRow(_ name: String, _ detail: String, state: String, action: @escaping () -> Void) -> some View {
    HStack(spacing: 12) {
      VStack(alignment: .leading, spacing: 1) {
        Text(name).geist(size: 14, weight: .medium).foregroundStyle(sb.ink)
        Text(detail).geist(size: 12).foregroundStyle(sb.ink(.w4))
      }
      Spacer(minLength: 8)
      connectTrailing(state, action: action)
    }
    .padding(.vertical, 10)
  }

  @ViewBuilder
  private func connectTrailing(_ state: String, action: @escaping () -> Void) -> some View {
    switch state {
    case "on": Text("✓ on").geistMono(size: 12).foregroundStyle(sb.ink(.w6))
    case "connecting": Text("…").geistMono(size: 13).foregroundStyle(sb.ink(.w4))
    case "unavailable": Text("not installed").geist(size: 12).foregroundStyle(sb.ink(.w35))
    default:
      Button(action: action) {
        Text(state == "needsSignIn" ? "Retry" : "Connect").geist(size: 13, weight: .semibold).foregroundStyle(sb.inkInverted)
          .padding(.horizontal, 12).padding(.vertical, 4)
          .background(RoundedRectangle(cornerRadius: 7).fill(sb.ink))
      }
      .buttonStyle(.plain)
    }
  }

  // MARK: capture

  private var captureWidget: some View {
    VStack(spacing: 8) {
      Button { model.captureContinuous() } label: {
        Text("● Start listening — continuously").geist(size: 14, weight: .semibold).foregroundStyle(sb.inkInverted)
          .frame(maxWidth: .infinity).padding(.vertical, 11)
          .background(RoundedRectangle(cornerRadius: 11).fill(sb.ink))
      }
      .buttonStyle(.plain)
      Button { model.captureMeetingsOnly() } label: {
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

/// Simple wrapping chip row.
private struct FlowChips: View {
  @Environment(\.sbTheme) private var sb
  let items: [String]
  let onPick: (String) -> Void
  var body: some View {
    let cols = [GridItem(.adaptive(minimum: 90), spacing: 7)]
    LazyVGrid(columns: cols, alignment: .leading, spacing: 7) {
      ForEach(items, id: \.self) { item in
        Button { onPick(item) } label: {
          Text(item).geist(size: 14).foregroundStyle(sb.ink(.w85))
            .padding(.horizontal, 16).padding(.vertical, 8)
            .overlay(Capsule().stroke(sb.ink(.w14), lineWidth: 1))
        }
        .buttonStyle(.plain)
      }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }
}
