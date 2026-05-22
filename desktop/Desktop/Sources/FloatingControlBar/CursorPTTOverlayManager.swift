import AppKit
import Combine
import SwiftUI

/// Manages the full-screen transparent cursor overlay.
///
/// Lifecycle:
///   showIdle()            — called once at startup; tiny dot follows cursor always
///   startListening(barState:) — pulsing dot + live transcript; subscribes to voiceTranscript
///   startProcessing()     — spinning ring; between Option release and first AI token
///   startResponding(barState:) — streaming bubble; intercepts mouse clicks for dismiss
///   showNotification(_:)  — amber bubble for proactive alerts
///   dismiss()             — returns to idle; never restores the floating bar
@MainActor
final class CursorPTTOverlayManager {
    static let shared = CursorPTTOverlayManager()

    private(set) var overlayState = CursorPTTOverlayState()

    private var panel: NSPanel?
    private var cursorTrackingSource: DispatchSourceTimer?
    private var barStateCancellable: AnyCancellable?
    private var transcriptCancellable: AnyCancellable?
    private var queryCancellable: AnyCancellable?
    private var autoDismissWork: DispatchWorkItem?

    private init() {}

    // MARK: - Public API

    func showIdle() {
        overlayState.phase = .idle
        showPanel(interceptMouse: false)
        startCursorTimer()
    }

    func startListening(barState: FloatingControlBarState) {
        autoDismissWork?.cancel()
        autoDismissWork = nil
        // Cancel previous response subscriptions so a completing prior response can't
        // schedule an auto-dismiss that fires and kills the incoming new response.
        cancelResponseSubscriptions()
        resetContent()
        overlayState.phase = .listening
        panel?.ignoresMouseEvents = true

        transcriptCancellable = barState.$voiceTranscript
            .receive(on: DispatchQueue.main)
            .sink { [weak self] text in
                self?.overlayState.transcriptText = text
            }
    }

    func startProcessing() {
        // Keep transcriptCancellable alive — batch transcript arrives during this phase
        overlayState.phase = .processing
        panel?.ignoresMouseEvents = true
    }

    func startResponding(barState: FloatingControlBarState) {
        cancelResponseSubscriptions()
        resetContent()
        // Clear stale message before subscribing so the publisher doesn't immediately
        // fire with an old complete message and trigger a premature auto-dismiss.
        barState.currentAIMessage = nil
        overlayState.phase = .responding
        panel?.ignoresMouseEvents = false

        queryCancellable = barState.$displayedQuery
            .receive(on: DispatchQueue.main)
            .filter { !$0.isEmpty }
            .sink { [weak self] query in
                self?.overlayState.displayedQuery = query
            }

        barStateCancellable = barState.$currentAIMessage
            .receive(on: DispatchQueue.main)
            .sink { [weak self] message in
                guard let self else { return }
                self.overlayState.streamingText = Self.sanitizeForCursorBubble(message?.text ?? "")
                if let message, message.isStreaming {
                    // New content arriving — cancel any stale auto-dismiss timer
                    self.autoDismissWork?.cancel()
                    self.autoDismissWork = nil
                } else if let message, !message.isStreaming, !message.text.isEmpty {
                    self.scheduleAutoDismiss(after: 5.0)
                }
            }
    }

    func showNotification(_ notification: FloatingBarNotification) {
        autoDismissWork?.cancel()
        cancelResponseSubscriptions()
        transcriptCancellable = nil
        overlayState.displayedQuery = notification.title
        overlayState.streamingText = notification.message
        overlayState.phase = .notifying
        panel?.ignoresMouseEvents = false
        scheduleAutoDismiss(after: 6.0)
    }

    func dismiss() {
        autoDismissWork?.cancel()
        autoDismissWork = nil
        cancelResponseSubscriptions()
        transcriptCancellable = nil
        resetContent()
        overlayState.phase = .idle
        panel?.ignoresMouseEvents = true
    }

    func startExecution() {
        autoDismissWork?.cancel()
        autoDismissWork = nil
        cancelResponseSubscriptions()
        transcriptCancellable = nil
        overlayState.phase = .executing
        panel?.ignoresMouseEvents = false
    }

    func cancelExecution() {
        overlayState.phase = .idle
        panel?.ignoresMouseEvents = true
    }

    func finishExecution() {
        scheduleAutoDismiss(after: 0.8)
    }

    // MARK: - Cursor-Bubble Sanitization

    /// Strip the `<computer_use>...</computer_use>` block from streaming text
    /// so the cursor bubble only carries the plain-English preamble. The
    /// plan window already visualizes the steps separately.
    static func sanitizeForCursorBubble(_ raw: String) -> String {
        // Fast path: no opener anywhere, nothing to do.
        guard raw.contains("<") else { return raw }

        var cleaned = raw
        let openTag = OmiComputerUseTool.openTag

        // Drop everything from the first opener onward — covers both the
        // "complete block" and "mid-stream, no closer yet" cases.
        if let openRange = cleaned.range(of: openTag) {
            cleaned = String(cleaned[..<openRange.lowerBound])
        } else if let lastLT = cleaned.lastIndex(of: "<"),
                  openTag.hasPrefix(String(cleaned[lastLT...]))
        {
            // Pre-opener: trailing "<" / "<c" / "<comp"… while the model
            // is partway through emitting the tag.
            cleaned = String(cleaned[..<lastLT])
        }

        return cleaned.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - Panel

    private func showPanel(interceptMouse: Bool) {
        if panel == nil {
            panel = makePTTPanel()
        }
        panel?.ignoresMouseEvents = !interceptMouse
        panel?.orderFrontRegardless()
    }

    private func makePTTPanel() -> NSPanel? {
        let screen = NSScreen.main ?? NSScreen.screens.first
        let frame = screen?.frame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let p = NSPanel(
            contentRect: frame,
            styleMask: .borderless,
            backing: .buffered,
            defer: false
        )
        p.isOpaque = false
        p.backgroundColor = .clear
        p.level = .screenSaver
        p.ignoresMouseEvents = true
        p.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]
        p.isReleasedWhenClosed = false
        p.hasShadow = false
        p.hidesOnDeactivate = false

        // Wrap in a container NSView — assigning NSHostingView directly as contentView
        // of a borderless panel causes re-entrant constraint crashes (see FloatingControlBarWindow).
        let hosting = NSHostingView(
            rootView: CursorBubbleView(state: overlayState)
                .onTapGesture { [weak self] in self?.dismiss() }
        )
        hosting.translatesAutoresizingMaskIntoConstraints = false
        let container = NSView()
        p.contentView = container
        container.addSubview(hosting)
        NSLayoutConstraint.activate([
            hosting.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            hosting.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            hosting.topAnchor.constraint(equalTo: container.topAnchor),
            hosting.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])
        return p
    }

    // MARK: - Cursor Tracking

    private func startCursorTimer() {
        stopCursorTimer()
        let source = DispatchSource.makeTimerSource(queue: .main)
        source.schedule(deadline: .now(), repeating: .milliseconds(16))
        source.setEventHandler { [weak self] in
            guard let self, let panel = self.panel else { return }
            let globalLoc = NSEvent.mouseLocation
            let localX = globalLoc.x - panel.frame.minX
            let localY = panel.frame.height - (globalLoc.y - panel.frame.minY)
            let newPos = CGPoint(x: localX, y: localY)
            let dx = newPos.x - self.overlayState.cursorPosition.x
            let dy = newPos.y - self.overlayState.cursorPosition.y
            if dx * dx + dy * dy > 1 {
                self.overlayState.cursorPosition = newPos
            }
            self.updatePanelScreenIfNeeded(for: globalLoc)
        }
        source.resume()
        cursorTrackingSource = source
    }

    private func stopCursorTimer() {
        cursorTrackingSource?.cancel()
        cursorTrackingSource = nil
    }

    private func updatePanelScreenIfNeeded(for location: CGPoint) {
        guard let panel,
              let screen = NSScreen.screens.first(where: { NSMouseInRect(location, $0.frame, false) }),
              screen.frame != panel.frame else { return }
        panel.setFrame(screen.frame, display: false)
        panel.orderFrontRegardless()
    }

    // MARK: - Auto-Dismiss

    private func scheduleAutoDismiss(after delay: TimeInterval) {
        autoDismissWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            self?.dismiss()
        }
        autoDismissWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
    }

    // MARK: - Helpers

    private func cancelResponseSubscriptions() {
        barStateCancellable = nil
        queryCancellable = nil
    }

    private func resetContent() {
        overlayState.streamingText = ""
        overlayState.transcriptText = ""
        overlayState.displayedQuery = ""
    }
}
