import AppKit
import OmiTheme
import SwiftUI

// A directory of people reads better as a table than as a stack of cards: one
// row per person, columns you can sort, and enough restraint that several
// hundred people stay scannable.

enum PeopleListSort: String, CaseIterable, Identifiable, Sendable {
  case lastTouch, name, reach

  var id: String { rawValue }

  var title: String {
    switch self {
    case .lastTouch: return "Last touch"
    case .name: return "Person"
    case .reach: return "Channels"
    }
  }
}

/// Pure list shaping, kept out of the view so it can be tested directly.
enum PeopleListOrder {
  static func reach(_ person: PeopleIntelPerson) -> Int {
    person.channels.reduce(0) { $0 + $1.count }
  }

  static func sorted(
    _ people: [PeopleIntelPerson], by sort: PeopleListSort, descending: Bool
  ) -> [PeopleIntelPerson] {
    let ordered: [PeopleIntelPerson]
    switch sort {
    case .name:
      ordered = people.sorted {
        $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
      }
    case .reach:
      ordered = people.sorted { lhs, rhs in
        let l = reach(lhs)
        let r = reach(rhs)
        if l == r { return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending }
        return l < r
      }
    case .lastTouch:
      // People with no recorded touch sort as oldest rather than dropping out.
      ordered = people.sorted { lhs, rhs in
        let l = PeopleDateFormat.date(from: lhs.lastTouch?.date) ?? .distantPast
        let r = PeopleDateFormat.date(from: rhs.lastTouch?.date) ?? .distantPast
        if l == r { return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending }
        return l < r
      }
    }
    return descending ? ordered.reversed() : ordered
  }
}

struct PeopleListTable: View {
  let people: [PeopleIntelPerson]
  @Binding var sort: PeopleListSort
  @Binding var descending: Bool
  let onSelect: (PeopleIntelPerson) -> Void

  @Environment(\.sbTheme) private var sb
  /// Why names may be missing. Resolved off the main actor on appear; `.authorized` until then so
  /// the notice never flashes for the (normal) case where names are fine.
  @State private var namesAccess: PeopleContactsAccess = .authorized

  private var rows: [PeopleIntelPerson] {
    PeopleListOrder.sorted(people, by: sort, descending: descending)
  }

  var body: some View {
    VStack(spacing: 0) {
      // Without Contacts, iMessage people are listed by phone number. Say so, once, instead of
      // leaving a wall of numbers unexplained.
      if let notice = namesAccess.notice { namesNotice(notice) }
      header
      Divider().overlay(sb.ink(.w09))
      ScrollView {
        LazyVStack(spacing: 0) {
          ForEach(rows) { person in
            PersonTableRow(person: person) { onSelect(person) }
            Divider().overlay(sb.ink(.w05))
          }
        }
        .padding(.bottom, 28)
      }
    }
    .padding(.horizontal, 28)
    .task { await refreshNamesAccess() }
    // Coming back from System Settings is the one moment this can change while the tab is open.
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      Task { await refreshNamesAccess() }
    }
  }

  private func refreshNamesAccess() async {
    namesAccess = await Task.detached(priority: .utility) { PeopleContactsAccess.current() }.value
  }

  private func namesNotice(_ text: String) -> some View {
    HStack(alignment: .center, spacing: 8) {
      Image(systemName: "person.crop.circle.badge.questionmark")
        .font(.system(size: 12, weight: .medium))
        .foregroundStyle(sb.ink(.w45))
      Text(text)
        .geist(size: 11.5)
        .foregroundStyle(sb.ink(.w6))
        .fixedSize(horizontal: false, vertical: true)
      Spacer(minLength: 8)
      // Only offered when System Settings is actually where the fix lives; a pending prompt is
      // answered in place, and we never re-ask (macOS ignores a second request after a denial).
      if namesAccess.canOpenSettings {
        Button {
          PeopleContactsAccess.openSettings()
        } label: {
          Text("Open Settings")
            .geist(size: 11, weight: .semibold)
            .foregroundStyle(sb.ink(.w75))
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Capsule().fill(sb.ink(.w08)))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("people-contacts-open-settings")
      }
    }
    .padding(.horizontal, 12)
    .padding(.vertical, 9)
    .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(sb.ink(.w05)))
    .padding(.bottom, 10)
    .accessibilityIdentifier("people-contacts-names-notice")
  }

  private var header: some View {
    HStack(spacing: 12) {
      columnButton(.name).frame(maxWidth: .infinity, alignment: .leading)
      columnButton(.reach).frame(width: 108, alignment: .leading)
      columnButton(.lastTouch).frame(width: 116, alignment: .trailing)
    }
    .padding(.vertical, 8)
    .padding(.horizontal, 8)
  }

  private func columnButton(_ column: PeopleListSort) -> some View {
    Button {
      if sort == column {
        descending.toggle()
      } else {
        sort = column
        // Recency reads newest-first; names read A-Z. Pick the obvious default.
        descending = column != .name
      }
    } label: {
      HStack(spacing: 3) {
        Text(column.title)
          .geist(size: 10, weight: .semibold)
          .foregroundStyle(sb.ink(sort == column ? .w6 : .w35))
        if sort == column {
          Image(systemName: descending ? "chevron.down" : "chevron.up")
            .font(.system(size: 7, weight: .bold))
            .foregroundStyle(sb.ink(.w45))
        }
      }
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .accessibilityIdentifier("people-column-\(column.rawValue)")
  }
}

private struct PersonTableRow: View {
  let person: PeopleIntelPerson
  let onTap: () -> Void

  @Environment(\.sbTheme) private var sb
  @State private var isHovering = false

  var body: some View {
    Button(action: onTap) {
      HStack(spacing: 12) {
        HStack(spacing: 10) {
          PersonProfileAvatar(person: person, size: 28)
          VStack(alignment: .leading, spacing: 1) {
            Text(person.name)
              .geist(size: 12.5, weight: .medium)
              .foregroundStyle(sb.ink(.w85))
              .lineLimit(1)
            if let subtitle {
              Text(subtitle)
                .geist(size: 10.5)
                .foregroundStyle(sb.ink(.w4))
                .lineLimit(1)
                .truncationMode(.tail)
            }
          }
        }
        .frame(maxWidth: .infinity, alignment: .leading)

        HStack(spacing: 6) {
          ChannelDots(channels: person.channels)
          Text("\(PeopleListOrder.reach(person))")
            .geistMono(size: 10)
            .foregroundStyle(sb.ink(.w35))
        }
        .frame(width: 108, alignment: .leading)

        Text(PeopleDateFormat.relative(from: person.lastTouch?.date) ?? "—")
          .geistMono(size: 10.5)
          .foregroundStyle(sb.ink(.w45))
          .frame(width: 116, alignment: .trailing)
      }
      .padding(.vertical, 9)
      .padding(.horizontal, 8)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .background(
      RoundedRectangle(cornerRadius: 8, style: .continuous)
        .fill(isHovering ? sb.ink(.w05) : Color.clear)
    )
    .onHover { hovering in
      isHovering = hovering
      if hovering { NSCursor.pointingHand.push() } else { NSCursor.pop() }
    }
    .accessibilityIdentifier("person-row-\(person.id)")
  }

  /// One short line: the relationship if we have one, else the contact name.
  private var subtitle: String? {
    let relationship = person.relationship.trimmingCharacters(in: .whitespaces)
    if !relationship.isEmpty {
      let clause =
        relationship.split(whereSeparator: { ";.".contains($0) }).first.map(String.init)
        ?? relationship
      return clause.trimmingCharacters(in: .whitespaces)
    }
    if let contact = person.contactName, contact != person.name, !contact.isEmpty { return contact }
    return nil
  }
}
