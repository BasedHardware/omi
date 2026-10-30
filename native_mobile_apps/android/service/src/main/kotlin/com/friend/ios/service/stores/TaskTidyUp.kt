package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Port of the data half of `TaskTidyUp.swift`: the daily AI tidy-up of open tasks
 * (docs/CHAT-FIRST.md). Nothing is applied on its own; Home shows one suggestion card and the
 * user reviews each change. `prompt` / `parse` and the stored form follow below (and-onboarding).
 */
object TaskTidyUp {
    data class Merge(val keep: String, val drop: List<String>, val why: String)

    data class Change(val id: String, val why: String)

    /** Task ids are the real backend ids (the prompt's short keys are mapped back by `parse`). */
    data class Proposal(
        val merges: List<Merge> = emptyList(),
        val done: List<Change> = emptyList(),
        val notTask: List<Change> = emptyList(),
        val important: List<String> = emptyList(),
    ) {
        /** Nothing to change (`important` alone is only a ranking hint, never a card). */
        val isEmpty: Boolean get() = merges.isEmpty() && done.isEmpty() && notTask.isEmpty()

        /** Tasks that would be merged away ("merge 6"). */
        val mergedCount: Int get() = merges.sumOf { it.drop.size }

        /** Only what still applies: every task named is still open. */
        fun restricted(open: Set<String>): Proposal = Proposal(
            merges = merges.mapNotNull { merge ->
                val drop = merge.drop.filter { it in open }
                if (merge.keep in open && drop.isNotEmpty()) Merge(merge.keep, drop, merge.why) else null
            },
            done = done.filter { it.id in open },
            notTask = notTask.filter { it.id in open },
            important = important.filter { it in open },
        )

        /** Each change the review sheet lists, in order: merges, done, not a task. */
        val edits: List<Edit>
            get() = merges.flatMap { merge -> merge.drop.map { Edit(it, Edit.Kind.Merge(merge.keep), merge.why) } } +
                done.map { Edit(it.id, Edit.Kind.Done, it.why) } +
                notTask.map { Edit(it.id, Edit.Kind.NotTask, it.why) }
    }

    /** One proposed change: a PATCH once the user applies it. */
    data class Edit(val taskID: String, val kind: Kind, val why: String) {
        sealed interface Kind {
            /** `superseded`, `superseded_by` the kept task. */
            data class Merge(val into: String) : Kind
            /** `completed`. */
            data object Done : Kind
            /** `cancelled` ("Not a task"). */
            data object NotTask : Kind
        }

        val id: String get() = taskID

        val status: ActionItem.Status
            get() = when (kind) {
                is Kind.Merge -> ActionItem.Status.Superseded
                Kind.Done -> ActionItem.Status.Completed
                Kind.NotTask -> ActionItem.Status.Cancelled
            }
    }

    /** At most this many tasks go into the prompt (newest first), so it stays short. */
    const val maxTasks = 60

    // The agent's question and answer (and-onboarding).

    /** `t1`, `t2`, ... for the prompt, mapped to the real ids. */
    fun keys(tasks: List<ActionItem>): Map<String, String> = tasks.mapIndexed { offset, task -> "t${offset + 1}" to task.id }.toMap()

    /** The question for the agent: the tasks as `id | task | due | source`, then the exact JSON shape. */
    fun prompt(
        tasks: List<ActionItem>,
        source: (ActionItem) -> String?,
        quote: (ActionItem) -> String? = { null },
        now: Instant = Instant.now(),
        zone: ZoneId = ZoneId.systemDefault(),
    ): String {
        val day = DateTimeFormatter.ofPattern("yyyy-MM-dd", Locale.US).withZone(zone)
        val lines = tasks.mapIndexed { offset, task ->
            val text = task.description.replace("\n", " ").replace("|", "/")
            val due = task.dueAt?.let { "due " + day.format(it) } ?: "-"
            val from = source(task)?.let { "\"${it.take(60)}\"" } ?: "-"
            val heard = task.createdAt?.let { day.format(it) } ?: "-"
            val said = quote(task)?.let { " | said: \"${it.replace("\n", " ").take(100)}\"" } ?: ""
            "t${offset + 1} | ${text.take(140)} | $due | $from $heard$said"
        }
        return listOf(
            "Tidy up my open tasks. Do not call tools and do not change anything; answer with JSON only.",
            "Today is ${day.format(now)}.",
            "Tasks (id | task | due | source conversation, date | what was said):",
            lines.joinToString("\n"),
            "",
            "Answer with exactly one JSON object and nothing else:",
            "{\"merge\":[{\"keep\":\"t1\",\"drop\":[\"t2\"],\"why\":\"...\"}],\"done\":[{\"id\":\"t3\",\"why\":\"...\"}]," +
                "\"notTask\":[{\"id\":\"t4\",\"why\":\"...\"}],\"important\":[\"t5\"]}",
            "Rules: merge only tasks that are the same action on the same thing (never just a similar topic), keep the " +
                "clearest. done only when it clearly already " +
                "happened or its moment has passed. notTask: a fragment, not something I have to do, someone else's job, or a " +
                "request I made of someone else or of an assistant (\"can you …\", \"kannst du …\") unless it is about me. " +
                "important: at most 5 that matter most now. \"why\": at most 8 words, in the task's language. " +
                "Leave a list empty when unsure.",
        ).joinToString("\n")
    }

    /**
     * The agent's answer as a proposal, or null when it holds no JSON object. Tolerates code
     * fences, text around the object, numbers for keys and unknown or repeated ids (dropped): each
     * task appears in at most one change, and a kept task is never also dropped.
     */
    fun parse(text: String, keys: Map<String, String>): Proposal? {
        val obj = jsonObject(text) ?: return null
        fun id(value: JsonElement?): String? {
            val primitive = value as? JsonPrimitive ?: return null
            if (primitive.isString) {
                val key = primitive.content.trim().lowercase()
                return keys[key] ?: keys["t$key"]
            }
            return primitive.doubleOrNull?.let { keys["t${it.toInt()}"] }
        }
        fun why(entry: JsonObject): String =
            ((entry["why"] as? JsonPrimitive)?.takeIf { it.isString }?.content ?: "").trim().take(120)
        val used = HashSet<String>()
        val merges = mutableListOf<Merge>()
        for (entry in (obj["merge"] as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }) {
            val keep = id(entry["keep"]) ?: continue
            if (keep in used) continue
            val rawDrop = entry["drop"]
            val drops = ((rawDrop as? JsonArray)?.toList() ?: listOfNotNull(rawDrop)).mapNotNull(::id)
            val unique = mutableListOf<String>()
            for (drop in drops) if (drop != keep && drop !in used && drop !in unique) unique.add(drop)
            if (unique.isEmpty()) continue
            used.add(keep)
            used.addAll(unique)
            merges.add(Merge(keep, unique, why(entry)))
        }
        fun changes(vararg names: String): List<Change> {
            val entries = names.firstNotNullOfOrNull { obj[it] as? JsonArray }.orEmpty()
            return entries.mapNotNull { raw ->
                val entry = raw as? JsonObject ?: JsonObject(mapOf("id" to raw))
                val task = id(entry["id"]) ?: return@mapNotNull null
                if (!used.add(task)) null else Change(task, why(entry))
            }
        }
        val done = changes("done")
        val notTask = changes("notTask", "not_task", "nottask")
        val seen = HashSet<String>()
        val important = (obj["important"] as? JsonArray).orEmpty().mapNotNull(::id).filter { seen.add(it) }
        return Proposal(merges, done, notTask, important.take(5))
    }

    /** The first `{` to the last `}` that parses, with Markdown code fences gone. */
    internal fun jsonObject(text: String): JsonObject? {
        val cleaned = text.replace("```json", "").replace("```", "")
        val start = cleaned.indexOf('{')
        if (start < 0) return null
        var end = cleaned.length
        while (true) {
            val close = cleaned.lastIndexOf('}', end - 1)
            if (close < start) return null
            val candidate = cleaned.substring(start, close + 1)
            (runCatching { Json.parseToJsonElement(candidate) }.getOrNull() as? JsonObject)?.let { return it }
            end = close
        }
    }

    /** The stored suggestion (`Codable` on iOS), with the Swift struct's keys. */
    fun encode(proposal: Proposal): String = buildJsonObject {
        putJsonArray("merges") {
            proposal.merges.forEach { merge ->
                add(
                    buildJsonObject {
                        put("keep", merge.keep)
                        putJsonArray("drop") { merge.drop.forEach { add(it) } }
                        put("why", merge.why)
                    },
                )
            }
        }
        putJsonArray("done") { proposal.done.forEach { add(buildJsonObject { put("id", it.id); put("why", it.why) }) } }
        putJsonArray("notTask") { proposal.notTask.forEach { add(buildJsonObject { put("id", it.id); put("why", it.why) }) } }
        putJsonArray("important") { proposal.important.forEach { add(it) } }
    }.toString()

    fun decode(text: String): Proposal? {
        val obj = runCatching { Json.parseToJsonElement(text) }.getOrNull() as? JsonObject ?: return null
        fun string(entry: JsonObject, key: String) = (entry[key] as? JsonPrimitive)?.content.orEmpty()
        fun strings(element: JsonElement?) = (element as? JsonArray).orEmpty().mapNotNull { (it as? JsonPrimitive)?.content }
        fun changes(name: String) =
            (obj[name] as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }.map { Change(string(it, "id"), string(it, "why")) }
        return Proposal(
            merges = (obj["merges"] as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }
                .map { Merge(string(it, "keep"), strings(it["drop"]), string(it, "why")) },
            done = changes("done"),
            notTask = changes("notTask"),
            important = strings(obj["important"]),
        )
    }
}
