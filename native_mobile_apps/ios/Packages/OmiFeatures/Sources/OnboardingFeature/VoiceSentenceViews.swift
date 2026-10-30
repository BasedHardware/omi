import OmiDesign
import OmiService
import SwiftUI

// The voice step: its progress steps, the gap sentence filling in as it is said,
// and the quiet listening line under it.

/// One step per sentence: finished ones full, the current one filling as it is said.
struct SentenceSteps: View {
    let done: Int
    let total: Int
    let current: Double
    let needsMore: Bool

    var body: some View {
        HStack(spacing: DS.Spacing.xs) {
            ForEach(0 ..< total, id: \.self) { index in
                GeometryReader { proxy in
                    Capsule().fill(DS.Palette.ink.opacity(0.1))
                        .overlay(alignment: .leading) {
                            Capsule().fill(index < done ? DS.Palette.success : DS.Palette.agent)
                                .frame(width: proxy.size.width * fill(index))
                        }
                }
                .frame(height: 4)
            }
        }
        .animation(.easeOut(duration: 0.35), value: done)
        .animation(.easeOut(duration: 0.25), value: current)
        .accessibilityElement()
        .accessibilityLabel(L("nativeVoiceSentenceOf", String(min(done + 1, total)), String(total)))
    }

    private func fill(_ index: Int) -> Double {
        if index < done || needsMore { return 1 }
        // The current step stops short of full until the sentence is really done.
        return index == done ? min(0.9, current) : 0
    }
}

/// The sentence to say, filling in as it is said: fixed words turn from faint to solid when
/// heard, the gaps fill with the user's own words.
struct GapSentenceText: View {
    let match: GapSentence.Match

    var body: some View {
        FlowLayout(spacing: 7) {
            // Stable ids: a gap filling moves the words after it instead of cross-fading them.
            ForEach(tokens, id: \.id) { item in
                switch item.token {
                case let .word(word, heard):
                    Text(word)
                        .foregroundStyle(heard ? DS.Palette.ink : DS.Palette.ink.opacity(0.45))
                case let .said(word):
                    Text(word)
                        .foregroundStyle(DS.Palette.agent)
                        .padding(.bottom, 3)
                        .overlay(alignment: .bottom) { Capsule().fill(DS.Palette.agent.opacity(0.5)).frame(height: 2) }
                        .transition(.opacity.combined(with: .scale(scale: 0.9, anchor: .bottomLeading)))
                case .gap:
                    Capsule().fill(DS.Palette.ink.opacity(0.18))
                        .frame(width: 64, height: 2)
                        .padding(.top, 26)
                }
            }
        }
        .font(DS.Typography.title)
        .animation(DS.Motion.snappy, value: match)
        .accessibilityElement()
        .accessibilityLabel(spoken)
    }

    private enum Token {
        case word(String, heard: Bool)
        case said(String)
        case gap
    }

    private var tokens: [(id: String, token: Token)] {
        match.pieces.enumerated().flatMap { index, piece -> [(id: String, token: Token)] in
            switch piece {
            case let .word(word, heard): [("w\(index)", .word(word, heard: heard))]
            case let .blank(text) where text.isEmpty: [("g\(index)", .gap)]
            case let .blank(text):
                text.split(separator: " ").enumerated().map { offset, word in ("b\(index)-\(offset)", .said(String(word))) }
            }
        }
    }

    private var spoken: String {
        match.pieces.map { piece in
            switch piece {
            case let .word(word, _): word
            case let .blank(text): text.isEmpty ? "…" : text
            }
        }
        .joined(separator: " ")
    }
}

/// Where the audio comes from and the input level, in one quiet line. The dot is still: red
/// while listening, gray otherwise.
struct ListeningLine: View {
    let voice: VoiceIntroStore

    var body: some View {
        HStack(spacing: DS.Spacing.md) {
            HStack(spacing: DS.Spacing.sm) {
                Circle()
                    .fill(voice.isListening ? DS.Palette.live : DS.Palette.inkTertiary)
                    .frame(width: 7, height: 7)
                Text(voice.isListening ? L("nativeListening") : L("nativeConnecting"))
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DS.Palette.inkSecondary)
            }
            .fixedSize()
            LevelBars(level: voice.isListening ? voice.level : 0, height: 16)
            Label(
                voice.source == .device ? L("nativeSourceOmi") : L("nativeSourceIphone"),
                systemImage: voice.source == .device ? "circle.circle" : "iphone"
            )
            .font(.footnote)
            .foregroundStyle(DS.Palette.inkTertiary)
            .fixedSize()
        }
        .accessibilityElement(children: .combine)
    }
}
