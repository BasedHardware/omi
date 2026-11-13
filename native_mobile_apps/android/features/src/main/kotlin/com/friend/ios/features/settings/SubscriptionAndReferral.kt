package com.friend.ios.features.settings

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.BasicTextField
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiPrimaryButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSheet
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.OmiGroupedList
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiSectionFooter
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.ProfileStore
import com.friend.ios.service.stores.makeProfileStore
import kotlinx.coroutines.launch

/**
 * Port of `SubscriptionAndReferral.swift`. Cancel the plan in the app (Flutter
 * `cancel_subscription_sheet`): why, anything to add, then confirm. Stripe keeps the plan until the
 * end of the billing period.
 */
@Composable
fun CancelSubscriptionSheet(store: ProfileStore, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var reason by remember { mutableStateOf<String?>(null) }
    var details by remember { mutableStateOf("") }
    var isCancelling by remember { mutableStateOf(false) }
    var failed by remember { mutableStateOf(false) }
    // Flutter's reason codes, stored with the cancellation.
    val reasons = listOf(
        "too_expensive" to L("cancelReasonTooExpensive"), "not_using_enough" to L("cancelReasonNotUsing"),
        "missing_features" to L("cancelReasonMissingFeatures"), "audio_quality" to L("cancelReasonAudioQuality"),
        "battery_drain" to L("cancelReasonBatteryDrain"), "found_alternative" to L("cancelReasonFoundAlternative"),
        "other" to L("cancelReasonOther"),
    )
    OmiSheet(onDismiss = onDismiss) {
        Box(Modifier.fillMaxSize()) {
            Column {
                // `ToolbarItem(.cancellationAction)`: Keep subscription, the title in the middle.
                Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = DS.Spacing.lg)) {
                    Text(L("keepSubscription"), style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.align(Alignment.CenterStart).plainButton(onClick = onDismiss))
                    Text(L("cancelSubscription"), style = com.friend.ios.design.TextStyles.headline, color = DS.Palette.ink, modifier = Modifier.align(Alignment.Center))
                }
                OmiGroupedList {
                    section(header = L("whyAreYouCanceling"), footer = L("cancelReasonSubtitle")) {
                        reasons.forEach { (code, title) ->
                            row(key = code, onClick = {
                                haptics.selection()
                                reason = code
                            }) {
                                Text(title, style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.weight(1f))
                                if (reason == code) SFImage("checkmark", tint = DS.Palette.ink)
                            }
                        }
                    }
                    section(header = L("tellUsMore")) {
                        row {
                            Box(Modifier.fillMaxWidth().heightIn(min = 44.dp)) {
                                if (details.isEmpty()) Text(L("cancelReasonDetailHint"), style = DS.Typography.body, color = DS.Palette.inkTertiary)
                                BasicTextField(
                                    details, { details = it },
                                    textStyle = DS.Typography.body.copy(color = DS.Palette.ink),
                                    cursorBrush = SolidColor(DS.Palette.agent),
                                    maxLines = 5,
                                    modifier = Modifier.fillMaxWidth(),
                                )
                            }
                        }
                    }
                    section(header = L("justAMoment")) {
                        row {
                            Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                                Text(L("nativeCancelAtPeriodEnd"), style = DS.Typography.callout, color = DS.Palette.ink)
                                if (failed) Text(L("nativeCancelFailed"), style = DS.Typography.caption, color = DS.Palette.live)
                            }
                        }
                        row(enabled = reason != null && !isCancelling, onClick = {
                            isCancelling = true
                            failed = false
                            scope.launch {
                                if (store.cancelSubscription(reason, details)) {
                                    haptics.success()
                                    onDismiss()
                                } else {
                                    failed = true
                                }
                                isCancelling = false
                            }
                        }) {
                            SettingsButtonText(L("cancelSubscription"), if (reason != null && !isCancelling) DS.Palette.live else DS.Palette.inkDisabled)
                        }
                    }
                }
            }
        }
    }
}

/**
 * Account > Invite friends: one line on what it is, your link with Share and Copy, three short
 * steps. Flutter showed the affiliate page (affiliate.omi.me); it stays one tap away.
 */
@Composable
fun ReferralScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val store = remember { settings.makeProfileStore() }
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val haptics = rememberHaptics()
    val scope = rememberCoroutineScope()
    var copied by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { store.loadReferral() }
    val url = store.referralURL
    val copyTitle = if (copied) L("copied") else L("nativeReferralCopy")
    val shareTitle = L("nativeReferralShare")
    val shareMessage = L("nativeReferralShareMessage")
    val unavailable = L("nativeReferralUnavailable")
    val steps = listOf(L("nativeReferralStep1"), L("nativeReferralStep2"), L("nativeReferralStep3"))
    val programPage = L("nativeReferralProgramPage")
    SettingsListPage(L("nativeSettingsInviteFriends"), onBack) {
        section { plainRow { SettingsHero("gift", L("nativeReferralTitle"), L("nativeReferralHero")) } }
        // Your link with Copy in one group, then Share as the screen's one primary action.
        when {
            url != null -> {
                section {
                    row {
                        Text(
                            url.removePrefix("https://"),
                            style = DS.Typography.callout.copy(fontFamily = FontFamily.Monospace),
                            color = DS.Palette.ink,
                            maxLines = 1,
                            overflow = TextOverflow.MiddleEllipsis,
                        )
                    }
                    row(onClick = {
                        (context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager)?.setPrimaryClip(ClipData.newPlainText(null, url))
                        haptics.success()
                        copied = true
                    }, separatorInset = OmiListMetrics.iconSeparatorInset) {
                        SettingsRowLabel(copyTitle, if (copied) "checkmark" else "doc.on.doc")
                    }
                }
                section {
                    plainRow {
                        OmiPrimaryButton(shareTitle) { shareText(context, "$shareMessage\n$url") }
                    }
                }
            }
            store.referralFailed -> section { row { RetryRow(unavailable) { scope.launch { store.loadReferral() } } } }
            else -> section { row { Box(Modifier.fillMaxWidth().heightIn(min = 120.dp), contentAlignment = Alignment.Center) { OmiProgress() } } }
        }
        section(
            header = L("nativeReferralHowItWorks"),
            footerContent = {
                OmiSectionFooter(programPage, Modifier.padding(top = DS.Spacing.xs).plainButton { uriHandler.openUri("https://affiliate.omi.me/") })
            },
        ) {
            steps.forEachIndexed { index, text ->
                // As the steps in Connect your AI: the number in quiet gray, then one sentence.
                row {
                    Row(Modifier.padding(vertical = DS.Spacing.xxs), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                        Text("${index + 1}", style = DS.Typography.body.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkSecondary, modifier = Modifier.width(18.dp))
                        Text(text, style = DS.Typography.body, color = DS.Palette.ink)
                    }
                }
            }
        }
    }
}
