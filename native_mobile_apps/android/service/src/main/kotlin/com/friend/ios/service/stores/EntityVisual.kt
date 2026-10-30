package com.friend.ios.service.stores

import com.friend.ios.core.models.ActionItem
import com.friend.ios.core.models.Conversation

/**
 * What a task or conversation shows as its picture. Only hard signals name a brand (the Iris
 * rule: a wrong logo is worse than a neutral one): a known service named in the text, or a
 * company address among the people. Otherwise the person the task is about, then the
 * conversation's emoji, then a category glyph.
 */
sealed interface EntityVisual {
    /** A brand: [bundled] is a logo the app ships (`logo-<key>`), else load it by [domain]. */
    data class Brand(val domain: String, val bundled: String? = null) : EntityVisual
    data class Person(val name: String, val email: String?) : EntityVisual
    data class Emoji(val emoji: String, val category: String?) : EntityVisual
    data class Symbol(val systemName: String) : EntityVisual

    companion object {
        fun forTask(task: ActionItem, source: Conversation?): EntityVisual =
            brandNamed(task.description) ?: companyAmong(source)
                ?: personIn(task.description, source)
                ?: source?.emoji?.let { Emoji(it, source.category) }
                ?: Symbol(categorySymbol(source?.category))

        fun forConversation(conversation: Conversation): EntityVisual =
            brandNamed(conversation.title) ?: companyAmong(conversation)
                ?: conversation.emoji?.let { Emoji(it, conversation.category) }
                ?: Symbol(categorySymbol(conversation.category))

        /** A service named as a word in [text] ("Email the deck via Gmail", "Notion page"). */
        fun brandNamed(text: String): Brand? {
            val words = text.lowercase().split(Regex("[^a-z0-9.]+")).toSet()
            return SERVICES.entries.firstOrNull { (name, _) ->
                if (" " in name) text.lowercase().contains(name) else name in words
            }?.value
        }

        /** The first company address (not a freemail or placeholder domain) among the people. */
        fun companyAmong(conversation: Conversation?): Brand? =
            conversation?.people.orEmpty().firstNotNullOfOrNull { person ->
                person.email?.substringAfter("@", "")?.lowercase()?.let(::registrable)?.takeIf(::isCompany)
            }?.let { Brand(it) }

        /** Someone from the conversation whose first name the task mentions ("Send Anna the deck"). */
        fun personIn(text: String, conversation: Conversation?): Person? {
            val words = text.split(Regex("\\W+")).filter { it.isNotEmpty() }.map { it.lowercase() }.toSet()
            return conversation?.people.orEmpty().firstNotNullOfOrNull { person ->
                val name = person.name ?: person.email?.substringBefore("@")?.replaceFirstChar { it.uppercase() }
                val first = name?.substringBefore(" ")?.lowercase()
                if (first != null && first.length > 1 && first in words) Person(name, person.email) else null
            }
        }

        fun categorySymbol(category: String?): String = when (category) {
            "health" -> "heart"
            "finance", "economics" -> "creditcard"
            "travel" -> "airplane"
            "work", "business" -> "briefcase"
            "education" -> "graduationcap"
            "family", "personal" -> "person"
            "social" -> "person.2"
            "technology" -> "laptopcomputer"
            else -> "checklist"
        }

        private fun registrable(host: String): String = host.removePrefix("www.").split(".").takeLast(2).joinToString(".")

        private fun isCompany(domain: String): Boolean =
            domain.contains(".") && domain !in FREEMAIL && domain.substringAfterLast(".") !in setOf("test", "local", "invalid", "example")

        private val FREEMAIL = setOf(
            "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "yahoo.com", "icloud.com",
            "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com", "gmx.de", "gmx.net", "web.de", "t-online.de",
            "mail.com", "yandex.com", "example.com", "example.org", "example.net",
        )

        /** Services worth a logo when a task names them; bundled marks where the app ships one. */
        private val SERVICES: Map<String, Brand> = linkedMapOf(
            "gmail" to Brand("gmail.com", "gmail"),
            "google calendar" to Brand("calendar.google.com", "google_calendar"),
            "todoist" to Brand("todoist.com", "todoist"),
            "asana" to Brand("asana.com", "asana"),
            "clickup" to Brand("clickup.com", "clickup"),
            "google tasks" to Brand("tasks.google.com", "google_tasks"),
            "slack" to Brand("slack.com"),
            "notion" to Brand("notion.so"),
            "linear" to Brand("linear.app"),
            "github" to Brand("github.com"),
            "figma" to Brand("figma.com"),
            "zoom" to Brand("zoom.us"),
            "whatsapp" to Brand("whatsapp.com"),
            "linkedin" to Brand("linkedin.com"),
            "stripe" to Brand("stripe.com"),
            "uber" to Brand("uber.com"),
            "airbnb" to Brand("airbnb.com"),
            "amazon" to Brand("amazon.com"),
            "spotify" to Brand("spotify.com"),
            "dropbox" to Brand("dropbox.com"),
            "jira" to Brand("atlassian.com"),
            "hubspot" to Brand("hubspot.com"),
            "salesforce" to Brand("salesforce.com"),
        )
    }
}
