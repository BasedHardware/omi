package com.friend.ios

import androidx.compose.animation.Crossfade
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import com.friend.ios.design.DS
import com.friend.ios.features.auth.ConsentScreen
import com.friend.ios.features.auth.SignInScreen
import com.friend.ios.service.LocalSessionStore
import com.friend.ios.service.stores.SessionStore.Phase
import com.friend.ios.shell.MainTabView

/** Port of `RootView.swift`: switches between the app's top-level phases. */
@Composable
fun RootView() {
    val session = LocalSessionStore.current
    val context = LocalContext.current
    LaunchedEffect(Unit) {
        val options = DebugLaunchOptions.current
        if (options.resetSession) session.signOut()
        session.restore()
        // omiGiveConsent also answers the consent screen of a restored session.
        if (options.givesConsent && session.phase is Phase.Consent) session.giveConsent()
        // omiSkipOnboarding also ends an onboarding a previous launch replayed.
        if (options.skipOnboarding && session.phase is Phase.Onboarding) session.completeOnboarding()
        // omiOnboardingStep on a signed-in install replays onboarding from that step.
        if (options.onboardingStep != null) session.replayOnboarding()
        val uid = options.autoSignIn
        if (session.phase == Phase.SignedOut && uid != null) {
            session.signInLocalDev(uid)
            if (options.givesConsent) session.giveConsent()
            if (options.skipOnboarding) {
                session.giveConsent()
                session.completeOnboarding()
            }
        }
    }
    val googleSignIn = remember(context) {
        if (GoogleSignIn.supportsGoogle(context)) suspend { GoogleSignIn.credential(context) } else null
    }
    Crossfade(session.phase::class, animationSpec = DS.Motion.standard(), label = "root") { phase ->
        when (phase) {
            Phase.Launching::class -> Box(Modifier.fillMaxSize().background(DS.Palette.background))
            Phase.SignedOut::class -> SignInScreen(googleSignIn)
            Phase.Consent::class -> ConsentScreen()
            Phase.Onboarding::class -> OnboardingRoot()
            else -> MainTabView()
        }
    }
}

/** `OnboardingScreen(store: environment.makeOnboarding())`. */
@Composable
private fun OnboardingRoot() {
    val environment = (LocalContext.current.applicationContext as OmiApplication).environment
    com.friend.ios.features.onboarding.OnboardingScreen(store = remember { environment.makeOnboarding() })
}
