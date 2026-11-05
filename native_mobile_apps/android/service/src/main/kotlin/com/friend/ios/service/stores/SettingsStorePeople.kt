package com.friend.ios.service.stores

import com.friend.ios.core.models.Person
import com.friend.ios.core.models.PersonConversation
import com.friend.ios.persistence.Preferences.Key
import java.text.Normalizer

/**
 * Port of `SettingsStore+People.swift`: Voice & People beyond add/rename/delete (Flutter
 * `settings/people`, `person_detail_page`, `people_clean_up_page`): stats, search, pinning, voice
 * samples, bulk clean-up.
 */

/** Talk time, last heard and conversation counts too (slower on the server, so on demand). */
suspend fun SettingsStore.loadPeopleWithStats() {
    runCatching { api.peopleWithStats() }.getOrNull()?.let { list -> people = list.sortedBy { it.name } }
}

fun SettingsStore.person(id: String): Person? = people.firstOrNull { it.id == id }

/** Case- and accent-insensitive name filter; everyone for an empty query. */
fun SettingsStore.people(matching: String): List<Person> {
    val trimmed = fold(matching.trim())
    if (trimmed.isEmpty()) return people
    return people.filter { fold(it.name).contains(trimmed) }
}

private fun fold(text: String): String = Normalizer.normalize(text, Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "").lowercase()

/** Who Clean up offers to delete: people Omi is unsure about, never pinned ones. */
val SettingsStore.cleanUpCandidates: List<Person>
    get() = people.filter { !it.isPinned && it.confidence == Person.Confidence.Unverified }

suspend fun SettingsStore.setPinned(id: String, pinned: Boolean) {
    val previous = person(id) ?: return
    replacePerson(previous.copy(isPinned = pinned))
    attempt({ api.setPersonPinned(id, pinned) }) { replacePerson(previous) }
}

suspend fun SettingsStore.deleteSample(personID: String, sampleIndex: Int) {
    val previous = person(personID) ?: return
    if (sampleIndex !in previous.sampleURLs.indices) return
    replacePerson(
        previous.copy(
            sampleURLs = previous.sampleURLs.filterIndexed { index, _ -> index != sampleIndex },
            sampleCount = maxOf(0, previous.sampleCount - 1),
        ),
    )
    attempt({ api.deleteSpeechSample(personID, sampleIndex) }) { replacePerson(previous) }
}

/** Deletes several people at once; anyone the backend refuses comes back. */
suspend fun SettingsStore.deletePeople(ids: Set<String>) {
    val removed = people.filter { it.id in ids }
    people = people.filter { it.id !in ids }
    val failed = mutableListOf<Person>()
    for (person in removed) {
        try {
            api.deletePerson(person.id)
        } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            failed += person
        }
    }
    lastError = if (failed.isEmpty()) null else "${failed.size} not deleted"
    if (failed.isNotEmpty()) people = (people + failed).sortedBy { it.name }
}

/** One page of this person's conversations, newest first; null when it could not load. */
suspend fun SettingsStore.conversations(personID: String, page: Int, perPage: Int = 20): List<PersonConversation>? =
    runCatching { api.conversationsWithPerson(personID, page, perPage) }.getOrNull()

private fun SettingsStore.replacePerson(person: Person) {
    people = people.map { if (it.id == person.id) person else it }
}

/**
 * Port of `SettingsStore+Transcription.swift`: Listening > Detect languages, the backend's
 * `single_language_mode`, read at the start of every recording.
 */

/** Last known value (Flutter's `cachedSingleLanguageMode`), shown before the backend answers. */
val SettingsStore.detectsLanguages: Boolean
    get() = !preferences.bool(Key.CachedSingleLanguageMode)

/** Asks the backend; returns the current value. */
suspend fun SettingsStore.loadLanguageDetection(): Boolean {
    runCatching { api.singleLanguageMode() }.getOrNull()?.let { preferences.set(Key.CachedSingleLanguageMode, it) }
    return detectsLanguages
}

/** Returns whether the backend took it (the switch goes back otherwise). */
suspend fun SettingsStore.setLanguageDetection(detects: Boolean): Boolean {
    lastError = null
    return try {
        api.setSingleLanguageMode(!detects)
        preferences.set(Key.CachedSingleLanguageMode, !detects)
        true
    } catch (e: Exception) {
        if (e is kotlinx.coroutines.CancellationException) throw e
        lastError = e.toString()
        false
    }
}

/** `makeImportStore()` (`StoreFactories.swift`). */
fun SettingsStore.makeImportStore(): ImportStore = ImportStore(api, scope)

/** `MemoriesStore.makeGraphStore(userName:)` (`StoreFactories.swift`). */
fun MemoriesStore.makeGraphStore(userName: String?): KnowledgeGraphStore = KnowledgeGraphStore(api, userName)
