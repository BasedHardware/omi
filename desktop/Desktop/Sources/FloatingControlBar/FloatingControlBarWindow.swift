import Cocoa
import Combine
import SwiftUI

/// NSWindow subclass for the floating control bar.
class FloatingControlBarWindow: NSWindow, NSWindowDelegate {
    private static let positionKey = "FloatingControlBarPosition"
    private static let sizeKey = "FloatingControlBarSize"
    private static let defaultSize = NSSize(width: 210, height: 50)
    private static let minBarSize = NSSize(width: 210, height: 50)
    private static let maxBarSize = NSSize(width: 1200, height: 1000)
    private static let expandedWidth: CGFloat = 430

    let state = FloatingControlBarState()
    private var hostingView: NSHostingView<AnyView>?
    private var isResizingProgrammatically = false
    private var inputHeightCancellable: AnyCancellable?
    private var resizeWorkItem: DispatchWorkItem?

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

        if let savedPosition = UserDefaults.standard.string(forKey: FloatingControlBarWindow.positionKey) {
            let origin = NSPointFromString(savedPosition)
            // Verify saved position is on a visible screen
            let onScreen = NSScreen.screens.contains { $0.visibleFrame.contains(NSPoint(x: origin.x + 100, y: origin.y + 30)) }
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
        // Esc closes the AI conversation, or hides the bar if collapsed
        if event.keyCode == 53 { // Escape
            if state.showingAIConversation {
                closeAIConversation()
            } else {
                hideBar()
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
            onCloseAI: { [weak self] in self?.closeAIConversation() },
            onCaptureScreenshot: { [weak self] in self?.captureScreenshot() }
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
                self?.state.isDragging = true
            }
        }

        NotificationCenter.default.addObserver(
            forName: .floatingBarDragDidEnd, object: nil, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.state.isDragging = false
            }
        }
    }

    // MARK: - AI Actions

    private func handleAskAI() {
        if state.showingAIConversation && !state.showingAIResponse {
            // Already showing input, close it
            closeAIConversation()
        } else if state.showingAIConversation {
            // Showing response, close it
            closeAIConversation()
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
            let url = ScreenCaptureManager.captureScreen()
            self?.state.screenshotURL = url

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

    /// Focus the text input field by finding the NSTextView in the view hierarchy
    func focusInputField() {
        guard let contentView = self.contentView else { return }
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
        }
    }

    func closeAIConversation() {
        AnalyticsManager.shared.floatingBarAskOmiClosed()
        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            state.showingAIConversation = false
            state.showingAIResponse = false
            state.aiInputText = ""
            state.aiResponseText = ""
            state.screenshotURL = nil
        }
        resizeToFixedHeight(FloatingControlBarWindow.minBarSize.height, animated: true)
    }

    private func hideBar() {
        self.orderOut(nil)
        onHide?()
    }

    // MARK: - Public State Updates

    func updateRecordingState(isRecording: Bool, duration: Int, isInitialising: Bool) {
        state.isRecording = isRecording
        state.duration = duration
        state.isInitialising = isInitialising
    }

    func showAIConversation() {
        // Show input and focus immediately — don't block on screenshot
        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            state.showingAIConversation = true
            state.showingAIResponse = false
            state.isAILoading = false
            state.aiInputText = ""
            state.aiResponseText = ""
            state.inputViewHeight = 100
        }
        resizeToFixedHeight(120, animated: true)
        setupInputHeightObserver()

        // Focus input ASAP (minimal delay for SwiftUI to create the text view)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) { [weak self] in
            self?.makeKeyAndOrderFront(nil)
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

    private func originForTopLeftAnchor(newSize: NSSize) -> NSPoint {
        NSPoint(
            x: frame.origin.x,
            y: frame.origin.y + (frame.height - newSize.height)
        )
    }

    private func resizeAnchored(to size: NSSize, makeResizable: Bool, animated: Bool = false) {
        // Cancel any pending resizeToFixedHeight work item to prevent stale resizes
        resizeWorkItem?.cancel()
        resizeWorkItem = nil

        let constrainedSize = NSSize(
            width: max(size.width, FloatingControlBarWindow.minBarSize.width),
            height: max(size.height, FloatingControlBarWindow.minBarSize.height)
        )
        let newOrigin = originForTopLeftAnchor(newSize: constrainedSize)

        log("FloatingControlBar: resizeAnchored to \(constrainedSize) resizable=\(makeResizable) animated=\(animated) from=\(frame.size)")

        if makeResizable {
            styleMask.insert(.resizable)
        } else {
            styleMask.remove(.resizable)
        }

        isResizingProgrammatically = true

        NSAnimationContext.beginGrouping()
        NSAnimationContext.current.duration = animated ? 0.3 : 0
        NSAnimationContext.current.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        self.setFrame(NSRect(origin: newOrigin, size: constrainedSize), display: true, animate: animated)
        NSAnimationContext.endGrouping()

        self.isResizingProgrammatically = false
    }

    private func resizeToFixedHeight(_ height: CGFloat, animated: Bool = false) {
        resizeWorkItem?.cancel()
        // Use narrow width for collapsed bar, expanded for AI panels
        let width = height <= FloatingControlBarWindow.minBarSize.height ? FloatingControlBarWindow.defaultSize.width : FloatingControlBarWindow.expandedWidth
        let size = NSSize(width: width, height: height)
        resizeWorkItem = DispatchWorkItem { [weak self] in
            self?.resizeAnchored(to: size, makeResizable: false, animated: animated)
        }
        if let workItem = resizeWorkItem {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05, execute: workItem)
        }
    }

    /// Resize window for PTT state (expanded when listening, narrow when idle)
    func resizeForPTTState(expanded: Bool) {
        let width = expanded ? FloatingControlBarWindow.expandedWidth : FloatingControlBarWindow.defaultSize.width
        let size = NSSize(width: width, height: FloatingControlBarWindow.minBarSize.height)
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

        resizeAnchored(to: targetSize, makeResizable: true, animated: animated)
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

    // MARK: - NSWindowDelegate

    @objc func windowDidMove(_ notification: Notification) {
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
    func setup(appState: AppState) {
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

        // Hide just orders out
        barWindow.onHide = {}

        // Send query through a dedicated ChatProvider
        let provider = ChatProvider()
        self.chatProvider = provider

        barWindow.onSendQuery = { [weak self, weak barWindow] message, screenshotURL in
            guard let self = self, let barWindow = barWindow else { return }
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
        window.state.aiResponseText = ""
        window.state.screenshotURL = nil

        let provider = ChatProvider()
        self.chatProvider = provider

        // Re-wire the onSendQuery to use the new provider
        window.onSendQuery = { [weak self, weak window] message, screenshotURL in
            guard let self = self, let window = window else { return }
            Task { @MainActor in
                await self.sendAIQuery(message, screenshotURL: screenshotURL, barWindow: window, provider: provider)
            }
        }

        if !window.isVisible {
            show()
        }

        // Set up state — go straight to response view (skip input view to avoid resize flicker)
        window.state.showingAIConversation = true
        window.state.showingAIResponse = true
        window.state.isAILoading = true
        window.state.aiInputText = query
        window.state.displayedQuery = query
        window.state.aiResponseText = ""
        window.resizeToResponseHeightPublic(animated: true)
        window.orderFrontRegardless()

        // Auto-send the query
        Task { @MainActor in
            await sendAIQuery(query, screenshotURL: screenshot, barWindow: window, provider: provider)
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

    private func sendAIQuery(_ message: String, screenshotURL: URL?, barWindow: FloatingControlBarWindow, provider: ChatProvider) async {
        AnalyticsManager.shared.floatingBarQuerySent(messageLength: message.count, hasScreenshot: screenshotURL != nil)

        // Initialize the provider if needed
        if provider.messages.isEmpty {
            await provider.initialize()
        }

        // Observe messages for streaming response
        chatCancellable?.cancel()
        barWindow.state.aiResponseText = ""
        barWindow.state.isAILoading = true
        chatCancellable = provider.$messages
            .dropFirst()  // Skip initial emission to prevent old response from flashing
            .receive(on: DispatchQueue.main)
            .sink { [weak barWindow] messages in
                guard let lastMessage = messages.last, lastMessage.sender == .ai else { return }
                if lastMessage.isStreaming {
                    barWindow?.updateAIResponse(type: "data", text: "")
                    barWindow?.state.aiResponseText = lastMessage.text
                    barWindow?.state.isAILoading = false
                    if !barWindow!.state.showingAIResponse {
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                            barWindow?.state.showingAIResponse = true
                        }
                        barWindow?.resizeToResponseHeightPublic(animated: true)
                    }
                } else {
                    barWindow?.state.aiResponseText = lastMessage.text
                    barWindow?.state.isAILoading = false
                }
            }

        // Build prompt with screenshot context if available
        var fullMessage = message
        if let url = screenshotURL {
            fullMessage = "[Screenshot of user's screen attached: \(url.path)]\n\n\(message)"
        }

        await provider.sendMessage(fullMessage)
    }
}

// Expose resizeToResponseHeight for the manager
extension FloatingControlBarWindow {
    func resizeToResponseHeightPublic(animated: Bool = false) {
        resizeToResponseHeight(animated: animated)
    }
}
