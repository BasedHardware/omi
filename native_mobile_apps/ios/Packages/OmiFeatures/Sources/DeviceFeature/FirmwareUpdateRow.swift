import OmiComponents
import OmiDesign
import OmiService
import SwiftUI
#if canImport(UIKit)
    import UIKit
#endif

/// The firmware update in My Devices: one row under Firmware, only when there is something to say
/// (an update on offer, one running, or how the last one ended). The update starts only from the
/// confirmation; below 20 % battery it is refused before asking.
struct FirmwareUpdateRow: View {
    @Environment(DeviceStore.self) private var devices
    @Environment(FirmwareStore.self) private var firmware
    @State private var confirming = false
    @State private var refusedForBattery = false

    var body: some View {
        Group {
            switch firmware.phase {
            case .idle:
                if let release = firmware.available { offer(release.version) }
            case .downloading:
                progress(L("downloadingFirmware"), value: nil, keepOpen: true)
            case let .installing(value):
                progress(L("installingFirmware"), value: value, keepOpen: true)
            case .restarting:
                progress(L("otaRebooting", devices.paired?.name ?? "Omi"), value: nil, keepOpen: false)
            case let .finished(version):
                Label(L("nativeFirmwareUpdated", version), systemImage: "checkmark.circle.fill")
                    .foregroundStyle(DS.Palette.success)
            case let .failed(failure):
                failed(failure)
            }
        }
        .alert(L("nativeFirmwareUpdateConfirmTitle"), isPresented: $confirming) {
            Button(L("nativeFirmwareUpdateStart")) { Task { await firmware.install() } }
            Button(L("cancel"), role: .cancel) {}
        } message: {
            Text(L("nativeFirmwareUpdateConfirmBody"))
        }
        .alert(L("nativeFirmwareBatteryTooLow"), isPresented: $refusedForBattery) {
            Button(L("ok"), role: .cancel) {}
        } message: {
            Text(L("nativeFirmwareBatteryTooLowBody"))
        }
        .onChange(of: isTransferring, initial: true) { keepScreenOn($1) }
        .onDisappear { keepScreenOn(false) }
    }

    private func offer(_ version: String) -> some View {
        HStack {
            Text(L("nativeFirmwareUpdateAvailable", version))
            Spacer()
            Button(L("update"), action: requestUpdate)
                .buttonStyle(.omiPill)
                .disabled(devices.connection != .connected)
                .accessibilityIdentifier("device.firmware.update")
        }
    }

    private func requestUpdate() {
        guard let battery = devices.battery, battery >= FirmwareStore.minimumBattery else {
            refusedForBattery = true
            return
        }
        confirming = true
    }

    private func progress(_ title: String, value: Double?, keepOpen: Bool) -> some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            HStack {
                Text(title)
                Spacer()
                if let value {
                    Text(value, format: .percent.precision(.fractionLength(0)))
                        .monospacedDigit()
                        .foregroundStyle(DS.Palette.inkSecondary)
                } else {
                    ProgressView()
                }
            }
            if let value { ProgressView(value: value).tint(DS.Palette.ink) }
            if keepOpen {
                Label(L("nativeFirmwareKeepAppOpen"), systemImage: "exclamationmark.triangle")
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.warning)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func failed(_ failure: FirmwareStore.Failure) -> some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            Label(failureTitle(failure), systemImage: "exclamationmark.triangle")
                .foregroundStyle(DS.Palette.warning)
            Text(failureBody(failure))
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.inkSecondary)
            HStack {
                if firmware.available != nil, failure == .download || failure == .install {
                    Button(L("tryAgain"), action: requestUpdate)
                        .buttonStyle(.omiPillSubtle)
                        .disabled(devices.connection != .connected)
                }
                Button(L("ok")) { firmware.dismissResult() }
                    .buttonStyle(.omiPillSubtle)
            }
        }
    }

    private var isTransferring: Bool {
        switch firmware.phase {
        case .downloading, .installing: true
        default: false
        }
    }

    private func failureTitle(_ failure: FirmwareStore.Failure) -> String {
        switch failure {
        case .lowBattery: L("nativeFirmwareBatteryTooLow")
        case .notConnected: L("nativeFirmwareConnectFirst")
        case .download, .install: L("firmwareUpdateFailedTitle")
        }
    }

    private func failureBody(_ failure: FirmwareStore.Failure) -> String {
        switch failure {
        case .lowBattery: L("nativeFirmwareBatteryTooLowBody")
        case .notConnected: L("nativeOmiOnAndNearby")
        case .download: L("firmwareDownloadFailedMessage")
        case .install: L("firmwareUpdateFailedMessage")
        }
    }

    /// The phone must not lock mid-transfer: a suspended app can drop the Bluetooth upload.
    private func keepScreenOn(_ on: Bool) {
        #if canImport(UIKit)
            UIApplication.shared.isIdleTimerDisabled = on
        #endif
    }
}
