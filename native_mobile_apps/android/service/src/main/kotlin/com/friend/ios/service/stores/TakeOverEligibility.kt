package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem

/**
 * Port of `TakeOverEligibility.swift`: whether "Omi takes over" makes sense for a task: only the
 * user's own tasks (the backend's `owner`), and only ones Omi can plausibly do on a screen:
 * write, send, research, book, schedule, order, remind, summarize. Not a climb, a workout or a
 * market visit, and not what Leo promised to do. Conservative on purpose: a missing button costs
 * less than a run that cannot work. English and German.
 */
object TakeOverEligibility {
    fun canTakeOver(task: ActionItem): Boolean {
        if (task.isCompleted || task.owner == ActionItem.Owner.Other) return false
        val text = normalized(task.description)
        if (text.isEmpty() || looksLikeSomeoneElses(task.description)) return false
        if (physicalMarkers.any { contains(text, it) }) return false
        val first = text.split(' ').firstOrNull() ?: return false
        // The task starts with something Omi can do ("Draft the memo", "Schreib Anna").
        if (first in digitalVerbs) return true
        // Or names a digital thing to act on anywhere ("Follow up with Anna by email").
        return digitalPhrases.any { contains(text, it) }
    }

    /**
     * "Leo unblocks the firmware release", "Northwind sends the term sheet": a name, then a
     * verb in the third person, is another person's commitment even when the owner is unknown.
     */
    fun looksLikeSomeoneElses(description: String): Boolean {
        val words = description.split(' ').filter { it.isNotEmpty() }
        if (words.size < 2) return false
        val initial = words[0].first()
        if (!initial.isUpperCase()) return false
        val first = words[0].lowercase()
        val second = words[1].lowercase()
        if (first in digitalVerbs || first in otherImperatives) return false
        val thirdPerson = second.length > 3 && second.endsWith("s") && !second.endsWith("ss")
        val germanThirdPerson = second.length > 3 && second.endsWith("t") && second !in digitalVerbs
        return thirdPerson || (germanThirdPerson && germanSubjects(words[0]) && looksGerman(description))
    }

    /**
     * "Anna schickt das Angebot", not "Renew passport": the "-t" ending only reads as a German
     * verb in a German sentence (an article, a preposition or an umlaut).
     */
    private fun looksGerman(text: String): Boolean {
        val lowered = text.lowercase()
        if (lowered.any { it in "äöüß" }) return true
        val markers = setOf("der", "die", "das", "den", "dem", "ein", "eine", "einen", "und", "mit", "für", "von", "zu", "auf", "noch", "bis")
        return lowered.split(' ').any { it in markers }
    }

    /** A capitalized first word that is not a German imperative ("Ziehe", "Buche") is a name. */
    private fun germanSubjects(word: String): Boolean = !word.lowercase().endsWith("e")

    private fun normalized(text: String): String = text.lowercase()
        .replace("e-mail", "email")
        .split(Regex("[^\\p{L}\\p{N}']+"))
        .filter { it.isNotEmpty() }
        .joinToString(" ")

    private fun contains(text: String, phrase: String): Boolean = " $text ".contains(" $phrase ")

    /** Imperatives Omi can carry out with its tools (drafts it leaves for the user to send). */
    val digitalVerbs: Set<String> = setOf(
        // English
        "email", "mail", "message", "text", "send", "draft", "write", "reply", "respond", "answer", "ask", "invite",
        "research", "look", "find", "search", "compare", "summarize", "summarise", "book", "schedule", "reschedule",
        "order", "reserve", "remind", "plan", "follow", "share", "forward", "compile", "outline", "translate",
        // German
        "schreib", "schreibe", "schreiben", "schick", "schicke", "schicken", "sende", "senden", "antworte", "antworten",
        "frag", "frage", "fragen", "lade", "recherchiere", "recherchieren", "such", "suche", "suchen", "finde", "finden",
        "vergleiche", "vergleichen", "fasse", "buche", "buchen", "plane", "planen", "bestelle", "bestellen", "reserviere",
        "reservieren", "erinnere", "erinnern", "entwirf", "entwerfen", "vereinbare", "vereinbaren", "übersetze",
    )

    /** Digital objects or channels that make a task doable even without a leading verb. */
    val digitalPhrases: List<String> = listOf(
        "email", "mail", "message", "text", "invite", "calendar", "meeting", "appointment", "reservation", "flight", "hotel",
        "ticket", "online", "draft", "memo", "summary", "doc", "document", "slack", "whatsapp", "follow up", "look up",
        "termin", "nachricht", "einladung", "kalender", "zusammenfassung", "flug", "entwurf",
    )

    /** Things done in person or with the body: Omi cannot do these, whatever the verb. */
    val physicalMarkers: List<String> = listOf(
        "climb", "climbing", "run", "jog", "walk", "hike", "gym", "workout", "work out", "exercise", "stretch", "swim",
        "yoga", "cook", "clean", "tidy", "wash", "laundry", "groceries", "pick up", "drop off", "drive", "go to", "visit",
        "at a market", "at the market", "in person", "sleep", "eat", "drink", "water the", "rocks",
        "klettern", "laufen", "joggen", "wandern", "sport", "trainieren", "kochen", "putzen", "aufräumen", "waschen",
        "einkaufen", "abholen", "fahren", "besuchen", "schlafen", "essen", "auf dem markt",
    )

    /**
     * Imperatives that are clearly the user's own but not doable by Omi (kept out of the
     * third-person check so "Maximize ..." is not read as a name).
     */
    val otherImperatives: Set<String> = setOf(
        "maximize", "implement", "improve", "measure", "copy", "choose", "purchase", "buy", "make", "build", "fix", "test",
        "integrate", "optimize", "utilize", "develop", "provide", "introduce", "explain", "clarify", "remove", "archive",
        "check", "create", "update", "review", "figure", "prepare", "set", "add", "collect", "gather", "confirm", "cancel",
        "ziehe", "kaufe", "baue", "teste", "verbessere",
    )
}

/** `agent.canTakeOver(task)` (the extension in `TakeOverEligibility.swift`). */
fun AgentStore.canTakeOver(task: ActionItem): Boolean = TakeOverEligibility.canTakeOver(task)
