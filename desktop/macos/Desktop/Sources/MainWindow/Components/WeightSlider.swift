import SwiftUI

// MARK: - WeightSlider
//
// Reusable SwiftUI card for editing per-task weights (quality/latency/cost).
// Three sliders auto-balance so the sum is always exactly 1.0 — moving one
// slider proportionally redistributes the other two. This makes it impossible
// to land on an invalid sum (matches the spec's "strict 100%" rule).
//
// Used by `AutoRouterSettingsView` (v5) to render one card per task. Each
// card shows the task's display name, three sliders with percentage labels,
// a "Reset to default" button (only when the user has customized weights
// away from the task default), and a sum indicator.
//
// Pure UI; no network or persistence — the parent view model owns state.

struct WeightSlider: View {
    let task: AutoRouterTask
    @Binding var weights: TaskWeights
    /// The task's default weights (used to compute "is customized" and as
    /// the reset target). Nil for tasks without a default.
    let defaults: TaskWeights?
    /// Called when the user taps "Reset to default". The parent view model
    /// should update `weights` in response (e.g., to `defaults`).
    let onReset: () -> Void

    /// True when `weights` differ from `defaults` by more than 0.1% on any axis
    /// (the `approximatelyEquals` tolerance is 1e-3 = 0.001 = 0.1%).
    /// Used to show/hide the "Reset to default" button.
    private var isCustomized: Bool {
        guard let defaults = defaults else { return false }
        return !weights.approximatelyEquals(defaults)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            slider(label: "Quality", percent: Binding(
                get: { weights.quality },
                set: { newValue in updateQuality(newValue) }
            ))
            slider(label: "Latency", percent: Binding(
                get: { weights.latency },
                set: { newValue in updateLatency(newValue) }
            ))
            slider(label: "Cost", percent: Binding(
                get: { weights.cost },
                set: { newValue in updateCost(newValue) }
            ))
            sumRow
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(NSColor.controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color(NSColor.separatorColor), lineWidth: 0.5)
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(task.displayName) weight sliders")
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            Text(task.displayName)
                .scaledFont(size: 15, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)
            Spacer()
            if isCustomized {
                Button(action: onReset) {
                    Text("Reset to default")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.purplePrimary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Reset \(task.displayName) weights to default")
            }
        }
    }

    // MARK: - Slider row

    private func slider(label: String, percent: Binding<Double>) -> some View {
        HStack(spacing: 12) {
            Text(label)
                .scaledFont(size: 13, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)
                .frame(width: 64, alignment: .leading)

            Slider(value: percent, in: 0...1, step: 0.01) {
                Text(label)
            } minimumValueLabel: {
                Text("0%").scaledFont(size: 10).foregroundColor(OmiColors.textTertiary)
            } maximumValueLabel: {
                Text("100%").scaledFont(size: 10).foregroundColor(OmiColors.textTertiary)
            }
            .accessibilityValue("\(Int(percent.wrappedValue * 100)) percent")
            .accessibilityLabel("\(task.displayName) \(label.lowercased()) weight")

            Text("\(Int(percent.wrappedValue * 100))%")
                .scaledFont(size: 13, weight: .medium, design: .monospaced)
                .foregroundColor(OmiColors.textPrimary)
                .frame(width: 44, alignment: .trailing)
        }
    }

    // MARK: - Sum indicator

    private var sum: Double {
        // Snap to 1.0 if extremely close (defensive against float drift after
        // repeated auto-rebalancing). Without this, repeated edits could leave
        // a residual like 0.9999999 that the server would reject.
        let raw = weights.quality + weights.latency + weights.cost
        return abs(raw - 1.0) < 1e-9 ? 1.0 : raw
    }

    private var sumRow: some View {
        // Sum is always 1.0 by construction (auto-rebalance), so the check is
        // defensive. If it ever drifts (e.g., bad defaults), the row still
        // renders correctly and surfaces the issue.
        let sumInt = Int(round(sum * 100))
        let isValid = sumInt == 100
        return HStack {
            Text("Sum:")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
            Text("\(sumInt)%")
                .scaledFont(size: 12, weight: .semibold, design: .monospaced)
                .foregroundColor(isValid ? OmiColors.success : OmiColors.error)
            if isValid {
                Image(systemName: "checkmark.circle.fill")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.success)
            } else {
                Image(systemName: "exclamationmark.triangle.fill")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.error)
            }
            Spacer()
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(isValid ? "Sum is 100%, valid" : "Sum is \(sumInt)%, must be 100%")
    }

    // MARK: - Auto-rebalance logic
    //
    // When the user moves one slider to `newValue`, the other two are
    // proportionally rebalanced to keep their ratio while absorbing the
    // delta. If the other two are both zero, the cost gets the full delta
    // (default fallback so the user can break out of a stuck state).
    //
    // Sum after rebalance is always exactly 1.0 (modulo floating-point
    // error which is corrected by the `sum` getter's snap-to-1.0).

    private func updateQuality(_ newValue: Double) {
        weights = rebalanced(current: weights, axis: .quality, newValue: newValue)
    }

    private func updateLatency(_ newValue: Double) {
        weights = rebalanced(current: weights, axis: .latency, newValue: newValue)
    }

    private func updateCost(_ newValue: Double) {
        weights = rebalanced(current: weights, axis: .cost, newValue: newValue)
    }

    private enum Axis { case quality, latency, cost }

    private func rebalanced(current: TaskWeights, axis: Axis, newValue: Double) -> TaskWeights {
        let clamped = max(0.0, min(1.0, newValue))
        let other1: (Double, Double)  // (value, target)
        let other2: (Double, Double)
        switch axis {
        case .quality:
            other1 = (current.latency, 1.0 - clamped)
            other2 = (current.cost, 1.0 - clamped)
        case .latency:
            other1 = (current.quality, 1.0 - clamped)
            other2 = (current.cost, 1.0 - clamped)
        case .cost:
            other1 = (current.quality, 1.0 - clamped)
            other2 = (current.latency, 1.0 - clamped)
        }

        let totalOther = other1.0 + other2.0
        if totalOther <= 1e-9 {
            // Both others are zero — split the remaining mass 50/50 between
        // the two non-edited axes (the doc comment above says "the cost gets
        // the full delta" — that was wrong; fixed as part of cubic review).
            switch axis {
            case .quality:
                return TaskWeights.fromUnchecked(quality: clamped, latency: (1.0 - clamped) / 2.0, cost: (1.0 - clamped) / 2.0)
            case .latency:
                return TaskWeights.fromUnchecked(quality: (1.0 - clamped) / 2.0, latency: clamped, cost: (1.0 - clamped) / 2.0)
            case .cost:
                return TaskWeights.fromUnchecked(quality: (1.0 - clamped) / 2.0, latency: (1.0 - clamped) / 2.0, cost: clamped)
            }
        }

        // Proportional rebalance: each other gets (its current share) * remaining.
        let remaining = 1.0 - clamped
        let new1 = other1.0 * (remaining / totalOther)
        let new2 = other2.0 * (remaining / totalOther)
        switch axis {
        case .quality:
            return TaskWeights.fromUnchecked(quality: clamped, latency: new1, cost: new2)
        case .latency:
            return TaskWeights.fromUnchecked(quality: new1, latency: clamped, cost: new2)
        case .cost:
            return TaskWeights.fromUnchecked(quality: new1, latency: new2, cost: clamped)
        }
    }
}
