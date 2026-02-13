import SwiftUI

/// Fullscreen overlay celebration when a goal is completed
struct GoalCelebrationView: View {
    @State private var showCelebration = false
    @State private var completedGoal: Goal?
    @State private var phase: CelebrationPhase = .idle

    enum CelebrationPhase {
        case idle, dim, confetti, text, fadeOut
    }

    var body: some View {
        ZStack {
            if showCelebration {
                // Dim overlay
                Color.black.opacity(phase == .dim ? 0.4 : (phase == .confetti || phase == .text ? 0.5 : 0))
                    .ignoresSafeArea()
                    .allowsHitTesting(false)

                // Confetti burst
                if phase == .confetti || phase == .text {
                    GoalConfettiView()
                        .allowsHitTesting(false)
                        .transition(.opacity)
                }

                // Celebration text
                if phase == .text, let goal = completedGoal {
                    VStack(spacing: 16) {
                        Text("Goal Completed!")
                            .font(.system(size: 32, weight: .bold))
                            .foregroundStyle(
                                LinearGradient(
                                    colors: [.yellow, .orange, .yellow],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                            .shadow(color: .yellow.opacity(0.6), radius: 12)

                        Text(goal.title)
                            .font(.system(size: 18, weight: .medium))
                            .foregroundColor(.white)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 40)

                        Text("\(Int(goal.targetValue)) \(goal.unit ?? "") reached")
                            .font(.system(size: 14))
                            .foregroundColor(.white.opacity(0.7))
                    }
                    .transition(.scale(scale: 0.7).combined(with: .opacity))
                }
            }
        }
        .animation(.easeInOut(duration: 0.3), value: phase)
        .onReceive(NotificationCenter.default.publisher(for: .goalCompleted)) { notification in
            if let goal = notification.object as? Goal {
                triggerCelebration(goal: goal)
            }
        }
    }

    private func triggerCelebration(goal: Goal) {
        completedGoal = goal
        showCelebration = true

        log("CELEBRATION: Goal '\(goal.title)' completed, starting animation")

        // Phase 1: Dim (immediate)
        withAnimation(.easeOut(duration: 0.3)) {
            phase = .dim
        }

        // Phase 2: Confetti burst (after 0.3s)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
            withAnimation(.easeOut(duration: 0.3)) {
                phase = .confetti
            }
        }

        // Phase 3: Text appears (after 0.8s)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            withAnimation(.spring(response: 0.5, dampingFraction: 0.7)) {
                phase = .text
            }
        }

        // Phase 4: Fade out (after 3.0s)
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
            withAnimation(.easeOut(duration: 0.5)) {
                phase = .fadeOut
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                showCelebration = false
                phase = .idle
                completedGoal = nil
            }
        }
    }
}

// MARK: - Goal Confetti View
/// Large confetti burst for goal completion celebration
struct GoalConfettiView: View {
    @State private var animate = false
    @State private var fadeOut = false

    private let particleConfigs: [(color: Color, size: CGFloat, angle: Double, distance: CGFloat, rotation: Double, isRect: Bool)] = {
        let colors: [Color] = [
            .yellow, Color(red: 1.0, green: 0.84, blue: 0), // Gold
            Color(red: 0.133, green: 0.773, blue: 0.369), // Green
            Color(red: 0.2, green: 0.6, blue: 1.0), // Blue
            .pink, .orange, .cyan, .mint,
            OmiColors.purplePrimary, OmiColors.purplePrimary.opacity(0.7)
        ]
        return (0..<40).map { _ in
            (
                color: colors.randomElement()!,
                size: CGFloat.random(in: 4...10),
                angle: Double.random(in: 0...(2 * .pi)),
                distance: CGFloat.random(in: 80...300),
                rotation: Double.random(in: 0...1080),
                isRect: Bool.random()
            )
        }
    }()

    var body: some View {
        GeometryReader { geo in
            let cx = geo.size.width / 2
            let cy = geo.size.height / 2

            ZStack {
                ForEach(0..<particleConfigs.count, id: \.self) { i in
                    let p = particleConfigs[i]
                    Group {
                        if p.isRect {
                            RoundedRectangle(cornerRadius: 1.5)
                                .fill(p.color)
                        } else {
                            Circle()
                                .fill(p.color)
                        }
                    }
                    .frame(width: p.size, height: p.size * (p.isRect ? 2.5 : 1))
                    .rotationEffect(.degrees(animate ? p.rotation : 0))
                    .offset(
                        x: animate ? cos(p.angle) * p.distance : 0,
                        y: animate ? sin(p.angle) * p.distance - 40 : 0
                    )
                    .scaleEffect(animate ? (fadeOut ? 0.1 : 1.0) : 0.1)
                    .opacity(fadeOut ? 0 : 1)
                    .position(x: cx, y: cy)
                }
            }
        }
        .onAppear {
            withAnimation(.easeOut(duration: 0.8)) {
                animate = true
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                withAnimation(.easeOut(duration: 0.8)) {
                    fadeOut = true
                }
            }
        }
    }
}
