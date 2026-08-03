import AppKit
import OmiTheme
import SwiftUI

// The person profile: a full page per person rather than a row expansion.
// Layout follows the CRM shape users already know — identity hero, then a
// scoped ask bar, then tabbed evidence (overview / messages / memories /
// commitments). Everything degrades: a person we know only a name and a
// channel for still renders a coherent page.

// MARK: - Tabs

enum PersonProfileTab: String, CaseIterable, Identifiable, Sendable {
  case overview, messages, memories, commitments

  var id: String { rawValue }

  var title: String {
    switch self {
    case .overview: return "Overview"
    case .messages: return "Messages"
    case .memories: return "Memories"
    case .commitments: return "Commitments"
    }
  }
}

// MARK: - Page

struct PersonProfilePage: View {
  let person: PeopleIntelPerson
  var onBack: () -> Void
  /// Routes a person-scoped prompt into chat. No-op when the host cannot chat.
  var onAsk: (String) -> Void = { _ in }

  @Environment(\.sbTheme) private var sb
  /// Decoded here rather than passed in so the People list does not have to own
  /// (or reload) the companion fields just to open one profile.
  @State private var context: PeopleProfileContext = .empty
  @StateObject private var history = PersonMessageHistoryModel()
  @StateObject private var memories = PersonMemoriesModel()
  @StateObject private var commitments = PersonCommitmentsModel()
  @State private var tab: PersonProfileTab = .overview
  @State private var askText: String = ""
  @State private var shareNote: String?
  @State private var isSharing = false

  private var extras: PersonProfileExtras { context.extras(for: person.id) }

  private var firstName: String {
    person.name.split(separator: " ").first.map(String.init) ?? person.name
  }

  var body: some View {
    VStack(spacing: 0) {
      topBar
      ScrollView {
        VStack(alignment: .leading, spacing: 18) {
          hero
          identityRows
          askBar
          actionChips
          tabStrip
          tabContent
        }
        .padding(.horizontal, 28)
        .padding(.top, 22)
        .padding(.bottom, 40)
        .frame(maxWidth: 860, alignment: .leading)
        .frame(maxWidth: .infinity, alignment: .leading)
      }
    }
    .onExitCommand(perform: onBack)
    .task(id: person.id) {
      // ~400 KB of JSON — decode off the main actor, like the People list does.
      context = await Task.detached(priority: .userInitiated) {
        PeopleProfileExtrasLoader.load(uid: nil)
      }.value
      await history.load(
        personID: person.id, contactName: person.contactName, displayName: person.name)
      await memories.load(
        personID: person.id, backendPersonID: person.personUUID, displayName: person.name)
      await commitments.load(
        profileID: person.id,
        displayName: person.name,
        contactName: person.contactName,
        aliases: person.aliases)
    }
  }

  // MARK: Top bar

  private var topBar: some View {
    HStack(spacing: 10) {
      Button(action: onBack) {
        HStack(spacing: 5) {
          Image(systemName: "chevron.left").font(.system(size: 11, weight: .semibold))
          Text("People").geist(size: 12, weight: .medium)
        }
        .foregroundStyle(sb.ink(.w6))
      }
      .buttonStyle(.plain)
      .accessibilityIdentifier("person-profile-back")

      Spacer()

      if let note = shareNote {
        Text(note)
          .geist(size: 11)
          .foregroundStyle(sb.ink(.w5))
          .transition(.opacity)
      }
      profileActionButton(
        title: "Export", icon: "square.and.arrow.down", identifier: "person-profile-export"
      ) {
        Task { await exportProfile(send: false) }
      }
      profileActionButton(
        title: "Send", icon: "paperplane", identifier: "person-profile-send", prominent: true
      ) {
        Task { await exportProfile(send: true) }
      }
      .disabled(isSharing)
    }
    .padding(.horizontal, 28)
    .padding(.vertical, 12)
    .background(sb.panel)
    .overlay(alignment: .bottom) { Rectangle().fill(sb.ink(.w09)).frame(height: 1) }
  }

  private func profileActionButton(
    title: String, icon: String, identifier: String, prominent: Bool = false,
    action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      HStack(spacing: 5) {
        Image(systemName: icon).font(.system(size: 10, weight: .semibold))
        Text(title).geist(size: 11, weight: .medium)
      }
      .foregroundStyle(prominent ? sb.inkInverted : sb.ink(.w7))
      .padding(.horizontal, 11)
      .padding(.vertical, 6)
      .background(
        RoundedRectangle(cornerRadius: 8, style: .continuous)
          .fill(prominent ? sb.ink : sb.ink(.w08))
      )
    }
    .buttonStyle(.plain)
    .accessibilityIdentifier(identifier)
  }

  // MARK: Hero

  private var hero: some View {
    HStack(alignment: .center, spacing: 16) {
      PersonProfileAvatar(person: person, size: 64)
      VStack(alignment: .leading, spacing: 4) {
        Text(person.name)
          .geist(size: 30, weight: .semibold)
          .foregroundStyle(sb.ink)
          .textSelection(.enabled)
        if let subtitle = heroSubtitle {
          Text(subtitle)
            .geist(size: 13)
            .foregroundStyle(sb.ink(.w55))
            .textSelection(.enabled)
        }
      }
      Spacer(minLength: 0)
    }
  }

  private var heroSubtitle: String? {
    let candidates = [extras.role, person.relationship, person.circle?.label]
    return candidates.compactMap { $0 }.first { !$0.isEmpty }
  }

  // MARK: Identity

  @ViewBuilder private var identityRows: some View {
    let rows = identityItems
    if !rows.isEmpty {
      VStack(alignment: .leading, spacing: 7) {
        ForEach(rows) { row in
          HStack(spacing: 8) {
            Image(systemName: row.icon)
              .font(.system(size: 11))
              .foregroundStyle(sb.ink(.w4))
              .frame(width: 14, alignment: .center)
            if let url = row.url {
              Link(row.value, destination: url)
                .geist(size: 12)
                .foregroundStyle(sb.ink(.w7))
            } else {
              Text(row.value)
                .geist(size: 12)
                .foregroundStyle(sb.ink(.w6))
                .textSelection(.enabled)
            }
          }
        }
      }
    }
  }

  private struct IdentityRow: Identifiable {
    let id: String
    let icon: String
    let value: String
    let url: URL?
  }

  private var identityItems: [IdentityRow] {
    var rows: [IdentityRow] = []
    if let contact = person.contactName, !contact.isEmpty, contact != person.name {
      rows.append(IdentityRow(id: "contact", icon: "person.crop.circle", value: contact, url: nil))
    }
    if let linkedin = person.linkedin, !linkedin.isEmpty,
      let label = linkedin.displayText, !label.isEmpty
    {
      let url = linkedin.url.flatMap(URL.init(string:))
      rows.append(IdentityRow(id: "linkedin", icon: "link", value: label, url: url))
    }
    // One affiliation only: the rest live under Overview. A profile header that
    // lists five organizations reads as a dump, not an identity.
    if let affiliation = extras.affiliations.first {
      rows.append(
        IdentityRow(
          id: "aff-\(affiliation.id)", icon: affiliationIcon(affiliation.kind),
          value: affiliation.name, url: nil))
    }
    return Array(rows.prefix(3))
  }

  private func affiliationIcon(_ kind: String) -> String {
    switch kind.lowercased() {
    case "company": return "building.2"
    case "school", "university": return "graduationcap"
    default: return "briefcase"
    }
  }

  // MARK: Ask bar

  private var askBar: some View {
    HStack(spacing: 8) {
      Image(systemName: "sparkles").font(.system(size: 12)).foregroundStyle(sb.ink(.w4))
      TextField("Ask anything about \(firstName)", text: $askText)
        .textFieldStyle(.plain)
        .geist(size: 13)
        .foregroundStyle(sb.ink)
        .onSubmit(submitAsk)
      if !askText.isEmpty {
        Button(action: submitAsk) {
          Image(systemName: "arrow.up.circle.fill")
            .font(.system(size: 16))
            .foregroundStyle(sb.ink(.w7))
        }
        .buttonStyle(.plain)
      }
    }
    .padding(.horizontal, 14)
    .padding(.vertical, 11)
    .sbCard(radius: 12)
    .accessibilityIdentifier("person-profile-ask")
  }

  private func submitAsk() {
    let trimmed = askText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return }
    onAsk("About \(person.name): \(trimmed)")
    askText = ""
  }

  // MARK: Action chips

  private var actionChips: some View {
    ScrollView(.horizontal, showsIndicators: false) {
      HStack(spacing: 8) {
        ForEach(suggestedPrompts, id: \.title) { prompt in
          Button {
            onAsk(prompt.body)
          } label: {
            HStack(spacing: 5) {
              Image(systemName: prompt.icon).font(.system(size: 10))
              Text(prompt.title).geist(size: 11, weight: .medium)
            }
            .foregroundStyle(sb.ink(.w7))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(Capsule().fill(sb.ink(.w07)))
          }
          .buttonStyle(.plain)
        }
      }
    }
  }

  private struct SuggestedPrompt {
    let title: String
    let icon: String
    let body: String
  }

  private var suggestedPrompts: [SuggestedPrompt] {
    [
      SuggestedPrompt(
        title: "Catch me up", icon: "clock.arrow.circlepath",
        body: "Catch me up on \(person.name) — what has happened between us recently?"),
      SuggestedPrompt(
        title: "What do I owe them?", icon: "checklist",
        body: "What open threads or commitments do I have with \(person.name)?"),
      SuggestedPrompt(
        title: "Draft a message", icon: "square.and.pencil",
        body: "Draft a message to \(person.name) picking up where we left off."),
    ]
  }

  // MARK: Tabs

  private var tabStrip: some View {
    HStack(spacing: 6) {
      ForEach(PersonProfileTab.allCases) { item in
        let selected = item == tab
        Button {
          withAnimation(SBMotion.standard) { tab = item }
        } label: {
          Text(item.title)
            .geist(size: 12, weight: selected ? .semibold : .medium)
            .foregroundStyle(selected ? sb.inkInverted : sb.ink(.w6))
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(Capsule().fill(selected ? sb.ink : sb.ink(.w06)))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("person-profile-tab-\(item.rawValue)")
      }
      Spacer(minLength: 0)
    }
  }

  @ViewBuilder private var tabContent: some View {
    switch tab {
    case .overview: overviewTab
    case .messages: PersonMessageLogView(model: history, personName: firstName)
    case .memories: PersonMemoriesView(model: memories, personName: firstName)
    case .commitments: commitmentsTab
    }
  }

  // MARK: Overview

  private var overviewTab: some View {
    VStack(alignment: .leading, spacing: 22) {
      if person.needsConfirmation == true, let reason = person.confirmReason, !reason.isEmpty {
        PersonProfileCallout(text: reason)
      }
      narrative
      channelsSection
      connectionsSection
      groupsSection
      bulletBlock("Facts", person.facts)
      bulletBlock("Activities", person.activities)
      if extras.affiliations.count > 1 {
        bulletBlock("Also affiliated with", extras.affiliations.dropFirst().map(\.name))
      }
      if !person.aliases.isEmpty {
        bulletBlock("Also known as", person.aliases)
      }
      if isOverviewEmpty {
        PersonProfileEmptyState(
          icon: "person.crop.circle.badge.questionmark",
          title: "Not much yet",
          message:
            "Omi builds this page from the conversations and messages you already have. It fills in as you talk to \(firstName)."
        )
      }
    }
  }

  private var isOverviewEmpty: Bool {
    person.who.isEmpty && person.now.isEmpty && person.overall.isEmpty
      && person.channels.isEmpty && (person.connections?.isEmpty ?? true)
      && extras.groups.isEmpty && person.facts.isEmpty && person.activities.isEmpty
  }

  @ViewBuilder private var narrative: some View {
    let blocks = [("Who", person.who), ("Now", person.now), ("Overall", person.overall)]
      .filter { !$0.1.isEmpty }
    if !blocks.isEmpty {
      VStack(alignment: .leading, spacing: 14) {
        ForEach(blocks, id: \.0) { title, text in
          VStack(alignment: .leading, spacing: 5) {
            SBSectionLabel(text: title)
            Text(text)
              .geist(size: 13)
              .foregroundStyle(sb.ink(.w75))
              .fixedSize(horizontal: false, vertical: true)
              .textSelection(.enabled)
          }
        }
      }
    }
  }

  @ViewBuilder private var channelsSection: some View {
    if !person.channels.isEmpty {
      VStack(alignment: .leading, spacing: 8) {
        SBSectionLabel(text: "Channels")
        ForEach(person.channels) { channel in
          HStack(spacing: 8) {
            Circle()
              .fill(PeopleChannelPalette.color(for: channel.key))
              .frame(width: 7, height: 7)
            Text(channel.label).geist(size: 12).foregroundStyle(sb.ink(.w7))
            Text("\(channel.count)").geistMono(size: 11).foregroundStyle(sb.ink(.w4))
            Spacer(minLength: 0)
            if let last = channel.last, !last.isEmpty {
              Text(last).geist(size: 11).foregroundStyle(sb.ink(.w4))
            }
          }
        }
      }
    }
  }

  @ViewBuilder private var connectionsSection: some View {
    let connections = person.connections ?? []
    if !connections.isEmpty {
      VStack(alignment: .leading, spacing: 8) {
        SBSectionLabel(text: "Who they know")
        ForEach(connections.prefix(5)) { connection in
          let detail = extras.connectionDetails[connection.id]
          VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 8) {
              Text(connection.name).geist(size: 12, weight: .medium).foregroundStyle(sb.ink(.w8))
              if let kind = detail?.kind, !kind.isEmpty {
                Text(kind)
                  .geist(size: 10)
                  .foregroundStyle(sb.ink(.w5))
                  .padding(.horizontal, 6)
                  .padding(.vertical, 2)
                  .background(Capsule().fill(sb.ink(.w06)))
              }
              Spacer(minLength: 0)
            }
            // `how` explains the edge in plain language; it is present on only
            // some connections, so fall back to the shared-group context.
            if let how = detail?.how, !how.isEmpty {
              Text(how).geist(size: 11).foregroundStyle(sb.ink(.w45))
                .fixedSize(horizontal: false, vertical: true)
            } else if let shared = detail?.context.first, !shared.isEmpty {
              Text("via \(shared)").geist(size: 11).foregroundStyle(sb.ink(.w45))
            }
          }
        }
      }
    }
  }

  @ViewBuilder private var groupsSection: some View {
    if !extras.groups.isEmpty {
      VStack(alignment: .leading, spacing: 8) {
        SBSectionLabel(text: "Shared groups")
        ForEach(extras.groups.prefix(6)) { group in
          VStack(alignment: .leading, spacing: 2) {
            Text(group.name).geist(size: 12).foregroundStyle(sb.ink(.w7))
            if let meaning = context.meaning(forGroup: group.name), !meaning.isEmpty {
              Text(meaning).geist(size: 11).foregroundStyle(sb.ink(.w45))
                .fixedSize(horizontal: false, vertical: true)
            }
          }
        }
      }
    }
  }

  @ViewBuilder private func bulletBlock(_ title: String, _ items: [String]) -> some View {
    if !items.isEmpty {
      VStack(alignment: .leading, spacing: 6) {
        SBSectionLabel(text: title)
        ForEach(items, id: \.self) { item in
          HStack(alignment: .top, spacing: 7) {
            Circle().fill(sb.ink(.w3)).frame(width: 4, height: 4).padding(.top, 6)
            Text(item)
              .geist(size: 12)
              .foregroundStyle(sb.ink(.w7))
              .fixedSize(horizontal: false, vertical: true)
              .textSelection(.enabled)
          }
        }
      }
    }
  }

  // MARK: Commitments

  private var commitmentsLayout: PersonCommitmentsTabLayout {
    PersonCommitmentsTabLayout(
      assigned: commitments.commitments,
      openThreads: person.openThreads,
      state: commitments.state)
  }

  /// Two different things live here and they are never mixed:
  ///
  /// 1. **Assigned** — real tasks that name this person, either as the one who has to act or
  ///    as the one who asked. Read from the backend, keyed on that person's id.
  /// 2. **Open threads** — prose the people pipeline noticed. Nobody is assigned to these.
  ///
  /// The old copy said none of this was assigned. That was accurate only while no task could
  /// carry a person at all; each section now states what it actually is.
  private var commitmentsTab: some View {
    let layout = commitmentsLayout
    return VStack(alignment: .leading, spacing: 22) {
      assignedCommitmentsSection(layout)
      openThreadsSection(layout)
      if layout.showsEmptyState {
        PersonProfileEmptyState(
          icon: "checklist",
          title: "Nothing open",
          message:
            "Tasks that name \(firstName) show up here, along with anything you left unresolved with them."
        )
      }
    }
  }

  @ViewBuilder private func assignedCommitmentsSection(_ layout: PersonCommitmentsTabLayout) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      SBSectionLabel(text: "Assigned")
      if layout.showsAssignedProgress {
        PersonProfileLoading(text: "Checking assigned tasks…")
      } else if case .failed(let reason) = layout.state {
        Text(reason)
          .geist(size: 11)
          .foregroundStyle(sb.ink(.w45))
      } else if layout.showsAssignedRows {
        Text("Tasks that name \(firstName). Each row says who has to act.")
          .geist(size: 11)
          .foregroundStyle(sb.ink(.w45))
        ForEach(layout.assigned) { item in
          commitmentRow(item)
        }
      } else if layout.showsAssignedPlaceholder {
        noAssignedTasksNote
      }
    }
    .accessibilityIdentifier("person-profile-commitments-assigned")
  }

  private var noAssignedTasksNote: some View {
    Text(
      "No tasks name \(firstName) yet. Omi assigns one only when a conversation names them outright."
    )
    .geist(size: 11)
    .foregroundStyle(sb.ink(.w45))
    .fixedSize(horizontal: false, vertical: true)
  }

  private func commitmentRow(_ item: PersonCommitmentItem) -> some View {
    HStack(alignment: .top, spacing: 8) {
      Image(systemName: item.completed ? "checkmark.circle.fill" : "circle")
        .font(.system(size: 11))
        .foregroundStyle(sb.ink(item.completed ? .w35 : .w5))
        .padding(.top, 1)
      VStack(alignment: .leading, spacing: 3) {
        Text(item.description)
          .geist(size: 12)
          .foregroundStyle(sb.ink(item.completed ? .w45 : .w8))
          .strikethrough(item.completed, color: sb.ink(.w35))
          .fixedSize(horizontal: false, vertical: true)
          .textSelection(.enabled)
        HStack(spacing: 6) {
          Text(item.direction.label)
            .geist(size: 10)
            .foregroundStyle(sb.ink(.w5))
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Capsule().fill(sb.ink(.w06)))
          if let due = item.dueAt {
            Text(Self.commitmentDueFormatter.string(from: due))
              .geist(size: 10)
              .foregroundStyle(sb.ink(.w45))
          }
        }
      }
      Spacer(minLength: 0)
    }
  }

  @ViewBuilder private func openThreadsSection(_ layout: PersonCommitmentsTabLayout) -> some View {
    if layout.showsOpenThreads {
      VStack(alignment: .leading, spacing: 8) {
        SBSectionLabel(text: "Open threads")
        Text("Loose ends Omi noticed with \(firstName). Nobody is assigned to these.")
          .geist(size: 11)
          .foregroundStyle(sb.ink(.w45))
        ForEach(layout.openThreads, id: \.self) { item in
          HStack(alignment: .top, spacing: 7) {
            Circle().fill(sb.ink(.w3)).frame(width: 4, height: 4).padding(.top, 6)
            Text(item)
              .geist(size: 12)
              .foregroundStyle(sb.ink(.w7))
              .fixedSize(horizontal: false, vertical: true)
              .textSelection(.enabled)
          }
        }
      }
      .accessibilityIdentifier("person-profile-commitments-threads")
    }
  }

  private static let commitmentDueFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .none
    return formatter
  }()

  // MARK: Export / send

  private func exportProfile(send: Bool) async {
    isSharing = true
    defer { isSharing = false }

    let document = PersonProfileDocument(person: person, context: context)
    guard let pdf = PersonProfileRenderer.renderPDF(document, size: PersonProfileDocument.pageSize)
    else {
      await note("Could not render the page.")
      return
    }
    let url: URL
    do {
      url = try PersonProfileRenderer.write(pdf: pdf, personName: person.name)
    } catch {
      await note("Could not save the page.")
      return
    }
    guard send else {
      _ = PersonProfileShare.revealInFinder(url)
      await note("Saved to Downloads.")
      return
    }

    let personID = person.id
    let contactName = person.contactName
    let displayName = person.name
    // Identity keys first: matching on these is what keeps a renamed contact addressable.
    let identityKeys = person.handles
    let handles = await Task.detached(priority: .userInitiated) {
      PersonHandleResolver.resolve(
        personID: personID, contactName: contactName, displayName: displayName,
        identityKeys: identityKeys)
    }.value

    let recipients = handles.phones + handles.emails
    let body = "Here's what I have on our conversations, \(firstName)."
    switch PersonProfileShare.compose(fileURL: url, recipients: recipients, body: body) {
    case .composerOpened:
      await note("Opened a draft — you send it.")
    case .unavailable(let reason):
      _ = PersonProfileShare.revealInFinder(url)
      await note("Saved to Downloads (\(reason)).")
    case .revealedInFinder, .copied:
      await note("Saved to Downloads.")
    }
  }

  @MainActor private func note(_ text: String) async {
    withAnimation(SBMotion.standard) { shareNote = text }
    try? await Task.sleep(nanoseconds: 4_000_000_000)
    withAnimation(SBMotion.standard) { shareNote = nil }
  }
}

// MARK: - Message log

private struct PersonMessageLogView: View {
  @ObservedObject var model: PersonMessageHistoryModel
  let personName: String
  @Environment(\.sbTheme) private var sb

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      switch model.state {
      case .idle, .loading:
        PersonProfileLoading(text: "Reading your messages…")
      case .needsConsent:
        PersonProfileEmptyState(
          icon: "lock",
          title: "Message history is off",
          message:
            "Turn on iMessage mapping on the People tab to read your conversation with \(personName). Messages are read on this Mac and never uploaded."
        )
      case .needsFullDiskAccess:
        PersonProfileEmptyState(
          icon: "folder.badge.questionmark",
          title: "Full Disk Access needed",
          message:
            "macOS needs Full Disk Access before Omi can read Messages. Grant it from the People tab."
        )
      case .unavailable:
        PersonProfileEmptyState(
          icon: "bubble.left.and.bubble.right",
          title: "No message store found",
          message: "Omi could not find Messages or WhatsApp data on this Mac.")
      case .failed(let reason):
        PersonProfileEmptyState(
          icon: "exclamationmark.triangle", title: "Could not read messages", message: reason)
      case .loaded:
        if model.messages.isEmpty {
          PersonProfileEmptyState(
            icon: "bubble.left",
            title: "No messages with \(personName)",
            message: "Omi found no one-to-one thread matching this person.")
        } else {
          if model.canLoadMore {
            Button {
              Task { await model.loadMore() }
            } label: {
              Text("Load earlier messages")
                .geist(size: 11, weight: .medium)
                .foregroundStyle(sb.ink(.w6))
            }
            .buttonStyle(.plain)
          }
          ForEach(groupedByDay, id: \.0) { day, items in
            VStack(alignment: .leading, spacing: 6) {
              Text(day)
                .geist(size: 10, weight: .semibold)
                .foregroundStyle(sb.ink(.w4))
                .padding(.top, 6)
              ForEach(items) { message in
                PersonMessageBubble(message: message)
              }
            }
          }
        }
      }
    }
  }

  private var groupedByDay: [(String, [PersonMessage])] {
    let calendar = Calendar.current
    let grouped = Dictionary(grouping: model.messages) { message in
      calendar.startOfDay(for: message.date)
    }
    return
      grouped
      .sorted { $0.key < $1.key }
      .map { (PersonProfileFormat.day.string(from: $0.key), $0.value.sorted { $0.date < $1.date }) }
  }
}

private struct PersonMessageBubble: View {
  let message: PersonMessage
  @Environment(\.sbTheme) private var sb

  var body: some View {
    HStack {
      if message.isFromMe { Spacer(minLength: 40) }
      VStack(alignment: message.isFromMe ? .trailing : .leading, spacing: 2) {
        Text(message.text)
          .geist(size: 12)
          .foregroundStyle(message.isFromMe ? sb.inkInverted : sb.ink(.w8))
          .padding(.horizontal, 11)
          .padding(.vertical, 7)
          .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
              .fill(message.isFromMe ? sb.ink.opacity(0.86) : sb.ink(.w08))
          )
          .textSelection(.enabled)
        Text(PersonProfileFormat.time.string(from: message.date))
          .geistMono(size: 9)
          .foregroundStyle(sb.ink(.w3))
      }
      if !message.isFromMe { Spacer(minLength: 40) }
    }
  }
}

// MARK: - Memories

private struct PersonMemoriesView: View {
  @ObservedObject var model: PersonMemoriesModel
  let personName: String
  @Environment(\.sbTheme) private var sb

  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      switch model.state {
      case .idle, .loading:
        PersonProfileLoading(text: "Finding memories…")
      case .unavailable:
        PersonProfileEmptyState(
          icon: "brain", title: "Memories unavailable",
          message: "Omi could not open the local memory store.")
      case .failed(let reason):
        PersonProfileEmptyState(
          icon: "exclamationmark.triangle", title: "Could not load memories", message: reason)
      case .loaded:
        if model.memories.isEmpty {
          PersonProfileEmptyState(
            icon: "brain",
            title: "No memories about \(personName) yet",
            message: "Facts Omi learns about \(personName) will collect here.")
        } else {
          ForEach(model.memories) { memory in
            VStack(alignment: .leading, spacing: 3) {
              Text(memory.content)
                .geist(size: 12)
                .foregroundStyle(sb.ink(.w75))
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
              if let created = memory.createdAt {
                Text(PersonProfileFormat.day.string(from: created))
                  .geistMono(size: 9)
                  .foregroundStyle(sb.ink(.w3))
              }
            }
            .padding(.vertical, 4)
          }
        }
      }
    }
  }
}

// MARK: - Shared small views

struct PersonProfileAvatar: View {
  let person: PeopleIntelPerson
  let size: CGFloat
  @Environment(\.sbTheme) private var sb
  // Decoding on every body evaluation is what the 38pt row avatar does; at hero
  // size that is a visible cost, so the image is resolved once per identity.
  @State private var image: NSImage?

  var body: some View {
    Group {
      if let image {
        Image(nsImage: image).resizable().scaledToFill()
      } else {
        Text(person.initials)
          .geist(size: size * 0.34, weight: .semibold)
          .foregroundStyle(sb.ink(.w6))
          .frame(maxWidth: .infinity, maxHeight: .infinity)
          .background(sb.ink(.w08))
      }
    }
    .frame(width: size, height: size)
    .clipShape(Circle())
    .overlay(Circle().stroke(sb.ink(.w09), lineWidth: 1))
    .task(id: person.id) {
      let path = person.photoPath ?? PeoplePhotos.photoPath(forID: person.id)
      guard let path else {
        image = nil
        return
      }
      image = await Task.detached(priority: .utility) { NSImage(contentsOfFile: path) }.value
    }
  }
}

private struct PersonProfileCallout: View {
  let text: String
  @Environment(\.sbTheme) private var sb

  var body: some View {
    HStack(alignment: .top, spacing: 8) {
      Image(systemName: "questionmark.circle").font(.system(size: 12))
      Text(text).geist(size: 12).fixedSize(horizontal: false, vertical: true)
    }
    .foregroundStyle(sb.ink(.w7))
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(sb.ink(.w06)))
  }
}

private struct PersonProfileEmptyState: View {
  let icon: String
  let title: String
  let message: String
  @Environment(\.sbTheme) private var sb

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      Image(systemName: icon).font(.system(size: 18)).foregroundStyle(sb.ink(.w3))
      Text(title).geist(size: 13, weight: .medium).foregroundStyle(sb.ink(.w7))
      Text(message)
        .geist(size: 12)
        .foregroundStyle(sb.ink(.w45))
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(.vertical, 18)
  }
}

private struct PersonProfileLoading: View {
  let text: String
  @Environment(\.sbTheme) private var sb

  var body: some View {
    HStack(spacing: 8) {
      ProgressView().controlSize(.small)
      Text(text).geist(size: 12).foregroundStyle(sb.ink(.w5))
    }
    .padding(.vertical, 14)
  }
}

enum PersonProfileFormat {
  static let day: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "EEE, MMM d, yyyy"
    return f
  }()

  static let time: DateFormatter = {
    let f = DateFormatter()
    f.timeStyle = .short
    f.dateStyle = .none
    return f
  }()
}

// MARK: - Printable document

/// The print-styled view rendered offscreen for export/send. Deliberately narrow
/// and text-only: no scroll views, no async image loading, nothing that needs a
/// live window to lay out correctly.
struct PersonProfileDocument: View {
  let person: PeopleIntelPerson
  let context: PeopleProfileContext

  static let pageSize = CGSize(width: 612, height: 792)  // US Letter at 72dpi

  private var extras: PersonProfileExtras { context.extras(for: person.id) }

  var body: some View {
    VStack(alignment: .leading, spacing: 14) {
      Text(person.name).font(.system(size: 26, weight: .semibold))
      if let role = extras.role ?? emptyToNil(person.relationship) {
        Text(role).font(.system(size: 12)).foregroundStyle(.secondary)
      }
      section("Who", person.who)
      section("Now", person.now)
      section("Overall", person.overall)
      list("Facts", person.facts)
      list("Open threads", person.openThreads)
      if !extras.groups.isEmpty {
        list("Shared groups", extras.groups.map(\.name))
      }
      Spacer(minLength: 0)
      Text("Generated by Omi")
        .font(.system(size: 9))
        .foregroundStyle(.tertiary)
    }
    .padding(44)
    .frame(width: Self.pageSize.width, height: Self.pageSize.height, alignment: .topLeading)
    .background(Color.white)
    .environment(\.colorScheme, .light)
  }

  private func emptyToNil(_ value: String) -> String? { value.isEmpty ? nil : value }

  @ViewBuilder private func section(_ title: String, _ body: String) -> some View {
    if !body.isEmpty {
      VStack(alignment: .leading, spacing: 3) {
        Text(title.uppercased())
          .font(.system(size: 9, weight: .semibold))
          .foregroundStyle(.secondary)
        Text(body).font(.system(size: 11)).fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  @ViewBuilder private func list(_ title: String, _ items: [String]) -> some View {
    if !items.isEmpty {
      VStack(alignment: .leading, spacing: 3) {
        Text(title.uppercased())
          .font(.system(size: 9, weight: .semibold))
          .foregroundStyle(.secondary)
        ForEach(items.prefix(12), id: \.self) { item in
          Text("• \(item)").font(.system(size: 11)).fixedSize(horizontal: false, vertical: true)
        }
      }
    }
  }
}
