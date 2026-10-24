package com.friend.ios.core

import java.net.URI

/** Port of `AppConfiguration.swift`: build-time configuration (BuildConfig on Android). */
data class AppConfiguration(
    val profile: Profile,
    val apiBaseURL: URI,
    /** `host:port` of the Firebase Auth emulator; null outside local development. */
    val authEmulator: HostPort?,
    val appVersion: String,
    val appBuild: String,
) {
    /** Mirrors the Flutter app's `OMI_APP_PROFILE`. */
    enum class Profile(val rawValue: String) {
        LocalDev("local_dev"), Beta("mobile_beta"), Production("production");

        companion object {
            fun from(raw: String?): Profile = entries.firstOrNull { it.rawValue == raw } ?: Production
        }
    }

    data class HostPort(val host: String, val port: Int)

    val isLocalDev: Boolean get() = profile == Profile.LocalDev

    companion object {
        fun parseHostPort(value: String?): HostPort? {
            val parts = value?.split(":") ?: return null
            if (parts.size != 2 || parts[0].isEmpty()) return null
            return parts[1].toIntOrNull()?.let { HostPort(parts[0], it) }
        }
    }
}
