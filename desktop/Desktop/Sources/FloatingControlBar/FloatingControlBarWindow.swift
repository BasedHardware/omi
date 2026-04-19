import Cocoa
import Combine
import SwiftUI

private final class FloatingBarHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        true
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
    static let expandedBarSize = NSSize(width: 210, height: 50)
    private static let maxBarSize = NSSize(width: 1200, height: 1000)
    private static let expandedWidth: CGFloat = 430
    private static let notificationWidth: CGFloat = 430
    private static let notificationHeight: CGFloat = 108
    private static let notificationSpacing: CGFloat = 8
    /// Minimum window height when AI response first appears.
    private static let minResponseHeight: CGFloat = 250
    /// Base height used as the reference for 2× cap (same as current default response height).
    private static let defaultBaseResponseHeight: CGFloat = 430
    /// Overhead (px) added to measured scroll content to account for control bar, header, follow-up input, and padding.
    private static let responseViewOverhead: CGFloat = 190

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
        let initialRect = NSRect(origin: .zero, size: FloatingControlBarWindow.minBarSize)

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
        self.level = .floating
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.isMovableByWindowBackground = false
        self.delegate = self
        self.minSize = FloatingControlBarWindow.minBarSize
        self.maxSize = FloatingControlBarWindow.maxBarSize

        setupViews()

        if ShortcutSettings.shared.draggableBarEnabled,
           let savedPosition = UserDefaults.standard.string(forKey: FloatingControlBarWindow.positionKey) {
            let origin = NSPointFromString(savedPosition)
            // Verify saved position is on a visible screen
            let onScreen = NSScreen.screens.contains { $0.visibleFrame.contains(NSPoint(x: origin.x + 14, y: origin.y + 14)) }
            if onScreen {
                self.setFrameOrigin(origin)
            } else {
                centerOnMainScreen()
            }
        } else {
            centerOnMainScreen()
        }
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

        guard state.showingAIConversation else { return }

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
        let container = NSView()
        self.contentView = container

        if let hosting = hostingView {
            hosting.sizingOptions = [.minSize, .maxSize]
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
                self?.validatePositionOnScreenChange()
            }
        }

        // Follow cursor across monitors — poll mouse position to move bar instantly
        startCursorScreenTracking()
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

        if ShortcutSettings.shared.draggableBarEnabled {
            // Translate position proportionally
            let relX = currentVisible.width > 0 ? (frame.origin.x - currentVisible.origin.x) / currentVisible.width : 0.5
            let relY = currentVisible.height > 0 ? (frame.origin.y - currentVisible.origin.y) / currentVisible.height : 1.0
            let newX = targetVisible.origin.x + relX * targetVisible.width
            let newY = targetVisible.origin.y + relY * targetVisible.height
            setFrameOrigin(NSPoint(x: newX, y: newY))
            UserDefaults.standard.set(NSStringFromPoint(frame.origin), forKey: FloatingControlBarWindow.positionKey)
        } else {
            // Non-draggable: center on new screen
            let x = targetVisible.midX - frame.width / 2
            let y = targetVisible.maxY - frame.height - 20
            setFrameOrigin(NSPoint(x: x, y: y))
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

        // Cancel any in-flight chat streaming to prevent re-expansion
        FloatingControlBarManager.shared.cancelChat()

        // Cancel dynamic response-height observer and reset its state
        responseHeightCancellable?.cancel()
        responseHeightCancellable = nil
        state.responseContentHeight = 0

        // Cancel PTT if in follow-up mode
        if state.isVoiceFollowUp {
            PushToTalkManager.shared.cancelListening()
        }

        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            state.showingAIConversation = false
            state.showingAIResponse = false
            state.aiInputText = ""
            state.isVoiceFollowUp = false
            state.voiceFollowUpTranscript = ""
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
        let size = FloatingControlBarWindow.minBarSize
        let restoreOrigin: NSPoint
        if !ShortcutSettings.shared.draggableBarEnabled {
            restoreOrigin = defaultPillOrigin()
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
        NSAnimationContext.beginGrouping()
        NSAnimationContext.current.duration = 0.3
        NSAnimationContext.current.allowsImplicitAnimation = false
        NSAnimationContext.current.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        self.setFrame(NSRect(origin: restoreOrigin, size: size), display: true, animate: true)
        NSAnimationContext.endGrouping()
        let targetFrame = NSRect(origin: restoreOrigin, size: size)
        preChatCenter = nil
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
            guard let self = self else { return }
            self.isResizingProgrammatically = false
            self.pendingRestoreOrigin = nil
            // Safety net: only snap if no new AI session was opened while the animation ran.
            // Without this guard, a rapid PTT query that fires within 0.35s gets collapsed
            // back to the pill position by this stale completion block.
            guard !self.state.showingAIConversation else { return }
            if self.frame != targetFrame {
                self.setFrame(targetFrame, display: true, animate: false)
            }
        }

        // Allow hover resizes again after the animation settles.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
            self?.suppressHoverResize = false
            FloatingControlBarManager.shared.flushQueuedNotificationsIfPossible()

            // If the user has the bar disabled, hide it completely after closing the
            // AI conversation instead of leaving the compact pill visible.
            if !FloatingControlBarManager.shared.isEnabled {
                self?.orderOut(nil)
            }
        }
    }

    private func hideBar() {
        self.orderOut(nil)
        AnalyticsManager.shared.floatingBarToggled(visible: false, source: state.showingAIConversation ? "escape_ai" : "bar_button")
        onHide?()
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
            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                state.showingAIConversation = true
                state.showingAIResponse = true
                state.isAILoading = false
                state.aiInputText = ""
            }
            resizeToResponseHeight(animated: true)
        } else {
            // Anchor from top so the control bar stays visually in place, input grows downward.
            let inputSize = NSSize(width: FloatingControlBarWindow.expandedWidth, height: 120)
            resizeAnchored(to: inputSize, makeResizable: false, animated: true, anchorTop: true)

            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                state.showingAIConversation = true
                state.showingAIResponse = false
                state.isAILoading = false
                state.aiInputText = ""
                state.currentAIMessage = nil
                // Match the explicit resize height so the observer doesn't immediately override it
                state.inputViewHeight = 120
            }
            setupInputHeightObserver()
        }

        // Make the window key so the OmiTextEditor's focusOnAppear can take effect.
        // The text editor itself handles focusing via updateNSView once it's in the window.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [weak self] in
            self?.makeKeyAndOrderFront(nil)
        }

        // Fallback: explicitly focus the input after SwiftUI layout settles.
        // The AutoFocusScrollView.viewDidMoveToWindow() fires once and can miss
        // if the window isn't yet key at that moment.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self] in
            self?.focusInputField()
        }

    }

    func clearVisibleConversationFromUI() {
        guard state.showingAIConversation else { return }

        FloatingControlBarManager.shared.cancelChat()
        FloatingControlBarManager.shared.clearPendingNotificationContext()
        responseHeightCancellable?.cancel()
        responseHeightCancellable = nil
        cancelInputHeightObserver()

        withAnimation(.spring(response: 0.3, dampingFraction: 0.88)) {
            state.clearVisibleConversation()
            state.showingAIConversation = true
            state.inputViewHeight = 120
        }

        let inputSize = NSSize(width: FloatingControlBarWindow.expandedWidth, height: 120)
        resizeAnchored(to: inputSize, makeResizable: false, animated: true, anchorTop: true)
        setupInputHeightObserver()

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) { [weak self] in
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
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    state.isAILoading = false
                    state.showingAIResponse = true
                }
                resizeToResponseHeight(animated: true)
            }
            state.aiResponseText += text
        case "done":
            withAnimation(.easeOut(duration: 0.2)) {
                state.isAILoading = false
            }
            if !text.isEmpty {
                state.aiResponseText = text
            }
        case "error":
            withAnimation(.easeOut(duration: 0.2)) {
                state.isAILoading = false
            }
            state.aiResponseText = text.isEmpty ? "An unknown error occurred." : text
        default:
            break
        }
    }

    // MARK: - Window Geometry

    /// Center-center: preserves midpoint (used by hover expand/collapse).
    private func originForCenterAnchor(newSize: NSSize) -> NSPoint {
        NSPoint(
            x: frame.midX - newSize.width / 2,
            y: frame.midY - newSize.height / 2
        )
    }

    /// Top-center: keeps top edge fixed, centers horizontally (used by chat expand/collapse).
    private func originForTopCenterAnchor(newSize: NSSize) -> NSPoint {
        let top = frame.origin.y + frame.height
        return NSPoint(
            x: frame.midX - newSize.width / 2,
            y: top - newSize.height
        )
    }

    private func resizeAnchored(to size: NSSize, makeResizable: Bool, animated: Bool = false, anchorTop: Bool = false) {
        // Cancel any pending resizeToFixedHeight work item to prevent stale resizes
        resizeWorkItem?.cancel()
        resizeWorkItem = nil

        let constrainedSize = NSSize(
            width: max(size.width, FloatingControlBarWindow.minBarSize.width),
            height: max(size.height, FloatingControlBarWindow.minBarSize.height)
        )
        let newOrigin = anchorTop
            ? originForTopCenterAnchor(newSize: constrainedSize)
            : originForCenterAnchor(newSize: constrainedSize)

        log("FloatingControlBar: resizeAnchored to \(constrainedSize) resizable=\(makeResizable) animated=\(animated) from=\(frame.size)")

        if makeResizable {
            styleMask.insert(.resizable)
        } else {
            styleMask.remove(.resizable)
        }

        isResizingProgrammatically = true

        // On macOS 26+ (Tahoe), animated setFrame triggers NSHostingView.updateAnimatedWindowSize
        // which invalidates safe area insets -> view graph -> requestUpdate -> setNeedsUpdateConstraints,
        // causing an infinite constraint update loop (OMI-COMPUTER-1J). Disable implicit animations
        // during the resize to prevent the updateAnimatedWindowSize code path.
        NSAnimationContext.beginGrouping()
        NSAnimationContext.current.duration = animated ? 0.3 : 0
        NSAnimationContext.current.allowsImplicitAnimation = false
        NSAnimationContext.current.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        self.setFrame(NSRect(origin: newOrigin, size: constrainedSize), display: true, animate: animated)
        NSAnimationContext.endGrouping()

        self.isResizingProgrammatically = false
    }

    private func resizeToFixedHeight(_ height: CGFloat, animated: Bool = false) {
        resizeWorkItem?.cancel()
        let width = FloatingControlBarWindow.expandedWidth
        let size = NSSize(width: width, height: height)
        resizeWorkItem = DispatchWorkItem { [weak self] in
            self?.resizeAnchored(to: size, makeResizable: false, animated: animated, anchorTop: true)
        }
        if let workItem = resizeWorkItem {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05, execute: workItem)
        }
    }

    /// Resize for hover expand/collapse — anchored from center so the circle grows outward.
    func resizeForHover(expanded: Bool) {
        guard !state.showingAIConversation, !state.isVoiceListening, !state.isShowingNotification, !suppressHoverResize else { return }
        resizeWorkItem?.cancel()
        resizeWorkItem = nil

        let targetSize = expanded ? FloatingControlBarWindow.expandedBarSize : FloatingControlBarWindow.minBarSize

        let doResize: () -> Void = { [weak self] in
            guard let self = self else { return }
            guard !self.state.showingAIConversation,
                  !self.state.isVoiceListening,
                  !self.state.isShowingNotification,
                  !self.suppressHoverResize
            else { return }
            let newOrigin = NSPoint(
                x: self.frame.midX - targetSize.width / 2,
                y: self.frame.midY - targetSize.height / 2
            )
            self.styleMask.remove(.resizable)
            self.isResizingProgrammatically = true
            self.setFrame(NSRect(origin: newOrigin, size: targetSize), display: true, animate: false)
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
    }

    /// Resize window for PTT state (expanded when listening, compact circle when idle)
    func resizeForPTTState(expanded: Bool) {
        let size = expanded
            ? NSSize(width: FloatingControlBarWindow.expandedWidth, height: FloatingControlBarWindow.expandedBarSize.height)
            : FloatingControlBarWindow.minBarSize
        resizeAnchored(to: size, makeResizable: false, animated: true)
    }

    func showNotification(_ notification: FloatingBarNotification, animated: Bool = true) {
        guard !state.showingAIConversation else { return }
        state.currentNotification = notification
        let barHeight = state.isHoveringBar ? Self.expandedBarSize.height : Self.minBarSize.height
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
        if state.isVoiceListening {
            targetSize = NSSize(width: Self.expandedWidth, height: Self.expandedBarSize.height)
        } else {
            targetSize = state.isHoveringBar ? Self.expandedBarSize : Self.minBarSize
        }
        resizeAnchored(to: targetSize, makeResizable: false, animated: animated, anchorTop: true)
    }

    /// Restore the compact pill size when we temporarily surface the bar outside
    /// of an active hover, notification, voice session, or AI conversation.
    func normalizeForTemporaryShow() {
        guard !state.showingAIConversation, !state.isVoiceListening, state.currentNotification == nil else { return }
        resizeAnchored(to: Self.minBarSize, makeResizable: false, animated: false, anchorTop: true)
    }

    private func resizeToResponseHeight(animated: Bool = false) {
        // Determine the 2× cap from the user's saved (or default) preferred height.
        let savedSize = UserDefaults.standard.string(forKey: FloatingControlBarWindow.sizeKey)
            .map(NSSizeFromString)
        let baseHeight = savedSize.map { max($0.height, Self.defaultBaseResponseHeight) } ?? Self.defaultBaseResponseHeight
        let maxHeight = baseHeight * 2

        // Start at the larger of minResponseHeight or current frame height so we never
        // shrink the window (e.g. during follow-up exchanges where it's already expanded).
        let startHeight = max(Self.minResponseHeight, frame.height)
        let initialSize = NSSize(width: Self.expandedWidth, height: startHeight)
        resizeAnchored(to: initialSize, makeResizable: true, animated: animated, anchorTop: true)
        setupResponseHeightObserver(maxHeight: maxHeight)
    }

    /// Observes `state.responseContentHeight` and expands the window to fit content,
    /// capped at `maxHeight`. Never shrinks automatically.
    private func setupResponseHeightObserver(maxHeight: CGFloat) {
        responseHeightCancellable?.cancel()
        responseHeightCancellable = state.$responseContentHeight
            .removeDuplicates()
            .debounce(for: .milliseconds(80), scheduler: DispatchQueue.main)
            .sink { [weak self] contentHeight in
                guard let self = self,
                      self.state.showingAIResponse,
                      !self.isUserResizing,
                      contentHeight > 0
                else { return }
                let targetHeight = (contentHeight + Self.responseViewOverhead).rounded()
                let clampedHeight = min(max(targetHeight, Self.minResponseHeight), maxHeight)
                // Only expand, never auto-shrink.
                guard clampedHeight > self.frame.height + 2 else { return }
                self.resizeAnchored(
                    to: NSSize(width: Self.expandedWidth, height: clampedHeight),
                    makeResizable: true,
                    animated: true,
                    anchorTop: true
                )
            }
    }

    /// Compute the default origin for the collapsed pill (top-center of the key screen).
    /// Used by closeAIConversation in non-draggable mode and centerOnMainScreen.
    private func defaultPillOrigin() -> NSPoint {
        let size = FloatingControlBarWindow.minBarSize
        let targetScreen = NSApp.keyWindow?.screen ?? NSScreen.main ?? NSScreen.screens.first
        guard let screen = targetScreen else { return .zero }
        let visibleFrame = screen.visibleFrame
        let x = visibleFrame.midX - size.width / 2
        let y = visibleFrame.maxY - size.height - 20
        return NSPoint(x: x, y: y)
    }

    /// Center the bar near the top of the main screen.
    private func centerOnMainScreen() {
        // Use the screen that has the key window, or fall back to main screen
        let targetScreen = NSApp.keyWindow?.screen ?? NSScreen.main ?? NSScreen.screens.first
        guard let screen = targetScreen else {
            self.center()
            return
        }
        let visibleFrame = screen.visibleFrame
        let x = visibleFrame.midX - frame.width / 2
        let y = visibleFrame.maxY - frame.height - 20  // 20pt from top
        self.setFrameOrigin(NSPoint(x: x, y: y))
        log("FloatingControlBarWindow: centered at (\(x), \(y)) on screen \(visibleFrame)")
    }

    func resetPosition() {
        UserDefaults.standard.removeObject(forKey: FloatingControlBarWindow.positionKey)
        centerOnMainScreen()
    }

    /// Called when monitors are connected/disconnected. Re-center if the bar is no longer
    /// fully visible on any screen.
    private func validatePositionOnScreenChange() {
        // Non-draggable mode: always restore to default position on screen change
        if !ShortcutSettings.shared.draggableBarEnabled {
            log("FloatingControlBarWindow: non-draggable mode, re-centering after monitor change")
            centerOnMainScreen()
            return
        }

        let barFrame = self.frame
        // Check if the bar's center point is on any visible screen
        let center = NSPoint(x: barFrame.midX, y: barFrame.midY)
        let onScreen = NSScreen.screens.contains { $0.visibleFrame.contains(center) }
        if !onScreen {
            log("FloatingControlBarWindow: bar center \(center) is off-screen after monitor change, re-centering")
            UserDefaults.standard.removeObject(forKey: FloatingControlBarWindow.positionKey)
            centerOnMainScreen()
        }
    }

    // MARK: - NSWindowDelegate

    func windowDidResignKey(_ notification: Notification) {
        guard state.showingAIConversation else { return }

        // Only dismiss when the user physically clicks away.
        // Programmatic focus changes — e.g. the AI agent activating a browser
        // window for automation — do NOT produce a mouse-down event, so we
        // leave the conversation open in those cases.
        let eventType = NSApp.currentEvent?.type
        let isMouseClick = eventType == .leftMouseDown
            || eventType == .rightMouseDown
            || eventType == .otherMouseDown
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
            minimumWidth = FloatingControlBarWindow.expandedWidth
        } else if state.currentNotification != nil {
            minimumWidth = FloatingControlBarWindow.notificationWidth
        } else if state.isVoiceListening {
            minimumWidth = FloatingControlBarWindow.expandedWidth
        } else if state.isHoveringBar {
            minimumWidth = FloatingControlBarWindow.expandedBarSize.width
        } else {
            minimumWidth = FloatingControlBarWindow.minBarSize.width
        }

        return NSSize(
            width: max(frameSize.width, minimumWidth),
            height: max(frameSize.height, FloatingControlBarWindow.minBarSize.height)
        )
    }

    func windowDidResize(_ notification: Notification) {
        if !isResizingProgrammatically && !isUserResizing && state.showingAIResponse {
            UserDefaults.standard.set(
                NSStringFromSize(self.frame.size), forKey: FloatingControlBarWindow.sizeKey
            )
        }
    }
}

// MARK: - FloatingControlBarManager

/// Singleton manager that owns the floating bar window and coordinates with AppState / ChatProvider.
@MainActor
class FloatingControlBarManager {
    static let shared = FloatingControlBarManager()

    private static let kAskOmiEnabled = "askOmiBarEnabled"
    private static let kSnoozedUntil = "floatingBar_snoozedUntil"
    private static let recentNotificationReuseInterval: TimeInterval = 60
    static let snoozeTwoHoursDuration: TimeInterval = 2 * 60 * 60

    private struct PendingFollowUpQuery {
        let text: String
        let fromVoice: Bool
    }

    private struct StoredNotificationMessage {
        let notification: FloatingBarNotification
        let context: FloatingBarNotificationContext?
        let createdAt: Date
    }

    private struct PendingNotificationContext {
        let message: ChatMessage
        let context: FloatingBarNotificationContext?
    }

    private var window: FloatingControlBarWindow?
    private var snoozeTimer: Timer?
    private var recordingCancellable: AnyCancellable?
    private var durationCancellable: AnyCancellable?
    private var chatCancellable: AnyCancellable?
    private var historyChatProvider: ChatProvider?
    private var floatingChatProvider: ChatProvider?
    private var pendingNotifications: [FloatingBarNotification] = []
    private var notificationDismissWorkItem: DispatchWorkItem?
    private var notificationWasTemporarilyShown = false
    private var storedNotificationMessages: [UUID: StoredNotificationMessage] = [:]
    private var mostRecentNotificationID: UUID?
    private var pendingNotificationContext: PendingNotificationContext?
    private var floatingSessionKey = "floating"
    private var activeQueryGeneration: Int = 0
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

    private init() {}

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

        // Keep the shared provider for syncing persisted messages into the main
        // chat history, but use an isolated provider for floating-bar sends.
        historyChatProvider = chatProvider
        let floatingProvider = floatingChatProvider ?? ChatProvider()
        floatingProvider.modelOverride = chatProvider.modelOverride
        floatingProvider.workingDirectory = chatProvider.workingDirectory
        floatingChatProvider = floatingProvider

        barWindow.onSendQuery = { [weak self, weak barWindow, weak floatingProvider] message in
            guard let self = self, let barWindow = barWindow, let provider = floatingProvider else { return }
            Task { @MainActor in
                await self.sendAIQuery(message, barWindow: barWindow, provider: provider)
            }
        }

        barWindow.onRate = { [weak floatingProvider] messageId, rating in
            guard let provider = floatingProvider else { return }
            Task { @MainActor in
                await provider.rateMessage(messageId, rating: rating)
            }
        }

        barWindow.onShareLink = { [weak barWindow] in
            guard let barWindow = barWindow else { return nil }
            // Share the visible floating-bar exchange history in chat order.
            var messageIds: [String] = []
            for exchange in barWindow.state.chatHistory {
                if let questionMessageId = exchange.questionMessageId {
                    messageIds.append(questionMessageId)
                }
                if exchange.aiMessage.isSynced {
                    messageIds.append(exchange.aiMessage.id)
                }
            }
            if let currentQuestionMessageId = barWindow.state.currentQuestionMessageId {
                messageIds.append(currentQuestionMessageId)
            }
            if let current = barWindow.state.currentAIMessage, current.isSynced {
                messageIds.append(current.id)
            }
            let orderedUniqueMessageIds = messageIds.reduce(into: [String]()) { ids, messageId in
                if !ids.contains(messageId) {
                    ids.append(messageId)
                }
            }
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

    /// Show the floating bar and persist the preference.
    func show() {
        log("FloatingControlBarManager: show() called, window=\(window != nil), isVisible=\(window?.isVisible ?? false)")
        isEnabled = true
        if isSnoozed {
            log("FloatingControlBarManager: show() suppressed because bar is snoozed until \(snoozedUntil?.description ?? "?")")
            return
        }
        window?.makeKeyAndOrderFront(nil)
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
        window?.orderOut(nil)
    }

    /// Show the floating bar temporarily without changing the user's persisted preference.
    /// Used when browser tools activate so the bar stays visible above Chrome.
    func showTemporarily() {
        guard window != nil else { return }
        if isSnoozed {
            log("FloatingControlBarManager: showTemporarily() suppressed because bar is snoozed")
            return
        }
        log("FloatingControlBarManager: showTemporarily() — showing bar above Chrome")
        window?.normalizeForTemporaryShow()
        window?.makeKeyAndOrderFront(nil)
    }

    func showNotification(
        title: String,
        message: String,
        assistantId: String,
        sound: NotificationSound,
        context: FloatingBarNotificationContext? = nil,
        screenshotData: Data? = nil
    ) {
        let notification = FloatingBarNotification(
            title: title,
            message: message,
            assistantId: assistantId,
            context: context,
            screenshotData: screenshotData
        )
        guard let window else {
            log("FloatingControlBarManager: dropping notification because window is not set up")
            return
        }

        if isSnoozed {
            log("FloatingControlBarManager: dropping notification because bar is snoozed until \(snoozedUntil?.description ?? "?")")
            return
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
            return
        }

        presentNotification(notification, in: window)
    }

    func dismissCurrentNotification() {
        notificationDismissWorkItem?.cancel()
        notificationDismissWorkItem = nil
        dismissNotificationAndAdvanceQueue(trackDismissal: true)
    }

    func flushQueuedNotificationsIfPossible() {
        guard let window, window.state.currentNotification == nil, !window.state.showingAIConversation,
              !pendingNotifications.isEmpty else { return }
        let nextNotification = pendingNotifications.removeFirst()
        presentNotification(nextNotification, in: window)
    }

    /// Cancel any in-flight chat streaming.
    func cancelChat() {
        activeQueryGeneration += 1
        pendingFollowUpQuery = nil
        chatCancellable?.cancel()
        chatCancellable = nil
        activeFloatingProvider()?.stopAgent()
        FloatingBarVoicePlaybackService.shared.stop()
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
    func openAIInputWithQuery(_ query: String, fromVoice: Bool = false) {
        guard let window = window else { return }

        // Cancel stale subscriptions immediately to prevent old data from flashing
        chatCancellable?.cancel()
        chatCancellable = nil
        window.cancelInputHeightObserver()

        // Reset visible state directly (no animation) to avoid contract-then-expand flicker.
        // Provider session context remains intact; only the floating-bar UI is reset.
        window.state.showingAIConversation = false
        window.state.clearVisibleConversation()
        window.state.currentQueryFromVoice = fromVoice
        pendingNotificationContext = nil
        floatingSessionKey = "floating"

        guard let provider = activeFloatingProvider() else { return }

        // Re-wire the onSendQuery to use the isolated floating-bar provider
        window.onSendQuery = { [weak self, weak window, weak provider] message in
            guard let self = self, let window = window, let provider = provider else { return }
            Task { @MainActor in
                await self.sendAIQuery(message, barWindow: window, provider: provider)
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

        // Auto-send the query
        Task { @MainActor in
            await self.sendAIQuery(query, barWindow: window, provider: provider)
        }
    }

    /// Send a follow-up query in the existing AI conversation (used by PTT follow-up).
    func sendFollowUpQuery(_ query: String, fromVoice: Bool = false) {
        guard let window = window, window.state.showingAIResponse else {
            // No active conversation — fall back to new conversation
            openAIInputWithQuery(query, fromVoice: fromVoice)
            return
        }
        guard let provider = activeFloatingProvider() else { return }

        // Archive current exchange
        if let currentMessage = window.state.currentAIMessage,
           !currentMessage.text.isEmpty || !currentMessage.contentBlocks.isEmpty {
            let currentQuery = window.state.displayedQuery.trimmingCharacters(in: .whitespacesAndNewlines)
            window.state.chatHistory.append(
                FloatingChatExchange(
                    question: currentQuery.isEmpty ? nil : currentQuery,
                    questionMessageId: window.state.currentQuestionMessageId,
                    aiMessage: currentMessage
                )
            )
        }

        if provider.isSending {
            pendingFollowUpQuery = PendingFollowUpQuery(text: query, fromVoice: fromVoice)
            prepareVisibleQueryState(query, in: window, fromVoice: fromVoice)
            provider.stopAgent()
            return
        }

        window.state.currentQueryFromVoice = fromVoice
        Task { @MainActor in
            await self.sendAIQuery(query, barWindow: window, provider: provider)
        }
    }

    func openNotificationAsChat(_ notification: FloatingBarNotification) {
        guard let window else { return }

        AnalyticsManager.shared.notificationClicked(
            notificationId: notification.id.uuidString,
            title: notification.title,
            assistantId: notification.assistantId,
            surface: "floating_bar"
        )

        notificationDismissWorkItem?.cancel()
        notificationDismissWorkItem = nil
        dismissNotificationAndAdvanceQueue(trackDismissal: false)
        _ = openNotificationConversation(notificationID: notification.id, in: window)
    }

    private func presentNotification(_ notification: FloatingBarNotification, in window: FloatingControlBarWindow) {
        persistNotificationMessageIfNeeded(notification)

        if !window.isVisible {
            notificationWasTemporarilyShown = true
            window.orderFrontRegardless()
        } else {
            notificationWasTemporarilyShown = false
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

        if !pendingNotifications.isEmpty, !window.state.showingAIConversation {
            let nextNotification = pendingNotifications.removeFirst()
            presentNotification(nextNotification, in: window)
            return
        }

        if notificationWasTemporarilyShown && !isEnabled && !window.state.showingAIConversation {
            window.orderOut(nil)
        }
        notificationWasTemporarilyShown = false
    }

    private func persistNotificationMessageIfNeeded(_ notification: FloatingBarNotification) {
        guard storedNotificationMessages[notification.id] == nil else { return }

        // Also append the notification as an assistant message in the main chat
        // history provider so it is visible on the home-page chat and synced to
        // the backend. The floating bar still uses its own provider for follow-up
        // questions (see openNotificationConversation), so this append does not
        // affect the floating-bar session in any way.
        if let historyProvider = historyChatProvider {
            let bodyText = notification.message.trimmingCharacters(in: .whitespacesAndNewlines)
            let messageText = bodyText.isEmpty ? notification.title : bodyText
            _ = historyProvider.appendAssistantMessage(messageText)
        }

        storedNotificationMessages[notification.id] = StoredNotificationMessage(
            notification: notification,
            context: notification.context,
            createdAt: Date()
        )
        mostRecentNotificationID = notification.id
    }

    private func openRecentNotificationConversationIfAvailable(in window: FloatingControlBarWindow) -> Bool {
        guard let mostRecentNotificationID else { return false }
        return openNotificationConversation(notificationID: mostRecentNotificationID, in: window)
    }

    @discardableResult
    private func openNotificationConversation(notificationID: UUID, in window: FloatingControlBarWindow) -> Bool {
        purgeExpiredNotificationMessages()

        guard let stored = storedNotificationMessages[notificationID],
              Date().timeIntervalSince(stored.createdAt) <= Self.recentNotificationReuseInterval else {
            return false
        }
        guard let provider = activeFloatingProvider() else { return false }

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

        let bodyText = stored.notification.message.trimmingCharacters(in: .whitespacesAndNewlines)
        let messageText = bodyText.isEmpty ? stored.notification.title : bodyText
        let notificationMessage = provider.appendAssistantMessage(messageText) ?? ChatMessage(text: messageText, sender: .ai)

        window.state.showingAIConversation = true
        window.state.showingAIResponse = true
        window.state.isAILoading = false
        window.state.aiInputText = ""
        if !shouldRestoreVisibleConversation {
            window.state.chatHistory = []
            window.state.displayedQuery = ""
            window.state.currentQuestionMessageId = nil
        }
        window.state.currentAIMessage = notificationMessage
        window.state.markConversationActivity()
        window.resizeToResponseHeightPublic(animated: true)
        window.orderFrontRegardless()
        window.focusInputField()

        pendingNotificationContext = PendingNotificationContext(
            message: notificationMessage,
            context: stored.context
        )
        floatingSessionKey = "floating"
        Task {
            await provider.invalidateAgentSession(sessionKey: "floating")
        }
        storedNotificationMessages.removeValue(forKey: notificationID)
        if mostRecentNotificationID == notificationID {
            mostRecentNotificationID = nil
        }
        return true
    }

    private func archiveVisibleConversationIfNeeded(in window: FloatingControlBarWindow) {
        guard let currentMessage = window.state.currentAIMessage else { return }
        guard !currentMessage.text.isEmpty || !currentMessage.contentBlocks.isEmpty else { return }

        let currentQuery = window.state.displayedQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        window.state.chatHistory.append(
            FloatingChatExchange(
                question: currentQuery.isEmpty ? nil : currentQuery,
                questionMessageId: window.state.currentQuestionMessageId,
                aiMessage: currentMessage
            )
        )
        window.state.displayedQuery = ""
        window.state.currentQuestionMessageId = nil
    }

    private func purgeExpiredNotificationMessages() {
        let now = Date()
        storedNotificationMessages = storedNotificationMessages.filter { _, stored in
            now.timeIntervalSince(stored.createdAt) <= Self.recentNotificationReuseInterval
        }

        if let mostRecentNotificationID, storedNotificationMessages[mostRecentNotificationID] == nil {
            self.mostRecentNotificationID = nil
        }
    }

    private func activeFloatingProvider() -> ChatProvider? {
        guard let floatingProvider = floatingChatProvider else { return nil }
        if let sharedProvider = historyChatProvider {
            floatingProvider.modelOverride = sharedProvider.modelOverride
            floatingProvider.workingDirectory = sharedProvider.workingDirectory
        }
        return floatingProvider
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
        barWindow.cancelInputHeightObserver()
        barWindow.state.currentQueryFromVoice = fromVoice
        barWindow.state.showingAIConversation = true
        barWindow.state.showingAIResponse = true
        barWindow.state.isAILoading = true
        barWindow.state.aiInputText = message
        barWindow.state.displayedQuery = message
        barWindow.state.markConversationActivity()
        barWindow.state.currentQuestionMessageId = nil
        barWindow.state.currentAIMessage = nil
        barWindow.state.isVoiceFollowUp = false
        barWindow.state.voiceFollowUpTranscript = ""
        barWindow.state.responseContentHeight = 0
        barWindow.resizeToResponseHeightPublic(animated: true)
    }

    private func isActiveQueryGeneration(_ generation: Int) -> Bool {
        generation == activeQueryGeneration
    }

    private func sendAIQuery(_ message: String, barWindow: FloatingControlBarWindow, provider: ChatProvider) async {
        let queryFromVoice = barWindow.state.currentQueryFromVoice
        prepareVisibleQueryState(message, in: barWindow, fromVoice: queryFromVoice)
        let generation = activeQueryGeneration

        // Check monthly usage limit for free users (shared with main chat page).
        let limiter = FloatingBarUsageLimiter.shared
        if limiter.isLimitReached {
            guard isActiveQueryGeneration(generation) else { return }
            barWindow.state.isAILoading = false
            barWindow.state.showingAIResponse = true
            barWindow.state.currentAIMessage = ChatMessage(
                text: "You've reached \(limiter.limitDescription). Upgrade to keep chatting without restrictions.",
                sender: .ai
            )
            barWindow.resizeToResponseHeightPublic(animated: true)
            NotificationCenter.default.post(
                name: .showUsageLimitPopup,
                object: nil,
                userInfo: ["reason": "floating_bar"]
            )
            return
        }

        limiter.recordQuery()
        FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()

        let screenshotData = await Task.detached { () -> Data? in
            return ScreenCaptureManager.captureScreenData()
        }.value
        barWindow.orderFrontRegardless()

        AnalyticsManager.shared.floatingBarQuerySent(messageLength: message.count, hasScreenshot: screenshotData != nil)

        let shouldPlayVoice = ShortcutSettings.shared.shouldSpeakFloatingBarResponse(
            forVoiceQuery: barWindow.state.currentQueryFromVoice
        )
        if shouldPlayVoice {
            FloatingBarVoicePlaybackService.shared.playFillerIfEnabled()
        }

        // Provider is already initialized by ViewModelContainer at app launch

        // Record message count before sending so we can detect the new AI response
        // in a shared provider that may already have many messages
        let messageCountBefore = provider.messages.count

        // Observe messages for streaming response
        chatCancellable?.cancel()
        barWindow.state.currentAIMessage = nil
        barWindow.state.currentQuestionMessageId = nil
        barWindow.state.isAILoading = true
        var hasSetUpResponseHeight = false
        chatCancellable = provider.$messages
            .receive(on: DispatchQueue.main)
            .sink { [weak self, weak barWindow] messages in
                guard let self, self.isActiveQueryGeneration(generation) else { return }
                // Find the AI response message added after our query
                guard messages.count > messageCountBefore,
                      let aiMessage = messages.last,
                      aiMessage.sender == .ai else { return }

                // Store the full ChatMessage (preserves contentBlocks, tool calls, thinking)
                barWindow?.state.currentAIMessage = aiMessage
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
                            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                                barWindow.state.showingAIResponse = true
                            }
                        }
                        barWindow.resizeToResponseHeightPublic(animated: true)
                    }
                } else {
                    barWindow?.state.isAILoading = false
                }
            }

        let floatingModel = ShortcutSettings.shared.selectedModel.isEmpty
            ? ModelQoS.Claude.defaultSelection
            : ShortcutSettings.shared.selectedModel
        let notificationContextSuffix = notificationContextSuffixIfNeeded(for: message)
        await provider.sendMessage(
            message,
            model: floatingModel,
            systemPromptSuffix: notificationContextSuffix,
            systemPromptPrefix: ChatProvider.floatingBarSystemPromptPrefix,
            sessionKey: floatingSessionKey,
            imageData: screenshotData
        )

        if let followUp = pendingFollowUpQuery {
            pendingFollowUpQuery = nil
            barWindow.state.currentQueryFromVoice = followUp.fromVoice
            await sendAIQuery(followUp.text, barWindow: barWindow, provider: provider)
            return
        }

        guard isActiveQueryGeneration(generation) else { return }
        let newMessages = Array(provider.messages.dropFirst(messageCountBefore))
        if let syncedUserMessage = newMessages.last(where: { $0.sender == .user && $0.text == message && $0.isSynced }) {
            barWindow.state.currentQuestionMessageId = syncedUserMessage.id
        }
        if let finalAIMessage = newMessages.last(where: { $0.sender == .ai }) {
            barWindow.state.currentAIMessage = finalAIMessage
        }
        // Cancel the messages subscription now that streaming is done.
        // Leaving it alive lets later sidebar mutations overwrite the floating bar display.
        chatCancellable?.cancel()
        chatCancellable = nil

        // Handle errors after sendMessage completes
        barWindow.state.isAILoading = false

        if let errorText = provider.errorMessage {
            // Provider reported an error (timeout, bridge crash, etc.)
            // Show it even if there's partial content — append to existing or create new message
            if barWindow.state.currentAIMessage != nil && !barWindow.state.aiResponseText.isEmpty {
                barWindow.state.currentAIMessage?.text += "\n\n⚠️ \(errorText)"
            } else {
                barWindow.state.currentAIMessage = ChatMessage(text: "⚠️ \(errorText)", sender: .ai)
            }
        } else if barWindow.state.currentAIMessage == nil || barWindow.state.aiResponseText.isEmpty {
            // No error message and no response — something else went wrong
            barWindow.state.currentAIMessage = ChatMessage(text: "Failed to get a response. Please try again.", sender: .ai)
        }

        // Ensure the response view is visible and resized (handles the case where
        // the sink never fired because no streaming data arrived before the error)
        if !barWindow.state.showingAIResponse {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                barWindow.state.showingAIResponse = true
            }
            barWindow.resizeToResponseHeightPublic(animated: true)
        }

        if shouldPlayVoice {
            FloatingBarVoicePlaybackService.shared.updateStreamingResponseIfEnabled(
                barWindow.state.currentAIMessage,
                isFinal: true
            )
        }
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
        floatingSessionKey = "floating"
    }
}

// Expose resizeToResponseHeight for the manager
extension FloatingControlBarWindow {
    func resizeToResponseHeightPublic(animated: Bool = false) {
        resizeToResponseHeight(animated: animated)
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
        let size = FloatingControlBarWindow.minBarSize
        if !ShortcutSettings.shared.draggableBarEnabled {
            // Non-draggable: always snap to the default pill position before saving.
            // This ensures preChatCenter is always the canonical default, not a
            // mid-animation frame or drifted position from a previous session.
            let origin = defaultPillOrigin()
            isResizingProgrammatically = true
            setFrame(NSRect(origin: origin, size: size), display: true, animate: false)
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
        preChatCenter = NSPoint(x: frame.midX, y: frame.midY)
    }

    /// Invalidates any in-flight windowDidResignKey dismiss animation so a new PTT
    /// query won't be immediately closed by a stale completion block.
    func cancelPendingDismiss() {
        resignKeyAnimationToken += 1
    }
}
