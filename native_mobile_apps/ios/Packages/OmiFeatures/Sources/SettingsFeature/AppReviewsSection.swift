import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// An app's reviews and, once the app is on (and not the user's own), the user's own rating.
struct AppReviewsSection: View {
    @Environment(AppCatalogStore.self) private var catalog
    let detail: AppDetail
    @State private var score = 0
    @State private var text = ""
    @State private var saving = false
    @State private var failed = false

    var body: some View {
        Section {
            if detail.app.isEnabled, !detail.isOwn { yourRating }
            if detail.reviews.isEmpty {
                Text(L("nativeAppNoReviews")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
            }
            ForEach(detail.reviews) { review in
                VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                    HStack {
                        Stars(score: Int(review.score.rounded()))
                        Text(review.username ?? L("nativeAppAnonymous")).font(DS.Typography.caption.weight(.semibold))
                        Spacer()
                        if let date = review.ratedAt {
                            Text(date.formatted(date: .abbreviated, time: .omitted))
                                .font(DS.Typography.caption)
                                .foregroundStyle(DS.Palette.inkTertiary)
                        }
                    }
                    Text(review.text).font(DS.Typography.callout)
                    if let response = review.response {
                        Text(L("nativeAppDeveloperReply", response))
                            .font(DS.Typography.caption)
                            .foregroundStyle(DS.Palette.inkSecondary)
                            .padding(.leading, DS.Spacing.md)
                    }
                }
                .padding(.vertical, DS.Spacing.xxs)
            }
        } header: {
            if detail.app.ratingCount > 0, let rating = detail.app.rating {
                Text(L("nativeAppReviewsSummary", rating.formatted(.number.precision(.fractionLength(1))), String(detail.app.ratingCount)))
            } else {
                Text(L("nativeAppReviews"))
            }
        }
        .onAppear {
            score = Int(detail.userReview?.score.rounded() ?? 0)
            text = detail.userReview?.text ?? ""
        }
        .alert(L("nativeAppReviewFailed"), isPresented: $failed) { Button(L("ok"), role: .cancel) {} }
    }

    private var yourRating: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            Text(detail.userReview == nil ? L("nativeAppRateIt") : L("nativeAppYourRating")).font(DS.Typography.cardTitle)
            HStack(spacing: DS.Spacing.sm) {
                ForEach(1 ... 5, id: \.self) { value in
                    Button { score = value } label: {
                        Image(systemName: value <= score ? "star.fill" : "star")
                            .font(.title3)
                            .foregroundStyle(value <= score ? DS.Palette.warning : DS.Palette.inkTertiary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(L("nativeAppStars", String(value)))
                    .accessibilityAddTraits(value == score ? .isSelected : [])
                }
            }
            TextField(L("nativeAppReviewPlaceholder"), text: $text, axis: .vertical)
                .lineLimit(1 ... 4)
                .font(DS.Typography.callout)
            Button(detail.userReview == nil ? L("nativeAppPostReview") : L("nativeAppUpdateReview")) {
                Task {
                    saving = true
                    failed = !(await catalog.review(detail.app.id, score: score, text: text))
                    saving = false
                }
            }
            .buttonStyle(.bordered)
            .disabled(score == 0 || saving)
            .accessibilityIdentifier("app.review.save")
        }
        .padding(.vertical, DS.Spacing.xs)
    }
}

struct Stars: View {
    let score: Int

    var body: some View {
        HStack(spacing: 1) {
            ForEach(1 ... 5, id: \.self) { value in
                Image(systemName: value <= score ? "star.fill" : "star")
            }
        }
        .font(.caption2)
        .foregroundStyle(DS.Palette.warning)
        .accessibilityElement()
        .accessibilityLabel(L("nativeAppStars", String(score)))
    }
}
