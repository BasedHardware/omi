import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// Settings › Capabilities › Apple Health (Flutter `apple_health_detail_page`): what Omi reads,
/// whether it is connected, the last sync, connect / disconnect.
struct AppleHealthScreen: View {
    @Environment(AppleHealthStore.self) private var health
    @State private var confirmsDisconnect = false

    /// Apple Health's own pink, only for its icons (as Flutter).
    static let pink = Color(red: 1, green: 0.176, blue: 0.333)

    var body: some View {
        SettingsList {
            Section {
                HStack(spacing: DS.Spacing.md) {
                    AppleHealthIcon(size: 44)
                    VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                        Text("Apple Health").font(DS.Typography.cardTitle)
                        status
                    }
                }
                .padding(.vertical, DS.Spacing.xs)
            }
            Section {
                feature("bubble.left", L("appleHealthFeatureChatTitle"), L("appleHealthFeatureChatDesc"))
                feature("lock", L("appleHealthFeatureReadOnlyTitle"), L("appleHealthFeatureReadOnlyDesc"))
                feature("arrow.triangle.2.circlepath.icloud", L("appleHealthFeatureSecureTitle"), L("appleHealthFeatureSecureDesc"))
            }
            Section {
                if health.isConnected {
                    Button(L("syncNow")) { Task { await health.sync() } }
                        .disabled(health.phase != .idle)
                    Button(L("appleHealthDisconnectCta"), role: .destructive) { confirmsDisconnect = true }
                        .disabled(health.phase != .idle)
                        .accessibilityIdentifier("health.disconnect")
                } else {
                    Button {
                        Task { await health.connect() }
                    } label: {
                        HStack {
                            Text(L("appleHealthConnectCta"))
                            if health.phase == .connecting { Spacer(); ProgressView() }
                        }
                    }
                    .disabled(health.phase != .idle)
                    .accessibilityIdentifier("health.connect")
                }
            } footer: {
                Text(L("appleHealthManageNote"))
            }
        }
        .omiPage("Apple Health")
        .task { await health.load() }
        .confirmationDialog(L("disconnectAppTitle", "Apple Health"), isPresented: $confirmsDisconnect, titleVisibility: .visible) {
            Button(L("appleHealthDisconnectCta"), role: .destructive) { Task { await health.disconnect() } }
        } message: {
            Text(L("nativeAppleHealthReconnectAnytime"))
        }
        .alert(alertTitle ?? "", isPresented: Binding(get: { alertTitle != nil }, set: { if !$0 { health.notice = nil } })) {
            Button(L("ok"), role: .cancel) {}
        } message: {
            if health.notice == .denied { Text(L("appleHealthDeniedBody")) }
        }
    }

    private var status: some View {
        Group {
            if health.isConnected {
                HStack(spacing: DS.Spacing.xs) {
                    Circle().fill(DS.Palette.success).frame(width: 7, height: 7)
                    Text(L("appleHealthConnectedBadge")).foregroundStyle(DS.Palette.success)
                    Text("·")
                    Text(health.lastSync.map { L("nativeAppleHealthLastSync", $0.formatted(.relative(presentation: .named))) }
                        ?? L("nativeAppleHealthNotSynced"))
                }
            } else {
                Text(L("nativeCapabilityHealth"))
            }
        }
        .font(DS.Typography.caption)
        .foregroundStyle(DS.Palette.inkSecondary)
    }

    /// Failures only; a successful connect or disconnect shows in the status line.
    private var alertTitle: String? {
        switch health.notice {
        case .denied: L("appleHealthDeniedTitle")
        case .unavailable: L("appleHealthNotAvailable")
        case .failed: L("nativeAppleHealthConnectFailed")
        case .disconnectFailed: L("failedToDisconnect")
        case .connected, .disconnected, nil: nil
        }
    }

    private func feature(_ icon: String, _ title: String, _ detail: String) -> some View {
        // A thin gray glyph as on every settings row; Health's pink stays on its own icon only.
        HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
            SettingsIcon(systemImage: icon)
            VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                Text(title).font(DS.Typography.cardTitle)
                Text(detail).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
            }
        }
        .padding(.vertical, DS.Spacing.xxs)
        .accessibilityElement(children: .combine)
    }
}

/// The heart on white, as Health's own icon.
struct AppleHealthIcon: View {
    let size: CGFloat

    var body: some View {
        Image(systemName: "heart.fill")
            .font(.system(size: size * 0.5, weight: .semibold))
            .foregroundStyle(AppleHealthScreen.pink)
            .frame(width: size, height: size)
            .background(.white, in: RoundedRectangle(cornerRadius: size * 0.28, style: .continuous))
            .accessibilityHidden(true)
    }
}
