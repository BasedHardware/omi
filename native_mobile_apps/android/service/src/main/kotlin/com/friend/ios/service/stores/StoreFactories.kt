package com.friend.ios.service.stores

/**
 * Port of `StoreFactories.swift`: screens create their own short-lived stores from the long-lived
 * ones, so the app shell does not have to build and inject each of them.
 */
fun SettingsStore.makeUsageStore(): UsageStore = UsageStore(api)

fun SettingsStore.makeProfileStore(): ProfileStore = ProfileStore(api, preferences, scope, cacheDirectory)

fun SettingsStore.makeAnnouncementsStore(): AnnouncementsStore = AnnouncementsStore(api, preferences)

/**
 * Profile > Name: first word given, the rest family, as at sign-up; the identity provider's
 * display name follows (best effort, like Flutter's `updateGivenName`).
 */
suspend fun SessionStore.changeName(name: String) {
    val trimmed = name.trim()
    if (trimmed.isEmpty()) return
    val parts = trimmed.split(" ", limit = 2)
    preferences.set(com.friend.ios.persistence.Preferences.Key.GivenName, parts[0])
    preferences.set(com.friend.ios.persistence.Preferences.Key.FamilyName, parts.getOrNull(1)?.trim()?.takeIf { it.isNotEmpty() })
    runCatching { auth.updateDisplayName(trimmed) }
}
