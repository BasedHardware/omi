import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// The paired Apple Watch as a recording source (Flutter's Apple Watch device and
/// `apple_watch_permission_page`): is the Omi watch app there, and may it use the microphone. The
/// watch asks for the microphone itself and answers back; recordings then start on the wrist.
/// Only on the path when a watch is paired.
struct WatchStep: View {
    let watch: WatchStore?
    let onContinue: () -> Void
    @State private var showsHelp = false

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerAppleWatch"), title: L("nativeWatchStepTitle"), subtitle: L("nativeWatchStepShort"),
            button: StepButton(title: L("continueButton"), action: onContinue)
        ) {
            Image(systemName: "applewatch")
                .font(.system(size: 72, weight: .ultraLight))
                .foregroundStyle(DS.Palette.ink)
                .frame(maxWidth: .infinity)
                .frame(height: 110)
                .accessibilityHidden(true)
            RowList {
                appRow
                microphoneRow
            }
            Button(L("nativeWatchNeedHelp")) { showsHelp = true }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.Palette.inkSecondary)
                .frame(maxWidth: .infinity)
        }
        .onAppear { watch?.ping() }
        .alert(L("nativeWatchNeedHelp"), isPresented: $showsHelp) {
            Button(L("gotIt"), role: .cancel) {}
        } message: {
            Text(L("nativeWatchTroubleshooting"))
        }
    }

    private var installed: Bool {
        watch?.isWatchAppInstalled == true || watch?.isAvailable == true
    }

    private var appRow: some View {
        row(
            "applewatch", L("nativeWatchAppRow"),
            installed ? L("nativeWatchAppInstalled") : L("nativeWatchAppMissing")
        ) {
            if installed {
                Image(systemName: "checkmark.circle.fill").font(.title3).foregroundStyle(DS.Palette.success)
            } else {
                Image(systemName: "arrow.down.circle").font(.title3).foregroundStyle(DS.Palette.inkTertiary)
            }
        }
    }

    private var microphoneRow: some View {
        let granted = watch?.microphoneGranted
        let detail = if granted == true {
            L("nativeWatchMicAllowed")
        } else if granted == false {
            L("nativeWatchMicDenied")
        } else if watch?.isRequestingMicrophone == true {
            L("nativeWatchMicLookAtWatch")
        } else {
            L("nativeWatchMicReason")
        }
        return row("mic", L("microphonePermission"), detail) {
            if granted == true {
                Image(systemName: "checkmark.circle.fill").font(.title3).foregroundStyle(DS.Palette.success)
                    .transition(.scale.combined(with: .opacity))
            } else if watch?.isRequestingMicrophone == true {
                ProgressView()
            } else {
                Button(L("allow")) { watch?.requestMicrophone() }
                    .buttonStyle(.omiPill)
                    .disabled(!installed)
                    .accessibilityIdentifier("onboarding.watch.allowMicrophone")
            }
        }
        .animation(DS.Motion.snappy, value: granted)
    }

    private func row(_ icon: String, _ title: String, _ detail: String, @ViewBuilder trailing: () -> some View) -> some View {
        HStack(spacing: DS.Spacing.md) {
            Image(systemName: icon).font(.title3).frame(width: 28, alignment: .leading)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.body.weight(.medium))
                Text(detail).font(.subheadline).foregroundStyle(DS.Palette.inkSecondary)
                    .contentTransition(.opacity)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            trailing()
        }
        .padding(.horizontal, DS.Spacing.lg)
        .padding(.vertical, DS.Spacing.md)
    }
}
