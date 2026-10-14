import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// The conversation being recorded, in full (Flutter `conversation_capturing/page.dart`): every
/// segment with its speaker, how long it runs, where the audio comes from, Pause/Resume and Stop.
/// A tap on a speaker names the voice, as on a finished conversation.
struct LiveTranscriptSheet: View {
    @Environment(CaptureStore.self) private var capture
    @Environment(LiveSpeakersStore.self) private var speakers
    @Environment(SettingsStore.self) private var settings
    @Environment(\.dismiss) private var dismiss
    @State private var naming: LiveSegment?

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: DS.Spacing.md) {
                        header
                        if lines.isEmpty {
                            Text(capture.isPaused ? L("paused") : L("nativeListeningHint"))
                                .font(DS.Typography.callout)
                                .foregroundStyle(DS.Palette.inkSecondary)
                                .padding(.top, DS.Spacing.xl)
                        }
                        ForEach(lines) { line in
                            row(line, isPartial: line.id == capture.partial?.id)
                        }
                        Color.clear.frame(height: 1).id(Self.bottom)
                    }
                    .padding(.horizontal, DS.Spacing.lg)
                    .padding(.bottom, DS.Spacing.section)
                }
                .onChange(of: capture.transcriptText) {
                    withAnimation(DS.Motion.gentle) { proxy.scrollTo(Self.bottom, anchor: .bottom) }
                }
            }
            .safeAreaInset(edge: .bottom) { controls }
            .navigationTitle(L("nativeLiveTranscript"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(L("nativeDone")) { dismiss() }
                }
            }
        }
        .onChange(of: capture.phase) {
            if capture.phase == .idle { dismiss() }
        }
        .sheet(item: $naming) { segment in namingSheet(segment) }
    }

    private static let bottom = "live.bottom"

    private var lines: [LiveSegment] {
        capture.segments + (capture.partial.map { [$0] } ?? [])
    }

    /// Recording since, the source, and the star mark from a double tap.
    private var header: some View {
        HStack(spacing: DS.Spacing.sm) {
            Circle().fill(capture.isPaused ? DS.Palette.inkTertiary : DS.Palette.live).frame(width: 8, height: 8)
            if case let .live(since) = capture.phase {
                TimelineView(.periodic(from: since, by: 1)) { context in
                    Text(Duration.seconds(max(0, context.date.timeIntervalSince(since).rounded())).formatted(.time(pattern: .minuteSecond)))
                        .monospacedDigit()
                }
            }
            if capture.isPaused { Text(L("paused")) }
            Spacer()
            if capture.starsConversation {
                Image(systemName: "star.fill").foregroundStyle(DS.Palette.warning).accessibilityLabel(L("starConversation"))
            }
            Label(
                capture.source == .device ? L("nativeAudioFromOmi") : L("nativeAudioFromPhone"),
                systemImage: capture.source == .device ? "circle.circle.fill" : "iphone"
            )
            .foregroundStyle(DS.Palette.agent)
        }
        .font(DS.Typography.caption.weight(.semibold))
        .foregroundStyle(DS.Palette.inkSecondary)
        .padding(.vertical, DS.Spacing.sm)
    }

    private func row(_ line: LiveSegment, isPartial: Bool) -> some View {
        let label = speakers.label(for: line)
        return VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
            Button {
                naming = line
            } label: {
                Text(speakerName(line, label))
                    .font(DS.Typography.micro)
                    .foregroundStyle(label.isUser ? DS.Palette.agent : DS.Palette.inkTertiary)
            }
            .buttonStyle(.plain)
            .disabled(isPartial || !capture.isLive)
            .accessibilityHint(L("nativeTapToNameVoice"))
            .accessibilityIdentifier("live.speaker")
            Text(line.text)
                .font(DS.Typography.body)
                .foregroundStyle(isPartial ? DS.Palette.inkSecondary : DS.Palette.ink)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    static func speaker(_ line: LiveSegment) -> String {
        if line.isUser { return L("nativeYou") }
        return L("speakerWithId", String((line.speakerID ?? 0) + 1))
    }

    /// You, the named person, else "Speaker N".
    private func speakerName(_ line: LiveSegment, _ label: LiveSpeakersStore.Label) -> String {
        if label.isUser { return L("nativeYou") }
        if let id = label.personID, let name = settings.person(id)?.name ?? speakers.name(for: id) { return name }
        return Self.speaker(line)
    }

    private func namingSheet(_ segment: LiveSegment) -> some View {
        let label = speakers.label(for: segment)
        return SpeakerNamePicker(
            line: .init(
                text: segment.text, isUser: label.isUser, personID: label.personID, hasVoice: segment.speakerID != nil,
                sameVoiceCount: speakers.lines(sameVoiceAs: segment).count, offersNotAPerson: false
            ),
            isSaving: speakers.isSaving
        ) { choice, scope in
            let speakers = speakers
            let settings = settings
            Task {
                if await speakers.assign(segment, to: choice, scope: scope) != nil { await settings.loadPeople() }
            }
        }
        .task { if settings.people.isEmpty { await settings.loadPeople() } }
    }

    private var controls: some View {
        HStack(spacing: DS.Spacing.md) {
            Button {
                if capture.isPaused { Task { await capture.resume() } } else { capture.pause() }
            } label: {
                Label(capture.isPaused ? L("resume") : L("pause"), systemImage: capture.isPaused ? "play.fill" : "pause.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.omiPillSubtle)
            .accessibilityIdentifier("live.pause")
            Button(role: .destructive) {
                Task { await capture.stop() }
            } label: {
                Label(L("nativeStopRecording"), systemImage: "stop.fill").frame(maxWidth: .infinity)
            }
            .buttonStyle(.omiPillSubtle)
            .accessibilityIdentifier("live.stop")
        }
        .disabled(!capture.isLive)
        .padding(.horizontal, DS.Spacing.lg)
        .padding(.vertical, DS.Spacing.sm)
        .background(.bar)
    }
}
