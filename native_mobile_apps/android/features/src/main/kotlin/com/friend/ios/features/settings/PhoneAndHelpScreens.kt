package com.friend.ios.features.settings

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import com.friend.ios.design.L
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiToggleRow
import com.friend.ios.service.LocalDeveloperStore
import java.util.Locale

// Phone Calls moved to PhoneCallsScreen.kt (the whole phone surface).

/**
 * Port of `PhoneAndHelpScreens.swift`. Help: the help center, feedback, what's new, replaying the
 * introduction, and developer mode. [onReplayIntroduction] closes Settings and shows the short
 * introduction to the app again.
 */
@Composable
fun HelpScreen(onBack: () -> Unit, onReplayIntroduction: () -> Unit) {
    val developer = LocalDeveloperStore.current
    val navigator = LocalSettingsNavigator.current
    val uriHandler = LocalUriHandler.current
    val icon = OmiListMetrics.iconSeparatorInset
    val helpCenter = L("helpCenter")
    val feedback = L("nativeSendFeedback")
    val whatsNew = L("whatsNew")
    val replay = L("nativeReplayIntroduction")
    val developerMode = L("nativeDeveloperMode")
    SettingsListPage(L("nativeSettingsHelp"), onBack) {
        section {
            row(onClick = { uriHandler.openUri("https://help.omi.me/${helpLanguage()}/") }, separatorInset = icon) {
                SettingsRowLabel(helpCenter, "book", Modifier.weight(1f))
                SettingsExternalArrow()
            }
            row(onClick = { uriHandler.openUri("https://feedback.omi.me/") }, separatorInset = icon) {
                SettingsRowLabel(feedback, "bubble.left", Modifier.weight(1f))
                SettingsExternalArrow()
            }
            supportChatRow() // Intercom support chat, only when configured
            row(onClick = { navigator.push(SettingsTopic.WhatsNew) }, chevron = true, separatorInset = icon) {
                SettingsRowLabel(whatsNew, "gift")
            }
        }
        section {
            row(onClick = onReplayIntroduction, separatorInset = icon) { SettingsRowLabel(replay, "play.rectangle") }
        }
        section(footer = L("nativeDeveloperModeFooter")) {
            row(separatorInset = icon) {
                OmiToggleRow(developer.isDeveloperMode, { developer.isDeveloperMode = it }) {
                    SettingsRowLabel(developerMode, "chevron.left.forwardslash.chevron.right")
                }
            }
        }
    }
}

/** Help center languages (Flutter `settings_destinations.dart`), English otherwise. */
fun helpLanguage(): String {
    val supported = listOf("en", "de", "es", "fr", "it", "pt", "ja", "ko", "zh", "nl", "pl", "ru", "tr")
    val code = Locale.getDefault().language
    return if (code in supported) code else "en"
}
