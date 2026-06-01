import SwiftUI

/// Full-screen transparent SwiftUI view rendering all cursor overlay states.
/// Positioned at `state.cursorPosition` (panel-local coords, top-left origin).
struct CursorBubbleView: View {
    @ObservedObject var state: CursorPTTOverlayState
    @State private var isPulsingRings = false
    @State private var isSpinning = false
    @State private var blinkVisible = true
    @State private var dotIndex = 0

    /// Offset so indicator sits below-right of cursor tip.
    private let offset = CGPoint(x: 22, y: -6)
    private let bubbleMaxWidth: CGFloat = 340

    var body: some View {
        GeometryReader { geometry in
            if state.phase != .hidden {
                indicator
                    .position(clampedPosition(in: geometry))
            }
        }
        .ignoresSafeArea()
    }

    // MARK: - Position

    private func clampedPosition(in geometry: GeometryProxy) -> CGPoint {
        // cursorPosition is already in panel-local coords (top-left origin) — no Y-flip needed
        let rawX = state.cursorPosition.x + offset.x
        let rawY = state.cursorPosition.y + offset.y
        // Use a tight clamp for the idle dot; wider clamp for bubbles so they don't overflow
        let hClamp: CGFloat = state.phase == .idle ? 10 : bubbleMaxWidth / 2 + 20
        let x = max(hClamp, min(rawX, geometry.size.width - hClamp))
        let y = max(min(rawY, geometry.size.height - 10), 10)
        return CGPoint(x: x, y: y)
    }

    // MARK: - State Router

    @ViewBuilder
    private var indicator: some View {
        switch state.phase {
        case .hidden:
            EmptyView()
        case .idle:
            idleDot
        case .listening:
            listeningView
        case .processing:
            processingView
        case .responding, .notifying:
            respondingBubble
        case .executing:
            executingCard
        }
    }

    // MARK: - Idle Dot

    private var idleDot: some View {
        Circle()
            .fill(Color.indigo)
            .frame(width: 7, height: 7)
            .shadow(color: Color.indigo.opacity(0.6), radius: 3)
            .opacity(0.75)
    }

    // MARK: - Listening

    private var listeningAccent: Color { Color.red }

    private var listeningView: some View {
        HStack(alignment: .top, spacing: 0) {
            pulsingDot
            if !state.transcriptText.isEmpty {
                transcriptBubble
                    .padding(.leading, 10)
            }
        }
    }

    private var pulsingDot: some View {
        ZStack {
            Circle()
                .stroke(listeningAccent.opacity(isPulsingRings ? 0.15 : 0.04), lineWidth: 1)
                .frame(width: isPulsingRings ? 44 : 38, height: isPulsingRings ? 44 : 38)
                .animation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true), value: isPulsingRings)
            Circle()
                .stroke(listeningAccent.opacity(isPulsingRings ? 0.32 : 0.10), lineWidth: 1.5)
                .frame(width: isPulsingRings ? 30 : 26, height: isPulsingRings ? 30 : 26)
                .animation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true).delay(0.12), value: isPulsingRings)
            Circle()
                .fill(listeningAccent)
                .frame(width: 8, height: 8)
                .shadow(color: listeningAccent.opacity(0.9), radius: 4)
        }
        .frame(width: 44, height: 44)
        .onAppear { isPulsingRings = true }
        .onDisappear { isPulsingRings = false }
    }

    private var transcriptBubble: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("You")
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(listeningAccent.opacity(0.8))
                .textCase(.uppercase)
                .tracking(0.5)
            Text(state.transcriptText)
                .font(.system(size: 12))
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: bubbleMaxWidth, alignment: .leading)
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(bubble(border: listeningAccent.opacity(0.3)))
        .environment(\.colorScheme, .dark)
    }

    // MARK: - Processing

    private var processingView: some View {
        HStack(alignment: .top, spacing: 0) {
            spinningDot
            VStack(alignment: .leading, spacing: 4) {
                if !state.transcriptText.isEmpty {
                    Text(state.transcriptText)
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: bubbleMaxWidth, alignment: .leading)
                }
                processingDots
            }
            .padding(.leading, 10)
        }
    }

    private var spinningDot: some View {
        ZStack {
            Circle()
                .stroke(
                    AngularGradient(
                        gradient: Gradient(colors: [Color.indigo.opacity(0.8), Color.indigo.opacity(0.1)]),
                        center: .center
                    ),
                    lineWidth: 1.5
                )
                .frame(width: 20, height: 20)
                .rotationEffect(.degrees(isSpinning ? 360 : 0))
                .animation(.linear(duration: 0.9).repeatForever(autoreverses: false), value: isSpinning)
            Circle()
                .fill(Color.indigo)
                .frame(width: 7, height: 7)
                .shadow(color: Color.indigo.opacity(0.8), radius: 3)
        }
        .frame(width: 22, height: 22)
        .onAppear { isSpinning = true }
        .onDisappear { isSpinning = false }
    }

    private var processingDots: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("omi")
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(Color.indigo.opacity(0.8))
                .textCase(.uppercase)
                .tracking(0.5)
            HStack(spacing: 4) {
                ForEach(0..<3, id: \.self) { i in
                    Circle()
                        .fill(Color.indigo)
                        .frame(width: 5, height: 5)
                        .opacity(dotIndex == i ? 1.0 : 0.25)
                }
            }
            .task {
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds: 300_000_000)
                    dotIndex = (dotIndex + 1) % 3
                }
            }
        }
        .frame(maxWidth: bubbleMaxWidth, alignment: .leading)
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(bubble(border: Color.indigo.opacity(0.2)))
        .environment(\.colorScheme, .dark)
    }

    // MARK: - Responding

    private var respondingBubble: some View {
        let isNotification = state.phase == .notifying
        let accentColor = isNotification ? Color.orange : Color.indigo
        return VStack(alignment: .leading, spacing: 0) {
            if !state.displayedQuery.isEmpty {
                Text(isNotification ? state.displayedQuery : "\u{201C}\(state.displayedQuery)\u{201D}")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .italic(!isNotification)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.bottom, 6)
                Divider().overlay(Color.white.opacity(0.08))
                    .padding(.bottom, 6)
            }
            Text("omi")
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(accentColor.opacity(0.9))
                .textCase(.uppercase)
                .tracking(0.5)
                .padding(.bottom, 3)
            if state.streamingText.isEmpty {
                blinkingCursor(color: accentColor)
            } else {
                Text(state.streamingText)
                    .font(.system(size: 13))
                    .foregroundColor(.primary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: bubbleMaxWidth, alignment: .leading)
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(bubble(border: accentColor.opacity(0.5)))
        .environment(\.colorScheme, .dark)
    }

    private func blinkingCursor(color: Color) -> some View {
        RoundedRectangle(cornerRadius: 1)
            .fill(color)
            .frame(width: 6, height: 13)
            .opacity(blinkVisible ? 1 : 0)
            .animation(.easeInOut(duration: 0.6).repeatForever(autoreverses: true), value: blinkVisible)
            .onAppear { blinkVisible = false }
            .onDisappear { blinkVisible = true }
    }

    // MARK: - Executing

    private var executingCard: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(Color.indigo)
                .frame(width: 5, height: 5)
            Text("esc · cancel")
                .font(.system(size: 9, design: .monospaced))
                .foregroundColor(.primary.opacity(0.3))
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(bubble(border: Color.indigo.opacity(0.4)))
        .environment(\.colorScheme, .dark)
    }

    // MARK: - Shared

    private func bubble(border: Color) -> some View {
        RoundedRectangle(cornerRadius: 11)
            .fill(Color(red: 12/255, green: 12/255, blue: 18/255).opacity(0.96))
            .overlay(RoundedRectangle(cornerRadius: 11).stroke(border, lineWidth: 1))
    }
}
