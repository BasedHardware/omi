import SwiftUI

/// Animated audio level waveform visualization
/// Shows 12 vertical bars that scale with audio level
struct AudioLevelWaveformView: View {
    let level: Float
    let barCount: Int
    let isActive: Bool

    init(level: Float, barCount: Int = 12, isActive: Bool = true) {
        self.level = level
        self.barCount = barCount
        self.isActive = isActive
    }

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0..<barCount, id: \.self) { index in
                BarView(
                    level: level,
                    index: index,
                    totalBars: barCount,
                    isActive: isActive
                )
            }
        }
        .frame(height: 32)  // Fixed height container
    }
}

private struct BarView: View {
    let level: Float
    let index: Int
    let totalBars: Int
    let isActive: Bool

    private let minHeight: CGFloat = 6
    private let maxHeight: CGFloat = 32
    private let barWidth: CGFloat = 3

    /// Calculate height based on audio level with some variation per bar
    private var barHeight: CGFloat {
        guard isActive else { return minHeight }

        // Apply sensitivity boost - amplify low levels more
        let boostedLevel = pow(CGFloat(level), 0.5) * 2.5  // Square root makes low levels more visible
        let clampedLevel = min(1.0, boostedLevel)

        // Create variation across bars (center bars taller)
        let centerOffset = abs(CGFloat(index) - CGFloat(totalBars - 1) / 2.0) / (CGFloat(totalBars) / 2.0)
        let variation = 1.0 - (centerOffset * 0.4) // Center bars up to 40% taller

        // Scale with audio level
        let scaledLevel = clampedLevel * variation

        // Add some randomness for organic feel
        let randomVariation = CGFloat.random(in: 0.85...1.15)

        let height = minHeight + (maxHeight - minHeight) * scaledLevel * randomVariation
        return max(minHeight, min(maxHeight, height))
    }

    private var barColor: Color {
        guard isActive else { return OmiColors.textTertiary.opacity(0.5) }

        // Color intensity based on level
        let boostedLevel = min(1.0, pow(CGFloat(level), 0.5) * 2.5)
        if boostedLevel > 0.6 {
            return OmiColors.purplePrimary
        } else if boostedLevel > 0.2 {
            return OmiColors.textPrimary
        } else if boostedLevel > 0.02 {
            return OmiColors.textSecondary
        }
        return OmiColors.textTertiary.opacity(0.5)
    }

    var body: some View {
        RoundedRectangle(cornerRadius: 1.5)
            .fill(barColor)
            .frame(width: barWidth, height: barHeight)
            .animation(.easeOut(duration: 0.08), value: level)
    }
}

#Preview {
    VStack(spacing: 20) {
        // Idle state
        HStack {
            Text("Idle:")
                .foregroundColor(.white)
            AudioLevelWaveformView(level: 0.0, isActive: false)
        }

        // Low level
        HStack {
            Text("Low:")
                .foregroundColor(.white)
            AudioLevelWaveformView(level: 0.1)
        }

        // Medium level
        HStack {
            Text("Medium:")
                .foregroundColor(.white)
            AudioLevelWaveformView(level: 0.4)
        }

        // High level
        HStack {
            Text("High:")
                .foregroundColor(.white)
            AudioLevelWaveformView(level: 0.8)
        }
    }
    .padding()
    .background(OmiColors.backgroundPrimary)
}
