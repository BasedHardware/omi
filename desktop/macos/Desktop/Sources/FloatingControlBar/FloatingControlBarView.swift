import AppKit
import Combine
@preconcurrency import MarkdownUI
import OmiSupport
import OmiTheme
import SwiftUI
import UniformTypeIdentifiers

/// Holds a non-Sendable value so the `@Sendable` NotificationCenter/Timer
/// closures (all run on `.main`) can capture it. Access is main-thread-only.
private final class MainSendableBox<Value>: @unchecked Sendable {
  var value: Value
  init(_ value: Value) { self.value = value }
}

enum ShortcutHintLayout {
  static func visibleTokens(for keys: [String]) -> [String] {
    keys
  }
}

/// A chat surface replaces the compact notch waveform, so recording must keep
/// its own visible projection while the conversation is open. This is derived
/// entirely from reducer-owned presentation state; it does not create another
/// PTT lifecycle owner.
enum FloatingChatPTTOverlayPolicy {
  static func shouldShow(
    showingAIConversation: Bool,
    isVoiceListening: Bool
  ) -> Bool {
    showingAIConversation && isVoiceListening
  }
}

enum NotchChromeLayout {
  /// A chat can be restoring or transitioning while the rendered conversation
  /// is already visible. Both states must keep the notch controls pinned;
  /// otherwise the logo and settings gear jump out to the surface edges for
  /// a frame during expansion.
  static func isChatPinned(
    showingAIConversation: Bool,
    hasVisibleConversation: Bool
  ) -> Bool {
    showingAIConversation || hasVisibleConversation
  }

  /// The hover menu and chat surface can grow much wider than the physical
  /// notch. Keep the controls in the notch-width header for the entire
  /// lifecycle so expansion never moves either control away from its
  /// collapsed position.
  static func width(
    chromeWidth: CGFloat,
    expandedWidth: CGFloat,
    switcherProgress: CGFloat,
    isChatPresented: Bool
  ) -> CGFloat {
    // The expanded surface owns the extra width. The header must remain a
    // stable physical-notch anchor whether the row is opening, closing, or
    // transitioning into/restoring chat. Keep the parameters at this seam
    // so tests cover every caller state without duplicating layout policy.
    _ = expandedWidth
    _ = switcherProgress
    _ = isChatPresented
    return chromeWidth
  }
}

/// Main floating control bar SwiftUI view composing all sub-views.
struct FloatingControlBarView: View {
  @EnvironmentObject var state: FloatingControlBarState
  @ObservedObject private var shortcutSettings = ShortcutSettings.shared
  @ObservedObject private var agentPills = AgentPillsManager.shared
  weak var window: NSWindow?
  var onPlayPause: () -> Void
  var onAskAI: () -> Void
  var onHide: () -> Void
  var onSendQuery: (String) -> Void
  var onCloseAI: () -> Void
  var onEscape: () -> Void
  var onClearVisibleConversation: () -> Void
  var onRate: ((String, Int?) -> Void)?
  var onShareLink: (() async -> String?)?

  @State private var isHovering = false
  @State private var onboardingGlowOn = false
  @State private var notchLogoHovering = false
  @State private var notchSettingsHovering = false
  @State private var agentSwitcherCollapseWorkItem: DispatchWorkItem?
  /// 0 = hover rows hidden, 1 = hover rows revealed below the fixed header.
  @State private var notchSwitcherProgress: CGFloat = 0
  /// Last reported text-editor height so inputViewHeight can be recomputed
  /// when the pill list changes while the input is open. (Cubic P2.)
  @State private var lastInputEditorHeight: CGFloat = 0
  private let agentChatSwitchTransition = Animation.easeOut(duration: 0.10)
  private var isChatChromePinned: Bool {
    NotchChromeLayout.isChatPinned(
      showingAIConversation: state.showingAIConversation,
      hasVisibleConversation: state.hasVisibleConversation
    )
  }
  private var notchHiddenCenterWidth: CGFloat {
    // Without a physical notch there is no dead zone to straddle — keep a
    // small deliberate gap between the lobes instead of the phantom one.
    state.usesNotchIsland
      ? FloatingControlBarWindow.notchHiddenCenterWidth(for: window?.screen ?? NSScreen.main)
      : FloatingControlBarWindow.pillSurfaceCenterGapWidth
  }
  private var notchSideWidth: CGFloat {
    if isChatChromePinned {
      return agentPills.pills.isEmpty
        ? FloatingControlBarWindow.notchCompactSideWidth
        : FloatingControlBarWindow.notchActiveSideWidth
    }
    if showingNotchThinking {
      return FloatingControlBarWindow.notchThinkingSideWidth
    }
    if agentPills.pills.isEmpty && !state.isVoiceListening {
      return FloatingControlBarWindow.notchCompactSideWidth
    }
    return FloatingControlBarWindow.notchActiveSideWidth
  }
  private var notchChromeWidth: CGFloat {
    notchHiddenCenterWidth + notchSideWidth * 2
  }
  private var notchChromeLayoutWidth: CGFloat {
    isChatChromePinned || shouldShowNotchHoverMenu
      ? max(notchChromeWidth, FloatingControlBarWindow.notchExpandedWidth)
      : notchChromeWidth
  }
  /// The surface can morph below it, but chrome always keeps the compact
  /// notch-width header so its controls do not drift.
  private var notchChromeMorphWidth: CGFloat {
    NotchChromeLayout.width(
      chromeWidth: notchChromeWidth,
      expandedWidth: FloatingControlBarWindow.notchExpandedWidth,
      switcherProgress: notchSwitcherProgress,
      isChatPresented: isChatChromePinned
    )
  }
  private var notchSurfaceHorizontalInset: CGFloat {
    state.usesNotchIsland ? FloatingControlBarWindow.notchGlowOutsetX : 0
  }
  private var notchSurfaceBottomInset: CGFloat {
    state.usesNotchIsland ? FloatingControlBarWindow.notchGlowOutsetBottom : 0
  }
  private var notchHoverMenuHeight: CGFloat {
    FloatingControlBarWindow.notchHoverMenuHeight(agentCount: agentPills.pills.count)
  }
  private var notchHoverRowWidth: CGFloat {
    max(
      0,
      min(
        notchChromeLayoutWidth - NotchAgentStackMetrics.listHorizontalInset * 2,
        FloatingControlBarWindow.notchExpandedWidth - NotchAgentStackMetrics.listHorizontalInset * 2
      )
    )
  }
  var body: some View {
    Group {
      if state.usesNotchIsland || state.showingAIConversation || state.isNotchHoverMenuVisible {
        unifiedFloatingSurface
      } else {
        VStack(spacing: state.isShowingNotification && !state.showingAIConversation ? 8 : 0) {
          barChrome

          if let notification = state.currentNotification, !state.showingAIConversation {
            barNotification(notification)
              .padding(.horizontal, OmiSpacing.sm)
              .padding(.bottom, OmiSpacing.sm)
              .transition(.move(edge: .top).combined(with: .opacity))
          }
        }
      }
    }
    .frame(
      maxWidth: .infinity,
      maxHeight: .infinity,
      alignment: state.usesNotchIsland || state.showingAIConversation || state.isNotchHoverMenuVisible
        ? .top : .center
    )
    .background(Color.clear)
    .omiAnimation(.spring(response: 0.35, dampingFraction: 0.82), value: state.currentNotification?.id)
    // Placed on the always-mounted root (not inside unifiedFloatingSurface) so
    // the pill→island morph still fires when transitioning out of the idle pill.
    .onChange(of: activeLifecycleKey) { _, _ in
      (window as? FloatingControlBarWindow)?.syncActiveIsland()
    }
  }

  /// Composite key for the active PTT lifecycle — any change drives the
  /// pill ↔ notch-island morph (see FloatingControlBarWindow.syncActiveIsland).
  private var activeLifecycleKey: String {
    "\(state.isVoiceListening)-\(state.isThinking)-\(state.isVoiceResponseGlowActive)"
  }

  /// Whether the bar chrome should stretch to fill the window width
  private var barNeedsFullWidth: Bool {
    isHovering || state.isVoiceListening
  }

  private var shouldShowAgentSwitcher: Bool {
    // Do NOT reserve the agent-list height while chat is open. When chat is
    // open the agent-list overlay is hidden, so reserving its height only
    // leaves a blank vertical gap and pushes/clips the chat content. The
    // switcher expands only for explicit pinned/hover interaction AND only
    // when chat is not open. (Cubic P2 + Codex P2.)
    !agentPills.pills.isEmpty
      && shouldShowNotchHoverMenu
  }

  private var shouldShowNotchHoverMenu: Bool {
    state.isNotchHoverMenuVisible
  }

  private var showingNotchWaveform: Bool {
    state.isVoiceListening && state.pttHintText.isEmpty
  }

  /// The notch "thinking" state: a PTT query is committed and being processed,
  /// with no live listening or open conversation surface. Shows the spinning
  /// Omi mark in the left notch lobe (chat already has its own loading UI).
  private var showingNotchThinking: Bool {
    (state.isThinking || state.isVoiceResponseWaiting)
      && !state.showingAIConversation
      && !state.isVoiceListening
  }

  private var showingPTTStatusBanner: Bool {
    !state.pttHintText.isEmpty
  }

  private var shouldUseOmiChatOverlayHitTarget: Bool {
    shouldShowNotchHoverMenu && !showingNotchWaveform
  }

  private var unifiedFloatingSurface: some View {
    VStack(spacing: 0) {
      if state.usesNotchIsland || state.showingAIConversation {
        notchChrome
      } else {
        // No camera housing to blend into — the pill surface starts
        // with a slim top inset instead of the notch chrome band.
        Color.clear
          .frame(height: FloatingControlBarWindow.pillSurfaceTopPadding)
      }

      if showingPTTStatusBanner {
        pttStatusBanner
          .frame(height: FloatingControlBarWindow.pttHintRowHeight)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.bottom, OmiSpacing.xs)
          .transition(.opacity)
      }

      if shouldShowNotchHoverMenu {
        if state.usesNotchIsland {
          VStack(spacing: 0) {
            notchOmiChatRow
              .frame(width: notchHoverRowWidth, height: FloatingControlBarWindow.notchAgentListRowHeight)
              .opacity(notchSwitcherProgress)
              .allowsHitTesting(!shouldUseOmiChatOverlayHitTarget && notchSwitcherProgress > 0.6)

            Color.clear
              .frame(
                width: notchChromeLayoutWidth,
                height: notchHoverMenuHeight - FloatingControlBarWindow.notchAgentListRowHeight
              )
          }
          .frame(width: notchChromeLayoutWidth, height: notchHoverMenuHeight, alignment: .top)
          .onHover { setAgentSwitcherHovering($0) }
          .transition(.identity)
        } else {
          pillAgentListMenu
        }
      }

      if state.showingAIConversation {
        conversationView
          .padding(.horizontal, OmiSpacing.md)
          .padding(.top, 0)
          .padding(.bottom, FloatingControlBarWindow.notchConversationBottomPadding)
          .transition(.opacity)
      }

      if let notification = state.currentNotification, !state.showingAIConversation {
        barNotification(notification)
          .padding(.horizontal, 10)
          .padding(.bottom, 10)
          .transition(.move(edge: .top).combined(with: .opacity))
      }
    }
    .overlay(alignment: .top) {
      if state.usesNotchIsland && shouldUseOmiChatOverlayHitTarget {
        ZStack(alignment: .top) {
          if !agentPills.pills.isEmpty {
            NotchAgentMorphField(
              manager: agentPills,
              activePillID: state.activeAgentChatPillID,
              progress: notchSwitcherProgress,
              notchHiddenCenterWidth: notchHiddenCenterWidth,
              notchSideWidth: notchSideWidth,
              notchChromeHeight: notchChromeHeight,
              rowTopOffset: FloatingControlBarWindow.notchAgentListRowHeight,
              onSelect: openAgentInChat
            )
            .frame(width: notchChromeLayoutWidth, height: notchChromeHeight + notchHoverMenuHeight)
            .allowsHitTesting(notchSwitcherProgress > 0.6)

            notchAgentLogoHitTarget
              .frame(width: notchChromeLayoutWidth, height: notchChromeHeight)
          }

          notchOmiChatOverlayHitTarget
            .frame(width: notchHoverRowWidth, height: FloatingControlBarWindow.notchAgentListRowHeight)
            .offset(y: notchChromeHeight)
            .opacity(notchSwitcherProgress)
            .allowsHitTesting(notchSwitcherProgress > 0.6)
            .zIndex(2)
        }
        .frame(width: notchChromeLayoutWidth, height: notchChromeHeight + notchHoverMenuHeight)
        .onHover { setAgentSwitcherHovering($0) }
      }
    }
    .onAppear { notchSwitcherProgress = shouldShowNotchHoverMenu ? 1 : 0 }
    .padding(.horizontal, notchSurfaceHorizontalInset)
    .padding(.bottom, notchSurfaceBottomInset)
    .background(alignment: .top) {
      GeometryReader { geometry in
        let bottomRadius: CGFloat = state.showingAIConversation || state.currentNotification != nil ? 22 : 18
        let surfaceSize = floatingSurfaceSize(geometry: geometry)
        let surfaceWidth = surfaceSize.width
        let surfaceHeight = surfaceSize.height

        ZStack(alignment: .top) {
          NotchDockShape(
            bottomRadius: bottomRadius,
            topRadius: state.usesNotchIsland ? 0 : 14
          )
          .fill(Color.black)
          .frame(width: surfaceWidth, height: surfaceHeight)

          if state.isVoiceResponseGlowActive {
            NotchResponseGlowView(
              bottomRadius: bottomRadius,
              topRadius: state.usesNotchIsland ? 0 : 14,
              edgeInset: state.usesNotchIsland ? 0 : 3
            )
            .frame(width: surfaceWidth, height: surfaceHeight)
          }

          // Onboarding: a plain white glow on the bar edge so first-run
          // users notice it — no animated sweep. Reuses the voice glow's
          // shape and ramps in 1s after the bar appears. Clears the
          // moment they start typing.
          if state.onboardingBarGlow && state.aiInputText.isEmpty {
            NotchLowerEdgeShape(
              bottomRadius: bottomRadius,
              topRadius: state.usesNotchIsland ? 0 : 14,
              edgeInset: state.usesNotchIsland ? 0 : 3
            )
            .stroke(
              Color.white,
              style: StrokeStyle(lineWidth: 3.2, lineCap: .round, lineJoin: .round)
            )
            .frame(width: surfaceWidth, height: surfaceHeight)
            .shadow(color: Color.white.opacity(0.85), radius: 12)
            .shadow(color: Color.white.opacity(0.5), radius: 22)
            .opacity(onboardingGlowOn ? 1 : 0)
            .allowsHitTesting(false)
            .task {
              // Signal-driven (cancels on disappear) instead of asyncAfter:
              // hold the bar un-glowed for a beat, then ease the glow in.
              onboardingGlowOn = false
              try? await Task.sleep(for: .seconds(1))
              guard !Task.isCancelled else { return }
              OmiMotion.withGated(.easeIn(duration: 0.7)) {
                onboardingGlowOn = true
              }
            }
            .onDisappear { onboardingGlowOn = false }
          }
        }
        .frame(width: geometry.size.width, height: geometry.size.height, alignment: .top)
      }
    }
    .overlay(alignment: .bottomTrailing) {
      if state.showingAIConversation {
        ZStack {
          ResizeHandleView(targetWindow: window)
            .frame(width: 20, height: 20)
          ResizeGripShape()
            .foregroundStyle(.white.opacity(0.3))
            .frame(width: 14, height: 14)
            .allowsHitTesting(false)
        }
        .padding(.trailing, notchSurfaceHorizontalInset + 4)
        .padding(.bottom, notchSurfaceBottomInset + 4)
      }
    }
    .overlay(alignment: .bottom) {
      if FloatingChatPTTOverlayPolicy.shouldShow(
        showingAIConversation: state.showingAIConversation,
        isVoiceListening: state.isVoiceListening
      ) {
        // `conversationView` replaces the normal notch waveform while
        // chat is open. Keep the recording/hint projection visible at
        // the bottom of that same surface instead of hiding PTT state.
        voiceListeningView
          .padding(.horizontal, OmiSpacing.md)
          .frame(height: 42)
          .background(Capsule().fill(Color.white.opacity(0.12)))
          .overlay(Capsule().stroke(Color.white.opacity(0.15), lineWidth: 1))
          .padding(.horizontal, notchSurfaceHorizontalInset + OmiSpacing.md)
          .padding(.bottom, notchSurfaceBottomInset + 8)
          .accessibilityIdentifier("floating_chat_ptt_recording")
          .accessibilityLabel(
            state.pttHintText.isEmpty ? "Recording voice message" : state.pttHintText
          )
          .allowsHitTesting(false)
          .transition(.move(edge: .bottom).combined(with: .opacity))
      }
    }
    .scaleEffect(
      x: max(0.001, state.notchRevealProgress),
      y: max(0.001, state.notchRevealProgress),
      anchor: .top
    )
    .opacity(min(1, max(0, state.notchRevealProgress * 1.4)))
    .contentShape(Rectangle())
    .contextMenu { barContextMenu }
    .onHover(perform: handleBarHover)
    .onChange(of: shouldShowNotchHoverMenu) { _, visible in
      if state.isVoicePresentationActive {
        // A PTT transition replaces the idle hover surface with a separately sized panel. Do not
        // let an in-flight hover spring keep changing the black surface after voice takes over.
        var transaction = Transaction()
        transaction.animation = nil
        withTransaction(transaction) {
          notchSwitcherProgress = 0
        }
        return
      }
      // Fixed window, animated content: in notch mode the NSPanel frame
      // never moves for hover expand/collapse — this value carries the
      // ENTIRE visible morph (black surface height/width, row reveal,
      // dot fan-out). A gentle spring on open, a bounce-free settle on
      // close, both Reduce Motion-gated.
      let morphAnim: Animation =
        visible
        ? FloatingControlBarWindow.notchHoverMenuExpandAnimation
        : FloatingControlBarWindow.notchHoverMenuCollapseAnimation
      OmiMotion.withGated(morphAnim) {
        notchSwitcherProgress = visible ? 1 : 0
      }
    }
    .onChange(of: state.isVoicePresentationActive) { _, active in
      guard active else { return }
      // These view-local values otherwise remain true until pointer exit and can paint stale
      // hover chrome over the voice presentation.
      var transaction = Transaction()
      transaction.animation = nil
      withTransaction(transaction) {
        isHovering = false
        notchLogoHovering = false
        notchSettingsHovering = false
        notchSwitcherProgress = 0
      }
    }
    .onChange(of: state.showingAIConversation) { _, isShowing in
      guard state.usesNotchIsland, !isShowing, shouldShowNotchHoverMenu else { return }
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.08) {
        guard shouldShowNotchHoverMenu else { return }
        (window as? FloatingControlBarWindow)?.resizeForAgentSwitcher(visible: true)
      }
    }
    .onChange(of: agentPills.pills.isEmpty) { _, isEmpty in
      if isEmpty {
        state.agentSwitcherPinned = false
        state.agentSwitcherHovering = false
        notchLogoHovering = false
        (window as? FloatingControlBarWindow)?.setPillAgentListVisible(false)
      }
    }
    .onDisappear { state.setNotchHoverMenuOpen(false) }
  }

  /// Size of the visible black surface behind the floating content.
  ///
  /// Notch idle ↔ hover lifecycle: the NSPanel frame is FIXED at the maximum
  /// hover surface, so the visible surface must derive from the content
  /// morph (`notchSwitcherProgress`), not from the window geometry — the
  /// spring on that progress IS the expand/collapse animation. Other states
  /// (chat, voice, notification, PTT hint) still resize the panel and keep
  /// the geometry-driven surface.
  private func floatingSurfaceSize(geometry: GeometryProxy) -> CGSize {
    let notchHoverLifecycle = NotchHoverSurfacePolicy.usesAnimatedHoverSurface(
      usesNotchIsland: state.usesNotchIsland,
      showingAIConversation: state.showingAIConversation,
      isVoicePresentationActive: state.isVoicePresentationActive,
      isShowingNotification: state.isShowingNotification)
    if notchHoverLifecycle {
      let openWidth = max(notchChromeWidth, FloatingControlBarWindow.notchExpandedWidth)
      return CGSize(
        width: notchChromeWidth + (openWidth - notchChromeWidth) * notchSwitcherProgress,
        height: notchChromeHeight + notchHoverMenuHeight * notchSwitcherProgress
      )
    }
    let hasExpandedSurface =
      state.showingAIConversation
      || state.currentNotification != nil
      || shouldShowNotchHoverMenu
      || showingPTTStatusBanner
    guard hasExpandedSurface else {
      return CGSize(width: notchChromeWidth, height: notchChromeHeight)
    }
    return CGSize(
      width: max(notchChromeWidth, geometry.size.width - notchSurfaceHorizontalInset * 2),
      height: max(notchChromeHeight, geometry.size.height - notchSurfaceBottomInset)
    )
  }

  private var notchChrome: some View {
    ZStack {
      HStack(spacing: 0) {
        notchAgentLobe
          .frame(width: notchSideWidth, height: notchChromeHeight)

        Spacer(minLength: notchHiddenCenterWidth)

        notchControlLobe
          .frame(width: notchSideWidth, height: notchChromeHeight)
      }

      Color.clear
        .frame(width: notchHiddenCenterWidth, height: notchChromeHeight)
        .allowsHitTesting(false)
    }
    .frame(height: notchChromeHeight)
    .frame(width: notchChromeMorphWidth)
  }

  private var notchAgentLobe: some View {
    HStack(spacing: 0) {
      if showingNotchWaveform {
        VoiceWaveformBars(isActive: true)
          .scaleEffect(0.72)
          .frame(width: 28, height: 15)
          .frame(width: 38, height: 27)
      } else if showingNotchThinking {
        NotchThinkingMark()
          .frame(width: 24, height: 24)
          .frame(width: notchSideWidth, height: notchChromeHeight, alignment: .trailing)
          .padding(.trailing, OmiSpacing.hairline)
      } else {
        ZStack(alignment: .trailing) {
          // The Omi mark always belongs to the compact notch header.
          // Hover rows reveal below it; they must never borrow or
          // animate this header identity into the expanded surface.
          NotchAgentPillsRowView(manager: agentPills, barWindow: window)
            .scaleEffect(notchLogoHovering ? 1.06 : 1.0)
        }
        .frame(width: notchSideWidth, height: notchChromeHeight, alignment: .trailing)
        .padding(.trailing, OmiSpacing.hairline)
        .contentShape(Rectangle())
        .onHover { setNotchLogoHovering($0) }
        .onTapGesture {
          openAgentChatsFromNotchLogo()
        }
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
  }

  /// Picks the actionable "Couldn't reach Omi" card for reach errors, else the
  /// normal notification card.
  @ViewBuilder
  private func barNotification(_ notification: FloatingBarNotification) -> some View {
    if notification.assistantId == "reach_error" {
      reachErrorCard(notification)
    } else {
      notificationView(notification)
    }
  }

  /// Hard reach failure (retries exhausted). Persists until the user picks
  /// Retry (re-runs the query, restarting backoff) or Skip (back to idle).
  private func reachErrorCard(_ notification: FloatingBarNotification) -> some View {
    HStack(alignment: .center, spacing: OmiSpacing.sm) {
      Image(systemName: "exclamationmark.triangle.fill")
        .font(.system(size: 14, weight: .semibold))
        .foregroundColor(.white.opacity(0.9))

      VStack(alignment: .leading, spacing: 1) {
        Text(notification.title)
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(.white)
          .lineLimit(1)
        if !notification.message.isEmpty {
          Text(notification.message)
            .scaledFont(size: 11)
            .foregroundColor(.white.opacity(0.7))
            .lineLimit(1)
        }
      }

      Spacer(minLength: OmiSpacing.sm)

      Button {
        FloatingControlBarManager.shared.retryReachError()
      } label: {
        Text("Retry")
          .scaledFont(size: 12, weight: .semibold)
          .foregroundColor(.white)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(Color.white.opacity(0.18))
          .clipShape(Capsule())
      }
      .buttonStyle(.plain)

      Button {
        FloatingControlBarManager.shared.dismissReachError()
      } label: {
        Text("Skip")
          .scaledFont(size: 12, weight: .semibold)
          .foregroundColor(.white.opacity(0.6))
          .padding(.horizontal, OmiSpacing.xs)
          .padding(.vertical, OmiSpacing.xxs)
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.md)
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  private var notchAgentLogoHitTarget: some View {
    GeometryReader { geometry in
      let logoCenterX = NotchAgentStackMetrics.logoCenterX(
        rowWidth: geometry.size.width,
        notchHiddenCenterWidth: notchHiddenCenterWidth,
        notchSideWidth: notchSideWidth
      )

      Color.clear
        .frame(width: 44, height: 44)
        .contentShape(Rectangle())
        .position(x: logoCenterX, y: notchChromeHeight / 2)
        .onHover { setNotchLogoHovering($0) }
        .onTapGesture {
          openAgentChatsFromNotchLogo()
        }
        .accessibilityLabel("Agent chats")
        .accessibilityHint("Open agent chats")
    }
  }

  private var notchControlLobe: some View {
    // Right-side lobe of the notch chrome. In notch mode the legacy
    // controlBarView is never rendered, so this lobe is the only hit
    // target on the right side of the notch. Wire it to open Ask Omi on
    // tap and accept hover so users on notched displays can still reach
    // the conversation/PTT entry point by clicking the notch. (Codex P1.)
    // It is intentionally subtle (transparent) to preserve the minimal
    // notch aesthetic.
    ZStack(alignment: .leading) {
      Button(action: onAskAI) {
        Color.clear
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)

      if !state.isVoicePresentationActive && notchSettingsHovering {
        notchSettingsButton
          .zIndex(1)
          .transition(.scale.combined(with: .opacity))
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    .padding(.leading, OmiSpacing.xs)
    // Breathing room between the settings gear and the island's right edge.
    .padding(.trailing, OmiSpacing.md)
    .accessibilityElement(children: .contain)
  }

  private var notchSettingsButton: some View {
    Button(action: openFloatingBarSettings) {
      Image(systemName: "gearshape.fill")
        .scaledFont(size: 12, weight: .semibold)
        .foregroundColor(.white.opacity(0.86))
        .frame(width: 26, height: 24)
        .frame(width: 44, height: 44)
        .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .help("Floating Bar Settings")
    .accessibilityIdentifier("notch_floating_bar_settings")
    .accessibilityLabel("Floating Bar Settings")
    .accessibilityHint("Open settings")
  }

  private var notchOmiChatRow: some View {
    Button {
      openOmiChatFromNotchRow()
    } label: {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "message.fill")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(.white.opacity(0.86))
          .frame(
            width: NotchAgentStackMetrics.listOrbSize,
            height: NotchAgentStackMetrics.listOrbSize
          )
          .frame(width: NotchAgentStackMetrics.listOrbSlotWidth, alignment: .leading)

        Text("Omi Chat")
          .scaledFont(size: 12, weight: .semibold)
          .foregroundStyle(.white.opacity(0.94))
          .lineLimit(1)
          .frame(maxWidth: .infinity, alignment: .leading)

        notchShortcutHint("Ask", keys: shortcutSettings.askOmiShortcut.displayTokens)
        notchShortcutHint(systemImage: "mic.fill", keys: shortcutSettings.pttShortcut.displayTokens)
      }
      .padding(.leading, NotchAgentStackMetrics.listRowLeadingPadding)
      .padding(.trailing, 10)
      .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
      .overlay(alignment: .bottom) {
        Rectangle()
          .fill(Color.white.opacity(0.11))
          .frame(height: 0.6)
      }
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
  }

  private var notchOmiChatOverlayHitTarget: some View {
    Button {
      openOmiChatFromNotchRow()
    } label: {
      Color.clear
        .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .accessibilityElement(children: .ignore)
    .accessibilityLabel("Omi Chat")
    .accessibilityHint("Open Omi Chat")
    .accessibilityAddTraits(.isButton)
  }

  private func notchShortcutHint(_ title: String, keys: [String]) -> some View {
    HStack(spacing: 3) {
      Text(title)
        .scaledFont(size: 8, weight: .semibold)
        .foregroundStyle(.white.opacity(0.54))
      notchShortcutKeys(keys)
    }
  }

  private func notchShortcutHint(systemImage: String, keys: [String]) -> some View {
    HStack(spacing: 3) {
      Image(systemName: systemImage)
        .scaledFont(size: 8, weight: .semibold)
        .foregroundStyle(.white.opacity(0.58))
        .frame(width: 8, height: 10)
      notchShortcutKeys(keys)
    }
  }

  private func notchShortcutKeys(_ keys: [String]) -> some View {
    ForEach(ShortcutHintLayout.visibleTokens(for: keys), id: \.self) { key in
      Text(key)
        .scaledFont(size: 8, weight: .medium)
        .foregroundStyle(.white.opacity(0.75))
        .lineLimit(1)
        .minimumScaleFactor(0.7)
        .padding(.horizontal, key.count > 1 ? 3 : 0)
        .frame(minWidth: 12, minHeight: 12)
        .background(Color.white.opacity(0.12))
        .cornerRadius(OmiChrome.stripRadius)
    }
    .fixedSize(horizontal: true, vertical: false)
  }

  private var notchChromeHeight: CGFloat {
    FloatingControlBarWindow.notchChromeHeight(for: window?.screen ?? NSScreen.main)
  }

  /// Full-width readable status strip under chrome / pill for too-short PTT
  /// taps and mic errors. Keeps long copy out of the narrow logo/mic slot.
  private var pttStatusBanner: some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(systemName: "mic.fill")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(.white.opacity(0.9))
      Text(state.pttHintText)
        .scaledFont(size: 12, weight: .medium)
        .foregroundColor(.white)
        .lineLimit(1)
      Spacer(minLength: 0)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  /// Collapsed pill / hover bar chrome. Conversations, notifications-with-
  /// chat, and the agent list all render on `unifiedFloatingSurface` — this
  /// chrome only ever shows the idle pill, hover hints, and voice states.
  private var barChrome: some View {
    VStack(spacing: 0) {
      controlBarView

      if showingPTTStatusBanner {
        pttStatusBanner
          .frame(height: FloatingControlBarWindow.pttHintRowHeight)
          .padding(.horizontal, 10)
          .padding(.bottom, OmiSpacing.xs)
          .transition(.opacity)
      }
    }
    .frame(maxWidth: barNeedsFullWidth || showingPTTStatusBanner ? .infinity : nil, alignment: .top)
    .overlay(alignment: .topTrailing) {
      if isHovering && !state.isVoiceListening {
        Button {
          openFloatingBarSettings()
        } label: {
          Image(systemName: "gearshape.fill")
            .font(.system(size: 11))
            .foregroundColor(.white.opacity(0.7))
            .frame(width: 22, height: 22)
            .background(Color.white.opacity(0.12))
            .cornerRadius(5)
        }
        .buttonStyle(.plain)
        .padding(OmiSpacing.xs)
        .transition(.opacity)
      }
    }
    // No .clipped() here: the pill's status/voice glow needs to render
    // outside the chrome bounds (the window grows via glow outsets).
    .background(DraggableAreaView(targetWindow: window))
    .floatingBackground(cornerRadius: barNeedsFullWidth ? 20 : 5)
    .contextMenu {
      barContextMenu
    }
    .onHover(perform: handleBarHover)
  }

  @ViewBuilder
  private var barContextMenu: some View {
    Button("Disable for 2 hours") {
      FloatingControlBarManager.shared.snooze(
        for: FloatingControlBarManager.snoozeTwoHoursDuration
      )
    }
  }

  private var conversationView: some View {
    ZStack(alignment: .top) {
      if case .agent = state.conversationSurface, let activeAgentChatPill {
        AgentMainChatView(
          pill: activeAgentChatPill,
          manager: agentPills,
          onBackToAgentRows: {
            showAgentListFromConversation()
          },
          onEscape: onEscape
        )
        .id(activeAgentChatPill.id)
        .zIndex(1)
      } else if state.conversationSurface == .mainResponse {
        mainConversationContainer {
          aiResponseView
            .id("response")
        }
        .zIndex(1)
      } else {
        mainConversationContainer {
          aiInputView
            .id("input")
        }
        .zIndex(1)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
  }

  @ViewBuilder
  private func mainConversationContainer<Content: View>(@ViewBuilder content: () -> Content) -> some View {
    // This is the expanded main-chat header, never the compact/hover row.
    // It cannot depend on pill projection timing: the main transcript can
    // render an accepted spawn receipt one update before the manager does.
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(spacing: OmiSpacing.sm) {
        Button(action: mainConversationBackAction) {
          Image(systemName: "chevron.left")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(.white.opacity(0.82))
            .frame(width: 36, height: 32)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(agentPills.pills.isEmpty ? "Close Omi Chat" : "Back to subagents")

        Text("Omi Chat")
          .scaledFont(size: OmiType.body, weight: .bold)
          .foregroundColor(.white)
          .lineLimit(1)

        Spacer(minLength: 0)

        if state.hasVisibleConversation {
          escToClearHint
        }
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.top, OmiSpacing.sm)

      content()
    }
  }

  private var activeAgentChatPill: AgentPill? {
    guard let id = state.activeAgentChatPillID else { return nil }
    return agentPills.pills.first { $0.id == id }
  }

  private var escToClearHint: some View {
    HStack(spacing: OmiSpacing.xxs) {
      Text("esc")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(.secondary)
        .frame(width: 30, height: 16)
        .background(Color.white.opacity(0.1))
        .cornerRadius(4)
      Text("to clear")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(.secondary)
    }
  }

  private func setAgentSwitcherHovering(_ hovering: Bool) {
    agentSwitcherCollapseWorkItem?.cancel()
    agentSwitcherCollapseWorkItem = nil

    if hovering {
      (window as? FloatingControlBarWindow)?.openNotchHoverMenuUntilExit()
      return
    }

    let workItem = DispatchWorkItem {
      (window as? FloatingControlBarWindow)?.updateNotchPointerFromGlobalMouse()
      if !shouldShowNotchHoverMenu {
        notchLogoHovering = false
      }
    }
    agentSwitcherCollapseWorkItem = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.12, execute: workItem)
  }

  private func toggleAgentSwitcherPinned() {
    guard !agentPills.pills.isEmpty else { return }
    agentSwitcherCollapseWorkItem?.cancel()
    agentSwitcherCollapseWorkItem = nil
    state.agentSwitcherPinned.toggle()
    state.agentSwitcherHovering = state.agentSwitcherPinned
  }

  private func setNotchLogoHovering(_ hovering: Bool) {
    guard !state.isVoicePresentationActive || !hovering else {
      notchLogoHovering = false
      return
    }
    OmiMotion.withGated(.spring(response: 0.18, dampingFraction: 0.74)) {
      notchLogoHovering = hovering
    }
    setAgentSwitcherHovering(hovering)
  }

  private func openAgentChatsFromNotchLogo() {
    guard !agentPills.pills.isEmpty else {
      onAskAI()
      return
    }
    if state.showingAIConversation {
      showAgentListFromConversation()
      return
    }
    if state.usesNotchIsland {
      toggleAgentSwitcherPinned()
      (window as? FloatingControlBarWindow)?.openNotchHoverMenuUntilExit()
    } else {
      (window as? FloatingControlBarWindow)?
        .setPillAgentListVisible(!state.isNotchHoverMenuVisible)
    }
  }

  private func openAgentInChat(_ pill: AgentPill) {
    openAgentInChat(agentID: pill.id)
  }

  private func openAgentInChat(agentID: UUID, completion: ((Bool) -> Void)? = nil) {
    openAgentInChat(
      ref: AgentTimelineRef(pillId: agentID, sessionId: nil, runId: nil),
      completion: completion
    )
  }

  private func openAgentInChat(ref: AgentTimelineRef, completion: ((Bool) -> Void)? = nil) {
    Task { @MainActor in
      let resolved = await agentPills.resolveAndPresentAgent(
        pillId: ref.pillId,
        sessionId: ref.sessionId,
        runId: ref.runId
      )
      guard resolved else {
        log(
          "FloatingControlBarView: agent open unavailable after hydrate "
            + "pillId=\(ref.pillId?.uuidString ?? "nil") "
            + "sessionId=\(ref.sessionId ?? "nil") "
            + "runId=\(ref.runId ?? "nil")"
        )
        completion?(false)
        return
      }
      guard
        let pill = agentPills.pills.first(where: { pill in
          if let pillId = ref.pillId, pill.id == pillId { return true }
          if let runId = ref.runId, pill.canonicalRunId == runId { return true }
          if let sessionId = ref.sessionId, pill.canonicalSessionId == sessionId { return true }
          return false
        }) ?? ref.pillId.flatMap({ id in agentPills.pills.first(where: { $0.id == id }) })
      else {
        completion?(false)
        return
      }
      if state.conversationSurface == .agent(pill.id) {
        showAgentListFromConversation()
        completion?(true)
        return
      }
      agentPills.markViewed(pillID: pill.id)
      let barWindow = window as? FloatingControlBarWindow
      let wasShowingConversation = state.showingAIConversation
      state.setNotchHoverMenuOpen(false)
      notchLogoHovering = false
      barWindow?.makeKeyAndOrderFront(nil)
      OmiMotion.withGated(agentChatSwitchTransition) {
        state.present(.agent(pill.id))
        state.isAILoading = false
      }
      barWindow?.resizeForActiveAgentChatPublic(pillID: pill.id, animated: !wasShowingConversation)
      completion?(true)
    }
  }

  private func openOmiChatFromNotchRow() {
    state.setNotchHoverMenuOpen(false)
    notchLogoHovering = false
    onAskAI()
  }

  private func showAgentListFromConversation() {
    (window as? FloatingControlBarWindow)?.leaveAgentConversation() ?? onCloseAI()
  }

  private func mainConversationBackAction() {
    guard !agentPills.pills.isEmpty else {
      onCloseAI()
      return
    }
    showAgentListFromConversation()
  }

  private func handleBarHover(_ hovering: Bool) {
    if state.usesNotchIsland {
      (window as? FloatingControlBarWindow)?.updateNotchPointerFromGlobalMouse()
      let showsHoverChrome = hovering && !state.isVoicePresentationActive
      OmiMotion.withGated(.easeOut(duration: FloatingControlBarWindow.notchHoverMenuExpandDuration)) {
        isHovering = showsHoverChrome && state.isNotchHoverMenuVisible
        notchSettingsHovering = showsHoverChrome
      }
      if !hovering || !state.isNotchHoverMenuVisible {
        notchLogoHovering = false
      }
      return
    }

    if !hovering {
      state.requiresHoverReset = false
    }

    let effectiveHover = hovering && !state.requiresHoverReset && isWithinActivationZoneForCurrentMode()
    state.isHoveringBar = effectiveHover

    // With subagents present, hovering the pill unfurls the agent rows —
    // the same surface the notch shows on hover — instead of the legacy
    // expanded bar. Moving the pointer away collapses back to the pill.
    if !agentPills.pills.isEmpty, !state.showingAIConversation {
      let barWindow = window as? FloatingControlBarWindow
      if effectiveHover {
        barWindow?.setPillAgentListVisible(true)
      } else {
        barWindow?.schedulePillAgentListCollapse()
      }
      return
    }

    // Resize window BEFORE updating SwiftUI state on expand so the expanded
    // content never renders in a too-small window. If the resize was
    // skipped (guarded), do NOT show the expanded bar — oversized content
    // in a small window force-grows it with the origin pinned, sliding
    // the pill sideways.
    var didExpand = false
    if effectiveHover {
      didExpand = (window as? FloatingControlBarWindow)?.resizeForHover(expanded: true) ?? false
    }
    OmiMotion.withGated(.easeOut(duration: FloatingControlBarWindow.notchHoverMenuExpandDuration)) {
      isHovering = effectiveHover && didExpand
    }
    if !effectiveHover {
      (window as? FloatingControlBarWindow)?.resizeForHover(expanded: false)
    }
  }

  private func isWithinActivationZoneForCurrentMode() -> Bool {
    guard state.usesNotchIsland else { return true }
    guard let window else { return false }
    // The notch window frame is fixed at the maximum hover surface, so the
    // activation zone must be derived from the VISIBLE content (collapsed
    // chrome when idle, the current-agent-count menu when open), never
    // from the window frame — otherwise hover triggers far below/beside
    // the visible island.
    let hitHeight =
      state.isAgentSwitcherExpanded
      ? max(notchChromeHeight, notchChromeHeight + notchHoverMenuHeight)
      : FloatingControlBarWindow.notchActivationHeight
    let visibleWidth =
      state.isAgentSwitcherExpanded
      ? max(notchChromeWidth, FloatingControlBarWindow.notchExpandedWidth)
      : notchChromeWidth
    let horizontalOutset = max(
      FloatingControlBarWindow.notchGlowOutsetX,
      (window.frame.width - visibleWidth) / 2
    )
    return FloatingControlBarGeometry.notchChromeActivationContains(
      mouseLocation: NSEvent.mouseLocation,
      windowFrame: window.frame,
      chromeHeight: hitHeight,
      horizontalOutset: horizontalOutset
    )
  }

  private func notificationView(_ notification: FloatingBarNotification) -> some View {
    // The entire card opens the chat. A SwiftUI Button only hit-tests its
    // visible content, so the previous layout left the padding and spacer
    // as dead zones — users reported clicks landing "on the box" doing
    // nothing. Wrapping the whole card in a single Button with
    // contentShape(Rectangle()) makes every pixel clickable. The dismiss
    // (X) button sits in an overlay on top so it keeps its own hit region.
    Button {
      FloatingControlBarManager.shared.openNotificationAsChat(notification)
    } label: {
      HStack(alignment: .top, spacing: 10) {
        ZStack {
          RoundedRectangle(cornerRadius: 10)
            .fill(Color.white.opacity(0.08))
            .frame(width: 34, height: 34)

          Image(systemName: "bell.badge.fill")
            .font(.system(size: 14, weight: .semibold))
            .foregroundColor(.white)
        }

        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Text(notification.title)
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(.white)
            .lineLimit(1)

          Text(notification.message)
            .scaledFont(size: 12)
            .foregroundColor(.white.opacity(0.72))
            .lineLimit(3)
            .fixedSize(horizontal: false, vertical: true)
        }

        Spacer(minLength: 0)

        // Reserve space so text never runs under the overlaid action buttons.
        // Wider for actionable (task) notifications that also show Execute.
        Color.clear
          .frame(width: notification.assistantId == "task" ? 90 : 36, height: 18)
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.md)
      .frame(maxWidth: .infinity, alignment: .leading)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .overlay(alignment: .topTrailing) {
      HStack(spacing: OmiSpacing.xs) {
        // Execute is only meaningful for actionable notifications (tasks).
        // Focus / Insight (tips) / other passive notifications are
        // informational — spawning an agent there made no sense.
        if notification.assistantId == "task" {
          Button {
            let model =
              ShortcutSettings.shared.selectedModel.isEmpty
              ? ModelQoS.Claude.defaultSelection
              : ShortcutSettings.shared.selectedModel
            let query = ProactiveTaskExecute.buildQuery(
              title: notification.title,
              message: notification.message
            )
            _ = AgentPillsManager.shared.spawn(
              query: query,
              model: model,
              originSurface: .floatingBar,
              systemPromptSuffix: ProactiveTaskExecute.systemPromptSuffix
            )
            FloatingControlBarManager.shared.dismissCurrentNotification()
          } label: {
            HStack(spacing: OmiSpacing.xxs) {
              Image(systemName: "sparkles")
                .font(.system(size: 9, weight: .bold))
              Text("Execute")
                .scaledFont(size: OmiType.micro, weight: .semibold)
            }
            .foregroundColor(.white)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xxs)
            .background(Color.white.opacity(0.18))
            .clipShape(Capsule())
          }
          .buttonStyle(.plain)
          .help("Spawn an agent to handle this")
        }

        Button {
          FloatingControlBarManager.shared.dismissCurrentNotification()
        } label: {
          Image(systemName: "xmark")
            .font(.system(size: 10, weight: .bold))
            .foregroundColor(.white.opacity(0.62))
            .frame(width: 18, height: 18)
            .background(Color.white.opacity(0.08))
            .clipShape(Circle())
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.md)
    }
    .floatingBackground(cornerRadius: 18)
  }

  private func openFloatingBarSettings() {
    activateMainAppWindow()
    // Post the navigate request once the main window is key (its
    // `navigateToFloatingBarSettings` receiver is mounted by then) rather than
    // guessing a fixed delay for the window to appear (BL-005).
    runWhenMainAppWindowKey {
      NotificationCenter.default.post(name: .navigateToFloatingBarSettings, object: nil)
    }
  }

  private func activateMainAppWindow() {
    NSApp.activate()

    if revealMainAppWindow() { return }

    // No existing window — open one and reveal it the moment it becomes key,
    // instead of guessing a fixed delay for openWindow(id:) to create it (BL-005).
    AppDelegate.openMainWindow?()
    runWhenMainAppWindowKey {
      NSApp.activate()
      _ = revealMainAppWindow()
    }
  }

  /// True for the app's real main window (not the floating panel or the
  /// menu-bar popover).
  private static func isRealMainAppWindow(_ window: NSWindow) -> Bool {
    !(window is NSPanel)
      && window.frame.width > 300
      && window.frame.height > 200
      && !window.title.hasPrefix("Item-")
  }

  /// Run `action` once the app's main window is key — immediately if one already
  /// is, otherwise on the next `didBecomeKeyNotification` for a real main window.
  /// Replaces fixed `asyncAfter` guesses that waited for `openWindow(id:)` to
  /// create/activate the window (BL-005); the window-key event is the real signal.
  private func runWhenMainAppWindowKey(_ action: @escaping () -> Void) {
    // The observer/Timer closures below are `@Sendable`; `action` is a non-Sendable
    // closure (it captures this view), so box it to carry it across safely. All of
    // these closures run on `.main`.
    let actionBox = MainSendableBox(action)
    if let key = NSApp.keyWindow, Self.isRealMainAppWindow(key) {
      // One runloop hop, same as the observer path below, so a freshly-keyed
      // window's content (e.g. the navigate receiver) is mounted before we act.
      DispatchQueue.main.async { actionBox.value() }
      return
    }
    let tokenBox = MainSendableBox<NSObjectProtocol?>(nil)
    let removeObserver: @Sendable () -> Void = {
      if let token = tokenBox.value { NotificationCenter.default.removeObserver(token) }
    }
    tokenBox.value = NotificationCenter.default.addObserver(
      forName: NSWindow.didBecomeKeyNotification, object: nil, queue: .main
    ) { note in
      let noteBox = MainSendableBox(note)
      MainActor.assumeIsolated {
        guard let window = noteBox.value.object as? NSWindow, Self.isRealMainAppWindow(window) else {
          return
        }
        removeObserver()
        // One runloop hop so SwiftUI can mount the freshly-opened window's
        // content (e.g. the navigate receiver) before we act.
        DispatchQueue.main.async { actionBox.value() }
      }
    }
    // Safety net: if no real main window ever becomes key (e.g. openMainWindow
    // was nil, or the view went away), drop the observer after a bounded delay
    // so it can't linger on the default center indefinitely.
    Timer.scheduledTimer(withTimeInterval: 10, repeats: false) { _ in removeObserver() }
  }

  @discardableResult
  private func revealMainAppWindow() -> Bool {
    guard
      let window = NSApp.windows.first(where: { window in
        let isRealAppWindow =
          !(window is NSPanel)
          && window.frame.width > 300
          && window.frame.height > 200
        let isMenuBarPopover = window.title.hasPrefix("Item-")
        return isRealAppWindow && !isMenuBarPopover && !window.isMiniaturized
      })
        ?? NSApp.windows.first(where: { window in
          let isRealAppWindow =
            !(window is NSPanel)
            && window.frame.width > 300
            && window.frame.height > 200
          let isMenuBarPopover = window.title.hasPrefix("Item-")
          return isRealAppWindow && !isMenuBarPopover
        })
    else {
      return false
    }

    window.deminiaturize(nil)
    window.makeKeyAndOrderFront(nil)
    window.orderFrontRegardless()
    return true
  }

  private var controlBarView: some View {
    let allowsHoverExpansion = isHovering && !state.isVoiceResponseGlowActive
    return Group {
      if !state.pttHintText.isEmpty {
        // Too-short / error copy lives in `pttStatusBanner` below — keep
        // the pill chrome as the idle strip so we don't stack two mics.
        PillStatusObservingView(manager: agentPills) { pills in
          let agentGroup =
            state.isVoiceResponseGlowActive
            ? nil
            : NotchAgentStatusGroup.aggregate(for: pills)
          compactCircleView(agentGroup: agentGroup)
            .modifier(AgentStatusGlow(group: agentGroup))
        }
        .frame(height: 14)
        .padding(.vertical, 5)
        .transition(.opacity)
      } else if state.isVoiceListening {
        voiceListeningView
          .padding(.horizontal, 10)
          .padding(.vertical, 5)
          .frame(height: 42)
          .transition(.opacity)
      } else if allowsHoverExpansion {
        VStack(spacing: 1) {
          compactButton(title: "Open Omi", keys: shortcutSettings.askOmiShortcut.displayTokens) {
            onAskAI()
          }

          HStack(spacing: OmiSpacing.xs) {
            compactLabel("Push to talk", keys: shortcutSettings.pttShortcut.displayTokens)
          }
        }
        .padding(.horizontal, OmiSpacing.xs)
        .padding(.vertical, 3)
        .frame(height: 50)
        .transition(.opacity)
      } else {
        PillStatusObservingView(manager: agentPills) { pills in
          let agentGroup =
            state.isVoiceResponseGlowActive
            ? nil
            : NotchAgentStatusGroup.aggregate(for: pills)
          compactCircleView(agentGroup: agentGroup)
            .modifier(AgentStatusGlow(group: agentGroup))
        }
        .transition(.opacity)
      }
    }
  }

  /// The pill-mode agent list: same rows as the notch hover menu, rendered
  /// directly (no notch morph — there is no logo ring to unfurl from).
  private var pillAgentListMenu: some View {
    PillStatusObservingView(manager: agentPills) { pills in
      VStack(spacing: 0) {
        notchOmiChatRow
          .frame(width: notchHoverRowWidth, height: FloatingControlBarWindow.notchAgentListRowHeight)

        ForEach(pills.prefix(NotchAgentStackMetrics.maxAgents), id: \.id) { pill in
          Button {
            openAgentInChat(pill)
          } label: {
            NotchAgentListRow(
              title: pill.title,
              status: pill.status,
              activity: ChatContinuityInvariants.agentPreviewText(
                prompt: pill.query,
                output: pill.latestActivity
              ),
              isSelected: pill.id == state.activeAgentChatPillID,
              progress: 1
            )
            .overlay(alignment: .leading) {
              pillRowIdentityMark(pill)
                .padding(.leading, NotchAgentStackMetrics.listRowLeadingPadding)
            }
            .frame(width: notchHoverRowWidth, height: FloatingControlBarWindow.notchAgentListRowHeight)
          }
          .buttonStyle(.plain)
          .help(pill.title)
        }
      }
      .padding(.bottom, FloatingControlBarWindow.notchHoverMenuBottomMargin)
      .frame(width: notchChromeLayoutWidth, alignment: .top)
      .onHover { handleBarHover($0) }
      .transition(.opacity)
    }
  }

  @ViewBuilder
  private func pillRowIdentityMark(_ pill: AgentPill) -> some View {
    let group = NotchAgentStatusGroup(status: pill.status)
    if pill.providerIdentity.rendersProviderMark {
      AgentProviderLogoMark(
        provider: pill.providerIdentity,
        statusColor: group.color,
        size: NotchAgentStackMetrics.listOrbSize + 5
      )
      .shadow(color: group.color.opacity(0.55), radius: 5)
    } else {
      Circle()
        .fill(group.color)
        .frame(width: NotchAgentStackMetrics.listOrbSize, height: NotchAgentStackMetrics.listOrbSize)
        .overlay(
          Circle()
            .strokeBorder(Color.white.opacity(0.42), lineWidth: 0.8)
        )
        .shadow(color: group.color.opacity(0.6), radius: 5)
    }
  }

  /// Minimal thin bar shown when not hovering. The fill is the primary
  /// ambient status channel at this size: voice-response gradient wins,
  /// then the aggregate subagent color, then neutral gray.
  private func compactCircleView(agentGroup: NotchAgentStatusGroup?) -> some View {
    RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
      .fill(compactPillFill(agentGroup: agentGroup))
      .frame(width: 28, height: 6)
      .shadow(
        color: state.isVoiceResponseGlowActive ? Color.white.opacity(0.85) : .clear,
        radius: state.isVoiceResponseGlowActive ? 16 : 0,
        x: 0,
        y: 0
      )
      .shadow(
        color: state.isVoiceResponseGlowActive ? Color.white.opacity(0.45) : .clear,
        radius: state.isVoiceResponseGlowActive ? 28 : 0,
        x: 0,
        y: 0
      )
      .overlay {
        if state.isVoiceResponseGlowActive {
          RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
            .stroke(
              LinearGradient(
                colors: [
                  Color.white.opacity(0.9),
                  Color(red: 0.25, green: 0.75, blue: 1.0),
                  Color.white.opacity(0.7),
                ],
                startPoint: .leading,
                endPoint: .trailing
              ),
              lineWidth: 1.4
            )
            .padding(-2.2)
            .blur(radius: 0.25)
        }
      }
      .omiAnimation(.easeInOut(duration: 0.18), value: state.isVoiceResponseGlowActive)
  }

  private func compactPillFill(agentGroup: NotchAgentStatusGroup?) -> LinearGradient {
    if state.isVoiceResponseGlowActive {
      return LinearGradient(
        colors: [
          Color.white.opacity(0.9),
          Color(red: 0.50, green: 0.75, blue: 1.0),
          Color.white.opacity(0.7),
        ],
        startPoint: .leading,
        endPoint: .trailing
      )
    }
    if let agentGroup {
      return LinearGradient(
        colors: [
          agentGroup.color.opacity(0.85),
          agentGroup.color,
          agentGroup.color.opacity(0.85),
        ],
        startPoint: .leading,
        endPoint: .trailing
      )
    }
    return LinearGradient(
      colors: [Color.white.opacity(0.5), Color.white.opacity(0.5)],
      startPoint: .leading,
      endPoint: .trailing
    )
  }

  private func compactToggle(_ title: String, isOn: Binding<Bool>) -> some View {
    Button(action: { isOn.wrappedValue.toggle() }) {
      HStack(spacing: 3) {
        Text(title)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(.white)
        RoundedRectangle(cornerRadius: OmiChrome.badgeRadius)
          .fill(isOn.wrappedValue ? Color.white.opacity(0.3) : Color.white.opacity(0.1))
          .frame(width: 26, height: 15)
          .overlay(alignment: isOn.wrappedValue ? .trailing : .leading) {
            Circle()
              .fill(.white)
              .frame(width: 11, height: 11)
              .padding(OmiSpacing.hairline)
          }
          .omiAnimation(.easeInOut(duration: 0.15), value: isOn.wrappedValue)
      }
    }
    .buttonStyle(.plain)
  }

  private func compactButton(title: String, keys: [String], action: @escaping () -> Void) -> some View {
    Button(action: action) {
      compactLabel(title, keys: keys)
    }
    .buttonStyle(.plain)
  }

  private func compactLabel(_ title: String, keys: [String]) -> some View {
    HStack(spacing: 3) {
      Text(title)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(.white)
      ForEach(keys, id: \.self) { key in
        Text(key)
          .scaledFont(size: 9)
          .foregroundColor(.white)
          .padding(.horizontal, key.count > 1 ? 4 : 0)
          .frame(minWidth: 15, minHeight: 15)
          .background(Color.white.opacity(0.1))
          .cornerRadius(OmiChrome.stripRadius)
      }
    }
  }

  private var voiceListeningView: some View {
    HStack(spacing: 7) {
      if state.pttHintText.isEmpty {
        // Playful realtime mic waveform (replaces the old pulsing red dot)
        VoiceWaveformBars(isActive: state.isVoiceListening)
      }

      Image(systemName: "mic.fill")
        .scaledFont(size: 12, weight: .semibold)
        .foregroundColor(.white)

      if state.isVoiceLocked && state.pttHintText.isEmpty {
        Image(systemName: "lock.fill")
          .scaledFont(size: OmiType.micro, weight: .bold)
          .foregroundColor(.orange)
          .frame(width: 18, height: 18)
          .background(Color.orange.opacity(0.2))
          .cornerRadius(4)
      }
    }
  }

  private var aiInputView: some View {
    AskAIInputView(
      userInput: Binding(
        get: { state.aiInputText },
        set: { state.aiInputText = $0 }
      ),
      canClearVisibleConversation: false,
      onSend: { message in
        (window as? FloatingControlBarWindow)?
          .beginVisibleMainQuery(message, fromVoice: false, animated: true)
        onSendQuery(message)
      },
      onClearVisibleConversation: onClearVisibleConversation,
      onEscape: onEscape,
      onHeightChange: { [self] height in
        lastInputEditorHeight = height
        recomputeUnifiedInputHeight()
      }
    )
    .onChange(of: agentPills.pills.count) {
      // The agent-pills header budget depends on whether pills exist, so
      // recompute the input height when the pill list changes while the
      // input/chat view is open. Without this the budget goes stale and
      // causes clipping or extra empty space. (Cubic P2.)
      recomputeUnifiedInputHeight()
    }
    .transition(
      .asymmetric(
        insertion: .move(edge: .top).combined(with: .opacity),
        removal: .move(edge: .top).combined(with: .opacity)
      ))
  }

  /// Recompute inputViewHeight from the last known editor height and the
  /// current agent-pills presence. Called on editor height change and on
  /// pill-list change so the shared expanded surface budget never goes stale.
  private func recomputeUnifiedInputHeight() {
    // Guard against stale zero editor height: the editor has not reported
    // its size yet (or was just re-created after a surface switch), so
    // recomputing now would shrink the window and clip input/send
    // controls. Fall back to the minimum content height so the panel
    // keeps a usable size until a real height arrives. (Cubic P2.)
    let height =
      lastInputEditorHeight > 0
      ? lastInputEditorHeight
      : FloatingControlBarWindow.notchInputPanelMinimumContentHeight
    let topBand =
      (state.usesNotchIsland || state.showingAIConversation)
      ? notchChromeHeight
      : FloatingControlBarWindow.pillSurfaceTopPadding
    let statusBanner =
      showingPTTStatusBanner
      ? FloatingControlBarWindow.pttStatusBannerBudget
      : 0
    let baseHeight = topBand + statusBanner + height + FloatingControlBarWindow.notchInputPanelVerticalPadding
    let headerBudget =
      !agentPills.pills.isEmpty
      ? FloatingControlBarWindow.notchChatHeaderVerticalBudget
      : 0
    state.inputViewHeight = baseHeight + headerBudget
  }

  private var floatingChatProvider: ChatProvider? {
    FloatingControlBarManager.shared.sharedFloatingProvider
  }

  private var aiResponseView: some View {
    // Re-read derived content when viewport anchors or streamed answer tokens change.
    let _ = state.chatViewport
    let _ = state.answerStreamToken
    let provider = floatingChatProvider
    return AIResponseView(
      isLoading: Binding(
        get: { state.isAILoading },
        set: { state.isAILoading = $0 }
      ),
      currentMessage: state.currentAIMessage(from: provider),
      userInput: state.displayedQuery,
      chatHistory: state.derivedChatHistory(from: provider),
      canClearVisibleConversation: false,
      showsHeader: false,
      onClearVisibleConversation: onClearVisibleConversation,
      onEscape: onEscape,
      onOpenMainApp: {
        (window as? FloatingControlBarWindow)?.closeAIConversation()
        (NSApp.delegate as? AppDelegate)?.openMainAppWindow()
      },
      onRate: onRate,
      onShareLink: onShareLink,
      onOpenAgent: { agentID, completion in
        openAgentInChat(agentID: agentID, completion: completion)
      },
      onOpenAgentRef: { ref, completion in
        openAgentInChat(ref: ref, completion: completion)
      }
    )
    .transition(
      .asymmetric(
        insertion: .move(edge: .bottom).combined(with: .opacity),
        removal: .move(edge: .bottom).combined(with: .opacity)
      ))
  }

}

private struct NotchDockShape: Shape {
  let bottomRadius: CGFloat
  var topRadius: CGFloat = 0

  func path(in rect: CGRect) -> Path {
    let radius = min(bottomRadius, rect.height / 2)
    // Square top corners blend into a physical notch/bezel; a floating
    // surface on a non-notched display rounds them instead.
    let topR = min(topRadius, rect.height / 2)
    var path = Path()
    path.move(to: CGPoint(x: rect.minX + topR, y: rect.minY))
    path.addLine(to: CGPoint(x: rect.maxX - topR, y: rect.minY))
    path.addQuadCurve(
      to: CGPoint(x: rect.maxX, y: rect.minY + topR),
      control: CGPoint(x: rect.maxX, y: rect.minY)
    )
    path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - radius))
    path.addQuadCurve(
      to: CGPoint(x: rect.maxX - radius, y: rect.maxY),
      control: CGPoint(x: rect.maxX, y: rect.maxY)
    )
    path.addLine(to: CGPoint(x: rect.minX + radius, y: rect.maxY))
    path.addQuadCurve(
      to: CGPoint(x: rect.minX, y: rect.maxY - radius),
      control: CGPoint(x: rect.minX, y: rect.maxY)
    )
    path.addLine(to: CGPoint(x: rect.minX, y: rect.minY + topR))
    path.addQuadCurve(
      to: CGPoint(x: rect.minX + topR, y: rect.minY),
      control: CGPoint(x: rect.minX, y: rect.minY)
    )
    path.closeSubpath()
    return path
  }
}

private struct NotchLowerEdgeShape: Shape {
  let bottomRadius: CGFloat
  /// 0 = open lower-edge path (notch mode: the top blends into the bezel).
  /// > 0 = closed full-perimeter ring with rounded top corners (pill mode:
  /// the surface is a floating card, so the glow wraps all the way around).
  var topRadius: CGFloat = 0
  /// Inset from the shape bounds. Pill-mode windows have no glow outsets,
  /// so the ring is drawn slightly inside the surface to avoid clipping.
  var edgeInset: CGFloat = 0

  func path(in rect: CGRect) -> Path {
    let rect = rect.insetBy(dx: edgeInset, dy: edgeInset)
    let radius = min(max(0, bottomRadius - edgeInset), rect.height / 2)
    var path = Path()
    if topRadius > 0 {
      let topR = min(max(0, topRadius - edgeInset), rect.height / 2)
      path.move(to: CGPoint(x: rect.minX + topR, y: rect.minY))
      path.addLine(to: CGPoint(x: rect.maxX - topR, y: rect.minY))
      path.addQuadCurve(
        to: CGPoint(x: rect.maxX, y: rect.minY + topR),
        control: CGPoint(x: rect.maxX, y: rect.minY)
      )
    } else {
      path.move(to: CGPoint(x: rect.maxX, y: rect.minY + 1))
    }
    path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - radius))
    path.addQuadCurve(
      to: CGPoint(x: rect.maxX - radius, y: rect.maxY),
      control: CGPoint(x: rect.maxX, y: rect.maxY)
    )
    path.addLine(to: CGPoint(x: rect.minX + radius, y: rect.maxY))
    path.addQuadCurve(
      to: CGPoint(x: rect.minX, y: rect.maxY - radius),
      control: CGPoint(x: rect.minX, y: rect.maxY)
    )
    if topRadius > 0 {
      let topR = min(max(0, topRadius - edgeInset), rect.height / 2)
      path.addLine(to: CGPoint(x: rect.minX, y: rect.minY + topR))
      path.addQuadCurve(
        to: CGPoint(x: rect.minX + topR, y: rect.minY),
        control: CGPoint(x: rect.minX, y: rect.minY)
      )
      path.closeSubpath()
    } else {
      path.addLine(to: CGPoint(x: rect.minX, y: rect.minY + 1))
    }
    return path
  }
}

private struct NotchResponseGlowView: View {
  let bottomRadius: CGFloat
  /// See `NotchLowerEdgeShape`: 0 = notch lower-edge glow, > 0 = pill-mode
  /// full-perimeter ring with this top corner radius.
  var topRadius: CGFloat = 0
  var edgeInset: CGFloat = 0

  var body: some View {
    TimelineView(.periodic(from: .now, by: 1.0 / 24.0)) { timeline in
      let time = timeline.date.timeIntervalSinceReferenceDate
      let phase = time.truncatingRemainder(dividingBy: 2.4) / 2.4
      let sweepStart = UnitPoint(x: -0.35 + phase * 1.7, y: 0.0)
      let sweepEnd = UnitPoint(x: 0.35 + phase * 1.7, y: 1.0)
      let edge = NotchLowerEdgeShape(
        bottomRadius: bottomRadius,
        topRadius: topRadius,
        edgeInset: edgeInset
      )

      ZStack {
        edge
          .stroke(
            LinearGradient(
              colors: [
                Color.white.opacity(1.0),
                Color(red: 0.72, green: 0.88, blue: 1.0).opacity(1.0),
                Color(red: 0.88, green: 0.95, blue: 1.0).opacity(1.0),
                Color.white.opacity(1.0),
              ],
              startPoint: .leading,
              endPoint: .trailing
            ),
            style: StrokeStyle(lineWidth: 3.2, lineCap: .round, lineJoin: .round)
          )

        edge
          .stroke(
            LinearGradient(
              stops: [
                .init(color: .clear, location: 0.0),
                .init(color: Color.white.opacity(0.55), location: 0.28),
                .init(color: Color(red: 0.22, green: 0.88, blue: 1.0).opacity(1.0), location: 0.45),
                .init(color: Color.white.opacity(1.0), location: 0.53),
                .init(color: Color(red: 1.0, green: 0.96, blue: 0.92).opacity(0.95), location: 0.70),
                .init(color: .clear, location: 1.0),
              ],
              startPoint: sweepStart,
              endPoint: sweepEnd
            ),
            style: StrokeStyle(lineWidth: 4.8, lineCap: .round, lineJoin: .round)
          )
      }
    }
    .allowsHitTesting(false)
  }
}

private struct NotchOmiMark: View {
  var dotColors: [Color] = []

  private static let dotCount = 8
  private static let dotDiameterRatio: CGFloat = 0.18
  private static let ringRadiusRatio: CGFloat = 0.33

  var body: some View {
    GeometryReader { geometry in
      let size = min(geometry.size.width, geometry.size.height)
      let center = CGPoint(
        x: geometry.size.width / 2,
        y: geometry.size.height / 2
      )
      let dotDiameter = size * Self.dotDiameterRatio
      let ringRadius = size * Self.ringRadiusRatio

      ZStack {
        ForEach(0..<Self.dotCount, id: \.self) { index in
          let angle = Double(index) / Double(Self.dotCount) * Double.pi * 2 - Double.pi
          Circle()
            .fill(dotColors.indices.contains(index) ? dotColors[index] : Color.white.opacity(0.96))
            .frame(width: dotDiameter, height: dotDiameter)
            .position(
              x: center.x + CGFloat(cos(angle)) * ringRadius,
              y: center.y + CGFloat(sin(angle)) * ringRadius
            )
        }
      }
    }
    .drawingGroup(opaque: false, colorMode: .linear)
    .accessibilityHidden(true)
  }
}

/// The Omi mark rendered as a spinning "thinking" indicator. The ring's dots
/// carry a brightness trail (bright head → faint tail) so the continuous
/// rotation reads as a sweeping comet rather than a static ring of dots.
private struct NotchThinkingMark: View {
  var body: some View {
    OmiThinkingMark()
  }
}

private struct SubagentChatPointer: Shape {
  func path(in rect: CGRect) -> Path {
    var path = Path()
    path.move(to: CGPoint(x: rect.midX, y: rect.minY))
    path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
    path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
    path.closeSubpath()
    return path
  }
}

private struct AgentMainChatView: View {
  @EnvironmentObject var state: FloatingControlBarState
  @ObservedObject var pill: AgentPill
  @ObservedObject var manager: AgentPillsManager
  let onBackToAgentRows: () -> Void
  let onEscape: () -> Void

  init(
    pill: AgentPill,
    manager: AgentPillsManager,
    onBackToAgentRows: @escaping () -> Void,
    onEscape: @escaping () -> Void
  ) {
    self.pill = pill
    self.manager = manager
    self.onBackToAgentRows = onBackToAgentRows
    self.onEscape = onEscape
  }

  private var isRunning: Bool {
    guard !hasFinalAssistantOutput else { return false }
    switch pill.status {
    case .queued, .starting, .running:
      return true
    case .done, .stopped, .failed:
      return false
    }
  }

  private var displayedMessages: [ChatMessage] {
    if !pill.conversationMessages.isEmpty {
      return normalizedAgentMessages(pill.conversationMessages)
    }
    var fallback = [ChatMessage(id: "\(pill.id.uuidString)-query", text: pill.query, sender: .user)]
    if let message = pill.aiMessage {
      let text = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
      if !text.isEmpty || !message.contentBlocks.isEmpty {
        fallback.append(message)
      }
    }
    return normalizedAgentMessages(fallback)
  }

  private var hasAssistantTurn: Bool {
    displayedMessages.contains { $0.sender == .ai }
  }

  private var hasFinalAssistantOutput: Bool {
    displayedMessages.contains { message in
      message.sender == .ai
        && !message.isStreaming
        && hasVisibleAssistantContent(message)
    }
  }

  private var activityText: String {
    pill.latestActivity.trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private var scrollContentToken: AnyHashable {
    AnyHashable(
      [
        String(pill.contentRevision),
        pill.latestActivity,
        displayedMessages.map { message in
          [
            message.id,
            message.text,
            String(message.contentBlocks.count),
            String(message.displayResources.count),
            String(message.isStreaming),
          ].joined(separator: "\u{1F}")
        }.joined(separator: "\u{1E}"),
      ].joined(separator: "\u{1D}")
    )
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      header

      ChatScrollContainer(
        bottomAnchorId: "agentBottom",
        contentChangeToken: scrollContentToken,
        scrollPaddingTrailing: 30,
        onContentHeightChange: { height in
          state.reportContentHeight(height, for: .agent(pill.id))
        }
      ) {
        conversationContent
          .id(pill.contentRevision)
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)

      followUpInput
    }
    .padding()
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .onAppear {
      manager.markViewed(pillID: pill.id)
    }
    .onExitCommand {
      onEscape()
    }
  }

  private var header: some View {
    HStack(spacing: OmiSpacing.sm) {
      Button(action: onBackToAgentRows) {
        Image(systemName: "chevron.left")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(.white.opacity(0.82))
          .frame(width: 36, height: 36)
          .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help("Back to chats")

      Text(pill.title)
        .scaledFont(size: OmiType.body, weight: .bold)
        .foregroundColor(.white)
        .lineLimit(1)

      Spacer(minLength: 8)

      statusBadge
    }
  }

  private var statusBadge: some View {
    HStack(spacing: OmiSpacing.xs) {
      Group {
        if displayStatus.isFinished {
          Button {
            manager.dismiss(pillID: pill.id)
            onBackToAgentRows()
          } label: {
            statusBadgeLabel
          }
          .buttonStyle(.plain)
          .help("Dismiss agent")
        } else {
          statusBadgeLabel
        }
      }

      if isRunning {
        stopButton
      }
    }
  }

  private var stopButton: some View {
    Button {
      manager.stop(pillID: pill.id)
    } label: {
      Image(systemName: "stop.fill")
        .scaledFont(size: 8, weight: .bold)
        .foregroundColor(.black.opacity(0.82))
        .frame(width: 22, height: 22)
        .background(pill.status.tintColor)
        .clipShape(Circle())
    }
    .buttonStyle(.plain)
    .accessibilityLabel("Stop subagent")
    .help("Stop subagent")
  }

  private var statusBadgeLabel: some View {
    Text(displayStatus.displayLabel)
      .scaledFont(size: 9, weight: .bold)
      .foregroundColor(statusForeground)
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xxs)
      .background(displayStatus.tintColor.opacity(statusBackgroundOpacity))
      .clipShape(Capsule())
  }

  private var displayStatus: AgentPill.Status {
    if hasFinalAssistantOutput, !pill.status.isFinished {
      return .done
    }
    return pill.status
  }

  private var statusForeground: Color {
    switch displayStatus {
    case .queued, .starting, .running, .done:
      return .black.opacity(0.86)
    case .stopped:
      return .black.opacity(0.78)
    case .failed:
      return .white
    }
  }

  private var statusBackgroundOpacity: Double {
    switch displayStatus {
    case .queued, .starting, .running, .done, .stopped:
      return 1
    case .failed:
      return 0.75
    }
  }

  @ViewBuilder
  private var conversationContent: some View {
    VStack(alignment: .leading, spacing: 14) {
      ForEach(displayedMessages) { message in
        agentMessageBubble(message)
      }

      if isRunning && !hasAssistantTurn {
        runningActivityView
      }
    }
  }

  private func normalizedAgentMessages(_ messages: [ChatMessage]) -> [ChatMessage] {
    let hasFinalOutput = messages.contains { message in
      message.sender == .ai
        && !message.isStreaming
        && hasVisibleAssistantContent(message)
    }
    guard hasFinalOutput else { return messages }
    return messages.filter { message in
      !(message.sender == .ai
        && message.isStreaming
        && !hasVisibleAssistantContent(message))
    }
  }

  private func hasVisibleAssistantContent(_ message: ChatMessage) -> Bool {
    !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      || !message.contentBlocks.isEmpty
      || !message.displayResources.isEmpty
  }

  private var runningActivityView: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      TypingIndicator()
        .frame(maxWidth: .infinity, minHeight: 24, alignment: .leading)
      if !activityText.isEmpty {
        Text(activityText)
          .scaledFont(size: 12, weight: .semibold)
          .foregroundColor(.white.opacity(0.62))
          .textSelection(.enabled)
      }
    }
  }

  @ViewBuilder
  private func agentMessageBubble(_ message: ChatMessage) -> some View {
    let trimmed = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
    if message.sender == .user {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        if !trimmed.isEmpty {
          Text(trimmed)
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(.white)
            .textSelection(.enabled)
            .lineLimit(nil)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        agentResourceStrip(message)
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, 9)
      .background(Color.white.opacity(0.10))
      .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
      .contextMenu {
        Button("Copy") {
          NSPasteboard.general.clearContents()
          NSPasteboard.general.setString(message.copyableText, forType: .string)
        }
      }
    } else if trimmed.isEmpty && message.isStreaming && message.displayResources.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        TypingIndicator()
          .frame(maxWidth: .infinity, minHeight: 24, alignment: .leading)
        if !activityText.isEmpty {
          Text(activityText)
            .scaledFont(size: 12, weight: .semibold)
            .foregroundColor(.white.opacity(0.62))
            .textSelection(.enabled)
        }
      }
    } else {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        agentAssistantContent(message)
        agentResourceStrip(message)
      }
      .padding(.horizontal, OmiSpacing.xxs)
      .contextMenu {
        Button("Copy") {
          NSPasteboard.general.clearContents()
          NSPasteboard.general.setString(message.copyableText, forType: .string)
        }
      }
    }
  }

  @ViewBuilder
  private func agentResourceStrip(_ message: ChatMessage) -> some View {
    if !message.displayResources.isEmpty {
      ChatResourceStrip(
        resources: message.displayResources,
        density: .compact,
        alignment: .leading
      )
      .environment(\.colorScheme, .dark)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  @ViewBuilder
  private func agentAssistantContent(_ message: ChatMessage) -> some View {
    if !message.contentBlocks.isEmpty {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        ForEach(groupedContentBlocks(for: message)) { group in
          switch group {
          case .text(_, let text):
            if !text.isEmpty {
              SelectableMarkdown(text: text, sender: .ai)
                .environment(\.colorScheme, .dark)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
          case .toolCalls(_, let calls):
            ToolCallsGroup(calls: calls, compact: true)
              .frame(maxWidth: .infinity, alignment: .leading)
          case .thinking(_, let text):
            ThinkingBlock(text: text)
              .frame(maxWidth: .infinity, alignment: .leading)
          case .discoveryCard(_, let title, let summary, let fullText):
            DiscoveryCard(title: title, summary: summary, fullText: fullText)
              .frame(maxWidth: .infinity, alignment: .leading)
          // Rich controls are main-chat-only; floating/notch stays passive.
          case .questionCard, .taskCard, .goalLink, .captureLink:
            EmptyView()
          case .agentSpawn(
            _, let pillId, let sessionId, let runId, let title, let objective, let provider
          ):
            AgentSpawnCard(
              title: title,
              objective: objective,
              provider: provider,
              ref: AgentTimelineRef(pillId: pillId, sessionId: sessionId, runId: runId),
              onOpen: nil
            )
            .frame(maxWidth: .infinity, alignment: .leading)
          case .agentCompletion(
            _, let pillId, let sessionId, let runId, let title, let promptSnippet, let output,
            let status
          ):
            AgentCompletionCard(
              title: title,
              promptSnippet: promptSnippet,
              output: output,
              status: status,
              ref: AgentTimelineRef(pillId: pillId, sessionId: sessionId, runId: runId),
              onOpen: nil
            )
            .frame(maxWidth: .infinity, alignment: .leading)
          }
        }
      }
    } else {
      let trimmed = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
      if !trimmed.isEmpty {
        Markdown(trimmed)
          .markdownTheme(.aiMessage(scale: 0.88))
          .textSelection(.enabled)
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: .infinity, alignment: .leading)
      }
    }
  }

  private func groupedContentBlocks(for message: ChatMessage) -> [ContentBlockGroup] {
    ContentBlockGroup.visibleChatGroups(
      message.contentBlocks,
      isStreaming: message.isStreaming
    )
  }

  private var followUpInput: some View {
    HStack(spacing: OmiSpacing.xs) {
      Button {
        onEscape()
        (NSApp.delegate as? AppDelegate)?.openMainAppWindow()
      } label: {
        HStack(spacing: OmiSpacing.xs) {
          Text("Continue in Omi")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(.white.opacity(0.85))
          Spacer(minLength: 0)
          Image(systemName: "arrow.up.forward.app")
            .scaledFont(size: OmiType.body)
            .foregroundColor(.secondary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(Color.white.opacity(0.10))
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous))
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .help("Open the Omi app to steer this agent")
    }
  }
}

/// Re-renders when any individual pill's @Published status changes — the
/// manager only publishes on pill add/remove, so per-pill observers are needed
/// for live status color updates (same pattern as NotchAgentPillsRowView).
private struct PillStatusObservingView<Content: View>: View {
  @ObservedObject var manager: AgentPillsManager
  @ViewBuilder let content: ([AgentPill]) -> Content
  @State private var pillStatusCancellables: [UUID: AnyCancellable] = [:]
  @State private var pillStatusChangeToken = 0

  var body: some View {
    let _ = pillStatusChangeToken
    content(NotchAgentStackMetrics.sortedPills(manager.pills))
      .onAppear { syncPillStatusObservers() }
      .onChange(of: manager.pills.map(\.id)) { _, _ in
        syncPillStatusObservers()
      }
  }

  private func syncPillStatusObservers() {
    let currentIDs = Set(manager.pills.map(\.id))
    pillStatusCancellables = pillStatusCancellables.filter { currentIDs.contains($0.key) }
    for pill in manager.pills where pillStatusCancellables[pill.id] == nil {
      pillStatusCancellables[pill.id] = pill.objectWillChange
        .receive(on: DispatchQueue.main)
        .sink { _ in
          pillStatusChangeToken &+= 1
        }
    }
  }
}

/// Aggregate agent-status glow on the collapsed pill — the pill itself glows
/// in the highest-priority status color (failed > running > queued > done >
/// stopped), breathing while agents are active, mirroring the PTT voice glow.
private struct AgentStatusGlow: ViewModifier {
  let group: NotchAgentStatusGroup?
  @State private var breathing = false

  private var isAnimated: Bool { group == .running || group == .queued }
  private var glowColor: Color { group?.color ?? .clear }

  func body(content: Content) -> some View {
    let pulse = isAnimated && breathing
    content
      .shadow(
        color: group == nil ? .clear : glowColor.opacity(pulse ? 0.95 : 0.6),
        radius: group == nil ? 0 : (pulse ? 15 : 9)
      )
      .shadow(
        color: group == nil ? .clear : glowColor.opacity(pulse ? 0.5 : 0.3),
        radius: group == nil ? 0 : (pulse ? 26 : 16)
      )
      .omiAnimation(
        isAnimated
          ? .easeInOut(duration: 1.15).repeatForever(autoreverses: true)
          : .easeInOut(duration: 0.25),
        value: breathing
      )
      .onAppear { breathing = true }
      .onChange(of: isAnimated) { _, _ in
        // Restart the repeat-forever animation when the aggregate
        // state flips between animated and static groups.
        breathing = false
        DispatchQueue.main.async { breathing = true }
      }
      .accessibilityLabel(group.map { "Subagents: \($0.title)" } ?? "")
  }
}

private struct NotchAgentPillsRowView: View {
  @ObservedObject var manager: AgentPillsManager
  weak var barWindow: NSWindow?
  @State private var pillStatusCancellables: [UUID: AnyCancellable] = [:]
  @State private var pillStatusChangeToken = 0

  private var stackedPills: [AgentPill] {
    NotchAgentStackMetrics.sortedPills(manager.pills)
  }

  var body: some View {
    let _ = pillStatusChangeToken
    NotchAgentOmiIndicatorView(pills: stackedPills)
      .frame(width: 21, height: 21)
      .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
      .accessibilityLabel("Subagent status")
      .accessibilityHint("Hover to fan out subagents, click to keep them open")
      .onAppear { syncPillStatusObservers() }
      .onChange(of: manager.pills.map(\.id)) { _, _ in
        syncPillStatusObservers()
      }
  }

  private func syncPillStatusObservers() {
    let currentIDs = Set(manager.pills.map(\.id))
    pillStatusCancellables = pillStatusCancellables.filter { currentIDs.contains($0.key) }
    for pill in manager.pills where pillStatusCancellables[pill.id] == nil {
      pillStatusCancellables[pill.id] = pill.objectWillChange
        .receive(on: DispatchQueue.main)
        .sink { _ in
          pillStatusChangeToken &+= 1
        }
    }
  }
}

@MainActor
private enum NotchAgentStackMetrics {
  static let maxAgents = FloatingControlBarWindow.notchAgentListMaxVisibleAgents
  static let listOrbSize: CGFloat = 11
  static let listHorizontalInset: CGFloat = 12
  static let listRowLeadingPadding: CGFloat = 12
  static let listOrbSlotWidth: CGFloat = 24
  static let logoFrameSize: CGFloat = 21
  static let logoTrailingInset: CGFloat = 2
  static let logoDotDiameterRatio: CGFloat = 0.18
  static let logoRingRadiusRatio: CGFloat = 0.33

  static func sortedPills(_ pills: [AgentPill]) -> [AgentPill] {
    let newestIndex = Dictionary(
      lastWriteWins: pills.enumerated().map {
        ($0.element.id, pills.count - 1 - $0.offset)
      })
    return pills.sorted { lhs, rhs in
      let lhsGroup = NotchAgentStatusGroup(status: lhs.status)
      let rhsGroup = NotchAgentStatusGroup(status: rhs.status)
      if lhsGroup.sortRank != rhsGroup.sortRank {
        return lhsGroup.sortRank < rhsGroup.sortRank
      }
      return (newestIndex[lhs.id] ?? 0) < (newestIndex[rhs.id] ?? 0)
    }
  }

  static func logoCenterX(
    rowWidth: CGFloat,
    notchHiddenCenterWidth: CGFloat,
    notchSideWidth: CGFloat
  ) -> CGFloat {
    let chromeWidth = notchHiddenCenterWidth + notchSideWidth * 2
    let chromeMinX = (rowWidth - chromeWidth) / 2
    return chromeMinX + notchSideWidth - logoTrailingInset - logoFrameSize / 2
  }

  static func logoDotSourceOffset(for index: Int) -> CGSize {
    let angle = Double(index) / Double(maxAgents) * Double.pi * 2 - Double.pi
    let ringRadius = logoFrameSize * logoRingRadiusRatio
    return CGSize(
      width: CGFloat(cos(angle)) * ringRadius,
      height: CGFloat(sin(angle)) * ringRadius
    )
  }

  static func smoothStep(_ value: CGFloat) -> CGFloat {
    let t = min(1, max(0, value))
    return t * t * (3 - 2 * t)
  }

  static func quadraticBezier(from start: CGPoint, control: CGPoint, to end: CGPoint, progress: CGFloat) -> CGPoint {
    let t = smoothStep(progress)
    let inverse = 1 - t
    return CGPoint(
      x: inverse * inverse * start.x + 2 * inverse * t * control.x + t * t * end.x,
      y: inverse * inverse * start.y + 2 * inverse * t * control.y + t * t * end.y
    )
  }

  /// The expanded-row identity mark uses the full orb size. The fixed header
  /// owns the compact Omi ring independently.
  static let logoDotScale: CGFloat = (logoFrameSize * logoDotDiameterRatio) / listOrbSize
}

private struct NotchAgentOmiIndicatorView: View {
  let pills: [AgentPill]

  private var visiblePills: [AgentPill] {
    Array(pills.prefix(NotchAgentStackMetrics.maxAgents))
  }

  var body: some View {
    NotchOmiMark(dotColors: visiblePills.map { NotchAgentStatusGroup(status: $0.status).color })
      .contentShape(Rectangle())
  }
}

/// The expanded agent rows live below the fixed notch header. Their status marks
/// fade into their row slots, while the Omi logo and settings remain anchored in
/// the compact header above.
private struct NotchAgentMorphField: View {
  @ObservedObject var manager: AgentPillsManager
  let activePillID: UUID?
  let progress: CGFloat
  let notchHiddenCenterWidth: CGFloat
  let notchSideWidth: CGFloat
  let notchChromeHeight: CGFloat
  let rowTopOffset: CGFloat
  let onSelect: (AgentPill) -> Void
  @State private var pillStatusCancellables: [UUID: AnyCancellable] = [:]
  @State private var pillStatusChangeToken = 0

  private var sortedPills: [AgentPill] {
    let _ = pillStatusChangeToken
    return Array(NotchAgentStackMetrics.sortedPills(manager.pills).prefix(NotchAgentStackMetrics.maxAgents))
  }

  var body: some View {
    GeometryReader { geometry in
      let width = geometry.size.width
      let chromeHeight = notchChromeHeight
      let rowHeight = FloatingControlBarWindow.notchAgentListRowHeight
      let rowSpacing = FloatingControlBarWindow.notchAgentListRowSpacing
      let verticalPadding = FloatingControlBarWindow.notchAgentListVerticalPadding
      let rowWidth = max(
        0,
        min(
          width - NotchAgentStackMetrics.listHorizontalInset * 2,
          FloatingControlBarWindow.notchExpandedWidth - NotchAgentStackMetrics.listHorizontalInset * 2))
      let rowMinX = (width - rowWidth) / 2
      let rowRevealProgress = NotchAgentStackMetrics.smoothStep((progress - 0.38) / 0.62)
      let pills = sortedPills

      ZStack {
        ForEach(Array(pills.enumerated()), id: \.offset) { index, pill in
          let rowMinY = chromeHeight + rowTopOffset + verticalPadding + CGFloat(index) * (rowHeight + rowSpacing)
          let rowCenter = CGPoint(x: width / 2, y: rowMinY + rowHeight / 2)
          let orbCenter = CGPoint(
            x: rowMinX + NotchAgentStackMetrics.listRowLeadingPadding + NotchAgentStackMetrics.listOrbSize / 2,
            y: rowCenter.y
          )
          let group = NotchAgentStatusGroup(status: pill.status)

          Button {
            onSelect(pill)
          } label: {
            NotchAgentListRow(
              title: pill.title,
              status: pill.status,
              activity: ChatContinuityInvariants.agentPreviewText(
                prompt: pill.query,
                output: pill.latestActivity
              ),
              isSelected: pill.id == activePillID,
              progress: rowRevealProgress
            )
            .frame(width: rowWidth, height: rowHeight)
          }
          .buttonStyle(.plain)
          .frame(width: rowWidth, height: rowHeight)
          .opacity(rowRevealProgress)
          .allowsHitTesting(progress > 0.6)
          .position(rowCenter)
          .help(pill.title)

          notchAgentIdentityMark(
            provider: pill.providerIdentity,
            color: group.color,
            isActive: pill.id == activePillID,
            progress: 1
          )
          .opacity(rowRevealProgress)
          .position(orbCenter)
          .allowsHitTesting(false)
        }
      }
      .frame(width: width, height: geometry.size.height, alignment: .top)
    }
    .onAppear { syncPillStatusObservers() }
    .onChange(of: manager.pills.map(\.id)) { _, _ in syncPillStatusObservers() }
  }

  private func syncPillStatusObservers() {
    let currentIDs = Set(manager.pills.map(\.id))
    pillStatusCancellables = pillStatusCancellables.filter { currentIDs.contains($0.key) }
    for pill in manager.pills where pillStatusCancellables[pill.id] == nil {
      pillStatusCancellables[pill.id] = pill.objectWillChange
        .receive(on: DispatchQueue.main)
        .sink { _ in
          pillStatusChangeToken &+= 1
        }
    }
  }

  @ViewBuilder
  private func notchAgentIdentityMark(
    provider: AgentHarnessMode?,
    color: Color,
    isActive: Bool,
    progress: CGFloat
  ) -> some View {
    if provider.rendersProviderMark {
      let scale = NotchAgentStackMetrics.logoDotScale + (1 - NotchAgentStackMetrics.logoDotScale) * progress
      AgentProviderLogoMark(provider: provider, statusColor: color, size: NotchAgentStackMetrics.listOrbSize + 5)
        .shadow(color: color.opacity(0.55), radius: isActive ? 9 : 5)
        .scaleEffect(scale)
        .frame(width: 18, height: 22)
    } else {
      NotchMorphDot(
        color: color,
        isActive: isActive,
        progress: progress
      )
    }
  }
}

/// A single dot that looks like a logo-ring dot at progress 0 (small, no stroke)
/// and a fanned status orb at progress 1 (full size, ringed).
private struct NotchMorphDot: View {
  let color: Color
  let isActive: Bool
  let progress: CGFloat

  var body: some View {
    let scale = NotchAgentStackMetrics.logoDotScale + (1 - NotchAgentStackMetrics.logoDotScale) * progress
    Circle()
      .fill(color)
      .frame(width: NotchAgentStackMetrics.listOrbSize, height: NotchAgentStackMetrics.listOrbSize)
      .overlay(
        Circle()
          .strokeBorder(Color.white.opacity(0.42 * Double(progress)), lineWidth: 0.8)
      )
      .shadow(color: color.opacity(0.6), radius: isActive ? 9 : 5)
      .scaleEffect(scale)
      .frame(width: 18, height: 22)
      .contentShape(Circle())
  }
}

private struct NotchLogoPlaceholderDot: View {
  let progress: CGFloat

  var body: some View {
    Circle()
      .fill(Color.white.opacity(0.96 * Double(1 - progress)))
      .frame(width: NotchAgentStackMetrics.listOrbSize, height: NotchAgentStackMetrics.listOrbSize)
      .scaleEffect(NotchAgentStackMetrics.logoDotScale)
      .frame(width: 18, height: 22)
  }
}

private struct NotchAgentListRow: View {
  let title: String
  let status: AgentPill.Status
  let activity: String
  let isSelected: Bool
  let progress: CGFloat

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      // The identity mark (Omi dot or provider logo) is rendered by the
      // traveling `notchAgentIdentityMark` that morphs from the collapsed
      // logo ring and lands on this slot. The row only reserves the space —
      // drawing a logo here too would double it up under the morph mark.
      Color.clear
        .frame(width: NotchAgentStackMetrics.listOrbSlotWidth, height: 18)

      VStack(alignment: .leading, spacing: 1) {
        Text(title)
          .scaledFont(size: 12, weight: .semibold)
          .foregroundStyle(.white.opacity(0.94))
          .lineLimit(1)
          .truncationMode(.tail)

        HStack(spacing: OmiSpacing.xxs) {
          Image(systemName: activityIcon)
            .font(.system(size: 8, weight: .bold))
            .foregroundStyle(statusColor.opacity(0.95))
            .frame(width: 9, height: 9)

          Text(progressSummary)
            .scaledFont(size: 9, weight: .medium)
            .foregroundStyle(.white.opacity(0.52))
            .lineLimit(1)
            .truncationMode(.tail)
        }
      }
      .opacity(progress)

      Spacer(minLength: 0)
    }
    .padding(.leading, NotchAgentStackMetrics.listRowLeadingPadding)
    .padding(.trailing, 10)
    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius, style: .continuous)
        .fill(isSelected ? Color.white.opacity(0.12 * Double(progress)) : .clear)
    )
    .overlay(alignment: .bottom) {
      Rectangle()
        .fill(Color.white.opacity(0.11 * Double(progress)))
        .frame(height: 0.6)
    }
    .contentShape(Rectangle())
  }

  private var progressSummary: String {
    let trimmed = activity.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty || trimmed == status.displayLabel {
      return status.displayLabel
    }
    if trimmed.lowercased().hasPrefix(status.displayLabel.lowercased()) {
      return trimmed
    }
    return "\(status.displayLabel) — \(trimmed)"
  }

  private var statusColor: Color {
    status.tintColor
  }

  private var activityIcon: String {
    switch status {
    case .queued:
      return "clock"
    case .starting, .running:
      return "sparkles"
    case .done:
      return "checkmark"
    case .stopped:
      return "stop.fill"
    case .failed:
      return "exclamationmark"
    }
  }
}

private enum NotchAgentStatusGroup: String, Identifiable {
  case running
  case queued
  case failed
  case stopped
  case done

  var id: String { rawValue }

  init(status: AgentPill.Status) {
    switch status {
    case .starting, .running:
      self = .running
    case .queued:
      self = .queued
    case .failed:
      self = .failed
    case .stopped:
      self = .stopped
    case .done:
      self = .done
    }
  }

  var title: String {
    switch self {
    case .running: return "Running"
    case .queued: return "Queued"
    case .failed: return "Failed"
    case .stopped: return "Stopped"
    case .done: return "Done"
    }
  }

  var color: Color {
    switch self {
    case .running: return Color(red: 1.0, green: 0.80, blue: 0.40)
    case .queued: return Color(red: 0.20, green: 0.86, blue: 1.0)
    case .failed: return Color(red: 1.0, green: 0.42, blue: 0.42)
    case .stopped: return Color(red: 0.64, green: 0.66, blue: 0.70)
    case .done: return Color(red: 0.27, green: 0.92, blue: 0.46)
    }
  }

  var highlightColor: Color {
    switch self {
    case .running: return Color(red: 1.0, green: 0.62, blue: 0.20)
    case .queued: return Color(red: 0.08, green: 0.52, blue: 1.0)
    case .failed: return Color(red: 1.0, green: 0.46, blue: 0.12)
    case .stopped: return Color(red: 0.42, green: 0.44, blue: 0.48)
    case .done: return Color(red: 0.08, green: 0.78, blue: 0.62)
    }
  }

  var shadowColor: Color {
    switch self {
    case .running: return Color(red: 0.72, green: 0.36, blue: 0.04)
    case .queued: return Color(red: 0.00, green: 0.44, blue: 0.95)
    case .failed: return Color(red: 0.78, green: 0.08, blue: 0.18)
    case .stopped: return Color(red: 0.24, green: 0.25, blue: 0.28)
    case .done: return Color(red: 0.02, green: 0.50, blue: 0.24)
    }
  }

  var sortRank: Int {
    switch self {
    case .running: return 0
    case .queued: return 1
    case .failed: return 2
    case .stopped: return 3
    case .done: return 4
    }
  }

  /// Highest-priority aggregate across all pills, for the collapsed-pill
  /// tint/glow: failure needs the user, activity is ambient. Finished
  /// agents the user has already viewed go quiet — done work should stop
  /// tugging at the eye.
  @MainActor
  static func aggregate(for pills: [AgentPill]) -> NotchAgentStatusGroup? {
    let groups =
      pills
      .filter { !($0.status.isFinished && $0.viewedAt != nil) }
      .map { NotchAgentStatusGroup(status: $0.status) }
    for candidate: NotchAgentStatusGroup in [.failed, .running, .queued, .done, .stopped]
    where groups.contains(candidate) {
      return candidate
    }
    return groups.first
  }

}

private struct NotchAgentStatusOrb: View {
  let group: NotchAgentStatusGroup
  let isActive: Bool
  var size: CGFloat = 16

  var body: some View {
    Circle()
      .fill(group.color)
      .overlay(
        Circle()
          .stroke(Color.white.opacity(isActive ? 0.34 : 0.20), lineWidth: 1)
      )
      .frame(width: size, height: size)
      .frame(width: size + 6, height: size + 6)
  }
}
