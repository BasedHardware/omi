import AppKit
import SwiftUI

/// Horizontal row of agent pill icons rendered just below the floating bar.
/// Each pill is a small rounded square containing the Omi logo + a status dot.
struct AgentPillsRowView: View {
    @ObservedObject var manager: AgentPillsManager

    var body: some View {
        HStack(spacing: AgentPillsLayout.pillSpacing) {
            ForEach(manager.pills) { pill in
                AgentPillView(pill: pill, manager: manager)
            }
        }
        .padding(.horizontal, AgentPillsLayout.rowHorizontalPadding)
        .padding(.vertical, AgentPillsLayout.rowVerticalPadding)
        .frame(minHeight: AgentPillsLayout.rowHeight, alignment: .top)
    }
}

enum AgentPillsLayout {
    static let pillSize: CGFloat = 38
    static let pillSpacing: CGFloat = 8
    static let rowHorizontalPadding: CGFloat = 6
    static let rowVerticalPadding: CGFloat = 4
    /// Total row height including padding (used by the overlay window for sizing).
    static let rowHeight: CGFloat = pillSize + rowVerticalPadding * 2
    /// Max popover width when hovering a pill.
    static let popoverWidth: CGFloat = 320
}

/// One agent pill: rounded square + circular Omi logo + status dot. Slowly
/// rotates the logo while running, settles when done.
struct AgentPillView: View {
    @ObservedObject var pill: AgentPill
    @ObservedObject var manager: AgentPillsManager
    @State private var rotationAngle: Double = 0
    @State private var isHovering: Bool = false
    @State private var rotationTask: Task<Void, Never>?

    var body: some View {
        ZStack(alignment: .topTrailing) {
            roundedSquare
                .overlay(omiBadge)
                .overlay(statusDot, alignment: .topTrailing)
                .scaleEffect(isHovering ? 1.06 : 1.0)
                .animation(.spring(response: 0.32, dampingFraction: 0.72), value: isHovering)
        }
        .frame(width: AgentPillsLayout.pillSize, height: AgentPillsLayout.pillSize)
        .contentShape(Rectangle())
        .onHover { hovering in
            isHovering = hovering
            if hovering {
                manager.hoveredPillID = pill.id
            } else if manager.hoveredPillID == pill.id {
                manager.hoveredPillID = nil
            }
        }
        .onAppear { startRotationIfRunning() }
        .onChange(of: pill.status) { startRotationIfRunning() }
        .onDisappear {
            rotationTask?.cancel()
            rotationTask = nil
        }
        .accessibilityLabel("\(pill.title) — \(pill.status.displayLabel)")
    }

    private var roundedSquare: some View {
        RoundedRectangle(cornerRadius: 9, style: .continuous)
            .fill(
                LinearGradient(
                    colors: [
                        Color(nsColor: NSColor(white: 0.18, alpha: 0.95)),
                        Color(nsColor: NSColor(white: 0.08, alpha: 0.95)),
                    ],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .strokeBorder(Color.white.opacity(0.10), lineWidth: 0.6)
            )
            .shadow(color: Color.black.opacity(0.45), radius: 6, x: 0, y: 3)
    }

    private var omiBadge: some View {
        ZStack {
            Circle()
                .fill(
                    LinearGradient(
                        colors: [
                            Color(red: 0.95, green: 0.95, blue: 0.97),
                            Color(red: 0.78, green: 0.78, blue: 0.82),
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: AgentPillsLayout.pillSize - 14, height: AgentPillsLayout.pillSize - 14)
                .overlay(
                    Circle().strokeBorder(Color.black.opacity(0.25), lineWidth: 0.5)
                )

            if let logo = AgentPillView.omiLogo {
                Image(nsImage: logo)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: .fit)
                    .frame(width: AgentPillsLayout.pillSize - 18, height: AgentPillsLayout.pillSize - 18)
                    .clipShape(Circle())
            } else {
                // Fallback: solid disc with a subtle highlight
                Circle()
                    .fill(Color(nsColor: NSColor(white: 0.05, alpha: 1.0)))
                    .frame(width: AgentPillsLayout.pillSize - 18, height: AgentPillsLayout.pillSize - 18)
            }
        }
        .rotationEffect(.degrees(rotationAngle))
    }

    @ViewBuilder
    private var statusDot: some View {
        // Only render a status dot when the agent has finished. While running
        // the rotating logo itself signals activity — the dot would be
        // redundant noise on top of that.
        if showStatusDot {
            ZStack {
                Circle()
                    .fill(Color(nsColor: NSColor(white: 0.05, alpha: 1.0)))
                    .frame(width: 10, height: 10)
                Circle()
                    .fill(statusColor)
                    .frame(width: 8, height: 8)
            }
            .offset(x: 3, y: -3)
            .transition(.scale.combined(with: .opacity))
        }
    }

    /// Show the dot only on terminal states. While running we rely on the
    /// rotating logo as the activity signal.
    private var showStatusDot: Bool {
        switch pill.status {
        case .done, .failed: return true
        default: return false
        }
    }

    private var statusColor: Color {
        switch pill.status {
        case .queued: return Color(red: 0.85, green: 0.78, blue: 0.30)
        case .starting, .running: return Color(red: 0.27, green: 0.92, blue: 0.46)
        case .done: return Color(red: 0.27, green: 0.92, blue: 0.46)  // green
        case .failed: return Color(red: 1.0, green: 0.42, blue: 0.42)
        }
    }

    private func startRotationIfRunning() {
        switch pill.status {
        case .starting, .running:
            // Continuous slow rotation. We use a Task instead of repeatForever
            // because repeatForever can't be cancelled cleanly from outside —
            // explicit Task.cancel() lets us actually halt rotation when the
            // agent finishes (otherwise the spinner kept going past Done).
            rotationTask?.cancel()
            rotationTask = Task { @MainActor in
                while !Task.isCancelled {
                    let target = rotationAngle + 360
                    withAnimation(.linear(duration: 4.0)) {
                        rotationAngle = target
                    }
                    do {
                        try await Task.sleep(nanoseconds: 4_000_000_000)
                    } catch {
                        break
                    }
                }
            }
        default:
            // Cancel the task and snap to the nearest full revolution with a
            // gentle settle.
            rotationTask?.cancel()
            rotationTask = nil
            let settled = (rotationAngle / 360.0).rounded() * 360.0
            withAnimation(.easeOut(duration: 0.35)) {
                rotationAngle = settled
            }
        }
    }

    /// Cached Omi logo image, loaded once from the resource bundle.
    private static let omiLogo: NSImage? = {
        if let url = Bundle.resourceBundle.url(forResource: "omi_app_icon", withExtension: "png"),
            let img = NSImage(contentsOf: url) {
            return img
        }
        if let url = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
            let img = NSImage(contentsOf: url) {
            return img
        }
        return nil
    }()
}

/// Popover panel that appears under the hovered pill. Shows what the agent is
/// doing right now (Clicky-style), and on completion suggested follow-ups.
struct AgentPillPopover: View {
    @ObservedObject var pill: AgentPill
    var onDismiss: () -> Void
    var onOpenInChat: () -> Void
    var onSendFollowUp: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            header
            activityRow
            if !isFinished {
                progressBar
            }
            if case .failed(let message) = pill.status {
                Text(message)
                    .scaledFont(size: 11)
                    .foregroundColor(Color(red: 1.0, green: 0.55, blue: 0.55))
                    .lineLimit(3)
            }
            if isFinished {
                followUpSection
            }
        }
        .padding(14)
        .frame(width: AgentPillsLayout.popoverWidth, alignment: .leading)
        .floatingBackground(cornerRadius: 14)
    }

    private var isFinished: Bool {
        switch pill.status {
        case .done, .failed: return true
        default: return false
        }
    }

    private var header: some View {
        HStack(alignment: .center, spacing: 8) {
            Text(pill.title)
                .scaledFont(size: 12, weight: .bold)
                .foregroundColor(.white)
                .lineLimit(1)

            Spacer(minLength: 6)

            Text(pill.status.displayLabel)
                .scaledFont(size: 10, weight: .semibold)
                .foregroundColor(statusBadgeForeground)
                .padding(.horizontal, 7)
                .padding(.vertical, 3)
                .background(statusBadgeBackground)
                .clipShape(Capsule())

            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(.white.opacity(0.6))
                    .frame(width: 18, height: 18)
                    .background(Color.white.opacity(0.08))
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Dismiss agent")
        }
    }

    private var statusBadgeForeground: Color {
        switch pill.status {
        case .queued: return Color(red: 0.0, green: 0.0, blue: 0.0)
        case .starting, .running: return Color(red: 0.18, green: 0.10, blue: 0.0)
        case .done: return Color(red: 0.07, green: 0.18, blue: 0.10)
        case .failed: return .white
        }
    }

    private var statusBadgeBackground: Color {
        switch pill.status {
        case .queued: return Color(red: 0.85, green: 0.85, blue: 0.85)
        case .starting, .running: return Color(red: 1.0, green: 0.78, blue: 0.30)
        case .done: return Color(red: 0.45, green: 0.92, blue: 0.55)
        case .failed: return Color(red: 0.78, green: 0.32, blue: 0.32)
        }
    }

    private var activityRow: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: activityIcon)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.white.opacity(0.7))
                .frame(width: 16, height: 16, alignment: .center)
                .background(Color.white.opacity(0.06))
                .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))

            Text(pill.latestActivity)
                .scaledFont(size: 12)
                .foregroundColor(.white.opacity(0.86))
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var activityIcon: String {
        let lower = pill.latestActivity.lowercased()
        if lower.contains("running command") || lower.hasPrefix("bash") { return "terminal" }
        if lower.contains("reading file") || lower.contains("editing file") { return "doc.text" }
        if lower.contains("searching") { return "magnifyingglass" }
        if lower.contains("fetching page") || lower.contains("web") { return "globe" }
        return "sparkles"
    }

    private var progressBar: some View {
        IndeterminateProgressBar()
            .frame(height: 3)
            .clipShape(RoundedRectangle(cornerRadius: 1.5))
    }

    private var followUpSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !pill.suggestedFollowUps.isEmpty {
                Text("Suggested next:")
                    .scaledFont(size: 10, weight: .medium)
                    .foregroundColor(.white.opacity(0.5))

                AgentFollowUpFlowLayout(spacing: 6) {
                    ForEach(pill.suggestedFollowUps, id: \.self) { suggestion in
                        Button {
                            onSendFollowUp(suggestion)
                        } label: {
                            Text(suggestion)
                                .scaledFont(size: 11, weight: .medium)
                                .foregroundColor(.white)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .background(Color.white.opacity(0.10))
                                .clipShape(Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            Button(action: onOpenInChat) {
                HStack(spacing: 6) {
                    Image(systemName: "bubble.left.and.bubble.right.fill")
                        .font(.system(size: 11))
                    Text("Open in chat")
                        .scaledFont(size: 11, weight: .medium)
                }
                .foregroundColor(.white)
                .padding(.horizontal, 12)
                .padding(.vertical, 7)
                .frame(maxWidth: .infinity)
                .background(Color.white.opacity(0.10))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }
            .buttonStyle(.plain)
        }
    }
}

/// Soft, infinitely-running progress bar shown while the agent runs.
private struct IndeterminateProgressBar: View {
    @State private var phase: CGFloat = 0

    var body: some View {
        GeometryReader { proxy in
            let width = proxy.size.width
            ZStack(alignment: .leading) {
                Color.white.opacity(0.08)
                LinearGradient(
                    colors: [
                        Color.white.opacity(0.02),
                        Color.white.opacity(0.65),
                        Color.white.opacity(0.02),
                    ],
                    startPoint: .leading,
                    endPoint: .trailing
                )
                .frame(width: width * 0.35)
                .offset(x: -width * 0.35 + (width + width * 0.35) * phase)
            }
            .clipped()
            .onAppear {
                withAnimation(.linear(duration: 1.4).repeatForever(autoreverses: false)) {
                    phase = 1
                }
            }
        }
    }
}

/// Minimal flow layout for follow-up chips so they wrap if too wide.
private struct AgentFollowUpFlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var rowWidth: CGFloat = 0
        var rowHeight: CGFloat = 0
        var totalHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if rowWidth + size.width > maxWidth {
                totalHeight += rowHeight + spacing
                rowWidth = size.width + spacing
                rowHeight = size.height
            } else {
                rowWidth += size.width + spacing
                rowHeight = max(rowHeight, size.height)
            }
        }
        totalHeight += rowHeight
        return CGSize(width: maxWidth.isFinite ? maxWidth : rowWidth, height: totalHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
