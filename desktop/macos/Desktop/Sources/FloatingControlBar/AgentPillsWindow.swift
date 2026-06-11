import AppKit
import Combine
import SwiftUI

/// Borderless overlay window that displays the agent pills row and the hover
/// popover directly below the floating control bar. Kept separate from the
/// main floating bar window so it doesn't fight the bar's tightly-managed
/// resize logic.
@MainActor
final class AgentPillsWindow: NSPanel, NSWindowDelegate {
    /// Vertical gap between the floating bar's bottom edge and the pills row.
    static let gapBelowBar: CGFloat = 8

    private let manager = AgentPillsManager.shared
    private var hostingView: NSHostingView<AnyView>?
    private var pillsCancellable: AnyCancellable?
    private var hoverCancellable: AnyCancellable?
    private weak var anchorWindow: NSWindow?

    init() {
        super.init(
            contentRect: NSRect(origin: .zero, size: NSSize(width: 200, height: AgentPillsLayout.rowHeight)),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        self.appearance = NSAppearance(named: .vibrantDark)
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = false
        self.level = .floating
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        self.isMovableByWindowBackground = false
        self.isReleasedWhenClosed = false
        self.delegate = self
        self.ignoresMouseEvents = false
        self.becomesKeyOnlyIfNeeded = true

        setupHostingView()
        observeManager()
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }

    /// Anchor the pills window to the floating bar's window frame.
    func attach(to barWindow: NSWindow) {
        self.anchorWindow = barWindow
        repositionToAnchor()
        // Reposition whenever the bar moves or resizes.
        NotificationCenter.default.addObserver(
            self, selector: #selector(anchorMoved(_:)),
            name: NSWindow.didMoveNotification, object: barWindow
        )
        NotificationCenter.default.addObserver(
            self, selector: #selector(anchorMoved(_:)),
            name: NSWindow.didResizeNotification, object: barWindow
        )
    }

    @objc private func anchorMoved(_ note: Notification) {
        repositionToAnchor()
    }

    private func setupHostingView() {
        let root = AgentPillsContainerView(
            manager: manager,
            onSendFollowUp: { [weak self] pill, text in
                self?.spawnFollowUp(from: pill, text: text)
            },
            onOpenInChat: { [weak self] pill in
                self?.openPillInChat(pill)
            }
        )

        let view = AnyView(root.preferredColorScheme(.dark).withFontScaling())
        let hosting = NSHostingView(rootView: view)
        hosting.appearance = NSAppearance(named: .vibrantDark)
        hosting.translatesAutoresizingMaskIntoConstraints = false
        hostingView = hosting

        let container = NSView()
        self.contentView = container
        container.addSubview(hosting)
        NSLayoutConstraint.activate([
            hosting.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            hosting.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            hosting.topAnchor.constraint(equalTo: container.topAnchor),
            hosting.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])
    }

    private func observeManager() {
        pillsCancellable = manager.$pills
            .receive(on: DispatchQueue.main)
            .sink { [weak self] pills in
                self?.updateVisibility(pillCount: pills.count)
                self?.repositionToAnchor()
            }
        hoverCancellable = manager.$hoveredPillID
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                self?.repositionToAnchor()
            }
    }

    private func updateVisibility(pillCount: Int) {
        if pillCount == 0 {
            self.orderOut(nil)
        } else if !self.isVisible, let anchor = anchorWindow, anchor.isVisible {
            self.orderFront(nil)
        }
    }

    /// Recompute frame size and position based on the anchor window and the
    /// current pill count + hover state.
    private func repositionToAnchor() {
        guard let anchor = anchorWindow else { return }

        let pillCount = manager.pills.count
        guard pillCount > 0 else {
            self.orderOut(nil)
            return
        }

        let rowWidth = computeRowWidth(pillCount: pillCount)
        let popoverHeight: CGFloat = manager.hoveredPillID != nil ? popoverEstimatedHeight() : 0
        let totalHeight = AgentPillsLayout.rowHeight + (popoverHeight > 0 ? popoverHeight + 6 : 0)

        let anchorFrame = anchor.frame
        // Center the row horizontally on the anchor, position right below it.
        let centerX = anchorFrame.midX
        let topY = anchorFrame.minY - AgentPillsWindow.gapBelowBar
        let originX = centerX - max(rowWidth, AgentPillsLayout.popoverWidth) / 2
        let originY = topY - totalHeight

        let frame = NSRect(
            x: originX,
            y: originY,
            width: max(rowWidth, AgentPillsLayout.popoverWidth),
            height: totalHeight
        )
        self.setFrame(frame, display: true, animate: false)

        // Make sure we're above the floating bar and visible on the same screen.
        if let anchorScreen = anchor.screen, anchorScreen != self.screen {
            self.setFrameOrigin(frame.origin)
        }

        if !self.isVisible, let anchor = anchorWindow, anchor.isVisible {
            self.orderFront(nil)
        }
    }

    private func computeRowWidth(pillCount: Int) -> CGFloat {
        let pillsWidth = CGFloat(pillCount) * AgentPillsLayout.pillSize
            + CGFloat(max(0, pillCount - 1)) * AgentPillsLayout.pillSpacing
        return pillsWidth + AgentPillsLayout.rowHorizontalPadding * 2
    }

    private func popoverEstimatedHeight() -> CGFloat {
        // Generous estimate that fits header + activity + (progress bar OR follow-ups).
        guard let id = manager.hoveredPillID,
            let pill = manager.pills.first(where: { $0.id == id })
        else { return 0 }
        switch pill.status {
        case .done, .failed: return 170
        default: return 110
        }
    }

    private func spawnFollowUp(from pill: AgentPill, text: String) {
        manager.spawnFromUserQuery(text, model: pill.model)
    }

    private func openPillInChat(_ pill: AgentPill) {
        // For the demo: bring the floating bar to front, open Ask Omi conversation
        // pre-populated with the pill's query so the user can continue inline.
        anchorWindow?.makeKeyAndOrderFront(nil)
        NotificationCenter.default.post(
            name: .agentPillRequestedChat,
            object: nil,
            userInfo: ["query": pill.query]
        )
    }
}

extension Notification.Name {
    static let agentPillRequestedChat = Notification.Name("agentPillRequestedChat")
}

/// SwiftUI container that draws the pills row plus a hover popover anchored
/// below it. The popover is rendered inside the same window so hovering the
/// pill smoothly transitions into hovering the popover.
struct AgentPillsContainerView: View {
    @ObservedObject var manager: AgentPillsManager
    var onSendFollowUp: (AgentPill, String) -> Void
    var onOpenInChat: (AgentPill) -> Void

    var body: some View {
        VStack(spacing: 6) {
            AgentPillsRowView(manager: manager)
                .floatingBackground(cornerRadius: 14)
                .fixedSize(horizontal: true, vertical: true)
                .frame(height: AgentPillsLayout.rowHeight)

            if let hoveredID = manager.hoveredPillID,
                let pill = manager.pills.first(where: { $0.id == hoveredID }) {
                AgentPillPopover(
                    pill: pill,
                    onDismiss: { manager.dismiss(pillID: pill.id) },
                    onOpenInChat: { onOpenInChat(pill) },
                    onSendFollowUp: { text in onSendFollowUp(pill, text) }
                )
                .transition(.move(edge: .top).combined(with: .opacity))
                .onHover { hovering in
                    // Keep the popover open while the user is interacting with it.
                    if hovering {
                        manager.hoveredPillID = pill.id
                    }
                }
            }

            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .top)
        .animation(.spring(response: 0.32, dampingFraction: 0.85), value: manager.hoveredPillID)
        .animation(.spring(response: 0.32, dampingFraction: 0.85), value: manager.pills.count)
    }
}
