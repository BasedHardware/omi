import AppKit
import OmiTheme
import SwiftUI

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
/// **It paints exactly one ground, and that ground is the app's glass.** A full-bleed dune photograph
/// under a black gradient used to sit behind this card, and every label on the very first screen a
/// new user reaches had to be white to survive it. The art is gone and the type is near-black:
/// blurred desktop, one card, two rungs of ink.
///
/// The card itself was `Color.white.opacity(0.05)` over `.ultraThinMaterial`. That is *within-window*
/// vibrancy — it frosts the app's own content rather than the desktop — so it was never the same
/// material as the panel around it. It became a bare wash-and-hairline `glassCard`, which was right
/// while `ShellGlassGround` made the whole window one slab of glass and a second scrim would have
/// spent the passthrough budget twice. `ShellWindowChrome` retired that slab and handed every other
/// destination its own panel (`PageGlassLane`); this card was missed, so a wash over nothing left the
/// user's wallpaper as the ground and the copy unreadable over a bright photograph. It is
/// `onboardingCard()`, which is `inkGlassPanel` — the one shared piece of glass, once.
struct SBOnboardingView: View {
  @StateObject private var model: SBOnboardingModel

  init(
    appState: AppState,
    chatProvider: ChatProvider,
    onComplete: (() -> Void)?
  ) {
    _model = StateObject(
      wrappedValue: SBOnboardingModel(
        appState: appState,
        chatProvider: chatProvider,
        onComplete: onComplete
      ))
  }

  var body: some View {
    GeometryReader { geometry in
      let panelSize = SBOnboardingPanelLayout.size(in: geometry.size)
      panel(in: panelSize)
        .frame(width: panelSize.width, height: panelSize.height)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    // Pins the panel's light appearance so `Ink`'s dynamic colours resolve dark here even on a
    // machine in Dark Mode. Without it this card is near-white type on a near-white ground.
    .glassContent()
    .onAppear { model.begin() }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      // Granting a permission means leaving Omi for System Settings and coming
      // back, so this return is the signal a grant may have landed — not a 20s
      // poll that Full Disk Access and Accessibility routinely outlive.
      model.recheckActivePermission()
    }
    // Safety net: the `.shortcut` step suspends global hotkeys and nulls the main
    // menu (restored only via the advance/skip/complete buttons). If the view is
    // removed by any other path (e.g. auth flips to signed-out), restore them here
    // so hotkeys/menu aren't left disabled until relaunch. Idempotent when unarmed.
    .onDisappear { model.disarmShortcutSummon() }
  }

  private func panel(in panelSize: CGSize) -> some View {
    VStack(spacing: 0) {
      // Navigation belongs to the onboarding card, not the window's corner. The window can be wider
      // than the card (and may be repositioned independently), so an outer overlay makes Back look
      // detached from the conversation it controls.
      HStack {
        Spacer(minLength: 0)
        ViewThatFits(in: .horizontal) {
          HStack(spacing: 8) {
            backButton
            if model.canSkipOnboarding { skipButton }
          }
          VStack(alignment: .trailing, spacing: 8) {
            backButton
            if model.canSkipOnboarding { skipButton }
          }
        }
      }
      .frame(minHeight: 44)
      .padding(.horizontal, 16)
      .padding(.top, 8)
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
              currentStepContainer(in: panelSize)
                .id("widget")
            }
            // Keep the last control above the progress band while ScrollViewReader settles after a
            // growing widget or a streamed message. A tiny sentinel spacer can leave an input or
            // permission action visually underneath the dots even though the band is a VStack
            // sibling, so reserve a full band's height plus a small breathing room here as well.
            Color.clear.frame(height: OnboardingGlass.scrollContentBottomPadding).id("bottom")
          }
          .padding(.horizontal, 28).padding(.top, 26)
        }
        // **The thread sits on the floor of the card, not its ceiling.** The panel is a fixed
        // 540 × 640 so it never jumps as the conversation grows, which means the first three steps
        // — the first screens a new user ever sees — otherwise draw one short paragraph at the top
        // of a card with ~380 pt of visibly empty card under it. Emptiness a border draws a box
        // around is not whitespace, it is an unfinished panel. Anchored to the bottom, a short
        // thread reads the way every chat does before you scroll, and the action the step is asking
        // for lands near the thumb instead of stranded mid-card.
        .defaultScrollAnchor(.bottom)
        .onChange(of: model.thread.count) { _, _ in scrollDown(proxy) }
        .onChange(of: model.showWidget) { _, _ in scrollDown(proxy) }
        .onChange(of: model.streamingText) { _, _ in scrollDown(proxy) }
        .onChange(of: model.shortcutPicked) { _, _ in scrollDown(proxy) }
        .onChange(of: model.shortcutPressed) { _, _ in scrollDown(proxy) }
        // Tapping "Custom shortcut" enters recording mode, which expands the widget with
        // instructions/refusal text below the preset rows. Without this scroll trigger the new
        // content is clipped below the fold.
        .onChange(of: model.shortcutRecording) { _, _ in scrollDown(proxy) }
        // The same rule for every widget that grows without touching the thread — a finished file
        // scan, a permission row turning into the relaunch offer, the demo arming its chord. See
        // `SBOnboardingModel.widgetShape`: without it the Files step's Continue renders below the
        // card's lower edge and the step reads as having no way forward.
        .onChange(of: model.widgetShape) { _, _ in scrollDown(proxy) }
      }
      // The band is a sibling of the scroll view, not an overlay on its content. It always claims the
      // same height, including while a step is streaming, so the current-step column never jumps when
      // one widget is replaced by the next.
      OnboardingProgressBand(
        total: SBOnboardingModel.Step.allCases.count,
        current: model.step.rawValue
      )
    }
    // One shadow, and it is `InkGlassShadow.ambient` — the same broad, diffuse one every floating
    // panel in this app casts, drawn by `onboardingCard`. Not the 60 pt black drop this used to carry
    // inside itself, which read as depth on the dark art and as dirt on glass.
    .onboardingCard()
  }

  /// The one current-step container. `model.step` is the live onboarding identity; giving the widget
  /// that identity lets SwiftUI run the shared height-relative transition when the model advances or
  /// goes back, while the fixed panel size keeps the visual drift proportional across window sizes.
  @ViewBuilder
  private func currentStepContainer(in panelSize: CGSize) -> some View {
    widget
      .padding(.leading, 26).padding(.top, 2)
      .id(model.step)
      .transition(.onboardingStep(in: panelSize))
      .animation(OnboardingGlass.stepAnimation, value: model.step)
      .animation(OnboardingGlass.stepAnimation, value: model.showWidget)
  }

  /// Back and Skip sit in the card header, next to the conversation they control. `glassChip()` is a
  /// wash — the treatment for a chip that already sits on a ground — and the card is already the
  /// ground here. `.glassFloatingBar` keeps the compact control legible without making it look like a
  /// second panel.
  private static let chipRadius: CGFloat = 999

  @ViewBuilder private var backButton: some View {
    if model.canGoBack {
      Button(action: { model.goBack() }) {
        Text("← Back")
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
          .padding(.horizontal, 14).padding(.vertical, 7)
          .glassFloatingBar(cornerRadius: Self.chipRadius)
      }
      .buttonStyle(.plain)
      .help("Go back and change an earlier answer")
    }
  }

  private var skipButton: some View {
    Button(action: { model.skip() }) {
      Text("Skip")
        .inkStyle(InkType.statusLabel, color: Ink.secondary)
        .padding(.horizontal, 14).padding(.vertical, 7)
        .glassFloatingBar(cornerRadius: Self.chipRadius)
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
    case .hello: nameWidget
    case .see:
      switch model.seePhase {
      case .permission:
        permStepWidget("screen_recording", "Screen Recording", "so I can see what you're looking at") {
          model.answerScreen()
        }
      case .openPage, .waitingForPage:
        openOrderPageWidget
      }
    case .card:
      cardWidget
    case .talk:
      switch model.talkPhase {
      case .microphone:
        permStepWidget("microphone", "Microphone", "so I can hear your push-to-talk question") {
          model.answerMic()
        }
      case .shortcut:
        shortcutWidget(isTalk: true)
      case .demo:
        screenDemoWidget
      }
    case .write: writeScenarioWidget
    case .ready: captureWidget
    }
  }

  /// The hand-off out of Omi is a button, never a side effect of the sentence above it. The page
  /// opens on this click, and the thread has already said what to do there and that Omi will bring
  /// the user back; `waitingForPage` is the few seconds between the click and the card beat.
  @ViewBuilder private var openOrderPageWidget: some View {
    VStack(alignment: .leading, spacing: 10) {
      handoffRow(
        symbol: "safari",
        title: "A demo order page, in your browser.",
        detail: "Norrland Goods, one desk lamp. Opens in your default browser; nothing on it is real."
      )
      if model.seePhase == .openPage {
        SBInkButton(title: "Open the order page", isDefaultAction: true) { model.openOrderPage() }
      } else {
        HStack(spacing: 8) {
          ProgressView().controlSize(.small)
          Text("Opening… look up once it's there.").inkStyle(InkType.statusLabel, color: Ink.secondary)
        }
        Button {
          model.openOrderPage()
        } label: {
          Text("Open it again").frame(maxWidth: .infinity)
        }
        .buttonStyle(InkButtonStyle(kind: .secondary))
      }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  /// One row that says where the user is about to go and what to do there. Same glass row as the
  /// receipts, because a hand-off and a receipt are the two ends of the same trip.
  private func handoffRow(symbol: String, title: String, detail: String) -> some View {
    HStack(alignment: .top, spacing: 12) {
      Image(systemName: symbol)
        .inkStyle(InkType.rowCopy, color: Ink.primary)
        .frame(width: 18)
      VStack(alignment: .leading, spacing: 3) {
        Text(title)
          .inkStyle(InkType.rowCopy, color: Ink.primary)
          .fixedSize(horizontal: false, vertical: true)
        Text(detail)
          .inkStyle(InkType.statusLabel, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      Spacer(minLength: 0)
    }
    .padding(.horizontal, 14).padding(.vertical, 12)
    .glassCard(cornerRadius: PageGlass.rowRadius)
  }

  /// The card beat's widget points at the real surface instead of reproducing it: the whole beat is
  /// about learning where cards live. Once "Remind me" lands, the task it created stays here through
  /// the notifications ask as the first thing Omi has written on the user's behalf.
  @ViewBuilder private var cardWidget: some View {
    VStack(alignment: .leading, spacing: 10) {
      ForEach(model.scenarioTaskChips, id: \.self) { task in
        scenarioWriteRow(symbol: "checkmark.circle", label: "TASK", text: task)
      }
      if model.cardPhase == .notifications {
        permStepWidget("notifications", "Notifications", "reach you away from the notch") {
          model.answerNotifications()
        }
      } else {
        handoffRow(
          symbol: "arrow.up",
          title: "Look up. The card is at the top of your screen.",
          detail: "It offers a reminder. Pick either answer; I'll bring you back here."
        )
        HStack(spacing: 8) {
          ProgressView().controlSize(.small)
          Text("Waiting for you to answer the card…").inkStyle(InkType.statusLabel, color: Ink.secondary)
        }
      }
    }
    .frame(maxWidth: 380, alignment: .leading)
  }

  /// One thing Omi wrote from the user's own words. Same glass row as the trust rows on the first
  /// screen, so "what Omi saved" reads like a receipt, not a notification.
  private func scenarioWriteRow(symbol: String, label: String, text: String) -> some View {
    HStack(alignment: .top, spacing: 12) {
      Image(systemName: symbol)
        .inkStyle(InkType.rowCopy, color: Ink.secondary)
        .frame(width: 18)
      VStack(alignment: .leading, spacing: 2) {
        Text(label).inkFont(InkType.statusLabel).foregroundStyle(Ink.secondary)
        Text(text).inkStyle(InkType.rowCopy, color: Ink.primary)
          .fixedSize(horizontal: false, vertical: true)
      }
      Spacer(minLength: 0)
    }
    .padding(.horizontal, 14).padding(.vertical, 10)
    .glassCard(cornerRadius: PageGlass.rowRadius)
  }

  /// The write beat: the note is offered, opened on a click, and then this side only has to say
  /// where to look, wait for Send, and show what Omi kept. The escapes are on screen the whole time
  /// the user is away, not only after a timeout; "Fix something" is honest about being a correction
  /// path rather than a magic button.
  @ViewBuilder private var writeScenarioWidget: some View {
    VStack(alignment: .leading, spacing: 10) {
      switch model.writePhase {
      case .intro:
        handoffRow(
          symbol: "envelope",
          title: "A note to Sam, already drafted.",
          detail: "Edit it however you like, then press Send. Demo mailbox; nothing leaves your Mac."
        )
        SBInkButton(title: "Open the note", isDefaultAction: true) { model.openComposePage() }
        Button {
          model.skipWriteBeat()
        } label: {
          Text("Skip for now").frame(maxWidth: .infinity)
        }
        .buttonStyle(InkButtonStyle(kind: .secondary))
      case .waitingForSend:
        handoffRow(
          symbol: "envelope",
          title: "The note is open in your browser.",
          detail: "Press Send when it reads right. I'll bring you back here."
        )
        if model.scenarioWriteDetectionTimedOut {
          Text("I haven't seen the note go out yet. Open it again, or skip this one.")
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        } else {
          HStack(spacing: 8) {
            ProgressView().controlSize(.small)
            Text("Waiting for Send…").inkStyle(InkType.statusLabel, color: Ink.secondary)
          }
        }
        HStack(spacing: 8) {
          Button {
            model.retryWriteDetection()
          } label: {
            Text("Open it again").frame(maxWidth: .infinity)
          }
          .buttonStyle(InkButtonStyle(kind: .secondary))
          Button {
            model.skipWriteBeat()
          } label: {
            Text("Skip for now").frame(maxWidth: .infinity)
          }
          .buttonStyle(InkButtonStyle(kind: .secondary))
        }
      case .review:
        ForEach(model.scenarioMemoryChips, id: \.self) { memory in
          scenarioWriteRow(symbol: "sparkles", label: "MEMORY", text: memory)
        }
        ForEach(model.scenarioTaskChips, id: \.self) { task in
          scenarioWriteRow(symbol: "checkmark.circle", label: "TASK", text: task)
        }
        if model.scenarioWritesPending {
          HStack(spacing: 8) {
            ProgressView().controlSize(.small)
            Text("Saving…").inkStyle(InkType.statusLabel, color: Ink.secondary)
          }
        } else {
          if model.scenarioMemoryChips.isEmpty && model.scenarioTaskChips.isEmpty {
            Text("Nothing to keep from that note. That happens; I only save what you actually said.")
              .inkStyle(InkType.statusLabel, color: Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          HStack(spacing: 8) {
            SBInkButton(title: "Looks right", isDefaultAction: true) { model.confirmScenarioWrites() }
            Button("Fix something") { model.requestScenarioWriteFix() }
              .buttonStyle(InkButtonStyle(kind: .secondary))
          }
          .padding(.top, 4)
        }
      }
    }
    .frame(maxWidth: 380, alignment: .leading)
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
        // The escape is a *control*, not a caption. As a bare `.plain` run of `statusLabel` this was
        // an 11 pt grey line sitting 10 pt under a full-width filled pill — the shape of a footnote,
        // on the one screen where the user most needs to know they are not trapped. `screenDemoWidget`
        // already learned this ("it used to be a tiny, easily-missed text link") and shipped the
        // secondary capsule; every skip in this flow is that same object now.
        Button {
          onContinue()
        } label: {
          Text("Skip for now").frame(maxWidth: .infinity)
        }
        .buttonStyle(InkButtonStyle(kind: .secondary))
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
            if model.chosenShortcut == opt.shortcut {
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
      Button {
        model.beginShortcutRecording(isTalk: isTalk)
      } label: {
        HStack(spacing: 8) {
          Image(systemName: "keyboard")
            .font(.system(size: 13, weight: .medium))
          Text("Custom shortcut").inkStyle(InkType.rowCopy, color: Ink.primary)
          Spacer()
          Text(model.shortcutRecording ? "Press it now" : "Set your own")
            .inkStyle(InkType.statusLabel, color: Ink.secondary)
        }
        .padding(.horizontal, 14).padding(.vertical, 11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(shortcutOptionShape.fill(model.shortcutRecording ? Ink.rowFillHover : .clear))
        .overlay(shortcutOptionShape.strokeBorder(Ink.hairline, lineWidth: 1))
        .contentShape(shortcutOptionShape)
      }
      .buttonStyle(.plain)
      if model.shortcutRecording {
        // A bare key is refused (`acceptsRecordedChord`) because a global bare `L` would make every
        // `L` typed anywhere open Omi. The refusal used to be silent, so the step looked broken to
        // anyone who pressed one; this is the refusal said out loud, in place of the instruction it
        // has just answered.
        Text(
          model.shortcutNeedsModifier
            ? "That one's on its own — add ⌘, ⌃ or ⌥ to it."
            : "Press the shortcut you want to use."
        )
        .inkStyle(InkType.rowCopy, color: Ink.primary)
        .fixedSize(horizontal: false, vertical: true)
        .padding(.top, 6)
      } else if let error = model.shortcutRegistrationError {
        Text(error)
          .inkStyle(InkType.rowCopy, color: Ink.errorRed)
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
      // Shortcut setup is required: Continue appears only after the selected shortcut has been
      // pressed, and there is deliberately no skip action on either shortcut stage.
      Group {
        if model.shortcutPicked, model.shortcutPressed {
          SBInkButton(title: "Continue", isDefaultAction: true) {
            isTalk ? model.answerShortcutTalk() : model.answerShortcutOpen()
          }
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
        VStack(alignment: .leading, spacing: 8) {
          HStack(spacing: 5) {
            Text("Hold").inkStyle(InkType.rowCopy, color: Ink.primary)
            ForEach(model.voiceChordTokens, id: \.self) { tok in keycap(tok) }
            Text("and ask about the order, out loud.").inkStyle(InkType.rowCopy, color: Ink.primary)
          }
          Text(
            "Try “When does this arrive?” I still have the order page in mind, and I answer at the top of your screen, in \(model.selectedResponseLanguageName)."
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

  // MARK: capture

  private var captureWidget: some View {
    VStack(spacing: 8) {
      Button {
        model.capture(SBOnboardingModel.defaultCaptureSelection)
      } label: {
        Text("Only Meetings").frame(maxWidth: .infinity)
      }
      .buttonStyle(InkButtonStyle(kind: .primary))
      .keyboardShortcut(.defaultAction)
      Button {
        model.capture(.always)
      } label: {
        Text("Always On").frame(maxWidth: .infinity)
      }
      .buttonStyle(InkButtonStyle(kind: .secondary))
    }
    .frame(maxWidth: 340, alignment: .leading)
  }
}
