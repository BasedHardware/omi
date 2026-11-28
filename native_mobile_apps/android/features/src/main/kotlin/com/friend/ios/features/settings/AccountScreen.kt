package com.friend.ios.features.settings

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.service.LocalSessionStore
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.changeName
import kotlinx.coroutines.launch

/**
 * Port of `AccountScreen.swift`. Account: name and email, plan & usage, invite friends, then sign
 * out and delete account. The user ID sits in Developer (only people building with Omi need it).
 */
@Composable
fun AccountScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val session = LocalSessionStore.current
    val navigator = LocalSettingsNavigator.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    var confirmSignOut by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    var editingName by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf("") }
    var shownName by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { settings.loadSubscription() }

    val notSet = L("notSet")
    val planUsage = SettingsTopic.PlanUsage
    val referral = SettingsTopic.Referral
    val planUsageTitle = planUsage.title()
    val referralTitle = referral.title()
    val planValue = settings.subscription?.let { planName(it) }
    SettingsListPage(L("account"), onBack) {
        section {
            row(onClick = {
                newName = shownName ?: settings.displayName.orEmpty()
                editingName = true
            }) { SettingsLabeledContent(L("name"), shownName ?: settings.displayName ?: notSet) }
            row { SettingsLabeledContent(L("email"), settings.email ?: notSet) }
        }
        section {
            row(onClick = { navigator.push(planUsage) }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
                SettingsRowLabel(planUsageTitle, planUsage.systemImage, value = planValue)
            }
            row(onClick = { navigator.push(referral) }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
                SettingsRowLabel(referralTitle, referral.systemImage)
            }
        }
        section {
            // The whole setup again: languages, the Omi, the voice (closes Settings).
            row(onClick = {
                navigator.dismiss()
                session.replayOnboarding()
            }) { SettingsRowLabel(L("nativeRedoOnboarding"), "arrow.counterclockwise") }
        }
        section {
            row(onClick = { confirmSignOut = true }) { SettingsButtonText(L("nativeSignOut")) }
            row(onClick = { confirmDelete = true }) { SettingsButtonText(L("nativeDeleteAccount"), DS.Palette.live) }
        }
    }

    if (confirmSignOut) {
        OmiConfirmationDialog(
            L("signOutQuestion"),
            listOf(DialogButton(L("nativeSignOut"), DialogButton.Role.Destructive) { session.signOut() }),
            onDismiss = { confirmSignOut = false },
        )
    }
    if (confirmDelete) {
        OmiConfirmationDialog(
            L("nativeDeleteAccountQuestion"),
            listOf(DialogButton(L("nativeDeleteAccount"), DialogButton.Role.Destructive) { scope.launch { session.deleteAccount(null) } }),
            onDismiss = { confirmDelete = false },
            message = L("nativeDeleteAccountWarning"),
        )
    }
    if (editingName) {
        OmiAlert(
            L("editName"),
            listOf(
                DialogButton(L("cancel"), DialogButton.Role.Cancel),
                DialogButton(L("save"), enabled = newName.isNotBlank()) {
                    val name = newName
                    scope.launch {
                        session.changeName(name)
                        settings.nameChanged(name)
                        shownName = settings.displayName
                        haptics.success()
                    }
                },
            ),
            onDismiss = { editingName = false },
            message = L("nativeHowShouldOmiCallYou"),
            textField = L("nativeYourName") to newName,
            onTextChange = { newName = it },
        )
    }
}
