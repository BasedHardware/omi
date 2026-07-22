import SwiftUI

/// Root view for one notch panel. The window frame is fixed; this view derives
/// a `NotchPresentation` and animates ONLY the inner content frame + corner
/// radii, anchored `.top` so every expansion grows out of the notch.
struct NotchView: View {
  @ObservedObject var vm: NotchViewModel
  /// The shared main-chat provider; the notch renders its timeline directly.
  var chatProvider: ChatProvider?
  @EnvironmentObject var barState: FloatingControlBarState
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  @State private var isHovering = false
  /// Esc key monitors, live only while a reply lingers (zero idle cost).
  @State private var lingerEscMonitors: [Any] = []

  // MARK: - Presentation ladder

  /// Single value that both the panel size and the rendered content derive
  /// from. Priority:
  /// open > listening > thinking > responding > hint > notification > idle.
  private var presentation: NotchPresentation {
    let base = NotchPresentation.derive(
      isOpen: vm.state == .open,
      tab: vm.selectedTab,
      isVoiceListening: barState.isVoiceListening,
      isThinking: barState.isThinking,
      isResponding: barState.isVoiceResponseActive,
      hintText: barState.pttHintText.isEmpty ? barState.transientHintText : barState.pttHintText,
      notificationID: barState.currentNotification?.id
    )
    // A finished reply lingers for a few seconds after the turn ends. heldReply
    // is set while the response streams, so this is already true the instant
    // the response goes inactive — the notch never collapses to idle first.
    if vm.isLingeringReply {
      switch base {
      case .idle, .notification: return .responding
      default: return base
      }
    }
    return base
  }

  // MARK: - Animations (two isolated timelines)

  /// Discrete morphs: open/close/voice/notification. Springs. The expanded
  /// voice states grow with the open spring; the compact thinking pill and the
  /// passive surfaces settle with the close spring.
  private var morphAnimation: Animation {
    if reduceMotion { return .easeInOut(duration: 0.25) }
    switch presentation {
    case .open, .listening, .responding: return NotchAnimation.open
    case .idle, .thinking, .hint, .notification: return NotchAnimation.close
    }
  }

  /// Continuous auto-grow while an answer streams. Calm, no spring bounce.
  /// Deliberately isolated from the morph timeline: keying the morph spring on
  /// the measured height makes the measure->resize->remeasure loop oscillate.
  private var heightAnimation: Animation {
    reduceMotion ? .easeInOut(duration: 0.25) : .smooth(duration: 0.35)
  }

  private var contentTransition: AnyTransition {
    reduceMotion
      ? .opacity
      : .scale(scale: 0.94, anchor: .top).combined(with: .opacity)
  }

  private var displayedSize: CGSize { vm.size(for: presentation) }

  private var topCornerRadius: CGFloat {
    presentation.isExpandedSurface ? NotchMetrics.cornerOpen.top : NotchMetrics.cornerClosed.top
  }

  private var bottomCornerRadius: CGFloat {
    presentation.isExpandedSurface ? NotchMetrics.cornerOpen.bottom : NotchMetrics.cornerClosed.bottom
  }

  // MARK: - Body

  var body: some View {
    ZStack(alignment: .top) {
      tray
      notchBody
    }
    .frame(width: vm.windowSize.width, height: vm.windowSize.height, alignment: .top)
    .animation(morphAnimation, value: presentation)
    .animation(heightAnimation, value: vm.chatBodyHeight)
    .animation(heightAnimation, value: vm.voiceBodyHeight)
    // Capture the reply as it streams so the linger is ready the moment the
    // response ends (prevents a one-frame collapse to idle).
    .onChange(of: barState.liveVoiceAssistantText) { _, reply in
      vm.noteReply(reply)
    }
    // A new turn starts fresh: reset the measured height and drop any lingering
    // reply from the previous turn.
    .onChange(of: barState.isVoiceListening) { _, listening in
      if listening {
        vm.voiceBodyHeight = nil
        vm.resetReply()
      }
    }
    // Turn ended: start the linger dismissal countdown (hovering pauses it).
    // No captured reply -> just settle back to idle.
    .onChange(of: barState.isVoicePresentationActive) { _, active in
      guard !active else { return }
      if vm.heldReply.isEmpty {
        vm.voiceBodyHeight = nil
      } else {
        vm.beginReplyDismiss()
      }
    }
    // Esc dismisses a lingering reply. The notch is non-activating, so a
    // panel-key handler can't see Esc without stealing focus from your app;
    // instead watch for it while (and only while) a reply lingers.
    .onChange(of: vm.isLingeringReply) { _, lingering in
      if lingering { installLingerEscMonitors() } else { removeLingerEscMonitors() }
    }
    .onDisappear { removeLingerEscMonitors() }
  }

  private func installLingerEscMonitors() {
    removeLingerEscMonitors()
    let local = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
      guard event.keyCode == 53 else { return event }
      MainActor.assumeIsolated { vm.dismissReply() }
      return nil
    }
    let global = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { event in
      guard event.keyCode == 53 else { return }
      MainActor.assumeIsolated { vm.dismissReply() }
    }
    lingerEscMonitors = [local, global].compactMap { $0 }
  }

  private func removeLingerEscMonitors() {
    lingerEscMonitors.forEach { NSEvent.removeMonitor($0) }
    lingerEscMonitors = []
  }

  /// The floating composer glued below the body's bottom edge: it offsets by
  /// the displayed height, so it rides both animation timelines with the body.
  @ViewBuilder
  private var tray: some View {
    // The composer is bound to main chat; it hides on the agents tab so a
    // send can't look like an agent follow-up while routing to main chat.
    if vm.state == .open, vm.selectedTab == .chat, let chatProvider {
      NotchTrayView(chatProvider: chatProvider)
        .frame(width: min(displayedSize.width - 40, 420))
        .offset(y: displayedSize.height + NotchMetrics.trayGap)
        .transition(.move(edge: .top).combined(with: .opacity))
    }
  }

  /// The black island is its OWN stable layer: a NotchShape fill whose frame
  /// always interpolates (no conditional content inside, so its identity can
  /// never break). The presentation-switched content crossfades ON TOP,
  /// clipped to the same shape — the Dynamic Island grammar: the black mass
  /// grows, the content swaps inside it.
  private var notchBody: some View {
    ZStack(alignment: .top) {
      NotchShape(topCornerRadius: topCornerRadius, bottomCornerRadius: bottomCornerRadius)
        .fill(Color.black)
        .frame(width: displayedSize.width, height: displayedSize.height)
        // 1pt seam hider: the top fillets must never reveal a hairline gap
        // against the physical black notch / bezel.
        .overlay(alignment: .top) {
          Rectangle()
            .fill(.black)
            .frame(height: 1)
            .padding(.horizontal, topCornerRadius)
        }
        .shadow(
          color: (vm.state == .open || isHovering || presentation.isExpandedSurface)
            ? .black.opacity(0.7) : .clear,
          radius: 8
        )
      bodyContent
        .frame(width: displayedSize.width, height: displayedSize.height, alignment: .top)
        .clipShape(NotchShape(topCornerRadius: topCornerRadius, bottomCornerRadius: bottomCornerRadius))
      // The Omi orb is rendered once across the whole voice turn so it morphs
      // in place (waveform -> ring -> waveform) instead of cross-fading. It sits
      // just below the camera housing, centered.
      voiceOrbLayer
    }
    .animation(morphAnimation, value: presentation)
    .animation(heightAnimation, value: vm.chatBodyHeight)
    .animation(heightAnimation, value: vm.voiceBodyHeight)
    .contentShape(NotchShape(topCornerRadius: topCornerRadius, bottomCornerRadius: bottomCornerRadius))
    .onHover(perform: handleHover)
    .onExitCommand {
      guard vm.state == .open else { return }
      withAnimation(NotchAnimation.close) { vm.close() }
    }
    // Voice-first: listening / thinking / responding all surface through the
    // presentation ladder on the already-visible notch — no force-open needed.
  }

  @ViewBuilder
  private var bodyContent: some View {
    switch presentation {
    case .open(let tab):
      VStack(spacing: 0) {
        headerRow
        openContent(for: tab)
          .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
          .padding(.horizontal, 20)
          .padding(.top, 4)
          .padding(.bottom, 14)
      }
      .clipped()
      .transition(contentTransition)
    case .listening:
      NotchVoiceView(
        text: barState.liveVoiceUserText,
        placeholder: "Listening…",
        emphasized: true,
        onOpenApp: nil,
        followsTail: true,
        topReserve: voiceTopReserve,
        onHeightChange: updateVoiceBodyHeight
      )
      .transition(contentTransition)
    case .thinking:
      // Just the reserved camera + orb space; the orb overlay draws the ring.
      Color.clear
        .frame(height: voiceThinkingReserve)
        .frame(maxWidth: .infinity, alignment: .top)
        .transition(contentTransition)
    case .responding:
      NotchVoiceView(
        text: respondingText,
        placeholder: "",
        emphasized: false,
        onOpenApp: { MainWindowReveal.activate() },
        followsTail: barState.isVoiceResponseActive,
        topReserve: voiceTopReserve,
        onHeightChange: updateVoiceBodyHeight
      )
      .transition(contentTransition)
    case .hint(let text):
      VStack(spacing: 2) {
        closedChrome
        Text(text)
          .font(.system(size: 11, weight: .medium))
          .foregroundStyle(.white.opacity(0.75))
          .lineLimit(1)
          .padding(.horizontal, 14)
      }
      .transition(contentTransition)
    case .notification(let id):
      VStack(spacing: NotchMetrics.notificationSpacing) {
        closedChrome
        if let notification = barState.currentNotification, notification.id == id {
          NotchNotificationCard(notification: notification)
        }
      }
      .transition(contentTransition)
    case .idle:
      closedChrome
    }
  }

  // MARK: - Voice orb (one instance across the whole turn, morphs in place)

  /// Height reserved for the morphing orb below the camera housing.
  private var voiceOrbHeight: CGFloat { 30 }
  private var voiceOrbTopGap: CGFloat { 4 }
  /// Space above the transcript: camera strip + gap + orb + breathing room
  /// before the text. Matches the orb overlay's top offset.
  private var voiceTopReserve: CGFloat {
    vm.closedNotchSize.height + voiceOrbTopGap + voiceOrbHeight + 16
  }
  /// Thinking has no text — just the camera strip + orb.
  private var voiceThinkingReserve: CGFloat {
    vm.closedNotchSize.height + voiceOrbTopGap + voiceOrbHeight + 8
  }

  /// The reply text while responding: the live stream, or the held reply while
  /// it lingers after the turn.
  private var respondingText: String {
    barState.isVoiceResponseActive ? barState.liveVoiceAssistantText : vm.heldReply
  }

  private var voiceOrbMode: NotchVoiceOrb.Mode {
    if barState.isVoiceListening { return .listening }
    if barState.isThinking { return .thinking }
    if barState.isVoiceResponseActive { return .speaking }
    return .logo  // a finished reply lingering: the Omi mark at rest
  }

  @ViewBuilder
  private var voiceOrbLayer: some View {
    if barState.isVoicePresentationActive || vm.isLingeringReply {
      NotchVoiceOrb(mode: voiceOrbMode)
        .frame(width: 72, height: voiceOrbHeight)
        .padding(.top, vm.closedNotchSize.height + voiceOrbTopGap)
        .allowsHitTesting(false)
        .transition(.opacity)
    }
  }

  // MARK: - Closed chrome (always-visible Omi identity)

  /// The gap the icons visually straddle: the camera housing plus a small
  /// margin on a real notch, a modest fixed gap on the fake notch.
  private var cameraGap: CGFloat {
    vm.hasPhysicalNotch ? vm.cameraWidth + 8 : 56
  }

  /// Logo and gear hug the camera module: [logo][camera][gear] centered as a
  /// cluster, outer space breathes. The mark opens the main Omi window; the
  /// gear opens settings — the only two interactions on the closed notch.
  private var closedChrome: some View {
    HStack(spacing: 0) {
      Spacer(minLength: 0)
      Button(action: { MainWindowReveal.activate() }) {
        NotchOmiMark()
          .frame(width: 24, height: 24)
          // Recording dot: transcription is running (legacy bar indicator).
          .overlay(alignment: .topTrailing) {
            if barState.isRecording {
              Circle()
                .fill(Color.red.opacity(0.9))
                .frame(width: 5, height: 5)
            }
          }
          .frame(
            width: NotchMetrics.closedSideWidth, height: vm.closedNotchSize.height,
            alignment: .trailing
          )
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .accessibilityLabel("Open Omi")
      Color.clear
        .frame(width: cameraGap)
      settingsButton
        .frame(
          width: NotchMetrics.closedSideWidth, height: vm.closedNotchSize.height,
          alignment: .leading
        )
      Spacer(minLength: 0)
    }
    .frame(height: vm.closedNotchSize.height)
  }

  private var settingsButton: some View {
    Button(action: openSettings) {
      Image(systemName: "gearshape.fill")
        .font(.system(size: 11, weight: .semibold))
        .foregroundStyle(.white.opacity(isHovering ? 0.95 : 0.7))
    }
    .buttonStyle(.plain)
    .accessibilityLabel("Omi settings")
  }

  // MARK: - Open header

  /// Jarvis grammar: the tab cluster and the gear FLANK the camera module at
  /// fixed offsets from center — controls stay clustered around the notch
  /// they grew out of, not at the panel edges.
  private var headerRow: some View {
    HStack(spacing: 0) {
      Spacer(minLength: 0)
      HStack(spacing: 6) {
        ForEach(NotchTab.allCases) { tab in
          tabButton(tab)
        }
      }
      // Camera void: header controls must never render under the physical
      // notch.
      Color.clear
        .frame(width: cameraGap)
      HStack(spacing: 6) {
        settingsButton
      }
      // Mirror the two-tab cluster's width so the camera void stays exactly
      // screen-centered (the gear alone is narrower than two tabs).
      .frame(width: 66, alignment: .leading)
      Spacer(minLength: 0)
    }
    .frame(height: vm.closedNotchSize.height)
    .padding(.top, 2)
  }

  private func tabButton(_ tab: NotchTab) -> some View {
    Button {
      withAnimation(reduceMotion ? .easeInOut(duration: 0.2) : NotchAnimation.tab) {
        vm.selectedTab = tab
      }
    } label: {
      Image(systemName: tab.symbol)
        .font(.system(size: 12, weight: .semibold))
        .foregroundStyle(vm.selectedTab == tab ? .white : .white.opacity(0.55))
        .frame(width: 30, height: 22)
        .background(
          Capsule().fill(vm.selectedTab == tab ? Color.white.opacity(0.14) : .clear)
        )
        .contentShape(Capsule())
    }
    .buttonStyle(.plain)
    .help(tab.label)
    .accessibilityLabel(tab.label)
  }

  @ViewBuilder
  private func openContent(for tab: NotchTab) -> some View {
    switch tab {
    case .chat:
      if let chatProvider {
        NotchChatView(chatProvider: chatProvider) { height in
          // 4pt jitter filter: sub-pixel measurement noise must not feed the
          // height animation or the measure loop oscillates.
          if abs((vm.chatBodyHeight ?? 0) - height) > 4 {
            vm.chatBodyHeight = height
          }
        }
      } else {
        Color.clear
      }
    case .agents:
      NotchAgentsView(vm: vm, manager: AgentPillsManager.shared)
    }
  }

  // MARK: - Interactions

  private func handleHover(_ hovering: Bool) {
    isHovering = hovering
    if hovering {
      vm.hoverEntered()
      // Hovering a lingering reply pauses its dismissal so the user can read it.
      vm.keepReply()
    } else {
      vm.hoverExited()
      vm.resumeReplyDismiss()
    }
  }

  /// Feeds the measured voice-content height into the view model behind a 4pt
  /// jitter filter (sub-pixel noise must not drive the height animation or the
  /// measure->resize->remeasure loop oscillates). Same guard the chat body uses.
  private func updateVoiceBodyHeight(_ height: CGFloat) {
    if abs((vm.voiceBodyHeight ?? 0) - height) > 4 {
      vm.voiceBodyHeight = height
    }
  }

  private func openSettings() {
    MainWindowReveal.openSettings()
  }
}
