import SwiftUI

// MARK: - ModelPicker
//
// Reusable SwiftUI dropdown for selecting which model to use for a task.
// The picker offers:
//   - "Auto (recommended)" — default; let the auto-router choose
//   - Each candidate model with its composite score
//
// Selection is bound to a `String?` (nil = Auto). When the user picks a
// specific model, the binding is set to the model ID; when they pick
// "Auto", the binding is set to nil. The parent view model writes through
// to `UserPrefs.modelOverrides[task]` via the existing debounced save path.
//
// Layout: rendered below the weight sliders inside each WeightSlider card.
//
// Accessibility:
//   - The picker label includes the task name
//   - The currently-active option shows a checkmark
//   - Each option's score is announced as part of the accessibility label

struct ModelPicker: View {
    /// task name (e.g., "ptt_response") — used for accessibility labels
    let task: AutoRouterTask

    /// nil = Auto (recommended); non-nil = user's pinned model ID
    @Binding var modelId: String?

    /// All candidates for this task, sorted by score desc (best first).
    /// Empty array → only "Auto" option shown.
    let candidates: [Candidate]

    /// Called when the user picks a specific model or switches to Auto.
    /// The parent view model uses this to update UserPrefs.modelOverrides.
    let onSelect: (String?) -> Void

    /// True when the user has overridden Auto (modelId is non-nil and
    /// matches a known candidate). Used to show the "Reset" hint.
    private var isOverridden: Bool {
        guard let id = modelId else { return false }
        return candidates.contains { $0.id == id }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text("Model")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.textSecondary)
                    .frame(width: 64, alignment: .leading)

                Picker("", selection: Binding(
                    get: { modelId ?? "__auto__" },
                    set: { newValue in
                        if newValue == "__auto__" {
                            modelId = nil
                            onSelect(nil)
                        } else {
                            modelId = newValue
                            onSelect(newValue)
                        }
                    }
                )) {
                    // Auto (recommended) option — always shown.
                    HStack(spacing: 6) {
                        Image(systemName: "wand.and.stars")
                            .scaledFont(size: 10)
                            .foregroundColor(OmiColors.purplePrimary)
                        Text("Auto (recommended)")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textPrimary)
                        if modelId == nil {
                            Image(systemName: "checkmark")
                                .scaledFont(size: 10)
                                .foregroundColor(OmiColors.success)
                        }
                    }
                    .tag("__auto__")
                    .accessibilityLabel("\(task.displayName) model: Auto (recommended)")

                    // Each candidate — only shown when we have them.
                    // (Empty array = the /candidates fetch hasn't returned
                    //  yet; the picker shows just Auto so the user has
                    //  something to interact with.)
                    ForEach(candidates) { candidate in
                        HStack(spacing: 6) {
                            Text(candidate.id)
                                .scaledFont(size: 12)
                                .foregroundColor(OmiColors.textPrimary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                            Text(String(format: "%.2f", candidate.total))
                                .scaledFont(size: 11, design: .monospaced)
                                .foregroundColor(OmiColors.textTertiary)
                            if modelId == candidate.id {
                                Image(systemName: "checkmark")
                                    .scaledFont(size: 10)
                                    .foregroundColor(OmiColors.success)
                            }
                        }
                        .tag(candidate.id)
                        .accessibilityLabel(
                            "\(task.displayName) model: \(candidate.id), "
                            + "score \(String(format: "%.2f", candidate.total))"
                        )
                    }
                }
                .pickerStyle(.menu)
                .accessibilityElement(children: .contain)
                .accessibilityLabel("\(task.displayName) model picker")

                Spacer()
            }
        }
    }
}

#if DEBUG
#Preview {
    struct PreviewWrapper: View {
        @State var selected: String? = nil
        let candidates = [
            Candidate(
                id: "gemini-1-5-flash-8b-exp",
                provider: "google",
                scores: .init(quality: 0.75, latency: 0.95, cost: 0.90),
                total: 0.9375
            ),
            Candidate(
                id: "gpt-realtime-2",
                provider: "openai",
                scores: .init(quality: 0.85, latency: 0.80, cost: 0.60),
                total: 0.7925
            ),
            Candidate(
                id: "claude-sonnet-4-6",
                provider: "anthropic",
                scores: .init(quality: 0.92, latency: 0.50, cost: 0.30),
                total: 0.5110
            ),
        ]
        var body: some View {
            VStack(spacing: 20) {
                ModelPicker(
                    task: .pttResponse,
                    modelId: $selected,
                    candidates: candidates,
                    onSelect: { _ in }
                )
                Text("Selected: \(selected ?? "Auto")")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
            }
            .padding(24)
            .frame(width: 500)
        }
    }
    return PreviewWrapper()
        .preferredColorScheme(.dark)
}
#endif
