import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI
import UniformTypeIdentifiers

/// Data & Privacy › Import data (Flutter `import_history_page`): pick a Limitless export zip, Omi
/// turns it into conversations in the background; past imports with their progress and counts.
struct ImportScreen: View {
    @Environment(SettingsStore.self) private var settings
    @State private var store: ImportStore
    @State private var picking = false
    @State private var started = false

    init(store: ImportStore) {
        _store = State(initialValue: store)
    }

    var body: some View {
        SettingsList {
            Section {
                Button { picking = true } label: {
                    HStack(spacing: DS.Spacing.md) {
                        Image(systemName: "doc.zipper").font(.system(size: 22, weight: .light)).foregroundStyle(DS.Palette.inkSecondary)
                        VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                            Text("Limitless").font(DS.Typography.cardTitle).foregroundStyle(DS.Palette.ink)
                            Text(L("nativeImportLimitlessHint")).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                        }
                        Spacer()
                        if store.isUploading { ProgressView() }
                    }
                }
                .disabled(store.isUploading)
                .accessibilityIdentifier("import.limitless")
                if started {
                    Text(L("nativeImportStarted")).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                } else if let error = store.lastError {
                    Text(error == "tooLarge" ? L("nativeImportTooLarge") : L("nativeImportFailed"))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.live)
                }
            } footer: {
                Text(L("nativeImportFooter"))
            }
            history
        }
        .omiPage(L("nativeSettingsImportHistory"))
        .task { await store.load() }
        .refreshable { await store.load() }
        .onDisappear { store.stopPolling() }
        .fileImporter(isPresented: $picking, allowedContentTypes: [.zip]) { result in
            guard case let .success(url) = result else { return }
            Task {
                started = await store.importZip(at: url, language: settings.spokenLanguage ?? "en")
                if started { DSHaptics.success() }
            }
        }
    }

    @ViewBuilder
    private var history: some View {
        Section(L("nativeImportsSoFar")) {
            switch store.phase {
            case .idle, .loading:
                ProgressView().frame(maxWidth: .infinity)
            case .failed:
                Text(L("couldNotLoadImportHistory")).foregroundStyle(DS.Palette.inkSecondary)
            case .loaded where store.jobs.isEmpty:
                Text(L("noImportsYet")).foregroundStyle(DS.Palette.inkSecondary)
            case .loaded:
                ForEach(store.jobs) { job in
                    ImportJobRow(job: job)
                        .swipeActions {
                            if job.isRunning {
                                Button(L("cancel")) { Task { await store.cancel(job.id) } }
                            } else {
                                Button(L("delete"), role: .destructive) { Task { await store.delete(job.id) } }
                            }
                        }
                }
            }
        }
    }
}

private struct ImportJobRow: View {
    let job: ImportJob

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.xs) {
            HStack {
                Text(status).font(DS.Typography.cardTitle)
                Spacer()
                if let date = job.createdAt {
                    Text(date.formatted(date: .abbreviated, time: .shortened))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkTertiary)
                }
            }
            if job.isRunning, let progress = job.progress {
                ProgressView(value: progress).tint(DS.Palette.ink)
                if let total = job.totalFiles, let done = job.processedFiles {
                    Text(L("nativeImportFiles", String(done), String(total)))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
            }
            if let created = job.created {
                Text(L("nativeImportCounts", String(created), String(job.skipped ?? 0)))
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.inkSecondary)
            }
            if job.status == .failed, let error = job.error {
                Text(error).font(DS.Typography.caption).foregroundStyle(DS.Palette.live).lineLimit(2)
            }
        }
        .padding(.vertical, DS.Spacing.xxs)
    }

    private var status: String {
        switch job.status {
        case .pending: L("statusPending")
        case .processing: L("statusProcessing")
        case .completed: L("statusCompleted")
        case .failed: L("statusFailed")
        case .cancelled: L("nativeImportCancelled")
        }
    }
}
