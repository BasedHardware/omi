import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// My Omi › Recordings on your Omi: one row with how many wait (or how the sync is going); it
/// opens the page with how full the Omi's storage is and the recordings themselves (time, length;
/// play, share, process now, delete). Replaces Flutter's sync page and `device_storage_card`;
/// syncing itself stays automatic.
struct DeviceRecordingsRow: View {
    @Environment(SyncStore.self) private var sync

    var body: some View {
        Section {
            NavigationLink { DeviceRecordingsScreen() } label: {
                HStack {
                    DeviceRow(L("nativeRecordingsOnOmi"), systemImage: "waveform")
                    Spacer(minLength: DS.Spacing.sm)
                    Text(value)
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .monospacedDigit()
                        .contentTransition(.numericText())
                }
            }
            .accessibilityIdentifier("device.recordings")
        }
    }

    /// The count waiting on the Omi; while syncing, how far along it is.
    private var value: String {
        if case let .syncing(progress) = sync.status { return "\(Int(progress * 100))%" }
        return "\(sync.deviceRecordings.count)"
    }
}

/// The recordings on the Omi: the sync line, storage, then each recording.
struct DeviceRecordingsScreen: View {
    @Environment(SyncStore.self) private var sync
    @State private var player = AudioClipPlayer()

    var body: some View {
        OmiGroupedList {
            Section {
                status
                if let storage = sync.deviceStorage { meter(used: Double(storage.usedBytes), free: Double(storage.freeBytes)) }
            }
            Section {
                if sync.deviceRecordings.isEmpty {
                    Text(L("nativeNoRecordingsWaiting"))
                        .font(DS.Typography.callout)
                        .foregroundStyle(DS.Palette.inkSecondary)
                } else {
                    ForEach(sync.deviceRecordings, id: \.filename) { recording in
                        PendingRecordingRow(recording: recording, player: player)
                    }
                    .onDelete { offsets in
                        for filename in offsets.map({ sync.deviceRecordings[$0].filename }) {
                            sync.delete(filename)
                        }
                    }
                }
            }
        }
        .omiPage(L("nativeRecordingsOnOmi"))
        .onDisappear { player.stop() }
    }

    private var status: some View {
        let (text, icon): (String, String) = switch sync.status {
        case let .waiting(seconds):
            (L("nativeOfflineSyncWaiting", DeviceScreen.duration(seconds)), "clock.arrow.circlepath")
        case let .syncing(progress):
            (L("nativeOfflineSyncing", String(Int(progress * 100))), "arrow.triangle.2.circlepath")
        case .synced, .hidden:
            (L("nativeOfflineSynced"), "checkmark.icloud")
        }
        return DeviceRow(text, systemImage: icon)
            .contentTransition(.numericText())
            .accessibilityIdentifier("device.offlineSync")
    }

    /// Used share of the Omi's storage; amber from 80 %, red from 95 % (`device_storage_card`).
    private func meter(used: Double, free: Double) -> some View {
        let total = used + free
        let fraction = total > 0 ? min(1, used / total) : 0
        let tint = fraction >= 0.95 ? DS.Palette.live : fraction >= 0.8 ? DS.Palette.warning : DS.Palette.ink
        return VStack(alignment: .leading, spacing: DS.Spacing.xs) {
            LabeledContent(L("nativeDeviceStorage"), value: L("deviceStoragePercentFull", String(Int((fraction * 100).rounded()))))
            OmiMeterBar(fraction: fraction, tint: tint)
            Text(L("deviceStorageUsedOfTotal", Self.bytes(used), Self.bytes(total)) + " · " + L("deviceStorageFree", Self.bytes(free)))
                .font(DS.Typography.caption)
                .foregroundStyle(DS.Palette.inkSecondary)
            if fraction >= 0.95 {
                Text(L("deviceStorageNearlyFull")).font(DS.Typography.caption).foregroundStyle(DS.Palette.live)
            }
        }
        .padding(.vertical, DS.Spacing.xxs)
    }

    static func bytes(_ count: Double) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(count), countStyle: .file)
    }
}
