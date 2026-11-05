import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// One app's page (Flutter `app_detail.dart`): what it does, setup, get / remove / subscribe, chat
/// with it, reviews (and the user's own rating), share.
struct AppDetailScreen: View {
    @Environment(AppCatalogStore.self) private var catalog
    @Environment(ChatStore.self) private var chat
    @Environment(\.openChat) private var openChat
    @Environment(\.openURL) private var openURL
    let appID: String
    let preview: OmiApp
    @State private var notice: String?
    @State private var working = false
    @State private var confirmsCancel = false
    @State private var purchase: Task<Void, Never>?

    var body: some View {
        let detail = catalog.details[appID]
        let app = detail?.app ?? preview
        SettingsList {
            header(app, detail: detail)
            if let detail, !detail.setupSteps.isEmpty || detail.setupInstructionsURL != nil || detail.setupInstructionsText != nil {
                setupSection(detail)
            }
            if !app.description.isEmpty {
                Section(L("nativeAppAbout")) { MarkdownBlocks(app.description).padding(.vertical, DS.Spacing.xxs) }
            }
            if let detail { promptsSection(detail) }
            if let detail, detail.app.isPaid { paymentSection(detail) }
            if let detail { AppReviewsSection(detail: detail) }
        }
        .omiPage(app.name)
        .toolbar {
            if let url = detail?.shareURL {
                ToolbarItem(placement: .topBarTrailing) {
                    ShareLink(item: url, subject: Text(app.name)) { Image(systemName: "square.and.arrow.up") }
                        .accessibilityLabel(L("share"))
                }
            }
        }
        .task { await catalog.loadDetail(appID) }
        .onDisappear { purchase?.cancel() }
        .alert(notice ?? "", isPresented: Binding(get: { notice != nil }, set: { if !$0 { notice = nil } })) {
            Button(L("ok"), role: .cancel) {}
        }
    }

    private func header(_ app: OmiApp, detail: AppDetail?) -> some View {
        Section {
            HStack(spacing: DS.Spacing.md) {
                AppIcon(url: app.imageURL, name: app.name, size: 64)
                VStack(alignment: .leading, spacing: DS.Spacing.xxs) {
                    Text(app.name).font(DS.Typography.sectionTitle)
                    if let author = app.author { Text(author).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary) }
                    HStack(spacing: DS.Spacing.sm) {
                        if let rating = app.rating, app.ratingCount > 0 {
                            Label(rating.formatted(.number.precision(.fractionLength(1))), systemImage: "star.fill")
                        }
                        Text(L("nativeAppInstalls", app.installs.formatted()))
                        if app.isPaid, let price = app.price {
                            Text(price.formatted(.currency(code: "USD")))
                        }
                    }
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.inkTertiary)
                }
            }
            .padding(.vertical, DS.Spacing.xs)
            // The header sits on the page (like an App Store listing); the actions under it.
            .listRowBackground(Color.clear)
            .listRowSeparator(.hidden)
            .listRowInsets(EdgeInsets(top: 0, leading: DS.Spacing.gutter, bottom: 0, trailing: DS.Spacing.gutter))
            primaryAction(app, detail: detail)
            if app.isEnabled, app.worksWithChat {
                Button {
                    Task {
                        await chat.talk(to: app)
                        openChat()
                    }
                } label: {
                    Label(L("nativeAppChatWith", app.name), systemImage: "bubble.left.and.bubble.right")
                }
                .buttonStyle(.omiSecondary)
                .listRowInsets(EdgeInsets(top: DS.Spacing.sm, leading: DS.Spacing.gutter, bottom: 0, trailing: DS.Spacing.gutter))
                .listRowBackground(Color.clear)
                .listRowSeparator(.hidden)
                .accessibilityIdentifier("app.chat")
            }
        }
    }

    @ViewBuilder
    private func primaryAction(_ app: OmiApp, detail: AppDetail?) -> some View {
        if detail?.needsPurchase == true, let link = detail?.paymentLink {
            Button {
                openURL(link)
                purchase?.cancel()
                purchase = Task { await catalog.awaitPurchase(appID) }
            } label: {
                if catalog.awaitingPurchase.contains(appID) {
                    Label(L("nativeAppWaitingForPayment"), systemImage: "hourglass")
                } else {
                    Text(app.price.map { L("nativeAppSubscribePrice", $0.formatted(.currency(code: "USD"))) } ?? L("nativeAppSubscribe"))
                }
            }
            .buttonStyle(OmiPrimaryButtonStyle())
            .listRowInsets(EdgeInsets(top: DS.Spacing.sm, leading: DS.Spacing.gutter, bottom: 0, trailing: DS.Spacing.gutter))
            .listRowBackground(Color.clear)
            .listRowSeparator(.hidden)
        } else {
            Button {
                Task {
                    working = true
                    if let reason = await catalog.setEnabled(app, !app.isEnabled) {
                        notice = reason == L10nFallback.couldNotChange ? L("nativeAppCouldNotChange") : reason
                    } else if !app.isEnabled, let home = detail?.homeURL {
                        openURL(catalog.signedSetupURL(home))
                    }
                    working = false
                }
            } label: {
                Text(app.isEnabled ? L("nativeRemove") : L("nativeGet"))
            }
            .buttonStyle(app.isEnabled ? AnyButtonStyle(OmiSecondaryButtonStyle()) : AnyButtonStyle(OmiPrimaryButtonStyle()))
            .disabled(working)
            .listRowInsets(EdgeInsets(top: DS.Spacing.sm, leading: DS.Spacing.gutter, bottom: 0, trailing: DS.Spacing.gutter))
            .listRowBackground(Color.clear)
            .listRowSeparator(.hidden)
            .accessibilityIdentifier("app.toggle")
        }
    }

    private func setupSection(_ detail: AppDetail) -> some View {
        Section {
            ForEach(Array(detail.setupSteps.enumerated()), id: \.offset) { index, step in
                Link(destination: catalog.signedSetupURL(step.url)) {
                    Label("\(index + 1). \(step.name)", systemImage: "arrow.up.right.square")
                }
            }
            if let url = detail.setupInstructionsURL {
                Link(L("nativeAppSetupGuide"), destination: url)
            }
            if let text = detail.setupInstructionsText {
                MarkdownBlocks(text)
            }
        } header: {
            SettingsHeader(L("nativeAppSetup"))
        } footer: {
            Text(L("nativeAppSetupFooter"))
        }
    }

    @ViewBuilder
    private func promptsSection(_ detail: AppDetail) -> some View {
        if detail.chatPrompt != nil || detail.conversationPrompt != nil || !detail.app.capabilities.isEmpty {
            Section(L("nativeAppWhatItDoes")) {
                if !detail.app.capabilities.isEmpty {
                    Text(detail.app.capabilities.sorted().map(AppsBrowserScreen.kindTitle).joined(separator: " · "))
                        .font(DS.Typography.callout)
                }
                if let prompt = detail.chatPrompt {
                    DisclosureGroup(L("nativeAppChatPersonality")) { Text(prompt).font(DS.Typography.callout) }
                }
                if let prompt = detail.conversationPrompt {
                    DisclosureGroup(L("nativeAppConversationPrompt")) { Text(prompt).font(DS.Typography.callout) }
                }
            }
        }
    }

    @ViewBuilder
    private func paymentSection(_ detail: AppDetail) -> some View {
        if let subscription = catalog.subscriptions[appID], detail.isUserPaid {
            Section(L("nativeAppSubscription")) {
                if subscription.isActive {
                    Button(L("nativeAppCancelSubscription"), role: .destructive) { confirmsCancel = true }
                } else if let end = subscription.periodEnd {
                    Text(L("nativeAppSubscriptionEnds", end.formatted(date: .abbreviated, time: .omitted)))
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
            }
            .confirmationDialog(L("nativeAppCancelQuestion"), isPresented: $confirmsCancel, titleVisibility: .visible) {
                Button(L("nativeAppCancelSubscription"), role: .destructive) {
                    Task { if await !catalog.cancelSubscription(appID) { notice = L("nativeAppCouldNotChange") } }
                }
            } message: {
                Text(L("nativeAppCancelFooter"))
            }
        }
    }
}

/// Type-erases the two button styles of the Get / Remove button.
struct AnyButtonStyle: ButtonStyle {
    private let make: (Configuration) -> AnyView

    init(_ style: some ButtonStyle) {
        make = { AnyView(style.makeBody(configuration: $0)) }
    }

    func makeBody(configuration: Configuration) -> some View {
        make(configuration)
    }
}
