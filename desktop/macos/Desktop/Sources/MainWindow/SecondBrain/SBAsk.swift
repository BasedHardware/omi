import OmiTheme
import SwiftUI

// MARK: - Ask / Chats

/// The Ask view: past-chat chips + a streamed answer thread that cites its
/// sources. Binds to the shared ChatProvider (messages stream in place).
struct SBAskView: View {
  @Environment(\.sbTheme) private var sb
  @ObservedObject var chat: ChatProvider

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      if !chat.sessions.isEmpty {
        ScrollView(.horizontal, showsIndicators: false) {
          HStack(spacing: 7) {
            SBFilterChip(label: "Now", selected: chat.currentSession == nil) {}
            ForEach(chat.sessions.prefix(6)) { session in
              SBFilterChip(label: session.title, selected: chat.currentSession?.id == session.id) {
                Task { await chat.selectSession(session) }
              }
            }
          }
          .padding(.bottom, 12)
        }
      }

      ScrollViewReader { proxy in
        ScrollView {
          VStack(alignment: .leading, spacing: 10) {
            ForEach(chat.messages) { message in
              messageBubble(message)
                .id(message.id)
            }
            if chat.isSending && (chat.messages.last?.sender == .user || chat.messages.isEmpty) {
              HStack(spacing: 8) {
                SBLogo(size: 12, spinning: true)
                Text("thinking…").geist(size: 12.5).foregroundStyle(sb.ink(.w4))
              }
            }
          }
          .padding(.vertical, 4)
        }
        .onChange(of: chat.messages.count) { _, _ in
          if let last = chat.messages.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } }
        }
      }
    }
    .padding(.horizontal, 30)
    .padding(.bottom, 12)
  }

  @ViewBuilder private func messageBubble(_ message: ChatMessage) -> some View {
    let isUser = message.sender == .user
    VStack(alignment: isUser ? .trailing : .leading, spacing: 4) {
      Text(message.text + (message.isStreaming ? " ▍" : ""))
        .geist(size: 15)
        .foregroundStyle(isUser ? sb.ink : sb.ink(.w85))
        .lineSpacing(2)
        .padding(.horizontal, 13).padding(.vertical, 9)
        .background(
          RoundedRectangle(cornerRadius: 13, style: .continuous)
            .fill(isUser ? sb.ink(.w1) : sb.ink(.w04))
        )
        .overlay(
          RoundedRectangle(cornerRadius: 13, style: .continuous)
            .stroke(isUser ? sb.ink(.w14) : sb.ink(.w08), lineWidth: 1)
        )
      if let citation = message.citations.first {
        Text("from \(citation.title) ›")
          .geistMono(size: 11.5).foregroundStyle(sb.ink(.w35))
          .padding(.leading, 4)
      }
    }
    .frame(maxWidth: .infinity, alignment: isUser ? .trailing : .leading)
  }
}

// MARK: - ⌘K palette

struct SBPaletteResult: Identifiable {
  let id = UUID()
  let kind: String
  let text: String
  let hint: String
  let go: () -> Void
}

struct SBPalette: View {
  @Environment(\.sbTheme) private var sb
  @ObservedObject var appState: AppState
  @ObservedObject var tasks: TasksStore
  let onClose: () -> Void
  let onOpenConversation: (String) -> Void
  let onNavigate: (Int) -> Void

  @State private var query = ""
  @FocusState private var focused: Bool

  var body: some View {
    ZStack(alignment: .top) {
      Color.black.opacity(0.45).ignoresSafeArea().onTapGesture(perform: onClose)
      VStack(spacing: 0) {
        HStack(spacing: 10) {
          SBLogo(size: 13, opacity: 0.6)
          TextField("Search conversations, memories, tasks…", text: $query)
            .textFieldStyle(.plain).geist(size: 13.5).foregroundStyle(sb.ink)
            .focused($focused)
            .onSubmit { results.first?.go() }
          Text("esc").geistMono(size: 11.5).foregroundStyle(sb.ink(.w3))
        }
        .padding(.horizontal, 16).padding(.vertical, 13)
        .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w09)).frame(height: 1) }

        ScrollView {
          VStack(spacing: 0) {
            if results.isEmpty {
              Text("No matches — press ↩ to ask Omi instead.")
                .geist(size: 13.5).foregroundStyle(sb.ink(.w35))
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(14)
            }
            ForEach(results) { r in
              Button { r.go() } label: {
                HStack(spacing: 10) {
                  Text(r.kind).geistMono(size: 10.5, weight: .medium).foregroundStyle(sb.ink(.w35))
                    .frame(width: 64, alignment: .leading)
                  Text(r.text).geist(size: 14).foregroundStyle(sb.ink(.w85)).lineLimit(1)
                  Spacer(minLength: 8)
                  Text(r.hint).geistMono(size: 11.5).foregroundStyle(sb.ink(.w25))
                }
                .padding(.horizontal, 10).padding(.vertical, 9)
                .contentShape(Rectangle())
              }
              .buttonStyle(.plain)
            }
          }
          .padding(6)
        }
        .frame(maxHeight: 360)
      }
      .frame(width: 480)
      .background(
        RoundedRectangle(cornerRadius: 14, style: .continuous).fill(sb.panel2)
          .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
      )
      .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(sb.ink(.w14), lineWidth: 1))
      .shadow(color: .black.opacity(0.5), radius: 40, y: 20)
      .padding(.top, 100)
    }
    .onAppear { focused = true }
    .onExitCommand(perform: onClose)
  }

  private var results: [SBPaletteResult] {
    let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    var all: [SBPaletteResult] = []
    for convo in appState.conversations.prefix(30) {
      all.append(SBPaletteResult(kind: "CONVO", text: convo.title, hint: SBDate.time(convo.createdAt)) {
        onClose(); onOpenConversation(convo.id)
      })
    }
    for task in tasks.incompleteTasks.prefix(30) {
      all.append(SBPaletteResult(kind: "TASK", text: task.description, hint: "todo") {
        onClose(); onNavigate(SidebarNavItem.tasks.rawValue)
      })
    }
    let pages: [(String, Int)] = [
      ("Settings", SidebarNavItem.settings.rawValue),
      ("Permissions", SidebarNavItem.permissions.rawValue),
      ("Memories", SidebarNavItem.memories.rawValue),
      ("Rewind timeline", SidebarNavItem.rewind.rawValue),
    ]
    for (name, idx) in pages {
      all.append(SBPaletteResult(kind: "PAGE", text: name, hint: "") {
        onClose(); onNavigate(idx)
      })
    }
    let filtered = q.isEmpty ? all : all.filter { ($0.kind + " " + $0.text).lowercased().contains(q) }
    return Array(filtered.prefix(8))
  }
}
