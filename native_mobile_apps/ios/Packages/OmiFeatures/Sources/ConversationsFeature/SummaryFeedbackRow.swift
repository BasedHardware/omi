import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// "Was this helpful? · Give feedback · ×" under Omi's own summary, or the same row about the
/// recording, now and then (`SummaryFeedbackStore` decides when and which). "Give feedback" opens
/// the reasons.
struct SummaryFeedbackRow: View {
    let feedback: SummaryFeedbackStore
    @State private var choosing = false

    var body: some View {
        Group {
            switch feedback.state {
            case .hidden:
                EmptyView()
            case .thanked:
                Label(L("nativeThanksForFeedback"), systemImage: "checkmark.circle.fill")
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.success)
                    .task {
                        try? await Task.sleep(for: .seconds(2))
                        withAnimation(DS.Motion.standard) { feedback.finish() }
                    }
            case .asking, .sending, .failed:
                HStack(spacing: DS.Spacing.sm) {
                    VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                        Text(Self.question(feedback.kind)).font(DS.Typography.callout.weight(.medium))
                        if feedback.state == .failed {
                            Text(L("nativeFeedbackNotSent")).font(DS.Typography.caption).foregroundStyle(DS.Palette.live)
                        } else if feedback.kind == .recording {
                            Text(L("feedbackSubtitleAudioQuality")).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                        }
                    }
                    Spacer(minLength: 0)
                    if feedback.state == .sending {
                        ProgressView().controlSize(.small)
                    } else {
                        Button(L("feedbackGiveFeedback")) { choosing = true }
                            .buttonStyle(.omiPillSubtle)
                            .accessibilityIdentifier("summary.feedback")
                    }
                    Button {
                        withAnimation(DS.Motion.standard) { feedback.dismiss() }
                    } label: {
                        Image(systemName: "xmark").font(.footnote.weight(.semibold)).foregroundStyle(DS.Palette.inkTertiary)
                            .frame(width: 28, height: 28)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(L("close"))
                }
                .omiCard(padding: DS.Spacing.md)
            }
        }
        .sheet(isPresented: $choosing) {
            FeedbackReasonsSheet(kind: feedback.kind) { helpful, reason in Task { await feedback.send(helpful: helpful, reason: reason) } }
                .presentationDetents([.height(340)])
        }
    }

    /// The row's and the sheet's question.
    static func question(_ kind: ConversationFeedbackKind) -> String {
        switch kind {
        case .summary: L("wasThisHelpful")
        case .recording: L("feedbackTitleAudioQuality")
        }
    }
}

/// "All good", or what was wrong with the summary or the recording; one tap sends.
private struct FeedbackReasonsSheet: View {
    let kind: ConversationFeedbackKind
    let onPick: (Bool, SummaryFeedbackReason?) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.lg) {
            Text(SummaryFeedbackRow.question(kind)).font(DS.Typography.sectionTitle)
            chip(L("feedbackAllGood"), systemImage: "hand.thumbsup", tint: DS.Palette.success) { pick(true, nil) }
            FlowChips {
                ForEach(SummaryFeedbackReason.reasons(for: kind), id: \.self) { reason in
                    chip(Self.title(reason), systemImage: nil, tint: nil) { pick(false, reason) }
                }
            }
            Spacer(minLength: 0)
        }
        .padding(DS.Spacing.gutter)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.Palette.background)
    }

    private func pick(_ helpful: Bool, _ reason: SummaryFeedbackReason?) {
        DSHaptics.tap()
        onPick(helpful, reason)
        dismiss()
    }

    private func chip(_ title: String, systemImage: String?, tint: Color?, action: @escaping () -> Void) -> some View {
        Button(action: action) { OmiChip(title, systemImage: systemImage, tint: tint) }
            .buttonStyle(.plain)
    }

    static func title(_ reason: SummaryFeedbackReason) -> String {
        switch reason {
        case .inaccurate: L("feedbackReasonSummaryInaccurate")
        case .incomplete: L("feedbackReasonSummaryIncomplete")
        case .irrelevant: L("feedbackReasonSummaryIrrelevant")
        case .wrongContext: L("feedbackReasonSummaryWrongContext")
        case .other: L("feedbackReasonSummaryOther")
        case .missingAudio: L("feedbackReasonRecordingMissingAudio")
        case .poorTranscription: L("feedbackReasonRecordingPoorTranscription")
        case .wrongSpeaker: L("feedbackReasonRecordingWrongSpeaker")
        case .delayedOrStuck: L("feedbackReasonRecordingDelayedOrStuck")
        case .fragmentedOrDuplicated: L("feedbackReasonRecordingFragmentedOrDuplicated")
        case .recordingOther: L("feedbackReasonRecordingOther")
        }
    }
}

/// Chips that wrap onto the next line, each line centred vertically.
struct FlowChips: Layout {
    var spacing: CGFloat = DS.Spacing.sm

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache _: inout ()) -> CGSize {
        let rows = rows(subviews, width: proposal.width ?? .infinity)
        let width = rows.map(\.width).max() ?? 0
        let height = rows.map(\.height).reduce(0, +) + spacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: proposal.width.map { $0.isFinite ? $0 : width } ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal _: ProposedViewSize, subviews: Subviews, cache _: inout ()) {
        var y = bounds.minY
        for row in rows(subviews, width: bounds.width) {
            var x = bounds.minX
            for index in row.items {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y + (row.height - size.height) / 2), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row {
        var items: [Int] = []
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    private func rows(_ subviews: Subviews, width: CGFloat) -> [Row] {
        var rows = [Row()]
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            if !rows[rows.count - 1].items.isEmpty, rows[rows.count - 1].width + spacing + size.width > width { rows.append(Row()) }
            var row = rows[rows.count - 1]
            row.width += (row.items.isEmpty ? 0 : spacing) + size.width
            row.height = max(row.height, size.height)
            row.items.append(index)
            rows[rows.count - 1] = row
        }
        return rows.filter { !$0.items.isEmpty }
    }
}
