package com.friend.ios.features.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSheet
import com.friend.ios.features.components.ConversationRow
import com.friend.ios.features.components.ConversationRowStyle
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.features.components.OmiListBuilder
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.network.endpoints.PhoneCallErrorDetail
import com.friend.ios.network.endpoints.PhoneCallQuota
import com.friend.ios.network.endpoints.VerifiedPhoneNumber
import com.friend.ios.service.LocalPhoneCallStore
import com.friend.ios.service.phonecalls.PhoneCallFailure
import com.friend.ios.service.phonecalls.PhoneNumberFormat
import com.friend.ios.service.stores.PhoneCallStore
import com.friend.ios.service.stores.deleteNumber
import com.friend.ios.service.stores.load
import kotlinx.coroutines.launch
import java.time.Instant

/**
 * Port of `PhoneCallsScreen.swift`. Settings > Phone Calls, the whole phone surface (Flutter
 * `phone_calls_page`, `phone_setup_intro_page`, `phone_call_settings_page`): set up a caller ID,
 * start a call (keypad or a contact), your number with delete, and past calls (the conversations
 * they became).
 */
@Composable
fun PhoneScreen(onBack: () -> Unit) {
    val phone = LocalPhoneCallStore.current
    val scope = rememberCoroutineScope()
    // Debug (`--ez omiPhoneDialer true`): the dialer opens for screenshots.
    var showsDialer by remember { mutableStateOf(com.friend.ios.features.components.DebugLaunch.flag("omiPhoneDialer")) }
    var deleting by remember { mutableStateOf<VerifiedPhoneNumber?>(null) }
    var deleteFailed by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { phone.load() }
    SettingsListPage(L("nativeSettingsPhoneCalls"), onBack) {
        val unavailable = phone.unavailable
        when {
            unavailable != null -> lockedSections(unavailable)
            !phone.numbersLoaded -> section { row { Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { OmiProgress() } } }
            phone.numbers.isEmpty() -> phoneIntroSections()
            else -> {
                callSection(phone) { showsDialer = true }
                numbersSection(phone) { deleting = it }
                historySection(phone)
            }
        }
    }
    if (showsDialer) {
        OmiSheet(onDismiss = { showsDialer = false }) { PhoneDialerScreen(onDismiss = { showsDialer = false }) }
    }
    // The call screen comes up here while Settings is open; elsewhere the app shell shows it.
    if (phone.showsCallScreen && !showsDialer && phone.phase != PhoneCallStore.Phase.Idle) {
        ActiveCallCover(onDismiss = { phone.showsCallScreen = false })
    }
    deleting?.let { number ->
        OmiConfirmationDialog(
            L("nativePhoneDeleteNumberTitle", PhoneNumberFormat.display(number.phoneNumber)),
            listOf(DialogButton(L("delete"), DialogButton.Role.Destructive) { scope.launch { deleteFailed = !phone.deleteNumber(number.id) } }),
            onDismiss = { deleting = null },
            message = L("nativePhoneDeleteNumberMessage"),
        )
    }
    if (deleteFailed) OmiAlert(L("phoneDeleteNumberFailed"), listOf(DialogButton(L("ok"))), onDismiss = { deleteFailed = false })
}

/**
 * Calls are not available on this plan (or the free calls are used up): what calling with Omi
 * is, why it is locked, and the way to the plans.
 */
@Composable
private fun OmiListBuilder.lockedSections(unavailable: PhoneCallErrorDetail) {
    val navigator = LocalSettingsNavigator.current
    val heroTitle = L("phoneCallsWithOmi")
    val heroMessage = L("phoneCallsSubtitle")
    val reason = PhoneCallWording.unavailable(unavailable)
    val seePlans = L("nativeSettingsSeePlans")
    section { plainRow { SettingsHero("phone.bubble", heroTitle, heroMessage) } }
    section {
        row(separatorInset = OmiListMetrics.iconSeparatorInset) {
            Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md), verticalAlignment = Alignment.CenterVertically) {
                SettingsIcon("lock")
                Text(reason, style = DS.Typography.callout, color = DS.Palette.inkSecondary)
            }
        }
        row(onClick = { navigator.push(SettingsTopic.PlanUsage) }, chevron = true) {
            Text(seePlans, style = DS.Typography.button, color = DS.Palette.ink)
        }
    }
}

@Composable
private fun OmiListBuilder.callSection(phone: PhoneCallStore, onNewCall: () -> Unit) {
    val returnTitle = L("nativePhoneReturnToCall")
    val newCall = L("nativePhoneNewCall")
    val footer = PhoneCallWording.quota(phone.quota)
    section(footer = footer) {
        if (phone.isInProgress && !phone.showsCallScreen) {
            row(onClick = { phone.showsCallScreen = true }, separatorInset = OmiListMetrics.iconSeparatorInset) {
                SettingsRowLabel(returnTitle, "phone.connection", tint = DS.Palette.success, titleColor = DS.Palette.success)
            }
        } else {
            val enabled = phone.quota?.hasAccess ?: true
            row(onClick = onNewCall, enabled = enabled, separatorInset = OmiListMetrics.iconSeparatorInset) {
                SettingsRowLabel(newCall, "phone", titleColor = if (enabled) DS.Palette.ink else DS.Palette.inkDisabled)
            }
        }
    }
}

@Composable
private fun OmiListBuilder.numbersSection(phone: PhoneCallStore, onDelete: (VerifiedPhoneNumber) -> Unit) {
    val deleteTitle = L("delete")
    section(header = L("nativeYourNumbers"), footer = L("nativePhoneCallerIDFooter")) {
        phone.numbers.forEach { number ->
            val verified = PhoneCallWording.verified(number.verifiedAt)
            row(key = number.id) {
                // `.swipeActions` / `.contextMenu`: Delete on a long press.
                ContextMenuBox({ listOf(MenuSection(items = listOf(MenuItem(deleteTitle, "trash", destructive = true) { onDelete(number) }))) }, Modifier.fillMaxWidth()) {
                    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                        Text(PhoneNumberFormat.display(number.phoneNumber), style = DS.Typography.cardTitle, color = DS.Palette.ink)
                        Text(verified, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                    }
                }
            }
        }
    }
}

@Composable
private fun OmiListBuilder.historySection(phone: PhoneCallStore) {
    val navigator = LocalSettingsNavigator.current
    val noCalls = L("nativePhoneNoCallsYet")
    section(header = L("nativePhoneRecentCalls")) {
        if (phone.history.isEmpty()) {
            row { Text(noCalls, style = DS.Typography.body, color = DS.Palette.inkSecondary) }
        }
        phone.history.forEach { conversation ->
            row(key = conversation.id, onClick = { navigator.openConversation?.invoke(conversation.id) }) {
                ConversationRow(conversation, Modifier.fillMaxWidth(), style = ConversationRowStyle.Plain)
            }
        }
    }
}

/** No number yet: what calling with Omi is, three steps, then number setup. */
@Composable
private fun OmiListBuilder.phoneIntroSections() {
    val navigator = LocalSettingsNavigator.current
    val heroTitle = L("phoneCallsWithOmi")
    val heroMessage = L("phoneCallsSubtitle")
    val getStarted = L("phoneGetStarted")
    val steps = listOf(
        Triple("checkmark.shield", L("nativePhoneSetupStep1Title"), L("nativePhoneSetupStep1Subtitle")),
        Triple("circle.grid.3x3", L("nativePhoneSetupStep2Title"), L("nativePhoneSetupStep2Subtitle")),
        Triple("waveform", L("nativePhoneSetupStep3Title"), L("phoneSetupStep3Subtitle")),
    )
    section { plainRow { SettingsHero("phone.bubble", heroTitle, heroMessage) } }
    section(footer = L("nativeCallRecordingConsent")) {
        steps.forEach { (icon, title, subtitle) ->
            row(separatorInset = OmiListMetrics.iconSeparatorInset) {
                Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md), verticalAlignment = Alignment.CenterVertically) {
                    SettingsIcon(icon)
                    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                        Text(title, style = DS.Typography.body, color = DS.Palette.ink)
                        Text(subtitle, style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                    }
                }
            }
        }
    }
    section {
        row(onClick = { navigator.push(SettingsRoute.PhoneNumberSetup) }, chevron = true) {
            Text(getStarted, style = DS.Typography.button, color = DS.Palette.ink)
        }
    }
}

/** How the phone screens word store states. */
object PhoneCallWording {
    @Composable
    fun failure(failure: PhoneCallFailure): String = when (failure) {
        PhoneCallFailure.AlreadyInProgress -> L("callAlreadyInProgress")
        PhoneCallFailure.MicrophonePermission -> L("nativePhoneMicrophoneNeeded")
        PhoneCallFailure.NoVerifiedNumber -> L("nativePhoneSetupStep1Title")
        is PhoneCallFailure.Server -> failure.detail?.let { unavailable(it) } ?: L("failedToStartCall")
        is PhoneCallFailure.Engine -> failure.message
    }

    @Composable
    fun unavailable(detail: PhoneCallErrorDetail): String = when (detail) {
        is PhoneCallErrorDetail.QuotaExceeded -> L("phoneFreeCallLimitReached")
        is PhoneCallErrorDetail.Message ->
            if (detail.text.contains("paid subscription", ignoreCase = true)) L("nativePhoneCallsNeedPlan") else detail.text
    }

    /** Free plans: calls left this month (and their length); nothing on unlimited plans. */
    @Composable
    fun quota(quota: PhoneCallQuota?): String? {
        if (quota == null || quota.isPaid) return null
        val limit = quota.monthlyLimit ?: return null
        if (limit <= 0) return null
        val remaining = quota.remaining ?: (limit - quota.monthlyUsed)
        if (remaining <= 0) return L("phoneFreeCallLimitReached")
        val minutes = (quota.maxDurationSeconds ?: 0) / 60
        return if (minutes > 0) {
            L("phoneFreeCallsRemainingWithMax", remaining.toString(), limit.toString(), minutes.toString())
        } else {
            L("phoneFreeCallsRemaining", remaining.toString(), limit.toString())
        }
    }

    @Composable
    fun verified(date: Instant?): String {
        if (date == null) return L("statusVerifiedLabel")
        return L("nativePhoneVerifiedAgo", relative(date))
    }
}
