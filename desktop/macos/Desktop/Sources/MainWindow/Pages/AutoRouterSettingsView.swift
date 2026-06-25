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
                    onReset: { viewModel.resetToDefaults(for: task) }
                )
            }
        }
    }

    // MARK: - Reset all

    private var resetAllSection: some View {
        // The "Reset all overrides" button is enabled only when at least
        // one task has a custom override. Otherwise it's a no-op.
        let hasAnyOverride = AutoRouterTask.allCases.contains { viewModel.isCustomized(for: $0) }
        return HStack {
            Spacer()
            Button(action: { viewModel.resetAllToDefaults() }) {
                Text("Reset all overrides")
                    .scaledFont(size: 13, weight: .medium)
            }
            .buttonStyle(.bordered)
            .disabled(!hasAnyOverride)
            .opacity(hasAnyOverride ? 1.0 : 0.5)
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
        switch viewModel.errorState {
        case .unauthorized:
            return "Sign in to save preferences."
        case .invalidWeights:
            return "Server rejected the weight values. Try adjusting the sliders."
        case .unavailable:
            return "Server is temporarily unavailable. Your changes are still on this screen."
        case .transport:
            return "Network error. Your changes are still on this screen."
        case .invalidWeight, .invalidURL, .invalidResponse, .decodingFailed, .serverError:
            return "Something went wrong. Try again."
        case .none:
            return ""
        }
    }
}

#if DEBUG
#Preview {
    AutoRouterSettingsView()
        .frame(width: 800, height: 800)
        .preferredColorScheme(.dark)
}
#endif
