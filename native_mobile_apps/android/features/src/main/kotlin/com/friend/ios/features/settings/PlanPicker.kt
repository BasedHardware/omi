package com.friend.ios.features.settings

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.PlanOffer
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiPrimaryButton
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.omiSurface
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiConfirmationDialog
import com.friend.ios.features.components.OmiListBuilder
import com.friend.ios.service.stores.PlanCatalog
import com.friend.ios.service.stores.PlanPurchase
import com.friend.ios.service.stores.PlanStore
import com.friend.ios.service.stores.PlanTier
import kotlinx.coroutines.launch

/**
 * Port of `PlanPicker.swift`. Plan & usage > the plans: Monthly or Yearly (with what yearly
 * saves), one card per plan (kicker, name, what it gives, price), a promo code, and the one button.
 * Free or cancelled: Stripe's checkout opens ([onCheckout]). A running plan: switching asks first.
 * Never pays by itself.
 */
@Composable
@androidx.compose.runtime.NonRestartableComposable
fun OmiListBuilder.planPickerSection(store: PlanStore, onCheckout: (String) -> Unit) {
    val scope = rememberCoroutineScope()
    val title = pickerTitle(store)
    if (store.plansUnavailable) {
        val unavailable = L("nativePlanUnavailable")
        val unavailableBody = L("nativePlanUnavailableBody")
        val tryAgain = L("nativeTryAgain")
        section(header = title) {
            row {
                Column(Modifier.padding(vertical = DS.Spacing.xxs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                    Text(unavailable, style = DS.Typography.body, color = DS.Palette.ink)
                    Text(unavailableBody, style = DS.Typography.callout, color = DS.Palette.inkSecondary)
                }
            }
            row(onClick = { scope.launch { store.load() } }) { SettingsButtonText(tryAgain) }
        }
    } else if (store.tiers.isNotEmpty()) {
        val footer = when (store.purchase) {
            is PlanPurchase.Checkout -> L("nativePlanCheckoutFooter")
            is PlanPurchase.Change -> L("nativePlanChangeFooter")
            PlanPurchase.ManagedElsewhere -> L("nativePlanManagedOnMac")
            PlanPurchase.Current, null -> null
        }
        section(header = title, footer = footer) {
            if (store.offersBothIntervals) plainRow { IntervalSwitch(store) }
            store.tiers.forEach { tier ->
                plainRow(key = tier.id) {
                    PlanCard(tier, store.interval, tier.id == store.selectedTier?.id, Modifier.padding(top = DS.Spacing.sm)) { store.selectedTierID = tier.id }
                }
            }
            plainRow(inset = DS.Spacing.lg) { Promo(store) }
            plainRow { BuyButton(store, onCheckout) }
        }
    }
}

@Composable
private fun pickerTitle(store: PlanStore): String {
    val subscription = store.subscription ?: return L("nativePlanUpgradeTitle")
    if (subscription.isPaid) return if (subscription.cancelAtPeriodEnd) L("nativePlanResubscribeTitle") else L("nativePlanChangeTitle")
    return L("nativePlanUpgradeTitle")
}

/** Monthly | Yearly · save 25 %, as two quiet capsules (the chips on Home). */
@Composable
private fun IntervalSwitch(store: PlanStore) {
    val haptics = rememberHaptics()
    val yearly = PlanCatalog.bestSavingsPercent(store.tiers)?.let { L("nativePlanYearlySave", "$it") } ?: L("nativePlanYearly")
    Row(Modifier.fillMaxWidth().padding(top = DS.Spacing.xs), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        listOf(L("nativePlanMonthly") to PlanOffer.Interval.Month, yearly to PlanOffer.Interval.Year).forEach { (text, interval) ->
            val selected = store.interval == interval
            Text(
                text,
                style = TextStyles.subheadline.semibold(),
                color = if (selected) DS.Palette.onAccent else DS.Palette.ink,
                modifier = Modifier
                    .plainButton {
                        haptics.selection()
                        store.interval = interval
                    }
                    .background(if (selected) DS.Palette.ink else DS.Palette.card, CircleShape)
                    .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
            )
        }
    }
}

/** "Promo code" opens one field; the code goes with checkout or the switch. */
@Composable
private fun Promo(store: PlanStore) {
    var showsPromo by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(top = DS.Spacing.sm), verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm)) {
        Row(
            Modifier.heightIn(min = 36.dp).plainButton { showsPromo = !showsPromo },
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs),
        ) {
            SFImage("tag", size = 15.sp, tint = DS.Palette.inkSecondary)
            Text(L("promoCode"), style = DS.Typography.callout, color = DS.Palette.inkSecondary)
            SFImage(if (showsPromo) "chevron.up" else "chevron.down", size = 13.sp, tint = DS.Palette.inkSecondary)
        }
        AnimatedVisibility(showsPromo) {
            Box(
                Modifier.fillMaxWidth().heightIn(min = DS.Size.searchField).omiSurface(CircleShape).padding(horizontal = DS.Spacing.lg),
                contentAlignment = Alignment.CenterStart,
            ) {
                if (store.promoCode.isEmpty()) Text(L("enterPromoCode"), style = DS.Typography.body, color = DS.Palette.inkTertiary)
                BasicTextField(
                    value = store.promoCode,
                    onValueChange = { store.promoCode = it },
                    singleLine = true,
                    textStyle = DS.Typography.body.copy(color = DS.Palette.ink),
                    cursorBrush = SolidColor(DS.Palette.agent),
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, autoCorrectEnabled = false),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

@Composable
private fun BuyButton(store: PlanStore, onCheckout: (String) -> Unit) {
    val purchase = store.purchase ?: return
    val scope = rememberCoroutineScope()
    var confirmsChange by remember { mutableStateOf(false) }
    val tierName = store.selectedTier?.title.orEmpty()
    fun buy() = scope.launch { store.buy()?.let(onCheckout) }
    val title = when (purchase) {
        PlanPurchase.Current -> L("nativePlanIsCurrent")
        PlanPurchase.ManagedElsewhere, is PlanPurchase.Change -> L("nativePlanSwitchTo", tierName)
        is PlanPurchase.Checkout -> if (store.subscription?.cancelAtPeriodEnd == true) L("resubscribe") else L("nativeUpgradeTo", tierName)
    }
    OmiPrimaryButton(
        title,
        Modifier.padding(top = DS.Spacing.sm),
        enabled = !store.isWorking && purchase != PlanPurchase.Current && purchase != PlanPurchase.ManagedElsewhere,
    ) {
        if (purchase is PlanPurchase.Change) confirmsChange = true else buy()
    }
    if (confirmsChange) {
        // Same plan, monthly to yearly: starts when the period ends. Another plan: now, prorated.
        val message = if (store.selectedTier?.isCurrent == true) L("nativePlanConfirmYearlyBody") else L("nativePlanConfirmSwitchBody", tierName)
        OmiConfirmationDialog(
            L("nativePlanConfirmSwitch", tierName),
            listOf(DialogButton(L("nativePlanSwitch")) { buy() }),
            onDismiss = { confirmsChange = false },
            message = message,
        )
    }
}

/**
 * One plan as a card (Home's decision cards): a colored kicker ("Most popular"), the name and its
 * one line, the price on the right, what it includes as check lines. The chosen one has an ink
 * edge and a check.
 */
@Composable
fun PlanCard(tier: PlanTier, interval: PlanOffer.Interval, isSelected: Boolean, modifier: Modifier = Modifier, onSelect: () -> Unit) {
    val haptics = rememberHaptics()
    val shape = ContinuousRoundedShape(DS.Radius.card)
    // "Current" on the plan paid now, else the backend's eyebrow in Omi blue.
    val kicker = if (tier.isCurrent) L("nativePlanCurrent") to DS.Palette.success else tier.eyebrow?.let { it to DS.Palette.agent }
    Column(
        modifier
            .fillMaxWidth()
            .plainButton {
                haptics.selection()
                onSelect()
            }
            .background(DS.Palette.card, shape)
            .border(if (isSelected) 1.5.dp else 1.dp, if (isSelected) DS.Palette.ink else DS.Palette.cardStroke, shape)
            .padding(DS.Spacing.lg),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.sm),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            kicker?.let { (text, color) -> Text(text, style = TextStyles.footnote.semibold(), color = color) }
            Spacer(Modifier.weight(1f).width(DS.Spacing.sm))
            // A radio, as in a system picker: the chosen plan filled.
            SFImage(if (isSelected) "checkmark.circle.fill" else "circle", size = 20.sp, tint = if (isSelected) DS.Palette.ink else DS.Palette.inkTertiary)
        }
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(tier.title, style = DS.Typography.sectionTitle, color = DS.Palette.ink)
                val subtitle = tier.subtitle
                if (subtitle != null && subtitle !in tier.features) Text(subtitle, style = DS.Typography.callout, color = DS.Palette.inkSecondary)
            }
            Spacer(Modifier.width(DS.Spacing.sm))
            Price(tier, interval)
        }
        if (tier.features.isNotEmpty()) {
            Column(Modifier.padding(top = DS.Spacing.xxs), verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs)) {
                tier.features.forEach { feature ->
                    Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.sm), verticalAlignment = Alignment.CenterVertically) {
                        SFImage("checkmark", size = 12.sp, weight = FontWeight.SemiBold, tint = DS.Palette.inkSecondary)
                        Text(feature, style = DS.Typography.callout, color = DS.Palette.ink)
                    }
                }
            }
        }
    }
}

/** "$13/mo", and for yearly what is billed once a year. */
@Composable
private fun Price(tier: PlanTier, interval: PlanOffer.Interval) {
    val offer = tier.offer(interval) ?: tier.offer(if (interval == PlanOffer.Interval.Year) PlanOffer.Interval.Month else PlanOffer.Interval.Year) ?: return
    Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(offer.priceString, style = DS.Typography.body.semibold().copy(fontFeatureSettings = "tnum"), color = DS.Palette.ink)
        val amount = offer.unitAmount
        if (offer.interval == PlanOffer.Interval.Year && amount != null) {
            Text(L("nativePlanBilledYearly", usd(amount / 100.0)), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
        }
    }
}
