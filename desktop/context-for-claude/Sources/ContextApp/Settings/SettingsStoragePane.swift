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
/// **`Expire screenshots` deletes user data permanently** (`I30`), so *switching to it* is not
/// reachable by one click on a radio button. Selecting it parks the choice in
/// `StorageSelection.pending` and opens a confirmation that states exactly what will happen; the
/// radio group shows the parked option as selected so the user can see what they are being asked
/// about, and cancelling puts it back. Only `confirm()` commits.
///
/// **And the confirmation states both bounds, and what survives them.** It is not only a size cap:
/// the sweep expires every screenshot older than `StorageLimit.retentionDays` as well, whatever the
/// threshold says. Copy that mentioned only the threshold made a 200 GB setting on an 8 GB disk look
/// like "nothing will be deleted" while a month-old screenshot was deleted anyway.
///
/// **The footnote carries the disclosure the dialog cannot.** This strategy is now the shipped
/// default (`StorageStrategy.default`), and a default raises no sheet — so the one place a user who
/// never touches this pane can learn that their month-old screenshots are being deleted, and that
/// the text of those moments is not, is the copy standing next to the selected row.
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
                footnote: "The text of everything you have seen and heard is kept forever, and is "
                    + "always searchable. Screenshots are the part that grows without bound, so by "
                    + "default they are deleted once they are \(StorageLimit.retentionDays) days "
                    + "old — or sooner if they pass the threshold. Choose Keep screenshots to hold "
                    + "on to the pictures as well."
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
                        subtitle: "Screenshots are deleted oldest-first once the ones on disk pass "
                            + "this. Screenshots older than \(StorageLimit.retentionDays) days are "
                            + "deleted even when the folder is well under it. Neither bound touches "
                            + "text or transcripts."
                    ) {
                        StorageThresholdStepper(bytes: $store.storageLimitBytes)
                    }
                }
            }

            SettingsSection(title: "Where it lives") {
                SettingsRow(
                    icon: "folder",
                    title: "Data folder",
                    subtitle: AgentPaths.abbreviate(ContextPaths.supportDirectory.path)
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
            isPresented: confirmationPresentation,
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

    /// The confirmation's presentation binding.
    ///
    /// **The setter deliberately does nothing.** It used to call `cancelStorageChange()` on every
    /// dismissal, which made the whole dialog ordering-dependent: SwiftUI is free to write
    /// `isPresented = false` *before* it runs the tapped button's action, and when it did, `cancel()`
    /// had already nulled the `pending` that `confirmStorage()` promotes — so `confirm()` returned
    /// `.unchanged` and the user's deliberate second click silently did nothing at all.
    ///
    /// Cancelling is now only ever the explicit Cancel button, which is also what ⎋ and a click
    /// outside trigger (SwiftUI routes both to the `.cancel`-role action). If some future dismissal
    /// path reached neither button, `pending` survives and the dialog re-presents — the user is asked
    /// again rather than having a destructive strategy committed or silently dropped, which is the
    /// safe direction to be wrong in.
    ///
    /// Exposed rather than inlined so `SettingsTests` can drive both orderings; a binding built
    /// inside `body` is not reachable from a test, which is why the bug was invisible to one.
    var confirmationPresentation: Binding<Bool> {
        Binding(get: { store.storage.isAwaitingConfirmation }, set: { _ in })
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

    // The three confirmation strings are internal rather than private so `SettingsTests` can assert
    // what the sheet actually says. They are the only disclosure the user gets before agreeing to
    // permanent deletion, and copy nothing reads is copy nothing can hold to its claims.
    var confirmationTitle: String {
        switch pending {
        case .limit:
            "Delete screenshots past \(StorageLimit.format(store.storageLimitBytes)) "
                + "or \(StorageLimit.retentionDays) days old?"
        default: ""
        }
    }

    /// Both bounds, and the age one stated as independent of the threshold.
    ///
    /// The sweep runs `enforceRetention(olderThanDays:toFitBytes:)`, which prunes by age *and* by
    /// size. A user who reads only the threshold sentence and picks 200 GB with 8 GB on disk
    /// reasonably concludes nothing will be deleted; a month later their oldest screenshots are gone.
    /// That is permanent deletion of their data and the dialog has to say it before they agree.
    var confirmationMessage: String {
        switch pending {
        case .limit:
            "Two things start happening. Screenshots are deleted oldest-first whenever the frames "
                + "folder passes \(StorageLimit.format(store.storageLimitBytes)), and screenshots older "
                + "than \(StorageLimit.retentionDays) days are deleted whatever the threshold says — "
                + "raising it does not keep them. Deleted screenshots cannot be recovered. What is "
                + "kept is everything you can read: the text of each screen, its window and app, and "
                + "every transcript. Those moments stay searchable; they just lose their picture."
        default: ""
        }
    }

    var confirmationAction: String {
        switch pending {
        case .limit: "Start expiring screenshots"
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
