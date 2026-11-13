package com.friend.ios

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.LaunchedEffect
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import com.friend.ios.design.AppearanceMode
import com.friend.ios.design.LocalOmiDark
import com.friend.ios.design.OmiTheme
import com.friend.ios.features.auth.WebAuthSession
import com.friend.ios.system.PushNotifications

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        // The Omi mark on black while the process starts (Theme.Omi.Splash), then Theme.Omi.
        installSplashScreen()
        super.onCreate(savedInstanceState)
        DebugLaunchOptions.read(intent)
        val environment = (application as OmiApplication).environment
        environment.microphonePermission.attach(this) // Capture (and-capture)
        environment.deviceTools.attach(this) // "Omi asks" (and-askomi)
        environment.companionPairing.attach(this) // the Omi's companion association (and-askomi)
        DebugAskOmi.start(environment) // and-askomi, debug builds only
        environment.healthPermission.attach(this) // Health Connect (and-transcribe)
        DebugLaunchOptions.current.appearance?.let { environment.settings.appearanceMode = it }
        // A link that launched the app waits in the router until Home is on screen.
        if (savedInstanceState == null) openLink(intent)
        setContent {
            // Follows Settings > Appearance live (snapshot state in SettingsStore).
            val appearance = AppearanceMode.from(environment.settings.appearanceMode)
            OmiTheme(appearance) {
                val dark = LocalOmiDark.current
                LaunchedEffect(dark) {
                    val style = if (dark) SystemBarStyle.dark(android.graphics.Color.TRANSPARENT)
                    else SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT)
                    enableEdgeToEdge(style, style)
                }
                environment.Provide { RootView() }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        openLink(intent)
    }

    /**
     * `.onOpenURL` + the notification tap of `OmiApp.swift`: the web sign-in callback first, then
     * `omi://` and h.omi.me links, launcher shortcuts, widget and notification taps (and
     * `--es omiDeepLink omi://...` in debug builds).
     */
    private fun openLink(intent: Intent?) {
        intent ?: return
        val router = (application as OmiApplication).environment.deepLinks
        intent.data?.let { uri ->
            if (WebAuthSession.handle(uri)) return
            router.open(uri.toString())
            return
        }
        PushNotifications.link(intent)?.let {
            router.open(it)
            return
        }
        if (BuildConfig.DEBUG) intent.getStringExtra("omiDeepLink")?.let { router.open(it) }
    }
}
