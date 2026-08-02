import AppKit
import ContextCore
import SwiftUI

/// Storage: the measured usage, and a strategy for when the disk fills up.
///
/// Two things are load-bearing here and neither is cosmetic.
///
/// **The usage figure is measured** (`I27`). `StorageMeasurement` walks the real support directory and
/// adds up allocated sizes. Nothing on this pane multiplies a frame count by an average.
///
/// **`Limit` deletes user data permanently** (`I30`), and `Compress` re-encodes it lossily, so neither
/// is reachable by one click on a radio button. Selecting either parks the choice in
/// `StorageSelection.pending` and opens a confirmation that states exactly what will happen; the radio
/// group shows the parked option as selected so the user can see what they are being asked about, and
/// cancelling puts it back. Only `confirm()` commits.
struct SettingsStoragePane: View {
    @ObservedObject var store: SettingsStore

    @State private var usage: StorageUsage?
    @State private var isMeasuring = false

    var body: some View {
        SettingsPaneScroll {
            VStack(alignment: .leading, spacing: 6) {
                if let usage {
                    SettingsHeadline(value: usage.formattedTotal, caption: store.storageLimitSummary)
                    Text(breakdown(usage))
                        .font(.system(size: 11))
                        .foregroundStyle(Ink.secondary)
                        .padding(.horizontal, 1)
                } else {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Measuring what is on disk…")
                            .font(.system(size: 12))
                            .foregroundStyle(Ink.secondary)
                    }
                    .frame(height: 44)
                }
            }
            .padding(.horizontal, 4)

            SettingsSection(
                title: "Storage management",
                footnote: "Context for Claude keeps everything. Pick a strategy if your disk is filling up."
            ) {
                ForEach(Array(StorageStrategy.allCases.enumerated()), id: \.element.id) { index, strategy in
                    if index > 0 { SettingsRowDivider() }
                    SettingsRadioRow(
                        symbol: strategy.symbol,
                        title: strategy.title,
                        subtitle: strategy.subtitle,
                        isSelected: store.storage.highlighted == strategy,
                        isDestructive: strategy.destroysExistingData
                    ) {
                        Sound.effect(.click)
                        store.selectStorage(strategy)
                    }
                }

                if store.storage.strategy == .limit {
                    SettingsRowDivider()
                    SettingsRow(
                        icon: "gauge.with.dots.needle.33percent",
                        title: "Threshold",
                        subtitle: "Recordings are deleted oldest-first once the frames on disk pass this."
                    ) {
                        StorageThresholdStepper(bytes: $store.storageLimitBytes)
                    }
                }
            }

            SettingsSection(title: "Where it lives") {
                SettingsRow(
                    icon: "folder",
                    title: "Data folder",
                    subtitle: AgentDetector.abbreviate(ContextPaths.supportDirectory.path)
                ) {
                    Button("Reveal") {
                        Sound.effect(.click)
                        NSWorkspace.shared.selectFile(
                            nil, inFileViewerRootedAtPath: ContextPaths.supportDirectory.path)
                    }
                    .controlSize(.small)
                }

                SettingsRowDivider()

                SettingsRow(
                    icon: "arrow.clockwise",
                    title: "Recalculate",
                    subtitle: usage?.isPartial == true
                        ? "The last walk could not read part of the folder, so the figure above is a floor."
                        : "Walks the folder again and adds up what is actually there."
                ) {
                    Button(isMeasuring ? "Measuring…" : "Measure") { measure() }
                        .controlSize(.small)
                        .disabled(isMeasuring)
                }
            }
        }
        .task { if usage == nil { measure() } }
        // The confirmation. `isPresented` is driven by the *model*, so there is no way to reach a
        // committed destructive strategy without this sheet having been answered.
        .confirmationDialog(
            confirmationTitle,
            isPresented: Binding(
                get: { store.storage.isAwaitingConfirmation },
                set: { presented in if !presented { store.cancelStorageChange() } }),
            titleVisibility: .visible
        ) {
            Button(confirmationAction, role: .destructive) {
                Sound.effect(.click)
                store.confirmStorage()
            }
            Button("Cancel", role: .cancel) { store.cancelStorageChange() }
        } message: {
            Text(confirmationMessage)
        }
    }

    // MARK: - Measuring

    private func measure() {
        isMeasuring = true
        Task {
            // Off the main actor: a full walk of a multi-gigabyte frames tree is thousands of stats.
            let measured = await Task.detached(priority: .utility) {
                StorageMeasurement.measure()
            }.value
            usage = measured
            isMeasuring = false
        }
    }

    private func breakdown(_ usage: StorageUsage) -> String {
        let parts = [
            "\(StorageLimit.format(usage.frameBytes)) of screenshots",
            "\(StorageLimit.format(usage.databaseBytes)) of text and transcripts",
            "\(usage.fileCount) files",
        ]
        let measured = parts.joined(separator: " · ")
        return usage.isPartial ? measured + " · part of the folder could not be read" : measured
    }

    // MARK: - Confirmation copy

    private var pending: StorageStrategy? {
        store.storage.isAwaitingConfirmation ? store.storage.highlighted : nil
    }

    private var confirmationTitle: String {
        switch pending {
        case .limit: "Delete recordings once \(StorageLimit.format(store.storageLimitBytes)) is reached?"
        case .compress: "Compress older recordings?"
        default: ""
        }
    }

    private var confirmationMessage: String {
        switch pending {
        case .limit:
            "Screenshots will be deleted oldest-first whenever the frames folder passes "
                + "\(StorageLimit.format(store.storageLimitBytes)). Deleted recordings cannot be recovered. "
                + "Transcripts are never deleted by this."
        case .compress:
            "Older screenshots will be re-encoded at a lower quality to reclaim space. "
                + "The original detail cannot be recovered."
        default: ""
        }
    }

    private var confirmationAction: String {
        switch pending {
        case .limit: "Turn on storage limit"
        case .compress: "Turn on compression"
        default: "Continue"
        }
    }
}

/// The threshold control: a stepper in whole gigabytes, clamped by `StorageLimit`.
struct StorageThresholdStepper: View {
    @Binding var bytes: Int64

    var body: some View {
        HStack(spacing: 6) {
            Text(StorageLimit.format(bytes))
                .font(.system(size: 12, weight: .medium, design: .monospaced))
                .foregroundStyle(Ink.primary)
                .frame(minWidth: 58, alignment: .trailing)
            Stepper(
                "",
                value: Binding(
                    get: { bytes },
                    set: { bytes = StorageLimit.clamp($0) }),
                in: StorageLimit.minimumBytes...StorageLimit.maximumBytes,
                // `Int64.Stride` is `Int`, and a 1 GB step fits it on every 64-bit Mac this ships to.
                step: Int(StorageLimit.stepBytes)
            )
            .labelsHidden()
        }
        .accessibilityLabel(Text("Storage threshold"))
        .accessibilityValue(Text(StorageLimit.format(bytes)))
    }
}
