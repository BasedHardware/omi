import OmiComponents
import OmiDesign
import OmiNetwork
import OmiService
import SwiftUI

/// Plan & usage › the plans: Monthly or Yearly (with what yearly saves), one card per plan
/// (kicker, name, what it gives, price), a promo code, and the one button. Free or cancelled:
/// Stripe's checkout opens in the app (`onCheckout`). A running plan: switching asks first.
/// Never pays by itself.
struct PlanPickerSection: View {
    @Bindable var store: PlanStore
    let onCheckout: (URL) -> Void
    @State private var confirmsChange = false
    @State private var showsPromo = false

    var body: some View {
        if store.plansUnavailable {
            Section {
                VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                    Text(L("nativePlanUnavailable")).foregroundStyle(DS.Palette.ink)
                    Text(L("nativePlanUnavailableBody")).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                }
                .padding(.vertical, DS.Spacing.xxs)
                Button(L("nativeTryAgain")) { Task { await store.load() } }
                    .foregroundStyle(DS.Palette.ink)
                    .accessibilityIdentifier("plan.retry")
            } header: {
                SettingsHeader(title)
            }
        } else if !store.tiers.isEmpty {
            Section {
                if store.offersBothIntervals { intervalSwitch.plainSettingsRow() }
                ForEach(store.tiers) { tier in
                    PlanCard(tier: tier, interval: store.interval, isSelected: tier.id == store.selectedTier?.id) {
                        DSHaptics.selection()
                        store.selectedTierID = tier.id
                    }
                    .plainSettingsRow()
                    .padding(.top, DS.Spacing.sm)
                }
                promo.plainSettingsRow(inset: DS.Spacing.lg)
                button.plainSettingsRow()
            } header: {
                SettingsHeader(title)
            } footer: {
                if let footer { Text(footer).padding(.top, DS.Spacing.xs) }
            }
        }
    }

    private var title: String {
        guard let subscription = store.subscription else { return L("nativePlanUpgradeTitle") }
        if subscription.isPaid { return subscription.cancelAtPeriodEnd ? L("nativePlanResubscribeTitle") : L("nativePlanChangeTitle") }
        return L("nativePlanUpgradeTitle")
    }

    /// Monthly | Yearly · save 25 %, as two quiet capsules (the chips on Home).
    private var intervalSwitch: some View {
        HStack(spacing: DS.Spacing.sm) {
            chip(L("nativePlanMonthly"), .month)
            chip(PlanCatalog.bestSavingsPercent(store.tiers).map { L("nativePlanYearlySave", String($0)) } ?? L("nativePlanYearly"), .year)
            Spacer(minLength: 0)
        }
        .padding(.top, DS.Spacing.xs)
    }

    private func chip(_ text: String, _ interval: PlanOffer.Interval) -> some View {
        let selected = store.interval == interval
        return Button {
            DSHaptics.selection()
            store.interval = interval
        } label: {
            Text(text)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(selected ? DS.Palette.onAccent : DS.Palette.ink)
                .padding(.horizontal, DS.Spacing.lg)
                .padding(.vertical, DS.Spacing.sm)
                .background(selected ? DS.Palette.ink : DS.Palette.card, in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("plan.interval.\(interval.rawValue)")
    }

    /// "Promo code" opens one field; the code goes with checkout or the switch.
    @ViewBuilder
    private var promo: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            Button {
                withAnimation(DS.Motion.gentle) { showsPromo.toggle() }
            } label: {
                HStack(spacing: DS.Spacing.xs) {
                    Image(systemName: "tag").accessibilityHidden(true)
                    Text(L("promoCode"))
                    Image(systemName: showsPromo ? "chevron.up" : "chevron.down").font(DS.Typography.caption)
                }
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.inkSecondary)
                .frame(minHeight: 36)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("plan.promo")
            if showsPromo {
                TextField(L("enterPromoCode"), text: $store.promoCode)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                    .padding(.horizontal, DS.Spacing.lg)
                    .frame(minHeight: DS.Size.searchField)
                    .omiSurface(Capsule())
            }
        }
        .padding(.top, DS.Spacing.sm)
    }

    @ViewBuilder
    private var button: some View {
        if let purchase = store.purchase {
            Button {
                if case .change = purchase { confirmsChange = true } else { Task { await buy() } }
            } label: {
                HStack(spacing: DS.Spacing.sm) {
                    if store.isWorking { ProgressView().tint(DS.Palette.onAccent) }
                    Text(buttonTitle(purchase))
                }
            }
            .buttonStyle(.omiPrimary)
            .disabled(store.isWorking || purchase == .current || purchase == .managedElsewhere)
            .padding(.top, DS.Spacing.sm)
            .accessibilityIdentifier("plan.buy")
            .confirmationDialog(confirmTitle, isPresented: $confirmsChange, titleVisibility: .visible) {
                Button(L("nativePlanSwitch")) { Task { await buy() } }
            } message: {
                Text(confirmMessage)
            }
        }
    }

    private func buy() async {
        if let url = await store.buy() { onCheckout(url) }
    }

    private var tierName: String {
        store.selectedTier?.title ?? ""
    }

    private func buttonTitle(_ purchase: PlanPurchase) -> String {
        switch purchase {
        case .current: return L("nativePlanIsCurrent")
        case .managedElsewhere: return L("nativePlanSwitchTo", tierName)
        case .change: return L("nativePlanSwitchTo", tierName)
        case .checkout:
            if store.subscription?.cancelAtPeriodEnd == true { return L("resubscribe") }
            return L("nativeUpgradeTo", tierName)
        }
    }

    private var confirmTitle: String {
        L("nativePlanConfirmSwitch", tierName)
    }

    /// Same plan, monthly to yearly: starts when the period ends. Another plan: now, prorated.
    private var confirmMessage: String {
        store.selectedTier?.isCurrent == true ? L("nativePlanConfirmYearlyBody") : L("nativePlanConfirmSwitchBody", tierName)
    }

    private var footer: String? {
        switch store.purchase {
        case .checkout: L("nativePlanCheckoutFooter")
        case .change: L("nativePlanChangeFooter")
        case .managedElsewhere: L("nativePlanManagedOnMac")
        case .current, .none: nil
        }
    }
}

/// One plan as a card (Home's decision cards): a colored kicker ("Most popular"), the name and its
/// one line, the price on the right, what it includes as check lines. The chosen one has an ink
/// edge and a check.
struct PlanCard: View {
    let tier: PlanTier
    let interval: PlanOffer.Interval
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            VStack(alignment: .leading, spacing: DS.Spacing.sm) {
                HStack {
                    if let kicker {
                        Text(kicker.text)
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(kicker.color)
                    }
                    Spacer(minLength: DS.Spacing.sm)
                    // A radio, as in a system picker: the chosen plan filled.
                    Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 20, weight: .regular))
                        .foregroundStyle(isSelected ? DS.Palette.ink : DS.Palette.inkTertiary)
                        .accessibilityHidden(true)
                }
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(tier.title).font(DS.Typography.sectionTitle).foregroundStyle(DS.Palette.ink)
                        if let subtitle = tier.subtitle, !tier.features.contains(subtitle) {
                            Text(subtitle).font(DS.Typography.callout).foregroundStyle(DS.Palette.inkSecondary)
                        }
                    }
                    Spacer(minLength: DS.Spacing.sm)
                    price
                }
                if !tier.features.isEmpty {
                    VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                        ForEach(tier.features, id: \.self) { feature in
                            HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.sm) {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundStyle(DS.Palette.inkSecondary)
                                    .accessibilityHidden(true)
                                Text(feature).font(DS.Typography.callout).foregroundStyle(DS.Palette.ink)
                            }
                        }
                    }
                    .padding(.top, DS.Spacing.xxs)
                }
            }
            .multilineTextAlignment(.leading)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(DS.Spacing.lg)
            .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous)
                    .strokeBorder(isSelected ? DS.Palette.ink : DS.Palette.cardStroke, lineWidth: isSelected ? 1.5 : 1)
            }
            .contentShape(RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityIdentifier("plan.tier.\(tier.id)")
    }

    /// "Current" (gray) on the plan paid now, else the backend's eyebrow in Omi blue.
    private var kicker: (text: String, color: Color)? {
        if tier.isCurrent { return (L("nativePlanCurrent"), DS.Palette.success) }
        return tier.eyebrow.map { ($0, DS.Palette.agent) }
    }

    /// Prices are US dollars written the backend's way ("$161.91"), whatever the region.
    static let usd = FloatingPointFormatStyle<Double>.Currency(code: "USD").locale(Locale(identifier: "en_US"))

    /// "$13/mo", and for yearly what is billed once a year.
    private var price: some View {
        let offer = tier.offer(interval) ?? tier.offer(interval == .year ? .month : .year)
        return VStack(alignment: .trailing, spacing: 2) {
            if let offer {
                Text(offer.priceString).font(.body.weight(.semibold)).foregroundStyle(DS.Palette.ink).monospacedDigit()
                if offer.interval == .year, let amount = offer.unitAmount {
                    Text(L("nativePlanBilledYearly", (Double(amount) / 100).formatted(Self.usd)))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
            }
        }
    }
}
