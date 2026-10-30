import OmiComponents
import OmiCore
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Speakers in the transcript: tapping a label asks "Who is this?"; after a change Omi offers to
/// rewrite the summary with the names and to label the same voice elsewhere. Used by `TranscriptView`.
extension TranscriptView {
    func speakerLabel(_ line: ConversationDetail.Line) -> some View {
        Button {
            DSHaptics.selection()
            naming = line
        } label: {
            Text(settings.speakerName(line))
                .font(DS.Typography.caption.weight(.medium))
                .foregroundStyle(DS.Palette.inkSecondary)
                .padding(.vertical, DS.Spacing.xxs)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(line.segmentID == nil)
        .accessibilityHint(L("speakerTagPromptWhoIsThis"))
        .accessibilityIdentifier("transcript.speaker.\(line.id)")
    }

    /// Follow-ups after a name changed: rewrite the summary, review the same voice elsewhere.
    @ViewBuilder
    var speakerTools: some View {
        if speakers.offersSummaryRefresh {
            Button {
                Task {
                    await speakers.refreshSummary()
                    await conversations.load()
                }
            } label: {
                HStack(spacing: DS.Spacing.sm) {
                    if speakers.isRefreshingSummary { ProgressView() } else { Image(systemName: "arrow.clockwise") }
                    Text(L("updateSummaryWithNewNames"))
                }
                .font(DS.Typography.callout.weight(.medium))
            }
            .buttonStyle(.omiPillSubtle)
            .disabled(speakers.isRefreshingSummary)
            .accessibilityIdentifier("transcript.updateSummary")
        }
        if let matches = speakers.matches, !matches.items.isEmpty {
            HStack(alignment: .top, spacing: DS.Spacing.md) {
                Image(systemName: "waveform.badge.magnifyingglass").foregroundStyle(DS.Palette.agent)
                VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                    Text(L("nativeVoiceMatchesTitle", matches.person.name)).font(DS.Typography.cardTitle)
                    Text(L("nativeVoiceMatchesBody", String(matches.items.count)))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                    Button(L("nativeVoiceMatchesReview")) { reviewsMatches = true }
                        .buttonStyle(.omiPill)
                        .padding(.top, DS.Spacing.xs)
                }
                Spacer(minLength: 0)
                Button { speakers.dismissMatches() } label: { Image(systemName: "xmark") }
                    .foregroundStyle(DS.Palette.inkTertiary)
                    .accessibilityLabel(L("close"))
            }
            .omiCard(padding: DS.Spacing.md)
        }
        if speakers.lastError != nil {
            Text(L("speakerTagPromptAnswerFailed"))
                .font(DS.Typography.caption)
                .foregroundStyle(DS.Palette.live)
        }
    }
}

extension SettingsStore {
    /// "You", the person's name, or "Speaker N" for a voice nobody named yet.
    func speakerName(_ line: ConversationDetail.Line) -> String {
        if line.isUser { return L("nativeSpeakerYou") }
        if let id = line.personID, let person = person(id), !person.name.isEmpty { return person.name }
        if let speakerID = line.speakerID { return L("speakerWithId", String(speakerID + 1)) }
        return line.speaker
    }
}
