import SwiftUI

/// Redesigned Conversations browser (Ink design system, light mode).
///
/// Ported from `mockup/screens/conversations.html`: a two-pane layout with a
/// ~320px left rail (search + conversation list) on `Ink.soft`, and a flexible
/// right reader on `Ink.canvas` showing the selected conversation — header,
/// a "What I heard" summary card, and the transcript turns.
///
/// Wires to real data via `appState.conversations` / `appState.people`.
struct RedesignConversationsPage: View {
  @ObservedObject var appState: AppState

  /// The currently selected conversation (first one by default).
  @State private var selected: ServerConversation?
  /// Local search text — filters the list client-side (title / overview / transcript).
  @State private var query: String = ""

  // MARK: Derived

  private var filtered: [ServerConversation] {
    let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return appState.conversations }
    let needle = trimmed.lowercased()
    return appState.conversations.filter { convo in
      if convo.title.lowercased().contains(needle) { return true }
      if convo.overview.lowercased().contains(needle) { return true }
      return convo.transcriptSegments.contains { $0.text.lowercased().contains(needle) }
    }
  }

  var body: some View {
    HStack(spacing: 0) {
      leftPanel
        .frame(width: 320)
        .frame(maxHeight: .infinity)
        .background(Ink.soft)
        .overlay(alignment: .trailing) {
          Rectangle().fill(Ink.hair).frame(width: 1)
        }

      rightReader
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Ink.canvas)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Ink.canvas)
    .onAppear {
      if appState.conversations.isEmpty {
        Task { await appState.loadConversations() }
      }
      if appState.people.isEmpty {
        Task { await appState.fetchPeople() }
      }
      syncSelection()
    }
    .onChange(of: appState.conversations) { _, _ in syncSelection() }
  }

  /// Ensure a valid selection: keep it if still present, otherwise pick the first.
  private func syncSelection() {
    if let current = selected, appState.conversations.contains(where: { $0.id == current.id }) {
      return
    }
    selected = appState.conversations.first
  }

  // MARK: - Left panel

  private var leftPanel: some View {
    VStack(alignment: .leading, spacing: 0) {
      VStack(alignment: .leading, spacing: 12) {
        Text("Conversations").inkH2()
        searchField
      }
      .padding(.horizontal, 18)
      .padding(.top, 18)
      .padding(.bottom, 10)

      if appState.isLoadingConversations && appState.conversations.isEmpty {
        loadingRail
      } else if filtered.isEmpty {
        emptyRail
      } else {
        ScrollView {
          LazyVStack(alignment: .leading, spacing: 2) {
            ForEach(filtered) { convo in
              ConversationRailRow(
                title: convo.title,
                subtitle: subtitle(for: convo),
                isActive: convo.id == selected?.id
              )
              .contentShape(Rectangle())
              .onTapGesture { selected = convo }
            }
          }
          .padding(.horizontal, 10)
          .padding(.top, 4)
          .padding(.bottom, 16)
        }
      }
    }
  }

  private var searchField: some View {
    HStack(spacing: 8) {
      Image(systemName: "magnifyingglass")
        .font(.system(size: 13))
        .foregroundColor(Ink.faint)
      TextField("Search transcripts…", text: $query)
        .textFieldStyle(.plain)
        .font(InkFont.sans(13))
        .foregroundColor(Ink.ink)
      if !query.isEmpty {
        Button {
          query = ""
        } label: {
          Image(systemName: "xmark.circle.fill")
            .font(.system(size: 13))
            .foregroundColor(Ink.faint)
        }
        .buttonStyle(.plain)
      }
    }
    .padding(.horizontal, 12)
    .frame(height: 38)
    .background(
      RoundedRectangle(cornerRadius: 10, style: .continuous)
        .fill(Ink.surface)
        .overlay(
          RoundedRectangle(cornerRadius: 10, style: .continuous)
            .strokeBorder(Ink.hair, lineWidth: 1))
    )
  }

  private var loadingRail: some View {
    VStack(spacing: 10) {
      ProgressView().controlSize(.small)
      Text("Loading…").inkCaption()
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private var emptyRail: some View {
    VStack(spacing: 8) {
      Image(systemName: "text.bubble")
        .font(.system(size: 26))
        .foregroundColor(Ink.faint.opacity(0.6))
      Text(query.isEmpty ? "No conversations yet" : "No matches")
        .inkSmall()
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .padding(.horizontal, 18)
  }

  // MARK: - Right reader

  @ViewBuilder
  private var rightReader: some View {
    if let convo = selected {
      ScrollView {
        VStack(alignment: .leading, spacing: 0) {
          readerHeader(convo)
          summaryCard(convo)
          transcriptSection(convo)
        }
        .frame(maxWidth: 720, alignment: .leading)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 40)
        .padding(.vertical, 36)
      }
    } else {
      VStack(spacing: 12) {
        Image(systemName: "text.bubble")
          .font(.system(size: 34))
          .foregroundColor(Ink.faint.opacity(0.5))
        Text("Select a conversation").inkH3()
        Text("Pick a conversation from the list to read it here.")
          .inkSmall()
      }
      .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
  }

  private func readerHeader(_ convo: ServerConversation) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(convo.title).inkH1()
      Text(headerMeta(for: convo)).inkCaption()
    }
    .padding(.bottom, 24)
  }

  @ViewBuilder
  private func summaryCard(_ convo: ServerConversation) -> some View {
    let overview = convo.overview.trimmingCharacters(in: .whitespacesAndNewlines)
    if !overview.isEmpty {
      InkCard(padding: 20) {
        VStack(alignment: .leading, spacing: 10) {
          Text("What I heard").inkEyebrow()
          Text(overview)
            .font(InkFont.sans(14))
            .foregroundColor(Ink.ink)
            .lineSpacing(4)
            .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }
      .padding(.bottom, 24)
    }
  }

  @ViewBuilder
  private func transcriptSection(_ convo: ServerConversation) -> some View {
    let segments = convo.transcriptSegments
    if !segments.isEmpty {
      Rectangle().fill(Ink.hair).frame(height: 1).padding(.bottom, 24)
      VStack(alignment: .leading, spacing: 16) {
        ForEach(segments) { seg in
          TranscriptTurn(
            name: speakerName(for: seg),
            time: timestamp(seg.start),
            text: seg.text
          )
        }
      }
    } else if convo.overview.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
      // Nothing to show at all.
      Text("No transcript available for this conversation.")
        .inkSmall()
    }
  }

  // MARK: - Speaker / participant resolution

  private func speakerName(for segment: TranscriptSegment) -> String {
    if segment.isUser { return "You" }
    if let pid = segment.personId, let person = appState.peopleById[pid], !person.name.isEmpty {
      return person.name
    }
    return "Speaker \(segment.speakerId + 1)"
  }

  /// Ordered, de-duplicated participant list ("You" first).
  private func participants(for convo: ServerConversation) -> [String] {
    var seen = Set<String>()
    var names: [String] = []
    for seg in convo.transcriptSegments {
      let name = speakerName(for: seg)
      if seen.insert(name).inserted { names.append(name) }
    }
    if let youIndex = names.firstIndex(of: "You"), youIndex != 0 {
      names.remove(at: youIndex)
      names.insert("You", at: 0)
    }
    return names
  }

  private func whoLabel(for convo: ServerConversation) -> String {
    let names = participants(for: convo)
    return names.isEmpty ? "Just you" : names.joined(separator: ", ")
  }

  // MARK: - Formatting

  /// Left-rail sub line: "who · duration · when".
  private func subtitle(for convo: ServerConversation) -> String {
    [whoLabel(for: convo), durationLabel(convo), relativeWhen(convo)].joined(separator: " · ")
  }

  /// Right-reader meta line: "Monday, July 6 · 23 min · You, Will, Josh".
  private func headerMeta(for convo: ServerConversation) -> String {
    let date = convo.startedAt ?? convo.createdAt
    let df = DateFormatter()
    df.dateFormat = "EEEE, MMMM d"
    return [df.string(from: date), durationLabel(convo), whoLabel(for: convo)]
      .joined(separator: " · ")
  }

  private func durationLabel(_ convo: ServerConversation) -> String {
    let seconds = convo.durationInSeconds
    if seconds < 60 { return "\(max(seconds, 0)) sec" }
    return "\(seconds / 60) min"
  }

  private func relativeWhen(_ convo: ServerConversation) -> String {
    let date = convo.startedAt ?? convo.createdAt
    let cal = Calendar.current
    let df = DateFormatter()
    if cal.isDateInToday(date) {
      df.dateFormat = "h:mm"
      return "today \(df.string(from: date))"
    }
    if cal.isDateInYesterday(date) {
      return "yesterday"
    }
    if let days = cal.dateComponents([.day], from: date, to: Date()).day, days < 7 {
      df.dateFormat = "EEE"
      return df.string(from: date)
    }
    df.dateFormat = "MMM d"
    return df.string(from: date)
  }

  /// mm:ss timestamp for a transcript turn.
  private func timestamp(_ start: Double) -> String {
    let total = max(Int(start), 0)
    return String(format: "%02d:%02d", total / 60, total % 60)
  }
}

// MARK: - Left-rail row

private struct ConversationRailRow: View {
  let title: String
  let subtitle: String
  let isActive: Bool

  @State private var hovering = false

  var body: some View {
    VStack(alignment: .leading, spacing: 4) {
      Text(title)
        .font(InkFont.sans(14, .medium))
        .foregroundColor(Ink.ink)
        .lineLimit(1)
        .truncationMode(.tail)
      Text(subtitle)
        .font(InkFont.sans(12))
        .foregroundColor(Ink.faint)
        .lineLimit(1)
        .truncationMode(.tail)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(12)
    .background(
      RoundedRectangle(cornerRadius: 11, style: .continuous)
        .fill(isActive ? Ink.surface : (hovering ? Ink.surface : .clear))
        .overlay(
          RoundedRectangle(cornerRadius: 11, style: .continuous)
            .strokeBorder(isActive ? Ink.hair : .clear, lineWidth: 1))
    )
    .onHover { hovering = $0 }
  }
}

// MARK: - Transcript turn

private struct TranscriptTurn: View {
  let name: String
  let time: String
  let text: String

  var body: some View {
    HStack(alignment: .top, spacing: 11) {
      Text(initials(from: name))
        .font(InkFont.sans(11, .semibold))
        .foregroundColor(Ink.accentInk)
        .frame(width: 28, height: 28)
        .background(Circle().fill(Ink.avatarFill(for: name)))

      VStack(alignment: .leading, spacing: 3) {
        HStack(spacing: 6) {
          Text(name)
            .font(InkFont.sans(12, .semibold))
            .foregroundColor(Ink.body)
          Text("· \(time)")
            .font(InkFont.mono(11))
            .foregroundColor(Ink.faint)
        }
        Text(text)
          .font(InkFont.sans(14))
          .foregroundColor(Ink.ink)
          .lineSpacing(3)
          .fixedSize(horizontal: false, vertical: true)
          .frame(maxWidth: 560, alignment: .leading)
      }
      Spacer(minLength: 0)
    }
  }

  private func initials(from name: String) -> String {
    let parts = name.split(separator: " ")
    if let first = parts.first?.first {
      if parts.count > 1, let second = parts[1].first {
        return "\(first)\(second)".uppercased()
      }
      return String(first).uppercased()
    }
    return "?"
  }
}
