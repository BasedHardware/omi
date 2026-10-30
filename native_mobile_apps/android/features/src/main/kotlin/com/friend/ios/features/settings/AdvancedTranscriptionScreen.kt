package com.friend.ios.features.settings

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.network.customstt.CustomSTTConfig
import com.friend.ios.network.customstt.CustomSTTProvider
import com.friend.ios.service.LocalCaptureStore
import com.friend.ios.service.LocalCustomSTTSettings
import com.friend.ios.service.LocalSettingsStore

/**
 * Port of `AdvancedTranscriptionScreen.swift`. Listening > Advanced transcription (Flutter
 * `transcription_settings_page`, "Cloud provider"): your own speech-to-text service with its key,
 * model, language and endpoint. Omi is the default; the phone's own recognizer stays the switch in
 * Listening (there is no Whisper model to download).
 */
@Composable
fun AdvancedTranscriptionScreen(onBack: () -> Unit) {
    val customSTT = LocalCustomSTTSettings.current
    val settings = LocalSettingsStore.current
    val capture = LocalCaptureStore.current
    val saved = customSTT.config
    var provider by rememberSaveable { mutableStateOf(saved?.provider?.rawValue) }
    var apiKey by rememberSaveable { mutableStateOf(saved?.apiKey.orEmpty()) }
    var model by rememberSaveable { mutableStateOf(saved?.model.orEmpty()) }
    var language by rememberSaveable { mutableStateOf(saved?.effectiveLanguage ?: "multi") }
    var url by rememberSaveable { mutableStateOf(saved?.url.orEmpty()) }
    var showsKey by rememberSaveable { mutableStateOf(false) }
    var notice by rememberSaveable { mutableStateOf<String?>(null) }
    var page by rememberSaveable { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { settings.loadLanguages() }
    val chosen = CustomSTTProvider.from(provider)
    val draft = chosen?.let {
        CustomSTTConfig(
            provider = it,
            apiKey = if (it.requiresAPIKey) apiKey.trim().ifEmpty { null } else null,
            model = model.ifEmpty { null },
            language = language,
            url = if (it.takesURL) url.trim().ifEmpty { null } else null,
        )
    }
    val hasChanges = draft != customSTT.config
    val apiKeyRequired = L("apiKeyRequired")
    val invalidURL = L("nativeCustomSttInvalidUrl")
    val savedText = L("saved")
    fun save() {
        if (draft != null && !draft.isComplete) {
            notice = if (draft.provider.requiresAPIKey && draft.apiKey.isNullOrEmpty()) apiKeyRequired else invalidURL
            return
        }
        customSTT.save(draft)
        notice = savedText
    }
    val omi = L("transcriptionSourceOmi")
    val auto = L("sttFilterAuto")
    SettingsSubPageHost(
        page = page,
        onClose = { page = null },
        base = {
            val canSave = !capture.isLive && hasChanges
            SettingsListPage(
                L("nativeAdvancedTranscription"),
                onBack,
                trailing = {
                    Text(
                        L("save"),
                        style = DS.Typography.body,
                        color = if (canSave) DS.Palette.ink else DS.Palette.inkDisabled,
                        modifier = Modifier.padding(end = DS.Spacing.sm).plainButton(enabled = canSave) { save() },
                    )
                },
            ) {
                val footer = if (chosen == null) L("speechToTextProviderDesc") else L("payYourSttProvider") + " " + L("nativeCustomSttFooter")
                section(footer = footer) {
                    row(onClick = { page = "provider" }, chevron = true) { SettingsLabeledContent(L("provider"), chosen?.displayName ?: omi) }
                }
                if (chosen != null) {
                    section(header = chosen.displayName) {
                        if (chosen.requiresAPIKey) {
                            row {
                                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                    SettingsTextField(
                                        apiKey, { apiKey = it }, L("enterApiKey"), Modifier.weight(1f),
                                        secure = !showsKey, keyboardType = KeyboardType.Password,
                                    )
                                    SFImage(
                                        if (showsKey) "eye.slash" else "eye", Modifier.plainButton { showsKey = !showsKey }, tint = DS.Palette.agent,
                                        contentDescription = if (showsKey) L("hideApiKey") else L("showApiKey"),
                                    )
                                }
                            }
                            chosen.apiKeyURL?.let { link ->
                                val uri = LocalUriHandler.current
                                row(onClick = { runCatching { uri.openUri(link) } }) { Text(L("getApiKey"), style = DS.Typography.body, color = DS.Palette.agent) }
                            }
                        }
                        if (chosen.takesURL) {
                            row { SettingsTextField(url, { url = it }, chosen.defaultURL ?: L("endpointUrl"), Modifier.fillMaxWidth(), keyboardType = KeyboardType.Uri) }
                        }
                        chosen.models.singleOrNull()?.let { only -> row { SettingsLabeledContent(L("model"), only) } }
                        val languageName = if (language == "multi") auto else settings.languages.firstOrNull { it.code == language }?.name ?: language
                        row(onClick = { page = "language" }, chevron = true) { SettingsLabeledContent(L("transcriptionLanguage"), languageName) }
                    }
                }
                section(footer = L("nativeEngineNoDownload")) {
                    row { SettingsLabeledContent(L("onDeviceTranscription"), L("usingNativeIosSpeech")) }
                }
            }
        },
    ) { current ->
        if (current == "provider") {
            LanguagePickerPage(
                title = L("provider"),
                options = listOf("" to omi) + CustomSTTProvider.entries.map { it.rawValue to it.displayName },
                selected = provider.orEmpty(),
                onBack = { page = null },
            ) { raw ->
                page = null
                if (raw != provider.orEmpty()) {
                    provider = raw.ifEmpty { null }
                    model = ""
                }
            }
        } else {
            LanguagePickerPage(
                title = L("transcriptionLanguage"),
                options = listOf("multi" to auto) + settings.languages.map { it.code to it.name },
                selected = language,
                onBack = { page = null },
            ) { code ->
                page = null
                language = code
            }
        }
    }
    notice?.let { title -> OmiAlert(title, listOf(DialogButton(L("ok"), DialogButton.Role.Cancel)), onDismiss = { notice = null }) }
}

/** A plain settings text field (`TextField` / `SecureField` in a `Section`). */
@Composable
private fun SettingsTextField(
    value: String,
    onChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    secure: Boolean = false,
    keyboardType: KeyboardType = KeyboardType.Text,
) {
    Box(modifier) {
        if (value.isEmpty()) Text(placeholder, style = DS.Typography.body, color = DS.Palette.inkTertiary, maxLines = 1)
        BasicTextField(
            value = value,
            onValueChange = onChange,
            singleLine = true,
            textStyle = DS.Typography.body.copy(color = DS.Palette.ink),
            cursorBrush = SolidColor(DS.Palette.agent),
            visualTransformation = if (secure) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(keyboardType = keyboardType, autoCorrectEnabled = false),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
