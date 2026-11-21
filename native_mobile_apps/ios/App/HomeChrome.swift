import OmiDesign
import OmiDevice
import OmiService
import SwiftUI

/// Omi's header pill: "Connect" without a device, name and battery while connected, otherwise the
/// connection state (tap: My Devices); a red dot while live, a small accent dot while offline
/// recordings wait to sync.
struct DevicePill: View {
    @Environment(DeviceStore.self) private var devices
    @Environment(CaptureStore.self) private var capture
    @Environment(SyncStore.self) private var sync

    var body: some View {
        HStack(spacing: DS.Spacing.sm) {
            // The pendant itself, with a small status dot: red while recording, green when
            // connected, none when it is away.
            OmiPendantThumbnail(size: 26)
                .opacity(devices.connection == .connected ? 1 : 0.45)
                .overlay(alignment: .bottomTrailing) {
                    if let dot = statusColor {
                        Circle().fill(dot).frame(width: 8, height: 8)
                            .overlay { Circle().strokeBorder(DS.Palette.background, lineWidth: 1.5) }
                    }
                }
            Text(label).font(.body.weight(.semibold)).lineLimit(1)
            if let battery {
                Text(battery).font(.subheadline).foregroundStyle(DS.Palette.inkSecondary).monospacedDigit()
            }
            Image(systemName: "chevron.down").font(.system(size: 11, weight: .semibold)).foregroundStyle(DS.Palette.inkTertiary)
        }
        .foregroundStyle(DS.Palette.ink)
        .frame(minHeight: DS.Size.headerButton)
        .contentShape(Rectangle())
        .overlay(alignment: .topTrailing) {
            if sync.hasPending {
                Circle().fill(DS.Palette.agent).frame(width: 7, height: 7).offset(x: 6).accessibilityHidden(true)
            }
        }
    }

    private var statusColor: Color? {
        if capture.isLive { return DS.Palette.live }
        return devices.connection == .connected ? DS.Palette.success : nil
    }

    private var battery: String? {
        guard devices.connection == .connected, let level = devices.battery else { return nil }
        return "\(level)%"
    }

    private var label: String {
        guard let paired = devices.paired else { return L("connect") }
        switch devices.connection {
        case .connected: return paired.name
        // Tapping opens My Devices, which explains what to check and can try again.
        case .connecting: return L("nativeConnecting")
        case .disconnected: return L("nativeNotConnected")
        }
    }
}

/// Omi's bottom bar: "Ask Omi" with a mic, and the round record button beside it.
struct OmiBottomBar: View {
    @Environment(CaptureStore.self) private var capture
    let onAsk: () -> Void
    /// The mic: opens the chat already listening.
    let onDictate: () -> Void
    /// Long press on record: choose the phone, the Omi or the watch.
    let onRecordWith: () -> Void
    /// A long press just opened Record with…: the release that follows is not a tap.
    @State private var longPressed = false

    /// What the bar covers above the bottom safe area; the pages keep their last rows clear of it.
    static let height = DS.Size.omiBarHeight + DS.Spacing.sm + DS.Spacing.xs

    var body: some View {
        // One rounded composer, as in the ChatGPT app: the prompt, the mic, and the record button
        // as the filled circle at the end.
        HStack(spacing: DS.Spacing.xs) {
            Button(action: onAsk) {
                Text(L("askOmi")).font(DS.Typography.body).foregroundStyle(DS.Palette.inkTertiary)
                    .frame(maxWidth: .infinity, minHeight: DS.Size.omiBarHeight, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("omibar.ask")
            Button(action: onDictate) {
                Image(systemName: "mic")
                    .font(.system(size: 18, weight: .regular))
                    .foregroundStyle(DS.Palette.ink)
                    .frame(width: 40, height: 40)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.hapticTap)
            .accessibilityLabel(L("nativeAskByVoice"))
            .accessibilityIdentifier("omibar.dictate")
            recordButton
        }
        .padding(.leading, DS.Spacing.lg + 2)
        .padding(.trailing, DS.Spacing.sm)
        .frame(minHeight: DS.Size.omiBarHeight)
        .background(DS.Palette.cardRaised, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 28, style: .continuous).strokeBorder(DS.Palette.cardStroke, lineWidth: 1)
        }
        .padding(.horizontal, DS.Spacing.gutter)
        .padding(.top, DS.Spacing.sm)
        .padding(.bottom, DS.Spacing.xs)
    }

    /// Tap: record with the phone (or stop); long press: choose the phone, the Omi or the watch.
    private var recordButton: some View {
        Button {
            if longPressed {
                longPressed = false
                return
            }
            DSHaptics.tap(.medium)
            Task { capture.isLive ? await capture.stop() : await capture.startPhone() }
        } label: {
            Group {
                if capture.isLive {
                    RoundedRectangle(cornerRadius: 3).fill(DS.Palette.onAccent).frame(width: 13, height: 13)
                } else {
                    Circle().fill(DS.Palette.live).frame(width: 14, height: 14)
                }
            }
            .frame(width: 40, height: 40)
            .background(DS.Palette.ink, in: Circle())
        }
        .buttonStyle(.plain)
        .simultaneousGesture(LongPressGesture(minimumDuration: 0.45).onEnded { _ in
            guard !capture.isLive else { return }
            longPressed = true
            DSHaptics.tap(.medium)
            onRecordWith()
            // Some releases never reach the button: never swallow a later tap.
            Task {
                try? await Task.sleep(for: .seconds(1.5))
                longPressed = false
            }
        })
        .accessibilityAction(named: L("nativeRecordWith")) { if !capture.isLive { onRecordWith() } }
        .accessibilityLabel(capture.isLive ? L("nativeStopRecording") : L("nativeRecordWithPhone"))
        .accessibilityIdentifier(capture.isLive ? "capture.stop" : "capture.startPhone")
    }
}
