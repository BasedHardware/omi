import SwiftUI

// MARK: - AutoRouterSettingsView
//
// Settings → Auto-router page. Lets the user override per-task weights
// (quality / latency / cost) for all 5 task types supported by the
// auto-router framework.
//
// Architecture:
//   - Owns an `AutoRouterSettingsViewModel` (`@StateObject`, lives for the
//     page's lifetime in the navigation stack)
//   - Renders one `WeightSlider` per task (5 cards)
//   - "Reset all overrides" clears every override in one tap
//   - Loading state: spinner during initial `load()` (prefs + task defaults)
//   - Error state: inline banner with retry button when save fails
//
// Persistence:
//   - All writes go through the view model → UserPrefsClient → Firestore
//     (backend v4). The view itself owns no state beyond a `selectedTask`
//     for potential future "highlight this task in /pick" cross-linking.
//
// Pure UI — no business logic here; all state changes go through the
// view model so the debounced save path stays correct.

struct AutoRouterSettingsView: View {
    /// Owns prefs state + debounced save. `@StateObject` so it survives
    /// SwiftUI re-renders without being recreated (which would lose pending
    /// debounce timers).
    @StateObject private var viewModel = AutoRouterSettingsViewModel()

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                introSection
                if viewModel.isLoading {
                    loadingSection
                } else {
                    taskCardsSection
                    resetAllSection
                    saveStatusSection
                }
            }
            .padding(24)
            .frame(maxWidth: 800, alignment: .leading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(OmiColors.backgroundPrimary)
        .navigationTitle("Auto-router")
        // `.task` (not `.onAppear`) — runs once per view lifecycle, and is
        // cancelled when the view goes away (matches the spec's preferred
        // caching behavior).
        .task {
            await viewModel.load()
        }
    }

    // MARK: - Intro

    private var introSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Auto-router picks the best model for each task")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
            Text("Adjust how much you value quality, latency, and cost for each task. Sliders auto-balance to 100%. Changes save automatically.")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
        }
    }

    // MARK: - Loading

    private var loadingSection: some View {
        HStack(spacing: 12) {
            ProgressView().scaleEffect(0.7)
            Text("Loading preferences…")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textSecondary)
            Spacer()
        }
        .padding(.vertical, 40)
        .frame(maxWidth: .infinity)
    }

    // MARK: - Task cards

    private var taskCardsSection: some View {
        VStack(spacing: 16) {
            ForEach(AutoRouterTask.allCases, id: \.self) { task in
                WeightSlider(
                    task: task,
                    weights: viewModel.binding(for: task),
                    defaults: viewModel.taskDefaults[task],
                    onReset: {
                        // v6: "Reset to default" resets BOTH weight overrides
                        // AND model overrides for this task.
                        viewModel.resetToDefaults(for: task)
                        viewModel.setModelOverride(nil, for: task)
                    },
                    // v6: model picker state — bound to viewModel's modelOverrides.
                    modelId: viewModel.bindingForModelOverride(for: task),
                    candidates: viewModel.candidatesByTask[task] ?? [],
                    onModelSelect: { modelId in
                        viewModel.setModelOverride(modelId, for: task)
                    }
                )
                // Lazy-load candidates when this card appears (v6).
                .task {
                    await viewModel.loadCandidates(for: task)
                }
            }
        }
    }

    // MARK: - Reset all

    private var resetAllSection: some View {
        // v6: Two reset buttons side-by-side.
        //   - "Reset all overrides" clears every weight override
        //   - "Reset all model overrides" clears every model override
        // Both are independent (clearing weights doesn't touch models and vice versa).
        let hasAnyWeightOverride = AutoRouterTask.allCases.contains { viewModel.isCustomized(for: $0) }
        let hasAnyModelOverride = AutoRouterTask.allCases.contains { viewModel.hasModelOverride(for: $0) }
        return HStack(spacing: 12) {
            Spacer()
            Button(action: { viewModel.clearAllModelOverrides() }) {
                Text("Reset all model overrides")
                    .scaledFont(size: 13, weight: .medium)
            }
            .buttonStyle(.bordered)
            .disabled(!hasAnyModelOverride)
            .opacity(hasAnyModelOverride ? 1.0 : 0.5)

            Button(action: { viewModel.resetAllToDefaults() }) {
                Text("Reset all overrides")
                    .scaledFont(size: 13, weight: .medium)
            }
            .buttonStyle(.bordered)
            .disabled(!hasAnyWeightOverride)
            .opacity(hasAnyWeightOverride ? 1.0 : 0.5)
        }
        .padding(.top, 8)
    }

    // MARK: - Save status

    @ViewBuilder
    private var saveStatusSection: some View {
        switch viewModel.saveStatus {
        case .idle:
            EmptyView()
        case .saving:
            HStack(spacing: 8) {
                ProgressView().scaleEffect(0.6)
                Text("Saving…")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                Spacer()
            }
        case .saved:
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.success)
                Text("Saved")
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                Spacer()
            }
        case .failed:
            errorBanner
        }
    }

    private var errorBanner: some View {
        HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.error)
            VStack(alignment: .leading, spacing: 2) {
                Text("Couldn't save preferences")
                    .scaledFont(size: 12, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Text(errorDescription)
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)
            }
            Spacer()
            Button(action: { viewModel.retrySave() }) {
                Text("Retry")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.purplePrimary)
            }
            .buttonStyle(.plain)
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(OmiColors.error.opacity(0.1))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(OmiColors.error.opacity(0.3), lineWidth: 0.5)
        )
    }

    private var errorDescription: String {
        viewModel.errorState?.userMessage ?? ""
    }
}

#if DEBUG
#Preview {
    AutoRouterSettingsView()
        .frame(width: 800, height: 800)
        .preferredColorScheme(.dark)
}
#endif
