import OmiComponents
import OmiDesign
import OmiDevice
import OmiService
import SwiftUI

/// My Omi › About this Omi: everything the Omi reports about itself, how well the connection holds
/// up, and forgetting it.
struct DeviceInfoScreen: View {
    let device: PairedDevice
    let codec: String?
    @Environment(DeviceStore.self) private var devices
    @Environment(FirmwareStore.self) private var firmware
    @Environment(\.dismiss) private var dismiss
    @State private var confirmForget = false

    var body: some View {
        OmiGroupedList {
            Section {
                LabeledContent(L("nativeModel"), value: device.modelNumber ?? "–")
                LabeledContent(L("nativeFirmware"), value: device.firmwareRevision ?? "–")
                LabeledContent(L("nativeAudioCodec"), value: codec ?? "–")
                if let hardware = device.hardwareRevision { LabeledContent(L("nativeHardwareRevision"), value: hardware) }
                if let manufacturer = device.manufacturerName { LabeledContent(L("manufacturer"), value: manufacturer) }
                if let serial = device.serialNumber {
                    LabeledContent(L("nativeSerialNumber"), value: serial).textSelection(.enabled)
                }
            }
            Section {
                NavigationLink { DeviceDiagnosticsScreen() } label: {
                    DeviceRow(L("nativeConnectionHealth"), systemImage: "waveform.path.ecg")
                }
                .accessibilityIdentifier("device.diagnostics")
            }
            Section {
                Button(L("nativeForgetDevice"), role: .destructive) { confirmForget = true }
                    .disabled(firmware.isBusy)
                    .accessibilityIdentifier("device.forget")
            }
        }
        .omiPage(L("nativeAboutThisOmi"))
        .confirmationDialog(L("nativeForgetDevice"), isPresented: $confirmForget, titleVisibility: .visible) {
            Button(L("nativeForgetDevice"), role: .destructive) {
                devices.forget()
                dismiss()
            }
        } message: {
            Text(L("forgetDeviceConfirmMessage"))
        }
    }
}
