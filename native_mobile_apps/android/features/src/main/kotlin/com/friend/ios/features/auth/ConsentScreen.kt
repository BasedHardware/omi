package com.friend.ios.features.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.CalmBackground
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiPrimaryButton
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.bold
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.service.LocalSessionStore

/**
 * Port of `ConsentScreen.swift`: Data & AI consent, before any AI processing (Flutter
 * `ai_consent_widget.dart`, same ARB copy). Local only, like Flutter's `aiConsentGiven`; shown
 * again after every sign-in.
 */
@Composable
fun ConsentScreen() {
    val session = LocalSessionStore.current
    val haptics = rememberHaptics()
    Box(Modifier.fillMaxSize()) {
        CalmBackground()
        Column(
            Modifier.fillMaxSize().safeDrawingPadding().padding(DS.Spacing.gutter),
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg),
        ) {
            Spacer(Modifier.weight(1f))
            SFImage("lock.shield.fill", size = 40.sp, tint = DS.Palette.agent)
            Text(L("dataAndPrivacy"), style = TextStyles.title1.bold(), color = DS.Palette.ink)
            Text(L("consentDataMessage"), style = DS.Typography.body, color = DS.Palette.inkSecondary)
            Text(
                legalText(L("yourDataIsProtected"), L("privacyPolicy"), L("and"), L("termsOfService"), linkColor = DS.Palette.ink),
                style = DS.Typography.caption,
                color = DS.Palette.inkTertiary,
            )
            Spacer(Modifier.weight(1f))
            OmiPrimaryButton(L("agreeAndContinue"), Modifier.padding(top = DS.Spacing.sm).testTag("consent.agree")) {
                haptics.success()
                session.giveConsent()
            }
            Box(
                Modifier.fillMaxWidth().heightIn(min = 40.dp).plainButton { session.signOut() },
                contentAlignment = Alignment.Center,
            ) {
                Text(L("useDifferentAccount"), style = TextStyles.callout.semibold(), color = DS.Palette.ink)
            }
        }
    }
}
