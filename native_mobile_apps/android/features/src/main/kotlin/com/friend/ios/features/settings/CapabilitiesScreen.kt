package com.friend.ios.features.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.friend.ios.core.models.Integration
import com.friend.ios.design.ContinuousRoundedShape
import com.friend.ios.design.DS
import com.friend.ios.design.L
import com.friend.ios.design.MenuItem
import com.friend.ios.design.MenuSection
import com.friend.ios.design.OmiMenu
import com.friend.ios.design.OmiPillButton
import com.friend.ios.design.OmiProgress
import com.friend.ios.design.SFImage
import com.friend.ios.features.components.DialogButton
import com.friend.ios.features.components.OmiAlert
import com.friend.ios.features.components.OmiListMetrics
import com.friend.ios.features.components.OmiPickerRow
import com.friend.ios.features.components.OmiToggleRow
import com.friend.ios.features.components.rememberConnectIntegration
import com.friend.ios.network.endpoints.TaskAppLevel
import com.friend.ios.network.endpoints.TaskAppOption
import com.friend.ios.service.LocalAppleHealthStore
import com.friend.ios.service.LocalCapabilitiesStore
import com.friend.ios.service.LocalSettingsStore
import com.friend.ios.service.stores.AppleHealthStore
import com.friend.ios.service.stores.CapabilitiesStore
import com.friend.ios.service.stores.TaskAppSettingsStore
import com.friend.ios.service.stores.makeTaskAppSettingsStore
import kotlinx.coroutines.launch

/**
 * Port of `CapabilitiesScreen.swift`. Connections > Apps & integrations: what is connected
 * (calendar, mail, task apps), what can be added, the Omi apps you installed, and the app store.
 * Apple Health is Health Connect on Android (its rows hide while unavailable, as on iOS); Apple
 * Reminders has no Android counterpart (docs/PLAN.md platform mapping).
 */
@Composable
fun CapabilitiesScreen(onBack: () -> Unit) {
    val store = LocalCapabilitiesStore.current
    val navigator = LocalSettingsNavigator.current
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { store.load() }
    LaunchedEffect(Unit) { store.loadApps() }
    val connect = rememberConnectIntegration()
    // Reminders (RemindersSyncStore) has no Android counterpart.
    val health = LocalAppleHealthStore.current
    LaunchedEffect(Unit) { health.load() }
    val connected = store.integrations.filter { it.isConnected }
    val available = store.integrations.filter { !it.isConnected }
    val browseTitle = L("nativeBrowseApps")
    SettingsListPage(L("nativeSettingsApps"), onBack) {
        if (connected.isNotEmpty() || health.isConnected) {
            section(header = L("nativeConnected")) {
                if (health.isAvailable && health.isConnected) {
                    row(key = "apple_health", onClick = { navigator.push(SettingsTopic.AppleHealth) }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
                        HealthRow(health)
                    }
                }
                connected.forEach { integration ->
                    row(
                        key = integration.id,
                        onClick = taskAppRoute(integration)?.let { route -> { navigator.push(route) } },
                        chevron = taskAppRoute(integration) != null,
                        separatorInset = OmiListMetrics.iconSeparatorInset,
                    ) { IntegrationRow(integration, store, connect) }
                }
            }
        }
        if (available.isNotEmpty() || (health.isAvailable && !health.isConnected)) {
            section(header = L("nativeSettingsAddIntegration"), footer = L("nativeCapabilitiesOnboardingReason")) {
                available.forEach { integration ->
                    row(key = integration.id, separatorInset = OmiListMetrics.iconSeparatorInset) { IntegrationRow(integration, store, connect) }
                }
                if (health.isAvailable && !health.isConnected) {
                    row(key = "apple_health", separatorInset = OmiListMetrics.iconSeparatorInset) { HealthRow(health) }
                }
            }
        }
        if (store.installedApps.isNotEmpty()) {
            section(header = L("nativeSettingsInstalledApps")) {
                store.installedApps.forEach { app -> row(key = app.id, separatorInset = 76.dp) { AppRow(app) } }
            }
        }
        section(footer = L("nativeOmiAppsFooter")) {
            row(onClick = { navigator.push(SettingsTopic.BrowseApps) }, chevron = true, separatorInset = OmiListMetrics.iconSeparatorInset) {
                SettingsRowLabel(browseTitle, "sparkle.magnifyingglass")
            }
        }
    }
}

/** Connected: opens its page (sync, disconnect). Not yet: Connect asks Health Connect right here. */
@Composable
private fun HealthRow(health: AppleHealthStore) {
    val scope = rememberCoroutineScope()
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            AppleHealthIcon(28.dp)
            Text(HEALTH_CONNECT, style = DS.Typography.body, color = DS.Palette.ink)
        }
        when {
            health.isConnected -> Unit
            health.phase == AppleHealthStore.Phase.Connecting -> OmiProgress()
            else -> OmiPillButton(L("nativeConnect"), prominent = false) { scope.launch { health.connect() } }
        }
    }
    if (health.notice == AppleHealthStore.Notice.Denied) {
        OmiAlert(
            L("appleHealthDeniedTitle"), listOf(DialogButton(L("ok"), DialogButton.Role.Cancel)),
            onDismiss = { health.notice = null }, message = L("appleHealthDeniedBody"),
        )
    }
}

/** One integration on one line: logo, name, and Connect, or the menu (and the task app's settings) once connected. */
@Composable
private fun IntegrationRow(integration: Integration, store: CapabilitiesStore, connect: (Integration) -> Unit) {
    val scope = rememberCoroutineScope()
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DS.Spacing.md)) {
            IntegrationLogo(integration.id)
            Text(capabilityName(integration.id), style = DS.Typography.body, color = DS.Palette.ink)
        }
        when {
            // A connected task app opens its settings (the row's chevron).
            integration.isConnected && taskAppRoute(integration) != null -> Unit
            store.connecting == integration.id -> OmiProgress()
            integration.isConnected -> OmiMenu(
                listOf(MenuSection(items = listOf(MenuItem(L("nativeDisconnect"), destructive = true) { scope.launch { store.disconnect(integration) } }))),
                contentDescription = L("nativeMore"),
            ) {
                Box(Modifier.size(32.dp), contentAlignment = Alignment.Center) { SFImage("ellipsis", tint = DS.Palette.inkSecondary) }
            }
            else -> OmiPillButton(L("nativeConnect"), prominent = false) { connect(integration) }
        }
    }
}

/** A brand logo on white (logos are made for white), or a glyph for the ones without one. */
@Composable
private fun IntegrationLogo(id: String) {
    val shape = ContinuousRoundedShape(7.dp)
    Box(
        Modifier.size(28.dp).background(Color.White, shape).border(0.5.dp, DS.Palette.hairline.copy(alpha = 0.5f), shape),
        contentAlignment = Alignment.Center,
    ) {
        val logo = integrationLogo(id)
        if (logo != null) {
            androidx.compose.foundation.Image(
                androidx.compose.ui.res.painterResource(logo), null,
                Modifier.padding(5.dp).fillMaxSize(), contentScale = androidx.compose.ui.layout.ContentScale.Fit,
            )
        } else {
            SFImage(capabilityIcon(id), size = 15.sp, tint = DS.Palette.agent)
        }
    }
}

/** `OmiMedia.logo(key)`: the brand logos copied from omi-native's `Resources/Media`. */
fun integrationLogo(id: String): Int? = when (id) {
    "google_calendar" -> com.friend.ios.features.R.drawable.logo_google_calendar
    "gmail" -> com.friend.ios.features.R.drawable.logo_gmail
    "todoist" -> com.friend.ios.features.R.drawable.logo_todoist
    "asana" -> com.friend.ios.features.R.drawable.logo_asana
    "clickup" -> com.friend.ios.features.R.drawable.logo_clickup
    "google_tasks" -> com.friend.ios.features.R.drawable.logo_google_tasks
    else -> null
}

/** A connected task app's settings page. */
private fun taskAppRoute(integration: Integration): SettingsRoute? =
    if (integration.isConnected && integration.kind == Integration.Kind.TaskApp) SettingsRoute.TaskApp(integration.id) else null

/** `CapabilitiesList.name`. */
fun capabilityName(id: String): String = when (id) {
    "google_calendar" -> "Google Calendar"
    "gmail" -> "Gmail"
    "todoist" -> "Todoist"
    "asana" -> "Asana"
    "clickup" -> "ClickUp"
    "google_tasks" -> "Google Tasks"
    else -> id
}

/** `CapabilitiesList.icon`. */
fun capabilityIcon(id: String): String = when (id) {
    "google_calendar" -> "calendar"
    "gmail" -> "envelope"
    else -> "checklist"
}

/** `CapabilitiesList.message`: why the last Connect did not work. */
@Composable
fun capabilityFailureMessage(failure: CapabilitiesStore.ConnectFailure, name: String): String = when (failure) {
    CapabilitiesStore.ConnectFailure.NotConfigured -> L("nativeCapabilityNotConfigured", name)
    CapabilitiesStore.ConnectFailure.Offline -> L("nativeCapabilityOffline")
    CapabilitiesStore.ConnectFailure.Cancelled -> L("nativeCapabilityCancelled")
    CapabilitiesStore.ConnectFailure.Failed -> L("nativeCapabilityLoginFailed", name)
}

/**
 * Port of `TaskAppSettingsScreen.swift`: one connected task app (Flutter
 * `todoist/asana/clickup/google_tasks_settings_page`): whether new tasks go here, where in it
 * (Asana workspace and project, ClickUp team, space and list), disconnect.
 */
@Composable
fun TaskAppSettingsScreen(appID: String, onBack: () -> Unit) {
    val capabilities = LocalCapabilitiesStore.current
    val settingsStore = LocalSettingsStore.current
    val settings = remember(settingsStore) { settingsStore.makeTaskAppSettingsStore() }
    val scope = rememberCoroutineScope()
    var confirmsDisconnect by remember { mutableStateOf(false) }
    LaunchedEffect(appID) { settings.load(appID) }
    val name = capabilityName(appID)
    val disconnect = L("nativeDisconnect")
    val isDefault = settings.defaultApp == appID
    SettingsListPage(name, onBack) {
        val defaultTitle = L("nativeTaskAppDefault")
        section(footer = L("nativeTaskAppDefaultFooter")) {
            row {
                OmiToggleRow(isDefault, { on -> if (on) scope.launch { settings.makeDefault(appID) } }, enabled = !isDefault) {
                    Text(defaultTitle, style = DS.Typography.body, color = DS.Palette.ink)
                }
            }
        }
        val levels = TaskAppLevel.levels(appID)
        if (levels.isNotEmpty()) {
            section(header = L("nativeTaskAppWhere"), footer = L("nativeTaskAppWhereFooter")) {
                levels.forEach { level -> row(key = level) { TaskAppPicker(settings, appID, level) } }
            }
        } else if (appID == "google_tasks") {
            section { row { Text(L("nativeTaskAppGoogleList"), style = DS.Typography.body, color = DS.Palette.inkSecondary) } }
        }
        section { row(onClick = { confirmsDisconnect = true }) { SettingsButtonText(disconnect, DS.Palette.live) } }
    }
    if (confirmsDisconnect) {
        com.friend.ios.features.components.OmiConfirmationDialog(
            L("nativeTaskAppDisconnectQuestion", name),
            listOf(com.friend.ios.features.components.DialogButton(disconnect, com.friend.ios.features.components.DialogButton.Role.Destructive) {
                scope.launch {
                    capabilities.integrations.firstOrNull { it.id == appID }?.let { capabilities.disconnect(it) }
                    settings.forget(appID)
                    onBack()
                }
            }),
            onDismiss = { confirmsDisconnect = false },
        )
    }
}

/**
 * One level's `Picker`: "None", the loaded choices, and a saved choice whose list has not loaded
 * yet (by name); a spinner while loading, a dash while there is nothing to pick.
 */
@Composable
private fun TaskAppPicker(settings: TaskAppSettingsStore, app: String, level: TaskAppLevel) {
    val scope = rememberCoroutineScope()
    val options = settings.options[level].orEmpty()
    val selected = settings.selection[app]?.get(level)
    val title = taskAppLevelTitle(level)
    val label: @Composable () -> Unit = { Text(title, style = DS.Typography.body, color = DS.Palette.ink) }
    when {
        level in settings.loading -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.weight(1f)) { label() }
            OmiProgress()
        }
        options.isEmpty() && selected == null -> Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(title, style = DS.Typography.body, color = DS.Palette.inkTertiary, modifier = Modifier.weight(1f))
            Text("–", style = DS.Typography.body, color = DS.Palette.inkTertiary)
        }
        else -> {
            val none = L("nativeTaskAppNone")
            val choices = listOf<TaskAppOption?>(null) + listOfNotNull(selected?.takeIf { it !in options }) + options
            OmiPickerRow(
                choices, selected, title = { it?.name ?: none },
                onSelect = { option -> scope.launch { settings.select(app, level, option) } },
                label = label,
            )
        }
    }
}

@Composable
private fun taskAppLevelTitle(level: TaskAppLevel): String = when (level) {
    TaskAppLevel.AsanaWorkspace -> L("nativeTaskAppWorkspace")
    TaskAppLevel.AsanaProject -> L("nativeTaskAppProject")
    TaskAppLevel.ClickupTeam -> L("nativeTaskAppTeam")
    TaskAppLevel.ClickupSpace -> L("nativeTaskAppSpace")
    TaskAppLevel.ClickupList -> L("nativeTaskAppList")
}
