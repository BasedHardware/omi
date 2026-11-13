package com.friend.ios.system.widgets

import android.content.Context

/**
 * The widgets' own strings, generated from omi-native `Extensions/OmiWidgets/Localizable.xcstrings`
 * (the iOS widget extension has its own catalog, outside the app's `Localizable.xcstrings`).
 * Keys are the English text; `%lld` became `%d`.
 */
internal object WidgetStrings {
    fun get(context: Context, key: String, vararg arguments: Any): String {
        val locale = context.resources.configuration.locales[0]
        val values = table[key] ?: return key
        val text = values[locale.toLanguageTag()] ?: values[locale.language] ?: values["en"] ?: key
        return if (arguments.isEmpty()) text else String.format(locale, text, *arguments)
    }

    private val table: Map<String, Map<String, String>> = mapOf(
        "%d open" to mapOf("de" to "%d offen", "en" to "%d open"),
        "%d tasks" to mapOf("en" to "%d tasks"),
        "All caught up" to mapOf("de" to "Alles erledigt", "en" to "All caught up"),
        "Battery" to mapOf("de" to "Akku", "en" to "Battery"),
        "Latest" to mapOf("de" to "Neuestes", "en" to "Latest"),
        "Low battery" to mapOf("de" to "Akku fast leer", "en" to "Low battery"),
        "No Omi paired" to mapOf("de" to "Kein Omi gekoppelt", "en" to "No Omi paired"),
        "No conversations yet" to mapOf("de" to "Noch keine Gespräche", "en" to "No conversations yet"),
        "Not connected" to mapOf("de" to "Nicht verbunden", "en" to "Not connected"),
        "Open Omi to continue" to mapOf("de" to "Öffne Omi, um weiterzumachen", "en" to "Open Omi to continue"),
        "Overdue" to mapOf("de" to "Überfällig", "en" to "Overdue"),
        "Up next" to mapOf("de" to "Als Nächstes", "en" to "Up next"),
        "Tomorrow" to mapOf("de" to "Morgen", "en" to "Tomorrow"),
        "Untitled conversation" to mapOf("de" to "Gespräch ohne Titel", "en" to "Untitled conversation"),
        "Yesterday" to mapOf("de" to "Gestern", "en" to "Yesterday"),
        "Your next tasks from Omi." to mapOf("de" to "Deine nächsten Aufgaben aus Omi.", "en" to "Your next tasks from Omi."),
        "Your Omi's charge at a glance." to mapOf("de" to "Der Akku deines Omi auf einen Blick.", "en" to "Your Omi's charge at a glance."),
        "Your latest conversation in Omi." to mapOf("de" to "Dein neuestes Gespräch in Omi.", "en" to "Your latest conversation in Omi."),
        // The recording and run notifications (`CaptureViews.swift`, `AgentViews.swift`).
        "Open Omi to reconnect" to mapOf("de" to "Öffne Omi, um die Verbindung wiederherzustellen", "en" to "Open Omi to reconnect"),
        "Finished" to mapOf("de" to "Fertig", "en" to "Finished"),
        "Paused" to mapOf("de" to "Pausiert", "en" to "Paused"),
        "Recording" to mapOf("de" to "Aufnahme", "en" to "Recording"),
        "Listening" to mapOf("de" to "Hört zu", "en" to "Listening"),
        "Omi pendant" to mapOf("de" to "Omi-Anhänger", "en" to "Omi pendant"),
        "Transcribing live" to mapOf("de" to "Live-Transkription", "en" to "Transcribing live"),
        "Transcribe Later" to mapOf("de" to "Später transkribieren", "en" to "Transcribe Later"),
        "Start" to mapOf("de" to "Starten", "en" to "Start"),
        "Stop" to mapOf("de" to "Stopp", "en" to "Stop"),
        "End" to mapOf("de" to "Beenden", "en" to "End"),
        "Omi is working" to mapOf("de" to "Omi arbeitet daran", "en" to "Omi is working"),
        "Omi finished" to mapOf("de" to "Omi ist fertig", "en" to "Omi finished"),
        "Omi couldn't finish" to mapOf("de" to "Omi kam nicht weiter", "en" to "Omi couldn't finish"),
        "Working" to mapOf("de" to "Arbeitet", "en" to "Working"),
        "Done" to mapOf("de" to "Fertig", "en" to "Done"),
        "Stuck" to mapOf("de" to "Hängt fest", "en" to "Stuck"),
        "Tap to see what Omi did" to mapOf("de" to "Tippe, um zu sehen, was Omi erledigt hat", "en" to "Tap to see what Omi did"),
        "Tap to open the task" to mapOf("de" to "Tippe, um die Aufgabe zu öffnen", "en" to "Tap to open the task"),
        "Getting started…" to mapOf("de" to "Legt los …", "en" to "Getting started…"),
        "+%d more" to mapOf("de" to "+%d weitere", "en" to "+%d more"),
    )
}
