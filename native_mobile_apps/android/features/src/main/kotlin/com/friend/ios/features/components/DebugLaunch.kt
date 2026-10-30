package com.friend.ios.features.components

/**
 * Port of `OmiComponents/DebugLaunch.swift`: launch extras a feature screen reads itself, so a
 * screenshot can show a state without tapping (`--es omiSettingsTopic listening`, ...). The app's
 * `DebugLaunchOptions.read` fills [values] in debug builds only; empty (inert) otherwise.
 */
object DebugLaunch {
    @Volatile
    var values: Map<String, String> = emptyMap()

    fun string(key: String): String? = values[key]

    fun flag(key: String): Boolean = string(key)?.let { it in setOf("YES", "1", "true") } ?: false
}
