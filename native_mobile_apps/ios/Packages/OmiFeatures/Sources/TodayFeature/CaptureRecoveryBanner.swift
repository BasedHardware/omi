import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

/// Home's notice when a recording did not end as meant (Flutter `capture_recovery_banner`): the
/// app was closed while recording, the connection dropped and the phone kept the audio, or the
/// system took the microphone away while the recording is still running.
struct CaptureRecoveryBanner: View {
    @Environment(CaptureStore.self) private var capture
    @Environment(SyncStore.self) private var sync

    var body: some View {
        VStack(spacing: DS.Spacing.sm) {
            if let recovery = capture.recovery { recoveryCard(recovery) }
            if let notice = capture.notice { noticeCard(notice) }
        }
    }

    private func recoveryCard(_ recovery: CaptureRecovery) -> some View {
        card(
            CardCopy(
                icon: recovery == .connectionLost ? "wifi.exclamationmark" : "exclamationmark.triangle.fill",
                title: title(recovery),
                message: message(recovery),
                identifier: "home.captureRecovery"
            ),
            dismiss: { capture.dismissRecovery() },
            buttons: {
                if case .interrupted = recovery, !capture.isLive {
                    Button(L("nativeRecoveryRecordAgain")) {
                        capture.dismissRecovery()
                        Task { await capture.startPhone() }
                    }
                    .buttonStyle(OmiPillButtonStyle())
                }
                if sync.status != .synced, !capture.isLive, sync.hasPending {
                    Button(L("nativeRecoveryUploadNow")) { Task { await sync.uploadPending() } }
                        .buttonStyle(OmiPillButtonStyle(prominent: false))
                }
            }
        )
    }

    /// The recording is still running: the system has the microphone and the app is asking for it
    /// back every few seconds, so this only says why it is quiet.
    private func noticeCard(_ notice: CaptureNotice) -> some View {
        card(
            CardCopy(
                icon: "mic.slash",
                title: L("nativeNoticeCapturePaused"),
                message: notice == .inputGone
                    ? L("nativeNoticeInputGoneMessage")
                    : L("nativeNoticeMicrophoneTakenMessage"),
                identifier: "home.captureNotice"
            ),
            dismiss: { capture.dismissNotice() },
            buttons: { EmptyView() }
        )
    }

    /// The words and the identity of one notice card; `card` only lays them out.
    private struct CardCopy {
        let icon: String
        let title: String
        let message: String
        let identifier: String
    }

    private func card(
        _ copy: CardCopy,
        dismiss: @escaping () -> Void,
        @ViewBuilder buttons: () -> some View
    ) -> some View {
        HStack(alignment: .top, spacing: DS.Spacing.md) {
            Image(systemName: copy.icon)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(DS.Palette.warning)
                .frame(width: 24)
            VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                Text(copy.title).font(DS.Typography.cardTitle)
                Text(copy.message).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                HStack(spacing: DS.Spacing.sm) { buttons() }
                    .padding(.top, DS.Spacing.xxs)
            }
            Spacer(minLength: 0)
            Button { withAnimation(DS.Motion.standard) { dismiss() } } label: {
                Image(systemName: "xmark").font(.caption.weight(.bold)).foregroundStyle(DS.Palette.inkTertiary)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(L("close"))
        }
        .padding(DS.Spacing.lg)
        .omiCardSurface()
        .accessibilityIdentifier(copy.identifier)
        .transition(.opacity.combined(with: .move(edge: .top)))
    }

    private func title(_ recovery: CaptureRecovery) -> String {
        switch recovery {
        case .interrupted: L("nativeRecoveryInterruptedTitle")
        case .connectionLost: L(capture.isLive ? "nativeRecoveryOfflineTitle" : "nativeRecoveryOfflineSavedTitle")
        }
    }

    private func message(_ recovery: CaptureRecovery) -> String {
        switch recovery {
        case let .interrupted(since):
            L("nativeRecoveryInterruptedMessage", since.formatted(date: .omitted, time: .shortened))
        case .connectionLost:
            L(capture.isLive ? "nativeRecoveryOfflineMessage" : "nativeRecoveryOfflineSavedMessage")
        }
    }
}
