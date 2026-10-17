package com.friend.ios.features.settings

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.friend.ios.core.models.AppDataAccess
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.plainButton
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiSectionBuilder
import com.friend.ios.features.components.OmiToggleRow
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.ProfileStore
import com.friend.ios.service.stores.makeProfileStore
import kotlinx.coroutines.launch

/**
 * Port of `PrivacyScreen.swift`. App > Privacy & data: what is kept (audio in the cloud, on this
 * phone), location and Android permissions, which apps see what, and exporting everything.
 * Importing history and deleting all memories live in Memory.
 */
@Composable
fun PrivacyScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val navigator = LocalSettingsNavigator.current
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    val scope = rememberCoroutineScope()
    val profile = remember { settings.makeProfileStore() }
    var confirmAudioOnPhone by remember { mutableStateOf(false) }
    var location by remember { mutableStateOf(locationAccess(context)) }
    val request = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        location = locationAccess(context, asked = true)
    }
    LaunchedEffect(Unit) { settings.loadPrivacy() }
    LaunchedEffect(Unit) { profile.loadAppsWithAccess() }
    // The temporary file goes once the screen does (leaving Privacy & data).
    DisposableEffect(Unit) { onDispose { profile.finishExport() } }

    val icon = OmiListMetrics.iconSeparatorInset
    val storeTitle = L("nativeStoreRecordings")
    val phoneTitle = L("nativeSettingsAudioOnPhone")
    val locationTitle = L("location")
    val allow = L("nativeAllow")
    val locationOn = L("nativeLocationOn")
    val locationOff = L("nativeLocationOff")
    val permissions = L("nativePermissions")
    val accessTitle = L("nativeSettingsAppAccess")
    val privacyPolicy = L("privacyPolicy")
    val terms = L("termsOfService")
    SettingsListPage(L("nativeSettingsPrivacy"), onBack) {
        section(footer = L("nativeStoreRecordingsFooter")) {
            row(separatorInset = icon) {
                OmiToggleRow(settings.storesRecordings, { value -> scope.launch { settings.setStoresRecordings(value) } }) {
                    SettingsRowLabel(storeTitle, "icloud")
                }
            }
            row(separatorInset = icon) {
                OmiToggleRow(profile.storesAudioOnPhone, { value -> if (value) confirmAudioOnPhone = true else profile.storesAudioOnPhone = false }) {
                    // "Keep audio on this phone": the iOS row's wording, the phone's glyph.
                    SettingsRowLabel(phoneTitle, "iphone")
                }
            }
        }
        section(footer = L("locationAccessDesc")) {
            // Where conversations happen (while in use). Never asked: the system prompt; denied: the Settings app.
            row(separatorInset = icon) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    SettingsRowLabel(locationTitle, "location", Modifier.weight(1f))
                    when (location) {
                        LocationAccess.NotDetermined -> OmiPillButton(allow) {
                            request.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
                        }
                        else -> Text(
                            if (location == LocationAccess.Allowed) locationOn else locationOff,
                            style = DS.Typography.body,
                            color = DS.Palette.inkSecondary,
                            modifier = Modifier.plainButton { openAppSettings(context) },
                        )
                    }
                }
            }
            row(onClick = { openAppSettings(context) }, separatorInset = icon) {
                SettingsRowLabel(permissions, "checkmark.shield", Modifier.weight(1f))
                SettingsExternalArrow()
            }
        }
        section {
            row(onClick = { navigator.push(SettingsRoute.AppAccess) }, chevron = true, separatorInset = icon) {
                SettingsRowLabel(accessTitle, "square.grid.2x2", value = profile.appsWithAccess?.size?.toString())
            }
            exportDataRow(profile, context)
        }
        section {
            row(onClick = { uriHandler.openUri("https://www.omi.me/pages/privacy") }) { SettingsButtonText(privacyPolicy) }
            row(onClick = { uriHandler.openUri("https://www.omi.me/pages/terms-of-service") }) { SettingsButtonText(terms) }
        }
    }
    if (confirmAudioOnPhone) {
        OmiAlert(
            L("privacyNotice"),
            listOf(DialogButton(L("cancel"), DialogButton.Role.Cancel), DialogButton(L("nativeKeepOnPhone")) { profile.storesAudioOnPhone = true }),
            onDismiss = { confirmAudioOnPhone = false },
            message = L("nativeRecordingsMayCaptureOthers"),
        )
    }
}

/** "Conversations, memories · when a conversation is created" (Flutter's access line). */
@Composable
fun accessSummary(app: AppDataAccess): String {
    val reads = listOfNotNull(if (app.readsConversations) L("conversations") else null, if (app.readsMemories) L("memories") else null)
    val trigger = when (app.trigger) {
        "memory_creation" -> L("nativeTriggerConversationCreated")
        "transcript_processed" -> L("nativeTriggerTranscript")
        "audio_bytes" -> L("nativeTriggerAudio")
        else -> null
    }
    val parts = listOfNotNull(reads.takeIf { it.isNotEmpty() }?.joinToString(", "), trigger)
    return if (parts.isEmpty()) L("nativeNoSpecificAccess") else parts.joinToString(" · ")
}

/** Privacy & data > Which apps see what: installed apps that read your conversations or memories, and when they run. */
@Composable
fun AppAccessScreen(onBack: () -> Unit) {
    val settings = LocalSettingsStore.current
    val profile = remember { settings.makeProfileStore() }
    LaunchedEffect(Unit) { profile.loadAppsWithAccess() }
    val apps = profile.appsWithAccess
    val none = L("nativeNoAppsAccessData")
    val summaries = apps.orEmpty().associate { it.id to accessSummary(it) }
    SettingsListPage(L("nativeSettingsAppAccess"), onBack) {
        section(footer = L("nativeAppAccessFooter")) {
            if (apps == null) {
                row { Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { OmiProgress() } }
            } else {
                if (apps.isEmpty()) row { Text(none, style = DS.Typography.body, color = DS.Palette.inkSecondary) }
                apps.forEach { app ->
                    row(key = app.id, separatorInset = 60.dp) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
                            AppIcon(app.imageURL, app.name, 32.dp)
                            Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                                Text(app.name, style = DS.Typography.body, color = DS.Palette.ink)
                                Text(summaries[app.id].orEmpty(), style = DS.Typography.caption, color = DS.Palette.inkSecondary)
                            }
                        }
                    }
                }
            }
        }
    }
}

/** Export all data: downloads one JSON file with everything Omi stores, then the share sheet. */
@Composable
private fun OmiSectionBuilder.exportDataRow(store: ProfileStore, context: Context) {
    when (val phase = store.exportPhase) {
        ProfileStore.ExportPhase.Idle, ProfileStore.ExportPhase.Failed -> row(onClick = { store.export() }, separatorInset = OmiListMetrics.iconSeparatorInset) {
            Column(verticalArrangement = Arrangement.spacedBy(DS.Spacing.xxs)) {
                SettingsRowLabel(L("nativeSettingsExport"), "square.and.arrow.up")
                if (phase == ProfileStore.ExportPhase.Failed) SettingsCaption(L("exportFailedTryAgain"), DS.Palette.live)
            }
        }
        ProfileStore.ExportPhase.Exporting -> row(separatorInset = OmiListMetrics.iconSeparatorInset) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                OmiProgress()
                Spacer(Modifier.width(DS.Spacing.sm))
                Text(L("exportingAllData"), style = DS.Typography.caption, color = DS.Palette.inkSecondary, modifier = Modifier.weight(1f))
                Text(L("cancel"), style = DS.Typography.body, color = DS.Palette.agent, modifier = Modifier.plainButton { store.cancelExport() })
            }
        }
        is ProfileStore.ExportPhase.Ready -> row(onClick = { share(context, phase.file) }, separatorInset = OmiListMetrics.iconSeparatorInset) {
            SettingsRowLabel(L("nativeShareExport"), "square.and.arrow.up", tint = DS.Palette.agent)
        }
    }
}

/** `ShareLink(item: url)`: the system share sheet with the export file (FileProvider in the app manifest). */
private fun share(context: Context, file: java.io.File) {
    runCatching {
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.omi.files", file)
        val send = Intent(Intent.ACTION_SEND).setType("application/json").putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        context.startActivity(Intent.createChooser(send, null).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}

/** `LocationStore.access`: never asked, allowed, or denied. */
private enum class LocationAccess { NotDetermined, Allowed, Denied }

private const val LOCATION_ASKED_KEY = "omi.location.asked"

private fun locationAccess(context: Context, asked: Boolean = false): LocationAccess {
    val prefs = context.getSharedPreferences("omi.settings", Context.MODE_PRIVATE)
    if (asked) prefs.edit().putBoolean(LOCATION_ASKED_KEY, true).apply()
    val granted = listOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
        .any { ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED }
    return when {
        granted -> LocationAccess.Allowed
        !prefs.getBoolean(LOCATION_ASKED_KEY, false) -> LocationAccess.NotDetermined
        else -> LocationAccess.Denied
    }
}

/** `UIApplication.openSettingsURLString`: the app's page in the system settings. */
internal fun openAppSettings(context: Context) {
    val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
    runCatching { context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
}
