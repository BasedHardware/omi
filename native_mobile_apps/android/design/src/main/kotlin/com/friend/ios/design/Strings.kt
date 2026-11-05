package com.friend.ios.design

import android.annotation.SuppressLint
import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext

/**
 * Port of `Strings.swift`: localized string by ARB key, keys shared with the Flutter app and
 * omi-native (`Tools/l10n/xcstrings2android.py` turns `a.b` into the resource `a__b`).
 * A missing key renders as itself, like `localizedString(forKey:value:)` with `value: key`.
 */
@Composable
@ReadOnlyComposable
fun L(key: String, vararg arguments: Any): String {
    LocalConfiguration.current // re-read on locale changes
    return Strings.get(LocalContext.current, key, *arguments)
}

/** The same lookup outside composition (stores, notifications). */
object Strings {
    private val ids = HashMap<String, Int>()

    @SuppressLint("DiscouragedApi")
    fun get(context: Context, key: String, vararg arguments: Any): String {
        val id = synchronized(ids) {
            ids.getOrPut(key) { context.resources.getIdentifier(key.replace(".", "__"), "string", context.packageName) }
        }
        if (id == 0) return key
        return if (arguments.isEmpty()) context.getString(id) else context.getString(id, *arguments)
    }
}
