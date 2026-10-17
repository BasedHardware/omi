package com.friend.ios.features.settings

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import com.friend.ios.design.ContextMenuBox
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.SFImage
import com.friend.ios.design.plainButton
import com.friend.ios.design.rememberHaptics
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiPickerRow
import com.friend.ios.features.components.OmiToggleRow
import com.friend.ios.service.LocalCaptureStore
import com.friend.ios.service.stores.CaptureStore
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.detectsLanguages
import com.friend.ios.service.stores.loadLanguageDetection
import com.friend.ios.service.stores.setLanguageDetection
import kotlinx.coroutines.launch
import com.friend.ios.service.stores.process
import com.friend.ios.service.stores.phoneRecordings
import com.friend.ios.service.LocalSyncStore
import com.friend.ios.features.components.PendingRecordingRow
import com.friend.ios.features.components.OmiListBuilder
import com.friend.ios.features.components.AudioClipPlayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.runtime.DisposableEffect

/**
 * Port of `CaptureSettingsScreen.swift`. How Omi helps > Listening: the language you speak, words
 * and names to recognize, when a conversation ends, recordings still on the phone; the speech
 * model, on-device transcription, Transcribe later and the transcription log sit one level down
 * in Advanced.
 */
@Composable
fun CaptureSettingsScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val navigator = LocalSettingsNavigator.current
    val capture = LocalCaptureStore.current
    val scope = rememberCoroutineScope()
    var detectsLanguages by remember { mutableStateOf(settings.detectsLanguages) }
    var pickingLanguage by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(Unit) { settings.loadVocabulary() }
    LaunchedEffect(Unit) { settings.loadLanguages() }
    LaunchedEffect(Unit) { detectsLanguages = settings.loadLanguageDetection() }

    SettingsSubPageHost(
        page = if (pickingLanguage) Unit else null,
        onClose = { pickingLanguage = false },
        base = {
            val spoken = settings.spokenLanguage ?: "en"
            val languageName = settings.languages.firstOrNull { it.code == spoken }?.name
            val icon = OmiListMetrics.iconSeparatorInset
            val vocabularyCount = settings.vocabulary.takeIf { it.isNotEmpty() }?.size?.toString()
            val timeouts = CaptureStore.conversationTimeouts.associateWith { timeoutLabel(it) }
            SettingsListPage(L("nativeSettingsListening"), onBack) {
                section(footer = L("nativeDetectLanguagesFooter")) {
                    // `.pickerStyle(.navigationLink)`: the value and a chevron, the list one level down.
                    row(onClick = { pickingLanguage = true }, chevron = true, separatorInset = icon) {
                        SettingsRowLabel(L("nativeSpokenLanguage"), "globe", value = languageName)
                    }
                    row(separatorInset = icon) {
                        OmiToggleRow(detectsLanguages, { value ->
                            detectsLanguages = value
                            scope.launch { if (!settings.setLanguageDetection(value)) detectsLanguages = !value }
                        }) { SettingsRowLabel(L("nativeDetectLanguages"), "character.bubble") }
                    }
                }
                section(footer = L("nativeConversationTimeoutFooter")) {
                    row(onClick = { navigator.push(SettingsTopic.Vocabulary) }, chevron = true, separatorInset = icon) {
                        SettingsRowLabel(L("nativeSettingsVocabulary"), "text.book.closed", value = vocabularyCount)
                    }
                    row(separatorInset = icon) {
                        OmiPickerRow(CaptureStore.conversationTimeouts, capture.conversationTimeout, { timeouts.getValue(it) }, { capture.conversationTimeout = it }) {
                            SettingsRowLabel(L("nativeSettingsEndsAfter"), "timer")
                        }
                    }
                }
                phoneRecordingsSection()
                section {
                    row(onClick = { navigator.push(SettingsTopic.ListeningAdvanced) }, chevron = true, separatorInset = icon) {
                        SettingsRowLabel(L("nativeSettingsAdvanced"), "slider.horizontal.3")
                    }
                }
            }
        },
    ) {
        LanguagePickerPage(
            title = L("nativeSpokenLanguage"),
            options = settings.languages.map { it.code to it.name },
            selected = settings.spokenLanguage ?: "en",
            onBack = { pickingLanguage = false },
        ) { code ->
            pickingLanguage = false
            scope.launch { settings.setSpokenLanguage(code) }
        }
    }
}

/** `Picker(...).pickerStyle(.navigationLink)`'s pushed list: one row per choice, a check on the chosen one. */
@Composable
fun LanguagePickerPage(title: String, options: List<Pair<String, String>>, selected: String, onBack: () -> Unit, onSelect: (String) -> Unit) {
    val haptics = rememberHaptics()
    SettingsListPage(title, onBack) {
        section {
            options.forEach { (code, name) ->
                row(key = code, onClick = {
                    haptics.selection()
                    onSelect(code)
                }) {
                    Text(name, style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.weight(1f))
                    if (code == selected) SFImage("checkmark", weight = FontWeight.SemiBold, tint = DS.Palette.agent)
                }
            }
        }
    }
}

/** `CaptureSettingsScreen.timeoutLabel`. */
@Composable
fun timeoutLabel(seconds: Int): String = when (seconds) {
    120 -> L("timeout2Minutes")
    300 -> L("timeout5Minutes")
    600 -> L("timeout10Minutes")
    1800 -> L("timeout30Minutes")
    -1 -> L("timeout4Hours")
    else -> {
        val hours = seconds / 3600
        val minutes = (seconds % 3600) / 60
        listOfNotNull(hours.takeIf { it > 0 }?.let { "$it h" }, minutes.takeIf { it > 0 }?.let { "$it min" }).joinToString(" ")
    }
}

/** Listening > Advanced: which speech model the server uses, transcribing on the phone instead, Transcribe later, and the transcription log. */
@Composable
fun ListeningAdvancedScreen(onBack: () -> Unit) {
    val capture = LocalCaptureStore.current
    var page by rememberSaveable { mutableStateOf<String?>(null) }
    SettingsSubPageHost(
        page = page,
        onClose = { page = null },
        base = {
            val omi = L("nativeSpeechModelOmi")
            val parakeet = L("nativeSpeechModelParakeet")
            SettingsListPage(L("nativeSettingsAdvanced"), onBack) {
                // Android: the toggle stays disabled where the phone has no on-device recognizer
                // (before Android 13, or no offline model), with the iOS line that says so.
                val onDeviceFooter = L("nativeOnDeviceTranscriptionFooter") + " " + L("nativeSpeechModelFooter") +
                    if (capture.canTranscribeOnDevice) "" else "\n\n" + L("nativeSpeechUnavailable")
                section(footer = onDeviceFooter) {
                    row {
                        // `.disabled(capture.isLive || capture.transcribesOnDevice)`: the value, dimmed, no menu.
                        val pickerEnabled = !capture.isLive && !capture.transcribesOnDevice
                        Box(Modifier.alpha(if (pickerEnabled) 1f else 0.4f)) {
                            if (pickerEnabled) {
                                OmiPickerRow(listOf(false, true), capture.usesParakeet, { if (it) parakeet else omi }, { capture.usesParakeet = it }) {
                                    Text(L("nativeSpeechModel"), style = DS.Typography.body, color = DS.Palette.ink)
                                }
                            } else {
                                SettingsLabeledContent(L("nativeSpeechModel"), if (capture.usesParakeet) parakeet else omi)
                            }
                        }
                    }
                    row {
                        OmiToggleRow(
                            capture.transcribesOnDevice, { capture.transcribesOnDevice = it },
                            enabled = !capture.isLive && (capture.canTranscribeOnDevice || capture.transcribesOnDevice),
                        ) {
                            Text(L("nativeOnDeviceTranscription"), style = DS.Typography.body, color = DS.Palette.ink)
                        }
                    }
                }
                section(footer = L("nativeTranscribeLaterFooter")) {
                    row {
                        OmiToggleRow(capture.transcribesLater, { capture.transcribesLater = it }, enabled = !capture.isLive) {
                            Text(L("nativeTranscribeLater"), style = DS.Typography.body, color = DS.Palette.ink)
                        }
                    }
                }
                section(footer = L("nativeTranscriptionLogFooter")) {
                    row(onClick = { page = "advancedTranscription" }, chevron = true) { SettingsButtonText(L("nativeAdvancedTranscription")) }
                    row(onClick = { page = "log" }, chevron = true) { SettingsButtonText(L("nativeTranscriptionLog")) }
                }
            }
        },
    ) { current ->
        when (current) {
            "advancedTranscription" -> AdvancedTranscriptionScreen { page = null }
            else -> DebugLogScreen(source = "stt") { page = null }
        }
    }
}

/** Listening > Words and names: the words Omi should recognize; add on top, long press to remove. */
@Composable
fun VocabularyScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val scope = rememberCoroutineScope()
    var newWord by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(Unit) { settings.loadVocabulary() }
    fun add() {
        val word = newWord
        newWord = ""
        scope.launch { settings.addWord(word) }
    }
    SettingsListPage(L("nativeSettingsVocabulary"), onBack) {
        section(footer = L("nativeVocabularyFooter")) {
            row {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f)) {
                        if (newWord.isEmpty()) Text(L("nativeAddWord"), style = DS.Typography.body, color = DS.Palette.inkTertiary, maxLines = 1)
                        BasicTextField(
                            value = newWord,
                            onValueChange = { newWord = it },
                            singleLine = true,
                            textStyle = DS.Typography.body.copy(color = DS.Palette.ink),
                            cursorBrush = SolidColor(DS.Palette.agent),
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                            keyboardActions = KeyboardActions(onDone = { add() }),
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    if (newWord.isNotBlank()) {
                        Text(L("nativeAdd"), style = DS.Typography.body.copy(fontWeight = FontWeight.SemiBold), color = DS.Palette.agent, modifier = Modifier.plainButton { add() })
                    }
                }
            }
        }
        if (settings.vocabulary.isNotEmpty()) {
            section {
                val delete = L("delete")
                settings.vocabulary.forEachIndexed { index, word ->
                    row(key = word) {
                        // `.onDelete` (swipe) on iOS; a long press offers Delete here.
                        ContextMenuBox({ listOf(MenuSection(items = listOf(MenuItem(delete, "trash", destructive = true) { scope.launch { settings.removeWords(setOf(index)) } }))) }, Modifier.fillMaxWidth()) {
                            Text(word, style = DS.Typography.body, color = DS.Palette.ink, modifier = Modifier.fillMaxWidth())
                        }
                    }
                }
            }
        }
    }
}

/**
 * `PhoneRecordingsSection`: recordings the phone's microphone kept (offline, or Transcribe later)
 * that the backend does not have yet: play, share, process now, delete. Hidden while there are none.
 */
@Composable
private fun OmiListBuilder.phoneRecordingsSection() {
    val sync = LocalSyncStore.current
    val recordings = sync.phoneRecordings
    if (recordings.isEmpty()) return
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val player = remember { AudioClipPlayer(context) }
    DisposableEffect(Unit) { onDispose { player.stop() } }
    section(header = L("nativeRecordingsOnPhone"), footer = L("nativeRecordingsOnPhoneFooter")) {
        recordings.forEach { recording ->
            row(key = recording.filename) {
                PendingRecordingRow(recording, player)
            }
        }
    }
}
