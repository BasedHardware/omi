import Cocoa
import Combine
import SwiftUI

/// NSWindow subclass for the floating control bar.
class FloatingControlBarWindow: NSWindow, NSWindowDelegate {
    private static let positionKey = "FloatingControlBarPosition"
    private static let sizeKey = "FloatingControlBarSize"
    private static let defaultSize = NSSize(width: 40, height: 10)
    private static let minBarSize = NSSize(width: 40, height: 10)
    static let expandedBarSize = NSSize(width: 210, height: 50)
    private static let maxBarSize = NSSize(width: 1200, height: 1000)
    private static let expandedWidth: CGFloat = 430

    let state = FloatingControlBarState()
    private var hostingView: NSHostingView<AnyView>?
    private var isResizingProgrammatically = false
    private var isUserDragging = false
    /// Suppresses hover resizes during close animation to prevent position drift.
    private var suppressHoverResize = false
    private var inputHeightCancellable: AnyCancellable?
    private var resizeWorkItem: DispatchWorkItem?
    /// Saved center point from before chat opened, used to restore position on close.
    private var preChatCenter: NSPoint?

    var onPlayPause: (() -> Void)?
    var onAskAI: (() -> Void)?
    var onHide: (() -> Void)?
    var onSendQuery: ((String, URL?) -> Void)?

    override init(
        contentRect: NSRect, styleMask style: NSWindow.StyleMask,
        backing backingStoreType: NSWindow.BackingStoreType = .buffered, defer flag: Bool = false
    ) {
        let initialRect = NSRect(origin: .zero, size: FloatingControlBarWindow.minBarSize)

        super.init(
            contentRect: initialRect,
            styleMask: [.borderless],
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
    override var canBecomeMain: Bool { true }

    override func keyDown(with event: NSEvent) {
        // Esc closes the AI conversation only — never hides the entire bar
        if event.keyCode == 53 { // Escape
            if state.showingAIConversation {
                closeAIConversation()
            }
            return
        }
        super.keyDown(with: event)
    }

    private func setupViews() {
        let swiftUIView = FloatingControlBarView(
            window: self,
            onPlayPause: { [weak self] in self?.onPlayPause?() },
            onAskAI: { [weak self] in self?.handleAskAI() },
            onHide: { [weak self] in self?.hideBar() },
            onSendQuery: { [weak self] message, screenshotURL in self?.onSendQuery?(message, screenshotURL) },
            onCloseAI: { [weak self] in self?.closeAIConversation() }
        ).environmentObject(state)

        hostingView = NSHostingView(rootView: AnyView(
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

    func captureScreenshot(thenFocusInput: Bool = false) {
        // Temporarily hide the bar to avoid capturing it in the screenshot
        let wasVisible = isVisible
        if wasVisible { orderOut(nil) }

        // Small delay to let the window disappear before capture
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
            // Capture screenshot off main thread — PNG encoding + file write can block
            Task.detached {
                let url = ScreenCaptureManager.captureScreen()
                await MainActor.run {
                    self?.state.screenshotURL = url
                }
            }

            if wasVisible {
                self?.orderFront(nil)
                self?.makeKeyAndOrderFront(nil)
            }

            if thenFocusInput {
                // Focus after a short delay to let SwiftUI create the text view
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                    self?.focusInputField()
                }
            }
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

        // Cancel PTT if in follow-up mode
        if state.isVoiceFollowUp {
            PushToTalkManager.shared.cancelListening()
        }

        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            state.showingAIConversation = false
            state.showingAIResponse = false
            state.aiInputText = ""
            state.currentAIMessage = nil
            state.screenshotURL = nil
            state.chatHistory = []
            state.isVoiceFollowUp = false
            state.voiceFollowUpTranscript = ""
        }
        // Suppress hover resizes while the close animation plays, otherwise onHover
        // fires mid-animation, reads an intermediate frame, and causes position drift.
        suppressHoverResize = true

        // Restore to saved center so hover expand/collapse stays consistent (no drift).
        if let center = preChatCenter {
            let size = FloatingControlBarWindow.minBarSize
            let restoreOrigin = NSPoint(x: center.x - size.width / 2, y: center.y - size.height / 2)
            resizeWorkItem?.cancel()
            resizeWorkItem = nil
            styleMask.remove(.resizable)
            isResizingProgrammatically = true
            NSAnimationContext.beginGrouping()
            NSAnimationContext.current.duration = 0.3
            NSAnimationContext.current.allowsImplicitAnimation = false
            NSAnimationContext.current.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            self.setFrame(NSRect(origin: restoreOrigin, size: size), display: true, animate: true)
            NSAnimationContext.endGrouping()
            // Keep isResizingProgrammatically true until animation finishes to prevent
            // intermediate frames from triggering unwanted side effects.
            let targetFrame = NSRect(origin: restoreOrigin, size: size)
            preChatCenter = nil
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
                self?.isResizingProgrammatically = false
                // Safety net: if the frame drifted during animation, snap to the correct position.
                if let self = self, self.frame != targetFrame {
                    self.setFrame(targetFrame, display: true, animate: false)
                }
            }
        } else {
            resizeAnchored(to: FloatingControlBarWindow.minBarSize, makeResizable: false, animated: true)
        }

        // Allow hover resizes again after the animation settles.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in
            self?.suppressHoverResize = false
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
        // Resize window BEFORE changing state so SwiftUI content doesn't render
        // in the old 28x28 frame (which causes a visible jump).
        // Save center so we can restore exact position when chat closes (avoids drift).
        preChatCenter = NSPoint(x: frame.midX, y: frame.midY)

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

        // Capture screenshot in background without hiding the bar
        Task.detached { [weak self] in
            let url = ScreenCaptureManager.captureScreen()
            let capturedSelf = self
            await MainActor.run {
                capturedSelf?.state.screenshotURL = url
            }
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
        guard !state.showingAIConversation, !state.isVoiceListening, !suppressHoverResize else { return }
        resizeWorkItem?.cancel()
        resizeWorkItem = nil

        let targetSize = expanded ? FloatingControlBarWindow.expandedBarSize : FloatingControlBarWindow.minBarSize

        let doResize: () -> Void = { [weak self] in
            guard let self = self else { return }
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

    private func resizeToResponseHeight(animated: Bool = false) {
        let savedSize = UserDefaults.standard.string(forKey: FloatingControlBarWindow.sizeKey)
            .map(NSSizeFromString)

        let targetSize = savedSize.map {
            NSSize(
                width: max($0.width, FloatingControlBarWindow.minBarSize.width),
                height: max($0.height, 430)
            )
        } ?? NSSize(width: 430, height: 430)

        resizeAnchored(to: targetSize, makeResizable: true, animated: animated, anchorTop: true)
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
        NSSize(
            width: max(frameSize.width, FloatingControlBarWindow.minBarSize.width),
            height: max(frameSize.height, FloatingControlBarWindow.minBarSize.height)
        )
    }

    func windowDidResize(_ notification: Notification) {
        if !isResizingProgrammatically && state.showingAIResponse {
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

    private var window: FloatingControlBarWindow?
    private var recordingCancellable: AnyCancellable?
    private var durationCancellable: AnyCancellable?
    private var chatCancellable: AnyCancellable?
    private var chatProvider: ChatProvider?

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

        // Reuse the sidebar's ChatProvider (bridge is already warm from app startup)
        self.chatProvider = chatProvider

        barWindow.onSendQuery = { [weak self, weak barWindow, weak chatProvider] message, screenshotURL in
            guard let self = self, let barWindow = barWindow, let provider = chatProvider else { return }
            Task { @MainActor in
                await self.sendAIQuery(message, screenshotURL: screenshotURL, barWindow: barWindow, provider: provider)
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
    }

    /// Whether the floating bar window is currently visible.
    var isVisible: Bool {
        window?.isVisible ?? false
    }

    /// Show the floating bar and persist the preference.
    func show() {
        log("FloatingControlBarManager: show() called, window=\(window != nil), isVisible=\(window?.isVisible ?? false)")
        isEnabled = true
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

    /// Cancel any in-flight chat streaming.
    func cancelChat() {
        chatCancellable?.cancel()
        chatCancellable = nil
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

    /// Open the AI input panel.
    func openAIInput() {
        guard let window = window else { return }

        // Activate the app so the window can become key and accept keyboard input.
        // Without this, makeFirstResponder silently fails when triggered from a global shortcut.
        NSApp.activate(ignoringOtherApps: true)

        // If a conversation is already showing, just focus the follow-up input
        if window.state.showingAIConversation && window.state.showingAIResponse {
            if !window.isVisible { show() }
            window.makeKeyAndOrderFront(nil)
            window.focusInputField()
            return
        }

        AnalyticsManager.shared.floatingBarAskOmiOpened(source: "shortcut")
        if !window.isVisible {
            show()
        }
        window.showAIConversation()
        window.orderFrontRegardless()
    }

    /// Open AI input with a pre-filled query and auto-send (used by PTT).
    func openAIInputWithQuery(_ query: String, screenshot: URL?) {
        guard let window = window else { return }

        // Cancel stale subscriptions immediately to prevent old data from flashing
        chatCancellable?.cancel()
        chatCancellable = nil
        window.cancelInputHeightObserver()

        // Reset state directly (no animation) to avoid contract-then-expand flicker
        window.state.showingAIConversation = false
        window.state.showingAIResponse = false
        window.state.aiInputText = ""
        window.state.currentAIMessage = nil
        window.state.screenshotURL = nil
        window.state.chatHistory = []
        window.state.isVoiceFollowUp = false
        window.state.voiceFollowUpTranscript = ""

        guard let provider = self.chatProvider else { return }

        // Re-wire the onSendQuery to use the shared provider
        window.onSendQuery = { [weak self, weak window, weak provider] message, screenshotURL in
            guard let self = self, let window = window, let provider = provider else { return }
            Task { @MainActor in
                await self.sendAIQuery(message, screenshotURL: screenshotURL, barWindow: window, provider: provider)
            }
        }

        if !window.isVisible {
            show()
        }

        // Save pre-chat center so closeAIConversation can restore the original position.
        // Without this, Escape after a PTT query places the bar at the response window's
        // center instead of where it was before the chat opened.
        window.savePreChatCenterIfNeeded()

        // Set up state — go straight to response view (skip input view to avoid resize flicker)
        window.state.showingAIConversation = true
        window.state.showingAIResponse = true
        window.state.isAILoading = true
        window.state.aiInputText = query
        window.state.displayedQuery = query
        window.state.currentAIMessage = nil
        window.resizeToResponseHeightPublic(animated: true)
        window.orderFrontRegardless()

        // Auto-send the query
        Task { @MainActor in
            await self.sendAIQuery(query, screenshotURL: screenshot, barWindow: window, provider: provider)
        }
    }

    /// Send a follow-up query in the existing AI conversation (used by PTT follow-up).
    func sendFollowUpQuery(_ query: String) {
        guard let window = window, window.state.showingAIResponse else {
            // No active conversation — fall back to new conversation
            openAIInputWithQuery(query, screenshot: nil)
            return
        }

        // Archive current exchange
        let currentQuery = window.state.displayedQuery
        if let currentMessage = window.state.currentAIMessage, !currentQuery.isEmpty, !currentMessage.text.isEmpty {
            window.state.chatHistory.append(FloatingChatExchange(question: currentQuery, aiMessage: currentMessage))
        }

        // Cancel existing streaming response if still in progress
        chatCancellable?.cancel()
        chatCancellable = nil

        // Set up new query
        window.state.displayedQuery = query
        window.state.currentAIMessage = nil
        window.state.isAILoading = true

        let screenshot = window.state.screenshotURL
        window.onSendQuery?(query, screenshot)
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

    private func sendAIQuery(_ message: String, screenshotURL: URL?, barWindow: FloatingControlBarWindow, provider: ChatProvider) async {
        AnalyticsManager.shared.floatingBarQuerySent(messageLength: message.count, hasScreenshot: screenshotURL != nil)

        // Provider is already initialized by ViewModelContainer at app launch

        // Record message count before sending so we can detect the new AI response
        // in a shared provider that may already have many messages
        let messageCountBefore = provider.messages.count

        // Observe messages for streaming response
        chatCancellable?.cancel()
        barWindow.state.currentAIMessage = nil
        barWindow.state.isAILoading = true
        chatCancellable = provider.$messages
            .receive(on: DispatchQueue.main)
            .sink { [weak barWindow] messages in
                // Find the AI response message added after our query
                guard messages.count > messageCountBefore,
                      let aiMessage = messages.last,
                      aiMessage.sender == .ai else { return }

                // Store the full ChatMessage (preserves contentBlocks, tool calls, thinking)
                barWindow?.state.currentAIMessage = aiMessage

                if aiMessage.isStreaming {
                    barWindow?.state.isAILoading = false
                    if let barWindow = barWindow, !barWindow.state.showingAIResponse {
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                            barWindow.state.showingAIResponse = true
                        }
                        barWindow.resizeToResponseHeightPublic(animated: true)
                    }
                } else {
                    barWindow?.state.isAILoading = false
                }
            }

        // Build prompt with screenshot context if available
        var fullMessage = message
        if let url = screenshotURL {
            fullMessage = "[Screenshot of user's screen attached: \(url.path)]\n\n\(message)"
        }

        await provider.sendMessage(fullMessage, model: ShortcutSettings.shared.selectedModel)

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
    }
}

// Expose resizeToResponseHeight for the manager
extension FloatingControlBarWindow {
    func resizeToResponseHeightPublic(animated: Bool = false) {
        resizeToResponseHeight(animated: animated)
    }

    /// Save the current center point so closeAIConversation can restore position.
    /// Only saves if preChatCenter is not already set (avoids overwriting during follow-ups).
    func savePreChatCenterIfNeeded() {
        guard preChatCenter == nil else { return }
        preChatCenter = NSPoint(x: frame.midX, y: frame.midY)
    }
}
