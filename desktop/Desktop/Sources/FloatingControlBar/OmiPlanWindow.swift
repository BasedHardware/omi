import AppKit
import SwiftUI

/// Standalone floating window that lists every step of a computer-use plan
/// with progress indicators. Lives independently of the cursor bubble so
/// the user can read the full plan while the cursor does its work.
@MainActor
final class OmiPlanWindow {
    static let shared = OmiPlanWindow()

    private let state = OmiPlanWindowState()
    private var panel: NSPanel?
    private var autoDismissWork: DispatchWorkItem?

    private init() {}

    // MARK: - Public API (called from OmiActionExecutor)

    func startExecution(planDescription: String, steps: [String]) {
        autoDismissWork?.cancel()
        autoDismissWork = nil

        state.planDescription = planDescription
        state.stepDescriptions = steps
        state.activeStepIndex = 0
        state.failedStepIndex = nil

        showPanel()
    }

    func updateStep(index: Int) {
        state.activeStepIndex = index
    }

    func markStepFailed(index: Int) {
        state.failedStepIndex = index
        scheduleDismiss(after: 3.0)
    }

    func cancelExecution() {
        scheduleDismiss(after: 0.5)
    }

    func finishExecution() {
        // Bumping the active index past the end makes every row render as
        // .completed — no separate "isFinished" flag needed.
        state.activeStepIndex = state.stepDescriptions.count
        scheduleDismiss(after: 1.5)
    }

    // MARK: - Panel Lifecycle

    private func showPanel() {
        if panel == nil {
            panel = makePanel()
        }
        positionPanel()
        panel?.orderFrontRegardless()
    }

    private func dismiss() {
        panel?.orderOut(nil)
    }

    private func scheduleDismiss(after seconds: TimeInterval) {
        autoDismissWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            Task { @MainActor in self?.dismiss() }
        }
        autoDismissWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: work)
    }

    private func makePanel() -> NSPanel {
        let initialSize = NSRect(x: 0, y: 0, width: 320, height: 200)
        let p = NSPanel(
            contentRect: initialSize,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        p.isOpaque = false
        p.backgroundColor = .clear
        p.level = .floating
        p.hasShadow = true
        p.isMovableByWindowBackground = true
        p.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]
        p.isReleasedWhenClosed = false
        p.hidesOnDeactivate = false

        // Borderless panels crash if NSHostingView is assigned directly as
        // contentView. Wrap in a plain container (same pattern as
        // CursorPTTOverlayManager).
        let hosting = NSHostingView(rootView: OmiPlanWindowView(state: state))
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

    /// Anchor the panel to the top-right of the screen containing the
    /// cursor, with a comfortable inset from the menu bar.
    private func positionPanel() {
        guard let panel else { return }
        let mouseLocation = NSEvent.mouseLocation
        let targetScreen = NSScreen.screens.first(where: { $0.frame.contains(mouseLocation) })
            ?? NSScreen.main
            ?? NSScreen.screens.first
        guard let targetScreen else { return }

        let panelSize = panel.frame.size
        let inset: CGFloat = 18
        let topInset: CGFloat = 44 // clear of the menu bar
        let origin = CGPoint(
            x: targetScreen.visibleFrame.maxX - panelSize.width - inset,
            y: targetScreen.visibleFrame.maxY - panelSize.height - topInset
        )
        panel.setFrameOrigin(origin)
    }
}

// MARK: - State

@MainActor
final class OmiPlanWindowState: ObservableObject {
    @Published var planDescription: String = ""
    @Published var stepDescriptions: [String] = []
    @Published var activeStepIndex: Int = 0
    @Published var failedStepIndex: Int? = nil
}

// MARK: - View

private struct OmiPlanWindowView: View {
    @ObservedObject var state: OmiPlanWindowState

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header
            HStack(spacing: 6) {
                Circle()
                    .fill(Color.indigo)
                    .frame(width: 6, height: 6)
                Text("OMI · COMPUTER USE")
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .tracking(0.8)
                    .foregroundColor(.secondary)
                Spacer()
                Text("esc · cancel")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.secondary.opacity(0.6))
            }

            if !state.planDescription.isEmpty {
                Text(state.planDescription)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.primary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Divider().opacity(0.4)

            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(state.stepDescriptions.enumerated()), id: \.offset) { index, description in
                    stepRow(index: index, description: description)
                }
            }
        }
        .padding(14)
        .frame(width: 320, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(.ultraThinMaterial)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 0.5)
        )
    }

    @ViewBuilder
    private func stepRow(index: Int, description: String) -> some View {
        let status = statusFor(index: index)
        HStack(alignment: .top, spacing: 10) {
            indicator(for: status)
                .frame(width: 14, height: 14)
                .padding(.top, 1)
            Text(description)
                .font(.system(size: 12))
                .foregroundColor(textColor(for: status))
                .strikethrough(status == .completed, color: .secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
    }

    private enum StepStatus { case completed, active, pending, failed }

    private func statusFor(index: Int) -> StepStatus {
        if state.failedStepIndex == index { return .failed }
        if index < state.activeStepIndex { return .completed }
        if index == state.activeStepIndex { return .active }
        return .pending
    }

    @ViewBuilder
    private func indicator(for status: StepStatus) -> some View {
        switch status {
        case .completed:
            ZStack {
                Circle().fill(Color.indigo)
                Image(systemName: "checkmark")
                    .font(.system(size: 8, weight: .bold))
                    .foregroundColor(.white)
            }
        case .active:
            ZStack {
                Circle().stroke(Color.indigo, lineWidth: 1.5)
                Circle()
                    .fill(Color.indigo)
                    .frame(width: 6, height: 6)
            }
        case .pending:
            Circle().stroke(Color.secondary.opacity(0.35), lineWidth: 1)
        case .failed:
            ZStack {
                Circle().fill(Color.red)
                Image(systemName: "xmark")
                    .font(.system(size: 8, weight: .bold))
                    .foregroundColor(.white)
            }
        }
    }

    private func textColor(for status: StepStatus) -> Color {
        switch status {
        case .completed: return .secondary
        case .active: return .primary
        case .pending: return .secondary.opacity(0.7)
        case .failed: return .red
        }
    }
}
