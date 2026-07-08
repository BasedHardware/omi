import AppKit
import SwiftUI

/// The redesigned "plan & usage" page — mockup `plan-usage.html`, light-wired.
/// Fetches the real subscription via `APIClient.getUserSubscription()` and
/// derives the plan name, renewal date, and monthly usage meters from it.
struct RedesignPlanUsagePage: View {
  @State private var subscription: UserSubscriptionResponse?
  @State private var isLoading = true

  private var planName: String {
    guard let sub = subscription?.subscription else { return "Operator" }
    if sub.features.contains("byok") { return "Free" }
    switch sub.plan {
    case .basic: return "Free"
    case .unlimited: return "Neo"
    case .architect, .pro: return "Architect"
    case .operator: return "Operator"
    }
  }

  private var renewsText: String? {
    guard let end = subscription?.subscription.currentPeriodEnd else { return nil }
    let f = DateFormatter()
    f.dateFormat = "MMM d"
    let prefix = subscription?.subscription.cancelAtPeriodEnd == true ? "Ends" : "Renews"
    return "\(prefix) \(f.string(from: Date(timeIntervalSince1970: TimeInterval(end))))"
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 24) {
        Text("PLAN & USAGE").inkEyebrow()

        HStack(alignment: .firstTextBaseline) {
          Text("You're on \(planName).").inkH1()
          Spacer(minLength: 12)
          if let renewsText { InkPill(text: renewsText) }
        }

        includedCard
        usageCard
        morePowerCard
      }
      .frame(maxWidth: 740, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .task {
      isLoading = true
      subscription = try? await APIClient.shared.getUserSubscription()
      isLoading = false
    }
  }

  // MARK: - What's included

  private var includedCard: some View {
    InkCard(radius: 16) {
      VStack(alignment: .leading, spacing: 0) {
        Text("What's included").inkH3().padding(.bottom, 8)
        includedRow("Unlimited memory, on your Mac and phone")
        includedRow("Messaging auto-reply across iMessage, Telegram, WhatsApp")
        includedRow("Rewind screen history + proactive nudges")
        includedRow("Use your memory in Claude, ChatGPT, and more")
      }
    }
  }

  private func includedRow(_ text: String) -> some View {
    HStack(spacing: 10) {
      Image(systemName: "checkmark").font(.system(size: 12, weight: .semibold))
        .foregroundColor(Ink.live)
      Text(text).font(InkFont.sans(14)).foregroundColor(Ink.body)
        .fixedSize(horizontal: false, vertical: true)
      Spacer(minLength: 0)
    }
    .padding(.vertical, 9)
  }

  // MARK: - This month

  private var usageCard: some View {
    InkCard(radius: 16) {
      VStack(alignment: .leading, spacing: 0) {
        Text("This month").inkH3()

        if let sub = subscription {
          usageRow(
            "Memories created",
            value: usageValue(sub.memoriesCreatedUsed, sub.memoriesCreatedLimit),
            pct: pct(sub.memoriesCreatedUsed, sub.memoriesCreatedLimit))
          usageRow(
            "Words transcribed",
            value: usageValue(sub.wordsTranscribedUsed, sub.wordsTranscribedLimit),
            pct: pct(sub.wordsTranscribedUsed, sub.wordsTranscribedLimit))
          usageRow(
            "Insights gained",
            value: usageValue(sub.insightsGainedUsed, sub.insightsGainedLimit),
            pct: pct(sub.insightsGainedUsed, sub.insightsGainedLimit))
        } else {
          Text(isLoading ? "Loading your usage…" : "Usage will show here once it's available.")
            .inkSmall().padding(.top, 12)
        }
      }
    }
  }

  private func usageRow(_ label: String, value: String, pct: Double) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      HStack {
        Text(label).font(InkFont.sans(14)).foregroundColor(Ink.body)
        Spacer(minLength: 8)
        Text(value).font(InkFont.mono(12)).foregroundColor(Ink.faint)
      }
      GeometryReader { geo in
        ZStack(alignment: .leading) {
          Capsule().fill(Ink.surface2)
          Capsule().fill(Ink.ink)
            .frame(width: max(0, min(1, pct / 100)) * geo.size.width)
        }
      }
      .frame(height: 8)
    }
    .padding(.top, 16)
  }

  // MARK: - More power

  private var morePowerCard: some View {
    NextCard {
      VStack(alignment: .leading, spacing: 14) {
        HStack(spacing: 7) {
          Circle().fill(Ink.accent).frame(width: 6, height: 6)
          Text("MORE POWER")
            .font(InkFont.sans(11, .semibold)).foregroundColor(Ink.accentStrong).tracking(1.2)
        }
        Text("Add teammates and I'll remember your shared meetings for both of you.")
          .inkBody()
          .frame(maxWidth: 480, alignment: .leading)
          .fixedSize(horizontal: false, vertical: true)
        InkButton(title: "Add a teammate", kind: .primary) {
          if let url = URL(string: "https://affiliate.omi.me") { NSWorkspace.shared.open(url) }
        }
      }
    }
  }

  // MARK: - Helpers

  /// Unlimited when the limit is non-positive; otherwise "used / limit".
  private func usageValue(_ used: Int, _ limit: Int) -> String {
    if limit <= 0 { return "\(formatted(used))" }
    return "\(formatted(used)) of \(formatted(limit))"
  }

  private func pct(_ used: Int, _ limit: Int) -> Double {
    guard limit > 0 else { return used > 0 ? 100 : 0 }
    return min(100, Double(used) / Double(limit) * 100)
  }

  private func formatted(_ n: Int) -> String {
    let f = NumberFormatter()
    f.numberStyle = .decimal
    return f.string(from: NSNumber(value: n)) ?? "\(n)"
  }
}
