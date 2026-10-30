package com.friend.ios

import android.content.Intent

/**
 * Port of `DebugLaunchOptions.swift`: the iOS `-omiX value` launch arguments as intent extras,
 * e.g. `adb shell am start -n com.friend.ios.native.dev/com.friend.ios.MainActivity
 * --es omiAutoSignIn alice --ez omiSkipOnboarding true --es omiTab memory`.
 * Ignored outside debug builds.
 */
data class DebugLaunchOptions(
    val autoSignIn: String? = null,
    val skipOnboarding: Boolean = false,
    val resetSession: Boolean = false,
    val initialTab: String? = null,
    val appearance: String? = null,
    /** `--ez omiShowSettings true`: Settings opens over Home (also implied by `omiSettingsTopic`). */
    val showsSettings: Boolean = false,
    /** `--es omiSettingsTopic listening`: the Settings screen to open (`SettingsScreen` reads it). */
    val settingsTopic: String? = null,
    // Sign-in and onboarding (and-onboarding)
    /** `--ez omiGiveConsent true`: answers the consent screen (also of a restored session). */
    val givesConsent: Boolean = false,
    /** `--es omiOnboardingStep voice`: replays onboarding from that step (`OnboardingStore.Step` name). */
    val onboardingStep: String? = null,
    /** `--ez omiOnboardingHasOmi true|false`: the answer of the `hasOmi` step for a later step. */
    val onboardingHasOmi: Boolean? = null,
    // The watch (and-wear)
    /** `--ez omiWatchPaired true|false`: onboarding behaves as if a watch is (not) paired. */
    val watchPaired: Boolean? = null,
) {
    companion object {
        var current = DebugLaunchOptions()
            private set

        fun read(intent: Intent?) {
            // Debug builds and the local-release build (both talk to the dev harness), never production.
            if (BuildConfig.OMI_APP_PROFILE != "local_dev" || intent == null) return
            current = DebugLaunchOptions(
                autoSignIn = intent.getStringExtra("omiAutoSignIn"),
                skipOnboarding = intent.getBooleanExtra("omiSkipOnboarding", false),
                resetSession = intent.getBooleanExtra("omiResetSession", false),
                initialTab = intent.getStringExtra("omiTab"),
                appearance = intent.getStringExtra("omiAppearance"),
                showsSettings = intent.getBooleanExtra("omiShowSettings", false) || intent.getStringExtra("omiSettingsTopic") != null,
                settingsTopic = intent.getStringExtra("omiSettingsTopic"),
                givesConsent = intent.getBooleanExtra("omiGiveConsent", false),
                onboardingStep = intent.getStringExtra("omiOnboardingStep"),
                onboardingHasOmi = if (intent.hasExtra("omiOnboardingHasOmi")) intent.getBooleanExtra("omiOnboardingHasOmi", false) else null,
                watchPaired = if (intent.hasExtra("omiWatchPaired")) intent.getBooleanExtra("omiWatchPaired", false) else null,
            )
            // Feature screens read their own extras (`DebugLaunch.string("omiSettingsScroll")`).
            val extras = intent.extras
            com.friend.ios.features.components.DebugLaunch.values =
                extras?.keySet()?.associateWith { key -> @Suppress("DEPRECATION") extras.get(key).toString() }.orEmpty()
        }
    }
}
