import OmiComponents
import OmiDesign
import OmiService
import SwiftUI

// MARK: About you

struct NameStep: View {
    @Bindable var store: OnboardingStore
    @FocusState private var focused: Bool

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerAboutYou"), title: L("nativeWhatShouldOmiCallYou"),
            button: StepButton(
                title: L("continueButton"),
                isEnabled: !store.givenName.trimmingCharacters(in: .whitespaces).isEmpty,
                action: { Task { await store.saveName() } }
            )
        ) {
            TextField(L("enterYourName"), text: $store.givenName)
                .font(.title2.weight(.semibold))
                .textContentType(.givenName)
                .submitLabel(.continue)
                .focused($focused)
                .onSubmit { Task { await store.saveName() } }
                .padding(.horizontal, DS.Spacing.lg)
                .frame(height: 60)
                .onboardingCard(padding: 0)
                .padding(.horizontal, DS.Spacing.gutter)
                .onAppear { focused = true }
        }
    }
}

/// Every language the user speaks, as simple as a list can be: the common ones and a search
/// field for the rest. A tap picks, another tap takes it out; the order of the taps is the order
/// of importance (a small 1, 2, 3), the first is the main language. Nothing is picked to begin.
struct LanguageStep: View {
    @Bindable var store: OnboardingStore
    @State private var search = ""
    @FocusState private var searching: Bool

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerAboutYou"), title: L("nativeWhichLanguages"), subtitle: L("nativeLanguagesTapHint"),
            button: StepButton(
                title: L("continueButton"), isEnabled: !store.spokenLanguages.isEmpty,
                action: { Task { await store.saveLanguage() } }
            ),
            scrolls: false
        ) {
            VStack(spacing: DS.Spacing.md) {
                searchField
                // The common languages show at once; only searching the full list waits for it.
                if store.languages.isEmpty, !search.isEmpty {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, DS.Spacing.xl)
                } else {
                    list
                }
                if let error = store.errorMessage {
                    Text(error).font(DS.Typography.caption).foregroundStyle(DS.Palette.live)
                }
            }
            .padding(.horizontal, DS.Spacing.gutter)
        }
        .task { await store.loadLanguages() }
    }

    private var searchField: some View {
        HStack(spacing: DS.Spacing.sm) {
            Image(systemName: "magnifyingglass").foregroundStyle(DS.Palette.inkTertiary)
            TextField(L("nativeSearchLanguages"), text: $search)
                .focused($searching)
                .autocorrectionDisabled()
                .submitLabel(.done)
            if !search.isEmpty {
                Button { search = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(DS.Palette.inkTertiary) }
                    .buttonStyle(.plain)
                    .accessibilityLabel(L("nativeClearSearch"))
            }
        }
        .padding(.horizontal, DS.Spacing.lg)
        .frame(height: 48)
        .onboardingCard(padding: 0)
    }

    private var list: some View {
        let rows = store.languageRows(matching: search)
        return ScrollView {
            VStack(spacing: 0) {
                ForEach(Array(rows.enumerated()), id: \.element.code) { index, language in
                    LanguageRow(name: language.name, rank: store.rank(of: language.code)) {
                        withAnimation(DS.Motion.snappy) { store.toggleLanguage(language.code) }
                        if !search.isEmpty {
                            search = ""
                            searching = false
                        }
                    }
                    .accessibilityIdentifier("onboarding.language.\(language.code)")
                    if index < rows.count - 1 {
                        Rectangle().fill(DS.Palette.ink.opacity(0.08)).frame(height: 0.5).padding(.leading, DS.Spacing.lg)
                    }
                }
                if rows.isEmpty {
                    Text(L("nativeNoLanguageMatches"))
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .frame(maxWidth: .infinity, minHeight: 52)
                }
            }
            .onboardingCard(padding: 0)
        }
        .scrollIndicators(.hidden)
        .scrollBounceBehavior(.basedOnSize)
        .scrollDismissesKeyboard(.immediately)
    }
}

/// A language: its name, and when picked its place (1 is the main language) in a small badge.
private struct LanguageRow: View {
    let name: String
    let rank: Int?
    let action: () -> Void

    var body: some View {
        Button {
            DSHaptics.selection()
            action()
        } label: {
            HStack(spacing: DS.Spacing.md) {
                Text(name)
                    .font(.body.weight(rank == nil ? .regular : .semibold))
                    .foregroundStyle(DS.Palette.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                ZStack {
                    if let rank {
                        Circle().fill(DS.Palette.agent)
                        Text("\(rank)")
                            .font(.footnote.weight(.bold))
                            .foregroundStyle(.white)
                            .contentTransition(.numericText())
                    } else {
                        Circle().strokeBorder(DS.Palette.ink.opacity(0.22), lineWidth: 1.5)
                    }
                }
                .frame(width: 26, height: 26)
            }
            .padding(.horizontal, DS.Spacing.lg)
            .frame(height: 48)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(rank == nil ? [] : [.isSelected])
        .accessibilityValue(rank.map { L("nativeLanguageRank", String($0)) } ?? "")
    }
}

struct SourceStep: View {
    let store: OnboardingStore
    @State private var picked: String?
    private let options = ["Friend", "TikTok", "Instagram", "YouTube", "X / Twitter", "Reddit", "Podcast", "Google", "Other"]

    var body: some View {
        OnboardingLayout(
            kicker: L("nativeKickerAboutYou"), title: L("whereDidYouHearAboutOmi"),
            button: StepButton(title: L("continueButton"), isEnabled: picked != nil, action: { store.saveSource(picked) }),
            secondary: StepButton(title: L("skip"), action: { store.saveSource(nil) })
        ) {
            FlowLayout(spacing: DS.Spacing.sm) {
                ForEach(options, id: \.self) { option in
                    Button {
                        DSHaptics.selection()
                        picked = option
                    } label: {
                        Text(option)
                            .font(.body.weight(.medium))
                            .foregroundStyle(picked == option ? DS.Palette.onAccent : DS.Palette.ink)
                            .padding(.horizontal, DS.Spacing.lg)
                            .frame(minHeight: 44)
                            .background(
                                picked == option ? AnyShapeStyle(DS.Palette.accent) : AnyShapeStyle(DS.Palette.ink.opacity(0.07)),
                                in: Capsule()
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, DS.Spacing.gutter)
        }
    }
}
