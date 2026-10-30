package com.friend.ios.features.settings

import android.app.Activity
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.ContactsContract
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.design.TextStyles
import com.friend.ios.design.plainButton
import com.friend.ios.design.pressable
import com.friend.ios.design.rememberHaptics
import com.friend.ios.design.semibold
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.conversations.SheetBar
import com.friend.ios.service.LocalPhoneCallStore
import com.friend.ios.service.phonecalls.PhoneCallFailure
import com.friend.ios.service.phonecalls.PhoneNumberFormat
import kotlinx.coroutines.launch

/**
 * Port of `PhoneDialerScreen.swift`. Starting a call: type a number on the keypad or pick one from
 * Contacts (the system picker, no contacts permission and no list of our own). Flutter
 * `phone_calls_page` (keypad + contacts tabs).
 */
@Composable
fun PhoneDialerScreen(onDismiss: () -> Unit) {
    val phone = LocalPhoneCallStore.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var number by remember { mutableStateOf("") }
    var contactName by remember { mutableStateOf<String?>(null) }
    var isStarting by remember { mutableStateOf(false) }
    var failure by remember { mutableStateOf<PhoneCallFailure?>(null) }
    // The system's phone-number picker hands back one number with read access to it only.
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val uri = result.data?.data ?: return@rememberLauncherForActivityResult
        if (result.resultCode != Activity.RESULT_OK) return@rememberLauncherForActivityResult
        pickedPhone(context, uri)?.let { (name, picked) ->
            contactName = name
            number = PhoneNumberFormat.stripped(picked)
        }
    }
    fun paste() {
        val text = (context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager)
            ?.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(context)?.toString() ?: return
        // Only the characters a number can have (Flutter `_sanitizePastedNumber`).
        val kept = text.filter { it.isDigit() || it == '+' || it == '*' || it == '#' }
        if (kept.isEmpty()) return
        number = kept
        contactName = null
    }

    Column(Modifier.fillMaxSize().background(DS.Palette.background)) {
        SheetBar(
            L("nativePhoneNewCall"),
            leading = { GlassCircleButton("xmark", contentDescription = L("cancel"), onClick = onDismiss) },
            trailing = {
                GlassCircleButton("person.crop.circle", contentDescription = L("phoneContactsTab")) {
                    picker.launch(Intent(Intent.ACTION_PICK, ContactsContract.CommonDataKinds.Phone.CONTENT_URI))
                }
            },
        )
        Column(
            Modifier.fillMaxSize().navigationBarsPadding().padding(DS.Spacing.gutter),
            verticalArrangement = Arrangement.spacedBy(DS.Spacing.lg, Alignment.Bottom),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            DialerDisplay(number, contactName, onDelete = {
                number = number.dropLast(1)
                if (number.isEmpty()) contactName = null
            }, onPaste = ::paste)
            PhoneKeypad(onKey = { key ->
                contactName = null
                number += key
            }, onLongZero = { number += "+" })
            CallButton(enabled = number.isNotEmpty() && !isStarting, dimmed = number.isEmpty(), isStarting = isStarting) {
                scope.launch {
                    isStarting = true
                    val started = phone.call(number, contactName)
                    isStarting = false
                    if (started) onDismiss() else failure = phone.failure ?: PhoneCallFailure.Server(null)
                }
            }
        }
    }
    failure?.let { shown ->
        OmiAlert(PhoneCallWording.failure(shown), listOf(DialogButton(L("ok"))), onDismiss = { failure = null })
    }
}

@Composable
private fun DialerDisplay(number: String, contactName: String?, onDelete: () -> Unit, onPaste: () -> Unit) {
    val placeholder = L("phoneEnterNumber")
    val paste = L("paste")
    Column(
        Modifier.fillMaxWidth().heightIn(min = 96.dp),
        verticalArrangement = Arrangement.spacedBy(DS.Spacing.xs, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        contactName?.let { Text(it, style = DS.Typography.sectionTitle, color = DS.Palette.ink) }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                number.ifEmpty { placeholder },
                style = TextStyles.system(34, FontWeight.Medium).copy(fontFeatureSettings = "tnum"),
                color = if (number.isEmpty()) DS.Palette.inkTertiary else DS.Palette.ink,
                textAlign = TextAlign.Center,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            if (number.isNotEmpty()) {
                Box(Modifier.plainButton(onClick = onDelete)) { SFImage("delete.left", size = 22.sp, tint = DS.Palette.inkSecondary, contentDescription = L("delete")) }
            }
        }
        if (number.isEmpty()) {
            // `.buttonStyle(.omiPillSubtle)` with its glyph.
            Row(
                Modifier
                    .pressable(pressedScale = 1f, pressedAlpha = 0.8f, haptic = false, onClick = onPaste)
                    .background(DS.Palette.cardRaised, CircleShape)
                    .padding(horizontal = DS.Spacing.lg, vertical = DS.Spacing.sm),
                horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xs),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                SFImage("doc.on.clipboard", size = 14.sp, tint = DS.Palette.ink)
                Text(paste, style = TextStyles.subheadline.semibold(), color = DS.Palette.ink)
            }
        }
    }
}

@Composable
private fun CallButton(enabled: Boolean, dimmed: Boolean, isStarting: Boolean, onClick: () -> Unit) {
    Box(
        Modifier
            .size(76.dp)
            .alpha(if (dimmed) 0.5f else 1f)
            .background(DS.Palette.success, CircleShape)
            .plainButton(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        if (isStarting) OmiProgress(tint = Color.White) else SFImage("phone.fill", size = 28.sp, tint = Color.White, contentDescription = L("phoneCallButton"))
    }
}

/** The 12-key pad (letters under the digits); a long press on 0 types `+`. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun PhoneKeypad(onKey: (String) -> Unit, onLongZero: (() -> Unit)? = null) {
    val haptics = rememberHaptics()
    Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.md), horizontalAlignment = Alignment.CenterHorizontally) {
        KEYS.chunked(3).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(DS.Spacing.xl)) {
                row.forEach { (digit, letters) ->
                    val source = remember { MutableInteractionSource() }
                    val pressed by source.collectIsPressedAsState()
                    Column(
                        Modifier
                            .size(72.dp)
                            .background(if (pressed) DS.Palette.hairline else DS.Palette.fill, CircleShape)
                            .combinedClickable(
                                interactionSource = source,
                                indication = null,
                                onClick = {
                                    haptics.selection()
                                    onKey(digit)
                                },
                                onLongClick = if (digit == "0" && onLongZero != null) ({ onLongZero() }) else null,
                            ),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center,
                    ) {
                        Text(digit, style = TextStyles.system(30), color = DS.Palette.ink)
                        Text(
                            letters.ifEmpty { " " },
                            style = TextStyles.system(9, FontWeight.SemiBold).copy(letterSpacing = 1.5.sp),
                            color = DS.Palette.ink,
                            modifier = Modifier.alpha(if (letters.isEmpty()) 0f else 1f),
                        )
                    }
                }
            }
        }
    }
}

private val KEYS = listOf(
    "1" to "", "2" to "ABC", "3" to "DEF", "4" to "GHI", "5" to "JKL", "6" to "MNO",
    "7" to "PQRS", "8" to "TUV", "9" to "WXYZ", "*" to "", "0" to "+", "#" to "",
)

/** The picked contact's name (null when it has none) and number, read through the picker's grant. */
private fun pickedPhone(context: Context, uri: Uri): Pair<String?, String>? = runCatching {
    val projection = arrayOf(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME, ContactsContract.CommonDataKinds.Phone.NUMBER)
    context.contentResolver.query(uri, projection, null, null, null)?.use { cursor ->
        if (!cursor.moveToFirst()) return@use null
        val name = cursor.getString(0)?.takeIf { it.isNotBlank() }
        val number = cursor.getString(1) ?: return@use null
        name to number
    }
}.getOrNull()
