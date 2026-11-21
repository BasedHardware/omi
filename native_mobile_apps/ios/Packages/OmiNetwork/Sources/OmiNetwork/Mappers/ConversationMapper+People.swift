import Foundation
import OmiCore

extension ConversationMapper {
    /// Participants first (they carry organizations; AI agents skipped), then calendar attendees.
    /// An attendee entry is a display name or an address; `attendee_emails` fills in the address
    /// when it is a name. One person per address.
    static func people(_ participants: [OmiAPI.Participant], event: OmiAPI.CalendarEventLink?) -> [ConversationPerson] {
        let fromSummary = participants.filter { $0.isAiAgent != true }.map {
            ConversationPerson(name: nonBlank($0.name), email: nonBlank($0.email), organization: nonBlank($0.organization))
        }
        var emails = event?.attendeeEmails ?? []
        var fromCalendar: [ConversationPerson] = (event?.attendees ?? []).map { entry in
            if entry.contains("@") {
                emails.removeAll { $0 == entry }
                return ConversationPerson(name: nil, email: entry)
            }
            let first = (entry.split(separator: " ").first.map(String.init) ?? entry).lowercased()
            let index = emails.firstIndex { $0.split(separator: "@").first.map { $0.lowercased().hasPrefix(first) } ?? false }
            let email = index.map { emails.remove(at: $0) }
            return ConversationPerson(name: entry, email: email)
        }
        fromCalendar += emails.map { ConversationPerson(name: nil, email: $0) }
        let known = Set(fromSummary.compactMap { $0.email?.lowercased() })
        return fromSummary + fromCalendar.filter { person in person.email.map { !known.contains($0.lowercased()) } ?? true }
    }

    private static func nonBlank(_ text: String?) -> String? {
        guard let text, !text.trimmingCharacters(in: .whitespaces).isEmpty else { return nil }
        return text
    }
}
