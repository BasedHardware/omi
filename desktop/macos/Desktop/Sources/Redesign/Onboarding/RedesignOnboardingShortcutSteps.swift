import AppKit
import SwiftUI

// MARK: - Shared light key cap

private struct RedesignKeyCap: View {
  let label: String
  var lit: Bool = false
  var big: Bool = true

  var body: some View {
    RoundedRectangle(cornerRadius: big ? 10 : 8, style: .continuous)
      .fill(lit ? Ink.accent : Ink.surface)
      .frame(minWidth: big ? 48 : 36, minHeight: big ? 48 : 32)
      .overlay(
        RoundedRectangle(cornerRadius: big ? 10 : 8, style: .continuous)
          .strokeBorder(lit ? Ink.accent : Ink.hair2, lineWidth: big ? 2 : 1)
      )
      .overlay(
        Text(label)
          .font(InkFont.sans(big ? 18 : 13, .semibold))
          .foregroundColor(lit ? Ink.accentInk : Ink.ink)
          .padding(.horizontal, label.count > 2 ? (big ? 14 : 10) : (big ? 10 : 8))
      )
      .fixedSize()
  }
}

private struct RedesignShortcutHeader: View {
  let beat: Int
  var onSkip: () -> Void
  var onForceComplete: (() -> Void)?
  var body: some View {
    RedesignOnboardingChrome(
      beat: beat, showsSkip: true, onSkip: onSkip, onForceComplete: onForceComplete)
  }
}

// MARK: - Step 10 · Floating bar shortcut

struct RedesignFloatingBarShortcutStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  let stepIndex: Int
  var onComplete: () -> Void
  var onSkip: () -> Void
  var onForceComplete: (() -> Void)?

  @ObservedObject private var shortcutSettings = ShortcutSettings.shared

  @State private var shortcutDetected = false
  @State private var showContinue = false
  @State private var isRecordingCustomShortcut = false
  @State private var captureError: String?
  @State private var localKeyMonitor: Any?
  @State private var globalKeyMonitor: Any?

  static var savedMenu: NSMenu?

  var body: some View {
    VStack(spacing: 0) {
      RedesignShortcutHeader(
        beat: RedesignOnboarding.beat(forStep: stepIndex), onSkip: onSkip,
        onForceComplete: onForceComplete)

      Spacer()

      VStack(spacing: 22) {
        Text("Ask me anything, instantly.")
          .inkDisplay(30).multilineTextAlignment(.center)
        Text("Press this shortcut. Do the keys light up?")
          .inkBody().multilineTextAlignment(.center)

        RoundedRectangle(cornerRadius: 16, style: .continuous)
          .fill(Ink.surface)
          .overlay(RoundedRectangle(cornerRadius: 16).strokeBorder(Ink.hair, lineWidth: 1))
          .frame(height: 128).frame(maxWidth: 420)
          .overlay {
            VStack(spacing: 12) {
              HStack(spacing: 8) {
                ForEach(Array(shortcutSettings.askOmiShortcut.displayTokens.enumerated()), id: \.offset) { _, symbol in
                  RedesignKeyCap(label: symbol, lit: shortcutDetected)
                }
              }
              Text(shortcutDetected ? "Shortcut detected" : "Press to test")
                .font(InkFont.sans(13, .medium)).foregroundColor(Ink.faint)
            }
          }

        VStack(spacing: 12) {
          Text("Choose a different shortcut:").font(InkFont.sans(14, .medium)).foregroundColor(Ink.muted)
          HStack(spacing: 10) {
            ForEach(ShortcutSettings.askOmiPresets, id: \.self) { shortcut in
              shortcutChoiceButton(shortcut)
            }
            customShortcutButton
          }
          if isRecordingCustomShortcut || shortcutSettings.askOmiUsesCustomShortcut || captureError != nil {
            customShortcutRecorder
          }
        }

        if showContinue {
          InkButton(title: "Continue", kind: .primary, size: .lg, action: onComplete)
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
      }

      Spacer()
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .onAppear {
      GlobalShortcutManager.shared.setRegistrationSuspended(true)
      installKeyMonitor()
    }
    .onDisappear {
      removeKeyMonitors()
      GlobalShortcutManager.shared.setRegistrationSuspended(false)
    }
  }

  private var customShortcutButton: some View {
    let isSelected = shortcutSettings.askOmiUsesCustomShortcut || isRecordingCustomShortcut
    return Button(action: beginCustomShortcutCapture) {
      Text("Custom").font(InkFont.sans(13, .medium))
        .foregroundColor(isSelected ? Ink.accentStrong : Ink.body)
        .padding(.horizontal, 14).frame(height: 36)
        .background(chipBackground(isSelected))
    }
    .buttonStyle(.plain)
  }

  private var customShortcutRecorder: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text(isRecordingCustomShortcut ? "Press your custom shortcut now" : "Custom shortcut")
        .font(InkFont.sans(13, .semibold)).foregroundColor(Ink.ink)
      HStack(spacing: 10) {
        HStack(spacing: 6) {
          ForEach(Array(shortcutSettings.askOmiShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
            RedesignKeyCap(label: token, lit: true, big: false)
          }
        }
        Spacer()
        InkButton(title: isRecordingCustomShortcut ? "Listening…" : "Save", kind: .plain, size: .sm) {
          handleCustomShortcutSaveButton()
        }
        .disabled(isRecordingCustomShortcut)
      }
      Text("Use at least one non-modifier key, like J or Return.")
        .font(InkFont.sans(12)).foregroundColor(Ink.faint)
      if let captureError {
        RedesignOnboardingError(message: captureError)
      }
    }
    .padding(14).frame(maxWidth: 420)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.surface2).overlay(
          RoundedRectangle(cornerRadius: 14).strokeBorder(Ink.hair, lineWidth: 1)))
  }

  private func shortcutChoiceButton(_ shortcut: ShortcutSettings.KeyboardShortcut) -> some View {
    let isSelected = shortcutSettings.askOmiShortcut == shortcut && !shortcutSettings.askOmiUsesCustomShortcut
    return Button {
      shortcutSettings.askOmiShortcut = shortcut
      isRecordingCustomShortcut = false
      captureError = nil
      resetDetectionState()
    } label: {
      HStack(spacing: 4) {
        ForEach(Array(shortcut.displayTokens.enumerated()), id: \.offset) { _, symbol in
          Text(symbol).font(InkFont.sans(13, .medium))
        }
      }
      .foregroundColor(isSelected ? Ink.accentStrong : Ink.body)
      .padding(.horizontal, 14).frame(height: 36)
      .background(chipBackground(isSelected))
    }
    .buttonStyle(.plain)
  }

  private func chipBackground(_ selected: Bool) -> some View {
    RoundedRectangle(cornerRadius: 12, style: .continuous)
      .fill(selected ? Ink.accentTint : Ink.surface)
      .overlay(
        RoundedRectangle(cornerRadius: 12).strokeBorder(selected ? Ink.accent : Ink.hair2, lineWidth: 1))
  }

  private func beginCustomShortcutCapture() {
    isRecordingCustomShortcut = true
    captureError = nil
    resetDetectionState()
  }
  private func handleCustomShortcutSaveButton() {
    guard shortcutSettings.askOmiUsesCustomShortcut else {
      beginCustomShortcutCapture()
      return
    }
    confirmShortcutAndContinue()
  }
  private func resetDetectionState() {
    shortcutDetected = false
    showContinue = false
  }
  private func confirmShortcutAndContinue() {
    captureError = nil
    shortcutDetected = true
    withAnimation(.easeInOut(duration: 0.3)) { showContinue = true }
  }

  private func installKeyMonitor() {
    let mask: NSEvent.EventTypeMask = [.keyDown, .flagsChanged]
    localKeyMonitor = NSEvent.addLocalMonitorForEvents(matching: mask) { event in
      handleShortcutEvent(event) ? nil : event
    }
    globalKeyMonitor = NSEvent.addGlobalMonitorForEvents(matching: mask) { event in
      _ = handleShortcutEvent(event)
    }
    if Self.savedMenu == nil { Self.savedMenu = NSApp.mainMenu }
    NSApp.mainMenu = nil
  }
  private func removeKeyMonitors() {
    if let monitor = localKeyMonitor { NSEvent.removeMonitor(monitor); localKeyMonitor = nil }
    if let monitor = globalKeyMonitor { NSEvent.removeMonitor(monitor); globalKeyMonitor = nil }
    if let menu = Self.savedMenu { NSApp.mainMenu = menu; Self.savedMenu = nil }
  }
  private func handleShortcutEvent(_ event: NSEvent) -> Bool {
    if isRecordingCustomShortcut { return captureCustomShortcut(from: event) }
    guard !shortcutDetected else { return false }
    guard shortcutSettings.askOmiShortcut.matchesKeyDown(event) else { return false }
    DispatchQueue.main.async { confirmShortcutAndContinue() }
    return true
  }
  private func captureCustomShortcut(from event: NSEvent) -> Bool {
    if event.type == .flagsChanged {
      captureError = "Ask omi needs a non-modifier key."
      return true
    }
    guard let shortcut = ShortcutSettings.KeyboardShortcut.fromRecordingEvent(event, allowModifierOnly: false)
    else { return false }
    shortcutSettings.askOmiShortcut = shortcut
    isRecordingCustomShortcut = false
    captureError = nil
    return true
  }
}

// MARK: - Step 11 · Floating bar demo

struct RedesignFloatingBarDemoView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  let stepIndex: Int
  var onComplete: () -> Void
  var onSkip: () -> Void
  var onForceComplete: (() -> Void)?

  @ObservedObject private var shortcutSettings = ShortcutSettings.shared
  @State private var barActivated = false
  @State private var showContinue = false

  var body: some View {
    VStack(spacing: 0) {
      RedesignShortcutHeader(
        beat: RedesignOnboarding.beat(forStep: stepIndex), onSkip: onSkip,
        onForceComplete: onForceComplete)

      Spacer()

      VStack(spacing: 26) {
        VStack(spacing: 12) {
          if !barActivated {
            Text("I see your screen — so my answers fit your moment.")
              .inkDisplay(28).multilineTextAlignment(.center).frame(maxWidth: 560)
            Text("Press this shortcut to open Ask omi.").inkBody().multilineTextAlignment(.center)
          } else {
            Text("Type in the bar: \"Which computer should I buy?\"")
              .inkDisplay(26).multilineTextAlignment(.center).frame(maxWidth: 560)
          }
        }

        if !barActivated {
          VStack(spacing: 12) {
            HStack(spacing: 6) {
              ForEach(Array(shortcutSettings.askOmiShortcut.displayTokens.enumerated()), id: \.offset) { index, symbol in
                if index > 0 {
                  Text("+").font(InkFont.sans(15, .medium)).foregroundColor(Ink.faint)
                }
                RedesignKeyCap(label: symbol, big: false)
              }
            }
            Text("Ask omi opens at the top of your screen.")
              .font(InkFont.sans(13)).foregroundColor(Ink.faint)
          }
          .transition(.opacity)
        } else {
          RedesignMacLineupPreview()
            .frame(maxWidth: 900)
            .transition(.opacity.combined(with: .move(edge: .bottom)))
        }
      }
      .padding(.horizontal, 40)

      Spacer()

      if showContinue {
        InkButton(title: "Continue", kind: .primary, size: .lg, action: onComplete)
          .padding(.bottom, 32)
          .transition(.move(edge: .bottom).combined(with: .opacity))
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .onAppear {
      FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
      GlobalShortcutManager.shared.registerShortcuts()
    }
    .onDisappear {
      if FloatingControlBarManager.shared.barState?.showingAIConversation == true {
        FloatingControlBarManager.shared.toggleAIInput()
      }
    }
    .onChange(of: barActivated) { _, activated in
      if activated { Task { await waitForResponse() } }
    }
    .onReceive(Timer.publish(every: 0.25, on: .main, in: .common).autoconnect()) { _ in
      guard !barActivated,
        FloatingControlBarManager.shared.barState?.showingAIConversation == true
      else { return }
      withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) { barActivated = true }
    }
  }

  @MainActor
  private func waitForResponse() async {
    guard let barState = FloatingControlBarManager.shared.barState else { return }
    for _ in 0..<120 {
      try? await Task.sleep(nanoseconds: 500_000_000)
      if barState.showingAIResponse, let msg = barState.currentAIMessage, !msg.isStreaming {
        withAnimation(.easeInOut(duration: 0.3)) { showContinue = true }
        return
      }
    }
    withAnimation(.easeInOut(duration: 0.3)) { showContinue = true }
  }
}

private struct RedesignMacLineupPreview: View {
  private static let lineupImage: NSImage? = {
    guard let url = Bundle.resourceBundle.url(forResource: "onboarding_mac_lineup", withExtension: "png")
    else { return nil }
    return NSImage(contentsOf: url)
  }()

  var body: some View {
    Group {
      if let nsImage = Self.lineupImage {
        Image(nsImage: nsImage)
          .resizable().interpolation(.high).scaledToFit()
          .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
      } else {
        RoundedRectangle(cornerRadius: 20).fill(Ink.surface2).frame(height: 260)
          .overlay(
            Text("Mac lineup image unavailable")
              .font(InkFont.sans(14, .medium)).foregroundColor(Ink.faint))
      }
    }
  }
}

// MARK: - Step 12 · Voice shortcut

struct RedesignVoiceShortcutStepView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  let stepIndex: Int
  var onComplete: () -> Void
  var onSkip: () -> Void
  var onForceComplete: (() -> Void)?

  @ObservedObject private var shortcutSettings = ShortcutSettings.shared

  @State private var shortcutDetected = false
  @State private var showContinue = false
  @State private var isRecordingCustomShortcut = false
  @State private var captureError: String?
  @State private var localKeyMonitor: Any?
  @State private var globalKeyMonitor: Any?

  static var savedMenu: NSMenu?

  var body: some View {
    VStack(spacing: 0) {
      RedesignShortcutHeader(
        beat: RedesignOnboarding.beat(forStep: stepIndex), onSkip: onSkip,
        onForceComplete: onForceComplete)

      Spacer()

      VStack(spacing: 22) {
        Text("Talk to me, hands-free.").inkDisplay(30).multilineTextAlignment(.center)
        Text("Press and hold to test. Does the key light up?").inkBody().multilineTextAlignment(.center)

        RoundedRectangle(cornerRadius: 16, style: .continuous)
          .fill(Ink.surface)
          .overlay(RoundedRectangle(cornerRadius: 16).strokeBorder(Ink.hair, lineWidth: 1))
          .frame(height: 128).frame(maxWidth: 420)
          .overlay {
            VStack(spacing: 12) {
              HStack(spacing: 8) {
                ForEach(Array(shortcutSettings.pttShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
                  RedesignKeyCap(label: token, lit: shortcutDetected)
                }
              }
              Text(shortcutDetected ? "Shortcut detected" : "Press and hold to test")
                .font(InkFont.sans(13, .medium)).foregroundColor(Ink.faint)
            }
          }

        VStack(spacing: 12) {
          Text("Try another shortcut if it doesn't react:")
            .font(InkFont.sans(14, .medium)).foregroundColor(Ink.muted)
          HStack(spacing: 10) {
            ForEach(ShortcutSettings.pttPresets, id: \.self) { shortcut in
              shortcutChoiceButton(shortcut)
            }
            customShortcutButton
          }
          if isRecordingCustomShortcut || shortcutSettings.pttUsesCustomShortcut || captureError != nil {
            customShortcutRecorder
          }
        }

        if showContinue {
          InkButton(title: "Continue", kind: .primary, size: .lg, action: onComplete)
            .transition(.move(edge: .trailing).combined(with: .opacity))
        }
      }

      Spacer()
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .onAppear {
      FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
      resetFloatingBarConversation()
      FloatingControlBarManager.shared.hide()
      PushToTalkManager.shared.cleanup()
      installKeyMonitor()
    }
    .onDisappear { removeKeyMonitors() }
  }

  private func resetFloatingBarConversation() {
    guard let barState = FloatingControlBarManager.shared.barState else { return }
    barState.showingAIConversation = false
    barState.showingAIResponse = false
    barState.aiInputText = ""
    barState.currentAIMessage = nil
    barState.chatHistory = []
    barState.isVoiceFollowUp = false
    barState.voiceFollowUpTranscript = ""
  }

  private var customShortcutButton: some View {
    let isSelected = shortcutSettings.pttUsesCustomShortcut || isRecordingCustomShortcut
    return Button(action: beginCustomShortcutCapture) {
      Text("Custom").font(InkFont.sans(13, .medium))
        .foregroundColor(isSelected ? Ink.accentStrong : Ink.body)
        .padding(.horizontal, 14).frame(height: 36)
        .background(chipBackground(isSelected))
    }
    .buttonStyle(.plain)
  }

  private var customShortcutRecorder: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text(isRecordingCustomShortcut ? "Press and hold your custom shortcut now" : "Custom shortcut")
        .font(InkFont.sans(13, .semibold)).foregroundColor(Ink.ink)
      HStack(spacing: 10) {
        HStack(spacing: 6) {
          ForEach(Array(shortcutSettings.pttShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
            RedesignKeyCap(label: token, lit: true, big: false)
          }
        }
        Spacer()
        InkButton(title: isRecordingCustomShortcut ? "Listening…" : "Save", kind: .plain, size: .sm) {
          handleCustomShortcutSaveButton()
        }
        .disabled(isRecordingCustomShortcut)
      }
      Text("You can use one key or a combination like ⌘ J.")
        .font(InkFont.sans(12)).foregroundColor(Ink.faint)
      if let captureError { RedesignOnboardingError(message: captureError) }
    }
    .padding(14).frame(maxWidth: 420)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.surface2).overlay(
          RoundedRectangle(cornerRadius: 14).strokeBorder(Ink.hair, lineWidth: 1)))
  }

  private func shortcutChoiceButton(_ shortcut: ShortcutSettings.KeyboardShortcut) -> some View {
    let isSelected = shortcutSettings.pttShortcut == shortcut && !shortcutSettings.pttUsesCustomShortcut
    return Button {
      shortcutSettings.pttShortcut = shortcut
      isRecordingCustomShortcut = false
      captureError = nil
      resetDetectionState()
    } label: {
      HStack(spacing: 6) {
        ForEach(Array(shortcut.displayTokens.enumerated()), id: \.offset) { _, token in
          Text(token).font(InkFont.sans(13, .medium))
        }
      }
      .foregroundColor(isSelected ? Ink.accentStrong : Ink.body)
      .padding(.horizontal, 14).frame(height: 36)
      .background(chipBackground(isSelected))
    }
    .buttonStyle(.plain)
  }

  private func chipBackground(_ selected: Bool) -> some View {
    RoundedRectangle(cornerRadius: 12, style: .continuous)
      .fill(selected ? Ink.accentTint : Ink.surface)
      .overlay(
        RoundedRectangle(cornerRadius: 12).strokeBorder(selected ? Ink.accent : Ink.hair2, lineWidth: 1))
  }

  private func beginCustomShortcutCapture() {
    isRecordingCustomShortcut = true
    captureError = nil
    resetDetectionState()
  }
  private func handleCustomShortcutSaveButton() {
    guard shortcutSettings.pttUsesCustomShortcut else {
      beginCustomShortcutCapture()
      return
    }
    confirmShortcutAndContinue()
  }
  private func resetDetectionState() {
    shortcutDetected = false
    showContinue = false
  }
  private func confirmShortcutAndContinue() {
    captureError = nil
    shortcutDetected = true
    withAnimation(.easeInOut(duration: 0.3)) { showContinue = true }
  }

  private func installKeyMonitor() {
    let mask: NSEvent.EventTypeMask = [.flagsChanged, .keyDown, .keyUp]
    localKeyMonitor = NSEvent.addLocalMonitorForEvents(matching: mask) { event in
      handleShortcutEvent(event) ? nil : event
    }
    globalKeyMonitor = NSEvent.addGlobalMonitorForEvents(matching: mask) { event in
      _ = handleShortcutEvent(event)
    }
    if Self.savedMenu == nil { Self.savedMenu = NSApp.mainMenu }
    NSApp.mainMenu = nil
  }
  private func removeKeyMonitors() {
    if let monitor = localKeyMonitor { NSEvent.removeMonitor(monitor); localKeyMonitor = nil }
    if let monitor = globalKeyMonitor { NSEvent.removeMonitor(monitor); globalKeyMonitor = nil }
    if let menu = Self.savedMenu { NSApp.mainMenu = menu; Self.savedMenu = nil }
  }
  private func handleShortcutEvent(_ event: NSEvent) -> Bool {
    if isRecordingCustomShortcut { return captureCustomShortcut(from: event) }
    guard !shortcutDetected else { return false }
    let shortcut = shortcutSettings.pttShortcut
    let detected: Bool
    switch event.type {
    case .flagsChanged: detected = shortcut.matchesFlagsChanged(event)
    case .keyDown: detected = !event.isARepeat && shortcut.matchesKeyDown(event)
    default: detected = false
    }
    guard detected else { return false }
    confirmShortcutAndContinue()
    return true
  }
  private func captureCustomShortcut(from event: NSEvent) -> Bool {
    guard let shortcut = ShortcutSettings.KeyboardShortcut.fromRecordingEvent(event, allowModifierOnly: true)
    else {
      if event.type == .flagsChanged,
        event.modifierFlags.intersection(.deviceIndependentFlagsMask).isEmpty
      {
        return false
      }
      captureError = "Press the key combination you want to use."
      return false
    }
    shortcutSettings.pttShortcut = shortcut
    isRecordingCustomShortcut = false
    captureError = nil
    return true
  }
}

// MARK: - Step 13 · Voice demo

struct RedesignVoiceDemoView: View {
  @ObservedObject var appState: AppState
  @ObservedObject var chatProvider: ChatProvider
  let stepIndex: Int
  var onComplete: () -> Void
  var onSkip: () -> Void
  var onForceComplete: (() -> Void)?

  @ObservedObject private var pttManager = PushToTalkManager.shared
  @ObservedObject private var shortcutSettings = ShortcutSettings.shared

  @State private var observedShortcutPress = false
  @State private var waitingForResponse = false
  @State private var showContinue = false
  @State private var previousTranscriptionMode: ShortcutSettings.PTTTranscriptionMode?
  @State private var outputReadiness: SystemAudioMuteController.OutputReadiness = .unavailable

  var body: some View {
    VStack(spacing: 0) {
      RedesignShortcutHeader(
        beat: RedesignOnboarding.beat(forStep: stepIndex), onSkip: onSkip,
        onForceComplete: onForceComplete)

      Spacer()

      VStack(spacing: 22) {
        VStack(spacing: 12) {
          Text("Hold \(shortcutSettings.pttShortcut.displayLabel) and ask.")
            .inkDisplay(28).multilineTextAlignment(.center)
          Text("Try: \"What's on my screen?\"").inkBody().multilineTextAlignment(.center)
        }

        if outputReadiness.shouldAskUserToTurnUpVolume {
          volumeWarning.transition(.opacity)
        } else if !observedShortcutPress {
          VStack(spacing: 12) {
            Text("Hold the shortcut, speak, then release")
              .font(InkFont.sans(13)).foregroundColor(Ink.faint)
            HStack(spacing: 6) {
              ForEach(Array(shortcutSettings.pttShortcut.displayTokens.enumerated()), id: \.offset) { _, token in
                RedesignKeyCap(label: token, big: false)
              }
              Text("hold").font(InkFont.sans(13, .medium)).foregroundColor(Ink.faint)
            }
          }
          .transition(.opacity)
        } else if !showContinue {
          Text(waitingForResponse ? "Waiting for omi to respond…" : "Listening… release when done")
            .font(InkFont.sans(13)).foregroundColor(Ink.faint)
            .transition(.opacity)
        }
      }
      .padding(.horizontal, 40)

      Spacer()

      if showContinue {
        InkButton(title: "Continue", kind: .primary, size: .lg, action: onComplete)
          .padding(.bottom, 32)
          .transition(.move(edge: .bottom).combined(with: .opacity))
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .onAppear {
      FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
      resetFloatingBarConversation()
      refreshOutputReadiness()
      if let barState = FloatingControlBarManager.shared.barState {
        PushToTalkManager.shared.setup(barState: barState)
      }
      previousTranscriptionMode = shortcutSettings.pttTranscriptionMode
      shortcutSettings.pttTranscriptionMode = .live
      Task { await chatProvider.warmupBridge() }
    }
    .onDisappear {
      shortcutSettings.pttTranscriptionMode = previousTranscriptionMode ?? .batch
      resetFloatingBarConversation()
      PushToTalkManager.shared.cleanup()
    }
    .task { await pollOutputReadiness() }
    .onChange(of: pttManager.state) { _, newState in
      refreshOutputReadiness()
      guard !outputReadiness.shouldAskUserToTurnUpVolume else { return }
      if newState != .idle { observedShortcutPress = true }
      if OnboardingFlow.shouldUnlockVoiceShortcutContinue(
        observedShortcutPress: observedShortcutPress, pttState: newState), !waitingForResponse
      {
        waitingForResponse = true
        Task { await waitForResponse() }
      }
    }
  }

  private var volumeWarning: some View {
    VStack(spacing: 12) {
      Text(volumeWarningTitle).font(InkFont.sans(15, .semibold)).foregroundColor(Ink.ink)
        .multilineTextAlignment(.center)
      Text("Turn up your Mac volume so you can hear omi respond, then try push-to-talk.")
        .font(InkFont.sans(13)).foregroundColor(Ink.faint).multilineTextAlignment(.center)
      InkButton(title: "I turned it up", kind: .primary, size: .sm, action: refreshOutputReadiness)
    }
    .padding(18).frame(maxWidth: 420)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.surface).overlay(
          RoundedRectangle(cornerRadius: 14).strokeBorder(Ink.hair, lineWidth: 1)))
  }

  private var volumeWarningTitle: String {
    switch outputReadiness {
    case .muted: return "Your Mac volume is muted"
    case .zeroVolume: return "Your Mac volume is at 0"
    case .audible, .unavailable: return ""
    }
  }

  @MainActor
  private func waitForResponse() async {
    guard let barState = FloatingControlBarManager.shared.barState else {
      showContinueNow()
      return
    }
    for _ in 0..<80 {
      try? await Task.sleep(nanoseconds: 250_000_000)
      if let msg = barState.currentAIMessage, !msg.isStreaming,
        !msg.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      {
        showContinueNow()
        return
      }
      if !chatProvider.isSending, observedShortcutPress,
        (chatProvider.errorMessage != nil || barState.currentAIMessage != nil)
      {
        showContinueNow()
        return
      }
    }
    showContinueNow()
  }

  private func showContinueNow() {
    withAnimation(.easeInOut(duration: 0.3)) { showContinue = true }
  }

  private func resetFloatingBarConversation() {
    guard let barState = FloatingControlBarManager.shared.barState else { return }
    barState.showingAIConversation = false
    barState.showingAIResponse = false
    barState.aiInputText = ""
    barState.currentAIMessage = nil
    barState.chatHistory = []
    barState.isVoiceFollowUp = false
    barState.voiceFollowUpTranscript = ""
  }

  private func refreshOutputReadiness() {
    outputReadiness = SystemAudioMuteController.shared.defaultOutputReadiness()
  }

  @MainActor
  private func pollOutputReadiness() async {
    while !Task.isCancelled {
      try? await Task.sleep(nanoseconds: 1_000_000_000)
      refreshOutputReadiness()
    }
  }
}
