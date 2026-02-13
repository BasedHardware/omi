import Cocoa
import Combine
import SwiftUI

/// NSWindow subclass for the floating control bar.
class FloatingControlBarWindow: NSWindow, NSWindowDelegate {
    private static let positionKey = "FloatingControlBarPosition"
    private static let sizeKey = "FloatingControlBarSize"
    private static let defaultSize = NSSize(width: 430, height: 60)
    private static let minBarSize = NSSize(width: 430, height: 60)
    private static let maxBarSize = NSSize(width: 1200, height: 1000)

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

    private func setupViews() {
        let swiftUIView = FloatingControlBarView(
            window: self,
            onPlayPause: { [weak self] in self?.onPlayPause?() },
            onAskAI: { [weak self] in self?.handleAskAI() },
            onHide: { [weak self] in self?.hideBar() },
            onSendQuery: { [weak self] message, screenshotURL in self?.onSendQuery?(message, screenshotURL) },
            onCloseAI: { [weak self] in self?.closeAIConversation() },
            onAskFollowUp: { [weak self] in self?.resetToInputView() },
            onCaptureScreenshot: { [weak self] in self?.captureScreenshot() }
        ).environmentObject(state)

        hostingView = NSHostingView(rootView: AnyView(
            swiftUIView
                .preferredColorScheme(.dark)
                .environment(\.colorScheme, .dark)
        ))
        hostingView?.appearance = NSAppearance(named: .vibrantDark)
        self.contentView = hostingView

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
            onAskAI?()
        }
    }

    func captureScreenshot() {
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
        }
    }

    func closeAIConversation() {
        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            state.showingAIConversation = false
            state.showingAIResponse = false
            state.aiInputText = ""
            state.aiResponseText = ""
            state.screenshotURL = nil
        }
        resizeToFixedHeight(60, animated: true)
    }

    private func resetToInputView() {
        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            state.showingAIResponse = false
            state.aiResponseText = ""
            state.aiInputText = ""
            state.isAILoading = false
            state.inputViewHeight = 120
        }
        resizeToFixedHeight(120, animated: true)
        setupInputHeightObserver()
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
        // Capture screenshot before showing the AI panel
        captureScreenshot()

        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            state.showingAIConversation = true
            state.showingAIResponse = false
            state.isAILoading = true
            state.aiInputText = ""
            state.aiResponseText = ""
            state.inputViewHeight = 100
        }
        resizeToFixedHeight(120, animated: true)
        setupInputHeightObserver()
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
        let constrainedSize = NSSize(
            width: max(size.width, FloatingControlBarWindow.minBarSize.width),
            height: max(size.height, FloatingControlBarWindow.minBarSize.height)
        )
        let newOrigin = originForTopLeftAnchor(newSize: constrainedSize)

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
        let size = NSSize(width: 430, height: height)
        resizeWorkItem = DispatchWorkItem { [weak self] in
            self?.resizeAnchored(to: size, makeResizable: false, animated: animated)
        }
        if let workItem = resizeWorkItem {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05, execute: workItem)
        }
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

    private var window: FloatingControlBarWindow?
    private var recordingCancellable: AnyCancellable?
    private var durationCancellable: AnyCancellable?
    private var chatCancellable: AnyCancellable?
    private var chatProvider: ChatProvider?

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

    /// Show the floating bar.
    func show() {
        log("FloatingControlBarManager: show() called, window=\(window != nil), isVisible=\(window?.isVisible ?? false)")
        window?.orderFront(nil)
        log("FloatingControlBarManager: show() done, frame=\(window?.frame ?? .zero)")
    }

    /// Hide the floating bar.
    func hide() {
        window?.orderOut(nil)
    }

    /// Toggle visibility.
    func toggle() {
        guard let window = window else { return }
        if window.isVisible {
            hide()
        } else {
            show()
        }
    }

    /// Open the AI input panel.
    func openAIInput() {
        guard let window = window else { return }
        if !window.isVisible {
            show()
        }
        window.showAIConversation()
        window.makeKeyAndOrderFront(nil)
    }

    // MARK: - AI Query

    private func sendAIQuery(_ message: String, screenshotURL: URL?, barWindow: FloatingControlBarWindow, provider: ChatProvider) async {
        // Initialize the provider if needed
        if provider.messages.isEmpty {
            await provider.initialize()
        }

        // Observe messages for streaming response
        chatCancellable?.cancel()
        chatCancellable = provider.$messages
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
