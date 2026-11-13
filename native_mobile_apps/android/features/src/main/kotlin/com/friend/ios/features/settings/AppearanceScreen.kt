package com.friend.ios.features.settings

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiColorScheme
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.service.LocalSettingsStore
import java.util.Locale

/**
 * Port of `AppearanceScreen.swift`. App > Appearance: System, Light or Dark as three small
 * previews, and the app's language (Android's per-app language, Settings > Apps > Omi > Language).
 */
@Composable
fun AppearanceScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val context = LocalContext.current
    val haptics = rememberHaptics()
    val language = appLanguage()
    val languageTitle = L("nativeAppLanguage")
    SettingsListPage(L("appearance"), onBack) {
        section(header = L("nativeSettingsTheme")) {
            row {
                Row(Modifier.fillMaxWidth().padding(vertical = DS.Spacing.sm), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                    AppearanceModes.forEach { mode ->
                        ModeChoice(mode, settings.appearanceMode == mode, Modifier.weight(1f)) {
                            haptics.selection()
                            settings.appearanceMode = mode
                        }
                    }
                }
            }
        }
        section(footer = L("nativeAppLanguageHint")) {
            row(onClick = { openLanguageSettings(context) }) {
                SettingsRowLabel(languageTitle, "globe", Modifier.weight(1f), value = language)
                Spacer(Modifier.width(DS.Spacing.sm))
                SettingsExternalArrow()
            }
        }
    }
}

/** `AppearanceScreen.modes`. */
val AppearanceModes = listOf("system", "light", "dark")

/** `AppearanceScreen.title(_:)`: the Appearance row's value on the Settings root. */
@Composable
fun AppearanceScreenTitle(mode: String): String = when (mode) {
    "light" -> L("nativeAppearanceLight")
    "system" -> L("nativeAppearanceSystem")
    else -> L("nativeAppearanceDark")
}

/** The language the app shows, in that language's own words ("Deutsch"). */
@Composable
private fun appLanguage(): String {
    val locale = LocalConfiguration.current.locales[0] ?: Locale.getDefault()
    return locale.getDisplayLanguage(locale).replaceFirstChar { it.titlecase(locale) }
}

/** Android 13+ has a per-app language screen; earlier, the app's own settings page. */
private fun openLanguageSettings(context: Context) {
    val uri = Uri.fromParts("package", context.packageName, null)
    val intent = if (Build.VERSION.SDK_INT >= 33) Intent(Settings.ACTION_APP_LOCALE_SETTINGS, uri) else Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, uri)
    runCatching { context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
}

/** One appearance option: a tiny screen in that look, its name and a check. */
@Composable
private fun ModeChoice(mode: String, isSelected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    Column(modifier.plainButton(onClick = onClick), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        val shape = ContinuousRoundedShape(DS.Radius.sm)
        Box(
            Modifier
                .fillMaxWidth()
                .height(96.dp)
                .clip(shape),
        ) {
            when (mode) {
                "light" -> MiniScreen(dark = false)
                "dark" -> MiniScreen(dark = true)
                // Light on the left half, dark on the right: "follows the phone".
                else -> {
                    MiniScreen(dark = false)
                    Box(Modifier.fillMaxSize().drawWithContent { clipRect(left = size.width / 2) { this@drawWithContent.drawContent() } }) { MiniScreen(dark = true) }
                }
            }
            // The border on top of the preview, as `.overlay { strokeBorder }`.
            Box(Modifier.fillMaxSize().border(if (isSelected) 2.dp else 1.dp, if (isSelected) DS.Palette.ink else DS.Palette.hairline, shape))
        }
        Text(AppearanceScreenTitle(mode), style = DS.Typography.callout, color = DS.Palette.ink)
        SFImage(if (isSelected) "checkmark.circle.fill" else "circle", size = 20.sp, tint = if (isSelected) DS.Palette.ink else DS.Palette.inkTertiary)
    }
}

/** A sketch of an Omi screen in one color scheme: page, a title bar and two cards. */
@Composable
private fun MiniScreen(dark: Boolean) {
    OmiColorScheme(dark) {
        Column(Modifier.fillMaxSize().background(DS.Palette.background).padding(8.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Box(Modifier.size(30.dp, 5.dp).background(DS.Palette.ink, CircleShape))
            repeat(2) {
                Column(
                    Modifier.fillMaxWidth().background(DS.Palette.card, ContinuousRoundedShape(5.dp)).padding(6.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Box(Modifier.fillMaxWidth().height(4.dp).background(DS.Palette.ink.copy(alpha = 0.8f), CircleShape))
                    Box(Modifier.size(24.dp, 4.dp).background(DS.Palette.inkTertiary, CircleShape))
                }
            }
        }
    }
}
