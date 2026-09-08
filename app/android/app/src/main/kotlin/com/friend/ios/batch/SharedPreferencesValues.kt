package com.friend.ios.batch

import android.content.SharedPreferences

/** Typed reads avoid SharedPreferences.getAll(), which copies the entire preferences map.
 * Retain legacy scalar representations used by Flutter's preferences bridge. */
internal class SharedPreferencesValues(private val prefs: SharedPreferences) : NativeBlePreferences {
    override fun string(key: String, defaultValue: String): String {
        val name = "flutter.$key"
        return try { prefs.getString(name, defaultValue) ?: defaultValue } catch (_: ClassCastException) {
            scalar(name)?.toString() ?: defaultValue
        }
    }

    override fun boolean(key: String, defaultValue: Boolean): Boolean {
        val name = "flutter.$key"
        return try { prefs.getBoolean(name, defaultValue) } catch (_: ClassCastException) {
            string(key).toBooleanStrictOrNull() ?: defaultValue
        }
    }

    override fun integer(key: String, defaultValue: Int): Int {
        val name = "flutter.$key"
        return try { prefs.getLong(name, defaultValue.toLong()).toInt() } catch (_: ClassCastException) {
            try { prefs.getInt(name, defaultValue) } catch (_: ClassCastException) {
                string(key).toIntOrNull() ?: defaultValue
            }
        }
    }

    private fun scalar(name: String): Any? {
        try { return prefs.getBoolean(name, false) } catch (_: ClassCastException) { }
        try { return prefs.getLong(name, 0) } catch (_: ClassCastException) { }
        try { return prefs.getInt(name, 0) } catch (_: ClassCastException) { }
        return try { prefs.getFloat(name, 0f) } catch (_: ClassCastException) { null }
    }
}
