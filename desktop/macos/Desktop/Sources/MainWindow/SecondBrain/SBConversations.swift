import OmiTheme
import SwiftUI

// MARK: - Container (list ↔ detail)

/// Conversations surface: a searchable, date-grouped list that drills into a
/// read-only detail. Binds to AppState.conversations (+ star toggle) and fetches
/// full detail via APIClient.getConversation.
struct SBConversationsContainer: View {
  @ObservedObject var appState: AppState
  @State private var query = ""
  @State private var filter: ConvoFilter = .all
  @State private var selectedId: String?

  enum ConvoFilter: String, CaseIterable { case all = "All", starred = "★ Starred" }

  var body: some View {
    Group {
      if let id = selectedId,
        let convo = appState.conversations.first(where: { $0.id == id })
      {
        SBConversationDetail(appState: appState, base: convo, onBack: { selectedId = nil })
      } else {
        list
      }
    }
    .task { await appState.loadConversations() }
  }

  private var list: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        SBSearchField(text: $query, placeholder: "Search everything you've said or heard…")
          .padding(.bottom, 12)

        HStack(spacing: 7) {
          ForEach(ConvoFilter.allCases, id: \.self) { f in
            SBFilterChip(label: f.rawValue, selected: filter == f) { filter = f }
          }
          Spacer()
        }
        .padding(.bottom, 10)

        let groups = groupedConversations()
        if groups.isEmpty {
          Text("Nothing matches — try fewer words, or ask Omi directly.")
            .geist(size: 13.5)
            .foregroundStyle(sbInk(.w35))
            .padding(.vertical, 16)
        }
        ForEach(groups, id: \.label) { group in
          SBSectionLabel(text: group.label).padding(.top, 14).padding(.bottom, 2)
          ForEach(group.items) { convo in
            row(convo)
          }
        }

        Text("Grouping by person is coming — once speaker ID is confident enough to trust.")
          .geist(size: 12)
          .foregroundStyle(sbInk(.w28))
          .padding(.top, 14)
      }
      .padding(.horizontal, 30)
      .padding(.bottom, 20)
    }
  }

  @Environment(\.sbTheme) private var sb
  private func sbInk(_ t: SBInk) -> Color { sb.ink(t) }

  private func row(_ convo: ServerConversation) -> some View {
    HStack(spacing: 12) {
      VStack(alignment: .leading, spacing: 1) {
        Text(convo.title).geist(size: 15).foregroundStyle(sb.ink(.w9))
        Text(sourceLabel(convo)).geist(size: 12.5).foregroundStyle(sb.ink(.w38))
      }
      Spacer(minLength: 8)
      Text(metaLabel(convo)).geistMono(size: 12.5).foregroundStyle(sb.ink(.w4))
      Text(SBDate.time(convo.createdAt)).geistMono(size: 12.5).foregroundStyle(sb.ink(.w25))
      Button {
        Task { await appState.setConversationStarred(convo.id, starred: !convo.starred) }
      } label: {
        Text(convo.starred ? "★" : "☆")
          .font(.system(size: 13.5))
          .foregroundStyle(convo.starred ? sb.ink : sb.ink(.w25))
      }
      .buttonStyle(.plain)
    }
    .padding(.vertical, 12)
    .contentShape(Rectangle())
    .onTapGesture { selectedId = convo.id }
    .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w07)).frame(height: 1) }
  }

  // MARK: grouping

  private struct ConvoGroup { let label: String; let items: [ServerConversation] }

  private func groupedConversations() -> [ConvoGroup] {
    let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let filtered = appState.conversations.filter { convo in
      if filter == .starred && !convo.starred { return false }
      if q.isEmpty { return true }
      return (convo.title + " " + convo.overview + " " + sourceLabel(convo)).lowercased().contains(q)
    }
    let cal = Calendar.current
    var order: [String] = []
    var buckets: [String: [ServerConversation]] = [:]
    for convo in filtered.sorted(by: { $0.createdAt > $1.createdAt }) {
      let label = SBDate.groupLabel(convo.createdAt, calendar: cal)
      if buckets[label] == nil { order.append(label) }
      buckets[label, default: []].append(convo)
    }
    return order.map { ConvoGroup(label: $0, items: buckets[$0] ?? []) }
  }

  private func sourceLabel(_ convo: ServerConversation) -> String {
    convo.source?.rawValue.replacingOccurrences(of: "_", with: " ").capitalized ?? "Omi"
  }

  private func metaLabel(_ convo: ServerConversation) -> String {
    let n = convo.structured.actionItems.count
    if n > 0 { return n == 1 ? "1 task" : "\(n) tasks" }
    let secs = convo.durationInSeconds
    return secs > 0 ? "\(max(1, secs / 60)) min" : convo.structured.category.capitalized
  }
}

// MARK: - Detail

struct SBConversationDetail: View {
  @Environment(\.sbTheme) private var sb
  @ObservedObject var appState: AppState
  let base: ServerConversation
  var onBack: () -> Void

  @State private var full: ServerConversation?
  @State private var loading = true

  private var convo: ServerConversation { full ?? base }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 0) {
        Button(action: onBack) {
          Text("← Back").geist(size: 13.5).foregroundStyle(sb.ink(.w4))
        }
        .buttonStyle(.plain)
        .padding(.bottom, 10)

        Text(convo.title)
          .geist(size: 23, weight: .semibold, tracking: 23 * -0.02)
          .foregroundStyle(sb.ink)
        Text(detailMeta)
          .geistMono(size: 12.5)
          .foregroundStyle(sb.ink(.w4))
          .padding(.top, 4).padding(.bottom, 14)

        if !convo.overview.isEmpty {
          SBSectionLabel(text: "Summary").padding(.bottom, 6)
          Text(convo.overview)
            .geist(size: 15)
            .foregroundStyle(sb.ink(.w8))
            .lineSpacing(3)
            .padding(.bottom, 16)
        }

        let actions = convo.structured.actionItems
        if !actions.isEmpty {
          SBSectionLabel(text: "Omi did").padding(.bottom, 2)
          ForEach(actions) { item in
            HStack(alignment: .top, spacing: 10) {
              Text("✓").foregroundStyle(sb.ink(.w45))
              Text(item.description).geist(size: 14).foregroundStyle(sb.ink(.w8))
              Spacer(minLength: 0)
            }
            .padding(.vertical, 9)
            .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w07)).frame(height: 1) }
          }
        }

        SBSectionLabel(text: "Transcript").padding(.top, 16).padding(.bottom, 6)
        if loading && convo.transcriptSegments.isEmpty {
          Text("Loading transcript…").geist(size: 13.5).foregroundStyle(sb.ink(.w35))
            .padding(.vertical, 8)
        } else if convo.transcriptSegments.isEmpty {
          Text("No transcript for this conversation.")
            .geist(size: 13.5).foregroundStyle(sb.ink(.w35)).padding(.vertical, 8)
        } else {
          ForEach(convo.transcriptSegments) { seg in
            VStack(alignment: .leading, spacing: 3) {
              Text(speakerLabel(seg))
                .geistMono(size: 11, weight: .medium, tracking: 11 * 0.06)
                .foregroundStyle(seg.isUser ? sb.ink(.w6) : sb.ink(.w4))
              Text(seg.text)
                .geist(size: 14.5)
                .foregroundStyle(sb.ink(.w75))
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 7)
          }
        }
      }
      .padding(.horizontal, 30)
      .padding(.bottom, 24)
    }
    .task {
      loading = true
      full = try? await APIClient.shared.getConversation(id: base.id)
      loading = false
    }
  }

  private var detailMeta: String {
    var parts: [String] = []
    if let src = base.source?.rawValue { parts.append(src.replacingOccurrences(of: "_", with: " ").capitalized) }
    let mins = convo.durationInSeconds / 60
    if mins > 0 { parts.append("\(mins) min") }
    parts.append(SBDate.dayTime(convo.createdAt))
    return parts.joined(separator: " · ")
  }

  private func speakerLabel(_ seg: TranscriptSegment) -> String {
    if seg.isUser { return "You" }
    if let s = seg.speaker, !s.isEmpty {
      // "SPEAKER_0" / "SPEAKER 0" → "Speaker 1"; a real name stays as-is.
      let digits = s.filter(\.isNumber)
      if !digits.isEmpty, let n = Int(digits) { return "Speaker \(n + 1)" }
      return s.capitalized
    }
    return "Speaker \(seg.speakerId + 1)"
  }
}

// MARK: - Shared small components

struct SBSearchField: View {
  @Environment(\.sbTheme) private var sb
  @Binding var text: String
  var placeholder: String

  var body: some View {
    HStack(spacing: 10) {
      Text("⌕").foregroundStyle(sb.ink(.w3)).font(.system(size: 13))
      TextField(placeholder, text: $text)
        .textFieldStyle(.plain)
        .geist(size: 13.5)
        .foregroundStyle(sb.ink)
    }
    .padding(.horizontal, 12).padding(.vertical, 8)
    .background(RoundedRectangle(cornerRadius: 10).fill(sb.ink(.w05)))
    .overlay(RoundedRectangle(cornerRadius: 10).stroke(sb.ink(.w09), lineWidth: 1))
  }
}

struct SBFilterChip: View {
  @Environment(\.sbTheme) private var sb
  let label: String
  let selected: Bool
  let action: () -> Void
  var body: some View {
    Button(action: action) {
      Text(label)
        .geist(size: 12.5)
        .foregroundStyle(selected ? sb.ink : sb.ink(.w5))
        .padding(.horizontal, 11).padding(.vertical, 4)
        .background(Capsule().fill(selected ? sb.ink(.w1) : .clear))
        .overlay(Capsule().stroke(selected ? sb.ink(.w5) : sb.ink(.w12), lineWidth: 1))
    }
    .buttonStyle(.plain)
  }
}

// MARK: - Date helpers

enum SBDate {
  private static let t: DateFormatter = {
    let f = DateFormatter(); f.dateFormat = "h:mm a"; return f
  }()
  private static let weekday: DateFormatter = {
    let f = DateFormatter(); f.dateFormat = "EEEE"; return f
  }()
  private static let dayT: DateFormatter = {
    let f = DateFormatter(); f.dateFormat = "EEE h:mm a"; return f
  }()

  static func time(_ d: Date) -> String { t.string(from: d) }
  static func dayTime(_ d: Date) -> String { dayT.string(from: d) }

  static func groupLabel(_ d: Date, calendar: Calendar) -> String {
    if calendar.isDateInToday(d) { return "TODAY" }
    if calendar.isDateInYesterday(d) { return "YESTERDAY" }
    if let days = calendar.dateComponents([.day], from: d, to: Date()).day, days < 7 {
      return weekday.string(from: d).uppercased()
    }
    let f = DateFormatter(); f.dateFormat = "MMM d"
    return f.string(from: d).uppercased()
  }
}
