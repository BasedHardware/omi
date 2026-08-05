import AppKit
import OmiTheme
import SwiftUI

enum SBOnboardingRepository {
  static let url = URL(string: "https://github.com/BasedHardware/omi")!
}

enum SBOnboardingPanelLayout {
  static let maximumSize = CGSize(width: 540, height: 640)
  static let horizontalInset: CGFloat = 24
  static let verticalInset: CGFloat = 20

  static func size(in availableSize: CGSize) -> CGSize {
    CGSize(
      width: min(maximumSize.width, max(0, availableSize.width - horizontalInset * 2)),
      height: min(maximumSize.height, max(0, availableSize.height - verticalInset * 2))
    )
  }
}

/// The Second Brain conversational onboarding — a chat with Omi that streams
/// word-by-word and performs real side-effects. Replaces the legacy wizard.
///
/// **It paints no ground.** A full-bleed dune photograph under a black gradient used to sit behind
/// this card, which meant the window's glass (`DesktopHomeView.glassShellGround` — "the one ground in
/// this window") was covered by the very first screen a new user reaches, and every label on it had
/// to be white to survive. On the light-pinned panel that art is gone and the type is near-black:
/// blurred desktop, one wash-and-hairline card, two rungs of ink.
///
/// The card itself was `Color.white.opacity(0.05)` over `.ultraThinMaterial`. That is *within-window*
/// vibrancy — it frosts the app's own content rather than the desktop — so it was never the same
/// material as the panel around it, and stacked a second scrim on a ground already tuned to the
/// contrast floor. It is `onboardingCard()` now, which is the shared wash the rest of the app's cards
/// are.
struct SBOnboardingView: View {
  @StateObject private var model: SBOnboardingModel
  @ObservedObject private var importConnectorStatusStore: ImportConnectorStatusStore
  @State private var selectedImportConnector: ImportConnector?
  /// Language step: false shows the detected default + Continue; true reveals the picker.
  @State private var languageChanging = false
  @State private var showAIAssistants = false

  init(
    appState: AppState,
    chatProvider: ChatProvider,
    importConnectorStatusStore: ImportConnectorStatusStore,
    onComplete: (() -> Void)?
  ) {
    _model = StateObject(
      wrappedValue: SBOnboardingModel(
        appState: appState,
        chatProvider: chatProvider,
        importConnectorStatusStore: importConnectorStatusStore,
        onComplete: onComplete
      ))
    _importConnectorStatusStore = ObservedObject(wrappedValue: importConnectorStatusStore)
  }

  var body: some View {
    GeometryReader { geometry in
      let panelSize = SBOnboardingPanelLayout.size(in: geometry.size)
      panel
        .frame(width: panelSize.width, height: panelSize.height)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    // Pins the panel's light appearance so `Ink`'s dynamic colours resolve dark here even on a
    // machine in Dark Mode. Without it this card is near-white type on a near-white ground.
    .glassContent()
    .overlay(alignment: .topTrailing) {
      ViewThatFits(in: .horizontal) {
        HStack(spacing: 8) {
          backButton
          skipButton
        }
        VStack(alignment: .trailing, spacing: 8) {
          backButton
          skipButton
        }
      }
      .padding(.top, 20).padding(.trailing, 24)
    }
    .onAppear { model.begin() }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      if model.step == .context { refreshContextStates() }
      // Granting a permission means leaving Omi for System Settings and coming
      // back, so this return is the signal a grant may have landed — not a 20s
      // poll that Full Disk Access and Accessibility routinely outlive.
      model.recheckActivePermission()
    }
    .onChange(of: model.step) { _, step in
      if step == .context { refreshContextStates() }
    }
    .onReceive(importConnectorStatusStore.connectorDidSync) { connectorID in
      model.markPersistedContextConnectorConnected(connectorID)
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
                Text("omi is typing…").inkStyle(InkType.statusLabel, color: Ink.secondary)
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
      // No progress dots — the user shouldn't count steps or feel a finish line. The strip is still
      // reserved rather than drawn over, which is the part that matters: a foot the column cannot
      // grow into (see `OnboardingProgressBand`).
      Color.clear.frame(height: 14)
    }
    // No shadow of its own. The window's panel already carries the one ambient shadow in this system,
    // and the 60 pt black drop this had inside it read as depth on the dark art and as dirt on glass.
    .onboardingCard()
  }

  @ViewBuilder private var backButton: some View {
    if model.canGoBack {
      Button(action: { model.goBack() }) {
        Text("← Back")
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
          .padding(.horizontal, 14).padding(.vertical, 7)
          .glassChip()
      }
      .buttonStyle(.plain)
      .help("Go back and change an earlier answer")
      .padding(.trailing, 12)
    }
  }

  private var skipButton: some View {
    Button(action: { model.skip() }) {
      Text("Skip")
        .inkStyle(InkType.statusLabel, color: Ink.secondary)
        .padding(.horizontal, 14).padding(.vertical, 7)
        .glassChip()
    }
    .buttonStyle(.plain)
    .help("Skip onboarding and go to your second brain")
  }

  private func scrollDown(_ proxy: ScrollViewProxy) {
    withAnimation(.easeOut(duration: 0.25)) { proxy.scrollTo("bottom", anchor: .bottom) }
  }

  @ViewBuilder private func messageRow(_ msg: SBOnboardingModel.Msg) -> some View {
    if msg.isOmi { omiRow(msg.text) } else { meRow(msg.text) }
  }

  /// Omi's turn. `prose` is the one role that carries paragraphs, and it is the reading rung — this
  /// is a sentence someone reads, not a label they glance at.
  private func omiRow(_ text: String) -> some View {
    HStack(alignment: .top, spacing: 10) {
      SBLogo(size: 16, opacity: 0.9)
      Text(text).inkStyle(InkType.prose, color: Ink.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: 380, alignment: .leading)
      Spacer(minLength: 0)
    }
  }

  /// The user's own turn, which is why it is `primary` against Omi's `secondary`: on this card the
  /// thing you said is the thing you look back for.
  private func meRow(_ text: String) -> some View {
    HStack {
      Spacer(minLength: 40)
      Text(text).inkStyle(InkType.rowCopy, color: Ink.primary)
        .fixedSize(horizontal: false, vertical: true)
        .padding(.horizontal, 13).padding(.vertical, 8)
        .glassRow(.selected)
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
    case .files: filesWidget
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
        // `GlassSeparator`, not `Divider()`: a `Divider` inherits the host window's appearance rather
        // than the panel's pinned one, so on a Dark machine it draws a light rule on a light card.
        GlassSeparator()
        trustRow("PRIVATE") { Text("Your data is encrypted, and only yours.") }
        GlassSeparator()
        trustRow("YOURS") { Text("Pause me anytime. Delete anything, forever.") }
      }
      .glassCard(cornerRadius: PageGlass.rowRadius)
      SBInkButton(title: "Set up Omi →", isDefaultAction: true) { model.answerPromise() }
    }
  }

  private func trustRow<Content: View>(_ tag: String, @ViewBuilder content: () -> Content) -> some View {
    HStack(alignment: .top, spacing: 12) {
      Text(tag).inkFont(InkType.statusLabel).foregroundStyle(Ink.secondary).frame(
        width: 52, alignment: .leading)
      // The promise is the copy this whole step exists for, so it never truncates — `PRIVATE` used to
      // carry `.lineLimit(1)` and lost its second half at any narrow width.
      content().inkStyle(InkType.rowCopy, color: Ink.primary)
        .fixedSize(horizontal: false, vertical: true)
      Spacer(minLength: 0)
    }
    .padding(.horizontal, 14).padding(.vertical, 12)
  }

  private var nameWidget: some View {
    HStack(spacing: 8) {
      TextField("your name", text: $model.nameDraft)
        .textFieldStyle(.plain).inkStyle(InkType.rowCopy, color: Ink.primary)
        .padding(.horizontal, 13).padding(.vertical, 9)
        .glassField()
        .onSubmit { model.answerName() }
      SBInkButton(title: "→", horizontalPadding: 15, verticalPadding: 9) { model.answerName() }
    }
    .frame(maxWidth: 360, alignment: .leading)
  }

  private var howHeardWidget: some View {
    FlowChips(items: SBOnboardingModel.howHeardSources, selectedItem: model.howHeard) { source in
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
          Text(draft).inkStyle(InkType.prose, color: Ink.primary)
          if model.languageIsDetectedFromMac {
            Text(SBOnboardingLanguageCopy.detectedLanguageDetail)
              .inkStyle(InkType.statusLabel, color: Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
        }
        SBInkButton(title: SBOnboardingLanguageCopy.continueAction(for: draft), isDefaultAction: true) {
          if let m = all.first(where: { $0.name.lowercased() == draft.lowercased() }) {
            model.pickLanguage(code: m.code, name: m.name)
          } else {
            model.answerLanguageText()
          }
        }
        Button {
          languageChanging = true
        } label: {
          Text(SBOnboardingLanguageCopy.changeSpokenLanguageAction)
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
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
          .textFieldStyle(.plain).inkStyle(InkType.rowCopy, color: Ink.primary)
          .padding(.horizontal, 13).padding(.vertical, 10)
          .glassField()
          .onSubmit { if let first = matches.first { model.pickLanguage(code: first.code, name: first.name) } }
        if !matches.isEmpty {
          VStack(spacing: 0) {
            ForEach(matches, id: \.code) { lang in
              Button {
                model.pickLanguage(code: lang.code, name: lang.name)
              } label: {
                HStack {
                  Text(lang.name).inkStyle(InkType.rowCopy, color: Ink.primary)
                  Spacer()
                  Text(lang.code).inkStyle(InkType.statusLabel, color: Ink.secondary)
                }
                .padding(.horizontal, 13).padding(.vertical, 9)
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
              }
              .buttonStyle(.plain)
              if lang.code != matches.last?.code { GlassSeparator() }
            }
          }
          .glassCard(cornerRadius: PageGlass.chipRadius)
        }
      }
    }
    .frame(maxWidth: 340, alignment: .leading)
  }

  private var roleWidget: some View {
    VStack(alignment: .leading, spacing: 10) {
      FlowChips(
        items: ["Student", "Sales", "Consultant", "Founder", "Engineer", "Analyst", "Creator", "Other"],
        selectedItem: model.role
      ) { r in
        model.pickRole(r)
      }
      HStack(spacing: 8) {
        TextField("or just say it in your own words…", text: $model.roleDraft)
          .textFieldStyle(.plain).inkStyle(InkType.rowCopy, color: Ink.primary)
          .padding(.horizontal, 13).padding(.vertical, 9)
          .glassField()
          .onSubmit { model.answerRoleText() }
        SBInkButton(title: "→", horizontalPadding: 15, verticalPadding: 9) { model.answerRoleText() }
      }
      .frame(maxWidth: 360)
    }
  }

  // MARK: permissions (one at a time)

  /// Every branch here is chosen by `model.permissionPrimaryAction`, so what the
  /// row can do is a property of the permission state rather than of a layout —
  /// and every branch keeps an explicit way forward, with the consequence spelled out.
  private func permStepWidget(
    _ key: String, _ name: String, _ why: String, onContinue: @escaping () -> Void
  ) -> some View {
    let action = model.permissionPrimaryAction(key)
    return VStack(alignment: .leading, spacing: 10) {
      VStack(alignment: .leading, spacing: 3) {
        Text(name).inkStyle(InkType.rowCopy, color: Ink.primary)
        // Every sentence on this card wraps and none of them truncate. Three of four shipped cut off
        // mid-word in the source app before this modifier went on, and a permission whose reason is
        // half-visible is a permission people deny.
        Text(why).inkStyle(InkType.statusLabel, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      if action == .reopen {
        Text("\(name) is on, but macOS only hands it to a fresh launch. Reopen me and I'll pick up right here.")
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
        Button {
          model.acceptPermissionRelaunch(key)
        } label: {
          Text("Reopen Omi").frame(maxWidth: .infinity)
        }
        .buttonStyle(InkButtonStyle(kind: .primary))
        // The escape, with the consequence spelled out — never gate a step on something macOS cannot
        // grant from a dialog. `secondary`, because on glass there is no fainter rung to hide it in,
        // and an escape nobody can read is an escape nobody takes.
        Button {
          onContinue()
        } label: {
          Text("Later — \(name) stays off until you reopen")
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
        .buttonStyle(.plain)
      } else if action == .proceed {
        Button {
          onContinue()
        } label: {
          HStack(spacing: 6) {
            Text("✓  \(name) on")
            Spacer()
            Text("Continue →")
          }
          .frame(maxWidth: .infinity)
        }
        .buttonStyle(InkButtonStyle(kind: .primary))
        .keyboardShortcut(.defaultAction)
      } else {
        // Never `.disabled`: while macOS is being waited on, the button becomes
        // a re-check. A grant that lands after the poll gave up used to leave
        // the user staring at a dead "Waiting for macOS…" with nothing to press.
        //
        // Waiting reads as a *secondary* capsule rather than a dimmed primary one: a filled pill at
        // 40% ink is the shape of a disabled control, and this one is the opposite of disabled.
        Button {
          if action == .recheck { model.recheckPermission(key) } else { model.requestPerm(key) }
        } label: {
          Text(action == .recheck ? "Waiting for macOS… check again" : "Allow \(name)")
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(InkButtonStyle(kind: action == .recheck ? .secondary : .primary))
        Button {
          onContinue()
        } label: {
          Text("Skip for now").inkStyle(InkType.statusLabel, color: Ink.secondary)
        }
        .buttonStyle(.plain)
      }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  @ViewBuilder private var filesWidget: some View {
    switch model.localFileProfileState {
    case .idle:
      permStepWidget("full_disk_access", "Full Disk Access", "cite your files · read-only, stays on this Mac") {
        model.answerFiles()
      }
    case .scanning:
      VStack(alignment: .leading, spacing: 10) {
        Text("Building your local profile").inkStyle(InkType.rowCopy, color: Ink.primary)
        HStack(spacing: 8) {
          ProgressView().controlSize(.small)
          Text("Scanning your projects and recent files…")
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
      .frame(maxWidth: 380, alignment: .leading)
    case .complete(let fileCount, let memoryCount, let deniedFolders):
      VStack(alignment: .leading, spacing: 10) {
        Text("Your local profile is ready").inkStyle(InkType.rowCopy, color: Ink.primary)
        Text("\(fileCount.formatted()) files indexed · \(memoryCount) profile memories saved")
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
        if !deniedFolders.isEmpty {
          Text("Some folders need access later: \(deniedFolders.joined(separator: ", "))")
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
        if model.fdaState != .on {
          // Same contract as `permStepWidget`: waiting turns the button into a
          // re-check rather than disabling it, so a grant that lands after the
          // poll gave up is never unreachable.
          let fdaAction = model.permissionPrimaryAction("full_disk_access")
          Button(
            fdaAction == .recheck
              ? "Waiting for Full Disk Access… check again" : "Allow Full Disk Access"
          ) {
            if fdaAction == .recheck {
              model.recheckPermission("full_disk_access")
            } else {
              model.requestPerm("full_disk_access")
            }
          }
          .buttonStyle(.plain)
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
        }
        SBInkButton(title: "Continue", isDefaultAction: true) { model.finishFilesStep() }
      }
      .frame(maxWidth: 380, alignment: .leading)
    case .failed(let message):
      VStack(alignment: .leading, spacing: 10) {
        Text("I couldn't finish scanning your files").inkStyle(InkType.rowCopy, color: Ink.primary)
        Text(message).inkStyle(InkType.statusLabel, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
        HStack(spacing: 10) {
          SBInkButton(title: "Retry") { model.retryLocalFileScan() }
          Button("Continue without a scan") { model.finishFilesStep() }
            .buttonStyle(.plain)
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
        }
      }
      .frame(maxWidth: 380, alignment: .leading)
    }
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
    // A keycap is a control, so its outline is `Ink.hairline` rather than a card's `separator`, and
    // it inverts when struck — `Ink.primary` fill with an `Ink.surface` glyph, the same inversion the
    // primary button and the granted checkbox use. The 1 pt black drop under it is gone: on glass a
    // tight dark shadow reads as dirt, and the panel already carries the one ambient shadow.
    .foregroundStyle(active ? Ink.surface : Ink.primary)
    .frame(minWidth: 34, minHeight: 34)
    .padding(.horizontal, 7).padding(.vertical, 5)
    .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(active ? Ink.primary : Ink.rowFill))
    .overlay(
      RoundedRectangle(cornerRadius: 8, style: .continuous)
        .strokeBorder(active ? Color.clear : Ink.hairline, lineWidth: 1.5)
    )
    .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.checkbox)), value: active)
    .fixedSize()
  }

  // MARK: summon shortcut

  private var shortcutOptionShape: RoundedRectangle {
    RoundedRectangle(cornerRadius: PageGlass.rowRadius, style: .continuous)
  }

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
            Text(opt.sub).inkStyle(InkType.statusLabel, color: Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
            Spacer()
            if model.shortcutRecording {
              Text("Press a key").inkStyle(InkType.statusLabel, color: Ink.secondary)
            } else if model.chosenShortcut == opt.shortcut {
              Text("✓").inkStyle(InkType.statusLabel, color: Ink.primary)
            }
          }
          .padding(.horizontal, 14).padding(.vertical, 11)
          .frame(maxWidth: .infinity, alignment: .leading)
          // A pressable option, so it keeps an outline at rest (`Ink.hairline`, a control's edge)
          // rather than the list-row treatment, where rest is genuinely nothing. The selection is
          // carried by the fill — a row of outlined boxes with one heavier outline is not a choice
          // anyone can see at a glance.
          .background(shortcutOptionShape.fill(model.chosenShortcut == opt.shortcut ? Ink.rowFillHover : .clear))
          .overlay(shortcutOptionShape.strokeBorder(Ink.hairline, lineWidth: 1))
          .contentShape(shortcutOptionShape)
        }
        .buttonStyle(.plain)
      }
      if model.shortcutRecording {
        Text("Press the shortcut you want to use.")
          .inkStyle(InkType.rowCopy, color: Ink.primary)
          .fixedSize(horizontal: false, vertical: true)
          .padding(.top, 6)
      } else if model.shortcutPicked {
        VStack(alignment: .leading, spacing: 10) {
          HStack(spacing: 6) {
            ForEach(model.shortcutTokens, id: \.self) { tok in keycap(tok, active: model.shortcutPressed) }
          }
          // Confirmation is the one line here that gets the ink: "that works" is the answer the user
          // pressed the key to find out, and it has to outrank the instruction it replaces.
          Text(
            model.shortcutPressed
              ? "Perfect, that works."
              : "Now press it to test."
          )
          .inkStyle(InkType.rowCopy, color: model.shortcutPressed ? Ink.primary : Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.top, 6)
      }
      // Continue only appears once the key has actually been pressed; before that,
      // just a quiet Skip so the user is never stuck.
      Group {
        if model.shortcutPressed {
          SBInkButton(title: "Continue", isDefaultAction: true) {
            isTalk ? model.answerShortcutTalk() : model.answerShortcutOpen()
          }
        } else {
          Button {
            isTalk ? model.answerShortcutTalk() : model.answerShortcutOpen()
          } label: {
            Text("Skip for now").inkStyle(InkType.statusLabel, color: Ink.secondary)
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
      if model.screenDemoPTTReady {
        VStack(alignment: .leading, spacing: 6) {
          HStack(spacing: 5) {
            Text("Hold").inkStyle(InkType.rowCopy, color: Ink.primary)
            ForEach(model.voiceChordTokens, id: \.self) { tok in keycap(tok) }
            Text("and ask me about it, out loud.").inkStyle(InkType.rowCopy, color: Ink.primary)
          }
          Text(
            "Ask me what’s on your screen in \(model.selectedResponseLanguageName). I can see it, and I answer at the top of your screen."
          )
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
        }
      } else if model.screenDemoPTTUnavailable {
        VStack(alignment: .leading, spacing: 8) {
          Text("Voice setup isn't available yet. You can retry, or skip for now.")
            .inkStyle(InkType.rowCopy, color: Ink.primary)
            .fixedSize(horizontal: false, vertical: true)
          Button("Try again") {
            model.startScreenDemo()
          }
          .buttonStyle(InkButtonStyle(kind: .secondary))
        }
      } else {
        HStack(spacing: 8) {
          ProgressView().controlSize(.small)
          Text("Preparing voice…").inkStyle(InkType.rowCopy, color: Ink.secondary)
        }
      }
      // Continue appears once Omi has actually answered — before that, an always-
      // tappable, clearly-visible "Skip for now" so the user is never stuck if the
      // demo doesn't fire (it used to be a tiny, easily-missed text link).
      Group {
        if model.screenDemoDone {
          SBInkButton(title: "Continue", isDefaultAction: true) { model.answerScreenDemo() }
        } else {
          Button {
            model.answerScreenDemo()
          } label: {
            Text("Skip for now").frame(maxWidth: .infinity)
          }
          .buttonStyle(InkButtonStyle(kind: .secondary))
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
        Button {
          showAIAssistants.toggle()
        } label: {
          HStack {
            Text("AI assistants").inkStyle(InkType.rowCopy, color: Ink.primary)
            Spacer()
            Image(systemName: showAIAssistants ? "chevron.up" : "chevron.down")
              .font(.system(size: 11, weight: .semibold))
              .foregroundStyle(Ink.secondary)
          }
        }
        .buttonStyle(.plain)
        .padding(.vertical, 12)
        if showAIAssistants {
          GlassSeparator()
          ForEach(Array(model.agentRows.enumerated()), id: \.element.id) { i, row in
            connectRow(id: row.id, row.name, row.detail, state: model.agentStates[row.id] ?? "idle") {
              model.connectAgent(row.id)
            }
            if i < model.agentRows.count - 1 { GlassSeparator() }
          }
        }
      }
      .padding(.horizontal, 14)
      .glassCard(cornerRadius: PageGlass.rowRadius)
      SBInkButton(title: "Continue", isDefaultAction: true) { model.answerAgents() }
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
          if i < model.contextRows.count - 1 { GlassSeparator() }
        }
      }
      .padding(.horizontal, 14)
      .glassCard(cornerRadius: PageGlass.rowRadius)
      SBInkButton(title: "Continue", isDefaultAction: true) { model.answerContext() }
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
          Text(name).inkStyle(InkType.rowCopy, color: Ink.primary)
          Text(detail).inkStyle(InkType.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
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
    // Every readout here is `secondary` — glass carries two rungs, so "checking…" and "not installed"
    // cannot sit a step below "✓ on"; they all read as subordinate to the connector's name, which is
    // `primary`. The actions are stadium capsules from the one button style, not 7 pt rounded rects.
    switch state {
    case "on": Text("✓ on").inkStyle(InkType.statusLabel, color: Ink.secondary).fixedSize()
    case "connecting": Text("…").inkStyle(InkType.statusLabel, color: Ink.secondary).fixedSize()
    case "checking": Text("checking…").inkStyle(InkType.statusLabel, color: Ink.secondary).fixedSize()
    case "unavailable": Text("not installed").inkStyle(InkType.statusLabel, color: Ink.secondary).fixedSize()
    case "error":
      Button("Retry", action: action)
        .buttonStyle(InkButtonStyle(kind: .primary))
    default:
      Button(state == "needsSignIn" ? "Retry" : "Connect", action: action)
        .buttonStyle(InkButtonStyle(kind: .primary))
    }
  }

  // MARK: capture

  private var captureWidget: some View {
    VStack(spacing: 8) {
      Button {
        model.capture(SBOnboardingModel.defaultCaptureSelection)
      } label: {
        HStack(spacing: 4) {
          Text("● Only during meetings")
          // The qualifier is on the filled capsule, so it steps down in *alpha* on the label colour
          // rather than moving to another rung — the ladder is for type on the panel, and there is no
          // second ink inside a primary button.
          Text("· from my calendar").opacity(0.75)
        }
        .frame(maxWidth: .infinity)
      }
      .buttonStyle(InkButtonStyle(kind: .primary))
      .keyboardShortcut(.defaultAction)
      Button {
        model.capture(.continuous)
      } label: {
        Text("Start listening — continuously").frame(maxWidth: .infinity)
      }
      .buttonStyle(InkButtonStyle(kind: .secondary))
    }
    .frame(maxWidth: 340, alignment: .leading)
  }
}

/// Wrapping chip row where each chip hugs its content (no wide grid cells that
/// push short chips far apart).
private struct FlowChips: View {
  let items: [String]
  var selectedItem: String? = nil
  let onPick: (String) -> Void
  var body: some View {
    ChipFlowLayout(spacing: 8, lineSpacing: 8) {
      ForEach(items, id: \.self) { item in
        let isSelected = selectedItem == item
        Button {
          onPick(item)
        } label: {
          // Selected inverts the ladder the same way the primary button does — `Ink.primary` fill,
          // `Ink.surface` label — so a chosen chip and a chosen anything else are the same object.
          Text(item).inkStyle(InkType.rowCopy, color: isSelected ? Ink.surface : Ink.primary)
            .padding(.horizontal, 15).padding(.vertical, 8)
            .background(Capsule(style: .continuous).fill(isSelected ? Ink.primary : .clear))
            .overlay(Capsule(style: .continuous).strokeBorder(isSelected ? .clear : Ink.hairline, lineWidth: 1))
            .contentShape(Capsule(style: .continuous))
        }
        .buttonStyle(.plain)
        .animation(InkReduceMotion.animation(.easeOut(duration: InkMotion.press)), value: isSelected)
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
