import SwiftUI

/// "Worth knowing" — quiet insights omi noticed. Mockup `insights.html`, light-wired.
/// Reads real insights from `InsightStorage.shared`.
struct RedesignInsightsPage: View {
  @ObservedObject private var storage = InsightStorage.shared
  @Binding var selectedIndex: Int

  private var insights: [StoredInsight] { storage.visibleInsights }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 12) {
        header

        if insights.isEmpty {
          emptyState
        } else {
          ForEach(insights) { item in
            insightCard(item)
          }
        }
      }
      .frame(maxWidth: 720, alignment: .leading)
      .frame(maxWidth: .infinity, alignment: .center)
      .padding(.horizontal, 48)
      .padding(.vertical, 44)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
  }

  private var header: some View {
    HStack(alignment: .top) {
      VStack(alignment: .leading, spacing: 8) {
        Text("Worth knowing").inkH1()
        Text("Quiet things I noticed. Nothing urgent unless I say so.").inkSmall()
      }
      Spacer()
      if storage.unreadCount > 0 {
        InkButton(title: "Mark all read", kind: .ghost, size: .sm) {
          storage.markAllAsRead()
        }
        .padding(.top, 4)
      }
    }
    .padding(.bottom, 4)
  }

  private func insightCard(_ item: StoredInsight) -> some View {
    let title = item.insight.headline?.isEmpty == false ? item.insight.headline! : item.insight.insight
    let sub = subtitle(for: item)
    return HStack(alignment: .top, spacing: 14) {
      iconChip(item.insight.category.icon)
      VStack(alignment: .leading, spacing: 3) {
        Text(title)
          .font(InkFont.sans(15, .medium)).foregroundColor(Ink.ink)
          .fixedSize(horizontal: false, vertical: true)
        if !sub.isEmpty {
          Text(sub).font(InkFont.sans(13)).foregroundColor(Ink.muted)
            .fixedSize(horizontal: false, vertical: true)
        }
      }
      Spacer(minLength: 8)
      if !item.isRead {
        InkButton(title: "Got it", kind: .plain, size: .sm) {
          storage.markAsRead(item.id)
        }
      }
    }
    .padding(20)
    .background(
      RoundedRectangle(cornerRadius: 14, style: .continuous)
        .fill(Ink.surface)
        .overlay(
          RoundedRectangle(cornerRadius: 14, style: .continuous)
            .strokeBorder(Ink.hair, lineWidth: 1))
    )
  }

  private func iconChip(_ systemName: String) -> some View {
    RoundedRectangle(cornerRadius: 10, style: .continuous)
      .fill(Ink.accentTint)
      .frame(width: 36, height: 36)
      .overlay(
        Image(systemName: systemName)
          .font(.system(size: 15, weight: .medium))
          .foregroundColor(Ink.accentStrong))
  }

  private var emptyState: some View {
    VStack(alignment: .leading, spacing: 10) {
      Text("Nothing worth flagging yet.")
        .font(InkFont.serif(22, .medium)).foregroundColor(Ink.ink).tracking(-0.3)
      Text("I'll drop a quiet note here when something comes up across your day — nothing urgent unless I say so.")
        .inkSmall()
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(.top, 8)
    .frame(maxWidth: .infinity, alignment: .leading)
  }

  private func subtitle(for item: StoredInsight) -> String {
    if let reasoning = item.insight.reasoning, !reasoning.isEmpty { return reasoning }
    if !item.contextSummary.isEmpty { return item.contextSummary }
    // Fall back to the insight body when the title used the headline.
    if item.insight.headline?.isEmpty == false { return item.insight.insight }
    return ""
  }
}
