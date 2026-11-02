import OmiTheme
import SwiftUI

/// Pure presentation of the ladder-v1 plans payload. Every plan name, price, line and
/// button label is the backend's string; the only client words are sheet chrome (badges,
/// the Monthly chip, expand, manage, empty and error) — the same set mobile keeps in l10n.
struct StorefrontPlansView: View {
  let data: PlanStorefront?
  var loading = false
  var failed = false
  /// Price id whose purchase is in flight; every button is disabled meanwhile.
  var busyPriceId: String?
  var error: String?
  var livePlanId: String?
  /// Expanded "See all plans" on first render (snapshot tests).
  var startExpanded = false
  let onRetry: () -> Void
  let onSelect: (PlanStorefront.Tier, PlanStorefront.Price) -> Void
  let onManage: () -> Void

  @State private var chosen: PlanStorefront.Interval?
  @State private var expanded: Bool?

  var body: some View {
    if let data, !data.showSubscriptionUi {
      EmptyView()
    } else {
      content
    }
  }

  private var legacy: Bool { data?.current?.legacy == true }

  private var content: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.lg) {
      if let data {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          if let header = data.header {
            Text(header)
              .scaledFont(size: OmiType.heading, weight: .bold)
              .foregroundColor(Ink.primary)
          }
          if let current = data.current {
            Text(current.line)
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
          }
          if legacy, let note = data.current?.legacyNote {
            Text(note)
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.primary)
              .fixedSize(horizontal: false, vertical: true)
              .padding(.top, OmiSpacing.xxs)
          }
        }
        StorefrontUsageMeter(usage: data.usage)
      }

      if loading {
        HStack {
          Spacer()
          ProgressView().controlSize(.small)
          Spacer()
        }
        .padding(.vertical, OmiSpacing.xxl)
      } else if failed {
        notice("Couldn't load plans. Check your connection and try again.") {
          Button("Try again", action: onRetry)
            .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        }
      } else if let data, !(data.tiers.isEmpty && !legacy) {
        if !legacy { tierList(data) }
      } else {
        notice("Plans aren't available right now. Try again in a minute.") { EmptyView() }
      }

      if let error {
        Text(error)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(SettingsInk.notice)
      }

      if data == nil || failed || legacy || data?.current?.priceId != nil {
        Button(action: onManage) {
          Text("Manage billing")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        .disabled(busyPriceId != nil)
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  private func notice(_ text: String, @ViewBuilder action: () -> some View) -> some View {
    VStack(spacing: OmiSpacing.md) {
      Text(text)
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .multilineTextAlignment(.center)
      action()
    }
    .frame(maxWidth: .infinity)
    .padding(OmiSpacing.xxl)
    .background(cardShape.fill(Ink.rowFill).overlay(cardShape.stroke(Ink.separator, lineWidth: 1)))
  }

  private var cardShape: RoundedRectangle {
    RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
  }

  @ViewBuilder
  private func tierList(_ data: PlanStorefront) -> some View {
    let selected: PlanStorefront.Interval =
      data.cancelScheduled ? (data.current?.interval ?? .month) : (chosen ?? data.initialInterval)
    let parts = data.partitionedTiers
    let isExpanded = expanded ?? startExpanded

    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      if !data.cancelScheduled, let yearly = data.yearlyToggleLabel {
        HStack(spacing: OmiSpacing.hairline) {
          intervalChip("Monthly", selected: selected == .month) { chosen = .month }
          intervalChip(yearly, selected: selected == .year) { chosen = .year }
        }
        .padding(OmiSpacing.hairline)
        .background(Capsule().fill(Ink.wash))
      }
      ForEach(parts.primary) { tierCard($0, data: data, interval: selected) }
      if !parts.rest.isEmpty {
        Button {
          expanded = !isExpanded
        } label: {
          Text("See all plans")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.secondary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, OmiSpacing.xs)
        }
        .buttonStyle(.plain)
        .accessibilityValue(isExpanded ? "Expanded" : "Collapsed")
        if isExpanded {
          ForEach(parts.rest) { tierCard($0, data: data, interval: selected) }
        }
      }
    }
  }

  private func intervalChip(_ label: String, selected: Bool, action: @escaping () -> Void) -> some View {
    Button(action: action) {
      Text(label)
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(selected ? Ink.primary : Ink.secondary)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.xs)
        .background(Capsule().fill(selected ? Ink.surface : Color.clear))
    }
    .buttonStyle(.plain)
    .accessibilityAddTraits(selected ? .isSelected : [])
  }

  private func tierCard(_ tier: PlanStorefront.Tier, data: PlanStorefront, interval: PlanStorefront.Interval)
    -> some View
  {
    let price = data.offeredPrice(tier, interval: interval)
    let cta = price.flatMap { data.actionLabel(tier: tier, price: $0, livePlanId: livePlanId) }
    let highlight = tier.recommended && !data.cancelScheduled

    return VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(alignment: .top, spacing: OmiSpacing.sm) {
        Text(tier.name)
          .scaledFont(size: OmiType.subheading, weight: .bold)
          .foregroundColor(Ink.primary)
        Spacer(minLength: OmiSpacing.sm)
        if highlight { badge("Recommended") }
        if tier.isCurrent { badge("Your plan") }
      }

      if let price {
        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(price.headline)
            .scaledFont(size: OmiType.heading, weight: .bold)
            .foregroundColor(Ink.primary)
          if let subline = price.subline {
            Text(subline)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }
        }
      }

      if !tier.hoursLine.isEmpty {
        Text(tier.hoursLine)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
          .fixedSize(horizontal: false, vertical: true)
      }

      if !tier.compact && !tier.bullets.isEmpty {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          ForEach(tier.bullets, id: \.self) { bullet in
            HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.xs) {
              Text("•").foregroundColor(Ink.tertiary)
              Text(bullet)
                .fixedSize(horizontal: false, vertical: true)
            }
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
          }
        }
      }

      if let blocked = tier.blockedLine {
        Text(blocked)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .padding(.top, OmiSpacing.xxs)
      } else if let price, let cta {
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          Button {
            onSelect(tier, price)
          } label: {
            HStack(spacing: OmiSpacing.xs) {
              if busyPriceId != nil && busyPriceId == price.id {
                ProgressView().controlSize(.small)
              }
              Text(cta)
                .scaledFont(size: OmiType.body, weight: .semibold)
                .lineLimit(2)
            }
            .frame(maxWidth: .infinity)
          }
          .buttonStyle(OmiButtonStyle(.primary))
          .disabled(busyPriceId != nil)
          if let renewal = price.renewalLine {
            Text(renewal)
              .scaledFont(size: OmiType.micro)
              .foregroundColor(Ink.tertiary)
          }
        }
        .padding(.top, OmiSpacing.xxs)
      }
    }
    .padding(OmiSpacing.xl)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      cardShape
        .fill(highlight ? Ink.accent.opacity(0.08) : Ink.rowFill)
        .overlay(cardShape.stroke(highlight ? Ink.accent.opacity(0.85) : Ink.separator, lineWidth: highlight ? 1.5 : 1))
    )
  }

  private func badge(_ label: String) -> some View {
    Text(label)
      .scaledFont(size: OmiType.micro, weight: .bold)
      .foregroundColor(Ink.primary)
      .padding(.horizontal, OmiSpacing.xs)
      .padding(.vertical, OmiSpacing.hairline)
      .background(Capsule().fill(Ink.wash))
  }
}

/// The backend's meter line over a bar; nothing renders without a line.
struct StorefrontUsageMeter: View {
  let usage: PlanStorefront.Usage

  var body: some View {
    if let line = usage.meterLine {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        Text(line)
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
        if let percent = usage.percent {
          GeometryReader { proxy in
            ZStack(alignment: .leading) {
              Capsule().fill(Ink.wash)
              Capsule()
                .fill(percent >= 100 ? SettingsInk.notice : Ink.accent)
                .frame(width: proxy.size.width * CGFloat(min(max(percent, 0), 100)) / 100)
            }
          }
          .frame(height: 6)
          .accessibilityElement()
          .accessibilityValue("\(min(percent, 100)) percent")
        }
      }
      .padding(OmiSpacing.lg)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(
        RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
          .fill(Ink.rowFill)
          .overlay(
            RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous)
              .stroke(Ink.separator, lineWidth: 1))
      )
    }
  }
}

/// 80% nudge and exhausted-budget entry. At 100% the payload has no nudge line, so the
/// banner uses the backend's exhausted-surface header.
struct StorefrontBudgetBanner: View {
  let data: PlanStorefront
  let onOpen: () -> Void
  let onDismiss: () -> Void

  var body: some View {
    let line = data.showsBudgetNudge ? data.usage.nudgeLine : (data.budgetExhausted ? data.header : nil)
    if let line {
      HStack(spacing: OmiSpacing.md) {
        Text(line)
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.primary)
          .fixedSize(horizontal: false, vertical: true)
        Spacer(minLength: OmiSpacing.sm)
        Button("See plans", action: onOpen)
          .buttonStyle(OmiButtonStyle(.primary, size: .compact))
        if data.showsBudgetNudge {
          Button("Not now", action: onDismiss)
            .buttonStyle(OmiButtonStyle(.secondary, size: .compact))
        }
      }
      .padding(OmiSpacing.lg)
      .background(
        RoundedRectangle(cornerRadius: SettingsGlassMetrics.cardRadius, style: .continuous).fill(Ink.wash))
    }
  }
}
