package com.friend.ios.features.settings

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiNavigationStack
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.OmiSearchField
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.rememberNavPath
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.service.LocalPhoneCallStore
import com.friend.ios.service.phonecalls.CallingCodes
import com.friend.ios.service.phonecalls.PhoneNumberFormat
import com.friend.ios.service.stores.PhoneCallStore
import com.friend.ios.service.stores.PhoneCallStore.Verification
import com.friend.ios.service.stores.pollVerification
import com.friend.ios.service.stores.retryVerification
import com.friend.ios.service.stores.startVerification
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.text.Collator
import java.util.Locale

/** The setup's own pushes (`NavigationLink { CountryPicker }`, `.navigationDestination { PhoneVerifyScreen }`). */
private enum class PhoneSetupRoute { Country, Verify }

/**
 * Port of `PhoneNumberSetupScreen.swift`. Your number as caller ID: pick the country, type the
 * number, Omi has Twilio call it (Flutter `phone_setup_number_page`).
 */
@Composable
fun PhoneNumberSetupScreen(onBack: () -> Unit) {
    val phone = LocalPhoneCallStore.current
    val scope = rememberCoroutineScope()
    val path = rememberNavPath<PhoneSetupRoute>()
    var region by rememberSaveable { mutableStateOf(Locale.getDefault().country.uppercase().ifEmpty { "US" }) }
    var number by rememberSaveable { mutableStateOf("") }
    val e164 = PhoneNumberFormat.e164(number, region)

    OmiNavigationStack(path, root = {
        val focus = remember { FocusRequester() }
        LaunchedEffect(Unit) { runCatching { focus.requestFocus() } }
        val title = L("nativePhoneYourNumberTitle")
        val countryLabel = L("nativePhoneCountry")
        val hint = L("phoneNumberHint")
        val failure = phone.verificationFailure
        val footer = when {
            failure != null -> null
            number.isNotEmpty() && e164 == null -> L("nativePhoneInvalidNumber")
            else -> L("nativePhoneCallerIDHint")
        }
        val failureText = failure?.let { PhoneCallWording.failure(it) }
        val continueTitle = L("phoneContinue")
        SettingsListPage(title, onBack) {
            section(
                header = title,
                footer = footer,
                footerContent = failureText?.let { text -> { Text(text, style = TextStyles.footnote, color = DS.Palette.live, modifier = Modifier.padding(horizontal = OmiListMetrics.rowInset)) } },
            ) {
                row(onClick = { path.push(PhoneSetupRoute.Country) }, chevron = true) {
                    SettingsLabeledContent(countryLabel, countryTitle(region))
                }
                row {
                    Box(Modifier.fillMaxWidth()) {
                        if (number.isEmpty()) Text(hint, style = DS.Typography.body, color = DS.Palette.inkTertiary)
                        BasicTextField(
                            number, { number = it }, singleLine = true,
                            textStyle = DS.Typography.body.copy(color = DS.Palette.ink),
                            cursorBrush = SolidColor(DS.Palette.agent),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                            modifier = Modifier.fillMaxWidth().focusRequester(focus),
                        )
                    }
                }
            }
            section {
                val enabled = e164 != null && !phone.isStartingVerification
                row(enabled = enabled, onClick = {
                    val target = e164 ?: return@row
                    scope.launch {
                        if (!phone.startVerification(target)) return@launch
                        if (phone.verification?.status == Verification.Status.Verified) onBack() else path.push(PhoneSetupRoute.Verify)
                    }
                }) {
                    Text(continueTitle, style = DS.Typography.button, color = if (enabled) DS.Palette.ink else DS.Palette.inkDisabled)
                    if (phone.isStartingVerification) {
                        Spacer(Modifier.weight(1f))
                        OmiProgress()
                    }
                }
            }
        }
    }) { route ->
        when (route) {
            PhoneSetupRoute.Country -> CountryPicker(region, onBack = { path.pop() }) {
                region = it
                path.pop()
            }
            PhoneSetupRoute.Verify -> PhoneVerifyScreen(onBack = { path.pop() }, onDone = onBack)
        }
    }
}

/**
 * Twilio is calling: answer, type the code (Flutter `phone_setup_verify_page`). Polls while shown.
 */
@Composable
fun PhoneVerifyScreen(onBack: () -> Unit, onDone: () -> Unit) {
    val phone = LocalPhoneCallStore.current
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val status = phone.verification?.status
    LaunchedEffect(Unit) { phone.pollVerification() }
    LaunchedEffect(status) {
        if (status != Verification.Status.Verified) return@LaunchedEffect
        haptics.success()
        delay(800)
        onDone()
    }
    val look = statusLook(status ?: Verification.Status.Calling)
    val pulses = status == Verification.Status.Calling || status == Verification.Status.InProgress
    val answerFrom = L("nativePhoneAnswerCallFrom")
    val enterCode = L("nativePhoneEnterCodeOnCall")
    val followVoice = L("nativePhoneFollowVoice")
    val tryAgain = L("phoneTryAgain")
    val code = phone.verification?.code
    SettingsListPage(L("nativePhoneSetupStep1Title"), onBack) {
        section(footer = PhoneNumberFormat.display(phone.verification?.phoneNumber.orEmpty())) {
            row(separatorInset = OmiListMetrics.iconSeparatorInset) {
                Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md), verticalAlignment = Alignment.CenterVertically) {
                    PulsingSymbol(look.icon, look.tint, pulses)
                    Text(look.text, style = DS.Typography.body, color = look.tint)
                }
            }
            row { SettingsLabeledContent(answerFrom, PhoneCallStore.VERIFICATION_CALLER_ID) }
            row {
                if (code != null) {
                    Column(Modifier.padding(vertical = DS.Spacing.xs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                        Text(enterCode, style = DS.Typography.body, color = DS.Palette.inkSecondary)
                        Text(
                            code.toList().joinToString(" "),
                            style = TextStyles.system(34, FontWeight.Bold).copy(fontFeatureSettings = "tnum"),
                            color = DS.Palette.ink,
                        )
                    }
                } else {
                    Text(followVoice, style = DS.Typography.body, color = DS.Palette.ink)
                }
            }
        }
        if (status == Verification.Status.Missed || status == Verification.Status.TimedOut) {
            section {
                row(enabled = !phone.isStartingVerification, onClick = { scope.launch { phone.retryVerification() } }) {
                    Text(tryAgain, style = DS.Typography.body, color = DS.Palette.agent)
                }
            }
        }
    }
}

private class StatusLook(val text: String, val icon: String, val tint: Color)

@Composable
private fun statusLook(status: Verification.Status): StatusLook = when (status) {
    Verification.Status.Calling -> StatusLook(L("statusCalling"), "phone.arrow.down.left", DS.Palette.ink)
    Verification.Status.InProgress -> StatusLook(L("statusCallInProgress"), "phone.connection", DS.Palette.ink)
    Verification.Status.Missed -> StatusLook(L("statusCallMissed"), "phone.down", DS.Palette.warning)
    Verification.Status.Verified -> StatusLook(L("statusVerifiedLabel"), "checkmark.circle.fill", DS.Palette.success)
    Verification.Status.TimedOut -> StatusLook(L("statusTimedOut"), "exclamationmark.circle", DS.Palette.live)
}

/** `.symbolEffect(.pulse, isActive:)`. */
@Composable
private fun PulsingSymbol(name: String, tint: Color, pulses: Boolean) {
    val transition = rememberInfiniteTransition(label = "pulse")
    val alpha by transition.animateFloat(1f, 0.35f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "alpha")
    Box(Modifier.width(28.dp), contentAlignment = Alignment.Center) {
        SFImage(name, size = 17.sp, tint = tint, modifier = if (pulses) Modifier.alpha(alpha) else Modifier)
    }
}

/** Every region with a calling code, searchable, in the user's language. */
@Composable
fun CountryPicker(selection: String, onBack: () -> Unit, onSelect: (String) -> Unit) {
    var query by remember { mutableStateOf("") }
    val prompt = L("searchCountries")
    val regions = remember(query) {
        val collator = Collator.getInstance()
        CallingCodes.byRegion.keys
            .filter { query.isEmpty() || countryTitle(it).contains(query, ignoreCase = true) }
            .sortedWith { a, b -> collator.compare(countryTitle(a), countryTitle(b)) }
    }
    SettingsListPage(L("phoneSelectCountryTitle"), onBack) {
        section { plainRow { OmiSearchField(prompt, query, { query = it }, L("nativeClearSearch")) } }
        section {
            regions.forEach { region ->
                row(key = region, onClick = { onSelect(region) }) {
                    Text(countryTitle(region), style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.weight(1f))
                    if (region == selection) SFImage("checkmark", size = 17.sp, tint = DS.Palette.ink)
                }
            }
        }
    }
}

/** `CountryPicker.title`: "Germany (+49)" in the user's language. */
fun countryTitle(region: String): String {
    val name = Locale("", region).getDisplayCountry(Locale.getDefault()).ifEmpty { region }
    return CallingCodes.byRegion[region]?.let { "$name (+$it)" } ?: name
}
