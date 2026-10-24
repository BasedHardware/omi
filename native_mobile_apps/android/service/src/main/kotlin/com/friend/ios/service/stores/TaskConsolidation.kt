package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Recommendation
import java.text.Normalizer
import java.time.Instant
import java.time.ZoneId

/**
 * Port of `TaskConsolidation.swift`: Home's tasks, condensed (docs/CHAT-FIRST.md): only what is
 * the user's to do, the same task heard in several conversations as one card, ranked, and only
 * the ones that matter now. Pure rules on the client; the daily AI tidy-up (`TaskTidyUp`)
 * proposes the rest. English and German.
 */
object TaskConsolidation {
    /** One card's tasks: the one kept and the duplicates merged into it. */
    data class Group(val task: ActionItem, val duplicates: List<ActionItem> = emptyList()) {
        val id: String get() = task.id
        val all: List<ActionItem> get() = listOf(task) + duplicates
        val ids: List<String> get() = all.map { it.id }

        /** Distinct source conversations, the kept task's first ("From 2 conversations"). */
        val conversationIDs: List<String> get() = all.mapNotNull { it.conversationID }.distinct()

        /** The earliest due date among the merged tasks that the backend is reasonably sure of. */
        val dueAt: Instant? get() = all.filter { (it.dueConfidence ?: 1.0) >= minimumDueConfidence }.mapNotNull { it.dueAt }.minOrNull()

        val priority: ActionItem.Priority?
            get() = if (all.any { it.priority == ActionItem.Priority.High }) ActionItem.Priority.High else task.priority
    }

    /** One "Needs you" task card. */
    data class Card(
        val group: Group,
        val kicker: Kicker,
        /** The backend's "What matters now" pick for this task, when there is one. */
        val recommendation: Recommendation? = null,
        /** "Later" was tapped: hidden from Needs you until then. */
        val snoozedUntil: Instant? = null,
    ) {
        sealed interface Kicker {
            data object Overdue : Kicker
            data object DueToday : Kicker
            /** Due tomorrow or the day after. */
            data class DueSoon(val date: Instant) : Kicker
            /** Someone waits on the user (blocked, a reply owed). */
            data object Waiting : Kicker
            /** Omi or the backend picked it (`What matters now`, the tidy-up's important list). */
            data object Suggestion : Kicker
        }

        val task: ActionItem get() = group.task
        val id: String get() = group.id
    }

    /** What ranks a task besides its own fields. */
    data class Signals(
        /** Tasks the backend's "What matters now" or the tidy-up marked important. */
        val picks: Set<String> = emptySet(),
        /** Tasks someone waits on (a recommendation that says so). */
        val waiting: Set<String> = emptySet(),
        /** Tasks Omi already works on (any run, a workstream): their run shows instead. */
        val handled: Set<String> = emptySet(),
        /**
         * Tasks Omi works on right now: their card stays in place and shows the run (Home task
         * card, docs/HOME_TASK_CARD.md), even once a refresh gives them a workstream.
         */
        val running: Set<String> = emptySet(),
        /** Task id -> "Later" until. */
        val snoozes: Map<String, Instant> = emptyMap(),
        /** Task id -> the words it was extracted from (`ConversationsStore.quote`), when loaded. */
        val quotes: Map<String, String> = emptyMap(),
        val now: Instant = Instant.now(),
        val zone: ZoneId = ZoneId.systemDefault(),
    )

    /** Below this the backend guessed the due date; it does not make a task urgent. */
    const val minimumDueConfidence = 0.4
    /** Token overlap from which two tasks with the same verb are one. */
    const val duplicateThreshold = 0.6

    // Cards

    /**
     * The tasks that matter now, ranked (`first`), and the ones the user put off (`second`,
     * soonest back first). [recommendations] with a task become that task's card.
     */
    fun cards(tasks: List<ActionItem>, recommendations: List<Recommendation> = emptyList(), signals: Signals): Pair<List<Card>, List<Card>> {
        // A request the user made of someone else (an assistant, a colleague) stays in All tasks.
        val own = tasks.filter { isCandidate(it) && !isRequestToSomeoneElse(it.description, signals.quotes[it.id]) }
        val groups = groups(own).filter { group -> group.all.none { it.id in signals.handled || (it.workstreamID != null && it.id !in signals.running) } }
        val byTask = LinkedHashMap<String, Recommendation>()
        for (recommendation in recommendations) {
            val id = recommendation.taskID ?: continue
            if (byTask[id] == null) byTask[id] = recommendation
        }
        val active = mutableListOf<Pair<Card, RankKey>>()
        val snoozed = mutableListOf<Card>()
        for (group in groups) {
            val recommendation = group.ids.firstNotNullOfOrNull { byTask[it] }
            val key = rankKey(group, recommendation != null, signals)
            val until = group.ids.mapNotNull { signals.snoozes[it] }.filter { it > signals.now }.maxOrNull()
            if (until != null) {
                snoozed += Card(group, key.kicker, recommendation, until)
            } else if (key.isImportant) {
                active += Card(group, key.kicker, recommendation) to key
            }
        }
        val ranked = active.sortedWith { a, b -> a.second.compareTo(b.second) }.map { it.first }
        // The backend's own picks lead (Home: Omi asks, finished runs, What matters now, then tasks).
        val picked = ranked.filter { it.recommendation != null }
        val comingBack = snoozed.sortedBy { it.snoozedUntil ?: Instant.MAX }
        return (picked + ranked.filter { it.recommendation == null }) to comingBack
    }

    // Hiding

    /** Something for the user to do: open, theirs, and a real task rather than a stray phrase. */
    fun isCandidate(task: ActionItem): Boolean {
        if (!task.isOpen || task.owner == ActionItem.Owner.Other) return false
        if (TakeOverEligibility.looksLikeSomeoneElses(task.description)) return false
        return !isFragment(task.description)
    }

    /**
     * Clearly not actionable: one word, a few letters, filler from speech ("um", "yeah so"), a
     * sentence cut off mid-way.
     */
    fun isFragment(text: String): Boolean {
        val trimmed = text.trim()
        val words = words(trimmed)
        if (words.size < 2 || trimmed.count { it.isLetter() } < 6) return true
        if (words[0] in fillers) return true
        return trimmed.endsWith("...") || trimmed.endsWith("…")
    }

    /**
     * Said to someone else in the second person ("Kannst du dir mal das Transkript ziehen ...",
     * "Could you send me the deck"): the other person's job, often an assistant on a laptop.
     * Unless the user said it about himself ("can you remind me", "ich muss ...").
     */
    fun isRequestToSomeoneElse(text: String, quote: String?): Boolean {
        val spoken = " " + words(listOf(quote ?: "", text).joinToString(" ")).joinToString(" ") + " "
        if (requestPhrases.none { spoken.contains(" $it ") }) return false
        return selfPhrases.none { spoken.contains(" $it ") }
    }

    /**
     * The due date that makes a task urgent: none when the backend guessed it (low confidence) or
     * filled in the end of the day it was heard ("23:59" on its creation day) with no time said.
     */
    fun deadline(task: ActionItem, quote: String?, zone: ZoneId): Instant? {
        val due = task.dueAt ?: return null
        if ((task.dueConfidence ?: 1.0) < minimumDueConfidence) return null
        val local = due.atZone(zone)
        val endOfDay = local.hour == 23 && local.minute == 59
        val created = task.createdAt
        if (!endOfDay || created == null || created.atZone(zone).toLocalDate() != local.toLocalDate()) return due
        val spoken = " " + words(listOf(quote ?: "", task.description).joinToString(" ")).joinToString(" ") + " "
        return if (timePhrases.any { spoken.contains(" $it ") }) due else null
    }

    // Duplicates

    /**
     * Tasks merged where they say the same thing: same verb and at least [duplicateThreshold]
     * token overlap (Jaccard). The kept task is the most useful one: due date, high priority,
     * then the first heard. Order follows the input.
     */
    fun groups(tasks: List<ActionItem>): List<Group> {
        val buckets = mutableListOf<MutableList<ActionItem>>()
        val signatures = mutableListOf<Signature>()
        for (task in tasks) {
            val signature = Signature(task.description)
            val index = signatures.indexOfFirst { it.matches(signature) }
            if (index >= 0) {
                buckets[index] += task
            } else {
                buckets += mutableListOf(task)
                signatures += signature
            }
        }
        return buckets.map { members ->
            val kept = members.sortedWith(keepsBefore).first()
            Group(kept, members.filter { it.id != kept.id })
        }
    }

    fun isDuplicate(lhs: String, rhs: String): Boolean = Signature(lhs).matches(Signature(rhs))

    /** Token Jaccard similarity of two task texts (stop words dropped, light stemming). */
    fun similarity(lhs: String, rhs: String): Double = Signature(lhs).similarity(Signature(rhs))

    private val keepsBefore = Comparator<ActionItem> { lhs, rhs ->
        if ((lhs.dueAt == null) != (rhs.dueAt == null)) return@Comparator if (lhs.dueAt != null) -1 else 1
        val lhsHigh = lhs.priority == ActionItem.Priority.High
        val rhsHigh = rhs.priority == ActionItem.Priority.High
        if (lhsHigh != rhsHigh) return@Comparator if (lhsHigh) -1 else 1
        val left = lhs.createdAt ?: Instant.MAX
        val right = rhs.createdAt ?: Instant.MAX
        if (left != right) left.compareTo(right) else lhs.id.compareTo(rhs.id)
    }

    internal class Signature(text: String) {
        val verb: String
        val tokens: Set<String>

        init {
            val all = words(text)
            // "Leo unblocks the firmware release": the verb is the second word.
            val verbIndex = if (TakeOverEligibility.looksLikeSomeoneElses(text) && all.size > 1) 1 else 0
            verb = all.getOrNull(verbIndex)?.let(::stem) ?: ""
            tokens = all.filter { it !in stopWords }.map(::stem).toSet()
        }

        fun similarity(other: Signature): Double {
            val union = tokens union other.tokens
            if (union.isEmpty()) return 0.0
            return (tokens intersect other.tokens).size.toDouble() / union.size
        }

        fun matches(other: Signature): Boolean = verb.isNotEmpty() && verb == other.verb && similarity(other) >= duplicateThreshold
    }

    // Ranking

    /**
     * Lexicographic: overdue, someone waits, picked, due within two days, high priority, Omi
     * can do it, then the newest.
     */
    internal data class RankKey(
        val overdue: Boolean,
        val waiting: Boolean,
        val picked: Boolean,
        val dueSoon: Boolean,
        val high: Boolean,
        val omiCan: Boolean,
        val created: Instant,
        val kicker: Card.Kicker,
        val dueToday: Boolean,
    ) : Comparable<RankKey> {
        val isImportant: Boolean get() = overdue || dueToday || dueSoon || waiting || picked || high

        private val flags: List<Int> get() = listOf(overdue, waiting, picked, dueToday || dueSoon, high, omiCan).map { if (it) 0 else 1 }

        override fun compareTo(other: RankKey): Int {
            val a = flags
            val b = other.flags
            for (i in a.indices) if (a[i] != b[i]) return a[i].compareTo(b[i])
            return other.created.compareTo(created)
        }
    }

    internal fun rankKey(group: Group, recommended: Boolean, signals: Signals): RankKey {
        val zone = signals.zone
        val todayDate = signals.now.atZone(zone).toLocalDate()
        val today = todayDate.atStartOfDay(zone).toInstant()
        val due = group.all.mapNotNull { deadline(it, signals.quotes[it.id], zone) }.minOrNull()
        val overdue = due?.let { it < today } ?: false
        val dueToday = due?.let { it.atZone(zone).toLocalDate() == todayDate } ?: false
        val soonLimit = todayDate.plusDays(3).atStartOfDay(zone).toInstant()
        val dueSoon = !overdue && !dueToday && (due?.let { it < soonLimit } ?: false)
        val waiting = group.ids.any { it in signals.waiting } || group.all.any { someoneWaits(it.description) }
        val picked = recommended || group.ids.any { it in signals.picks }
        val kicker: Card.Kicker = when {
            overdue -> Card.Kicker.Overdue
            dueToday -> Card.Kicker.DueToday
            waiting -> Card.Kicker.Waiting
            dueSoon && due != null -> Card.Kicker.DueSoon(due)
            else -> Card.Kicker.Suggestion
        }
        return RankKey(
            overdue = overdue, waiting = waiting, picked = picked, dueSoon = dueSoon, high = group.priority == ActionItem.Priority.High,
            omiCan = TakeOverEligibility.canTakeOver(group.task),
            created = group.all.mapNotNull { it.createdAt }.maxOrNull() ?: Instant.MIN, kicker = kicker, dueToday = dueToday,
        )
    }

    /** The task itself says someone is waiting ("Reply to Anna", "Leo is blocked on ..."). */
    internal fun someoneWaits(text: String): Boolean {
        val spoken = " " + words(text).joinToString(" ") + " "
        return waitingPhrases.any { spoken.contains(" $it ") }
    }

    // Words

    private val marks = Regex("\\p{Mn}+")
    private val separators = Regex("[^\\p{L}\\p{N}]+")

    internal fun words(text: String): List<String> {
        val folded = marks.replace(Normalizer.normalize(text, Normalizer.Form.NFD), "").lowercase()
        return folded.replace("e-mail", "email").split(separators).filter { it.isNotEmpty() }
    }

    /** Plural and conjugation endings, so "unblocks" meets "unblock" and "schicke" meets "schick". */
    internal fun stem(word: String): String {
        var result = word
        if (result.length > 5 && result.endsWith("en")) {
            result = result.dropLast(2)
        } else if (result.length > 3 && result.endsWith("s") && !result.endsWith("ss")) {
            result = result.dropLast(1)
        }
        if (result.length > 4 && result.endsWith("e")) result = result.dropLast(1)
        return result
    }

    internal val stopWords: Set<String> = setOf(
        "the", "a", "an", "to", "for", "of", "and", "or", "with", "on", "in", "at", "by", "from", "my", "our", "your",
        "his", "her", "their", "this", "that", "it", "is", "be", "about", "up", "out", "some", "all",
        "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "und", "oder", "mit", "fur",
        "zu", "zum", "zur", "an", "am", "auf", "im", "von", "vom", "bei", "mein", "meine", "meinen", "dein", "deine",
    )

    /** Speech filler a real task never starts with. */
    internal val fillers: Set<String> = setOf(
        "um", "uh", "uhm", "hmm", "yeah", "yep", "okay", "ok", "and", "but", "because", "so",
        "ahm", "ah", "ja", "und", "aber", "weil", "oder", "naja",
    )

    /** A request to the listener (folded: "könntest" is "konntest"). */
    internal val requestPhrases: List<String> = listOf(
        "can you", "could you", "would you", "will you", "can u", "please",
        "kannst du", "kannst dir", "kannst mir", "konntest du", "wurdest du",
        "konnen sie", "konnten sie", "wurden sie", "bitte",
    )

    /** The user speaking about himself: still his own task. */
    internal val selfPhrases: List<String> = listOf(
        "remind me", "i need to", "i have to", "i should", "i must", "i will", "i ll", "i want to", "i m going to",
        "erinnere mich", "erinner mich", "ich muss", "ich sollte", "ich will", "ich werde", "ich mochte", "ich mach",
    )

    /** A time of day said out loud, which makes "by the end of today" a real deadline. */
    internal val timePhrases: List<String> = listOf(
        "today", "tonight", "this evening", "end of day", "eod", "midnight", "right now", "asap",
        "heute", "heute abend", "heute nacht", "noch heute", "bis heute", "mitternacht", "tagesende", "sofort", "jetzt",
    )

    internal val waitingPhrases: List<String> = listOf(
        "waiting", "waits", "waiting on", "blocked", "blocking", "reply to", "respond to", "get back to", "owe",
        "wartet", "warten", "blockiert", "antworte", "zuruckmelden", "melde dich",
    )
}
