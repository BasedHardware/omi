import Cocoa
import Combine
import SwiftUI
import OmiTheme

private final class FloatingBarHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        true
    }
}

private final class FloatingBarContainerView: NSView {
    weak var controlBarWindow: FloatingControlBarWindow?

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach(removeTrackingArea)
        addTrackingArea(NSTrackingArea(
            rect: bounds,
            options: [.mouseEnteredAndExited, .mouseMoved, .activeAlways, .inVisibleRect],
            owner: self,
            userInfo: nil
        ))
    }

    override func mouseEntered(with event: NSEvent) {
        controlBarWindow?.updateNotchPointer(from: event)
    }

    override func mouseMoved(with event: NSEvent) {
        controlBarWindow?.updateNotchPointer(from: event)
    }

    override func mouseExited(with event: NSEvent) {
        controlBarWindow?.updateNotchPointerFromGlobalMouse()
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        guard controlBarWindow?.acceptsMouseHit(inContentPoint: point) ?? true else {
            return nil
        }
        return super.hitTest(point)
    }
}

private extension Duration {
    var millisecondsString: String {
        let components = self.components
        let milliseconds = Double(components.seconds) * 1000
            + Double(components.attoseconds) / 1_000_000_000_000_000
        return String(format: "%.1f", milliseconds)
    }
}

/// NSPanel subclass for the floating control bar.
///
/// Using a non-activating panel lets the Ask Omi shortcut focus the floating bar
/// without surfacing the main Omi window when the app is already running.
class FloatingControlBarWindow: NSPanel, NSWindowDelegate {
    private static let positionKey = "FloatingControlBarPosition"
    private static let sizeKey = "FloatingControlBarSize"
    private static let defaultSize = NSSize(width: 40, height: 14)
    private static let minBarSize = NSSize(width: 40, height: 14)
    /// Fallback physical notch dead zone. Prefer `notchHiddenCenterWidth(for:)`,
    /// which reads macOS' actual top auxiliary areas for the current screen.
    static let fallbackNotchHiddenCenterWidth: CGFloat = 172
    static let notchHiddenCenterSafetyPadding: CGFloat = 34
    static var notchHiddenCenterWidth: CGFloat {
        fallbackNotchHiddenCenterWidth + notchHiddenCenterSafetyPadding
    }
    static let notchCompactSideWidth: CGFloat = 30
    static let notchActiveSideWidth: CGFloat = 42
    /// Thinking keeps the compact active lobe width: the visible state is the
    /// spinning Omi mark only, without a right-side text label.
    static let notchThinkingSideWidth: CGFloat = notchActiveSideWidth
    static let defaultNotchChromeHeight: CGFloat = 34
    static var notchChromeHeight: CGFloat { defaultNotchChromeHeight }
    static let notchActivationHeight: CGFloat = 17
    static let notchGlowOutsetX: CGFloat = 24
    static let notchGlowOutsetBottom: CGFloat = 24
    static let notchConversationBottomPadding: CGFloat = 18
    static let notchInputPanelVerticalPadding: CGFloat = 46
    static let notchInputPanelMinimumContentHeight: CGFloat = 40
    /// Extra vertical budget added on top of the input editor when notch mode
    /// renders the "Back / Omi Chat" header above the input (agent pills present).
    /// Header row (32pt) + VStack top padding (8) + spacing (8) = 48pt.
    static let notchChatHeaderVerticalBudget: CGFloat = 48
    static let notchAgentListMaxVisibleAgents = 8
    static let notchAgentListRowHeight: CGFloat = 44
    static let notchAgentListRowSpacing: CGFloat = 0
    static let notchAgentListVerticalPadding: CGFloat = 0
    static let notchAgentListBottomMargin: CGFloat = 8
    static let notchHoverMenuBottomMargin: CGFloat = 8
    private static let responseStreamingResizeStep: CGFloat = 56
    private static let legacyPillGlowOutsetX: CGFloat = 22
    private static let legacyPillGlowOutsetY: CGFloat = 18
    static func notchAgentListHeight(agentCount: Int) -> CGFloat {
        let visibleCount = min(max(0, agentCount), notchAgentListMaxVisibleAgents)
        guard visibleCount > 0 else { return 0 }
        return notchAgentListVerticalPadding * 2
            + CGFloat(visibleCount) * notchAgentListRowHeight
            + CGFloat(max(0, visibleCount - 1)) * notchAgentListRowSpacing
            + notchAgentListBottomMargin
    }
    static func notchHoverMenuHeight(agentCount: Int) -> CGFloat {
        notchAgentListRowHeight
            + notchAgentListHeight(agentCount: agentCount)
            + notchHoverMenuBottomMargin
    }
    static let expandedBarSize = NSSize(width: 210, height: 50)
    /// Center gap between the two chrome lobes on displays without a notch —
    /// there is no camera housing to straddle, so keep a small deliberate gap
    /// instead of the phantom notch dead zone.
    static let pillSurfaceCenterGapWidth: CGFloat = 56
    /// Slim top inset that replaces the notch chrome band on the pill's
    /// expanded surfaces (agent list, chat).
    static let pillSurfaceTopPadding: CGFloat = 10
    /// Pill-mode Ask Omi input panel height (top inset + editor + padding).
    static var pillInputPanelHeight: CGFloat {
        pillSurfaceTopPadding + notchInputPanelMinimumContentHeight + notchInputPanelVerticalPadding
    }
    private static let voiceBarSize = NSSize(width: 224, height: 42)
    /// Readable status strip under chrome/pill for too-short PTT / mic errors.
    static let pttHintRowHeight: CGFloat = 30
    private static let maxBarSize = NSSize(width: 1200, height: 1000)
    static let notchExpandedWidth: CGFloat = 382
    private static let notificationWidth: CGFloat = 430
    private static let notificationHeight: CGFloat = 108
    private static let notificationSpacing: CGFloat = 8
    /// Vertical room for the readable PTT status banner under chrome/pill.
    static var pttStatusBannerBudget: CGFloat { notificationSpacing + pttHintRowHeight }
    private static let askOmiAnimationDuration: TimeInterval = 0.14
    private static let askOmiSettleDelay: TimeInterval = 0.16
    /// Hover-menu (agent switcher) motion.
    ///
    /// Notch mode uses the fixed-window architecture (DynamicNotchKit /
    /// boring.notch): the NSPanel is sized ONCE to the maximum hover-menu
    /// surface for the idle ↔ hover lifecycle and never animates its frame —
    /// per-frame window resizes are synchronous WindowServer round-trips plus
    /// an NSHostingView re-layout, which is what made hover expansion janky.
    /// The entire visible expand/collapse is the SwiftUI content morph
    /// (`notchSwitcherProgress`) driven by the two animations below.
    ///
    /// Pill mode still resizes its panel; it keeps the duration constants
    /// below shared with its content transitions so both finish together.
    static let notchHoverMenuExpandAnimation: Animation = .spring(response: 0.35, dampingFraction: 0.75)
    static let notchHoverMenuCollapseAnimation: Animation = .spring(response: 0.3, dampingFraction: 1.0)
    static let notchHoverMenuExpandDuration: TimeInterval = 0.16
    static let notchHoverMenuCollapseDuration: TimeInterval = 0.10
    private static let frameNoopEpsilon: CGFloat = 0.5
    private static let startupDisplayRevalidationDelays: [TimeInterval] = [0.2, 0.8, 2.0]
    private static let topInset: CGFloat = 40
    private static let topInsetWhenNotchModeFallsBackToPill: CGFloat = 4
    /// Minimum window height when AI response first appears.
    private static let minResponseHeight: CGFloat = 250
    /// Base height used as the reference for 2× cap (same as current default response height).
    private static let defaultBaseResponseHeight: CGFloat = 430
    /// Overhead (px) added to measured scroll content to account for control bar, header, follow-up input, and padding.
    private static let responseViewOverhead: CGFloat = 199

    let state = FloatingControlBarState()
    private var hostingView: NSHostingView<AnyView>?
    private var isResizingProgrammatically = false
    private var isUserDragging = false
    /// Set by ResizeHandleNSView while the user is manually dragging the corner.
    /// Prevents the response-height observer from fighting manual resize.
    var isUserResizing = false
    /// Suppresses hover resizes during close animation to prevent position drift.
    private var suppressHoverResize = false
    private var inputHeightCancellable: AnyCancellable?
    private var responseHeightCancellable: AnyCancellable?
    private var agentPillsCancellable: AnyCancellable?
    private var voiceResponseGlowCancellable: AnyCancellable?
    private var draggableBarCancellable: AnyCancellable?
    private var pttHintCancellable: AnyCancellable?
    private var previousVoiceResponseGlowActive = false
    private var resizeWorkItem: DispatchWorkItem?
    /// Saved center point from before chat opened, used to restore position on close.
    private var preChatCenter: NSPoint?
    /// Token incremented each time a windowDidResignKey dismiss animation starts.
    /// Checked in the completion block so a new PTT query can cancel a stale close.
    private var resignKeyAnimationToken: Int = 0
    /// The target origin of an in-progress close/restore animation, set in
    /// closeAIConversation() and cleared when the animation settles.
    /// Used by savePreChatCenterIfNeeded() to snap to the correct pill position
    /// if a new PTT query fires while the restore animation is still running.
    private var pendingRestoreOrigin: NSPoint?
    /// The idle pill frame captured just before morphing into the active island
    /// on a non-notch display, so the pill returns to the exact same spot.
    private var savedPillFrame: NSRect?
    private var frameAnimationToken: Int = 0
    private var pendingFrameAnimationTarget: NSRect?
    private var startupDisplayRevalidationWorkItems: [DispatchWorkItem] = []

    /// The bar adopts the notch-island presentation whenever it is actively
    /// engaged — PTT listening, thinking, or speaking a reply — on ANY display,
    /// so external monitors morph from the idle pill into the island too.
    private var barWantsActiveIsland: Bool {
        state.isVoiceListening || state.isThinking || state.isVoiceResponseGlowActive
    }
    private var notchModeEnabled: Bool {
        Self.shouldUseNotchIsland(
            displayHasCameraHousing: Self.screenHasCameraHousing(screenForPlacement),
            hasActiveIsland: barWantsActiveIsland,
            draggableBarEnabled: ShortcutSettings.shared.draggableBarEnabled
        )
    }
    /// Hardware-only notch detection (ignores the transient active-island state) —
    /// "does this display physically have a camera housing".
    var usesNotchIslandForCurrentScreen: Bool {
        Self.screenHasCameraHousing(screenForPlacement)
    }
    private var screenForPlacement: NSScreen? {
        self.screen ?? NSApp.keyWindow?.screen ?? NSScreen.main ?? NSScreen.screens.first
    }
    private var notchSideWidth: CGFloat {
        if state.showingAIConversation {
            return AgentPillsManager.shared.pills.isEmpty
                ? Self.notchCompactSideWidth
                : Self.notchActiveSideWidth
        }
        if AgentPillsManager.shared.pills.isEmpty && !state.isVoiceListening {
            return Self.notchCompactSideWidth
        }
        return Self.notchActiveSideWidth
    }
    private var notchHiddenCenterWidthForCurrentScreen: CGFloat {
        Self.notchHiddenCenterWidth(for: screenForPlacement)
    }
    private var notchChromeHeightForCurrentScreen: CGFloat {
        Self.notchChromeHeight(for: screenForPlacement)
    }
    private var notchInputPanelHeightForCurrentScreen: CGFloat {
        Self.notchInputPanelHeight(for: screenForPlacement)
    }
    private func notchSize(active: Bool) -> NSSize {
        let sideWidth = active ? Self.notchActiveSideWidth : Self.notchCompactSideWidth
        return notchSize(sideWidth: sideWidth)
    }
    private func notchSize(sideWidth: CGFloat) -> NSSize {
        return NSSize(width: notchHiddenCenterWidthForCurrentScreen + sideWidth * 2, height: notchChromeHeightForCurrentScreen)
    }
    private func notchSize(sideWidth: CGFloat, for screen: NSScreen) -> NSSize {
        NSSize(
            width: Self.notchHiddenCenterWidth(for: screen) + sideWidth * 2,
            height: Self.notchChromeHeight(for: screen)
        )
    }
    private func responseGlowWindowSize(forSurfaceSize size: NSSize, usesNotchIsland: Bool) -> NSSize {
        if usesNotchIsland {
            return NSSize(
                width: size.width + Self.notchGlowOutsetX * 2,
                height: size.height + Self.notchGlowOutsetBottom
            )
        }
        guard state.isVoiceResponseGlowActive || collapsedPillAgentGlowActive else { return size }
        guard size.width <= Self.minBarSize.width + 0.5,
              size.height <= Self.minBarSize.height + 0.5
        else { return size }
        return NSSize(
            width: size.width + Self.legacyPillGlowOutsetX * 2,
            height: size.height + Self.legacyPillGlowOutsetY * 2
        )
    }

    /// Whether the collapsed pill is showing the ambient subagent status
    /// tint/glow (mirrors `NotchAgentStatusGroup.aggregate`: finished agents
    /// the user has viewed go quiet).
    private var collapsedPillAgentGlowActive: Bool {
        !notchModeEnabled
            && AgentPillsManager.shared.pills.contains {
                !($0.status.isFinished && $0.viewedAt != nil)
            }
    }
    private func responseGlowWindowSizeForCurrentScreen(forSurfaceSize size: NSSize) -> NSSize {
        responseGlowWindowSize(forSurfaceSize: size, usesNotchIsland: notchModeEnabled)
    }
    /// Bare hover-menu surface size. `resizeAnchored` adds the transparent glow
    /// outsets exactly once when converting this to an NSPanel frame.
    private func notchHoverMenuSurfaceSize(agentCount: Int) -> NSSize {
        NSSize(
            width: max(collapsedBarSize.width, Self.notchExpandedWidth),
            height: notchChromeHeightForCurrentScreen
                + Self.notchHoverMenuHeight(agentCount: agentCount)
        )
    }
    /// The constant notch window surface for the whole idle ↔ hover-menu
    /// lifecycle: the maximum hover-menu surface at the visible-agent ceiling.
    /// The panel is sized to this once (entering notch mode / screen change)
    /// and the visible expand/collapse is carried entirely by the SwiftUI
    /// content morph — never by an NSPanel frame animation.
    private func notchFixedIdleSurfaceSize() -> NSSize {
        notchHoverMenuSurfaceSize(agentCount: Self.notchAgentListMaxVisibleAgents)
    }
    private func notchFixedIdleSurfaceSize(for screen: NSScreen) -> NSSize {
        NSSize(
            width: max(notchCollapsedSize(for: screen).width, Self.notchExpandedWidth),
            height: Self.notchChromeHeight(for: screen)
                + Self.notchHoverMenuHeight(agentCount: Self.notchAgentListMaxVisibleAgents)
        )
    }
    /// Re-assert the fixed idle/hover window frame. A no-op when the panel is
    /// already there (the common case for every hover expand/collapse); only
    /// transitions returning from a differently-sized state (chat, voice,
    /// notification, PTT hint) actually move the frame.
    private func assertNotchFixedHoverSurfaceFrame(animated: Bool = true) {
        guard notchModeEnabled else { return }
        resizeAnchored(
            to: notchFixedIdleSurfaceSize(),
            makeResizable: false,
            animated: animated,
            animationDuration: Self.notchHoverMenuCollapseDuration,
            anchorTop: true
        )
    }
    /// Height of the VISIBLE notch content (chrome band, plus the open hover
    /// menu sized to the CURRENT agent count). The window frame stays at the
    /// maximum hover surface for the whole idle ↔ hover lifecycle, so pointer
    /// math must derive from content, not from `frame`.
    private var notchVisibleContentHeight: CGFloat {
        var height = notchChromeHeightForCurrentScreen
        if state.isNotchHoverMenuVisible {
            height += Self.notchHoverMenuHeight(agentCount: AgentPillsManager.shared.pills.count)
        }
        return height
    }
    /// Width of the visible notch content for the idle ↔ hover lifecycle.
    private var notchVisibleContentWidth: CGFloat {
        state.isNotchHoverMenuVisible
            ? max(notchCollapsedSize.width, Self.notchExpandedWidth)
            : notchCollapsedSize.width
    }
    /// Horizontal transparent margin between the fixed window edge and the
    /// visible content. With the constantly-large window this is wider than
    /// the glow outset while the menu is closed — hover/click activation must
    /// hug the visible chrome, not the window frame.
    private var notchVisibleContentHorizontalOutset: CGFloat {
        max(Self.notchGlowOutsetX, (frame.width - notchVisibleContentWidth) / 2)
    }
    private func currentResponseSurfaceHeight(usesNotchIsland: Bool? = nil) -> CGFloat {
        if usesNotchIsland ?? notchModeEnabled {
            return max(0, frame.height - Self.notchGlowOutsetBottom)
        }
        return frame.height
    }
    private func currentResponseSurfaceWidth(usesNotchIsland: Bool? = nil) -> CGFloat {
        if usesNotchIsland ?? notchModeEnabled {
            return max(0, frame.width - Self.notchGlowOutsetX * 2)
        }
        return frame.width
    }
    private var notchCollapsedSize: NSSize {
        NSSize(width: notchHiddenCenterWidthForCurrentScreen + notchSideWidth * 2, height: notchChromeHeightForCurrentScreen)
    }
    private func notchCollapsedSize(for screen: NSScreen) -> NSSize {
        notchSize(sideWidth: notchSideWidth, for: screen)
    }
    private var collapsedBarSize: NSSize { notchModeEnabled ? notchCollapsedSize : Self.minBarSize }
    private var expandedContentWidth: CGFloat { Self.notchExpandedWidth }
    private var inputPanelHeight: CGFloat {
        // Chat always mounts shared top chrome, so budget chrome height even off-notch.
        let base = (notchModeEnabled || state.showingAIConversation)
            ? notchInputPanelHeightForCurrentScreen
            : Self.pillInputPanelHeight
        let statusBanner = state.pttHintText.isEmpty ? 0 : Self.pttStatusBannerBudget
        // When notch mode renders the "Back / Omi Chat" header (agent pills
        // present), the input panel needs additional vertical room so the
        // header + editor + padding all fit. (Codex P2 — input/send clipping.)
        if !AgentPillsManager.shared.pills.isEmpty {
            return base + statusBanner + Self.notchChatHeaderVerticalBudget
        }
        return base + statusBanner
    }

    var onPlayPause: (() -> Void)?
    var onAskAI: (() -> Void)?
    var onHide: (() -> Void)?
    var onSendQuery: ((String) -> Void)?
    var onRate: ((String, Int?) -> Void)?
    var onShareLink: (() async -> String?)?

    override init(
        contentRect: NSRect, styleMask style: NSWindow.StyleMask,
        backing backingStoreType: NSWindow.BackingStoreType = .buffered, defer flag: Bool = false
    ) {
        let initialScreen = NSScreen.main ?? NSScreen.screens.first
        let initialUsesNotchIsland = FloatingControlBarWindow.shouldUseNotchIsland(
            displayHasCameraHousing: FloatingControlBarWindow.screenHasCameraHousing(initialScreen),
            hasActiveIsland: false,
            draggableBarEnabled: ShortcutSettings.shared.draggableBarEnabled
        )
        let initialSize = initialUsesNotchIsland
            ? NSSize(
                width: FloatingControlBarWindow.notchHiddenCenterWidth(for: initialScreen)
                    + FloatingControlBarWindow.notchCompactSideWidth * 2,
                height: FloatingControlBarWindow.notchChromeHeight(for: initialScreen)
            )
            : FloatingControlBarWindow.minBarSize
        let initialRect = NSRect(origin: .zero, size: initialSize)

        super.init(
            contentRect: initialRect,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: backingStoreType,
            defer: flag
        )

        self.appearance = NSAppearance(named: .vibrantDark)
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = false
        self.level = initialUsesNotchIsland ? .statusBar : .floating
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.isMovableByWindowBackground = false
        self.acceptsMouseMovedEvents = true
        self.delegate = self
        self.minSize = initialSize
        self.maxSize = FloatingControlBarWindow.maxBarSize

        setupViews()
        updateNotchIslandState()

        if ShortcutSettings.shared.draggableBarEnabled,
           !notchModeEnabled,
           let savedPosition = UserDefaults.standard.string(forKey: FloatingControlBarWindow.positionKey) {
            let origin = NSPointFromString(savedPosition)
            // Validate that the full bar frame (not just a 14pt inset) fits inside
            // some screen's visibleFrame. visibleFrame already excludes the Dock
            // and menu bar on macOS, so clamping against it is what keeps the
            // input field above the Dock (#6684).
            let candidateFrame = NSRect(origin: origin, size: frame.size)
            if let targetScreen = NSScreen.screens.first(where: { $0.visibleFrame.intersects(candidateFrame) }) {
                let clamped = FloatingControlBarWindow.clamp(candidateFrame, to: targetScreen.visibleFrame)
                self.setFrameOrigin(clamped.origin)
            } else {
                centerOnMainScreen()
            }
        } else {
            centerOnMainScreen()
        }
        scheduleStartupDisplayRevalidation()
    }

    /// Clamp `rect` so it stays entirely inside `visible`. visibleFrame already
    /// excludes the Dock and menu bar, so clamping here keeps the Floating Bar
    /// off both. This also gracefully handles rects larger than the screen.
    static func clamp(_ rect: NSRect, to visible: NSRect) -> NSRect {
        guard visible.width > 0 && visible.height > 0 else { return rect }
        var r = rect
        // Clamp x so the window fits between visible.minX and visible.maxX.
        let maxX = max(visible.minX, visible.maxX - r.width)
        r.origin.x = min(max(r.origin.x, visible.minX), maxX)
        // Clamp y so the window fits between visible.minY and visible.maxY.
        let maxY = max(visible.minY, visible.maxY - r.height)
        r.origin.y = min(max(r.origin.y, visible.minY), maxY)
        return r
    }

    static func screenHasCameraHousing(_ screen: NSScreen?) -> Bool {
        // Testing hook: force the non-notch (pill) presentation on notched
        // hardware so the fallback surface can be exercised locally. getenv so
        // values loaded from the bundle .env (BundleEnvironment) are seen too.
        if let forced = getenv("OMI_FORCE_NO_NOTCH"), String(cString: forced) == "1" { return false }
        // Testing hook: force the notch-island presentation on non-notch hardware
        // (external display / dev machine) so notch-only UI can be exercised
        // locally. Mirror of OMI_FORCE_NO_NOTCH; NO_NOTCH wins if both are set.
        if let forced = getenv("OMI_FORCE_NOTCH"), String(cString: forced) == "1" { return true }
        guard let screen else { return false }
        if #available(macOS 12.0, *) {
            if let leftArea = screen.auxiliaryTopLeftArea,
               let rightArea = screen.auxiliaryTopRightArea,
               !leftArea.isEmpty,
               !rightArea.isEmpty {
                return true
            }
            return screen.safeAreaInsets.top > 0
        }
        return false
    }

    /// A physical notch is fixed to the display, so the movable-bar preference
    /// always opts into the pill presentation instead.
    static func shouldUseNotchIsland(
        displayHasCameraHousing: Bool,
        hasActiveIsland: Bool,
        draggableBarEnabled: Bool
    ) -> Bool {
        !draggableBarEnabled && (displayHasCameraHousing || hasActiveIsland)
    }

    static func notchChromeHeight(for screen: NSScreen?) -> CGFloat {
        guard let screen else { return notchChromeHeight }
        if #available(macOS 12.0, *) {
            return notchChromeHeight(
                topSafeAreaInset: screen.safeAreaInsets.top,
                auxiliaryTopLeftArea: screen.auxiliaryTopLeftArea,
                auxiliaryTopRightArea: screen.auxiliaryTopRightArea
            )
        }
        return notchChromeHeight
    }

    static func notchChromeHeight(
        topSafeAreaInset: CGFloat,
        auxiliaryTopLeftArea: NSRect?,
        auxiliaryTopRightArea: NSRect?
    ) -> CGFloat {
        let auxiliaryHeights = [auxiliaryTopLeftArea, auxiliaryTopRightArea]
            .compactMap { area -> CGFloat? in
                guard let area, !area.isEmpty, area.height > 0 else { return nil }
                return area.height
            }
        let measuredHeight = max(topSafeAreaInset, auxiliaryHeights.max() ?? 0)
        guard measuredHeight > 0 else { return notchChromeHeight }
        return max(notchChromeHeight, measuredHeight)
    }

    static func notchInputPanelHeight(for screen: NSScreen?) -> CGFloat {
        notchChromeHeight(for: screen) + notchInputPanelMinimumContentHeight + notchInputPanelVerticalPadding
    }

    static func notchHiddenCenterWidth(for screen: NSScreen?) -> CGFloat {
        guard let screen else { return notchHiddenCenterWidth }
        if #available(macOS 12.0, *),
           let leftArea = screen.auxiliaryTopLeftArea,
           let rightArea = screen.auxiliaryTopRightArea,
           !leftArea.isEmpty,
           !rightArea.isEmpty {
            let measuredGap = rightArea.minX - leftArea.maxX
            if measuredGap > 0 {
                return max(notchHiddenCenterWidth, measuredGap + notchHiddenCenterSafetyPadding)
            }
        }
        return notchHiddenCenterWidth
    }

    private func updateNotchIslandState() {
        let usesNotch = notchModeEnabled
        // Leaving the idle pill for the active island on a non-notch display —
        // remember the pill's exact spot so we can restore it when we return
        // (otherwise the pill drifts to a recomputed top-center each cycle).
        if usesNotch, !state.usesNotchIsland, !Self.screenHasCameraHousing(screenForPlacement),
           !state.showingAIConversation, state.currentNotification == nil {
            savedPillFrame = frame
        }
        if state.usesNotchIsland != usesNotch {
            state.usesNotchIsland = usesNotch
        }
        if !usesNotch {
            state.notchRevealProgress = 1
        }
        level = usesNotch ? .statusBar : .floating
    }

    private func refreshPresentationForDraggableBarPreference() {
        let wasUsingNotchIsland = state.usesNotchIsland
        updateNotchIslandState()
        guard wasUsingNotchIsland != state.usesNotchIsland,
              let screen = screenForPlacement
        else { return }

        let targetFrame = frameForCurrentState(on: screen, usesNotchIsland: state.usesNotchIsland)
        resizeToFrame(
            targetFrame,
            makeResizable: state.showingAIConversation && state.showingAIResponse,
            animated: isVisible
        )
    }

    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }

    override func keyDown(with event: NSEvent) {
        if event.keyCode == 53 { // Escape
            handleEscapeKey()
            return
        }
        super.keyDown(with: event)
    }

    func handleEscapeKey() {
        if FloatingBarVoicePlaybackService.shared.isSpeaking {
            FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
            return
        }

        if !state.showingAIConversation, !notchModeEnabled, state.isNotchHoverMenuVisible {
            setPillAgentListVisible(false)
            return
        }

        guard state.showingAIConversation else { return }

        if !state.aiInputText.isEmpty {
            state.aiInputText = ""
            return
        }

        if state.hasVisibleConversation {
            clearVisibleConversationFromUI()
        } else {
            closeAIConversation()
        }
    }

    private func setupViews() {
        let swiftUIView = FloatingControlBarView(
            window: self,
            onPlayPause: { [weak self] in self?.onPlayPause?() },
            onAskAI: { [weak self] in self?.handleAskAI() },
            onHide: { [weak self] in self?.hideBar() },
            onSendQuery: { [weak self] message in self?.onSendQuery?(message) },
            onCloseAI: { [weak self] in self?.closeAIConversation() },
            onEscape: { [weak self] in self?.handleEscapeKey() },
            onClearVisibleConversation: { [weak self] in self?.clearVisibleConversationFromUI() },
            onRate: { [weak self] messageId, rating in self?.onRate?(messageId, rating) },
            onShareLink: { [weak self] in await self?.onShareLink?() }
        ).environmentObject(state)

        hostingView = FloatingBarHostingView(rootView: AnyView(
            swiftUIView
                .withFontScaling()
                .preferredColorScheme(.dark)
                .environment(\.colorScheme, .dark)
        ))
        hostingView?.appearance = NSAppearance(named: .vibrantDark)

        // CRITICAL: Use a container view instead of making NSHostingView the contentView directly.
        // When NSHostingView IS the contentView of a borderless window, it tries to negotiate
        // window sizing through updateWindowContentSizeExtremaIfNecessary and updateAnimatedWindowSize,
        // causing re-entrant constraint updates that crash in _postWindowNeedsUpdateConstraints.
        // Wrapping in a container breaks that "I own this window" relationship.
        //
        // sizingOptions: Remove .intrinsicContentSize so the hosting view can expand beyond
        // its SwiftUI ideal size. Keep .minSize and .maxSize for proper min/max constraints.
        // Setting [] removes ALL sizing info (broken). Default includes .intrinsicContentSize
        // which pins the view to its ideal size (prevents expansion). [.minSize, .maxSize] is correct.
        let container = FloatingBarContainerView()
        container.controlBarWindow = self
        container.wantsLayer = true
        container.layer?.backgroundColor = NSColor.clear.cgColor
        self.contentView = container

        if let hosting = hostingView {
            hosting.sizingOptions = [.minSize, .maxSize]
            hosting.wantsLayer = true
            hosting.layer?.backgroundColor = NSColor.clear.cgColor
            hosting.translatesAutoresizingMaskIntoConstraints = false
            container.addSubview(hosting)
            NSLayoutConstraint.activate([
                hosting.leadingAnchor.constraint(equalTo: container.leadingAnchor),
                hosting.trailingAnchor.constraint(equalTo: container.trailingAnchor),
                hosting.topAnchor.constraint(equalTo: container.topAnchor),
                hosting.bottomAnchor.constraint(equalTo: container.bottomAnchor),
            ])
        }

        NotificationCenter.default.addObserver(
            forName: .floatingBarDragDidStart, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.isUserDragging = true
                self?.state.isDragging = true
            }
        }

        NotificationCenter.default.addObserver(
            forName: .floatingBarDragDidEnd, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.isUserDragging = false
                self?.state.isDragging = false
            }
        }

        // Re-validate position when monitors are connected/disconnected
        NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.validatePositionOnScreenChange(reason: "screen_parameters_changed")
            }
        }

        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.activeSpaceDidChangeNotification, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.performSpacesTransitionGrowIn()
            }
        }

        draggableBarCancellable = ShortcutSettings.shared.$draggableBarEnabled
            .dropFirst()
            .sink { [weak self] _ in
                Task { @MainActor in
                    self?.refreshPresentationForDraggableBarPreference()
                }
            }

        // Follow cursor across monitors — poll mouse position to move bar instantly
        startCursorScreenTracking()
        observeNotchAgentPills()
        observeVoiceResponseGlow()
        observePttHint()
    }

    private func performSpacesTransitionGrowIn() {
        updateNotchIslandState()
        guard notchModeEnabled, isVisible else { return }
        // The panel already lives on every Space (.canJoinAllSpaces), so switching
        // Spaces must NOT replay the reveal "pop" — doing so re-zoomed the island on
        // every desktop/app switch, which felt excessive. Keep it fully revealed and
        // only re-assert the resting frame if the current one has actually drifted
        // (e.g. the active screen's notch geometry changed).
        state.notchRevealProgress = 1
        let targetFrame = defaultFrameForCurrentState()
        guard !Self.framesEquivalent(frame, targetFrame) else { return }
        resizeToFrame(targetFrame, makeResizable: styleMask.contains(.resizable), animated: false)
    }

    private func defaultFrameForCurrentState() -> NSRect {
        let size: NSSize
        if state.showingAIConversation {
            let height = max(inputPanelHeight, frame.height)
            size = NSSize(width: expandedContentWidth, height: height)
        } else if !state.pttHintText.isEmpty {
            size = pttHintSurfaceSize(usesNotchIsland: notchModeEnabled)
        } else if state.isVoiceListening {
            size = notchModeEnabled ? notchSize(active: true) : Self.voiceBarSize
        } else if state.currentNotification != nil {
            size = NSSize(
                width: Self.notificationWidth,
                height: notchChromeHeightForCurrentScreen + Self.notificationSpacing + Self.notificationHeight
            )
        } else {
            // Idle ↔ hover-menu lifecycle: notch mode holds one fixed frame.
            size = notchModeEnabled ? notchFixedIdleSurfaceSize() : collapsedBarSize
        }
        let windowSize = responseGlowWindowSizeForCurrentScreen(forSurfaceSize: size)
        return NSRect(origin: defaultTopCenteredOrigin(for: windowSize), size: windowSize)
    }

    private func currentSurfaceSize(
        usesNotchIsland: Bool,
        frameIncludesVoiceGlow: Bool? = nil
    ) -> NSSize {
        if state.showingAIConversation {
            let defaultWidth = Self.notchExpandedWidth
            let width = max(defaultWidth, currentResponseSurfaceWidth(usesNotchIsland: usesNotchIsland))
            // Chat always mounts shared top chrome, so budget chrome height even
            // on non-notch displays (pillSurfaceTopPadding alone would clip).
            let panelHeight = notchInputPanelHeightForCurrentScreen
            let statusBanner = state.pttHintText.isEmpty ? 0 : Self.pttStatusBannerBudget
            let reservedGlowOutset = usesNotchIsland ? Self.notchGlowOutsetBottom : 0
            let contentHeight = max(panelHeight + statusBanner, frame.height - reservedGlowOutset)
            return NSSize(width: width, height: contentHeight)
        }
        // Grow just enough to fit the readable PTT status banner under chrome/pill.
        // (isVoiceListening is true during the hint, so this must precede it.)
        if !state.pttHintText.isEmpty {
            return pttHintSurfaceSize(usesNotchIsland: usesNotchIsland)
        }
        if state.isVoiceListening {
            return usesNotchIsland ? notchSize(active: true) : Self.voiceBarSize
        }
        if state.currentNotification != nil {
            let barHeight = usesNotchIsland
                ? notchChromeHeightForCurrentScreen
                : (state.isHoveringBar ? Self.expandedBarSize.height : Self.minBarSize.height)
            return NSSize(
                width: Self.notificationWidth,
                height: barHeight + Self.notificationSpacing + Self.notificationHeight
            )
        }
        // Idle ↔ hover-menu lifecycle: notch mode holds one fixed frame sized
        // to the maximum hover-menu surface; the content morph does the rest.
        return usesNotchIsland ? notchFixedIdleSurfaceSize() : Self.minBarSize
    }

    private func currentSurfaceSizeForCurrentScreen(frameIncludesVoiceGlow: Bool? = nil) -> NSSize {
        currentSurfaceSize(usesNotchIsland: notchModeEnabled, frameIncludesVoiceGlow: frameIncludesVoiceGlow)
    }

    private func frameForCurrentState(on screen: NSScreen, usesNotchIsland: Bool) -> NSRect {
        let size: NSSize
        if state.showingAIConversation {
            let width = Self.notchExpandedWidth
            let chromeHeight = Self.notchChromeHeight(for: screen)
            // Chat always mounts shared top chrome.
            let panelHeight = Self.notchInputPanelHeight(for: screen)
            let statusBanner = state.pttHintText.isEmpty ? 0 : Self.pttStatusBannerBudget
            size = NSSize(
                width: width,
                height: max(panelHeight + statusBanner, frame.height, chromeHeight + statusBanner)
            )
        } else if !state.pttHintText.isEmpty {
            size = pttHintSurfaceSize(usesNotchIsland: usesNotchIsland, screen: screen)
        } else if state.isVoiceListening {
            size = usesNotchIsland ? notchSize(sideWidth: Self.notchActiveSideWidth, for: screen) : Self.voiceBarSize
        } else if state.currentNotification != nil {
            let barHeight = usesNotchIsland
                ? Self.notchChromeHeight(for: screen)
                : (state.isHoveringBar ? Self.expandedBarSize.height : Self.minBarSize.height)
            size = NSSize(
                width: Self.notificationWidth,
                height: barHeight + Self.notificationSpacing + Self.notificationHeight
            )
        } else {
            // Idle ↔ hover-menu lifecycle: the notch island keeps one fixed
            // frame (sized here on entry/screen change) so hover never resizes.
            size = usesNotchIsland ? notchFixedIdleSurfaceSize(for: screen) : Self.minBarSize
        }
        let windowSize = responseGlowWindowSize(forSurfaceSize: size, usesNotchIsland: usesNotchIsland)
        return NSRect(
            origin: topCenteredOrigin(for: windowSize, on: screen, usesNotchIsland: usesNotchIsland),
            size: windowSize
        )
    }

    private func topCenteredOrigin(for size: NSSize, on screen: NSScreen, usesNotchIsland: Bool) -> NSPoint {
        let anchorFrame = usesNotchIsland ? screen.frame : screen.visibleFrame
        var frame = FloatingControlBarGeometry.topCenteredFrame(size: size, anchorFrame: anchorFrame)
        if !usesNotchIsland {
            frame.origin.y -= topInsetForPillFallback
        }
        return frame.origin
    }

    private func growOutFromNotch(on targetScreen: NSScreen) {
        state.usesNotchIsland = true
        level = .statusBar
        styleMask.remove(.resizable)

        let targetFrame = frameForCurrentState(on: targetScreen, usesNotchIsland: true)
        animateGrowOutFromNotch(to: targetFrame)
    }

    private func animateGrowOutFromNotch(to targetFrame: NSRect, duration: TimeInterval = 0.16) {
        resizeWorkItem?.cancel()
        resizeWorkItem = nil
        frameAnimationToken += 1
        let token = frameAnimationToken
        isResizingProgrammatically = true
        alphaValue = 1
        state.notchRevealProgress = 0.001
        setFrame(targetFrame, display: true, animate: false)

        OmiMotion.withGated(.easeOut(duration: duration)) {
            state.notchRevealProgress = 1
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + duration) { [weak self] in
            guard let self, self.frameAnimationToken == token else { return }
            self.setFrame(targetFrame, display: true, animate: false)
            self.state.notchRevealProgress = 1
            self.alphaValue = 1
            self.isResizingProgrammatically = false
        }
    }

    private enum NotchPointerMode {
        case activationOnly
        case openMenuRetention
    }

    private func notchPointerContains(localPoint point: NSPoint, mode: NotchPointerMode) -> Bool {
        // The window frame is the fixed maximum hover surface, so activation
        // and retention zones must come from the VISIBLE content geometry —
        // deriving them from `frame` would trigger hover from far below the
        // collapsed chrome.
        let chromeHeight: CGFloat
        switch mode {
        case .activationOnly:
            chromeHeight = Self.notchActivationHeight
        case .openMenuRetention:
            chromeHeight = max(Self.notchActivationHeight, notchVisibleContentHeight)
        }

        return FloatingControlBarGeometry.notchChromeActivationContainsLocal(
            localPoint: point,
            windowSize: frame.size,
            chromeHeight: chromeHeight,
            horizontalOutset: notchVisibleContentHorizontalOutset
        )
    }

    fileprivate func updateNotchPointer(from event: NSEvent) {
        updateNotchPointer(localPoint: event.locationInWindow)
    }

    func updateNotchPointerFromGlobalMouse() {
        let mouse = NSEvent.mouseLocation
        let localPoint = NSPoint(x: mouse.x - frame.minX, y: mouse.y - frame.minY)
        updateNotchPointer(localPoint: localPoint)
    }

    func openNotchHoverMenuUntilExit() {
        setNotchHoverMenuVisible(true)
    }

    private func updateNotchPointer(localPoint point: NSPoint) {
        guard notchModeEnabled,
              !state.showingAIConversation,
              state.currentNotification == nil
        else {
            setNotchHoverMenuVisible(false)
            return
        }

        let mode: NotchPointerMode = state.isNotchHoverMenuVisible ? .openMenuRetention : .activationOnly
        setNotchHoverMenuVisible(notchPointerContains(localPoint: point, mode: mode))
    }

    private func setNotchHoverMenuVisible(_ visible: Bool) {
        guard notchModeEnabled else { return }
        let allowed = visible && state.canShowNotchHoverMenu
        guard state.notchHoverMenuOpen != allowed else { return }

        // The NSPanel frame is fixed for the idle ↔ hover lifecycle; flipping
        // this state drives the SwiftUI content morph (`notchSwitcherProgress`)
        // that carries the entire visible expand/collapse. The resize call only
        // re-asserts the fixed frame (a no-op unless returning from a
        // differently-sized state).
        state.setNotchHoverMenuOpen(allowed)
        resizeForAgentSwitcher(visible: allowed)
    }

    fileprivate func acceptsMouseHit(inContentPoint point: NSPoint) -> Bool {
        guard notchModeEnabled else { return true }
        guard !state.showingAIConversation,
              state.currentNotification == nil
        else { return true }

        // Content-derived hit region: the fixed window is larger than the
        // visible chrome/menu, and its transparent margins must keep passing
        // clicks through to windows below (hitTest returns nil outside this).
        let chromeHeight = state.isNotchHoverMenuVisible
            ? max(Self.notchActivationHeight, notchVisibleContentHeight)
            : notchChromeHeightForCurrentScreen
        return FloatingControlBarGeometry.notchChromeActivationContainsLocal(
            localPoint: point,
            windowSize: frame.size,
            chromeHeight: chromeHeight,
            horizontalOutset: notchVisibleContentHorizontalOutset
        )
    }

    private func observeNotchAgentPills() {
        agentPillsCancellable = AgentPillsManager.shared.$pills
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                guard let self,
                      self.state.currentNotification == nil
                else { return }

                guard self.notchModeEnabled else {
                    // Keep the pill agent list sized to its rows; close it
                    // when the last agent disappears.
                    if self.state.isNotchHoverMenuVisible {
                        if AgentPillsManager.shared.pills.isEmpty {
                            self.setPillAgentListVisible(false)
                        } else if !self.state.showingAIConversation {
                            self.resizeForAgentSwitcher(visible: true)
                        }
                        return
                    }
                    // Collapsed idle pill: apply/remove the status-glow window
                    // outset promptly when agents appear or all disappear
                    // (same reasoning as the voice-response glow observer).
                    guard !self.state.showingAIConversation,
                          !self.state.isVoiceListening,
                          !self.state.isHoveringBar,
                          self.state.currentNotification == nil
                    else { return }
                    self.resizeToFrame(self.canonicalCollapsedPillFrame(), makeResizable: false, animated: false)
                    return
                }

                if self.state.showingAIConversation {
                    self.resizeAnchored(
                        to: self.currentSurfaceSizeForCurrentScreen(),
                        makeResizable: self.styleMask.contains(.resizable),
                        animated: true,
                        anchorTop: true
                    )
                    return
                }
                // Voice listening/thinking/glow own their own frames (syncActiveIsland).
                guard !self.state.isVoiceListening,
                      !self.state.isThinking,
                      !self.state.isVoiceResponseGlowActive,
                      self.state.pttHintText.isEmpty
                else { return }
                // Idle ↔ hover lifecycle: pills appearing or disappearing must
                // not resize the panel — the fixed frame already fits the
                // agent-count ceiling and the content morph handles the rest.
                self.assertNotchFixedHoverSurfaceFrame(animated: false)
            }
    }

    private func observeVoiceResponseGlow() {
        voiceResponseGlowCancellable = state.$voiceProjection
            .map { $0.isResponseActive || $0.isResponseWaiting }
            .removeDuplicates()
            .receive(on: DispatchQueue.main)
            .sink { [weak self] isActive in
                guard let self else { return }
                self.previousVoiceResponseGlowActive = isActive
                // On legacy (non-notch) displays the compact pill frame is only
                // enlarged to fit the glow/stroke outset during an explicit
                // resize. Without this, a PTT response that starts while the
                // bar is collapsed keeps the 40×14 frame and clips the white
                // glow for the entire spoken reply. Resize to the glow-adjusted
                // collapsed size on the active/inactive transitions so the
                // outset is applied/removed promptly.
                guard !self.notchModeEnabled else { return }
                guard !self.state.showingAIConversation,
                      !self.state.isVoiceListening,
                      !self.state.isHoveringBar,
                      !self.state.isNotchHoverMenuVisible,
                      self.state.currentNotification == nil
                else { return }
                self.resizeToFrame(self.canonicalCollapsedPillFrame(), makeResizable: false, animated: false)
            }
    }

    /// Resize when the transient PTT status banner appears or clears.
    /// `isVoiceListening` is already true when the hint fires, so the banner
    /// needs its own resize for chrome/pill and for open chat (which also mounts
    /// the banner under the shared top chrome).
    private func observePttHint() {
        pttHintCancellable = state.$voiceProjection
            .map { $0.hint.isEmpty }
            .removeDuplicates()
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                guard let self else { return }
                self.resizeAnchored(
                    to: self.currentSurfaceSizeForCurrentScreen(),
                    makeResizable: self.state.showingAIConversation && self.state.showingAIResponse,
                    animated: true,
                    anchorTop: true
                )
            }
    }

    private func pttHintSurfaceSize(usesNotchIsland: Bool, screen: NSScreen? = nil) -> NSSize {
        let chromeHeight: CGFloat
        let width: CGFloat
        if usesNotchIsland {
            chromeHeight = screen.map { Self.notchChromeHeight(for: $0) } ?? notchChromeHeightForCurrentScreen
            width = Self.notchExpandedWidth
        } else {
            chromeHeight = Self.voiceBarSize.height
            width = max(Self.voiceBarSize.width, Self.notchExpandedWidth * 0.72)
        }
        return NSSize(
            width: width,
            height: chromeHeight + Self.pttStatusBannerBudget
        )
    }

    private var cursorTrackingTimer: DispatchSourceTimer?

    /// Poll mouse position at ~250ms to move the bar when the cursor enters a different screen.
    private func startCursorScreenTracking() {
        let timer = DispatchSource.makeTimerSource(queue: .main)
        timer.schedule(deadline: .now(), repeating: .milliseconds(250))
        timer.setEventHandler { [weak self] in
            self?.checkCursorScreen()
        }
        timer.resume()
        cursorTrackingTimer = timer
    }

    private func checkCursorScreen() {
        let wasUsingNotchIsland = notchModeEnabled
        // Only follow when there are multiple screens
        guard NSScreen.screens.count > 1 else { return }

        // Find which screen the cursor is on
        let mouseLocation = NSEvent.mouseLocation
        guard let targetScreen = NSScreen.screens.first(where: { $0.frame.contains(mouseLocation) }) else { return }

        // Already on the same screen — nothing to do
        let currentScreen = self.screen ?? NSScreen.main
        if targetScreen == currentScreen { return }

        // Move to the equivalent position on the target screen
        let currentVisible = currentScreen?.visibleFrame ?? .zero
        let targetVisible = targetScreen.visibleFrame

        let targetUsesNotchIsland = Self.screenHasCameraHousing(targetScreen)

        if targetUsesNotchIsland {
            growOutFromNotch(on: targetScreen)
            log("FloatingControlBarWindow: grew out from notch on screen \(targetScreen.localizedName)")
            return
        }

        if ShortcutSettings.shared.draggableBarEnabled && !targetUsesNotchIsland {
            // Translate position proportionally
            let relX = currentVisible.width > 0 ? (frame.origin.x - currentVisible.origin.x) / currentVisible.width : 0.5
            let relY = currentVisible.height > 0 ? (frame.origin.y - currentVisible.origin.y) / currentVisible.height : 1.0
            let newX = targetVisible.origin.x + relX * targetVisible.width
            let newY = targetVisible.origin.y + relY * targetVisible.height
            // Clamp against the target screen's visibleFrame so the bar doesn't
            // land under that screen's Dock after a cross-screen migration (#6684).
            let clamped = FloatingControlBarWindow.clamp(
                NSRect(origin: NSPoint(x: newX, y: newY), size: frame.size),
                to: targetVisible
            )
            setFrameOrigin(clamped.origin)
            UserDefaults.standard.set(NSStringFromPoint(frame.origin), forKey: FloatingControlBarWindow.positionKey)
        } else {
            // Non-draggable: center on new screen
            let x = targetVisible.midX - frame.width / 2
            let y = targetVisible.maxY - frame.height - topInsetForPillFallback
            let clamped = FloatingControlBarWindow.clamp(
                NSRect(origin: NSPoint(x: x, y: y), size: frame.size),
                to: targetVisible
            )
            setFrameOrigin(clamped.origin)
        }

        updateNotchIslandState()
        if wasUsingNotchIsland != notchModeEnabled {
            resizeAnchored(
                to: currentSurfaceSize(usesNotchIsland: targetUsesNotchIsland),
                makeResizable: state.showingAIConversation && state.showingAIResponse,
                animated: true,
                anchorTop: true
            )
        }
        log("FloatingControlBarWindow: followed cursor to screen \(targetScreen.localizedName)")
    }

    // MARK: - AI Actions

    private func handleAskAI() {
        if state.showingAIConversation && !state.showingAIResponse {
            // Already showing input, close it
            closeAIConversation()
        } else if state.showingAIConversation && state.showingAIResponse {
            // Showing response — focus the follow-up input instead of closing
            makeKeyAndOrderFront(nil)
            focusInputField()
        } else {
            AnalyticsManager.shared.floatingBarAskOmiOpened(source: "button")
            onAskAI?()
        }
    }

    /// Focus the text input field by finding the NSTextView in the view hierarchy.
    /// Returns `true` if the text view was found and focused.
    @discardableResult
    func focusInputField() -> Bool {
        guard let contentView = self.contentView else { return false }
        // Find the NSTextView inside the hosting view hierarchy
        func findTextView(in view: NSView) -> NSTextView? {
            if let textView = view as? NSTextView { return textView }
            for subview in view.subviews {
                if let found = findTextView(in: subview) { return found }
            }
            return nil
        }
        if let textView = findTextView(in: contentView) {
            makeKeyAndOrderFront(nil)
            makeFirstResponder(textView)
            return true
        }
        return false
    }

    func closeAIConversation() {
        AnalyticsManager.shared.floatingBarAskOmiClosed()
        resignKeyAnimationToken += 1
        let closeAnimationToken = resignKeyAnimationToken

        // Collapsing the chat should not interrupt spoken playback. The voice
        // response glow is owned by playback state and must survive surface
        // transitions while audio is still being delivered. However the UI
        // streaming subscription must still be cancelled so late-arriving
        // chunks cannot re-present .mainResponse and pop the panel back open.
        // (Codex P2 — streaming reopens surface during playback.)
        let keepVoiceResponseAlive = state.isVoiceResponseGlowActive
        FloatingControlBarManager.shared.cancelChat(keepVoiceAlive: keepVoiceResponseAlive)

        // Cancel dynamic response-height observer and reset its state
        responseHeightCancellable?.cancel()
        responseHeightCancellable = nil
        state.responseContentHeight = 0

        // Cancel PTT if listening while chat closes
        PushToTalkManager.shared.cancelListening()

        OmiMotion.withGated(.easeOut(duration: 0.08)) {
            state.showingAIConversation = false
            state.showingAIResponse = false
            state.activeAgentChatPillID = nil
            // Also clear conversationSurface so a stale .agent(id) doesn't keep
            // hasVisibleConversation true. Without this, canRestoreVisibleConversation
            // treats the dead agent surface as restorable and the next Ask Omi open
            // restores into a blank response panel instead of a fresh input.
            state.conversationSurface = .closed
            state.isAILoading = false
            state.isHoveringBar = false
            state.requiresHoverReset = true
        }
        // Suppress hover resizes while the close animation plays, otherwise onHover
        // fires mid-animation, reads an intermediate frame, and causes position drift.
        suppressHoverResize = true

        // Determine the target origin for the collapsed pill.
        // Non-draggable: always use the fixed default position so the pill never drifts,
        // regardless of where the expanded window ended up (anchorTop grows downward,
        // so the window center shifts — anchoring from center would land in the wrong spot).
        // Draggable + preChatCenter set: restore to where the bar was before chat opened.
        // Draggable + no preChatCenter: fall back to current center-anchor (best effort).
        // Notch mode restores the FIXED idle/hover surface frame, not the bare
        // collapsed chrome — hover expansion never resizes the panel again.
        let surfaceSize = notchModeEnabled ? notchFixedIdleSurfaceSize() : collapsedBarSize
        let size = responseGlowWindowSizeForCurrentScreen(forSurfaceSize: surfaceSize)
        let restoreOrigin: NSPoint
        if !ShortcutSettings.shared.draggableBarEnabled || notchModeEnabled {
            restoreOrigin = defaultTopCenteredFrame(for: size).origin
        } else if let center = preChatCenter {
            restoreOrigin = NSPoint(x: center.x - size.width / 2, y: center.y - size.height / 2)
        } else {
            restoreOrigin = NSPoint(x: frame.midX - size.width / 2, y: frame.midY - size.height / 2)
        }

        resizeWorkItem?.cancel()
        resizeWorkItem = nil
        styleMask.remove(.resizable)
        isResizingProgrammatically = true
        // Record the animation target so savePreChatCenterIfNeeded() can snap to it
        // if a new PTT query fires while this restore animation is still running.
        pendingRestoreOrigin = restoreOrigin
        animateFrame(to: NSRect(origin: restoreOrigin, size: size), duration: Self.askOmiAnimationDuration)
        let targetFrame = NSRect(origin: restoreOrigin, size: size)
        preChatCenter = nil
        DispatchQueue.main.asyncAfter(deadline: .now() + Self.askOmiSettleDelay) { [weak self] in
            guard let self = self else { return }
            guard self.resignKeyAnimationToken == closeAnimationToken else { return }
            self.isResizingProgrammatically = false
            self.pendingRestoreOrigin = nil
            // Safety net: only snap if no new AI session was opened while the close settled.
            // Without this guard, a rapid PTT query that fires while close settles gets collapsed
            // back to the pill position by this stale completion block.
            guard !self.state.showingAIConversation else { return }
            if !NSEqualRects(self.frame, targetFrame) {
                self.setFrame(targetFrame, display: true, animate: false)
            }
        }

        // Allow hover resizes again after the animation settles.
        DispatchQueue.main.asyncAfter(deadline: .now() + Self.askOmiSettleDelay) { [weak self] in
            guard let self = self else { return }
            guard self.resignKeyAnimationToken == closeAnimationToken else { return }
            self.suppressHoverResize = false
            FloatingControlBarManager.shared.flushQueuedNotificationsIfPossible()

            // If the user has the bar disabled, hide it completely after closing the
            // AI conversation instead of leaving the compact pill visible — unless a
            // queued notification was just flushed; hiding now would swallow it, and
            // its dismissal re-hides the bar anyway.
            if !FloatingControlBarManager.shared.isEnabled && self.state.currentNotification == nil {
                self.orderOut(nil)
            }
        }
    }

    private func hideBar() {
        retractIntoNotch { [weak self] in
            guard let self else { return }
            self.orderOut(nil)
            AnalyticsManager.shared.floatingBarToggled(visible: false, source: self.state.showingAIConversation ? "escape_ai" : "bar_button")
            self.onHide?()
        }
    }

    // MARK: - Public State Updates

    func updateRecordingState(isRecording: Bool, duration: Int, isInitialising: Bool) {
        state.isRecording = isRecording
        state.duration = duration
        state.isInitialising = isInitialising
    }

    func showAIConversation() {
        resizeWorkItem?.cancel()
        resizeWorkItem = nil
        makeKeyAndOrderFront(nil)

        let shouldRestoreVisibleConversation = state.canRestoreVisibleConversation
        if !shouldRestoreVisibleConversation && state.hasVisibleConversation {
            state.clearVisibleConversation()
        }

        // Resize window BEFORE changing state so SwiftUI content doesn't render
        // in the old 28x28 frame (which causes a visible jump).
        // Save center so we can restore exact position when chat closes (avoids drift).
        preChatCenter = NSPoint(x: frame.midX, y: frame.midY)

        if shouldRestoreVisibleConversation {
            cancelInputHeightObserver()
            OmiMotion.withGated(.easeOut(duration: 0.08)) {
                state.present(.mainResponse)
                state.isAILoading = false
            }
            // Notch mode snaps: the fixed idle/hover frame is usually LARGER
            // than the response surface, and an animated shrink would flash
            // the geometry-driven black surface at full height first. The
            // frame delta is all transparent margin, so the snap is invisible.
            resizeToResponseHeight(animated: !notchModeEnabled)
            // Mid-stream close cancels the floating binder; re-subscribe so the
            // restored viewport tracks provider updates within the 10-min window.
            FloatingControlBarManager.shared.reobserveStreamingTurnIfNeeded(in: self)
        } else {
            // Anchor from top so the control bar stays visually in place, input grows downward.
            // Notch mode snaps instead of animating: the window is coming DOWN
            // from the fixed idle/hover frame, and an animated shrink would
            // flash the geometry-driven black surface at full height before it
            // contracts. The frame delta is all transparent margin, so the
            // snap is invisible; the content transition carries the open.
            let inputSize = NSSize(width: expandedContentWidth, height: inputPanelHeight)
            if notchModeEnabled {
                state.notchRevealProgress = 1
            }
            resizeAnchored(
                to: inputSize,
                makeResizable: false,
                animated: !notchModeEnabled,
                animationDuration: Self.askOmiAnimationDuration,
                anchorTop: true
            )

            OmiMotion.withGated(.easeOut(duration: Self.askOmiAnimationDuration)) {
                state.present(.mainInput)
                state.isAILoading = false
                state.setLocalAnswerOverride(nil)
                // Match the explicit resize height so the observer doesn't immediately override it
                state.inputViewHeight = inputPanelHeight
            }
            setupInputHeightObserver()
        }

        // Fallback: explicitly focus the input after SwiftUI layout settles.
        // The AutoFocusScrollView.viewDidMoveToWindow() fires once and can miss
        // if the window isn't yet key at that moment.
        DispatchQueue.main.async { [weak self] in
            self?.focusInputField()
        }

    }

    func leaveAgentConversation() {
        if !AgentPillsManager.shared.pills.isEmpty {
            showAgentRowsFromConversation()
        } else {
            showMainConversationFromAgent()
        }
    }

    private func showAgentRowsFromConversation() {
        guard !AgentPillsManager.shared.pills.isEmpty else { return showMainConversationFromAgent() }

        responseHeightCancellable?.cancel()
        responseHeightCancellable = nil
        cancelInputHeightObserver()

        OmiMotion.withGated(.spring(response: 0.22, dampingFraction: 0.9)) {
            state.hideConversationSurface()
        }
        if notchModeEnabled {
            openNotchHoverMenuUntilExit()
        } else {
            setPillAgentListVisible(true)
        }
    }

    private func showMainConversationFromAgent() {
        guard state.activeAgentChatPillID != nil else {
            closeAIConversation()
            return
        }

        state.leaveAgentSurface()
        if state.conversationSurface == .mainInput {
            resizeForMainInputAfterAgentExit()
        } else {
            resizeForActiveAgentChatPublic(pillID: nil, animated: true)
        }
        focusInputField()
    }

    private func animateNotchReveal(from sourceSize: NSSize, to targetSize: NSSize, duration: TimeInterval) {
        let startWidth = max(notchSize(active: false).width, min(sourceSize.width, targetSize.width))
        let startHeight = max(notchChromeHeightForCurrentScreen, min(sourceSize.height, targetSize.height))
        let widthProgress = targetSize.width > 0 ? startWidth / targetSize.width : 1
        let heightProgress = targetSize.height > 0 ? startHeight / targetSize.height : 1
        let startProgress = min(1, max(0.001, min(widthProgress, heightProgress)))

        frameAnimationToken += 1
        let token = frameAnimationToken
        state.notchRevealProgress = startProgress

        OmiMotion.withGated(.easeOut(duration: duration)) {
            state.notchRevealProgress = 1
        }

        DispatchQueue.main.asyncAfter(deadline: .now() + duration) { [weak self] in
            guard let self, self.frameAnimationToken == token else { return }
            self.state.notchRevealProgress = 1
        }
    }

    func clearVisibleConversationFromUI() {
        guard state.showingAIConversation else { return }

        if state.activeAgentChatPillID != nil {
            leaveAgentConversation()
            return
        }

        FloatingControlBarManager.shared.cancelChat()
        FloatingControlBarManager.shared.clearPendingNotificationContext()
        responseHeightCancellable?.cancel()
        responseHeightCancellable = nil
        cancelInputHeightObserver()

        OmiMotion.withGated(.spring(response: 0.22, dampingFraction: 0.9)) {
            state.clearVisibleConversation()
            state.present(.mainInput)
            state.inputViewHeight = inputPanelHeight
        }

        let inputSize = NSSize(width: expandedContentWidth, height: inputPanelHeight)
        resizeAnchored(to: inputSize, makeResizable: false, animated: true, anchorTop: true)
        setupInputHeightObserver()

        DispatchQueue.main.asyncAfter(deadline: .now() + Self.askOmiSettleDelay) { [weak self] in
            self?.focusInputField()
        }
    }

    private func setupInputHeightObserver() {
        inputHeightCancellable?.cancel()
        inputHeightCancellable = state.$inputViewHeight
            .removeDuplicates()
            .debounce(for: .milliseconds(50), scheduler: DispatchQueue.main)
            .sink { [weak self] height in
                guard let self = self,
                      self.state.showingAIConversation,
                      !self.state.showingAIResponse
                else { return }
                self.resizeToFixedHeight(height)
            }
    }

    func cancelInputHeightObserver() {
        inputHeightCancellable?.cancel()
        inputHeightCancellable = nil
    }

    func updateAIResponse(type: String, text: String) {
        guard state.showingAIConversation else { return }

        switch type {
        case "data":
            if state.isAILoading {
                OmiMotion.withGated(.spring(response: 0.24, dampingFraction: 0.9)) {
                    state.isAILoading = false
                    state.present(.mainResponse)
                }
                resizeToResponseHeight(animated: true)
            }
            state.appendLocalAnswerText(text)
        case "done":
            OmiMotion.withGated(.easeOut(duration: 0.12)) {
                state.isAILoading = false
            }
            if !text.isEmpty {
                state.replaceLocalAnswerText(text)
            }
        case "error":
            OmiMotion.withGated(.easeOut(duration: 0.12)) {
                state.isAILoading = false
            }
            state.replaceLocalAnswerText(text.isEmpty ? "An unknown error occurred." : text)
        default:
            break
        }
    }

    // MARK: - Window Geometry

    private func resizeAnchored(
        to size: NSSize,
        makeResizable: Bool,
        animated: Bool = false,
        animationDuration: TimeInterval = 0.3,
        anchorTop: Bool = false
    ) {
        // Cancel any pending resizeToFixedHeight work item to prevent stale resizes
        resizeWorkItem?.cancel()
        resizeWorkItem = nil
        updateNotchIslandState()
        self.level = notchModeEnabled ? .statusBar : .floating

        let windowSize = responseGlowWindowSizeForCurrentScreen(forSurfaceSize: size)
        let constrainedSize = NSSize(
            width: max(windowSize.width, FloatingControlBarWindow.minBarSize.width),
            height: max(windowSize.height, FloatingControlBarWindow.minBarSize.height)
        )
        let transitionAnchor: FloatingControlBarGeometry.TransitionAnchor
        if anchorTop, notchModeEnabled, let screenFrame = screenForPlacement?.frame {
            // A notch island is fixed to its display's camera housing. Never
            // carry a transient animation offset into its next surface state.
            transitionAnchor = .screenTopCenter(screenFrame)
        } else if anchorTop {
            transitionAnchor = .topCenter
        } else {
            transitionAnchor = .center
        }
        let targetFrame = FloatingControlBarGeometry.targetFrame(
            currentFrame: frame,
            targetSize: constrainedSize,
            anchor: transitionAnchor
        )
        resizeToFrame(
            targetFrame,
            makeResizable: makeResizable,
            animated: animated,
            animationDuration: animationDuration
        )
    }

    /// Applies a semantic PTT/agent-switcher transition. These states must not
    /// choose their anchor through a generic resize call: notch surfaces always
    /// return to the display camera housing, while pill surfaces preserve or
    /// restore the user's position according to their transition contract.
    private func resizeSurfaceTransition(
        _ transition: FloatingControlBarGeometry.SurfaceTransition,
        toSurfaceSize size: NSSize,
        animated: Bool,
        animationDuration: TimeInterval
    ) {
        resizeWorkItem?.cancel()
        resizeWorkItem = nil
        updateNotchIslandState()
        level = notchModeEnabled ? .statusBar : .floating

        let windowSize = responseGlowWindowSizeForCurrentScreen(forSurfaceSize: size)
        let constrainedSize = NSSize(
            width: max(windowSize.width, Self.minBarSize.width),
            height: max(windowSize.height, Self.minBarSize.height)
        )
        let placement: FloatingControlBarGeometry.SurfacePlacement = notchModeEnabled
            ? .notch(screenFrame: screenForPlacement?.frame)
            : .pill(
                draggable: ShortcutSettings.shared.draggableBarEnabled,
                canonicalCompactFrame: canonicalCollapsedPillFrame()
            )
        let targetFrame = FloatingControlBarGeometry.surfaceTransitionFrame(
            currentFrame: frame,
            targetSize: constrainedSize,
            transition: transition,
            placement: placement
        )
        resizeToFrame(
            targetFrame,
            makeResizable: false,
            animated: animated,
            animationDuration: animationDuration
        )
    }

    private func resizeToFrame(
        _ targetFrame: NSRect,
        makeResizable: Bool,
        animated: Bool = false,
        animationDuration: TimeInterval = 0.18
    ) {
        let wasResizable = styleMask.contains(.resizable)
        if makeResizable {
            styleMask.insert(.resizable)
        } else {
            styleMask.remove(.resizable)
        }

        let alreadyAtTarget = Self.framesEquivalent(frame, targetFrame)
        let alreadyAnimatingToTarget = pendingFrameAnimationTarget.map {
            Self.framesEquivalent($0, targetFrame)
        } ?? false

        if alreadyAtTarget, wasResizable == makeResizable {
            frameAnimationToken += 1
            pendingFrameAnimationTarget = nil
            isResizingProgrammatically = false
            return
        }
        if alreadyAnimatingToTarget, wasResizable == makeResizable {
            return
        }

        log("FloatingControlBar: resizeToFrame to \(targetFrame.size) resizable=\(makeResizable) animated=\(animated) from=\(frame.size)")

        isResizingProgrammatically = true

        if animated {
            // Keep windowDidResize from persisting transient animation frames as
            // the user's saved response size until the final frame lands.
            animateFrame(to: targetFrame, duration: animationDuration) { [weak self] in
                self?.isResizingProgrammatically = false
            }
        } else {
            self.setFrame(targetFrame, display: true, animate: false)
            self.isResizingProgrammatically = false
        }
    }

    private static func framesEquivalent(_ lhs: NSRect, _ rhs: NSRect) -> Bool {
        abs(lhs.origin.x - rhs.origin.x) <= frameNoopEpsilon
            && abs(lhs.origin.y - rhs.origin.y) <= frameNoopEpsilon
            && abs(lhs.size.width - rhs.size.width) <= frameNoopEpsilon
            && abs(lhs.size.height - rhs.size.height) <= frameNoopEpsilon
    }

    private func animateFrame(to frame: NSRect, duration: TimeInterval, completion: (() -> Void)? = nil) {
        frameAnimationToken += 1
        let token = frameAnimationToken
        pendingFrameAnimationTarget = frame

        // Reduce Motion (or zero duration): land on the final frame directly.
        guard duration > 0, !OmiMotion.reduceMotion else {
            setFrame(frame, display: true, animate: false)
            pendingFrameAnimationTarget = nil
            completion?()
            return
        }

        // Core Animation drives the interpolation on the display link — unlike a
        // GCD-timer step loop it stays smooth while SwiftUI re-lays-out the
        // content mid-resize, and starting a new group retargets the in-flight
        // animation from its current frame instead of jumping.
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = duration
            context.timingFunction = CAMediaTimingFunction(name: .easeOut)
            context.allowsImplicitAnimation = true
            self.animator().setFrame(frame, display: true)
        }, completionHandler: { [weak self] in
            guard let self, self.frameAnimationToken == token else { return }
            self.setFrame(frame, display: true, animate: false)
            self.pendingFrameAnimationTarget = nil
            completion?()
        })
    }

    private func resizeToFixedHeight(_ height: CGFloat, animated: Bool = false) {
        resizeWorkItem?.cancel()
        let width = expandedContentWidth
        let size = NSSize(width: width, height: height)
        resizeWorkItem = DispatchWorkItem { [weak self] in
            self?.resizeAnchored(to: size, makeResizable: false, animated: animated, anchorTop: true)
        }
        if let workItem = resizeWorkItem {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05, execute: workItem)
        }
    }

    private func defaultAutoResponseMaxHeight() -> CGFloat {
        let screenHeight = (screenForPlacement ?? screen ?? NSScreen.main)?.visibleFrame.height
            ?? NSScreen.screens.first?.visibleFrame.height
            ?? Self.defaultBaseResponseHeight
        return max(Self.minResponseHeight, floor(screenHeight / 3))
    }

    private func storedResponseSurfaceSize() -> NSSize? {
        guard let rawSize = UserDefaults.standard.string(forKey: Self.sizeKey) else {
            return nil
        }

        let size = NSSizeFromString(rawSize)
        guard size.width >= expandedContentWidth - 1,
              size.height > Self.minResponseHeight + 2
        else {
            UserDefaults.standard.removeObject(forKey: Self.sizeKey)
            return nil
        }

        return size
    }

    private func responseHeightConfiguration() -> (initialHeight: CGFloat, maxHeight: CGFloat) {
        let savedSize = storedResponseSurfaceSize()
        let defaultCap = defaultAutoResponseMaxHeight()
        if let savedSize {
            // Clamp the persisted height to the current screen's cap so a tall
            // saved value from a larger display cannot be restored oversized on
            // a smaller screen. (Cubic P2 — cross-monitor sizing consistency.)
            let savedHeight = min(max(Self.minResponseHeight, savedSize.height), defaultCap)
            return (savedHeight, defaultCap)
        }
        return (min(Self.defaultBaseResponseHeight, defaultCap), defaultCap)
    }

    /// Hover expand/collapse. Notch mode never resizes the panel here (fixed
    /// window, animated content); the pill resize is anchored from center so
    /// the circle grows outward.
    /// Returns false when a guard skipped the expansion; the view must not
    /// render expanded hover content in that case, or the oversized SwiftUI
    /// content force-grows the window with the origin pinned (a rightward
    /// drift).
    @discardableResult
    func resizeForHover(expanded: Bool) -> Bool {
        guard !state.showingAIConversation, !state.isVoiceListening, !state.isVoiceResponseGlowActive, !state.isShowingNotification, !suppressHoverResize else { return false }
        // The pill agent list owns the window size while open; hover
        // exits must not collapse it out from under the list.
        guard notchModeEnabled || !state.isNotchHoverMenuVisible else { return false }
        guard !notchModeEnabled else {
            // Fixed window, animated content: hover expand/collapse never
            // touches the NSPanel frame. Re-assert the fixed idle/hover
            // surface (a no-op in steady state) and let the SwiftUI content
            // morph carry the visible transition.
            assertNotchFixedHoverSurfaceFrame()
            return true
        }
        resizeWorkItem?.cancel()
        resizeWorkItem = nil

        let targetSize = expanded ? FloatingControlBarWindow.expandedBarSize : FloatingControlBarWindow.minBarSize

        let doResize: () -> Void = { [weak self] in
            guard let self = self else { return }
            guard !self.state.showingAIConversation,
                  !self.state.isVoiceListening,
                  !self.state.isVoiceResponseGlowActive,
                  !self.state.isShowingNotification,
                  !self.suppressHoverResize
            else { return }
            // Expand grows outward from the current center; collapse snaps
            // back to the canonical pill position so transient layout forces
            // can never permanently drift the pill sideways.
            let targetFrame = expanded
                ? FloatingControlBarGeometry.centerAnchoredFrame(
                    currentFrame: self.frame,
                    targetSize: targetSize
                )
                : self.canonicalCollapsedPillFrame()
            self.styleMask.remove(.resizable)
            self.isResizingProgrammatically = true
            self.setFrame(targetFrame, display: true, animate: false)
            self.isResizingProgrammatically = false
        }

        if expanded {
            // Expand synchronously so the window is already large enough when
            // SwiftUI re-evaluates body with isHovering=true. If this were async,
            // the 50px expanded content renders in the still-22px window, causing
            // the tracking area to invalidate and trigger immediate unhover — producing
            // a flicker loop when hovering from the top or bottom edge.
            doResize()
        } else {
            // Collapse async to avoid blocking SwiftUI body evaluation during unhover.
            // Cancellable via resizeWorkItem so rapid hover in/out doesn't queue stale
            // resizes. (OMI-COMPUTER-1PT)
            resizeWorkItem = DispatchWorkItem(block: doResize)
            DispatchQueue.main.async(execute: resizeWorkItem!)
        }
        return true
    }

    /// Canonical collapsed-pill frame on displays without a notch: the user's
    /// saved (dragged) position when draggable, otherwise the default
    /// top-center. Collapse-to-idle transitions snap here so transient layout
    /// forces (e.g. oversized content briefly growing the window with the
    /// origin pinned) can never permanently drift the pill sideways.
    private func canonicalCollapsedPillFrame() -> NSRect {
        let windowSize = responseGlowWindowSizeForCurrentScreen(forSurfaceSize: collapsedBarSize)
        if ShortcutSettings.shared.draggableBarEnabled,
           let saved = UserDefaults.standard.string(forKey: Self.positionKey) {
            let origin = NSPointFromString(saved)
            if origin != .zero {
                // Saved origins are recorded for the bare pill; keep the pill's
                // top-center fixed when the glow outset inflates the window.
                let bare = Self.minBarSize
                let topCenter = NSPoint(x: origin.x + bare.width / 2, y: origin.y + bare.height)
                return NSRect(
                    x: topCenter.x - windowSize.width / 2,
                    y: topCenter.y - windowSize.height,
                    width: windowSize.width,
                    height: windowSize.height
                )
            }
        }
        return NSRect(origin: defaultTopCenteredOrigin(for: windowSize), size: windowSize)
    }

    /// Gives the subagent switcher enough room to unfurl into a centered
    /// stacked list without opening the full chat surface. In notch mode the
    /// window already holds the fixed maximum hover surface, so this only
    /// re-asserts that frame; the pill window still resizes, skipping glow
    /// outsets.
    func resizeForAgentSwitcher(visible: Bool) {
        guard !state.showingAIConversation,
              !state.isVoiceListening,
              !state.isShowingNotification,
              !suppressHoverResize
        else { return }

        if notchModeEnabled {
            // Fixed window, animated content — the switcher open/close is a
            // pure SwiftUI morph; the frame move below is a no-op unless we
            // are returning from a differently-sized surface (e.g. chat).
            assertNotchFixedHoverSurfaceFrame()
            return
        }

        if visible {
            let expandedSize = pillAgentListWindowSize(agentCount: AgentPillsManager.shared.pills.count)
            resizeSurfaceTransition(
                .agentSwitcher(visible: true),
                toSurfaceSize: expandedSize,
                animated: true,
                animationDuration: Self.notchHoverMenuExpandDuration
            )
        } else {
            resizeSurfaceTransition(
                .agentSwitcher(visible: false),
                toSurfaceSize: collapsedBarSize,
                animated: true,
                animationDuration: Self.notchHoverMenuCollapseDuration
            )
        }
    }

    /// Window size for the pill-mode agent list. No chrome band and no glow
    /// outsets — the surface starts at a slim top inset and fills the window.
    private func pillAgentListWindowSize(agentCount: Int) -> NSSize {
        NSSize(
            width: Self.notchExpandedWidth,
            height: Self.pillSurfaceTopPadding + Self.notchHoverMenuHeight(agentCount: agentCount)
        )
    }

    private var pillListCollapseWorkItem: DispatchWorkItem?

    /// Hover-driven agent list open/close for displays without a notch —
    /// the pill-mode analog of the notch hover menu. Opens when the pointer
    /// enters the pill, collapses when it leaves (see
    /// `schedulePillAgentListCollapse`), and also closes on esc, click-away,
    /// selecting an agent, or the last agent ending.
    func setPillAgentListVisible(_ visible: Bool) {
        guard !notchModeEnabled else { return }
        pillListCollapseWorkItem?.cancel()
        pillListCollapseWorkItem = nil
        let allowed = visible
            && state.canShowNotchHoverMenu
            && !AgentPillsManager.shared.pills.isEmpty
        guard state.notchHoverMenuOpen != allowed else { return }

        if allowed {
            // Resize before flipping state so the expanded list never renders
            // in a too-small window (same ordering as the hover-expand path).
            resizeForAgentSwitcher(visible: true)
            state.setNotchHoverMenuOpen(true)
        } else {
            state.setNotchHoverMenuOpen(false)
            resizeForAgentSwitcher(visible: false)
        }
    }

    /// Collapse the pill agent list shortly after the pointer leaves it.
    /// Delayed with a global-mouse recheck because SwiftUI hover events
    /// flicker while the window resizes underneath the cursor.
    func schedulePillAgentListCollapse() {
        guard !notchModeEnabled, state.isNotchHoverMenuVisible else { return }
        pillListCollapseWorkItem?.cancel()
        let workItem = DispatchWorkItem { [weak self] in
            guard let self, self.state.isNotchHoverMenuVisible else { return }
            let mouse = NSEvent.mouseLocation
            guard !self.frame.insetBy(dx: -8, dy: -8).contains(mouse) else { return }
            self.setPillAgentListVisible(false)
        }
        pillListCollapseWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.18, execute: workItem)
    }

    /// Resize window for PTT state (expanded when listening, compact circle when idle)
    func resizeForPTTState(expanded: Bool) {
        if notchModeEnabled {
            if state.showingAIConversation {
                return
            }
            // Collapse returns to the FIXED idle/hover surface frame (not the
            // bare collapsed island) so the next hover expand stays a pure
            // content morph with no window resize.
            let targetSize = expanded ? notchSize(active: true) : notchFixedIdleSurfaceSize()
            resizeSurfaceTransition(
                .pushToTalk(expanded: expanded),
                toSurfaceSize: targetSize,
                animated: true,
                animationDuration: Self.askOmiAnimationDuration
            )
            return
        }
        // On legacy displays, when the voice-response glow is still active
        // (e.g. realtime audio received this turn), collapse to the glow-adjusted
        // compact size so the white glow/stroke is not clipped until the idle
        // timer clears it.
        resizeSurfaceTransition(
            .pushToTalk(expanded: expanded),
            toSurfaceSize: expanded ? Self.voiceBarSize : Self.minBarSize,
            animated: true,
            animationDuration: 0.18
        )
    }

    /// Size the notch to fit the "thinking" indicator (active width) while a PTT
    /// query is being processed, then collapse it back once the response takes
    /// over. Voice listening and the open conversation surface own sizing while
    /// they are active, so this defers to them.
    /// Single authority for the pill ↔ notch-island morph across the active PTT
    /// lifecycle (idle pill → listening → thinking → answering → idle pill).
    /// Called whenever any active flag changes. Because notchModeEnabled is
    /// active-aware, this engages the island on external monitors too.
    func syncActiveIsland() {
        // The chat panel and notifications own their own geometry.
        guard !state.showingAIConversation, state.currentNotification == nil else { return }
        guard let screen = screenForPlacement else { return }

        let wasIsland = state.usesNotchIsland
        updateNotchIslandState()  // sets state.usesNotchIsland + level from notchModeEnabled
        let island = state.usesNotchIsland
        let target = activeIslandTargetFrame(on: screen, island: island)

        if wasIsland != island && island {
            // Idle pill → active island: grow with the reveal pop.
            styleMask.remove(.resizable)
            animateGrowOutFromNotch(to: target)
        } else if wasIsland != island && !island {
            // Active island → idle pill: shrink back to the resting pill at the
            // exact spot it left from (fall back to the computed top-center).
            state.notchRevealProgress = 1
            let pillFrame: NSRect
            if let saved = savedPillFrame {
                pillFrame = NSRect(origin: saved.origin, size: target.size)
                savedPillFrame = nil
            } else {
                pillFrame = target
            }
            resizeToFrame(pillFrame, makeResizable: false, animated: true, animationDuration: 0.16)
        } else {
            // Same mode, different sub-state (e.g. listening → thinking).
            resizeToFrame(target, makeResizable: false, animated: true, animationDuration: Self.askOmiAnimationDuration)
        }
    }

    /// The window frame for the current active sub-state, in the given mode.
    private func activeIslandTargetFrame(on screen: NSScreen, island: Bool) -> NSRect {
        let size: NSSize
        if island {
            let base: NSSize
            if state.isVoiceListening {
                base = notchSize(sideWidth: Self.notchActiveSideWidth, for: screen)
            } else if state.isThinking || state.isVoiceResponseWaiting {
                base = notchSize(sideWidth: Self.notchThinkingSideWidth, for: screen)
            } else if state.isVoiceResponseGlowActive {
                // Answering (voice-response glow) — collapsed island.
                base = notchCollapsedSize(for: screen)
            } else {
                // Active lifecycle over — restore the fixed idle/hover surface
                // frame so the next hover expand needs no window resize.
                base = notchFixedIdleSurfaceSize(for: screen)
            }
            size = responseGlowWindowSize(forSurfaceSize: base, usesNotchIsland: true)
        } else {
            size = state.isVoiceListening ? Self.voiceBarSize : Self.minBarSize
        }
        return NSRect(
            origin: topCenteredOrigin(for: size, on: screen, usesNotchIsland: island),
            size: size
        )
    }

    /// Pop the notch in from a near-zero scale the first time it is revealed via
    /// Push-to-Talk (it stays hidden at launch on notched displays).
    func playNotchRevealAnimation() {
        guard notchModeEnabled else { return }
        state.notchRevealProgress = 0.01
        OmiMotion.withGated(.easeOut(duration: 0.24)) {
            state.notchRevealProgress = 1
        }
    }

    /// Mirror of the reveal: shrink the island back into the camera housing,
    /// then order the window out. Non-notch surfaces (and Reduce Motion) skip
    /// straight to the completion.
    func retractIntoNotch(then completion: @escaping () -> Void) {
        guard notchModeEnabled, isVisible, !OmiMotion.reduceMotion else {
            completion()
            return
        }
        frameAnimationToken += 1
        let token = frameAnimationToken
        OmiMotion.withGated(.easeIn(duration: 0.18)) {
            state.notchRevealProgress = 0.01
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.18) { [weak self] in
            guard let self, self.frameAnimationToken == token else { return }
            completion()
            // Leave the island ready to render for show paths that skip the
            // reveal (e.g. showTemporarily) — the next reveal re-zeroes it.
            self.state.notchRevealProgress = 1
        }
    }

    func showNotification(_ notification: FloatingBarNotification, animated: Bool = true) {
        guard !state.showingAIConversation else { return }
        state.currentNotification = notification
        let barHeight = notchModeEnabled
            ? notchChromeHeightForCurrentScreen
            : (state.isHoveringBar ? Self.expandedBarSize.height : Self.minBarSize.height)
        let targetSize = NSSize(
            width: Self.notificationWidth,
            height: barHeight + Self.notificationSpacing + Self.notificationHeight
        )
        resizeAnchored(to: targetSize, makeResizable: false, animated: animated, anchorTop: true)
    }

    func dismissNotification(animated: Bool = true) {
        guard state.currentNotification != nil else { return }
        state.currentNotification = nil

        let targetSize: NSSize
        if state.isVoiceListening && !notchModeEnabled {
            targetSize = Self.voiceBarSize
        } else if notchModeEnabled && !state.isVoiceListening {
            // Return to the fixed idle/hover surface frame.
            targetSize = notchFixedIdleSurfaceSize()
        } else {
            targetSize = state.isHoveringBar && !notchModeEnabled ? Self.expandedBarSize : collapsedBarSize
        }
        resizeAnchored(to: targetSize, makeResizable: false, animated: animated, anchorTop: true)
    }

    /// Restore the compact pill size when we temporarily surface the bar outside
    /// of an active hover, notification, voice session, or AI conversation.
    func normalizeForTemporaryShow() {
        guard !state.showingAIConversation, !state.isVoiceListening, state.currentNotification == nil else { return }
        resizeAnchored(
            to: notchModeEnabled ? notchFixedIdleSurfaceSize() : collapsedBarSize,
            makeResizable: false,
            animated: false,
            anchorTop: true
        )
    }

    var hasSettledClosedForAutomation: Bool {
        let settledSize = responseGlowWindowSizeForCurrentScreen(
            forSurfaceSize: notchModeEnabled ? notchFixedIdleSurfaceSize() : collapsedBarSize
        )
        return !state.showingAIConversation
            && !suppressHoverResize
            && pendingRestoreOrigin == nil
            && NSEqualSizes(frame.size, settledSize)
    }

    private func resizeToResponseHeight(animated: Bool = false) {
        let responseHeight = responseHeightConfiguration()

        // Preserve manual response sizing across follow-up sends. The window may
        // include glow padding, so compare and resize using the underlying black
        // response surface rather than the inflated NSWindow frame.
        let startWidth = max(expandedContentWidth, currentResponseSurfaceWidth())
        let startHeight = max(responseHeight.initialHeight, currentResponseSurfaceHeight())
        let initialSize = NSSize(width: startWidth, height: startHeight)
        resizeAnchored(to: initialSize, makeResizable: true, animated: animated, anchorTop: true)
        state.present(.mainResponse)
        setupResponseHeightObserver(for: .mainResponse, maxHeight: responseHeight.maxHeight)
    }

    private func beginMainResponseHeight(animated: Bool = false) {
        let responseHeight = responseHeightConfiguration()
        let initialSize = NSSize(width: expandedContentWidth, height: responseHeight.initialHeight)
        resizeAnchored(to: initialSize, makeResizable: true, animated: animated, anchorTop: true)
        state.present(.mainResponse)
        setupResponseHeightObserver(for: .mainResponse, maxHeight: responseHeight.maxHeight)
    }

    /// Observes the active surface's measured content height and expands the
    /// window to fit it, capped at `maxHeight`. Never shrinks automatically.
    private func setupResponseHeightObserver(
        for surface: FloatingConversationSurface,
        maxHeight: CGFloat
    ) {
        responseHeightCancellable?.cancel()
        let key = surface.measurementKey
        responseHeightCancellable = state.$responseContentHeights
            .map { $0[key] ?? 0 }
            .removeDuplicates()
            .debounce(for: .milliseconds(80), scheduler: DispatchQueue.main)
            .sink { [weak self] contentHeight in
                guard let self = self,
                      self.state.conversationSurface == surface,
                      !self.isUserResizing,
                      contentHeight > 0
                else { return }
                let targetHeight = (contentHeight + Self.responseViewOverhead).rounded(.up)
                let steppedHeight = (targetHeight / Self.responseStreamingResizeStep).rounded(.up) * Self.responseStreamingResizeStep
                let clampedHeight = min(max(steppedHeight, Self.minResponseHeight), maxHeight)
                // Only expand, never auto-shrink. In notch mode an active voice
                // response glow inflates the window frame, so compare content
                // growth against the underlying response surface height rather
                // than the glow-padded window height.
                guard clampedHeight > self.currentResponseSurfaceHeight() + 2 else { return }
                self.resizeAnchored(
                    to: NSSize(width: max(self.expandedContentWidth, self.currentResponseSurfaceWidth()), height: clampedHeight),
                    makeResizable: true,
                    animated: false,
                    anchorTop: true
                )
            }
    }

    /// Compute the default origin for the collapsed pill (top-center of the key screen).
    /// Used by closeAIConversation in non-draggable mode and centerOnMainScreen.
    private func defaultPillOrigin() -> NSPoint {
        defaultTopCenteredFrame(for: collapsedBarSize).origin
    }

    private func defaultTopCenteredFrame(for size: NSSize) -> NSRect {
        if notchModeEnabled, let screen = screenForPlacement {
            return NSRect(
                origin: topCenteredOrigin(for: size, on: screen, usesNotchIsland: true),
                size: size
            )
        }
        return FloatingControlBarGeometry.defaultPillFrame(
            size: size,
            visibleFrame: geometryScreenVisibleFrame(),
            topInset: topInsetForPillFallback
        )
    }

    private func defaultTopCenteredOrigin(for size: NSSize) -> NSPoint {
        defaultTopCenteredFrame(for: size).origin
    }

    private func geometryScreenVisibleFrame() -> NSRect {
        let targetScreen = self.screen ?? NSApp.keyWindow?.screen ?? NSScreen.main ?? NSScreen.screens.first
        return targetScreen?.visibleFrame ?? .zero
    }

    private var topInsetForPillFallback: CGFloat {
        Self.topInsetWhenNotchModeFallsBackToPill
    }

    /// Center the bar near the top of the main screen.
    private func centerOnMainScreen() {
        // Use the screen that has the key window, or fall back to main screen
        let targetScreen = NSApp.keyWindow?.screen ?? NSScreen.main ?? NSScreen.screens.first
        guard let screen = targetScreen else {
            self.center()
            return
        }
        if notchModeEnabled {
            let targetFrame = frameForCurrentState(on: screen, usesNotchIsland: true)
            self.setFrame(targetFrame, display: true, animate: false)
            log("FloatingControlBarWindow: centered notch island at \(targetFrame.origin) on screen \(screen.frame)")
            return
        }
        let origin = FloatingControlBarGeometry.defaultPillFrame(
            size: frame.size,
            visibleFrame: screen.visibleFrame,
            topInset: Self.topInset
        ).origin
        self.setFrameOrigin(origin)
        log("FloatingControlBarWindow: centered at \(origin) on screen \(screen.visibleFrame)")
    }

    func resetPosition() {
        UserDefaults.standard.removeObject(forKey: FloatingControlBarWindow.positionKey)
        centerOnMainScreen()
    }

    /// Called when monitors are connected/disconnected. Re-center if the bar is no longer
    /// fully visible on any screen.
    private func scheduleStartupDisplayRevalidation() {
        startupDisplayRevalidationWorkItems.forEach { $0.cancel() }
        startupDisplayRevalidationWorkItems = Self.startupDisplayRevalidationDelays.map { delay in
            let workItem = DispatchWorkItem { [weak self] in
                Task { @MainActor in
                    self?.validatePositionOnScreenChange(reason: "startup_display_revalidation")
                }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: workItem)
            return workItem
        }
    }

    private func validatePositionOnScreenChange(reason: String) {
        guard !isUserDragging else { return }
        updateNotchIslandState()
        // Non-draggable mode: always restore to default position on screen change
        if !ShortcutSettings.shared.draggableBarEnabled || notchModeEnabled {
            log("FloatingControlBarWindow: re-centering after display revalidation reason=\(reason) usesNotch=\(notchModeEnabled)")
            centerOnMainScreen()
            return
        }

        let barFrame = self.frame
        // Match the clamp approach used elsewhere in this window: prefer an
        // on-screen clamp over unconditional re-centering, so the bar stays
        // near where the user left it when a monitor is plugged/unplugged.
        // visibleFrame already excludes the Dock and menu bar, so clamping
        // also fixes the same Dock-encroachment scenario the rest of the PR
        // addresses.
        if let targetScreen = NSScreen.screens.first(where: { $0.visibleFrame.intersects(barFrame) }) {
            let clamped = FloatingControlBarWindow.clamp(barFrame, to: targetScreen.visibleFrame)
            if clamped != barFrame {
                log("FloatingControlBarWindow: clamping bar \(barFrame) to \(targetScreen.visibleFrame) after display revalidation reason=\(reason)")
                self.setFrameOrigin(clamped.origin)
                UserDefaults.standard.set(NSStringFromPoint(clamped.origin), forKey: FloatingControlBarWindow.positionKey)
            }
        } else {
            log("FloatingControlBarWindow: bar frame \(barFrame) does not intersect any visible screen, re-centering reason=\(reason)")
            UserDefaults.standard.removeObject(forKey: FloatingControlBarWindow.positionKey)
            centerOnMainScreen()
        }
    }

    // MARK: - NSWindowDelegate

    /// A floating panel can move between displays when macOS changes Spaces or
    /// reassigns windows, without emitting a display-configuration change. Keep
    /// the SwiftUI presentation flag and frame in lockstep with the panel's
    /// actual screen so an idle bar cannot render as the legacy pill inside a
    /// notch-sized window (which is visually hidden by the camera housing).
    func windowDidChangeScreen(_ notification: Notification) {
        guard !isUserDragging, let screen = screenForPlacement else { return }

        let previousUsesNotchIsland = state.usesNotchIsland
        updateNotchIslandState()

        // An open chat owns its user-resizable response dimensions. Updating
        // the render mode is sufficient here; rebuilding its frame from the
        // compact-bar defaults would discard that size (and can double-count
        // an active voice-response glow).
        guard !state.showingAIConversation else { return }

        let targetFrame = frameForCurrentState(on: screen, usesNotchIsland: state.usesNotchIsland)
        let requiresFrameRefresh = !Self.framesEquivalent(frame, targetFrame)
        guard previousUsesNotchIsland != state.usesNotchIsland || requiresFrameRefresh else { return }

        resizeToFrame(
            targetFrame,
            makeResizable: state.showingAIConversation && state.showingAIResponse,
            animated: false
        )
        log(
            "FloatingControlBarWindow: reconciled screen change to \(screen.localizedName) "
                + "usesNotch=\(state.usesNotchIsland)"
        )
    }

    func windowDidResignKey(_ notification: Notification) {
        // Only dismiss when the user physically clicks away.
        // Programmatic focus changes — e.g. the AI agent activating a browser
        // window for automation — do NOT produce a mouse-down event, so we
        // leave the conversation open in those cases.
        let eventType = NSApp.currentEvent?.type
        let isMouseClick = eventType == .leftMouseDown
            || eventType == .rightMouseDown
            || eventType == .otherMouseDown

        guard state.showingAIConversation else {
            // The pinned pill agent list (non-notch) has no pointer-exit
            // tracking, so click-away is one of its close affordances.
            if isMouseClick, !notchModeEnabled, state.isNotchHoverMenuVisible {
                setPillAgentListVisible(false)
            }
            return
        }
        guard isMouseClick else { return }

        // Close in-place so the bar collapses smoothly instead of blinking out and back in.
        resignKeyAnimationToken += 1
        closeAIConversation()
    }

    @objc func windowDidMove(_ notification: Notification) {
        // Only persist position when the user is physically dragging the bar.
        // Programmatic moves (resize animations, chat open/close) should not
        // overwrite the saved position — that causes silent drift.
        guard isUserDragging else { return }
        UserDefaults.standard.set(
            NSStringFromPoint(self.frame.origin), forKey: FloatingControlBarWindow.positionKey
        )
    }

    func windowWillResize(_ sender: NSWindow, to frameSize: NSSize) -> NSSize {
        let minimumWidth: CGFloat
        if state.showingAIConversation {
            minimumWidth = expandedContentWidth
        } else if state.currentNotification != nil {
            minimumWidth = FloatingControlBarWindow.notificationWidth
        } else if state.isVoiceListening && !notchModeEnabled {
            minimumWidth = FloatingControlBarWindow.voiceBarSize.width
        } else if state.isHoveringBar {
            minimumWidth = FloatingControlBarWindow.expandedBarSize.width
        } else {
            minimumWidth = collapsedBarSize.width
        }

        return NSSize(
            width: max(frameSize.width, minimumWidth),
            height: max(frameSize.height, FloatingControlBarWindow.minBarSize.height)
        )
    }

    func windowDidResize(_ notification: Notification) {
        // Response size persistence is committed when the user finishes dragging
        // the resize grip. Persisting ordinary resize notifications here records
        // programmatic min-height transitions as user preferences because AppKit
        // can deliver the final resize notification after our animation flag is
        // cleared.
    }

    func finishUserResponseResize() {
        isUserResizing = false
        if state.conversationSurface.isResponseLike {
            persistCurrentResponseSurfaceSize()
        }
    }

    private func persistCurrentResponseSurfaceSize() {
        let size = NSSize(width: currentResponseSurfaceWidth(), height: currentResponseSurfaceHeight())
        guard state.conversationSurface.isResponseLike,
              size.width >= expandedContentWidth - 1,
              size.height >= Self.minResponseHeight
        else {
            UserDefaults.standard.removeObject(forKey: Self.sizeKey)
            return
        }

        UserDefaults.standard.set(NSStringFromSize(size), forKey: FloatingControlBarWindow.sizeKey)
    }
}

// MARK: - FloatingControlBarManager

enum VoiceOwnerBoundDispatch<Value> {
    case rejectedOwnerChange
    case dispatched(Value)
}

enum OwnerBoundNotificationPresentationResult: Equatable {
    case rejectedOwnerChange
    case windowUnavailable
    case suppressed
    case queued
    case presented
}

/// Singleton manager that owns the floating bar window and coordinates with AppState / ChatProvider.
@MainActor
class FloatingControlBarManager {
    static let shared = FloatingControlBarManager()

    private static let kAskOmiEnabled = "askOmiBarEnabled"
    private static let kSnoozedUntil = "floatingBar_snoozedUntil"
    private static let recentNotificationReuseInterval: TimeInterval = 60
    static let snoozeTwoHoursDuration: TimeInterval = 2 * 60 * 60

    struct NotificationProjectionSnapshot: Equatable {
        let queuedCount: Int
        let pendingJournalCount: Int
        let storedJournalCount: Int
    }

    private struct PendingFollowUpQuery {
        let text: String
        let presentation: QueryPresentation
        let voiceTurnID: VoiceTurnID?
    }

    private enum QueryPresentation {
        case visible(fromVoice: Bool)
        case voiceOnly

        var fromVoice: Bool {
            switch self {
            case .visible(let fromVoice):
                return fromVoice
            case .voiceOnly:
                return true
            }
        }
    }

    /// Testable physical provider boundary for non-hub PTT. The turn owner is
    /// checked both before asynchronous preparation and immediately before the
    /// provider dispatch, so an account switch while queued can never submit the
    /// old transcript under the new account.
    static func performOwnerBoundVoiceDispatch<Value>(
        turnID: VoiceTurnID,
        coordinator: VoiceTurnCoordinator? = nil,
        prepare: () async -> Void = {},
        dispatch: () async -> Value
    ) async -> VoiceOwnerBoundDispatch<Value> {
        let coordinator = coordinator ?? .shared
        guard coordinator.requireCurrentOwner(for: turnID) != nil else {
            return .rejectedOwnerChange
        }
        await prepare()
        guard coordinator.requireCurrentOwner(for: turnID) != nil else {
            return .rejectedOwnerChange
        }
        return .dispatched(await dispatch())
    }

    private struct StoredNotificationMessage {
        let ownerID: String
        let context: FloatingBarNotificationContext?
        let messageClientTurnId: String
        let createdAt: Date
    }

    private struct OwnerNotificationKey: Hashable {
        let ownerID: String
        let notificationID: UUID
    }

    private struct PendingNotificationContext {
        let message: ChatMessage
        let context: FloatingBarNotificationContext?
    }

    private var window: FloatingControlBarWindow?
    /// Tracks whether the deferred notch reveal has happened this session for
    /// explicit opt-in contexts such as onboarding/demo/minimal mode.
    private var hasRevealedNotchThisSession = false
    private var snoozeTimer: Timer?
    private var recordingCancellable: AnyCancellable?
    private var durationCancellable: AnyCancellable?
    private var chatCancellable: AnyCancellable?
    private var historyChatProvider: ChatProvider?

    /// Public read-only access to the floating bar's chat provider so the
    /// agent pills manager can inherit the working directory / model.
    var sharedFloatingProvider: ChatProvider? { historyChatProvider }

    /// Public read-only access to the currently-active agent chat pill in the
    /// floating bar, so viewed-pill expiration can skip the one the user is
    /// actively reading.
    var activeAgentChatPillID: UUID? { window?.state.activeAgentChatPillID }

    func openAgentChatFromTimeline(agentID: UUID, completion: ((Bool) -> Void)? = nil) {
        openAgentChatFromTimeline(
            ref: AgentTimelineRef(pillId: agentID, sessionId: nil, runId: nil),
            completion: completion
        )
    }

    func openAgentChatFromTimeline(ref: AgentTimelineRef, completion: ((Bool) -> Void)? = nil) {
        guard let window else {
            completion?(false)
            return
        }
        activeQueryGeneration += 1
        let generation = activeQueryGeneration
        Task { @MainActor in
            let resolved = await AgentPillsManager.shared.resolveAndPresentAgent(
                pillId: ref.pillId,
                sessionId: ref.sessionId,
                runId: ref.runId
            )
            guard isActiveQueryGeneration(generation) else { return }
            guard resolved else {
                log(
                    "FloatingControlBarManager: agent link unavailable after hydrate "
                        + "pillId=\(ref.pillId?.uuidString ?? "nil") "
                        + "sessionId=\(ref.sessionId ?? "nil") "
                        + "runId=\(ref.runId ?? "nil")"
                )
                completion?(false)
                return
            }
            let pillID = AgentPillsManager.shared.pills.first(where: { pill in
                if let pillId = ref.pillId, pill.id == pillId { return true }
                if let runId = ref.runId, pill.canonicalRunId == runId { return true }
                if let sessionId = ref.sessionId, pill.canonicalSessionId == sessionId { return true }
                return false
            })?.id ?? ref.pillId
            guard let pillID else {
                log("FloatingControlBarManager: agent hydrate succeeded but pill id missing")
                completion?(false)
                return
            }
            AgentPillsManager.shared.markViewed(pillID: pillID)
            window.state.setNotchHoverMenuOpen(false)
            window.makeKeyAndOrderFront(nil)
            OmiMotion.withGated(.easeOut(duration: 0.10)) {
                window.state.present(.agent(pillID))
                window.state.isAILoading = false
            }
            window.resizeForActiveAgentChatPublic(pillID: pillID, animated: true)
            completion?(true)
        }
    }

    /// Called when a pill is dismissed while it is the one shown in the Ask Omi
    /// surface. Leaves the agent surface so conversationSurface resets instead
    /// of dangling as .agent(id) for a removed pill. (Codex P2 — clear active
    /// chat when dismissing a pill.)
    func leaveActiveAgentSurfaceFromPillDismiss() {
        guard let window else { return }
        window.leaveAgentConversation()
    }
    private var pendingNotifications: [FloatingBarNotification] = []
    private var notificationDismissWorkItem: DispatchWorkItem?
    private var notificationWasTemporarilyShown = false
    private var storedNotificationMessages: [OwnerNotificationKey: StoredNotificationMessage] = [:]
    private var pendingNotificationJournalWrites: Set<OwnerNotificationKey> = []
    private var mostRecentNotificationKey: OwnerNotificationKey?
    private var ownerChangeCancellable: AnyCancellable?
    private var pendingNotificationContext: PendingNotificationContext?
    private var activeQueryGeneration: Int = 0
    private var selectedFloatingModel: String {
        let selected = ShortcutSettings.shared.selectedModel
        return selected.isEmpty ? ModelQoS.Claude.defaultSelection : selected
    }
    private var pendingFollowUpQuery: PendingFollowUpQuery?

    /// Whether the user has enabled the Ask Omi bar (persisted across launches).
    /// Defaults to true for new users.
    var isEnabled: Bool {
        get {
            // Default to true if never set
            if UserDefaults.standard.object(forKey: Self.kAskOmiEnabled) == nil {
                return true
            }
            return UserDefaults.standard.bool(forKey: Self.kAskOmiEnabled)
        }
        set {
            UserDefaults.standard.set(newValue, forKey: Self.kAskOmiEnabled)
        }
    }

    /// Timestamp until which the bar and notifications are temporarily suppressed.
    /// Independent from `isEnabled` — snoozing does not flip the persisted enable preference.
    var snoozedUntil: Date? {
        get {
            let timestamp = UserDefaults.standard.double(forKey: Self.kSnoozedUntil)
            guard timestamp > 0 else { return nil }
            return Date(timeIntervalSince1970: timestamp)
        }
        set {
            if let newValue {
                UserDefaults.standard.set(newValue.timeIntervalSince1970, forKey: Self.kSnoozedUntil)
            } else {
                UserDefaults.standard.removeObject(forKey: Self.kSnoozedUntil)
            }
        }
    }

    var isSnoozed: Bool {
        guard let snoozedUntil else { return false }
        return snoozedUntil > Date()
    }

    /// Hide the bar and suppress notifications for the given duration.
    func snooze(for duration: TimeInterval) {
        let until = Date().addingTimeInterval(duration)
        snoozedUntil = until
        notificationDismissWorkItem?.cancel()
        notificationDismissWorkItem = nil
        pendingNotifications.removeAll()
        if let window, window.state.currentNotification != nil {
            window.dismissNotification(animated: false)
        }
        window?.orderOut(nil)
        scheduleSnoozeTimer()
        AnalyticsManager.shared.floatingBarToggled(visible: false, source: "snooze")
    }

    /// Clear snooze state; the bar becomes visible again if the user preference is enabled.
    func endSnooze() {
        snoozedUntil = nil
        snoozeTimer?.invalidate()
        snoozeTimer = nil
        if isEnabled {
            window?.makeKeyAndOrderFront(nil)
        }
    }

    private func scheduleSnoozeTimer() {
        snoozeTimer?.invalidate()
        snoozeTimer = nil
        guard let snoozedUntil else { return }
        let interval = snoozedUntil.timeIntervalSinceNow
        guard interval > 0 else {
            self.snoozedUntil = nil
            return
        }
        let timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: false) { [weak self] _ in
            Task { @MainActor in self?.endSnooze() }
        }
        snoozeTimer = timer
    }

    private init() {
        ownerChangeCancellable = NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)
            .sink { [weak self] _ in
                MainActor.assumeIsolated {
                    self?.resetOwnerProjection()
                }
            }
    }

    func resetOwnerProjection() {
        activeQueryGeneration &+= 1
        notificationDismissWorkItem?.cancel()
        notificationDismissWorkItem = nil
        pendingNotifications.removeAll()
        pendingNotificationJournalWrites.removeAll()
        storedNotificationMessages.removeAll()
        mostRecentNotificationKey = nil
        pendingNotificationContext = nil
        if window?.state.currentNotification != nil {
            window?.dismissNotification(animated: false)
        }
        window?.state.clearVisibleConversation()
    }

    var notificationProjectionSnapshot: NotificationProjectionSnapshot {
        NotificationProjectionSnapshot(
            queuedCount: pendingNotifications.count,
            pendingJournalCount: pendingNotificationJournalWrites.count,
            storedJournalCount: storedNotificationMessages.count
        )
    }

    static func performOwnerBoundNotificationAdmission<Value>(
        ownerID: String,
        currentOwnerID: @escaping @MainActor () -> String? = {
            RuntimeOwnerIdentity.currentOwnerId()
        },
        record: () async -> Value?
    ) async -> Value? {
        guard !ownerID.isEmpty, currentOwnerID() == ownerID else { return nil }
        guard let value = await record() else { return nil }
        guard currentOwnerID() == ownerID else { return nil }
        return value
    }

    /// Create the floating bar window and wire up AppState bindings.
    func setup(appState: AppState, chatProvider: ChatProvider) {
        guard window == nil else {
            log("FloatingControlBarManager: setup() called but window already exists")
            return
        }
        log("FloatingControlBarManager: setup() creating floating bar window")

        let barWindow = FloatingControlBarWindow(
            contentRect: .zero,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )

        // Play/pause toggles transcription
        barWindow.onPlayPause = { [weak appState] in
            guard let appState = appState else { return }
            appState.toggleTranscription()
        }

        // Ask AI opens the input panel
        barWindow.onAskAI = { [weak barWindow] in
            barWindow?.showAIConversation()
            barWindow?.makeKeyAndOrderFront(nil)
        }

        // Hide persists the preference so bar stays hidden across restarts
        barWindow.onHide = { [weak self] in
            self?.isEnabled = false
        }

        // Default floating/notch chat is a second view over the main chat provider.
        // That keeps streamed deltas, unsynced local IDs, and prompt history in one
        // canonical transcript instead of waiting for backend polling to reconcile.
        historyChatProvider = chatProvider

        barWindow.onSendQuery = { [weak self, weak barWindow, weak chatProvider] message in
            guard let self = self, let barWindow = barWindow, let provider = chatProvider else { return }
            Task { @MainActor in
                await self.withQueryTracer(query: message, fromVoice: false) {
                    await self.routeQuery(message, barWindow: barWindow, provider: provider, fromVoice: false)
                }
            }
        }

        barWindow.onRate = { [weak chatProvider] messageId, rating in
            guard let provider = chatProvider else { return }
            Task { @MainActor in
                await provider.rateMessage(messageId, rating: rating)
            }
        }

        barWindow.onShareLink = { [weak self, weak barWindow] in
            guard let self, let barWindow = barWindow else { return nil }
            // Share synced message ids from the viewport cursor over the shared provider.
            let orderedUniqueMessageIds = barWindow.state.syncedShareMessageIds(
                from: self.historyChatProvider
            )
            guard !orderedUniqueMessageIds.isEmpty else { return nil }
            do {
                let response = try await APIClient.shared.shareChatMessages(messageIds: orderedUniqueMessageIds)
                return response.url
            } catch {
                log("Failed to get chat share link: \(error)")
                return nil
            }
        }

        // Observe recording state
        recordingCancellable = appState.$isTranscribing
            .combineLatest(appState.$isSavingConversation)
            .receive(on: DispatchQueue.main)
            .sink { [weak barWindow] isTranscribing, isSaving in
                barWindow?.updateRecordingState(
                    isRecording: isTranscribing,
                    duration: Int(RecordingTimer.shared.duration),
                    isInitialising: isSaving
                )
            }

        // Observe duration from RecordingTimer
        durationCancellable = RecordingTimer.shared.$duration
            .receive(on: DispatchQueue.main)
            .sink { [weak barWindow, weak appState] duration in
                guard let appState = appState else { return }
                barWindow?.updateRecordingState(
                    isRecording: appState.isTranscribing,
                    duration: Int(duration),
                    isInitialising: appState.isSavingConversation
                )
            }

        self.window = barWindow

        // Re-apply any in-flight snooze that survived app relaunch.
        if isSnoozed {
            scheduleSnoozeTimer()
        } else if snoozedUntil != nil {
            snoozedUntil = nil
        }

    }

    /// Whether the floating bar window is currently visible.
    var isVisible: Bool {
        window?.isVisible ?? false
    }

    struct AutomationState {
        let isVisible: Bool
        let isAskOmiOpen: Bool
        let isAskOmiFocused: Bool
        let frame: String?
        let isVoiceListening: Bool
        let isVoiceResponseActive: Bool
        let usesNotchIsland: Bool
    }

    var automationState: AutomationState {
        guard let window else {
            return AutomationState(
                isVisible: false,
                isAskOmiOpen: false,
                isAskOmiFocused: false,
                frame: nil,
                isVoiceListening: false,
                isVoiceResponseActive: false,
                usesNotchIsland: false
            )
        }
        let focused = window.firstResponder is NSTextView
        return AutomationState(
            isVisible: window.isVisible,
            isAskOmiOpen: window.state.showingAIConversation,
            isAskOmiFocused: focused,
            frame: NSStringFromRect(window.frame),
            isVoiceListening: window.state.isVoiceListening,
            isVoiceResponseActive: window.state.isVoiceResponseGlowActive,
            usesNotchIsland: window.state.usesNotchIsland
        )
    }

    func openAskOmiForAutomation(reset: Bool, wait: Bool = true) async -> [String: String] {
        guard let window else {
            return ["error": "floating_bar_window_unavailable"]
        }
        if reset {
            if let provider = sharedFloatingProvider {
                _ = await provider.automationClearOwnerSurfaceState(chatId: "default")
                if let error = await provider.automationResetChatForHarness() {
                    return ["error": error]
                }
            }
            if window.state.showingAIConversation {
                window.closeAIConversation()
                _ = await waitForAskOmiClosed(in: window)
            }
        }

        let start = ContinuousClock.now
        openAIInput()
        guard wait else {
            return [
                "triggered": "true",
                "frame": NSStringFromRect(window.frame),
                "focused": (window.firstResponder is NSTextView) ? "true" : "false",
            ]
        }
        let openMs = await waitForAutomationCondition {
            window.isVisible && window.state.showingAIConversation && !window.state.showingAIResponse
        }
        if !(window.firstResponder is NSTextView) {
            _ = window.focusInputField()
        }
        let focusMs = await waitForAutomationCondition {
            window.firstResponder is NSTextView
        }
        let elapsedMs = start.duration(to: .now).millisecondsString
        return [
            "openMs": openMs ?? "timeout",
            "focusMs": focusMs ?? "timeout",
            "elapsedMs": elapsedMs,
            "frame": NSStringFromRect(window.frame),
            "focused": (window.firstResponder is NSTextView) ? "true" : "false",
        ]
    }

    func closeAskOmiForAutomation(wait: Bool = true) async -> [String: String] {
        guard let window else {
            return ["error": "floating_bar_window_unavailable"]
        }
        let start = ContinuousClock.now
        if window.state.showingAIConversation {
            window.closeAIConversation()
        }
        guard wait else {
            return [
                "triggered": "true",
                "visible": window.isVisible ? "true" : "false",
                "askOmiOpen": window.state.showingAIConversation ? "true" : "false",
                "frame": NSStringFromRect(window.frame),
            ]
        }
        let closeMs = await waitForAskOmiClosed(in: window)
        let elapsedMs = start.duration(to: .now).millisecondsString
        return [
            "closeMs": closeMs ?? "timeout",
            "elapsedMs": elapsedMs,
            "visible": window.isVisible ? "true" : "false",
            "askOmiOpen": window.state.showingAIConversation ? "true" : "false",
            "frame": NSStringFromRect(window.frame),
        ]
    }

    func automationFloatingBarChatSnapshot(limit: Int) -> [String: String] {
        guard let provider = sharedFloatingProvider else {
            return ["error": "floating chat provider unavailable"]
        }
        return provider.automationFloatingChatSnapshot(limit: limit)
    }

    func seedSubagentsForAutomation(count: Int) async -> [String: String] {
        guard let window else {
            return ["error": "floating_bar_window_unavailable"]
        }
        let pills = AgentPillsManager.shared.replaceWithAutomationPills(count: count)
        if !window.state.showingAIConversation {
            window.showAIConversation()
        }
        window.state.present(.mainInput)
        window.state.isAILoading = false
        window.resizeToResponseHeightPublic(animated: false)
        window.state.present(.mainInput)
        return [
            "count": "\(pills.count)",
            "first": pills.first?.id.uuidString ?? "",
            "frame": NSStringFromRect(window.frame),
        ]
    }

    func openSeededSubagentForAutomation(index: Int, wait: Bool = true) async -> [String: String] {
        guard let window else {
            return ["error": "floating_bar_window_unavailable"]
        }
        let pills = AgentPillsManager.shared.pills
        guard pills.indices.contains(index) else {
            return ["error": "subagent_index_out_of_range"]
        }
        let pill = pills[index]
        let start = ContinuousClock.now
        AgentPillsManager.shared.markViewed(pillID: pill.id)
        OmiMotion.withGated(.easeOut(duration: 0.10)) {
            window.state.present(.agent(pill.id))
            window.state.isAILoading = false
        }
        window.resizeForActiveAgentChatPublic(pillID: pill.id, animated: false)
        guard wait else {
            return ["triggered": "true", "active": pill.id.uuidString]
        }
        let selectMs = await waitForAutomationCondition {
            window.state.activeAgentChatPillID == pill.id && window.state.showingAIResponse
        }
        return [
            "selectMs": selectMs ?? "timeout",
            "elapsedMs": start.duration(to: .now).millisecondsString,
            "active": pill.id.uuidString,
            "frame": NSStringFromRect(window.frame),
        ]
    }

    func backFromSubagentForAutomation(wait: Bool = true) async -> [String: String] {
        guard let window else {
            return ["error": "floating_bar_window_unavailable"]
        }
        let start = ContinuousClock.now
        let expectsRows = !AgentPillsManager.shared.pills.isEmpty
        window.leaveAgentConversation()
        guard wait else {
            return [
                "triggered": "true",
                "active": window.state.activeAgentChatPillID?.uuidString ?? "",
                "mode": expectsRows ? "rows" : "main",
                "rowsOpen": window.state.isNotchHoverMenuVisible ? "true" : "false",
            ]
        }
        let backMs = await waitForAutomationCondition {
            window.state.activeAgentChatPillID == nil
                && (expectsRows
                    ? (!window.state.showingAIConversation && window.state.isNotchHoverMenuVisible)
                    : window.state.showingAIConversation)
        }
        return [
            "backMs": backMs ?? "timeout",
            "elapsedMs": start.duration(to: .now).millisecondsString,
            "mode": expectsRows ? "rows" : "main",
            "rowsOpen": window.state.isNotchHoverMenuVisible ? "true" : "false",
            "frame": NSStringFromRect(window.frame),
        ]
    }

    private func waitForAutomationCondition(_ condition: @MainActor @escaping () -> Bool) async -> String? {
        let start = ContinuousClock.now
        while start.duration(to: .now) < .milliseconds(500) {
            if condition() {
                return start.duration(to: .now).millisecondsString
            }
            try? await Task.sleep(for: .milliseconds(5))
        }
        return nil
    }

    private func waitForAskOmiClosed(in window: FloatingControlBarWindow) async -> String? {
        await waitForAutomationCondition {
            window.hasSettledClosedForAutomation
        }
    }

    /// Apply the product-level launch presentation policy.
    ///
    /// Normal signed-in Desktop launch must show the floating bar when enabled;
    /// deferred reveal is reserved for explicit opt-in contexts such as onboarding
    /// or a future minimal mode.
    func presentForLaunch(context: FloatingBarLaunchContext) {
        let presentation = FloatingBarLaunchPolicy.presentation(
            isEnabled: isEnabled,
            context: context,
            displayHasNotch: window?.usesNotchIslandForCurrentScreen == true
        )

        switch presentation {
        case .hidden:
            return
        case .showImmediately:
            show()
        case .deferUntilFirstPushToTalk:
            showDeferredUntilFirstPushToTalk()
        }
    }

    /// Opt-in presentation for contexts where the notch should stay hidden until
    /// the user's first Push-to-Talk press (which calls `show()`).
    func showDeferredUntilFirstPushToTalk() {
        if window?.usesNotchIslandForCurrentScreen == true, !hasRevealedNotchThisSession {
            isEnabled = true
            log("FloatingControlBarManager: showDeferredUntilFirstPushToTalk() — notch hidden until first Push-to-Talk")
            return
        }
        show()
    }

    /// Show the floating bar and persist the preference.
    func show() {
        log("FloatingControlBarManager: show() called, window=\(window != nil), isVisible=\(window?.isVisible ?? false)")
        isEnabled = true
        if isSnoozed {
            log("FloatingControlBarManager: show() suppressed because bar is snoozed until \(snoozedUntil?.description ?? "?")")
            return
        }
        // Reveal on every hidden→present transition (not just once per session):
        // the island should always grow out of the notch instead of popping in.
        let shouldPlayNotchReveal =
            window?.usesNotchIslandForCurrentScreen == true
            && (window?.isVisible != true || !hasRevealedNotchThisSession)
        hasRevealedNotchThisSession = true
        window?.normalizeForTemporaryShow()
        window?.makeKeyAndOrderFront(nil)
        if shouldPlayNotchReveal {
            window?.playNotchRevealAnimation()
        }
        log("FloatingControlBarManager: show() done, frame=\(window?.frame ?? .zero)")

        // Auto-focus input if AI conversation is open
        if let window = window, window.state.showingAIConversation && !window.state.showingAIResponse {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                window.focusInputField()
            }
        }
    }

    /// Hide the floating bar and persist the preference.
    func hide() {
        isEnabled = false
        if let window {
            window.retractIntoNotch { [weak window] in
                window?.orderOut(nil)
            }
        }
    }

    /// Show the floating bar temporarily without changing the user's persisted preference.
    /// Used when browser tools activate so the bar stays visible above Chrome.
    func showTemporarily() {
        guard window != nil else { return }
        if !isEnabled {
            // The user has explicitly disabled the floating bar. Honor that even when
            // a background browser tool would otherwise surface it — unlike the
            // notification path, there is no follow-up that re-hides it, so showing
            // here leaves the bar visible "forever" despite the toggle being off.
            log("FloatingControlBarManager: showTemporarily() suppressed because bar is disabled")
            return
        }
        if isSnoozed {
            log("FloatingControlBarManager: showTemporarily() suppressed because bar is snoozed")
            return
        }
        log("FloatingControlBarManager: showTemporarily() — showing bar above Chrome")
        window?.normalizeForTemporaryShow()
        window?.makeKeyAndOrderFront(nil)
    }

    @discardableResult
    func showNotification(
        ownerID: String,
        title: String,
        message: String,
        assistantId: String,
        sound: NotificationSound,
        context: FloatingBarNotificationContext? = nil,
        action: FloatingBarNotificationAction? = nil,
        screenshotData: Data? = nil
    ) -> OwnerBoundNotificationPresentationResult {
        guard !ownerID.isEmpty, RuntimeOwnerIdentity.currentOwnerId() == ownerID else {
            log("FloatingControlBarManager: rejecting notification from stale runtime owner")
            return .rejectedOwnerChange
        }
        let notification = FloatingBarNotification(
            ownerID: ownerID,
            title: title,
            message: message,
            assistantId: assistantId,
            context: context,
            action: action,
            screenshotData: screenshotData
        )
        guard let window else {
            log("FloatingControlBarManager: dropping notification because window is not set up")
            return .windowUnavailable
        }

        if isSnoozed {
            log("FloatingControlBarManager: dropping notification because bar is snoozed until \(snoozedUntil?.description ?? "?")")
            return .suppressed
        }

        switch sound {
        case .focusLost, .focusRegained:
            sound.playCustomSound()
        case .default, .none:
            break
        }

        if !window.state.showingAIConversation {
            persistNotificationMessageIfNeeded(notification)
        }

        if window.state.currentNotification != nil || window.state.showingAIConversation {
            pendingNotifications.append(notification)
            return .queued
        }

        presentNotification(notification, in: window)
        return .presented
    }

    func dismissCurrentNotification() {
        notificationDismissWorkItem?.cancel()
        notificationDismissWorkItem = nil
        dismissNotificationAndAdvanceQueue(trackDismissal: true)
    }

    func flushQueuedNotificationsIfPossible() {
        guard let window, window.state.currentNotification == nil, !window.state.showingAIConversation
        else { return }
        while !pendingNotifications.isEmpty {
            let nextNotification = pendingNotifications.removeFirst()
            guard nextNotification.ownerID == RuntimeOwnerIdentity.currentOwnerId() else {
                log("FloatingControlBarManager: dropping queued notification from stale runtime owner")
                continue
            }
            presentNotification(nextNotification, in: window)
            return
        }
    }

    /// Detach the floating UI from any in-flight chat streaming.
    func cancelChat(keepVoiceAlive: Bool = false, stopProvider: Bool = false) {
        activeQueryGeneration += 1
        pendingFollowUpQuery = nil
        chatCancellable?.cancel()
        chatCancellable = nil
        // Floating close/hide is presentation-only now that default floating
        // chat shares the main provider. Only explicit floating barge-ins should
        // interrupt, and those go through owner-aware routeQuery checks.
        if stopProvider, !keepVoiceAlive {
            let provider = activeFloatingProvider()
            _ = provider?.stopAgent(owner: .floatingDefault)
            _ = provider?.stopAgent(owner: .floatingVoice)
        }
        if !keepVoiceAlive {
            FloatingBarVoicePlaybackService.shared.stop()
        }
    }

    /// After mid-stream close → restore, re-bind the floating viewport to the
    /// still-streaming provider turn so answer text/blocks keep updating.
    func reobserveStreamingTurnIfNeeded(in barWindow: FloatingControlBarWindow) {
        guard let provider = historyChatProvider else { return }
        let turnId = barWindow.state.chatViewport.activeClientTurnId
        let answer = barWindow.state.currentAIMessage(from: provider)
        guard FloatingControlBarState.shouldReobserveStreamingTurn(
            activeClientTurnId: turnId,
            answerMessage: answer
        ), let turnId else {
            // Refresh a completed/partial answer that advanced while the surface was closed.
            if let message = answer {
                barWindow.state.bindAnswerMessage(message)
            }
            return
        }

        let generation = activeQueryGeneration
        let shouldPlayVoice = ShortcutSettings.shared.shouldSpeakFloatingBarResponse(
            forVoiceQuery: barWindow.state.currentQueryFromVoice
        )
        chatCancellable?.cancel()
        var hasSetUpResponseHeight = barWindow.state.showingAIResponse
        chatCancellable = provider.$messages
            .receive(on: DispatchQueue.main)
            .sink { [weak self, weak barWindow] messages in
                guard let self, self.isActiveQueryGeneration(generation) else { return }
                guard let aiMessage = messages.last(where: {
                    $0.clientTurnId == turnId && $0.sender == .ai
                }) else { return }

                barWindow?.state.bindAnswerMessage(aiMessage)
                if let userMessage = messages.last(where: {
                    $0.clientTurnId == turnId && $0.sender == .user
                }) {
                    barWindow?.state.bindQuestionMessageId(userMessage.id)
                }
                if shouldPlayVoice {
                    FloatingBarVoicePlaybackService.shared.updateStreamingResponseIfEnabled(
                        aiMessage,
                        isFinal: !aiMessage.isStreaming
                    )
                }

                if aiMessage.isStreaming {
                    barWindow?.state.isAILoading = false
                    if let barWindow, !hasSetUpResponseHeight {
                        hasSetUpResponseHeight = true
                        if !barWindow.state.showingAIResponse {
                            OmiMotion.withGated(.spring(response: 0.24, dampingFraction: 0.9)) {
                                barWindow.state.present(.mainResponse)
                            }
                        }
                        barWindow.resizeToResponseHeightPublic(animated: true)
                    }
                } else {
                    barWindow?.state.isAILoading = false
                    self.chatCancellable?.cancel()
                    self.chatCancellable = nil
                }
            }

        if let answer {
            barWindow.state.bindAnswerMessage(answer)
            barWindow.state.isAILoading = false
        }
    }

    /// Toggle visibility.
    func toggle() {
        guard let window = window else { return }
        if window.isVisible {
            AnalyticsManager.shared.floatingBarToggled(visible: false, source: "shortcut")
            hide()
        } else {
            AnalyticsManager.shared.floatingBarToggled(visible: true, source: "shortcut")
            show()
        }
    }

    /// Toggle AI input: if conversation is open, collapse it; otherwise open it.
    func toggleAIInput() {
        guard let window = window else { return }
        if window.isVisible && window.state.showingAIConversation {
            window.closeAIConversation()
        } else {
            openAIInput()
        }
    }

    /// Open the AI input panel.
    func openAIInput() {
        guard let window = window else { return }

        // The bar is a non-activating panel, so it can become key for text input
        // without surfacing the main Omi window.

        // If a conversation is already showing, just focus the follow-up input
        if window.state.showingAIConversation && window.state.showingAIResponse {
            if !window.isVisible {
                // Show without persisting enabled state — bar hides again when conversation closes
                window.makeKeyAndOrderFront(nil)
            }
            window.makeKeyAndOrderFront(nil)
            window.focusInputField()
            return
        }

        AnalyticsManager.shared.floatingBarAskOmiOpened(source: "shortcut")
        if !window.isVisible {
            // Show window without persisting enabled state — if the user has the bar
            // disabled, it will hide again when the AI conversation closes.
            window.makeKeyAndOrderFront(nil)
        }

        if openRecentNotificationConversationIfAvailable(in: window) {
            return
        }

        window.showAIConversation()
        window.orderFrontRegardless()
    }

    /// Open AI input with a pre-filled query and auto-send (used by PTT).
    /// Dashboard actions use the same shared timeline, but first restore the
    /// hidden viewport with the established grow-from-notch transition.
    func openDashboardQuery(_ query: String) {
        guard let window else { return }
        let shouldRevealFromNotch =
            window.usesNotchIslandForCurrentScreen && !window.isVisible
        if !window.isVisible {
            window.normalizeForTemporaryShow()
            window.makeKeyAndOrderFront(nil)
            if shouldRevealFromNotch {
                hasRevealedNotchThisSession = true
                window.playNotchRevealAnimation()
            }
        }
        openAIInputWithQuery(query)
    }

    func openAIInputWithQuery(
        _ query: String,
        fromVoice: Bool = false,
        voiceTurnID: VoiceTurnID? = nil
    ) {
        guard let window = window else { return }
        guard let provider = activeFloatingProvider() else { return }

        if fromVoice {
            guard let voiceTurnID,
                  VoiceTurnCoordinator.shared.requireCurrentOwner(for: voiceTurnID) != nil
            else { return }
            chatCancellable?.cancel()
            chatCancellable = nil
            window.cancelInputHeightObserver()
            window.state.currentQueryFromVoice = true
            if window.state.showingAIConversation {
                window.closeAIConversation()
            } else if !window.isVisible {
                window.makeKeyAndOrderFront(nil)
            }
            Task { @MainActor in
                guard VoiceTurnCoordinator.shared.requireCurrentOwner(for: voiceTurnID) != nil else {
                    return
                }
                await self.withQueryTracer(query: query, fromVoice: true) {
                    await self.routeQuery(
                        query,
                        barWindow: window,
                        provider: provider,
                        presentation: .voiceOnly,
                        voiceTurnID: voiceTurnID
                    )
                }
            }
            return
        }

        // Cancel stale subscriptions immediately to prevent old data from flashing
        chatCancellable?.cancel()
        chatCancellable = nil
        window.cancelInputHeightObserver()

        // Reset visible state without animation; keep provider session (cancelInFlightWork: false).
        window.state.showingAIConversation = false
        window.state.clearVisibleConversation(cancelInFlightWork: false)
        window.state.currentQueryFromVoice = fromVoice
        pendingNotificationContext = nil

        // Re-wire onSendQuery for typed follow-ups (force fromVoice:false after voice turns).
        window.onSendQuery = { [weak self, weak window, weak provider] message in
            guard let self = self, let window = window, let provider = provider else { return }
            Task { @MainActor in
                await self.withQueryTracer(query: message, fromVoice: false) {
                    await self.routeQuery(message, barWindow: window, provider: provider, fromVoice: false)
                }
            }
        }

        if !window.isVisible {
            // Show window without persisting enabled state — if the user has the bar
            // disabled, it will hide again when the AI conversation closes.
            window.makeKeyAndOrderFront(nil)
        }

        // Cancel any in-flight windowDidResignKey dismiss animation before saving the
        // pre-chat center. Without this, the stale completion block fires after the new
        // query opens and immediately closes it.
        window.cancelPendingDismiss()

        // Save pre-chat center so closeAIConversation can restore the original position.
        // Without this, Escape after a PTT query places the bar at the response window's
        // center instead of where it was before the chat opened.
        window.savePreChatCenterIfNeeded()

        // Mark the query source before sending so playback behavior is correct.
        window.state.currentQueryFromVoice = fromVoice
        window.orderFrontRegardless()

        // Auto-send the query. PTT bypasses the typed onSendQuery closure, so
        // we need to apply the same router rule here ourselves.
        Task { @MainActor in
            await self.withQueryTracer(query: query, fromVoice: fromVoice) {
                await self.routeQuery(query, barWindow: window, provider: provider, fromVoice: fromVoice)
            }
        }
    }

    /// QueryTracer: establish the per-query TaskLocal tracer context for a
    /// floating-bar query. Reuses an existing tracer (PTT transfers one in via
    /// `QueryTracerContext`) or creates a fresh one for typed queries. The
    /// tracer's origin is set here, so `total_ms` measures from query submission
    /// through the kernel-owned turn and any control effect to the final trace.
    private func withQueryTracer(query: String, fromVoice: Bool, _ body: () async -> Void) async {
        let tracer =
            QueryTracerContext.current
            ?? QueryTracer(query: query, inputMode: fromVoice ? .voicePTTBatch : .text)
        await QueryTracerContext.$current.withValue(tracer) {
            await body()
        }
    }

    /// Submit ordinary requests to the kernel-backed chat. Explicit provider
    /// and agent handoffs enter the same kernel control plane through
    /// `spawn_agent`; there is no surface-local semantic router.
    private func routeQuery(
        _ message: String,
        barWindow: FloatingControlBarWindow,
        provider: ChatProvider,
        fromVoice: Bool,
        voiceTurnID: VoiceTurnID? = nil
    ) async {
        await routeQuery(
            message,
            barWindow: barWindow,
            provider: provider,
            presentation: .visible(fromVoice: fromVoice),
            voiceTurnID: voiceTurnID
        )
    }

    private func routeQuery(
        _ message: String,
        barWindow: FloatingControlBarWindow,
        provider: ChatProvider,
        presentation: QueryPresentation,
        voiceTurnID: VoiceTurnID? = nil
    ) async {
        guard voiceTurnID.map({ VoiceTurnCoordinator.shared.requireCurrentOwner(for: $0) != nil })
            ?? true else { return }
        let turnOwner = chatTurnOwner(for: presentation)
        let directive = AgentPillsManager.providerDirective(
            from: message,
            contextualPreviousRequest: recentVisibleUserRequest(in: barWindow)
        )
        if provider.isSending, directive == nil {
            guard provider.canInterruptActiveTurn(owner: turnOwner) else {
                showSharedProviderBusy(in: barWindow, presentation: presentation)
                return
            }
            pendingFollowUpQuery = PendingFollowUpQuery(
                text: message,
                presentation: presentation,
                voiceTurnID: voiceTurnID
            )
            if case .visible(let fromVoice) = presentation {
                prepareVisibleQueryState(message, in: barWindow, fromVoice: fromVoice)
            }
            provider.stopAgent(owner: turnOwner, reason: .superseded)
            return
        }

        // Show the thinking state immediately while the kernel accepts the
        // turn or applies an explicit control-plane handoff.
        if case .visible(let fromVoice) = presentation {
            prepareVisibleQueryState(message, in: barWindow, fromVoice: fromVoice)
        }

        let routerTracer = QueryTracerContext.current
        if let directive {
            if provider.isSending {
                guard provider.canInterruptActiveTurn(owner: turnOwner) else {
                    showSharedProviderBusy(in: barWindow, presentation: presentation)
                    return
                }
                pendingFollowUpQuery = nil
                provider.stopAgent(owner: turnOwner, reason: .superseded)
            }
            routerTracer?.mark("kernel_route", metadata: ["effect": "spawn_agent", "provider": directive.provider.rawValue])
            await resolveDelegationAndDispatch(
                originalRequest: message,
                proposedBrief: directive.rewrittenQuery,
                proposedTitle: directive.title,
                proposedAck: directive.ack,
                directedProvider: directive.provider,
                barWindow: barWindow,
                provider: provider,
                presentation: presentation,
                voiceTurnID: voiceTurnID
            )
            return
        }

        routerTracer?.mark("kernel_route", metadata: ["authority": "agent_kernel"])
        await dispatchChatQuery(
            message,
            barWindow: barWindow,
            provider: provider,
            presentation: presentation,
            voiceTurnID: voiceTurnID
        )
    }

    private func recordDelegationExchange(
        provider: ChatProvider,
        userText: String,
        assistantText: String,
        origin: String,
        continuityKey: String,
        assistantContentBlocks: [ChatContentBlock] = []
    ) async -> (user: ChatMessage?, assistant: ChatMessage?) {
        await provider.recordJournalExchange(
            continuityKey: continuityKey,
            userText: userText,
            assistantText: assistantText,
            origin: origin,
            contentBlocks: assistantContentBlocks
        )
    }

    private func resolveDelegationAndDispatch(
        originalRequest: String,
        proposedBrief: String,
        proposedTitle: String?,
        proposedAck: String?,
        directedProvider: AgentPillsManager.DirectedProvider?,
        barWindow: FloatingControlBarWindow,
        provider: ChatProvider,
        presentation: QueryPresentation,
        voiceTurnID: VoiceTurnID?
    ) async {
        guard voiceTurnID.map({ VoiceTurnCoordinator.shared.requireCurrentOwner(for: $0) != nil })
            ?? true else { return }
        let exchangeId = UUID().uuidString
        let brief = proposedBrief.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedProvider = directedProvider
        let title = proposedTitle?.trimmingCharacters(in: .whitespacesAndNewlines)
        let titleSuffix = (title?.isEmpty == false) ? " titled \"\(title!)\"" : ""
        let providerPrefix = resolvedProvider.map { "\($0.displayName) in " } ?? ""
        let ack = proposedAck?.trimmingCharacters(in: .whitespacesAndNewlines)
        let assistantText = ack?.isEmpty == false
            ? "\(ack!) I started \(providerPrefix)a background agent\(titleSuffix) for that."
            : "I started \(providerPrefix)a background agent\(titleSuffix) for that."
        let producingSurface = provider.mainChatSurfaceReference()
        let pill: AgentPill?
        do {
            guard voiceTurnID.map({ VoiceTurnCoordinator.shared.requireCurrentOwner(for: $0) != nil })
                ?? true else { return }
            pill = try await AgentDelegationExecutor.shared.spawnResolvedDelegation(
                .init(
                    originalUserText: originalRequest,
                    brief: brief,
                    title: proposedTitle,
                    spokenAck: proposedAck,
                    directedProvider: resolvedProvider,
                    originSurface: .floatingBar
                ),
                model: selectedFloatingModel,
                fromVoice: presentation.fromVoice,
                producerJournalIntent: AgentPillProducerJournalIntent(
                    surface: producingSurface,
                    userText: originalRequest,
                    assistantText: assistantText
                )
            )
            guard voiceTurnID.map({ VoiceTurnCoordinator.shared.requireCurrentOwner(for: $0) != nil })
                ?? true else { return }
        } catch {
            logError("FloatingControlBarWindow: canonical background spawn failed", error: error)
            let failureText = "I couldn't start that background agent."
            let recordedTurn = await recordDelegationExchange(
                provider: provider,
                userText: originalRequest,
                assistantText: failureText,
                origin: "floating_spawn_failed",
                continuityKey: "floating_spawn_failed:\(exchangeId)"
            )
            switch presentation {
            case .visible:
                if let assistantMessage = recordedTurn.assistant {
                    completeVisibleAgentResponse(
                        userText: originalRequest,
                        assistantMessage: assistantMessage,
                        barWindow: barWindow
                    )
                } else {
                    presentJournalAdmissionFailure(in: barWindow)
                }
            case .voiceOnly:
                if recordedTurn.assistant != nil {
                    FloatingBarVoicePlaybackService.shared.speakOneShot(failureText)
                } else {
                    FloatingBarVoicePlaybackService.shared.speakOneShot("I couldn't save that response. Please try again.")
                }
            }
            return
        }

        guard let pill else {
            let assistantText = "What should the background agent do?"
            let recordedTurn = await recordDelegationExchange(
                provider: provider,
                userText: originalRequest,
                assistantText: assistantText,
                origin: "floating_invalid_brief",
                continuityKey: "floating_control:\(exchangeId):invalid-brief"
            )
            switch presentation {
            case .visible:
                if let assistantMessage = recordedTurn.assistant {
                    completeVisibleAgentResponse(
                        userText: originalRequest,
                        assistantMessage: assistantMessage,
                        barWindow: barWindow
                    )
                } else {
                    presentJournalAdmissionFailure(in: barWindow)
                }
            case .voiceOnly:
                if recordedTurn.assistant != nil {
                    FloatingBarVoicePlaybackService.shared.speakOneShot(assistantText)
                } else {
                    FloatingBarVoicePlaybackService.shared.speakOneShot("I couldn't save that response. Please try again.")
                }
            }
            return
        }
        guard let canonicalSessionID = pill.canonicalSessionId, !canonicalSessionID.isEmpty,
              let canonicalRunID = pill.canonicalRunId, !canonicalRunID.isEmpty else {
            log("FloatingControlBarWindow: accepted spawn omitted canonical handles")
            return
        }
        let continuityKey = "floating_spawn:\(pill.id.uuidString)"
        // The accepted spawn RPC synchronously materializes this exact exchange
        // in the kernel journal before returning. Refresh that authority instead
        // of issuing a second writer RPC with a competing producer payload.
        await provider.kernelTurnProjection.refresh(surface: producingSurface)
        let recordedTurn = (
            user: provider.messages.last(where: {
                $0.clientTurnId == continuityKey && $0.sender == .user
            }),
            assistant: provider.messages.last(where: {
                $0.clientTurnId == continuityKey && $0.sender == .ai
            })
        )
        switch presentation {
        case .visible:
            if let assistantMessage = recordedTurn.assistant {
                completeVisibleAgentHandoff(
                    originalRequest: originalRequest,
                    assistantMessage: assistantMessage,
                    barWindow: barWindow
                )
            } else {
                presentJournalAdmissionFailure(in: barWindow)
            }
        case .voiceOnly:
            break
        }
    }

    private func recentVisibleUserRequest(in barWindow: FloatingControlBarWindow) -> String? {
        let displayed = barWindow.state.displayedQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        if !displayed.isEmpty {
            return displayed
        }
        let history = barWindow.state.derivedChatHistory(from: historyChatProvider)
        return history.reversed().compactMap { exchange in
            exchange.question?.trimmingCharacters(in: .whitespacesAndNewlines)
        }.first { !$0.isEmpty }
    }

    private func dispatchChatQuery(
        _ message: String,
        barWindow: FloatingControlBarWindow,
        provider: ChatProvider,
        presentation: QueryPresentation,
        voiceTurnID: VoiceTurnID?
    ) async {
        guard voiceTurnID.map({ VoiceTurnCoordinator.shared.requireCurrentOwner(for: $0) != nil })
            ?? true else { return }
        switch presentation {
        case .visible:
            await sendAIQuery(
                message,
                barWindow: barWindow,
                provider: provider,
                voiceTurnID: voiceTurnID
            )
        case .voiceOnly:
            guard let voiceTurnID else { return }
            await sendVoiceOnlyQuery(
                message,
                barWindow: barWindow,
                provider: provider,
                voiceTurnID: voiceTurnID
            )
        }
    }

    private func chatTurnOwner(for presentation: QueryPresentation) -> ChatTurnOwner {
        switch presentation {
        case .visible(let fromVoice):
            return fromVoice ? .floatingVoice : .floatingDefault
        case .voiceOnly:
            return .floatingVoice
        }
    }

    private func showSharedProviderBusy(in barWindow: FloatingControlBarWindow, presentation: QueryPresentation) {
        let message = ChatMessage(text: "Omi is already responding in the app.", sender: .ai)
        switch presentation {
        case .visible:
            chatCancellable?.cancel()
            chatCancellable = nil
            barWindow.state.displayedQuery = ""
            barWindow.state.bindQuestionMessageId(nil)
            barWindow.state.setLocalAnswerOverride(message)
            barWindow.state.isAILoading = false
            barWindow.state.present(.mainResponse)
            barWindow.state.markConversationActivity()
            barWindow.resizeToResponseHeightPublic(animated: true)
        case .voiceOnly:
            FloatingBarVoicePlaybackService.shared.speakOneShot(message.text)
        }
    }

    private func completeVisibleAgentHandoff(
        originalRequest: String,
        assistantMessage: ChatMessage,
        barWindow: FloatingControlBarWindow
    ) {
        var message = assistantMessage
        message.isStreaming = false
        completeVisibleAgentResponse(
            userText: originalRequest,
            assistantMessage: message,
            barWindow: barWindow
        )
    }

    private func completeVisibleAgentResponse(
        userText: String,
        assistantMessage: ChatMessage,
        barWindow: FloatingControlBarWindow
    ) {
        chatCancellable?.cancel()
        chatCancellable = nil
        barWindow.state.clearSubmittedAIDraftIfUnchanged(userText)
        barWindow.state.displayedQuery = userText
        // Provider timeline is a journal projection. Bind the accepted row but
        // never enrich or append it from the surface.
        if let provider = historyChatProvider,
           let index = provider.messages.firstIndex(where: { $0.id == assistantMessage.id })
        {
            barWindow.state.bindAnswerMessage(provider.messages[index])
        } else {
            presentJournalAdmissionFailure(in: barWindow)
            return
        }
        barWindow.state.isAILoading = false
        barWindow.state.present(.mainResponse)
        barWindow.state.markConversationActivity()
        barWindow.resizeToResponseHeightPublic(animated: true)
    }

    private func presentJournalAdmissionFailure(in barWindow: FloatingControlBarWindow) {
        log("FloatingControlBarManager: refusing unjournaled visible response")
        chatCancellable?.cancel()
        chatCancellable = nil
        barWindow.state.setLocalAnswerOverride(
            ChatMessage(text: "⚠️ I couldn't save that response. Please try again.", sender: .ai)
        )
        barWindow.state.isAILoading = false
        barWindow.state.present(.mainResponse)
        barWindow.resizeToResponseHeightPublic(animated: true)
    }

    private func dispatchPendingQueryIfNeeded(
        barWindow: FloatingControlBarWindow,
        provider: ChatProvider
    ) async -> Bool {
        guard let pending = pendingFollowUpQuery else { return false }
        pendingFollowUpQuery = nil
        barWindow.state.currentQueryFromVoice = pending.presentation.fromVoice
        await routeQuery(
            pending.text,
            barWindow: barWindow,
            provider: provider,
            presentation: pending.presentation,
            voiceTurnID: pending.voiceTurnID
        )
        return true
    }

    /// Send a follow-up query in the existing AI conversation (used by PTT follow-up).
    func sendFollowUpQuery(
        _ query: String,
        fromVoice: Bool = false,
        voiceTurnID: VoiceTurnID? = nil
    ) {
        if fromVoice {
            guard let voiceTurnID,
                  VoiceTurnCoordinator.shared.requireCurrentOwner(for: voiceTurnID) != nil
            else { return }
        }
        guard let window = window, window.state.showingAIResponse else {
            // No active conversation — fall back to new conversation
            openAIInputWithQuery(query, fromVoice: fromVoice, voiceTurnID: voiceTurnID)
            return
        }
        guard let provider = activeFloatingProvider() else { return }

        // Archive current exchange as viewport id anchors (content stays on provider).
        window.state.archiveCurrentExchange(using: provider)

        if provider.isSending {
            let turnOwner = chatTurnOwner(for: .visible(fromVoice: fromVoice))
            guard provider.canInterruptActiveTurn(owner: turnOwner) else {
                showSharedProviderBusy(in: window, presentation: .visible(fromVoice: fromVoice))
                return
            }
            pendingFollowUpQuery = PendingFollowUpQuery(
                text: query,
                presentation: .visible(fromVoice: fromVoice),
                voiceTurnID: voiceTurnID
            )
            prepareVisibleQueryState(query, in: window, fromVoice: fromVoice)
            provider.stopAgent(owner: turnOwner, reason: .superseded)
            return
        }

        window.state.currentQueryFromVoice = fromVoice
        Task { @MainActor in
            guard voiceTurnID.map({ VoiceTurnCoordinator.shared.requireCurrentOwner(for: $0) != nil })
                ?? true else { return }
            await self.withQueryTracer(query: query, fromVoice: fromVoice) {
                await self.sendAIQuery(
                    query,
                    barWindow: window,
                    provider: provider,
                    voiceTurnID: voiceTurnID
                )
            }
        }
    }

    func openNotificationAsChat(_ notification: FloatingBarNotification) {
        guard notification.ownerID == RuntimeOwnerIdentity.currentOwnerId(),
              let window else { return }

        AnalyticsManager.shared.notificationClicked(
            notificationId: notification.id.uuidString,
            title: notification.title,
            assistantId: notification.assistantId,
            surface: "floating_bar"
        )

        notificationDismissWorkItem?.cancel()
        notificationDismissWorkItem = nil
        dismissNotificationAndAdvanceQueue(trackDismissal: false)
        if case .openWhatMattersNow(let recommendationID) = notification.action {
            ContextualTaskNavigationRouter.shared.request(recommendationID: recommendationID)
            return
        }
        _ = openNotificationConversation(notificationID: notification.id, in: window)
    }

    private func presentNotification(_ notification: FloatingBarNotification, in window: FloatingControlBarWindow) {
        guard notification.ownerID == RuntimeOwnerIdentity.currentOwnerId() else {
            log("FloatingControlBarManager: refusing to present stale-owner notification")
            return
        }
        persistNotificationMessageIfNeeded(notification)

        // The flag must survive the whole notification chain: when a queued
        // notification is presented the window is already visible from the
        // temp-show, so resetting it here would skip the re-hide in
        // dismissNotificationAndAdvanceQueue and leave the bar on screen
        // forever with "Show floating bar" off (#6972). The bar can also be
        // visible while disabled (e.g. a notification flushed right as an AI
        // conversation closes), so any presentation with the bar disabled
        // must arm the re-hide; dismissNotificationAndAdvanceQueue owns the reset.
        if !window.isVisible || !isEnabled {
            notificationWasTemporarilyShown = true
            if !window.isVisible {
                window.orderFrontRegardless()
            }
        }

        window.showNotification(notification)
        AnalyticsManager.shared.notificationSent(
            notificationId: notification.id.uuidString,
            title: notification.title,
            assistantId: notification.assistantId,
            surface: "floating_bar"
        )

        let dismissWorkItem = DispatchWorkItem { [weak self] in
            self?.dismissNotificationAndAdvanceQueue(trackDismissal: true)
        }
        notificationDismissWorkItem = dismissWorkItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 6.0, execute: dismissWorkItem)
    }

    private func dismissNotificationAndAdvanceQueue(trackDismissal: Bool) {
        guard let window else { return }

        let dismissedNotification = window.state.currentNotification
        window.dismissNotification()

        if trackDismissal, let dismissedNotification {
            AnalyticsManager.shared.notificationDismissed(
                notificationId: dismissedNotification.id.uuidString,
                title: dismissedNotification.title,
                assistantId: dismissedNotification.assistantId,
                surface: "floating_bar"
            )
        }

        if !window.state.showingAIConversation {
            while !pendingNotifications.isEmpty {
                let nextNotification = pendingNotifications.removeFirst()
                guard nextNotification.ownerID == RuntimeOwnerIdentity.currentOwnerId() else {
                    log("FloatingControlBarManager: dropping queued notification from stale runtime owner")
                    continue
                }
                presentNotification(nextNotification, in: window)
                return
            }
        }

        if notificationWasTemporarilyShown && !isEnabled && !window.state.showingAIConversation {
            window.orderOut(nil)
        }
        notificationWasTemporarilyShown = false
    }

    private func persistNotificationMessageIfNeeded(_ notification: FloatingBarNotification) {
        let ownerID = notification.ownerID
        guard !ownerID.isEmpty,
              RuntimeOwnerIdentity.currentOwnerId() == ownerID,
              let provider = historyChatProvider else { return }
        let surface = provider.mainChatSurfaceReference()
        let key = OwnerNotificationKey(ownerID: ownerID, notificationID: notification.id)
        guard storedNotificationMessages[key] == nil,
              !pendingNotificationJournalWrites.contains(key) else { return }

        // Notifications become chat-visible only after canonical journal
        // admission. The notification card itself remains an independent
        // presentation surface while this async write is pending.
        let bodyText = notification.message.trimmingCharacters(in: .whitespacesAndNewlines)
        let messageText = bodyText.isEmpty ? notification.title : bodyText
        let continuityKey = "notification:\(notification.id.uuidString)"
        pendingNotificationJournalWrites.insert(key)
        Task { @MainActor [weak self, weak provider] in
            guard let self else { return }
            guard let provider else {
                self.pendingNotificationJournalWrites.remove(key)
                return
            }
            let storedMessage = await Self.performOwnerBoundNotificationAdmission(
                ownerID: ownerID
            ) {
                let recorded = await provider.recordJournalExchange(
                    surface: surface,
                    ownerID: ownerID,
                    continuityKey: continuityKey,
                    userText: "",
                    assistantText: messageText,
                    origin: "proactive_notification"
                )
                return recorded.assistant
            }
            self.pendingNotificationJournalWrites.remove(key)
            guard storedMessage != nil else {
                log("FloatingControlBarManager: notification journal admission rejected")
                return
            }
            self.storedNotificationMessages[key] = StoredNotificationMessage(
                ownerID: ownerID,
                context: notification.context,
                messageClientTurnId: continuityKey,
                createdAt: Date()
            )
            self.mostRecentNotificationKey = key
        }
    }

    func mainChatSurfaceReference() -> AgentSurfaceReference {
        historyChatProvider?.mainChatSurfaceReference()
            ?? .mainChat(chatId: "default")
    }

    func realtimeVoiceSurfaceReference() -> AgentSurfaceReference {
        historyChatProvider?.realtimeVoiceSurfaceReference()
            ?? .realtimeVoice(chatId: "default")
    }

    func kernelVoiceContextSnapshot() async throws -> KernelVoiceContextSnapshot {
        guard let provider = historyChatProvider else {
            return .empty
        }
        return try await provider.prepareRealtimeVoiceContextSnapshot()
    }

    func recordExchange(
        surface: AgentSurfaceReference,
        ownerID: String? = nil,
        userText: String,
        assistantText: String,
        origin: String = "realtime_voice",
        continuityKey: String
    ) async -> Bool {
        await historyChatProvider?.kernelTurnProjection.recordExchange(
            surface: surface,
            userText: userText,
            assistantText: assistantText,
            origin: origin,
            continuityKey: continuityKey,
            ownerID: ownerID
        ) ?? false
    }

    func refreshKernelJournal(surface: AgentSurfaceReference) async {
        await historyChatProvider?.kernelTurnProjection.refresh(surface: surface)
    }

    /// Enrich the assistant turn that produced this pill's `agentSpawn` with one
    /// deterministic terminal block. This method never stages or records a
    /// second timeline row; SQLite journal revision replay updates every UI.
    @discardableResult
    func recordPillTerminalCompletion(
        ownerID: String,
        pillID: UUID,
        producingSurface: AgentSurfaceReference? = nil,
        runId: String?,
        userText: String,
        title: String = "Background agent",
        assistantText: String,
        status: String = "completed",
        resources: [ChatResource] = []
    ) async -> Bool {
        // This guard intentionally precedes every current-pill lookup. A late
        // owner-A terminal task may outlive the owner-change purge, and an
        // externally supplied UUID can be reused by owner B.
        guard !ownerID.isEmpty, RuntimeOwnerIdentity.currentOwnerId() == ownerID else {
            return false
        }
        let output = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !output.isEmpty else { return false }
        let prompt = userText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let provider = historyChatProvider else { return false }
        let pill = AgentPillsManager.shared.pills.first(where: {
            $0.id == pillID && $0.ownerID == ownerID
        })
        let surface = producingSurface
            ?? pill?.producingJournalSurface
            ?? provider.mainChatSurfaceReference()
        guard let updated = await Self.performOwnerBoundPillTerminalAdmission(
            ownerID: ownerID,
            record: {
                await provider.kernelTurnProjection.appendAgentCompletion(
                    surface: surface,
                    ownerID: ownerID,
                    pillID: pillID,
                    sessionID: pill?.canonicalSessionId,
                    runID: runId,
                    title: title,
                    promptSnippet: prompt,
                    output: output,
                    status: status,
                    resources: resources
                )
            }
        ) else { return false }
        observeAgentCompletionContext(pillID: pillID, runId: runId)
        if !resources.isEmpty,
           let projected = provider.messages.first(where: { $0.id == updated.turnId }) {
            deliverAgentArtifactCompletionToFloatingSurface(projected)
        }
        return true
    }

    static func performOwnerBoundPillTerminalAdmission<Value>(
        ownerID: String,
        currentOwnerID: @escaping @MainActor () -> String? = {
            RuntimeOwnerIdentity.currentOwnerId()
        },
        record: () async -> Value?
    ) async -> Value? {
        guard !ownerID.isEmpty, currentOwnerID() == ownerID else { return nil }
        guard let value = await record() else { return nil }
        guard currentOwnerID() == ownerID else { return nil }
        return value
    }

    private func observeAgentCompletionContext(pillID: UUID, runId: String?) {
        guard AuthService.shared.isSignedIn else { return }
        let stableReference = runId.flatMap { $0.isEmpty ? nil : $0 } ?? pillID.uuidString
        let subject: TaskContextSubject? = runId
            .flatMap { AgentRuntimeStatusStore.shared.projection(forRunID: $0) }
            .flatMap { projection in
                guard projection.surface.surfaceKind == "workstream" else { return nil }
                let workstreamID = projection.surface.externalRefId
                return TaskContextSubject(kind: .workstream, id: workstreamID, workstreamID: workstreamID)
            }
        guard let event = TaskLocalContextEvent.normalized(
            kind: .agent,
            rawReference: "agent-completed:\(stableReference)",
            subject: subject
        ) else { return }
        let matched = TaskContextSubjectMatcher.shared.resolve(event)
        Task { await TaskContextualResurfacingService.shared.observe(matched) }
    }

    private func openRecentNotificationConversationIfAvailable(in window: FloatingControlBarWindow) -> Bool {
        guard let key = mostRecentNotificationKey,
              key.ownerID == RuntimeOwnerIdentity.currentOwnerId() else { return false }
        return openNotificationConversation(notificationID: key.notificationID, in: window)
    }

    @discardableResult
    private func openNotificationConversation(notificationID: UUID, in window: FloatingControlBarWindow) -> Bool {
        purgeExpiredNotificationMessages()

        guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return false }
        let key = OwnerNotificationKey(ownerID: ownerID, notificationID: notificationID)
        guard let stored = storedNotificationMessages[key],
              stored.ownerID == ownerID,
              Date().timeIntervalSince(stored.createdAt) <= Self.recentNotificationReuseInterval,
              let provider = historyChatProvider,
              let notificationMessage = provider.messages.last(where: {
                  $0.clientTurnId == stored.messageClientTurnId
              }) else {
            return false
        }
        notificationDismissWorkItem?.cancel()
        notificationDismissWorkItem = nil
        pendingNotifications.removeAll { $0.id == notificationID }
        if window.state.currentNotification != nil {
            window.dismissNotification()
        }

        window.cancelPendingDismiss()
        window.savePreChatCenterIfNeeded()
        window.cancelInputHeightObserver()
        let shouldRestoreVisibleConversation = window.state.canRestoreVisibleConversation
        if shouldRestoreVisibleConversation {
            archiveVisibleConversationIfNeeded(in: window)
        } else if window.state.hasVisibleConversation {
            window.state.clearVisibleConversation()
        }

        window.state.present(.mainResponse)
        window.state.isAILoading = false
        if !shouldRestoreVisibleConversation {
            window.state.clearViewport()
        }
        window.state.bindAnswerMessage(notificationMessage)
        window.state.markConversationActivity()
        window.resizeToResponseHeightPublic(animated: true)
        window.orderFrontRegardless()
        window.focusInputField()

        pendingNotificationContext = PendingNotificationContext(
            message: notificationMessage,
            context: stored.context
        )
        Task {
            if let provider = activeFloatingProvider() {
                await provider.invalidateAgentSurface(surface: provider.mainChatSurfaceReference())
            }
        }
        storedNotificationMessages.removeValue(forKey: key)
        if mostRecentNotificationKey == key {
            mostRecentNotificationKey = nil
        }
        return true
    }

    private func archiveVisibleConversationIfNeeded(in window: FloatingControlBarWindow) {
        window.state.archiveCurrentExchange(using: self.historyChatProvider)
        window.state.displayedQuery = ""
        window.state.bindQuestionMessageId(nil)
    }

    private func purgeExpiredNotificationMessages() {
        let now = Date()
        storedNotificationMessages = storedNotificationMessages.filter { _, stored in
            now.timeIntervalSince(stored.createdAt) <= Self.recentNotificationReuseInterval
        }

        if let mostRecentNotificationKey,
           storedNotificationMessages[mostRecentNotificationKey] == nil {
            self.mostRecentNotificationKey = nil
        }
    }

    private func activeFloatingProvider() -> ChatProvider? {
        historyChatProvider
    }

    private func deliverAgentArtifactCompletionToFloatingSurface(_ message: ChatMessage) {
        guard let window else { return }
        chatCancellable?.cancel()
        chatCancellable = nil

        var completedMessage = message
        completedMessage.isStreaming = false

        window.state.archiveCurrentExchange(using: self.historyChatProvider)

        if self.historyChatProvider?.messages.contains(where: { $0.id == completedMessage.id }) == true {
            window.state.bindAnswerMessage(completedMessage)
        } else {
            window.state.setLocalAnswerOverride(completedMessage)
        }
        window.state.displayedQuery = ""
        window.state.bindQuestionMessageId(nil)
        window.state.isAILoading = false
        if window.state.conversationSurface == .mainInput || window.state.conversationSurface == .mainResponse {
            window.state.present(.mainResponse)
            window.resizeToResponseHeightPublic(animated: true)
        } else {
            window.state.markConversationActivity()
        }
    }

    /// Access the bar state for PTT updates.
    var barState: FloatingControlBarState? {
        return window?.state
    }

    /// Resize the floating bar for PTT state changes.
    func resizeForPTT(expanded: Bool) {
        window?.resizeForPTTState(expanded: expanded)
    }

    // MARK: - AI Query

    private func prepareVisibleQueryState(_ message: String, in barWindow: FloatingControlBarWindow, fromVoice: Bool) {
        activeQueryGeneration += 1
        chatCancellable?.cancel()
        chatCancellable = nil
        FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
        barWindow.beginVisibleMainQuery(message, fromVoice: fromVoice, animated: true)
    }

    private func isActiveQueryGeneration(_ generation: Int) -> Bool {
        generation == activeQueryGeneration
    }

    /// Screen / visual cues that, when present in a query, trigger a screenshot capture.
    nonisolated private static let screenshotCues = [
        // explicit screen references
        "screen", "on my display", "what's on", "whats on", "on display",
        "look at", "looking at", "do you see", "can you see", "what do you see",
        "what am i looking at", "screenshot", "visible", "in front of me",
        "this page", "this window", "this app", "this tab", "this site",
        // visual verb + deictic (this/that/it)
        "read this", "read that", "read it", "summarize this", "summarize that",
        "explain this", "explain that", "what is this", "what's this", "whats this",
        "what does this", "what is that", "what's that", "translate this", "translate that",
        "fix this", "fix that", "what's this error", "this error", "this code",
        "this image", "this picture", "this photo", "this diagram", "this chart",
        "highlighted", "selected", "this selection",
    ]

    /// Heuristic: does this query plausibly need a screenshot of the user's screen?
    /// Defaults to NO — captures only when the text references the screen, something
    /// visual, or a visual verb paired with a deictic ("read this", "what's that").
    /// Keeps screenshots off the ~70% of queries that never look at the screen.
    nonisolated static func queryNeedsScreenshot(_ message: String) -> Bool {
        let m = message.lowercased()
        return screenshotCues.contains(where: { m.contains($0) })
    }

    private func sendAIQuery(
        _ message: String,
        barWindow: FloatingControlBarWindow,
        provider: ChatProvider,
        voiceTurnID: VoiceTurnID? = nil
    ) async {
        // Defensive cancellation guard. `sendAIQuery` is a long async function
        // (screenshot capture, limiter check, provider.sendMessage). If a parent
        // task cancels us (e.g. closeAIConversation racing, the user firing a
        // second query, a future refactor that runs the router in parallel),
        // we should bail before doing setup work — especially before
        // `limiter.recordQuery()` (which would consume a local quota slot)
        // and before the screenshot capture. This matches the pattern used
        // elsewhere in the codebase (OnboardingChatView, FileIndexingView,
        // DesktopHomeView) and is cheap insurance against future refactors.
        guard !Task.isCancelled,
              voiceTurnID.map({ VoiceTurnCoordinator.shared.requireCurrentOwner(for: $0) != nil })
                ?? true
        else { return }

        // QueryTracer: `pre_llm` brackets everything between query submission and
        // the ChatProvider call (screenshot capture, usage checks, filler audio).
        let currentTracer = QueryTracerContext.current
        currentTracer?.begin("pre_llm")
        let queryFromVoice = barWindow.state.currentQueryFromVoice
        let voiceCompletionToken = queryFromVoice
            ? VoiceTurnCoordinator.shared.nonHubCompletionToken()
            : nil
        var voiceCompletionOutcome = VoiceNonHubCompletionOutcome.providerFailed
        defer {
            if let voiceCompletionToken {
                VoiceTurnCoordinator.shared.completeNonHubProvider(
                    voiceCompletionToken,
                    outcome: voiceCompletionOutcome
                )
            }
        }
        prepareVisibleQueryState(message, in: barWindow, fromVoice: queryFromVoice)
        let generation = activeQueryGeneration

        // Re-check after the await-free setup work above.
        guard !Task.isCancelled else { return }

        FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()

        // Only capture a screenshot when the query is actually about what's on
        // screen. Capturing on every query cost ~225ms + a large image in the
        // prompt for questions that never look at the screen ("what's my goal").
        let needsScreenshot = Self.queryNeedsScreenshot(message)
        let screenshotData: Data?
        if needsScreenshot {
            guard voiceTurnID.map({ VoiceTurnCoordinator.shared.requireCurrentOwner(for: $0) != nil })
                ?? true else { return }
            currentTracer?.begin("screenshot_capture")
            screenshotData = await Task.detached { () -> Data? in
                return ScreenCaptureManager.captureScreenData()
            }.value
            guard voiceTurnID.map({ VoiceTurnCoordinator.shared.requireCurrentOwner(for: $0) != nil })
                ?? true else { return }
            currentTracer?.end("screenshot_capture")
        } else {
            screenshotData = nil
            currentTracer?.mark("screenshot_capture")
        }
        barWindow.orderFrontRegardless()

        AnalyticsManager.shared.floatingBarQuerySent(messageLength: message.count, hasScreenshot: screenshotData != nil)

        let shouldPlayVoice = ShortcutSettings.shared.shouldSpeakFloatingBarResponse(
            forVoiceQuery: barWindow.state.currentQueryFromVoice
        )
        if shouldPlayVoice {
            // QueryTracer: hand the tracer to the playback service so it can close
            // the `tts_start` span when the first real audio reaches the speaker.
            FloatingBarVoicePlaybackService.shared.tracer = currentTracer
            FloatingBarVoicePlaybackService.shared.playFillerIfEnabled()
        }

        // Provider is already initialized by ViewModelContainer at app launch

        let clientTurnId = UUID().uuidString

        // Observe messages for streaming response — bind viewport ids only.
        chatCancellable?.cancel()
        barWindow.state.beginTurn(clientTurnId: clientTurnId)
        barWindow.state.isAILoading = true
        var hasSetUpResponseHeight = false
        chatCancellable = provider.$messages
            .receive(on: DispatchQueue.main)
            .sink { [weak self, weak barWindow] messages in
                guard let self, self.isActiveQueryGeneration(generation) else { return }
                guard let aiMessage = messages.last(where: {
                    $0.clientTurnId == clientTurnId && $0.sender == .ai
                }) else { return }

                // Viewport cursor over provider messages (preserves contentBlocks via id lookup)
                barWindow?.state.bindAnswerMessage(aiMessage)
                if let userMessage = messages.last(where: {
                    $0.clientTurnId == clientTurnId && $0.sender == .user
                }) {
                    barWindow?.state.bindQuestionMessageId(userMessage.id)
                }
                if shouldPlayVoice {
                    FloatingBarVoicePlaybackService.shared.updateStreamingResponseIfEnabled(
                        aiMessage,
                        isFinal: !aiMessage.isStreaming
                    )
                }

                if aiMessage.isStreaming {
                    barWindow?.state.isAILoading = false
                    if let barWindow = barWindow, !hasSetUpResponseHeight {
                        hasSetUpResponseHeight = true
                        if !barWindow.state.showingAIResponse {
                            OmiMotion.withGated(.spring(response: 0.24, dampingFraction: 0.9)) {
                                barWindow.state.present(.mainResponse)
                            }
                        }
                        barWindow.resizeToResponseHeightPublic(animated: true)
                    }
                } else {
                    barWindow?.state.isAILoading = false
                }
            }

        let notificationContextSuffix = notificationContextSuffixIfNeeded(for: message)
        currentTracer?.end("pre_llm")
        guard voiceTurnID.map({ VoiceTurnCoordinator.shared.requireCurrentOwner(for: $0) != nil })
            ?? true else { return }
        var journalAccepted: Bool?
        let providerResponse: String?
        if let voiceTurnID {
            let outcome = await Self.performOwnerBoundVoiceDispatch(
                turnID: voiceTurnID,
                dispatch: {
                    await provider.sendMessage(
                        message,
                        model: selectedFloatingModel,
                        systemPromptSuffix: notificationContextSuffix,
                        systemPromptStyle: .floating,
                        surfaceRef: provider.mainChatSurfaceReference(),
                        imageData: screenshotData,
                        turnOwner: chatTurnOwner(for: .visible(fromVoice: queryFromVoice)),
                        clientTurnId: clientTurnId,
                        onAccepted: { [weak barWindow] in
                            barWindow?.state.clearSubmittedAIDraftIfUnchanged(message)
                        },
                        onJournalFinalized: { accepted in
                            journalAccepted = accepted
                        }
                    )
                })
            guard case .dispatched(let response) = outcome else { return }
            providerResponse = response
        } else {
            providerResponse = await provider.sendMessage(
                message,
                model: selectedFloatingModel,
                systemPromptSuffix: notificationContextSuffix,
                systemPromptStyle: .floating,
                surfaceRef: provider.mainChatSurfaceReference(),
                imageData: screenshotData,
                turnOwner: chatTurnOwner(for: .visible(fromVoice: queryFromVoice)),
                clientTurnId: clientTurnId,
                onAccepted: { [weak barWindow] in
                    barWindow?.state.clearSubmittedAIDraftIfUnchanged(message)
                },
                onJournalFinalized: { accepted in
                    journalAccepted = accepted
                }
            )
        }
        guard voiceTurnID.map({ VoiceTurnCoordinator.shared.requireCurrentOwner(for: $0) != nil })
            ?? true else { return }
        if providerResponse != nil {
            voiceCompletionOutcome = journalAccepted == true ? .journalAccepted : .journalFailed
        }

        if await dispatchPendingQueryIfNeeded(barWindow: barWindow, provider: provider) {
            return
        }

        guard isActiveQueryGeneration(generation) else { return }
        if let syncedUserMessage = provider.messages.last(where: {
            $0.clientTurnId == clientTurnId && $0.sender == .user && $0.isSynced
        }) {
            barWindow.state.bindQuestionMessageId(syncedUserMessage.id)
        }
        if let finalAIMessage = provider.messages.last(where: {
            $0.clientTurnId == clientTurnId && $0.sender == .ai
        }) {
            barWindow.state.bindAnswerMessage(finalAIMessage)
        }
        // Cancel the messages subscription now that streaming is done.
        // Leaving it alive lets later sidebar mutations overwrite the floating bar display.
        chatCancellable?.cancel()
        chatCancellable = nil

        // Handle errors after sendMessage completes
        barWindow.state.isAILoading = false

        if let errorText = provider.displayErrorMessage {
            // Provider reported an error (timeout, bridge crash, etc.).
            // Prefer mutating the provider-backed answer in place; only use
            // localAnswerOverride when there is no provider message to update.
            if let existing = barWindow.state.currentAIMessage(from: provider),
               let index = provider.messages.firstIndex(where: { $0.id == existing.id })
            {
                let existingText = provider.messages[index].text
                provider.messages[index].text = existingText.isEmpty
                    ? "⚠️ \(errorText)"
                    : existingText + "\n\n⚠️ \(errorText)"
                provider.messages[index].isStreaming = false
                barWindow.state.bindAnswerMessage(provider.messages[index])
            } else {
                barWindow.state.setLocalAnswerOverride(ChatMessage(text: "⚠️ \(errorText)", sender: .ai))
            }
        } else if barWindow.state.shouldPresentEmptyResponseFailure(from: provider) {
            // No error and no provider-backed answer content (text/blocks/resources).
            // Never call setLocalAnswerOverride when an answerMessageId is already
            // bound — that would clear the provider answer (including block-only).
            barWindow.state.setLocalAnswerOverride(
                ChatMessage(text: "Failed to get a response. Please try again.", sender: .ai)
            )
        }

        // Ensure the response view is visible and resized (handles the case where
        // the sink never fired because no streaming data arrived before the error)
        if !barWindow.state.showingAIResponse {
            OmiMotion.withGated(.spring(response: 0.24, dampingFraction: 0.9)) {
                barWindow.state.present(.mainResponse)
            }
            barWindow.resizeToResponseHeightPublic(animated: true)
        }

        if shouldPlayVoice {
            FloatingBarVoicePlaybackService.shared.updateStreamingResponseIfEnabled(
                barWindow.state.currentAIMessage(from: provider),
                isFinal: true
            )
        }
    }

    private func sendVoiceOnlyQuery(
        _ message: String,
        barWindow: FloatingControlBarWindow,
        provider: ChatProvider,
        voiceTurnID: VoiceTurnID
    ) async {
        guard VoiceTurnCoordinator.shared.requireCurrentOwner(for: voiceTurnID) != nil else {
            return
        }
        let currentTracer = QueryTracerContext.current
        currentTracer?.begin("pre_llm")
        activeQueryGeneration += 1
        let generation = activeQueryGeneration
        let voiceCompletionToken = VoiceTurnCoordinator.shared.nonHubCompletionToken()
        var voiceCompletionOutcome = VoiceNonHubCompletionOutcome.providerFailed
        defer {
            if let voiceCompletionToken {
                VoiceTurnCoordinator.shared.completeNonHubProvider(
                    voiceCompletionToken,
                    outcome: voiceCompletionOutcome
                )
            }
        }

        barWindow.state.currentQueryFromVoice = true
        if let turnID = VoiceTurnCoordinator.shared.activeTurnID {
            VoiceTurnCoordinator.shared.send(.clearPresentation(turnID: turnID))
        }

        FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
        FloatingBarVoicePlaybackService.shared.tracer = currentTracer
        FloatingBarVoicePlaybackService.shared.playFillerIfEnabled()

        let needsScreenshot = Self.queryNeedsScreenshot(message)
        let screenshotData: Data?
        if needsScreenshot {
            guard VoiceTurnCoordinator.shared.requireCurrentOwner(for: voiceTurnID) != nil else {
                return
            }
            currentTracer?.begin("screenshot_capture")
            screenshotData = await Task.detached { () -> Data? in
                ScreenCaptureManager.captureScreenData()
            }.value
            guard VoiceTurnCoordinator.shared.requireCurrentOwner(for: voiceTurnID) != nil else {
                return
            }
            currentTracer?.end("screenshot_capture")
        } else {
            screenshotData = nil
            currentTracer?.mark("screenshot_capture")
        }

        AnalyticsManager.shared.floatingBarQuerySent(messageLength: message.count, hasScreenshot: screenshotData != nil)

        let clientTurnId = UUID().uuidString
        chatCancellable?.cancel()
        chatCancellable = provider.$messages
            .receive(on: DispatchQueue.main)
            .sink { [weak self] messages in
                guard let self, self.isActiveQueryGeneration(generation) else { return }
                guard let aiMessage = messages.last(where: {
                    $0.clientTurnId == clientTurnId && $0.sender == .ai
                }) else { return }
                FloatingBarVoicePlaybackService.shared.updateStreamingResponseIfEnabled(
                    aiMessage,
                    isFinal: !aiMessage.isStreaming
                )
            }

        currentTracer?.end("pre_llm")
        guard VoiceTurnCoordinator.shared.requireCurrentOwner(for: voiceTurnID) != nil else {
            return
        }
        var journalAccepted: Bool?
        let dispatchOutcome = await Self.performOwnerBoundVoiceDispatch(
            turnID: voiceTurnID,
            dispatch: {
                await provider.sendMessage(
                    message,
                    model: selectedFloatingModel,
                    systemPromptStyle: .floating,
                    surfaceRef: provider.mainChatSurfaceReference(),
                    imageData: screenshotData,
                    turnOwner: .floatingVoice,
                    clientTurnId: clientTurnId,
                    onJournalFinalized: { accepted in
                        journalAccepted = accepted
                    }
                )
            })
        guard case .dispatched(let providerResponse) = dispatchOutcome else { return }
        guard VoiceTurnCoordinator.shared.requireCurrentOwner(for: voiceTurnID) != nil else {
            return
        }
        if providerResponse != nil {
            voiceCompletionOutcome = journalAccepted == true ? .journalAccepted : .journalFailed
        }

        if await dispatchPendingQueryIfNeeded(barWindow: barWindow, provider: provider) {
            return
        }

        guard isActiveQueryGeneration(generation) else { return }
        if let finalAIMessage = provider.messages.last(where: {
            $0.clientTurnId == clientTurnId && $0.sender == .ai
        }) {
            FloatingBarVoicePlaybackService.shared.updateStreamingResponseIfEnabled(finalAIMessage, isFinal: true)
        } else if let errorText = provider.displayErrorMessage, !errorText.isEmpty {
            FloatingBarVoicePlaybackService.shared.speakOneShot(errorText)
        } else {
            FloatingBarVoicePlaybackService.shared.speakOneShot("I couldn't get a response. Please try again.")
        }

        chatCancellable?.cancel()
        chatCancellable = nil
    }

    private func notificationContextSuffixIfNeeded(for message: String) -> String? {
        guard let pendingNotificationContext else { return nil }

        let trimmedMessage = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedMessage.isEmpty else { return nil }

        var provenanceLines: [String] = []
        if let context = pendingNotificationContext.context {
            provenanceLines.append(
                "If the user asks why they received the notification or what it was based on, start from this exact notification provenance instead of guessing:"
            )
            provenanceLines.append("notification_title: \(context.sourceTitle)")
            provenanceLines.append("assistant_id: \(context.assistantId)")
            if let sourceApp = context.sourceApp, !sourceApp.isEmpty {
                provenanceLines.append("source_app: \(sourceApp)")
            }
            if let windowTitle = context.windowTitle, !windowTitle.isEmpty {
                provenanceLines.append("window_title: \(windowTitle)")
            }
            if let contextSummary = context.contextSummary, !contextSummary.isEmpty {
                provenanceLines.append("context_summary: \(contextSummary)")
            }
            if let currentActivity = context.currentActivity, !currentActivity.isEmpty {
                provenanceLines.append("current_activity: \(currentActivity)")
            }
            if let reasoning = context.reasoning, !reasoning.isEmpty {
                provenanceLines.append("reasoning: \(reasoning)")
            }
            if let detail = context.detail, !detail.isEmpty {
                provenanceLines.append("detail: \(detail)")
            }
        }

        let provenanceBlock = provenanceLines.isEmpty ? "" : "\n\n" + provenanceLines.joined(separator: "\n")

        return """
<floating_bar_notification_context>
Before the user's latest message, you proactively sent this assistant message in the floating bar.
Treat it as your immediately previous turn in the same conversation and answer as a continuation.

Assistant message:
\(pendingNotificationContext.message.text)\(provenanceBlock)
</floating_bar_notification_context>
"""
    }

    func clearPendingNotificationContext() {
        pendingNotificationContext = nil
    }
}

// Expose resizeToResponseHeight for the manager
extension FloatingControlBarWindow {
    func resizeToResponseHeightPublic(animated: Bool = false) {
        resizeToResponseHeight(animated: animated)
    }

    func resizeForActiveAgentChatPublic(pillID: UUID? = nil, animated: Bool = false) {
        let responseHeight = responseHeightConfiguration()
        let surface: FloatingConversationSurface
        if let pillID {
            surface = .agent(pillID)
            state.present(surface)
        } else {
            surface = state.conversationSurface
        }
        let targetSize = NSSize(
            width: max(expandedContentWidth, currentResponseSurfaceWidth()),
            height: max(responseHeight.initialHeight, currentResponseSurfaceHeight())
        )
        if targetSize.height > currentResponseSurfaceHeight() + 2 || targetSize.width > currentResponseSurfaceWidth() + 2 {
            resizeAnchored(
                to: targetSize,
                makeResizable: true,
                animated: animated,
                animationDuration: 0.10,
                anchorTop: true
            )
        }
        setupResponseHeightObserver(for: surface, maxHeight: responseHeight.maxHeight)
    }

    /// Switch from the Ask Omi input panel to the response-sized surface before
    /// routing a visible query. Keeping this transition in the window preserves
    /// the invariant that conversation state and NSPanel sizing move together.
    func beginVisibleMainQuery(_ message: String, fromVoice: Bool, animated: Bool = true) {
        cancelInputHeightObserver()
        state.currentQueryFromVoice = fromVoice
        state.markAIDraftSubmitted(message)
        state.displayedQuery = message
        state.clearCurrentAnswerAnchors()
        // clearCurrentAnswerAnchors keeps archived exchanges; sendAIQuery binds the real turn id.
        state.isAILoading = true
        state.markConversationActivity()
        state.resetMeasuredContentHeight(for: .mainResponse)
        beginMainResponseHeight(animated: animated)
        orderFrontRegardless()
    }

    /// Resize the window to the normal Ask Omi input height after exiting an
    /// agent surface to `.mainInput`. Cancels the response-height observer and
    /// installs the input-height observer so non-Notch displays preserve the
    /// pill-mode "back to Omi chat" behavior instead of using Notch row navigation.
    func resizeForMainInputAfterAgentExit() {
        responseHeightCancellable?.cancel()
        responseHeightCancellable = nil
        state.responseContentHeight = 0
        state.inputViewHeight = inputPanelHeight
        let inputSize = NSSize(width: expandedContentWidth, height: inputPanelHeight)
        resizeAnchored(to: inputSize, makeResizable: false, animated: true, anchorTop: true)
        setupInputHeightObserver()
    }

    /// Save the current center point so closeAIConversation can restore position.
    /// Only saves if preChatCenter is not already set (avoids overwriting during follow-ups).
    /// If a close/restore animation is in flight (pendingRestoreOrigin is set), snaps the
    /// window to that target first so the saved center reflects the true pill position,
    /// not an intermediate animation frame.
    /// In non-draggable mode, always snaps to the fixed default position so the saved
    /// center is always the canonical top-center default, never a drifted value.
    func savePreChatCenterIfNeeded() {
        guard preChatCenter == nil else { return }
        let size = collapsedBarSize
        if !ShortcutSettings.shared.draggableBarEnabled || notchModeEnabled {
            // Non-draggable: always snap to the default pill position before saving.
            // This ensures preChatCenter is always the canonical default, not a
            // mid-animation frame or drifted position from a previous session.
            // Notch mode snaps to its fixed idle/hover surface frame instead
            // (usually a no-op — the frame never left it).
            let snapFrame: NSRect
            if notchModeEnabled {
                snapFrame = defaultTopCenteredFrame(
                    for: responseGlowWindowSizeForCurrentScreen(forSurfaceSize: notchFixedIdleSurfaceSize())
                )
            } else {
                snapFrame = NSRect(origin: defaultPillOrigin(), size: size)
            }
            isResizingProgrammatically = true
            setFrame(snapFrame, display: true, animate: false)
            isResizingProgrammatically = false
            pendingRestoreOrigin = nil
        } else if let restoreOrigin = pendingRestoreOrigin {
            // Draggable: if a restore animation is running, snap to its target immediately
            // so we record the correct pill position rather than a mid-animation frame.
            isResizingProgrammatically = true
            setFrame(NSRect(origin: restoreOrigin, size: size), display: true, animate: false)
            isResizingProgrammatically = false
            pendingRestoreOrigin = nil
        }
        if !notchModeEnabled, state.isNotchHoverMenuVisible {
            // Chat is opening from the taller pill agent list. The pill's true
            // center is the list's top-center minus half a pill — recording the
            // list frame's midpoint would drop the restored pill lower every
            // open/close cycle.
            preChatCenter = NSPoint(x: frame.midX, y: frame.maxY - size.height / 2)
            return
        }
        preChatCenter = NSPoint(x: frame.midX, y: frame.midY)
    }

    /// Invalidates any in-flight windowDidResignKey dismiss animation so a new PTT
    /// query won't be immediately closed by a stale completion block.
    func cancelPendingDismiss() {
        resignKeyAnimationToken += 1
        frameAnimationToken += 1
        if !ShortcutSettings.shared.draggableBarEnabled {
            pendingRestoreOrigin = nil
        }
        suppressHoverResize = false
        isResizingProgrammatically = false
    }
}
