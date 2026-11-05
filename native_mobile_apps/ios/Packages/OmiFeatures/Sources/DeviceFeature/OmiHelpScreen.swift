import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// My Omi › Help with your Omi: learning the button again and charging help (Flutter device
/// settings: Device Tutorial, Charging Issues; Diagnostics lives in About this Omi).
/// One row on the device screen leads here, so the device screen stays about the device.
struct OmiHelpScreen: View {
    let deviceName: String
    let tutorial: AnyView?
    @Environment(DeviceStore.self) private var devices
    @State private var showsTutorial = false

    var body: some View {
        OmiGroupedList {
            Section {
                if tutorial != nil {
                    Button { showsTutorial = true } label: {
                        row(L("nativeLearnTheButton"), symbol: "hand.tap", trailing: "chevron.right")
                    }
                    .disabled(devices.connection != .connected)
                    .accessibilityIdentifier("device.tutorial")
                }
                Link(destination: DeviceScreen.chargingHelpURL(deviceName)) {
                    row(L("nativeChargingHelp"), symbol: "bolt", trailing: "arrow.up.right")
                }
            } footer: {
                // What each row is, said once (rows stay one line).
                VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                    if tutorial != nil, devices.connection != .connected { Text(L("nativeOmiOnAndNearby")) }
                    Text(L("nativeHelpFooter"))
                }
            }
        }
        .omiPage(L("nativeHelpWithYourOmi"))
        .fullScreenCover(isPresented: $showsTutorial) { tutorial }
    }

    /// A one-line row that opens something: the glyph, the title, where it goes on the right.
    private func row(_ title: String, symbol: String, trailing: String) -> some View {
        HStack {
            DeviceRow(title, systemImage: symbol)
            Spacer(minLength: DS.Spacing.sm)
            Image(systemName: trailing)
                .font(DS.Typography.caption.weight(.semibold))
                .foregroundStyle(DS.Palette.inkTertiary)
                .accessibilityHidden(true)
        }
    }
}

/// Simulator QA without tapping (Debug builds only).
enum DeviceDebug {
    static var page: String? {
        #if DEBUG
            UserDefaults.standard.string(forKey: "omiDevicePage")
        #else
            nil
        #endif
    }
}
