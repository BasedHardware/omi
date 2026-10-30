package com.friend.ios.features.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.DeveloperKey
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiPrimaryButton
import com.friend.ios.design.SFImage
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.DebugLaunch
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiSectionBuilder
import com.friend.ios.service.LocalDeveloperStore
import kotlinx.coroutines.launch

/**
 * Port of `ConnectAIScreen.swift`. Connections > Connect your AI: Claude, ChatGPT or any other MCP
 * client reads what Omi knows. Claude and ChatGPT sign in to Omi themselves (no key to copy);
 * other assistants get their own MCP key, created right here. The raw API and MCP keys stay in
 * Developer.
 */
@Composable
fun ConnectAIScreen(onBack: () -> Unit) {
    val developer = LocalDeveloperStore.current
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val haptics = rememberHaptics()
    val scope = rememberCoroutineScope()
    /** `omiConnectAITarget claude|chatGPT|other` (Debug) opens on that assistant. */
    var target by rememberSaveable { mutableStateOf(ConnectTarget.from(DebugLaunch.string("omiConnectAITarget")) ?: ConnectTarget.Claude) }
    var copied by remember { mutableStateOf<String?>(null) }
    var isCreating by remember { mutableStateOf(false) }
    var createFailed by remember { mutableStateOf(false) }
    LaunchedEffect(target) { copied = null }
    // The secret is shown once: it does not stay in memory after the screen.
    DisposableEffect(Unit) { onDispose { if (developer.createdKeyKind == DeveloperKey.Kind.Mcp) developer.createdKey = null } }
    val createdSecret = if (developer.createdKeyKind == DeveloperKey.Kind.Mcp) developer.createdKey?.secret else null
    val keyName = L("nativeConnectAIKeyName")
    fun createKey() = scope.launch {
        isCreating = true
        createFailed = !developer.createKey(DeveloperKey.Kind.Mcp, keyName)
        isCreating = false
    }
    LaunchedEffect(Unit) {
        // omiConnectAICreateKey (Debug, with the "other" target): creates the key right away.
        if (DebugLaunch.flag("omiConnectAICreateKey") && target == ConnectTarget.Other && createdSecret == null) createKey()
    }
    fun copy(text: String, id: String) {
        copyToClipboard(context, text)
        haptics.success()
        copied = id
    }
    val address = developer.mcpServerURL
    val titles = ConnectTarget.entries.map { it.title() }
    val intro = L("nativeConnectAIIntro")
    SettingsListPage(L("nativeConnectAI"), onBack) {
        section {
            plainRow(inset = DS.Spacing.lg) { Text(intro, style = DS.Typography.callout, color = DS.Palette.inkSecondary) }
            plainRow { Row(Modifier.padding(top = DS.Spacing.lg)) { OmiSegmentedPicker(titles, target.ordinal, textStyle = com.friend.ios.design.TextStyles.subheadline) { target = ConnectTarget.entries[it] } } }
        }
        section(header = L("nativeConnectAISteps"), footer = if (target == ConnectTarget.Other) L("nativeConnectAIKeyFooter") else null) {
            steps(target, address, createdSecret, copied, developer::mcpConfig, ::copy)
        }
        section {
            plainRow {
                when (target) {
                    ConnectTarget.Claude -> OmiPrimaryButton(L("nativeConnectAIOpenClaude")) { uriHandler.openUri(CLAUDE_URL) }
                    ConnectTarget.ChatGPT -> OmiPrimaryButton(L("nativeConnectAIOpenChatGPT")) { uriHandler.openUri(CHATGPT_URL) }
                    ConnectTarget.Other -> if (createdSecret != null) {
                        OmiPrimaryButton(if (copied == "config") L("copied") else L("nativeConnectAICopySetup")) { copy(developer.mcpConfig(createdSecret), "config") }
                    } else {
                        OmiPrimaryButton(L("nativeConnectAICreateKey"), enabled = !isCreating) { createKey() }
                    }
                }
            }
        }
    }
    if (createFailed) OmiAlert(L("nativeConnectAIFailed"), listOf(DialogButton(L("ok"), DialogButton.Role.Cancel)), onDismiss = { createFailed = false })
}

enum class ConnectTarget(val rawValue: String) {
    Claude("claude"), ChatGPT("chatGPT"), Other("other");

    @Composable
    fun title(): String = when (this) {
        Claude -> "Claude"
        ChatGPT -> "ChatGPT"
        Other -> L("nativeConnectAIOther")
    }

    companion object {
        fun from(raw: String?): ConnectTarget? = entries.firstOrNull { it.rawValue == raw }
    }
}

/** Claude's connector settings (the app opens it when installed). */
private const val CLAUDE_URL = "https://claude.ai/settings/connectors"

/** ChatGPT's apps settings. */
private const val CHATGPT_URL = "https://chatgpt.com/#settings/Connectors"

@Composable
private fun OmiSectionBuilder.steps(
    target: ConnectTarget,
    address: String,
    secret: String?,
    copied: String?,
    config: (String) -> String,
    copy: (String, String) -> Unit,
) {
    val addressTitle = L("nativeConnectAIAddress")
    when (target) {
        ConnectTarget.Claude -> {
            step(1, L("nativeConnectAIClaudeStep1"))
            copyRow(addressTitle, address, "address", copied, copy = copy)
            step(2, L("nativeConnectAIClaudeStep2"))
            step(3, L("nativeConnectAIClaudeStep3"))
        }
        ConnectTarget.ChatGPT -> {
            step(1, L("nativeConnectAIChatGPTStep1"))
            step(2, L("nativeConnectAIChatGPTStep2"))
            step(3, L("nativeConnectAIChatGPTStep3"))
        }
        ConnectTarget.Other -> {
            step(1, L("nativeConnectAIOtherStep1"))
            if (secret != null) copyRow(L("nativeConnectAIKey"), secret, "key", copied, copy = copy)
            step(2, L("nativeConnectAIOtherStep2"))
            copyRow(addressTitle, address, "address", copied, copy = copy)
            if (secret != null) copyRow(L("nativeConnectAISetup"), config(secret), "config", copied, shown = "JSON", copy = copy)
        }
    }
}

/** A numbered step: the number in quiet gray, then one sentence. */
private fun OmiSectionBuilder.step(number: Int, text: String) {
    row(key = "step$number") {
        Row(Modifier.padding(vertical = DS.Spacing.xxs), horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            Text("$number", style = DS.Typography.body.copy(fontFeatureSettings = "tnum"), color = DS.Palette.inkSecondary, modifier = Modifier.width(18.dp))
            Text(text, style = DS.Typography.body, color = DS.Palette.ink)
        }
    }
}

/** A value to copy: its name, the value (shortened in the middle) and a copy glyph. */
private fun OmiSectionBuilder.copyRow(title: String, value: String, id: String, copied: String?, shown: String? = null, copy: (String, String) -> Unit) {
    row(key = "copy$id", onClick = { copy(value, id) }, separatorInset = 16.dp + 18.dp + DS.Spacing.md) {
        Row(Modifier.fillMaxWidth().padding(start = 18.dp + DS.Spacing.md), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            Text(title, style = DS.Typography.body, color = DS.Palette.ink)
            Text(
                shown ?: value,
                style = DS.Typography.callout.copy(fontFamily = FontFamily.Monospace),
                color = DS.Palette.inkSecondary,
                maxLines = 1,
                overflow = TextOverflow.MiddleEllipsis,
                textAlign = androidx.compose.ui.text.style.TextAlign.End,
                modifier = Modifier.weight(1f),
            )
            SFImage(if (copied == id) "checkmark" else "doc.on.doc", size = 15.sp, tint = DS.Palette.inkSecondary)
        }
    }
}
