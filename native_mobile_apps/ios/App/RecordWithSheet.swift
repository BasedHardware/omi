import OmiComponents
import OmiDesign
import OmiDevice
import OmiService
import SwiftUI

/// "Record with…" (Flutter `battery_info_widget`, long press on the record button): one source at
/// a time, the phone's microphone, the Omi, or the Apple Watch.
struct RecordWithSheet: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        let devices = environment.devices
        let watch = environment.watch
        let omiReady = devices.connection == .connected && devices.codec != nil
        NavigationStack {
            OmiGroupedList {
                source(L("nativeRecordWithIPhone"), detail: L("nativeRecordWithPhoneDetail"), icon: "iphone", enabled: true) {
                    Task { await environment.capture.startPhone() }
                }
                source(
                    devices.paired?.name ?? "Omi",
                    detail: omiReady ? L("nativeRecordWithOmiDetail") : L("nativeRecordWithOmiUnavailable"),
                    icon: "circle.circle", enabled: omiReady
                ) {
                    guard let codec = devices.codec else { return }
                    Task { await environment.capture.startDevice(codec: codec) }
                }
                source(
                    L("nativeRecordWithWatch"),
                    detail: watch.isAvailable ? L("nativeRecordWithWatchDetail") : L("nativeRecordWithWatchUnavailable"),
                    icon: "applewatch", enabled: watch.isAvailable
                ) {
                    watch.startFromPhone()
                }
            }
            .scrollContentBackground(.hidden)
            .background(DS.Palette.background)
            .navigationTitle(L("nativeRecordWith"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } }
            }
        }
        .presentationDetents([.medium])
        // Solid, like the app's other surfaces (the default sheet glass greys the list in light mode).
        .presentationBackground(DS.Palette.background)
        .onAppear { watch.ping() }
    }

    private func source(_ title: String, detail: String, icon: String, enabled: Bool, start: @escaping () -> Void) -> some View {
        Button {
            DSHaptics.tap(.medium)
            dismiss()
            start()
        } label: {
            Label {
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    Text(title).foregroundStyle(enabled ? DS.Palette.ink : DS.Palette.inkDisabled)
                    Text(detail).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                }
            } icon: {
                Image(systemName: icon)
                    .font(.system(size: 17, weight: .regular))
                    .foregroundStyle(enabled ? DS.Palette.inkSecondary : DS.Palette.inkDisabled)
            }
        }
        .disabled(!enabled || environment.capture.isLive)
        .accessibilityIdentifier("recordWith.\(icon)")
    }
}
