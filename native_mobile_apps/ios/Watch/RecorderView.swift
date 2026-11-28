import SwiftUI

/// One big button: tap to record, tap again to stop. Elapsed time while recording, the Omi's
/// battery on top while it is connected to the iPhone.
struct RecorderView: View {
    let recorder: WatchRecorder

    var body: some View {
        VStack(spacing: 6) {
            if let battery = recorder.phone?.omiBattery {
                Label("watch.omiBattery \(battery)", systemImage: Self.batteryIcon(battery))
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            Spacer(minLength: 0)
            Button(action: recorder.toggle) {
                RecordButtonFace(phase: recorder.phase)
            }
            .buttonStyle(.plain)
            .disabled(recorder.phase == .starting)
            .accessibilityLabel(
                recorder.isRecording ? Text("watch.accessibility.stopRecording") : Text("watch.accessibility.startRecording")
            )
            Spacer(minLength: 0)
            status
                .multilineTextAlignment(.center)
                .frame(minHeight: 40)
        }
        .padding(.horizontal, 4)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black)
    }

    @ViewBuilder private var status: some View {
        switch recorder.phase {
        case let .recording(since):
            Text(since, style: .timer)
                .font(.system(size: 24, weight: .semibold, design: .rounded))
                .monospacedDigit()
                .accessibilityLabel(Text("watch.accessibility.elapsedRecordingTime"))
        case .starting:
            Text("watch.starting").font(.headline)
        case .idle:
            if let notice = recorder.notice {
                Text(Self.text(notice)).font(.footnote).foregroundStyle(.orange)
            } else {
                Text("watch.tapToRecord").font(.headline)
            }
        }
    }

    static func text(_ notice: WatchRecorder.Notice) -> LocalizedStringKey {
        switch notice {
        case .microphoneDenied: "watch.error.microphoneDenied"
        case .microphoneFailed: "watch.error.microphoneFailed"
        case .phoneBusy: "watch.error.phoneBusy"
        case .phoneSignedOut: "watch.error.phoneSignedOut"
        case .phoneFailed: "watch.error.phoneFailed"
        }
    }

    static func batteryIcon(_ level: Int) -> String {
        switch level {
        case ..<13: "battery.0percent"
        case ..<38: "battery.25percent"
        case ..<63: "battery.50percent"
        case ..<88: "battery.75percent"
        default: "battery.100percent"
        }
    }
}

private struct RecordButtonFace: View {
    let phase: WatchRecorder.Phase

    var body: some View {
        ZStack {
            Circle()
                .fill(isRecording ? Color.red : Color.white)
                .frame(width: 92, height: 92)
            switch phase {
            case .idle:
                Image("OmiLogo").resizable().scaledToFit().frame(width: 44, height: 44)
            case .starting:
                ProgressView().tint(.black)
            case .recording:
                RoundedRectangle(cornerRadius: 6).fill(Color.white).frame(width: 30, height: 30)
            }
        }
        .overlay {
            if isRecording {
                Circle().stroke(Color.red.opacity(0.4), lineWidth: 3).frame(width: 104, height: 104)
                    .phaseAnimator([false, true]) { ring, expanded in
                        ring.scaleEffect(expanded ? 1.12 : 1).opacity(expanded ? 0 : 1)
                    } animation: { _ in .easeOut(duration: 1.2) }
            }
        }
        .animation(.easeInOut(duration: 0.2), value: phase)
    }

    private var isRecording: Bool {
        if case .recording = phase { return true }
        return false
    }
}
