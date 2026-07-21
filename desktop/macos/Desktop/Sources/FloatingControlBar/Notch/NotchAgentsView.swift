import SwiftUI

/// The agents tab: running/recent agent sessions from AgentPillsManager.
/// Tapping a row drills into that agent's conversation (rendered by the same
/// shared ChatMessagesView); back returns to the list.
struct NotchAgentsView: View {
  @ObservedObject var vm: NotchViewModel
  @ObservedObject var manager: AgentPillsManager

  var body: some View {
    if let pillID = vm.openAgentPillID,
      let pill = manager.pills.first(where: { $0.id == pillID })
    {
      NotchAgentChatView(vm: vm, pill: pill)
    } else {
      agentList
    }
  }

  @ViewBuilder
  private var agentList: some View {
    if manager.pills.isEmpty {
      VStack(spacing: 8) {
        Image(systemName: "circle.hexagongrid")
          .font(.system(size: 20, weight: .light))
          .foregroundStyle(.white.opacity(0.4))
        Text("No agents yet")
          .font(.system(size: 12, weight: .medium))
          .foregroundStyle(.white.opacity(0.6))
        Text("Ask Omi to work on something in the background")
          .font(.system(size: 11))
          .foregroundStyle(.white.opacity(0.4))
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    } else {
      ScrollView {
        LazyVStack(spacing: 2) {
          ForEach(manager.pills) { pill in
            NotchAgentRow(pill: pill) {
              manager.markViewed(pillID: pill.id)
              vm.openAgentPillID = pill.id
            }
          }
        }
        .padding(.vertical, 6)
      }
    }
  }
}

private struct NotchAgentRow: View {
  @ObservedObject var pill: AgentPill
  let onOpen: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: onOpen) {
      HStack(spacing: 10) {
        Circle()
          .fill(pill.status.tintColor)
          .frame(width: 7, height: 7)
        VStack(alignment: .leading, spacing: 1) {
          Text(pill.title)
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(.white.opacity(0.94))
            .lineLimit(1)
            .truncationMode(.tail)
          Text(pill.latestActivity)
            .font(.system(size: 10))
            .foregroundStyle(.white.opacity(0.5))
            .lineLimit(1)
            .truncationMode(.tail)
        }
        Spacer(minLength: 0)
        Image(systemName: "chevron.right")
          .font(.system(size: 9, weight: .semibold))
          .foregroundStyle(.white.opacity(isHovering ? 0.6 : 0.25))
      }
      .padding(.horizontal, 10)
      .padding(.vertical, 7)
      .background(
        RoundedRectangle(cornerRadius: 10, style: .continuous)
          .fill(Color.white.opacity(isHovering ? 0.1 : 0))
      )
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
  }
}

/// Read-only agent transcript with a back affordance.
/// ponytail: no in-notch agent follow-up composer yet — the tray stays bound
/// to main chat; add an agent tray mode if follow-ups from the notch matter.
private struct NotchAgentChatView: View {
  @ObservedObject var vm: NotchViewModel
  @ObservedObject var pill: AgentPill

  var body: some View {
    VStack(spacing: 0) {
      HStack(spacing: 8) {
        Button {
          vm.openAgentPillID = nil
        } label: {
          HStack(spacing: 3) {
            Image(systemName: "chevron.left")
              .font(.system(size: 9, weight: .semibold))
            Text("Agents")
              .font(.system(size: 11, weight: .medium))
          }
          .foregroundStyle(.white.opacity(0.6))
          .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        Spacer()
        Circle()
          .fill(pill.status.tintColor)
          .frame(width: 6, height: 6)
        Text(pill.title)
          .font(.system(size: 11, weight: .semibold))
          .foregroundStyle(.white.opacity(0.85))
          .lineLimit(1)
      }
      .padding(.horizontal, 6)
      .padding(.bottom, 6)

      ChatMessagesView(
        messages: pill.conversationMessages,
        isSending: false,
        hasMoreMessages: false,
        isLoadingMoreMessages: false,
        isLoadingInitial: false,
        app: nil,
        onLoadMore: {},
        onRate: { _, _ in },
        horizontalContentPadding: 6,
        welcomeContent: {
          Text(pill.latestActivity)
            .font(.system(size: 11))
            .foregroundStyle(.white.opacity(0.5))
            .padding(.vertical, 14)
        }
      )
    }
  }
}
