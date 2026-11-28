import Foundation
import OmiCore
import OmiNetwork

/// Voice & People beyond add/rename/delete (Flutter `settings/people`, `person_detail_page`,
/// `people_clean_up_page`): stats, search, pinning, voice samples, bulk clean-up.
public extension SettingsStore {
    /// Talk time, last heard and conversation counts too (slower on the server, so on demand).
    func loadPeopleWithStats() async {
        if let list = try? await api.peopleWithStats() { people = list.sorted { $0.name < $1.name } }
    }

    func person(_ id: String) -> Person? {
        people.first { $0.id == id }
    }

    /// Case- and accent-insensitive name filter; everyone for an empty query.
    func people(matching query: String) -> [Person] {
        let trimmed = query.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return people }
        return people.filter { $0.name.range(of: trimmed, options: [.caseInsensitive, .diacriticInsensitive]) != nil }
    }

    /// Who Clean up offers to delete: people Omi is unsure about, never pinned ones.
    var cleanUpCandidates: [Person] {
        people.filter { !$0.isPinned && $0.confidence == .unverified }
    }

    func setPinned(_ id: String, _ pinned: Bool) async {
        guard let index = people.firstIndex(where: { $0.id == id }) else { return }
        let previous = people[index]
        people[index].isPinned = pinned
        await attempt {
            try await self.api.setPersonPinned(id, pinned: pinned)
        } rollback: {
            self.replace(previous)
        }
    }

    func deleteSample(of personID: String, at sampleIndex: Int) async {
        guard let index = people.firstIndex(where: { $0.id == personID }),
              people[index].sampleURLs.indices.contains(sampleIndex) else { return }
        let previous = people[index]
        people[index].sampleURLs.remove(at: sampleIndex)
        people[index].sampleCount = max(0, people[index].sampleCount - 1)
        await attempt {
            try await self.api.deleteSpeechSample(personID: personID, index: sampleIndex)
        } rollback: {
            self.replace(previous)
        }
    }

    /// Deletes several people at once; anyone the backend refuses comes back.
    func deletePeople(_ ids: Set<String>) async {
        let removed = people.filter { ids.contains($0.id) }
        people.removeAll { ids.contains($0.id) }
        var failed: [Person] = []
        for person in removed {
            do {
                try await api.deletePerson(person.id)
            } catch {
                failed.append(person)
            }
        }
        lastError = failed.isEmpty ? nil : "\(failed.count) not deleted"
        if !failed.isEmpty { people = (people + failed).sorted { $0.name < $1.name } }
    }

    /// One page of this person's conversations, newest first; `nil` when it could not load.
    func conversations(with personID: String, page: Int, perPage: Int = 20) async -> [Conversation]? {
        try? await api.conversations(withPerson: personID, page: page, perPage: perPage)
    }

    private func replace(_ person: Person) {
        if let index = people.firstIndex(where: { $0.id == person.id }) { people[index] = person }
    }
}
