import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Account › Plan & usage, one screen for Flutter's `usage_page`, plans sheet and `fair_use_page`:
/// the plan (renews or ends when), this month's meters against its limits, the plans to choose
/// from with Monthly or Yearly and the one button that upgrades (paid on Stripe's page in the
/// app), payment method and cancelling, then what Omi heard and the fair-use limits.
struct PlanUsageScreen: View {
    @Environment(SettingsStore.self) private var settings
    @State private var store: PlanStore?
    @State private var usage: UsageStore?
    @State private var browser: BrowserItem?
    /// The open page is Stripe's checkout (not the portal): coming back reads the plan again.
    @State private var browsingCheckout = false
    @State private var showsCancel = false

    var body: some View {
        ScrollViewReader { proxy in
            list.task(id: store?.subscription == nil) { await debugScroll(proxy) }
        }
    }

    /// `-omiPlanScroll plans|manage|activity|fairUse` (Debug): scrolls there for screenshots.
    private func debugScroll(_ proxy: ScrollViewProxy) async {
        guard let target = DebugLaunch.string("omiPlanScroll"), store?.subscription != nil else { return }
        try? await Task.sleep(for: .seconds(1.5))
        proxy.scrollTo(target, anchor: .top)
    }

    private var list: some View {
        SettingsList {
            if let store {
                PlanSummarySection(store: store)
                if let subscription = store.subscription {
                    if !store.meters.isEmpty { MetersSection(store: store, subscription: subscription) }
                    if subscription.showSubscriptionUI {
                        PlanPickerSection(store: store) { url in
                            browsingCheckout = true
                            browser = BrowserItem(url)
                        }
                        .id("plans")
                    }
                    manage(store, subscription).id("manage")
                } else if store.failed {
                    Section { retry(L("nativeCouldNotLoad")) { await store.load() } }
                } else {
                    Section { ProgressView().frame(maxWidth: .infinity, minHeight: 80) }
                }
            }
            if let usage {
                ActivitySection(store: usage).id("activity")
                FairUseSection(store: usage).id("fairUse")
            }
        }
        .omiPage(L("nativeSettingsPlanUsage"))
        .toolbar {
            if let usage, let stats = usage.current, !stats.totals.isEmpty {
                ShareLink(item: ActivitySection.shareText(stats.totals, period: usage.period)) {
                    Image(systemName: "square.and.arrow.up")
                }
                .accessibilityLabel(L("share"))
            }
        }
        .task {
            let plans = store ?? settings.makePlanStore()
            store = plans
            let activity = usage ?? settings.makeUsageStore()
            usage = activity
            await plans.load()
            await activity.loadFairUse()
        }
        .refreshable {
            await store?.load()
            await settings.loadSubscription()
            await usage?.load()
            await usage?.loadFairUse()
        }
        .sheet(item: $browser, onDismiss: returned) { SafariView(url: $0.url) }
        .sheet(isPresented: $showsCancel, onDismiss: returned) {
            CancelSubscriptionSheet(store: settings.makeProfileStore())
        }
    }

    /// Back from Stripe (checkout or portal) or the cancel sheet: the plan may have changed.
    private func returned() {
        let wasCheckout = browsingCheckout
        browsingCheckout = false
        Task {
            if wasCheckout { await store?.returnedFromCheckout() } else { await store?.load() }
            await settings.loadSubscription()
        }
    }

    /// Payment method and invoices (Stripe's portal), and cancelling a running plan.
    @ViewBuilder
    private func manage(_ store: PlanStore, _ subscription: Subscription) -> some View {
        if subscription.isPaid || subscription.hasStripeSubscription {
            Section {
                Button {
                    Task {
                        if let url = await store.portalURL() {
                            browsingCheckout = false
                            browser = BrowserItem(url)
                        }
                    }
                } label: {
                    HStack {
                        SettingsRowLabel(title: L("nativePlanManage"), systemImage: "creditcard")
                        Spacer()
                        Image(systemName: "arrow.up.right").font(DS.Typography.caption).foregroundStyle(DS.Palette.inkTertiary)
                    }
                }
                .accessibilityIdentifier("plan.portal")
                if subscription.isPaid, !subscription.cancelAtPeriodEnd {
                    Button(role: .destructive) { showsCancel = true } label: {
                        SettingsRowLabel(title: L("nativeCancelSubscription"), systemImage: "xmark.circle", tint: DS.Palette.live)
                            .foregroundStyle(DS.Palette.live)
                    }
                    .accessibilityIdentifier("account.cancelSubscription")
                }
            }
        }
    }

    /// "Free", or the paid plan's name.
    static func planName(_ subscription: Subscription) -> String {
        PlanCatalog.paidPlanName(subscription) ?? L("nativePlanFree")
    }
}

/// The plan as the page's headline, as Home shows its title: the name big, one gray line under it
/// (renews, ends, or what the free plan includes), and what the last action did.
private struct PlanSummarySection: View {
    let store: PlanStore

    var body: some View {
        Section {
            VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                Text(L("nativePlanYourPlan"))
                    .font(DS.Typography.sectionLabel)
                    .foregroundStyle(DS.Palette.inkSecondary)
                Text(store.subscription.map(PlanUsageScreen.planName) ?? " ")
                    .font(DS.Typography.display)
                    .foregroundStyle(DS.Palette.ink)
                    .redacted(reason: store.subscription == nil ? .placeholder : [])
                if let line = statusLine {
                    Text(line.text)
                        .font(DS.Typography.callout)
                        .foregroundStyle(line.warns ? DS.Palette.warning : DS.Palette.inkSecondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, DS.Spacing.lg)
            .padding(.bottom, DS.Spacing.xs)
            .accessibilityElement(children: .combine)
            .plainSettingsRow()
            if let notice = store.notice { NoticeRow(notice: notice) { store.dismissNotice() } }
        }
    }

    private var statusLine: (text: String, warns: Bool)? {
        guard let subscription = store.subscription else { return nil }
        guard subscription.isPaid else { return (L("nativePlanFreeLine"), false) }
        let price = store.tiers.first(where: \.isCurrent).flatMap { tier in
            [tier.monthly, tier.annual].compactMap { $0 }.first(where: \.isActive)
        }
        guard let end = subscription.currentPeriodEnd else { return price.map { ($0.priceString, false) } }
        let date = end.formatted(date: .long, time: .omitted)
        if subscription.cancelAtPeriodEnd {
            return (end < .now ? L("nativePlanEndedOn", date) : L("nativePlanEndsOn", date), true)
        }
        let renews = L("nativePlanRenewsOn", date)
        return (price.map { "\($0.priceString) · \(renews)" } ?? renews, false)
    }
}

/// One line saying what the last action did: green when it worked, red when it did not.
private struct NoticeRow: View {
    let notice: PlanStore.Notice
    let onDismiss: () -> Void

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
            Image(systemName: isError ? "exclamationmark.circle" : "checkmark.circle")
                .foregroundStyle(isError ? DS.Palette.live : DS.Palette.success)
                .accessibilityHidden(true)
            Text(text).font(DS.Typography.callout).foregroundStyle(DS.Palette.ink)
            Spacer(minLength: 0)
            Button(action: onDismiss) {
                Image(systemName: "xmark").font(DS.Typography.caption).foregroundStyle(DS.Palette.inkTertiary)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(L("close"))
        }
        .accessibilityIdentifier("plan.notice")
    }

    private var isError: Bool {
        switch notice {
        case .refused, .unreachable: true
        default: false
        }
    }

    private var text: String {
        switch notice {
        case let .upgraded(plan): L("nativePlanNoticeUpgraded", plan)
        case let .reactivated(message): message ?? L("nativePlanNoticeReactivated")
        case let .changed(message): message ?? L("nativePlanNoticeChanged")
        case let .refused(reason): reason
        case .unreachable: L("nativePlanNoticeUnreachable")
        }
    }
}

/// This month against the plan's limits: listening minutes, chat questions, and words or insights
/// where the plan limits them. A thin bar under each, amber from 80 %, red at the limit.
private struct MetersSection: View {
    let store: PlanStore
    let subscription: Subscription

    var body: some View {
        Section {
            ForEach(store.meters) { meter in
                VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                    HStack {
                        Text(title(meter.kind)).foregroundStyle(DS.Palette.ink)
                        Spacer(minLength: DS.Spacing.sm)
                        Text(value(meter)).foregroundStyle(DS.Palette.inkSecondary).monospacedDigit()
                    }
                    if let fraction = meter.fraction {
                        OmiMeterBar(fraction: fraction, tint: tint(meter))
                    }
                }
                .padding(.vertical, DS.Spacing.xxs)
                .accessibilityElement(children: .combine)
            }
        } header: {
            SettingsHeader(L("nativePlanThisMonth"))
        } footer: {
            if let footer { Text(footer) }
        }
    }

    private var footer: String? {
        let resets = subscription.usage.resetsAt?.formatted(.dateTime.month(.wide).day())
        if subscription.isOutOfMinutes, let resets { return L("nativeMeterMinutesUsedUp", resets) }
        return resets.map { L("nativePlanResetsOn", $0) }
    }

    private func tint(_ meter: UsageMeter) -> Color {
        meter.isAtLimit ? DS.Palette.live : meter.isNearLimit ? DS.Palette.warning : DS.Palette.ink
    }

    private func title(_ kind: UsageMeter.Kind) -> String {
        switch kind {
        case .listening: L("nativeMeterListening")
        case .chat: L("nativeMeterChat")
        case .chatSpend: L("nativeMeterChatSpend")
        case .words: L("nativeMeterWords")
        case .insights: L("nativeMeterInsights")
        }
    }

    private func value(_ meter: UsageMeter) -> String {
        let used = format(meter.used, meter.kind)
        guard let limit = meter.limit else { return L("nativeMeterNoLimit", used) }
        return meter.kind == .listening
            ? L("nativeMeterOfMinutes", used, format(limit, meter.kind))
            : L("nativeMeterOf", used, format(limit, meter.kind))
    }

    private func format(_ value: Double, _ kind: UsageMeter.Kind) -> String {
        kind == .chatSpend
            ? value.formatted(PlanCard.usd.precision(.fractionLength(0 ... 2)))
            : Int(value.rounded()).formatted()
    }
}
