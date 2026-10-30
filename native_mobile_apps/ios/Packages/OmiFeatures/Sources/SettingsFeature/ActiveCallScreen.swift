import AVKit
import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// The call in progress (Flutter `active_call_page`): who, how long, the live transcript of both
/// sides, mute / keypad (tones) / speaker / audio route / end. Minimizing keeps the call going.
public struct ActiveCallScreen: View {
    @Environment(PhoneCallStore.self) private var phone
    @Environment(\.dismiss) private var dismiss
    @State private var showsKeypad = false

    public init() {}

    public var body: some View {
        VStack(spacing: DS.Spacing.md) {
            topBar
            header
            if phone.phase == .active, let chip = transcriptionChip { Pill(chip.text, tint: chip.tint) }
            CallTranscriptView()
            controls
        }
        .padding(.horizontal, DS.Spacing.gutter)
        .padding(.bottom, DS.Spacing.lg)
        .background(AuroraBackground().ignoresSafeArea())
        .sheet(isPresented: $showsKeypad) { DTMFSheet() }
        .accessibilityIdentifier("phone.activeCall")
    }

    private var topBar: some View {
        HStack {
            Button { dismiss() } label: { Image(systemName: "chevron.down").font(.title3.weight(.semibold)) }
                .accessibilityLabel(L("nativePhoneMinimize"))
            Spacer()
            AudioRoutePicker()
                .frame(width: 36, height: 36)
                .accessibilityLabel(L("audioOutput"))
        }
        .foregroundStyle(DS.Palette.ink)
        .padding(.top, DS.Spacing.sm)
    }

    private var header: some View {
        VStack(spacing: DS.Spacing.xs) {
            Text(phone.otherParty).font(DS.Typography.largeTitle).lineLimit(1).minimumScaleFactor(0.6)
            if phone.contactName != nil, let number = phone.remoteNumber {
                Text(PhoneNumberFormat.display(number)).foregroundStyle(DS.Palette.inkSecondary)
            }
            status.font(DS.Typography.callout.monospacedDigit()).foregroundStyle(DS.Palette.inkSecondary)
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var status: some View {
        switch phone.phase {
        case .idle, .connecting: Text(L("callStateConnecting"))
        case .ringing: Text(L("callStateRinging"))
        case .active:
            if let start = phone.connectedAt {
                TimelineView(.periodic(from: start, by: 1)) { context in
                    Text(Duration.seconds(max(0, context.date.timeIntervalSince(start).rounded(.down)))
                        .formatted(.time(pattern: .minuteSecond)))
                }
            }
        case .ended:
            Text(phone.failure.map(PhoneCallWording.failure) ?? L("callStateEnded"))
                .foregroundStyle(phone.failure == nil ? DS.Palette.inkSecondary : DS.Palette.live)
        }
    }

    private var transcriptionChip: (text: String, tint: Color)? {
        switch phone.transcription {
        case .idle, .active: nil
        case .connecting: (L("transcriptionConnecting"), DS.Palette.inkSecondary)
        case .reconnecting: (L("transcriptionReconnecting"), DS.Palette.warning)
        case .failed: (L("transcriptionUnavailable"), DS.Palette.live)
        case .noAudio: (L("transcriptionNoAudio"), DS.Palette.warning)
        }
    }

    private var controls: some View {
        let live = phone.isInProgress
        return VStack(spacing: DS.Spacing.lg) {
            HStack(spacing: DS.Spacing.xl) {
                CallControl(
                    icon: phone.isMuted ? "mic.slash.fill" : "mic.fill",
                    title: phone.isMuted ? L("phoneUnmute") : L("phoneMute"), isOn: phone.isMuted
                ) { phone.toggleMute() }
                    .disabled(!live)
                CallControl(icon: "circle.grid.3x3.fill", title: L("phoneKeypad"), isOn: false) { showsKeypad = true }
                    .disabled(phone.phase != .active)
                CallControl(icon: "speaker.wave.2.fill", title: L("phoneSpeaker"), isOn: phone.isSpeakerOn) { phone.toggleSpeaker() }
                    .disabled(!live)
            }
            Button { phone.end() } label: {
                Image(systemName: "phone.down.fill")
                    .font(.title)
                    .frame(width: 76, height: 76)
                    .background(DS.Palette.live, in: Circle())
                    .foregroundStyle(.white)
            }
            .buttonStyle(.plain)
            .disabled(!live)
            .opacity(live ? 1 : 0.5)
            .accessibilityLabel(L("phoneEndCall"))
            .accessibilityIdentifier("phone.end")
        }
    }
}

private struct CallControl: View {
    let icon: String
    let title: String
    let isOn: Bool
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button(action: action) {
            VStack(spacing: DS.Spacing.xs) {
                Image(systemName: icon)
                    .font(.title2)
                    .frame(width: 64, height: 64)
                    .background(isOn ? DS.Palette.ink : DS.Palette.fill, in: Circle())
                    .foregroundStyle(isOn ? DS.Palette.onAccent : DS.Palette.ink)
                Text(title).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
            }
        }
        .buttonStyle(.plain)
        .opacity(isEnabled ? 1 : 0.4)
        .accessibilityAddTraits(isOn ? .isSelected : [])
    }
}

/// Both sides as bubbles, you on the right; translations (live interpreter) under the line.
private struct CallTranscriptView: View {
    @Environment(PhoneCallStore.self) private var phone

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: DS.Spacing.sm) {
                    if phone.transcript.isEmpty, phone.phase == .active, phone.transcription != .noAudio {
                        Text(L("transcriptPlaceholder")).foregroundStyle(DS.Palette.inkTertiary).padding(.top, DS.Spacing.xl)
                    }
                    ForEach(phone.transcript.segments) { segment in
                        bubble(segment).id(segment.id)
                    }
                }
                .padding(.vertical, DS.Spacing.sm)
            }
            .scrollIndicators(.hidden)
            .onChange(of: phone.transcript.segments.last?.id) { _, last in
                guard let last else { return }
                withAnimation(DS.Motion.gentle) { proxy.scrollTo(last, anchor: .bottom) }
            }
        }
    }

    private func bubble(_ segment: LiveSegment) -> some View {
        VStack(alignment: segment.isUser ? .trailing : .leading, spacing: DS.Spacing.xxs) {
            Text(segment.isUser ? L("nativePhoneCallYou") : phone.otherParty)
                .font(DS.Typography.micro)
                .foregroundStyle(DS.Palette.inkTertiary)
            VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                Text(segment.text)
                ForEach(phone.transcript.translations[segment.id] ?? [], id: \.self) { translated in
                    Text(translated).italic().foregroundStyle(DS.Palette.inkSecondary)
                }
            }
            .font(DS.Typography.callout)
            .padding(.horizontal, DS.Spacing.md)
            .padding(.vertical, DS.Spacing.sm)
            .background(segment.isUser ? DS.Palette.cardRaised : DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.md))
        }
        .frame(maxWidth: .infinity, alignment: segment.isUser ? .trailing : .leading)
        .padding(segment.isUser ? .leading : .trailing, DS.Spacing.section)
        .accessibilityElement(children: .combine)
    }
}

/// Tones into the call (menus, extensions).
private struct DTMFSheet: View {
    @Environment(PhoneCallStore.self) private var phone
    @Environment(\.dismiss) private var dismiss
    @State private var typed = ""

    var body: some View {
        VStack(spacing: DS.Spacing.lg) {
            Text(typed.isEmpty ? " " : typed).font(.system(size: 30, weight: .medium, design: .rounded).monospacedDigit())
            PhoneKeypad { digit in
                typed.append(digit)
                phone.sendDigit(digit)
            }
            Button(L("phoneHideKeypad")) { dismiss() }.buttonStyle(.omiPillSubtle)
        }
        .padding(DS.Spacing.gutter)
        .presentationDetents([.large])
    }
}

/// The system route picker: iPhone, speaker, AirPods and other Bluetooth or wired devices.
private struct AudioRoutePicker: UIViewRepresentable {
    func makeUIView(context _: Context) -> AVRoutePickerView {
        let view = AVRoutePickerView()
        view.prioritizesVideoDevices = false
        view.tintColor = .label
        return view
    }

    func updateUIView(_: AVRoutePickerView, context _: Context) {}
}

/// The app shell's part: while a call goes on and its screen is down, a banner on top returns to it.
public struct OngoingCallPresenter: ViewModifier {
    @Environment(PhoneCallStore.self) private var phone
    @State private var showsCall = false

    public init() {}

    public func body(content: Content) -> some View {
        content
            .safeAreaInset(edge: .top, spacing: 0) {
                if phone.isInProgress, !phone.showsCallScreen, !showsCall { banner }
            }
            .fullScreenCover(isPresented: Binding(get: { showsCall && phone.phase != .idle }, set: { showsCall = $0 })) {
                ActiveCallScreen()
            }
            .onChange(of: phone.phase) { _, phase in if phase == .idle { showsCall = false } }
    }

    private var banner: some View {
        Button { showsCall = true } label: {
            HStack(spacing: DS.Spacing.sm) {
                Image(systemName: "phone.fill")
                Text(phone.otherParty).font(DS.Typography.cardTitle).lineLimit(1)
                Spacer()
                if let start = phone.connectedAt {
                    Text(start, style: .timer).monospacedDigit()
                } else {
                    Text(phone.phase == .ringing ? L("callStateRinging") : L("callStateConnecting"))
                }
            }
            .font(DS.Typography.callout)
            .foregroundStyle(.white)
            .padding(.horizontal, DS.Spacing.lg)
            .padding(.vertical, DS.Spacing.sm)
            .background(DS.Palette.success, in: Capsule())
            .padding(.horizontal, DS.Spacing.lg)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(L("nativePhoneReturnToCall"))
        .accessibilityIdentifier("phone.banner")
    }
}
